from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import and_, func, or_, select

from app.auth.dependencies import DbSession, WorkspaceMemberAccess
from app.core.time import BRAZIL_TIME_ZONE, local_day_bounds_utc, utc_now
from app.models import InstagramAccount, InstagramPublicationJob
from app.schemas.analytics import (
    DailyPublicationMetric,
    InstagramAccountAnalytics,
    InstagramAnalyticsSummary,
)

router = APIRouter(prefix="/api/analytics", tags=["Instagram analytics"])
_QUEUED_STATUSES = ("waiting_for_media", "queued", "publishing")
AnalyticsPeriod = Literal["today", "yesterday", "7d", "30d", "all"]


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


@router.get("/summary", response_model=InstagramAnalyticsSummary)
async def get_analytics_summary(
    access: WorkspaceMemberAccess,
    db: DbSession,
    account_ids: list[UUID] | None = Query(default=None),
    period: AnalyticsPeriod = "7d",
) -> InstagramAnalyticsSummary:
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

    if not accounts:
        return InstagramAnalyticsSummary(
            period=period,
            followers_count=0 if account_ids == [] else None,
            media_count=0 if account_ids == [] else None,
            active_accounts=0,
            published_posts=0,
            queued_posts=0,
            failed_posts=0,
            accounts=[],
            daily_publications=[],
        )

    selected_ids = [account.id for account in accounts]
    now = utc_now()
    today = now.astimezone(BRAZIL_TIME_ZONE).date()
    if period == "yesterday":
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

    status_filters = []
    for job_status, timestamp_column in (
        ("published", InstagramPublicationJob.updated_at),
        ("failed", InstagramPublicationJob.updated_at),
        ("waiting_for_media", None),
        ("queued", None),
        ("publishing", None),
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
    for account in accounts:
        counts = job_counts.get(account.id, {})
        published = counts.get("published", 0)
        queued = sum(counts.get(status, 0) for status in _QUEUED_STATUSES)
        failed = counts.get("failed", 0)
        if account.status == "connected" and _utc(account.token_expires_at) > now:
            active_accounts += 1
        account_metrics.append(
            InstagramAccountAnalytics(
                account_id=account.id,
                username=account.username,
                profile_picture_url=account.profile_picture_url,
                follower_count=account.follower_count,
                media_count=account.media_count,
                published_posts=published,
                queued_posts=queued,
                failed_posts=failed,
            )
        )

    follower_counts = [account.follower_count for account in accounts]
    media_counts = [account.media_count for account in accounts]
    return InstagramAnalyticsSummary(
        period=period,
        followers_count=(
            sum(count for count in follower_counts if count is not None)
            if all(count is not None for count in follower_counts)
            else None
        ),
        media_count=(
            sum(count for count in media_counts if count is not None)
            if all(count is not None for count in media_counts)
            else None
        ),
        active_accounts=active_accounts,
        published_posts=sum(account.published_posts for account in account_metrics),
        queued_posts=sum(account.queued_posts for account in account_metrics),
        failed_posts=sum(account.failed_posts for account in account_metrics),
        accounts=account_metrics,
        daily_publications=daily_publications,
    )
