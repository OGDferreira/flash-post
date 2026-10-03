from datetime import datetime, timedelta, timezone
import random

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import local_day_bounds_utc
from app.models import (
    InstagramAccount,
    InstagramLoop,
    InstagramLoopAccount,
    InstagramLoopMedia,
    InstagramMedia,
    InstagramPublicationJob,
)

_ACTIVE_JOB_STATUSES = ("waiting_for_media", "queued", "publishing")
INSTAGRAM_MAX_POSTS_PER_24_HOURS = 100


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _scheduled_or_published_since(cutoff: datetime):
    return or_(
        and_(
            InstagramPublicationJob.status == "published",
            InstagramPublicationJob.updated_at >= cutoff,
        ),
        and_(
            InstagramPublicationJob.status.in_(_ACTIVE_JOB_STATUSES),
            InstagramPublicationJob.scheduled_for >= cutoff,
        ),
    )


async def _select_loop_media(
    db: AsyncSession,
    loop: InstagramLoop,
    account: InstagramAccount,
) -> InstagramMedia | None:
    media_query = (
        select(InstagramMedia)
        .join(InstagramLoopMedia, InstagramLoopMedia.media_id == InstagramMedia.id)
        .where(
            InstagramLoopMedia.loop_id == loop.id,
            InstagramMedia.workspace_id == loop.workspace_id,
        )
    )
    if loop.post_type == "reels":
        media_query = media_query.where(InstagramMedia.media_type == "video")
    elif loop.post_type == "images":
        media_query = media_query.where(InstagramMedia.media_type == "image")
    media_pool = list(
        (
            await db.scalars(
                media_query.order_by(InstagramMedia.created_at, InstagramMedia.id)
            )
        ).all()
    )
    if not media_pool:
        return None

    published_jobs = (
        await db.execute(
            select(
                InstagramPublicationJob.media_id,
                func.count(InstagramPublicationJob.id),
            )
            .where(
                InstagramPublicationJob.loop_id == loop.id,
                InstagramPublicationJob.account_id == account.id,
                InstagramPublicationJob.status == "published",
                InstagramPublicationJob.media_id.is_not(None),
            )
            .group_by(InstagramPublicationJob.media_id)
        )
    ).all()
    published_counts = {media_id: count for media_id, count in published_jobs}
    attempted_failure_ids = set(
        (
            await db.scalars(
                select(InstagramPublicationJob.media_id).where(
                    InstagramPublicationJob.loop_id == loop.id,
                    InstagramPublicationJob.account_id == account.id,
                    InstagramPublicationJob.status == "failed",
                    InstagramPublicationJob.attempts > 0,
                    InstagramPublicationJob.media_id.is_not(None),
                )
            )
        ).all()
    )
    if not loop.repeat_media:
        return next(
            (
                item
                for item in media_pool
                if item.id not in published_counts and item.id not in attempted_failure_ids
            ),
            None,
        )
    available_media = [
        item for item in media_pool if item.id not in attempted_failure_ids
    ]
    if not available_media:
        return None
    publication_count = sum(published_counts.values())
    return available_media[publication_count % len(available_media)]


async def _assign_waiting_jobs(db: AsyncSession, current: datetime) -> None:
    waiting_jobs = (
        await db.execute(
            select(InstagramPublicationJob, InstagramLoop, InstagramAccount)
            .join(InstagramLoop, InstagramLoop.id == InstagramPublicationJob.loop_id)
            .join(InstagramAccount, InstagramAccount.id == InstagramPublicationJob.account_id)
            .join(
                InstagramLoopAccount,
                InstagramLoopAccount.loop_id == InstagramLoop.id,
            )
            .where(
                InstagramPublicationJob.status == "waiting_for_media",
                InstagramPublicationJob.workspace_id == InstagramLoop.workspace_id,
                InstagramLoopAccount.account_id == InstagramAccount.id,
                InstagramLoop.status == "active",
                InstagramAccount.status == "connected",
                InstagramAccount.workspace_id == InstagramLoop.workspace_id,
                InstagramAccount.encrypted_access_token.is_not(None),
                InstagramAccount.token_expires_at > current,
            )
            .order_by(
                InstagramPublicationJob.scheduled_for,
                InstagramPublicationJob.id,
            )
            .with_for_update(skip_locked=True)
        )
    ).all()
    for job, loop, account in waiting_jobs:
        window_count = await db.scalar(
            select(func.count(InstagramPublicationJob.id)).where(
                InstagramPublicationJob.account_id == account.id,
                _scheduled_or_published_since(current - timedelta(hours=24)),
            )
        )
        if (window_count or 0) >= INSTAGRAM_MAX_POSTS_PER_24_HOURS:
            continue
        media = await _select_loop_media(db, loop, account)
        if media is not None:
            job.media_id = media.id
            job.status = "queued"


