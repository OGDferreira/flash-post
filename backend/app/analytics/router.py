import asyncio
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import logging
import time
from typing import Literal
from uuid import UUID

import httpx
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import and_, func, or_, select

from app.auth.dependencies import DbSession, OwnerAccess
from app.core.crypto import decrypt_value
from app.core.time import APP_TIME_ZONE_NAME, BRAZIL_TIME_ZONE, local_day_bounds_utc, utc_now
from app.instagram.oauth import (
    INSTAGRAM_INSIGHTS_PERMISSION,
    InstagramInsightsPermissionError,
    InstagramOAuthError,
    fetch_instagram_account_insights,
    fetch_instagram_media_views,
    fetch_instagram_profile_metrics,
    fetch_instagram_views,
    instagram_api_error_detail,
)
from app.models import (
    InstagramAccount,
    InstagramPublicationJob,
    SharkLead,
    SharkTransaction,
    User,
    WorkspaceMember,
)
from app.schemas.analytics import (
    AccountConnectionRank,
    DailyAccountConnectionMetric,
    DailyPublicationMetric,
    DailyRevenueMetric,
    InstagramAccountAnalytics,
    InstagramAnalyticsSummary,
)
router = APIRouter(prefix="/api/analytics", tags=["Instagram analytics"])
logger = logging.getLogger(__name__)
_QUEUED_STATUSES = ("waiting_for_media", "queued", "publishing")
AnalyticsPeriod = Literal["today", "yesterday", "7d", "30d", "all", "custom"]


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


_META_ACCOUNT_CONCURRENCY = 6
_META_CACHE_TTL_SECONDS = 120
_META_CACHE_MAX_ENTRIES = 2_000
_meta_cache: dict[tuple, tuple[float, object]] = {}


async def _cached_meta_call(key: tuple, loader):
    """Short-lived process cache for successful Meta reads.

    The dashboard, the notification bell and the analytics page often ask for
    the same account/period within seconds of each other. Errors are never
    cached, so a reconnect or permission fix is picked up on the next call.
    """
    now = time.monotonic()
    cached = _meta_cache.get(key)
    if cached is not None and cached[0] > now:
        return cached[1]
    value = await loader()
    if len(_meta_cache) >= _META_CACHE_MAX_ENTRIES:
        for expired_key in [k for k, (expiry, _v) in _meta_cache.items() if expiry <= now]:
            _meta_cache.pop(expired_key, None)
        if len(_meta_cache) >= _META_CACHE_MAX_ENTRIES:
            _meta_cache.pop(next(iter(_meta_cache)))
    _meta_cache[key] = (now + _META_CACHE_TTL_SECONDS, value)
    return value


def _cache_window(value: datetime) -> int:
    # Minute resolution: "until now" requests inside the same minute share a key.
    return int(value.timestamp()) // 60


@dataclass
class _AccountMetaResult:
    profile: tuple[int | None, int | None, int | None] | None = None
    profile_error: str | None = None
    media_views: int | None = None
    media_views_error: str | None = None
    period_views: int | None = None
    period_views_error: str | None = None
    account_insights: dict[str, int | None] = field(default_factory=dict)
    account_insight_errors: dict[str, str] = field(default_factory=dict)
    insights_error: str | None = None
    missing_permissions: set[str] = field(default_factory=set)


