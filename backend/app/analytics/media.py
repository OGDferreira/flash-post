"""Top publications and account engagement ranking from synced Insights."""

import asyncio
import logging
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select

from app.analytics.periods import AnalyticsPeriod, period_bounds, period_label
from app.auth.dependencies import DbSession, OwnerAccess, require_csrf
from app.core.time import APP_TIME_ZONE, APP_TIME_ZONE_NAME, local_date, utc_now
from app.instagram.daily_views_sync import sync_account_daily_views
from app.core.database import get_session_factory
from app.instagram.insights_sync import sync_account_media_insights, sync_workspace_accounts
from app.models import InstagramAccount, InstagramAccountDailyViews, InstagramMediaInsight

router = APIRouter(prefix="/api/analytics", tags=["Publication insights"])

ENGAGEMENT_FORMULA = (
    "Taxa de engajamento = (curtidas + comentários + compartilhamentos + salvamentos) "
    "÷ visualizações × 100. Só é calculada quando a Meta informou as cinco métricas "
    "da publicação; caso contrário aparece como indisponível."
)
_SYNC_COOLDOWN_SECONDS = 600
_last_manual_sync: dict[uuid.UUID, float] = {}


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def interactions_of(row: InstagramMediaInsight) -> int | None:
    parts = (row.likes, row.comments, row.shares, row.saves)
    return None if any(part is None for part in parts) else sum(parts)


def engagement_rate_of(row: InstagramMediaInsight) -> float | None:
    interactions = interactions_of(row)
    if interactions is None or not row.views:
        return None
    return round(interactions / row.views * 100, 2)


class PublicationInsight(BaseModel):
    id: uuid.UUID
    account_id: uuid.UUID
    username: str
    ig_media_id: str
    media_type: str | None
    media_product_type: str | None
    permalink: str | None
    thumbnail_url: str | None
    caption: str | None
    posted_at: datetime
    views: int | None
    reach: int | None
    likes: int | None
    comments: int | None
    shares: int | None
    saves: int | None
    interactions: int | None
    engagement_rate: float | None
    metrics_error: str | None
    synced_at: datetime


class PublicationInsightsResponse(BaseModel):
    period: str
    period_label: str
    time_zone: str
    sort: str
    order: str
    formula: str
    scope: str
    items: list[PublicationInsight]
    accounts_never_synced: list[str]


class AccountEngagementRow(BaseModel):
    account_id: uuid.UUID
    username: str
    profile_picture_url: str | None
    publications: int
    publications_with_complete_metrics: int
    views: int | None
    interactions: int | None
    engagement_rate: float | None
    synced_at: datetime | None
    sync_error: str | None


class AccountEngagementResponse(BaseModel):
    period: str
    period_label: str
    order: str
    formula: str
    rows: list[AccountEngagementRow]


def _window(start, end):
    conditions = []
    if start is not None:
        conditions.append(InstagramMediaInsight.posted_at >= start)
    if end is not None:
        conditions.append(InstagramMediaInsight.posted_at < end)
    return conditions


@router.get("/videos", response_model=PublicationInsightsResponse)
async def top_publications(
    access: OwnerAccess,
    db: DbSession,
    period: AnalyticsPeriod = "7d",
    start_date: date | None = None,
    end_date: date | None = None,
    account_id: uuid.UUID | None = None,
    media: Literal["videos", "all"] = "videos",
    sort: Literal["views", "engagement_rate", "interactions", "reach", "posted_at"] = "views",
    order: Literal["desc", "asc"] = "desc",
    limit: int = Query(default=50, ge=1, le=200),
) -> PublicationInsightsResponse:
    start, end = period_bounds(period, start_date, end_date, utc_now())
    query = (
        select(InstagramMediaInsight, InstagramAccount.username)
        .join(InstagramAccount, InstagramAccount.id == InstagramMediaInsight.account_id)
        .where(
            InstagramMediaInsight.workspace_id == access.workspace.id,
            InstagramAccount.workspace_id == access.workspace.id,
            *_window(start, end),
        )
    )
    if account_id is not None:
        query = query.where(InstagramMediaInsight.account_id == account_id)
    if media == "videos":
        query = query.where(InstagramMediaInsight.media_type == "VIDEO")
    rows = (await db.execute(query)).all()
    items = [
        PublicationInsight(
            id=row.id,
            account_id=row.account_id,
            username=username,
            ig_media_id=row.ig_media_id,
            media_type=row.media_type,
            media_product_type=row.media_product_type,
            permalink=row.permalink,
            thumbnail_url=row.thumbnail_url,
            caption=row.caption,
            posted_at=_utc(row.posted_at),
            views=row.views,
            reach=row.reach,
            likes=row.likes,
            comments=row.comments,
            shares=row.shares,
            saves=row.saves,
            interactions=interactions_of(row),
            engagement_rate=engagement_rate_of(row),
            metrics_error=row.metrics_error,
            synced_at=_utc(row.synced_at),
        )
        for row, username in rows
    ]
    # Unavailable values always sort last, whatever the direction.
    known = [item for item in items if getattr(item, sort) is not None]
    unknown = [item for item in items if getattr(item, sort) is None]
    known.sort(key=lambda item: getattr(item, sort), reverse=order == "desc")
    never_synced_query = select(InstagramAccount.username).where(
        InstagramAccount.workspace_id == access.workspace.id,
        InstagramAccount.status == "connected",
        InstagramAccount.insights_synced_at.is_(None),
    )
    if account_id is not None:
        never_synced_query = never_synced_query.where(InstagramAccount.id == account_id)
    return PublicationInsightsResponse(
        period=period,
        period_label=period_label(start, end),
        time_zone=APP_TIME_ZONE_NAME,
        sort=sort,
        order=order,
        formula=ENGAGEMENT_FORMULA,
        scope=(
            "Publicações feitas no período, com métricas vitalícias (acumuladas desde a "
            "publicação) na última sincronização."
        ),
        items=(known + unknown)[:limit],
        accounts_never_synced=list((await db.scalars(never_synced_query)).all()),
    )


