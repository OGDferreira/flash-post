from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select

from app.auth.dependencies import DbSession, WorkspaceMemberAccess
from app.models import InstagramAccount, InstagramPublicationJob
from app.schemas.analytics import (
    DailyPublicationMetric,
    InstagramAccountAnalytics,
    InstagramAnalyticsSummary,
)

router = APIRouter(prefix="/api/analytics", tags=["Instagram analytics"])
_QUEUED_STATUSES = ("waiting_for_media", "queued", "publishing")


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


@router.get("/summary", response_model=InstagramAnalyticsSummary)
async def get_analytics_summary(
    access: WorkspaceMemberAccess,
    db: DbSession,
    account_ids: list[UUID] | None = Query(default=None),
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
    grouped_jobs = await db.execute(
        select(
            InstagramPublicationJob.account_id,
            InstagramPublicationJob.status,
            func.count(InstagramPublicationJob.id),
        )
        .where(InstagramPublicationJob.account_id.in_(selected_ids))
        .group_by(InstagramPublicationJob.account_id, InstagramPublicationJob.status)
    )
    job_counts: dict[UUID, dict[str, int]] = {}
    for account_id, job_status, count in grouped_jobs:
        job_counts.setdefault(account_id, {})[job_status] = count

    now = datetime.now(timezone.utc)
    daily_rows = await db.execute(
        select(
            func.date(InstagramPublicationJob.updated_at),
            func.count(InstagramPublicationJob.id),
        )
        .where(
            InstagramPublicationJob.account_id.in_(selected_ids),
            InstagramPublicationJob.status == "published",
            InstagramPublicationJob.updated_at >= now - timedelta(days=6),
        )
        .group_by(func.date(InstagramPublicationJob.updated_at))
        .order_by(func.date(InstagramPublicationJob.updated_at))
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