async def _fetch_account_meta(
    account: InstagramAccount,
    *,
    period_start: datetime | None,
    period_end: datetime | None,
    now: datetime,
    include_account_insights: bool,
) -> _AccountMetaResult:
    result = _AccountMetaResult()
    unavailable_token = "O token de autorização não está disponível. Reconecte esta conta."
    if account.encrypted_access_token is None:
        result.profile_error = unavailable_token
        result.insights_error = unavailable_token
        return result
    try:
        access_token = decrypt_value(account.encrypted_access_token)
    except (RuntimeError, ValueError) as exc:
        message = "O FlashPost não conseguiu ler o token salvo. Reconecte esta conta."
        result.profile_error = message
        result.insights_error = message
        logger.warning(
            "Instagram metrics token could not be decrypted for account %s (%s).",
            account.id,
            type(exc).__name__,
        )
        return result
    token_key = hashlib.sha256(access_token.encode("utf-8")).hexdigest()[:16]

    try:
        live_followers, live_follows, live_media = await _cached_meta_call(
            ("profile", account.id, token_key, _cache_window(now)),
            lambda: fetch_instagram_profile_metrics(access_token),
        )
        result.profile = (live_followers, live_follows, live_media)
        missing_fields = [
            name
            for name, value in (("followers_count", live_followers), ("media_count", live_media))
            if value is None
        ]
        if missing_fields:
            result.profile_error = (
                f"A Meta não retornou os campos {', '.join(missing_fields)} nesta consulta."
            )
    except (httpx.HTTPError, InstagramOAuthError, RuntimeError, ValueError) as exc:
        result.profile_error = instagram_api_error_detail(exc)
        logger.warning(
            "Instagram profile metrics unavailable for account %s: %s",
            account.id,
            result.profile_error,
        )

    connected_at = _utc(account.connected_at)
    insight_start = max(period_start or connected_at, connected_at)
    insight_end = period_end or now
    if insight_start >= insight_end:
        # Nothing to measure yet (e.g. connected after the period ended).
        result.media_views = 0
        result.period_views = 0
        return result
    window = (_cache_window(insight_start), _cache_window(insight_end))
    try:
        if include_account_insights:
            result.account_insights, result.account_insight_errors = await _cached_meta_call(
                ("account_insights", account.id, token_key, *window),
                lambda: fetch_instagram_account_insights(
                    account.instagram_user_id, access_token, insight_start, insight_end
                ),
            )
        views, video_count, video_errors = await _cached_meta_call(
            ("media_views", account.id, token_key, *window),
            lambda: fetch_instagram_media_views(
                account.instagram_user_id, access_token, insight_start, insight_end
            ),
        )
        if video_errors:
            if any(INSTAGRAM_INSIGHTS_PERMISSION in error for error in video_errors):
                result.missing_permissions.add(INSTAGRAM_INSIGHTS_PERMISSION)
            # A partial sum would look like a real (lower) number; report it as
            # unavailable and say how many videos failed.
            result.media_views = None
            result.media_views_error = (
                "Não foi possível consultar visualizações "
                f"de {len(video_errors)} de {video_count} vídeos."
            )
        else:
            result.media_views = views
    except InstagramInsightsPermissionError:
        result.missing_permissions.add(INSTAGRAM_INSIGHTS_PERMISSION)
        result.insights_error = instagram_api_error_detail(InstagramInsightsPermissionError())
        result.account_insight_errors = {"all": result.insights_error}
        result.media_views_error = result.insights_error
        result.period_views_error = result.insights_error
        return result
    except (httpx.HTTPError, InstagramOAuthError, RuntimeError, ValueError) as exc:
        result.insights_error = instagram_api_error_detail(exc)
        result.media_views_error = result.insights_error
        logger.warning(
            "Instagram Insights unavailable for account %s: %s",
            account.id,
            result.insights_error,
        )

    try:
        result.period_views = await _cached_meta_call(
            ("period_views", account.id, token_key, *window),
            lambda: fetch_instagram_views(
                account.instagram_user_id, access_token, insight_start, insight_end
            ),
        )
    except InstagramInsightsPermissionError:
        result.missing_permissions.add(INSTAGRAM_INSIGHTS_PERMISSION)
        result.period_views_error = instagram_api_error_detail(
            InstagramInsightsPermissionError()
        )
    except (httpx.HTTPError, InstagramOAuthError, RuntimeError, ValueError) as exc:
        result.period_views_error = instagram_api_error_detail(exc)
        logger.info(
            "Instagram period views unavailable for account %s: %s",
            account.id,
            result.period_views_error,
        )
    return result