@router.get("/engagement-ranking", response_model=AccountEngagementResponse)
async def engagement_ranking(
    access: OwnerAccess,
    db: DbSession,
    period: AnalyticsPeriod = "30d",
    start_date: date | None = None,
    end_date: date | None = None,
    order: Literal["desc", "asc"] = "desc",
) -> AccountEngagementResponse:
    start, end = period_bounds(period, start_date, end_date, utc_now())
    accounts = (
        await db.scalars(
            select(InstagramAccount)
            .where(InstagramAccount.workspace_id == access.workspace.id)
            .order_by(InstagramAccount.username)
        )
    ).all()
    media_rows = (
        await db.scalars(
            select(InstagramMediaInsight).where(
                InstagramMediaInsight.workspace_id == access.workspace.id, *_window(start, end)
            )
        )
    ).all()
    by_account: dict[uuid.UUID, list[InstagramMediaInsight]] = {}
    for row in media_rows:
        by_account.setdefault(row.account_id, []).append(row)
    result: list[AccountEngagementRow] = []
    for account in accounts:
        rows = by_account.get(account.id, [])
        if not rows and account.status != "connected":
            continue
        complete = [row for row in rows if row.views and interactions_of(row) is not None]
        views = sum(row.views for row in complete) if complete else None
        interactions = sum(interactions_of(row) for row in complete) if complete else None
        result.append(
            AccountEngagementRow(
                account_id=account.id,
                username=account.username,
                profile_picture_url=account.profile_picture_url,
                publications=len(rows),
                publications_with_complete_metrics=len(complete),
                views=views,
                interactions=interactions,
                # Weighted by views: total interactions / total views.
                engagement_rate=round(interactions / views * 100, 2) if views else None,
                synced_at=_utc(account.insights_synced_at),
                sync_error=account.insights_sync_error,
            )
        )
    known = [row for row in result if row.engagement_rate is not None]
    unknown = [row for row in result if row.engagement_rate is None]
    known.sort(key=lambda row: (row.engagement_rate, row.views or 0), reverse=order == "desc")
    return AccountEngagementResponse(
        period=period,
        period_label=period_label(start, end),
        order=order,
        formula=(
            ENGAGEMENT_FORMULA
            + " Para a conta: soma das interações ÷ soma das visualizações das publicações "
            "do período com dados completos."
        ),
        rows=known + unknown,
    )


@router.post(
    "/accounts/{account_id}/sync",
    response_model=AccountEngagementRow,
    dependencies=[Depends(require_csrf)],
)
async def sync_account_now(
    account_id: uuid.UUID, access: OwnerAccess, db: DbSession
) -> AccountEngagementRow:
    account = await db.scalar(
        select(InstagramAccount).where(
            InstagramAccount.id == account_id,
            InstagramAccount.workspace_id == access.workspace.id,
        )
    )
    if account is None:
        raise HTTPException(status_code=404, detail="Conta não encontrada.")
    if account.status != "connected":
        raise HTTPException(status_code=409, detail="Reconecte a conta para sincronizar.")
    now = time.monotonic()
    if now - _last_manual_sync.get(account.id, 0.0) < _SYNC_COOLDOWN_SECONDS:
        raise HTTPException(
            status_code=429, detail="Sincronização recente; aguarde alguns minutos."
        )
    _last_manual_sync[account.id] = now
    synced = await sync_account_media_insights(db, account)
    await sync_account_daily_views(db, account)
    return AccountEngagementRow(
        account_id=account.id,
        username=account.username,
        profile_picture_url=account.profile_picture_url,
        publications=synced,
        publications_with_complete_metrics=0,
        views=None,
        interactions=None,
        engagement_rate=None,
        synced_at=_utc(account.insights_synced_at),
        sync_error=account.insights_sync_error,
    )



