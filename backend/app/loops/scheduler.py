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

    last_media_id = await db.scalar(
        select(InstagramPublicationJob.media_id)
        .where(
            InstagramPublicationJob.loop_id == loop.id,
            InstagramPublicationJob.account_id == account.id,
            InstagramPublicationJob.media_id.is_not(None),
            or_(
                InstagramPublicationJob.status.in_(("published", "queued", "publishing")),
                and_(
                    InstagramPublicationJob.status == "failed",
                    InstagramPublicationJob.attempts > 0,
                ),
            ),
        )
        .order_by(
            InstagramPublicationJob.scheduled_for.desc(),
            InstagramPublicationJob.id.desc(),
        )
        .limit(1)
    )
    if last_media_id is None:
        return media_pool[0]

    last_index = next(
        (index for index, item in enumerate(media_pool) if item.id == last_media_id),
        None,
    )
    if last_index is None:
        return media_pool[0]
    next_index = last_index + 1
    if next_index >= len(media_pool):
        return media_pool[0] if loop.repeat_media else None
    return media_pool[next_index]


async def _next_loop_media_for_new_accounts(
    db: AsyncSession,
    loop: InstagramLoop,
) -> tuple[bool, InstagramMedia | None]:
    media_pool = list(
        (
            await db.scalars(
                select(InstagramMedia)
                .join(InstagramLoopMedia, InstagramLoopMedia.media_id == InstagramMedia.id)
                .where(
                    InstagramLoopMedia.loop_id == loop.id,
                    InstagramMedia.workspace_id == loop.workspace_id,
                    (
                        InstagramMedia.media_type == "video"
                        if loop.post_type == "reels"
                        else InstagramMedia.media_type == "image"
                        if loop.post_type == "images"
                        else InstagramMedia.media_type.in_(("image", "video"))
                    ),
                )
                .order_by(InstagramMedia.created_at, InstagramMedia.id)
            )
        ).all()
    )
    if not media_pool:
        return False, None

    current_batch_media_id = await db.scalar(
        select(InstagramPublicationJob.media_id)
        .where(
            InstagramPublicationJob.loop_id == loop.id,
            InstagramPublicationJob.status.in_(("queued", "publishing")),
            InstagramPublicationJob.media_id.is_not(None),
        )
        .order_by(
            InstagramPublicationJob.scheduled_for.desc(),
            InstagramPublicationJob.id.desc(),
        )
        .limit(1)
    )
    if current_batch_media_id is not None:
        current = next(
            (item for item in media_pool if item.id == current_batch_media_id),
            None,
        )
        if current is not None:
            return True, current

    latest_job = await db.execute(
        select(InstagramPublicationJob.media_id)
        .where(
            InstagramPublicationJob.loop_id == loop.id,
            InstagramPublicationJob.media_id.is_not(None),
            or_(
                InstagramPublicationJob.status == "published",
                and_(
                    InstagramPublicationJob.status == "failed",
                    InstagramPublicationJob.attempts > 0,
                ),
            ),
        )
        .order_by(
            InstagramPublicationJob.scheduled_for.desc(),
            InstagramPublicationJob.id.desc(),
        )
        .limit(1)
    )
    last_media_id = latest_job.scalar_one_or_none()
    if last_media_id is None:
        return False, None
    last_index = next(
        (index for index, item in enumerate(media_pool) if item.id == last_media_id),
        None,
    )
    if last_index is None:
        return True, media_pool[0]
    next_index = last_index + 1
    if next_index >= len(media_pool):
        return True, media_pool[0] if loop.repeat_media else None
    return True, media_pool[next_index]


async def enqueue_loop_publications_now(
    db: AsyncSession,
    loop: InstagramLoop,
    accounts: list[InstagramAccount],
    now: datetime | None = None,
) -> int:
    """Queue the current playlist item for each eligible newly attached account."""
    current = now or datetime.now(timezone.utc)
    has_loop_history, shared_media = await _next_loop_media_for_new_accounts(db, loop)
    created_jobs = 0
    for account in accounts:
        daily_start, daily_end = local_day_bounds_utc(current)
        daily_count = await db.scalar(
            select(func.count(InstagramPublicationJob.id)).where(
                InstagramPublicationJob.account_id == account.id,
                or_(
                    and_(
                        InstagramPublicationJob.status == "published",
                        InstagramPublicationJob.updated_at >= daily_start,
                        InstagramPublicationJob.updated_at < daily_end,
                    ),
                    and_(
                        InstagramPublicationJob.status.in_(_ACTIVE_JOB_STATUSES),
                        InstagramPublicationJob.scheduled_for >= daily_start,
                        InstagramPublicationJob.scheduled_for < daily_end,
                    ),
                ),
            )
        )
        if (daily_count or 0) >= loop.daily_limit_per_account:
            continue
        rolling_count = await db.scalar(
            select(func.count(InstagramPublicationJob.id)).where(
                InstagramPublicationJob.account_id == account.id,
                _scheduled_or_published_since(current - timedelta(hours=24)),
            )
        )
        if (rolling_count or 0) >= INSTAGRAM_MAX_POSTS_PER_24_HOURS:
            continue
        active_job = await db.scalar(
            select(InstagramPublicationJob.id)
            .where(
                InstagramPublicationJob.account_id == account.id,
                InstagramPublicationJob.status.in_(_ACTIVE_JOB_STATUSES),
            )
            .limit(1)
        )
        if active_job is not None:
            continue

        selected_media = (
            shared_media
            if has_loop_history
            else await _select_loop_media(db, loop, account)
        )
        if selected_media is None:
            continue
        db.add(
            InstagramPublicationJob(
                workspace_id=loop.workspace_id,
                loop_id=loop.id,
                account_id=account.id,
                media_id=selected_media.id,
                scheduled_for=current,
                status="queued",
            )
        )
        created_jobs += 1
    await db.flush()
    return created_jobs


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