@router.get("/summary", response_model=InstagramAnalyticsSummary)
async def get_analytics_summary(
    access: OwnerAccess,
    db: DbSession,
    account_ids: list[UUID] | None = Query(default=None),
    period: AnalyticsPeriod = "7d",
    start_date: date | None = None,
    end_date: date | None = None,
    include_meta_insights: bool = False,
) -> InstagramAnalyticsSummary:
    if period == "custom":
        if start_date is None or end_date is None or end_date < start_date:
            raise HTTPException(
                status_code=422,
                detail="Período personalizado inválido. Informe datas inicial e final válidas.",
            )
    if account_ids is not None and len(set(account_ids)) != len(account_ids):
        raise HTTPException(
            status_code=422,
            detail="Each Instagram account can only be selected once.",
        )

    account_query = select(InstagramAccount).where(
        InstagramAccount.workspace_id == access.workspace.id
    )
    if account_ids is not None:
        account_query = account_query.where(InstagramAccount.id.in_(account_ids))
    accounts = (await db.scalars(account_query.order_by(InstagramAccount.username))).all()
    if account_ids is not None and len(accounts) != len(account_ids):
        raise HTTPException(
            status_code=404,
            detail="One or more selected Instagram accounts were not found in this workspace.",
        )

    selected_ids = [account.id for account in accounts]
    now = utc_now()
    today_start, today_end = local_day_bounds_utc(now)
    owner_connections_today = await db.scalar(
        select(func.count(InstagramAccount.id)).where(
            InstagramAccount.workspace_id == access.workspace.id,
            InstagramAccount.connected_by_user_id == access.workspace.owner_id,
            InstagramAccount.first_connected_at >= today_start,
            InstagramAccount.first_connected_at < today_end,
        )
    )
    team_connections_today = await db.scalar(
        select(func.count(InstagramAccount.id))
        .join(
            WorkspaceMember,
            WorkspaceMember.user_id == InstagramAccount.connected_by_user_id,
        )
        .where(
            InstagramAccount.workspace_id == access.workspace.id,
            WorkspaceMember.workspace_id == access.workspace.id,
            WorkspaceMember.role == "COLLABORATOR",
            WorkspaceMember.status == "ACTIVE",
            InstagramAccount.first_connected_at >= today_start,
            InstagramAccount.first_connected_at < today_end,
        )
    )
    active_collaborators = await db.scalar(
        select(func.count(func.distinct(WorkspaceMember.user_id))).where(
            WorkspaceMember.workspace_id == access.workspace.id,
            WorkspaceMember.role == "COLLABORATOR",
            WorkspaceMember.status == "ACTIVE",
        )
    ) or 0

    today = now.astimezone(BRAZIL_TIME_ZONE).date()
    if period == "custom":
        period_start = datetime.combine(
            start_date,
            datetime.min.time(),
            tzinfo=BRAZIL_TIME_ZONE,
        ).astimezone(timezone.utc)
        period_end = datetime.combine(
            end_date + timedelta(days=1),
            datetime.min.time(),
            tzinfo=BRAZIL_TIME_ZONE,
        ).astimezone(timezone.utc)
    elif period == "yesterday":
        period_day = today - timedelta(days=1)
        period_start = datetime.combine(
            period_day,
            datetime.min.time(),
            tzinfo=BRAZIL_TIME_ZONE,
        ).astimezone(timezone.utc)
        period_end = datetime.combine(
            today,
            datetime.min.time(),
            tzinfo=BRAZIL_TIME_ZONE,
        ).astimezone(timezone.utc)
    elif period == "today":
        period_start, _ = local_day_bounds_utc(now)
        period_end = None
    elif period == "7d":
        first_day = today - timedelta(days=6)
        period_start = datetime.combine(
            first_day,
            datetime.min.time(),
            tzinfo=BRAZIL_TIME_ZONE,
        ).astimezone(timezone.utc)
        period_end = None
    elif period == "30d":
        first_day = today - timedelta(days=29)
        period_start = datetime.combine(
            first_day,
            datetime.min.time(),
            tzinfo=BRAZIL_TIME_ZONE,
        ).astimezone(timezone.utc)
        period_end = None
    else:
        period_start = None
        period_end = None
    connection_period_end = period_end or now
    recent_chart_start = datetime.combine(
        today - timedelta(days=29),
        datetime.min.time(),
        tzinfo=BRAZIL_TIME_ZONE,
    ).astimezone(timezone.utc)
    connection_chart_start = max(period_start, recent_chart_start) if period_start else recent_chart_start
    connection_chart_end = min(connection_period_end, now)

    member_connection_conditions = [
        InstagramAccount.workspace_id == access.workspace.id,
        InstagramAccount.connected_by_user_id == User.id,
        InstagramAccount.first_connected_at.is_not(None),
        InstagramAccount.first_connected_at < connection_period_end,
    ]
    if period_start is not None:
        member_connection_conditions.append(
            InstagramAccount.first_connected_at >= period_start
        )
    member_connection_count = (
        select(func.count(InstagramAccount.id))
        .where(*member_connection_conditions)
        .correlate(User)
        .scalar_subquery()
    )
    connection_ranking_rows = (
        await db.execute(
            select(
                User.id,
                User.full_name,
                WorkspaceMember.role,
                member_connection_count.label("connected_accounts"),
            )
            .join(WorkspaceMember, WorkspaceMember.user_id == User.id)
            .where(
                WorkspaceMember.workspace_id == access.workspace.id,
                WorkspaceMember.role.in_(("OWNER", "COLLABORATOR")),
                WorkspaceMember.status == "ACTIVE",
            )
            .order_by(member_connection_count.desc(), User.full_name, User.id)
        )
    ).all()
    account_connection_ranking = [
        AccountConnectionRank(
            user_id=user_id,
            full_name=full_name,
            role=role,
            connected_accounts=connected_accounts,
        )
        for user_id, full_name, role, connected_accounts in connection_ranking_rows
    ]

    connection_dialect = db.get_bind().dialect.name
    local_connection_date = (
        func.date(
            func.timezone(APP_TIME_ZONE_NAME, InstagramAccount.first_connected_at)
        )
        if connection_dialect == "postgresql"
        else func.date(InstagramAccount.first_connected_at, "-3 hours")
    )
    connection_rows = await db.execute(
        select(
            local_connection_date,
            func.count(InstagramAccount.id),
        )
        .where(
            InstagramAccount.workspace_id == access.workspace.id,
            InstagramAccount.first_connected_at >= connection_chart_start,
            InstagramAccount.first_connected_at < connection_chart_end,
        )
        .group_by(local_connection_date)
        .order_by(local_connection_date)
    )
    connection_counts_by_day = {
        day.isoformat() if isinstance(day, date) else day: count
        for day, count in connection_rows
    }
    first_chart_day = connection_chart_start.astimezone(BRAZIL_TIME_ZONE).date()
    last_chart_day = (
        connection_chart_end - timedelta(microseconds=1)
    ).astimezone(BRAZIL_TIME_ZONE).date()
    daily_account_connections = [
        DailyAccountConnectionMetric(
            day=day,
            connected_accounts=connection_counts_by_day.get(day.isoformat(), 0),
        )
        for offset in range(max((last_chart_day - first_chart_day).days + 1, 0))
        if (day := first_chart_day + timedelta(days=offset))
    ]
    # SharkBot: one row per lead / per payment (see app.shark.ingest).
    # Leads count by join time, PIX generated by generation time, revenue by
    # approval time. Accounts are filtered only by verified attribution.
    def _in_period(column):
        conditions = []
        if period_start is not None:
            conditions.append(column >= period_start)
        if period_end is not None:
            conditions.append(column < period_end)
        return conditions

    lead_conditions = [SharkLead.workspace_id == access.workspace.id, *_in_period(SharkLead.joined_at)]
    created_conditions = [
        SharkTransaction.workspace_id == access.workspace.id,
        *_in_period(SharkTransaction.created_at_source),
    ]
    paid_conditions = [
        SharkTransaction.workspace_id == access.workspace.id,
        SharkTransaction.status == "paid",
        SharkTransaction.paid_at.is_not(None),
        *_in_period(SharkTransaction.paid_at),
    ]
    if account_ids is not None:
        lead_conditions.append(SharkLead.account_id.in_(selected_ids))
        created_conditions.append(SharkTransaction.account_id.in_(selected_ids))
        paid_conditions.append(SharkTransaction.account_id.in_(selected_ids))
    event_counts: dict[UUID, dict[str, int]] = {}
    event_amounts: dict[UUID, Decimal] = {}
    total_event_counts: dict[str, int] = {}
    for event_account_id, count in await db.execute(
        select(SharkLead.account_id, func.count(SharkLead.id))
        .where(*lead_conditions)
        .group_by(SharkLead.account_id)
    ):
        total_event_counts["lead_initiated"] = total_event_counts.get("lead_initiated", 0) + count
        if event_account_id is not None:
            event_counts.setdefault(event_account_id, {})["lead_initiated"] = count
    for event_account_id, count in await db.execute(
        select(SharkTransaction.account_id, func.count(SharkTransaction.id))
        .where(*created_conditions)
        .group_by(SharkTransaction.account_id)
    ):
        total_event_counts["pix_generated"] = total_event_counts.get("pix_generated", 0) + count
        if event_account_id is not None:
            event_counts.setdefault(event_account_id, {})["pix_generated"] = count
    pix_paid_amount = Decimal("0.00")
    for event_account_id, count, amount in await db.execute(
        select(
            SharkTransaction.account_id,
            func.count(SharkTransaction.id),
            func.coalesce(func.sum(SharkTransaction.amount), 0),
        )
        .where(*paid_conditions)
        .group_by(SharkTransaction.account_id)
    ):
        total_event_counts["pix_paid"] = total_event_counts.get("pix_paid", 0) + count
        pix_paid_amount += Decimal(str(amount or 0))
        if event_account_id is not None:
            event_counts.setdefault(event_account_id, {})["pix_paid"] = count
            event_amounts[event_account_id] = Decimal(str(amount or 0))
    paid_without_amount = (
        await db.scalar(
            select(func.count(SharkTransaction.id)).where(
                *paid_conditions, SharkTransaction.amount.is_(None)
            )
        )
        or 0
    )
    revenue_by_local_day: dict[date, Decimal] = {}
    for paid_at, amount in await db.execute(
        select(SharkTransaction.paid_at, SharkTransaction.amount)
        .where(*paid_conditions, SharkTransaction.amount.is_not(None))
        .order_by(SharkTransaction.paid_at, SharkTransaction.id)
    ):
        local_day = _utc(paid_at).astimezone(BRAZIL_TIME_ZONE).date()
        revenue_by_local_day[local_day] = revenue_by_local_day.get(
            local_day, Decimal("0.00")
        ) + Decimal(str(amount))
    daily_revenue = [
        DailyRevenueMetric(day=day, amount=amount)
        for day, amount in sorted(revenue_by_local_day.items())
    ]

    status_filters = []
    for job_status, timestamp_column in (
        ("published", InstagramPublicationJob.updated_at),
        ("failed", InstagramPublicationJob.updated_at),
        ("waiting_for_media", InstagramPublicationJob.scheduled_for),
        ("queued", InstagramPublicationJob.scheduled_for),
        ("publishing", InstagramPublicationJob.scheduled_for),
    ):
        conditions = [
            InstagramPublicationJob.status == job_status,
        ]
        if timestamp_column is not None and period_start is not None:
            conditions.append(timestamp_column >= period_start)
        if timestamp_column is not None and period_end is not None:
            conditions.append(timestamp_column < period_end)
        status_filters.append(and_(*conditions))
    grouped_jobs = await db.execute(
        select(
            InstagramPublicationJob.account_id,
            InstagramPublicationJob.status,
            func.count(InstagramPublicationJob.id),
        )
        .where(
            InstagramPublicationJob.account_id.in_(selected_ids),
            or_(*status_filters),
        )
        .group_by(InstagramPublicationJob.account_id, InstagramPublicationJob.status)
    )
    job_counts: dict[UUID, dict[str, int]] = {}
    for account_id, job_status, count in grouped_jobs:
        job_counts.setdefault(account_id, {})[job_status] = count

    dialect = db.get_bind().dialect.name
    local_job_date = (
        func.date(func.timezone(APP_TIME_ZONE_NAME, InstagramPublicationJob.updated_at))
        if dialect == "postgresql"
        else func.date(InstagramPublicationJob.updated_at, "-3 hours")
    )
    daily_query = (
        select(
            local_job_date,
            func.count(InstagramPublicationJob.id),
        )
        .where(
            InstagramPublicationJob.account_id.in_(selected_ids),
            InstagramPublicationJob.status == "published",
        )
        .group_by(local_job_date)
        .order_by(local_job_date)
    )
    if period_start is not None:
        daily_query = daily_query.where(InstagramPublicationJob.updated_at >= period_start)
    if period_end is not None:
        daily_query = daily_query.where(InstagramPublicationJob.updated_at < period_end)
    daily_rows = await db.execute(
        daily_query
    )
    daily_publications = [
        DailyPublicationMetric(day=day, published_posts=count)
        for day, count in daily_rows
    ]

    account_metrics: list[InstagramAccountAnalytics] = []
    active_accounts = 0
    errored_accounts = sum(account.status == "error" for account in accounts)
    disconnected_accounts = sum(
        account.status == "disconnected" for account in accounts
    )
    expired_accounts = 0
    active_account_list = [
        account
        for account in accounts
        if account.status == "connected" and _utc(account.token_expires_at) > now
    ]
    active_accounts = len(active_account_list)
    expired_accounts = sum(
        account.status == "connected" and _utc(account.token_expires_at) <= now
        for account in accounts
    )
    meta_results: dict[UUID, _AccountMetaResult] = {}
    if include_meta_insights and active_account_list:
        # Accounts are independent, so query Meta concurrently (bounded) instead
        # of one account after another.
        semaphore = asyncio.Semaphore(_META_ACCOUNT_CONCURRENCY)

        async def load(account: InstagramAccount) -> None:
            async with semaphore:
                meta_results[account.id] = await _fetch_account_meta(
                    account,
                    period_start=period_start,
                    period_end=period_end,
                    now=now,
                    include_account_insights=account_ids is not None,
                )

        await asyncio.gather(*(load(account) for account in active_account_list))

    missing_permissions = sorted(
        {
            permission
            for result in meta_results.values()
            for permission in result.missing_permissions
        }
    )
    profile_metrics_unavailable = any(
        result.profile_error is not None for result in meta_results.values()
    )
    # Missing permissions are reported separately (missing_permissions).
    insights_unavailable = any(
        (result.insights_error is not None or result.media_views is None)
        and not result.missing_permissions
        for result in meta_results.values()
    )
    for account in accounts:
        counts = job_counts.get(account.id, {})
        shark_counts = event_counts.get(account.id, {})
        result = meta_results.get(account.id)
        follower_count = account.follower_count
        follows_count = None
        media_count = account.media_count
        if result is not None and result.profile is not None:
            live_followers, live_follows, live_media = result.profile
            follower_count = live_followers if live_followers is not None else follower_count
            follows_count = live_follows
            media_count = live_media if live_media is not None else media_count
        insights: dict[str, int | None] = {}
        insight_metric_errors: dict[str, str] = {}
        if result is not None and account_ids is not None:
            insights = dict(result.account_insights)
            insight_metric_errors = dict(result.account_insight_errors)
            insights["views"] = result.media_views
            if result.media_views_error:
                insight_metric_errors["views"] = result.media_views_error
            insights["period_views"] = result.period_views
            if result.period_views_error:
                insight_metric_errors["period_views"] = result.period_views_error
            if result.insights_error and not insight_metric_errors.get("all"):
                if result.missing_permissions:
                    insight_metric_errors["all"] = result.insights_error
        account_metrics.append(
            InstagramAccountAnalytics(
                account_id=account.id,
                username=account.username,
                profile_picture_url=account.profile_picture_url,
                follower_count=follower_count,
                follows_count=follows_count,
                media_count=media_count,
                insights=insights,
                insights_metric_errors=insight_metric_errors,
                published_posts=counts.get("published", 0),
                queued_posts=sum(counts.get(status, 0) for status in _QUEUED_STATUSES),
                failed_posts=counts.get("failed", 0),
                status=account.status,
                insights_error=result.insights_error if result else None,
                profile_metrics_error=result.profile_error if result else None,
                leads=shark_counts.get("lead_initiated", 0),
                pix_generated=shark_counts.get("pix_generated", 0),
                pix_paid=shark_counts.get("pix_paid", 0),
                pix_paid_amount=event_amounts.get(account.id, Decimal("0.00")),
                views_count=result.media_views if result else None,
                period_views_count=result.period_views if result else None,
            )
        )

    def _complete_sum(values: list[int | None]) -> int | None:
        # A total is only meaningful when every active account answered;
        # otherwise report "unavailable" instead of a misleading partial zero.
        if not include_meta_insights or not active_account_list:
            return None
        if any(value is None for value in values):
            return None
        return sum(value for value in values if value is not None)

    views_count = _complete_sum(
        [meta_results[a.id].media_views for a in active_account_list if a.id in meta_results]
    )
    period_views_count = _complete_sum(
        [meta_results[a.id].period_views for a in active_account_list if a.id in meta_results]
    )
    views_partial = any(
        result.media_views_error is not None for result in meta_results.values()
    )

    follower_counts = [account.follower_count for account in account_metrics]
    media_counts = [account.media_count for account in account_metrics]
    return InstagramAnalyticsSummary(
        period=period,
        followers_count=(
            sum(count for count in follower_counts if count is not None)
            if accounts and all(count is not None for count in follower_counts)
            else 0 if account_ids == []
            else None
        ),
        media_count=(
            sum(count for count in media_counts if count is not None)
            if accounts and all(count is not None for count in media_counts)
            else 0 if account_ids == []
            else None
        ),
        views_count=views_count,
        period_views_count=period_views_count,
        views_partial=views_partial,
        insights_checked=include_meta_insights,
        missing_permissions=missing_permissions,
        insights_unavailable=insights_unavailable,
        profile_metrics_unavailable=profile_metrics_unavailable,
        active_accounts=active_accounts,
        errored_accounts=errored_accounts,
        disconnected_accounts=disconnected_accounts,
        expired_accounts=expired_accounts,
        active_collaborators=active_collaborators,
        published_posts=sum(account.published_posts for account in account_metrics),
        queued_posts=sum(account.queued_posts for account in account_metrics),
        failed_posts=sum(account.failed_posts for account in account_metrics),
        owner_connections_today=owner_connections_today or 0,
        team_connections_today=team_connections_today or 0,
        leads=total_event_counts.get("lead_initiated", 0),
        pix_generated=total_event_counts.get("pix_generated", 0),
        pix_paid=total_event_counts.get("pix_paid", 0),
        pix_paid_amount=pix_paid_amount.quantize(Decimal("0.01")),
        pix_paid_without_amount=paid_without_amount,
        accounts=account_metrics,
        daily_publications=daily_publications,
        daily_revenue=daily_revenue,
        daily_account_connections=daily_account_connections,
        account_connection_ranking=account_connection_ranking,
    )