# ------------------------------------------------- workspace background sync
logger = logging.getLogger(__name__)
_WORKSPACE_SYNC_CONCURRENCY = 4
_WORKSPACE_SYNC_COOLDOWN_SECONDS = 600
_workspace_syncs: dict[uuid.UUID, dict] = {}


class WorkspaceSyncStatus(BaseModel):
    running: bool
    total: int
    done: int
    failed: int
    started_at: datetime | None
    finished_at: datetime | None


def _sync_status(workspace_id: uuid.UUID) -> WorkspaceSyncStatus:
    state = _workspace_syncs.get(workspace_id) or {}
    return WorkspaceSyncStatus(
        running=bool(state.get("running")),
        total=state.get("total", 0),
        done=state.get("done", 0),
        failed=state.get("failed", 0),
        started_at=state.get("started_at"),
        finished_at=state.get("finished_at"),
    )


async def _run_workspace_sync(workspace_id: uuid.UUID, account_ids: list[uuid.UUID]) -> None:
    state = _workspace_syncs[workspace_id]
    semaphore = asyncio.Semaphore(_WORKSPACE_SYNC_CONCURRENCY)

    async def one(account_id: uuid.UUID) -> None:
        async with semaphore:
            # One session per account so a failure never blocks the others.
            async with get_session_factory()() as session:
                try:
                    await sync_workspace_accounts(session, [account_id])
                except Exception as exc:  # noqa: BLE001 - keep syncing the rest
                    await session.rollback()
                    state["failed"] += 1
                    logger.warning("Workspace sync skipped account %s (%s).", account_id, type(exc).__name__)
            state["done"] += 1

    try:
        await asyncio.gather(*(one(account_id) for account_id in account_ids))
    finally:
        state["running"] = False
        state["finished_at"] = utc_now()


@router.post("/sync", response_model=WorkspaceSyncStatus, dependencies=[Depends(require_csrf)])
async def sync_workspace_in_background(
    access: OwnerAccess, db: DbSession, force: bool = False
) -> WorkspaceSyncStatus:
    """Start syncing every connected account in the background and return at once.

    The UI polls ``GET /sync-status``; a recent or running sync is not repeated.
    """
    workspace_id = access.workspace.id
    state = _workspace_syncs.get(workspace_id)
    if state and state.get("running"):
        return _sync_status(workspace_id)
    finished = state.get("finished_at") if state else None
    if (
        not force
        and finished is not None
        and (utc_now() - finished).total_seconds() < _WORKSPACE_SYNC_COOLDOWN_SECONDS
    ):
        return _sync_status(workspace_id)
    account_ids = list(
        await db.scalars(
            select(InstagramAccount.id).where(
                InstagramAccount.workspace_id == workspace_id,
                InstagramAccount.status == "connected",
                InstagramAccount.encrypted_access_token.is_not(None),
                InstagramAccount.token_expires_at > utc_now(),
            )
        )
    )
    _workspace_syncs[workspace_id] = {
        "running": bool(account_ids),
        "total": len(account_ids),
        "done": 0,
        "failed": 0,
        "started_at": utc_now(),
        "finished_at": None if account_ids else utc_now(),
    }
    if account_ids:
        task = asyncio.create_task(_run_workspace_sync(workspace_id, account_ids))
        _workspace_syncs[workspace_id]["task"] = task  # keep a reference
    return _sync_status(workspace_id)


@router.get("/sync-status", response_model=WorkspaceSyncStatus)
async def workspace_sync_status(access: OwnerAccess) -> WorkspaceSyncStatus:
    return _sync_status(access.workspace.id)

# ------------------------------------------------------------ views per day
VIEWS_DEFINITIONS = {
    "received_views": (
        "Visualizações recebidas no dia: o que a Meta informa que o perfil recebeu naquele dia "
        "(qualquer vídeo, antigo ou novo). Não é acumulado."
    ),
    "published_videos_views": (
        "Visualizações acumuladas dos vídeos publicados no dia: soma das visualizações vitalícias "
        "(desde a publicação até a última sincronização) apenas dos vídeos postados naquele dia."
    ),
    "provisional": (
        "Os últimos dias podem subir: a Meta pode levar até 48 h para consolidar os números."
    ),
    "grouping": f"Dias no fuso {APP_TIME_ZONE_NAME}.",
}


class DailyViewsPoint(BaseModel):
    day: date
    received_views: int | None
    received_accounts: int
    expected_accounts: int
    published_videos: int
    published_videos_with_views: int
    published_videos_views: int | None
    provisional: bool