async def enqueue_due_loop_publications(
    db: AsyncSession,
    now: datetime | None = None,
) -> int:
    """Persist one idempotent publication intent per eligible account and due loop."""
    current = now or datetime.now(timezone.utc)
    await _assign_waiting_jobs(db, current)
    loops = (
        await db.scalars(
            select(InstagramLoop)
            .where(
                InstagramLoop.status == "active",
                InstagramLoop.next_run_at.is_not(None),
                InstagramLoop.next_run_at <= current,
            )
            .order_by(InstagramLoop.next_run_at, InstagramLoop.id)
            .with_for_update(skip_locked=True)
        )
    ).all()

    created_jobs = 0
    for loop in loops:
        scheduled_for = _as_utc(loop.next_run_at or current)
        accounts = (
            await db.scalars(
                select(InstagramAccount)
                .join(
                    InstagramLoopAccount,
                    InstagramLoopAccount.account_id == InstagramAccount.id,
                )
                .where(
                    InstagramLoopAccount.loop_id == loop.id,
                    InstagramAccount.workspace_id == loop.workspace_id,
                    InstagramAccount.status == "connected",
                    InstagramAccount.encrypted_access_token.is_not(None),
                    InstagramAccount.token_expires_at > current,
                )
                .order_by(InstagramAccount.id)
                .with_for_update(skip_locked=True)
            )
        ).all()

        for account in accounts:
            midnight, tomorrow = local_day_bounds_utc(scheduled_for)
            daily_jobs = await db.scalar(
                select(func.count(InstagramPublicationJob.id)).where(
                    InstagramPublicationJob.loop_id == loop.id,
                    InstagramPublicationJob.account_id == account.id,
                    or_(
                        and_(
                            InstagramPublicationJob.status == "published",
                            InstagramPublicationJob.updated_at >= midnight,
                            InstagramPublicationJob.updated_at < tomorrow,
                        ),
                        and_(
                            InstagramPublicationJob.status.in_(_ACTIVE_JOB_STATUSES),
                            InstagramPublicationJob.scheduled_for >= midnight,
                            InstagramPublicationJob.scheduled_for < tomorrow,
                        ),
                    ),
                )
            )
            if (daily_jobs or 0) >= loop.daily_limit_per_account:
                continue

            rolling_jobs = await db.scalar(
                select(func.count(InstagramPublicationJob.id)).where(
                    InstagramPublicationJob.account_id == account.id,
                    _scheduled_or_published_since(current - timedelta(hours=24)),
                )
            )
            if (rolling_jobs or 0) >= INSTAGRAM_MAX_POSTS_PER_24_HOURS:
                continue

            outstanding_job = await db.scalar(
                select(InstagramPublicationJob.id)
                .where(
                    InstagramPublicationJob.account_id == account.id,
                    InstagramPublicationJob.status.in_(_ACTIVE_JOB_STATUSES),
                )
                .limit(1)
            )
            if outstanding_job is not None:
                continue

            selected_media = await _select_loop_media(db, loop, account)

            db.add(
                InstagramPublicationJob(
                    workspace_id=loop.workspace_id,
                    loop_id=loop.id,
                    account_id=account.id,
                    media_id=selected_media.id if selected_media else None,
                    scheduled_for=scheduled_for,
                    status="queued" if selected_media else "waiting_for_media",
                )
            )
            created_jobs += 1

        interval_minutes = random.randint(
            loop.interval_min_minutes,
            loop.interval_max_minutes,
        )
        loop.last_run_at = scheduled_for
        loop.next_run_at = current + timedelta(minutes=interval_minutes)

    await db.commit()
    return created_jobs
