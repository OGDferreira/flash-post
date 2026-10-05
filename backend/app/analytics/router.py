from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import logging
from typing import Literal
from uuid import UUID

import httpx
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import and_, func, or_, select

from app.auth.dependencies import DbSession, OwnerAccess
from app.core.crypto import decrypt_value
from app.core.time import BRAZIL_TIME_ZONE, local_day_bounds_utc, utc_now
from app.instagram.oauth import (
    INSTAGRAM_INSIGHTS_PERMISSION,
    InstagramInsightsPermissionError,
    InstagramOAuthError,
    fetch_instagram_profile_metrics,
    fetch_instagram_views,
    instagram_api_error_detail,
)
from app.models import (
    InstagramAccount,
    InstagramPublicationJob,
    SharkEvent,
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
            func.timezone("America/Sao_Paulo", InstagramAccount.first_connected_at)
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
    event_conditions = [SharkEvent.workspace_id == access.workspace.id]
    if period_start is not None:
        event_conditions.append(SharkEvent.occurred_at >= period_start)
    if period_end is not None:
        event_conditions.append(SharkEvent.occurred_at < period_end)
    if account_ids is not None:
        event_conditions.append(
            or_(SharkEvent.account_id.in_(selected_ids), SharkEvent.account_id.is_(None))
        )
    event_rows = await db.execute(
        select(
            SharkEvent.account_id,
            SharkEvent.event_type,
            func.count(SharkEvent.id),
            func.coalesce(func.sum(SharkEvent.amount), 0),
        )
        .where(*event_conditions)
        .group_by(SharkEvent.account_id, SharkEvent.event_type)
    )
    event_counts: dict[UUID, dict[str, int]] = {}
    event_amounts: dict[UUID, Decimal] = {}
    total_event_counts: dict[str, int] = {}
    pix_paid_amount = Decimal("0.00")
    for event_account_id, event_type, count, amount in event_rows:
        total_event_counts[event_type] = total_event_counts.get(event_type, 0) + count
        if event_account_id is not None:
            account_counts = event_counts.setdefault(event_account_id, {})
            account_counts[event_type] = account_counts.get(event_type, 0) + count
            if event_type == "pix_paid":
                event_amounts[event_account_id] = event_amounts.get(
                    event_account_id, Decimal("0.00")
                ) + Decimal(str(amount or 0))
        if event_type == "pix_paid":
            pix_paid_amount += Decimal(str(amount or 0))

    dialect = db.get_bind().dialect.name
    local_event_date = (
        func.date(func.timezone("America/Sao_Paulo", SharkEvent.occurred_at))
        if dialect == "postgresql"
        else func.date(SharkEvent.occurred_at, "-3 hours")
    )
    daily_revenue_query = (
        select(local_event_date, func.coalesce(func.sum(SharkEvent.amount), 0))
        .where(
            *event_conditions,
            SharkEvent.event_type == "pix_paid",
        )
        .group_by(local_event_date)
        .order_by(local_event_date)
    )
    daily_revenue = [
        DailyRevenueMetric(day=day, amount=amount)
        for day, amount in await db.execute(daily_revenue_query)
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
        func.date(func.timezone("America/Sao_Paulo", InstagramPublicationJob.updated_at))
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
    views_count = 0
    missing_permissions: list[str] = []
    insights_unavailable = False
    profile_metrics_unavailable = False
    refreshed_profile_metrics: dict[
        UUID, tuple[int | None, int | None, int | None]
    ] = {}
    profile_metric_errors: dict[UUID, str] = {}
    insights_errors: dict[UUID, str] = {}
    for account in accounts:
        counts = job_counts.get(account.id, {})
        shark_counts = event_counts.get(account.id, {})
        published = counts.get("published", 0)
        queued = sum(counts.get(status, 0) for status in _QUEUED_STATUSES)
        failed = counts.get("failed", 0)
        token_expires_at = _utc(account.token_expires_at)
        if account.status == "connected" and _utc(account.token_expires_at) > now:
            active_accounts += 1
            if include_meta_insights and account.encrypted_access_token is None:
                profile_metrics_unavailable = True
                insights_unavailable = True
                profile_metric_errors[account.id] = (
                    "O token de autorização não está disponível. Reconecte esta conta."
                )
                insights_errors[account.id] = (
                    "O token de autorização não está disponível. Reconecte esta conta."
                )
            elif include_meta_insights:
                try:
                    access_token = decrypt_value(account.encrypted_access_token)
                except (RuntimeError, ValueError) as exc:
                    profile_metrics_unavailable = True
                    insights_unavailable = True
                    profile_metric_errors[account.id] = (
                        "O FlashPost não conseguiu ler o token salvo. Reconecte esta conta."
                    )
                    insights_errors[account.id] = (
                        "O FlashPost não conseguiu ler o token salvo. Reconecte esta conta."
                    )
                    logger.warning(
                        "Instagram metrics token could not be decrypted for account %s (%s).",
                        account.id,
                        type(exc).__name__,
                    )
                else:
                    try:
                        live_followers, live_follows, live_media = (
                            await fetch_instagram_profile_metrics(
                                access_token
                            )
                        )
                        if (
                            live_followers is None
                            or live_media is None
                        ):
                            profile_metrics_unavailable = True
                            missing_fields = [
                                field
                                for field, value in (
                                    ("followers_count", live_followers),
                                    ("media_count", live_media),
                                )
                                if value is None
                            ]
                            profile_metric_errors[account.id] = (
                                "A Meta não retornou os campos "
                                f"{', '.join(missing_fields)} nesta consulta."
                            )
                        refreshed_profile_metrics[account.id] = (
                            live_followers
                            if live_followers is not None
                            else account.follower_count,
                            live_follows,
                            live_media if live_media is not None else account.media_count,
                        )
                    except (
                        httpx.HTTPError,
                        InstagramOAuthError,
                        RuntimeError,
                        ValueError,
                    ) as exc:
                        profile_metrics_unavailable = True
                        profile_metric_errors[account.id] = instagram_api_error_detail(
                            exc
                        )
                        logger.warning(
                            "Instagram profile metrics unavailable for account %s: %s",
                            account.id,
                            profile_metric_errors[account.id],
                        )
                    insight_start = period_start or _utc(account.connected_at)
                    insight_start = max(insight_start, _utc(account.connected_at))
                    insight_end = period_end or now
                    if insight_start < insight_end:
                        try:
                            views_count += await fetch_instagram_views(
                                account.instagram_user_id,
                                access_token,
                                insight_start,
                                insight_end,
                            )
                        except InstagramInsightsPermissionError:
                            missing_permissions.append(INSTAGRAM_INSIGHTS_PERMISSION)
                            insights_errors[account.id] = instagram_api_error_detail(
                                InstagramInsightsPermissionError()
                            )
                        except (
                            httpx.HTTPError,
                            InstagramOAuthError,
                            RuntimeError,
                            ValueError,
                        ) as exc:
                            insights_unavailable = True
                            insights_errors[account.id] = instagram_api_error_detail(
                                exc
                            )
                            logger.warning(
                                "Instagram Insights unavailable for account %s: %s",
                                account.id,
                                insights_errors[account.id],
                            )
        elif account.status == "connected" and token_expires_at <= now:
            expired_accounts += 1
        account_metrics.append(
            InstagramAccountAnalytics(
                account_id=account.id,
                username=account.username,
                profile_picture_url=account.profile_picture_url,
                follower_count=refreshed_profile_metrics.get(
                    account.id,
                    (account.follower_count, None, account.media_count),
                )[0],
                media_count=refreshed_profile_metrics.get(
                    account.id,
                    (account.follower_count, None, account.media_count),
                )[2],
                published_posts=published,
                queued_posts=queued,
                failed_posts=failed,
                status=account.status,
                insights_error=insights_errors.get(account.id),
                profile_metrics_error=profile_metric_errors.get(account.id),
                leads=shark_counts.get("lead_initiated", 0),
                pix_generated=shark_counts.get("pix_generated", 0),
                pix_paid=shark_counts.get("pix_paid", 0),
                pix_paid_amount=event_amounts.get(account.id, Decimal("0.00")),
            )
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
        missing_permissions=sorted(set(missing_permissions)),
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
        accounts=account_metrics,
        daily_publications=daily_publications,
        daily_revenue=daily_revenue,
        daily_account_connections=daily_account_connections,
        account_connection_ranking=account_connection_ranking,
    )