class DailyViewsResponse(BaseModel):
    period: str
    period_label: str
    time_zone: str
    days: list[DailyViewsPoint]
    received_total: int | None
    received_days_complete: int
    received_days_total: int
    published_videos_views_total: int | None
    synced_at: datetime | None
    definitions: dict[str, str]


@router.get("/views-daily", response_model=DailyViewsResponse)
async def views_daily(
    access: OwnerAccess,
    db: DbSession,
    period: AnalyticsPeriod = "30d",
    start_date: date | None = None,
    end_date: date | None = None,
    account_id: uuid.UUID | None = None,
) -> DailyViewsResponse:
    now = utc_now()
    start, end = period_bounds(period, start_date, end_date, now)
    today = local_date(now)
    accounts_query = select(InstagramAccount).where(
        InstagramAccount.workspace_id == access.workspace.id,
        InstagramAccount.status == "connected",
    )
    if account_id is not None:
        accounts_query = accounts_query.where(InstagramAccount.id == account_id)
    accounts = (await db.scalars(accounts_query)).all()
    if account_id is not None and not accounts:
        raise HTTPException(status_code=404, detail="Conta não encontrada ou desconectada.")
    ids = [account.id for account in accounts]

    # "All time" starts at the first day with any data (never an empty decade).
    first_day = local_date(start, APP_TIME_ZONE) if start is not None else None
    last_day = min(local_date(end - timedelta(microseconds=1), APP_TIME_ZONE), today) if end else today
    daily_rows = (
        await db.execute(
            select(InstagramAccountDailyViews.account_id, InstagramAccountDailyViews.day, InstagramAccountDailyViews.views)
            .where(
                InstagramAccountDailyViews.workspace_id == access.workspace.id,
                InstagramAccountDailyViews.account_id.in_(ids or [uuid.uuid4()]),
            )
        )
    ).all()
    media_rows = (
        await db.scalars(
            select(InstagramMediaInsight).where(
                InstagramMediaInsight.workspace_id == access.workspace.id,
                InstagramMediaInsight.account_id.in_(ids or [uuid.uuid4()]),
                InstagramMediaInsight.media_type == "VIDEO",
                *_window(start, end),
            )
        )
    ).all()
    if first_day is None:
        candidates = [day for _a, day, _v in daily_rows] + [
            local_date(_utc(row.posted_at)) for row in media_rows
        ]
        first_day = min(candidates) if candidates else today
    first_day = max(first_day, today - timedelta(days=366))

    received: dict[date, dict[uuid.UUID, int]] = {}
    for row_account, day, views in daily_rows:
        received.setdefault(day, {})[row_account] = views
    seen_media: set[tuple[uuid.UUID, str]] = set()
    published: dict[date, list[InstagramMediaInsight]] = {}
    for row in media_rows:
        key = (row.account_id, row.ig_media_id)
        if key in seen_media:  # a video is counted once
            continue
        seen_media.add(key)
        published.setdefault(local_date(_utc(row.posted_at)), []).append(row)

    points: list[DailyViewsPoint] = []
    day = first_day
    while day <= last_day:
        day_end = _day_end(day)
        expected = sum(1 for account in accounts if _utc(account.connected_at) < day_end)
        reported = received.get(day, {})
        reporting = sum(1 for account in accounts if account.id in reported)
        complete = expected > 0 and reporting >= expected
        videos = published.get(day, [])
        with_views = [video for video in videos if video.views is not None]
        points.append(
            DailyViewsPoint(
                day=day,
                received_views=sum(reported.get(account.id, 0) for account in accounts) if complete else None,
                received_accounts=reporting,
                expected_accounts=expected,
                published_videos=len(videos),
                published_videos_with_views=len(with_views),
                published_videos_views=(
                    sum(video.views for video in with_views)
                    if videos and len(with_views) == len(videos)
                    else None
                ),
                provisional=day >= today - timedelta(days=2),
            )
        )
        day += timedelta(days=1)
    complete_points = [point for point in points if point.received_views is not None]
    pub_known = [point for point in points if point.published_videos_views is not None]
    synced = max((account.insights_synced_at for account in accounts if account.insights_synced_at), default=None)
    return DailyViewsResponse(
        period=period,
        period_label=period_label(start, end),
        time_zone=APP_TIME_ZONE_NAME,
        days=points,
        # A total of incomplete days would look exact; it is only given when every day is complete.
        received_total=(
            sum(point.received_views for point in complete_points)
            if points and len(complete_points) == len(points)
            else None
        ),
        received_days_complete=len(complete_points),
        received_days_total=len(points),
        published_videos_views_total=(
            sum(point.published_videos_views for point in pub_known) if pub_known else None
        ),
        synced_at=_utc(synced),
        definitions=VIEWS_DEFINITIONS,
    )


def _day_end(day: date) -> datetime:
    from app.core.time import day_bounds_utc

    return day_bounds_utc(day)[1]
