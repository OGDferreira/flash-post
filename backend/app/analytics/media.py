"""Top publications and account engagement ranking from synced Insights."""

import time
import uuid
from datetime import date, datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select

from app.analytics.periods import AnalyticsPeriod, period_bounds, period_label
from app.auth.dependencies import DbSession, OwnerAccess, require_csrf
from app.core.time import APP_TIME_ZONE_NAME, utc_now
from app.instagram.insights_sync import sync_account_media_insights
from app.models import InstagramAccount, InstagramMediaInsight

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
