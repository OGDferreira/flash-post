from datetime import datetime, timedelta, timezone
import random

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

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
MAX_CATCH_UP_RUNS_PER_TICK = 1


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def next_loop_run_time(loop: InstagramLoop, from_time: datetime) -> datetime:
    interval_minutes = random.randint(
        loop.interval_min_minutes,
        loop.interval_max_minutes,
    )
    return from_time + timedelta(minutes=interval_minutes)


def _scheduled_or_published_since(cutoff: datetime):
    return or_(
        and_(
            InstagramPublicationJob.status == "published",
            InstagramPublicationJob.updated_at >= cutoff,
        ),
        InstagramPublicationJob.status.in_(_ACTIVE_JOB_STATUSES),
        and_(
            InstagramPublicationJob.status == "failed",
            InstagramPublicationJob.attempts > 0,
            InstagramPublicationJob.updated_at >= cutoff,
        ),
    )


async def _loop_media_pool(
    db: AsyncSession,
    loop: InstagramLoop,
) -> list[InstagramMedia]:
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
    return list(
        (
            await db.scalars(
                media_query.order_by(InstagramMedia.created_at, InstagramMedia.id)
            )
        ).all()
    )


async def _ensure_loop_cursor(
    db: AsyncSession,
    loop: InstagramLoop,
    pool: list[InstagramMedia],
) -> bool:
    """Initialise the shared loop cursor; returns whether the loop has history."""
    if loop.next_media_index is not None:
        return True
    last_media_id = await db.scalar(
        select(InstagramPublicationJob.media_id)
        .where(
            InstagramPublicationJob.loop_id == loop.id,
            InstagramPublicationJob.media_id.is_not(None),
            or_(
                InstagramPublicationJob.status.in_(
                    ("queued", "publishing", "published")
                ),
                and_(
                    InstagramPublicationJob.status == "failed",
                    InstagramPublicationJob.attempts > 0,
                ),
            ),
        )
        .order_by(
            InstagramPublicationJob.scheduled_for.desc(),
            InstagramPublicationJob.created_at.desc(),
            InstagramPublicationJob.id.desc(),
        )
        .limit(1)
    )
    last_index = next(
        (index for index, item in enumerate(pool) if item.id == last_media_id),
        None,
    )
    loop.next_media_index = last_index + 1 if last_index is not None else 0
    return last_index is not None


def _reserve_round_media(
    loop: InstagramLoop,
    pool: list[InstagramMedia],
) -> InstagramMedia:
    """Advance the shared cursor once; every account in the round posts this media."""
    index = loop.next_media_index % len(pool)
    loop.next_media_index = index + 1
    return pool[index]


def _current_round_media(
    loop: InstagramLoop,
    pool: list[InstagramMedia],
) -> InstagramMedia:
    """Media of the round already in progress, without advancing the cursor."""
    return pool[(loop.next_media_index - 1) % len(pool)]


def _take_queue_sequence(loop: InstagramLoop) -> int:
    queue_sequence = loop.next_queue_sequence
    loop.next_queue_sequence += 1
    return queue_sequence


async def _reserve_next_loop_media(
    db: AsyncSession,
    loop: InstagramLoop,
    media_pool: list[InstagramMedia] | None = None,
) -> InstagramMedia | None:
    pool = media_pool if media_pool is not None else await _loop_media_pool(db, loop)
    if not pool:
        return None
    await _ensure_loop_cursor(db, loop, pool)
    return _reserve_round_media(loop, pool)


async def enqueue_loop_publications_now(
    db: AsyncSession,
    loop: InstagramLoop,
    accounts: list[InstagramAccount],
    now: datetime | None = None,
) -> int:
    """Queue the next sequential playlist item for each newly attached account."""
    loop = await db.scalar(
        select(InstagramLoop)
        .where(InstagramLoop.id == loop.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if loop is None:
        return 0
    current = now or datetime.now(timezone.utc)
    media_pool = await _loop_media_pool(db, loop)
    round_media: InstagramMedia | None = None
    created_jobs = 0
    for account in accounts:
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

        if not media_pool:
            continue
        # Todas as contas anexadas postam o mesmo vídeo da rodada em andamento.
        if round_media is None:
            if await _ensure_loop_cursor(db, loop, media_pool):
                round_media = _current_round_media(loop, media_pool)
            else:
                round_media = _reserve_round_media(loop, media_pool)
        selected_media = round_media
        queue_sequence = _take_queue_sequence(loop)
        db.add(
            InstagramPublicationJob(
                workspace_id=loop.workspace_id,
                loop_id=loop.id,
                account_id=account.id,
                media_id=selected_media.id,
                queue_sequence=queue_sequence,
                scheduled_for=current,
                status="queued",
            )
        )
        created_jobs += 1
    await db.flush()
    return created_jobs


async def _assign_waiting_jobs(db: AsyncSession, current: datetime) -> None:
    loop_ids = (
        await db.scalars(
            select(InstagramLoop.id)
            .join(
                InstagramPublicationJob,
                InstagramPublicationJob.loop_id == InstagramLoop.id,
            )
            .where(
                InstagramPublicationJob.status == "waiting_for_media",
                InstagramLoop.status == "active",
            )
            .distinct()
        )
    ).all()
    for loop_id in loop_ids:
        loop = await db.scalar(
            select(InstagramLoop)
            .where(InstagramLoop.id == loop_id, InstagramLoop.status == "active")
            .with_for_update(skip_locked=True)
        )
        if loop is None:
            continue
        media_pool = await _loop_media_pool(db, loop)
        round_media: InstagramMedia | None = None
        waiting_jobs = (
            await db.execute(
                select(InstagramPublicationJob, InstagramAccount)
                .join(
                    InstagramAccount,
                    InstagramAccount.id == InstagramPublicationJob.account_id,
                )
                .join(
                    InstagramLoopAccount,
                    InstagramLoopAccount.account_id == InstagramAccount.id,
                )
                .where(
                    InstagramPublicationJob.loop_id == loop.id,
                    InstagramPublicationJob.status == "waiting_for_media",
                    InstagramLoopAccount.loop_id == loop.id,
                    InstagramAccount.status == "connected",
                    InstagramAccount.workspace_id == loop.workspace_id,
                    InstagramAccount.encrypted_access_token.is_not(None),
                    InstagramAccount.token_expires_at > current,
                )
                .order_by(
                    InstagramPublicationJob.scheduled_for,
                    InstagramPublicationJob.account_id,
                )
                .with_for_update(skip_locked=True)
            )
        ).all()
        for job, account in waiting_jobs:
            window_count = await db.scalar(
                select(func.count(InstagramPublicationJob.id)).where(
                    InstagramPublicationJob.account_id == account.id,
                    InstagramPublicationJob.id != job.id,
                    _scheduled_or_published_since(current - timedelta(hours=24)),
                )
            )
            if (window_count or 0) >= INSTAGRAM_MAX_POSTS_PER_24_HOURS:
                continue
            if job.media_id is not None:
                job.status = "queued"
                continue
            if round_media is None:
                round_media = await _reserve_next_loop_media(db, loop, media_pool)
            media = round_media
            if media is not None:
                job.media_id = media.id
                job.queue_sequence = _take_queue_sequence(loop)
                job.status = "queued"


async def enqueue_due_loop_publications(
    db: AsyncSession,
    now: datetime | None = None,
) -> int:
    """Persist sequential publication intents for all due loop intervals."""
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

        media_pool = await _loop_media_pool(db, loop)
        catch_up_runs = 0
        while (
            scheduled_for <= current
            and catch_up_runs < MAX_CATCH_UP_RUNS_PER_TICK
        ):
            round_media: InstagramMedia | None = None
            for account in accounts:
                rolling_jobs = await db.scalar(
                    select(func.count(InstagramPublicationJob.id)).where(
                        InstagramPublicationJob.account_id == account.id,
                        _scheduled_or_published_since(
                            current - timedelta(hours=24)
                        ),
                    )
                )
                if (rolling_jobs or 0) >= INSTAGRAM_MAX_POSTS_PER_24_HOURS:
                    continue

                # Um único vídeo por rodada: todas as contas postam o mesmo.
                if round_media is None:
                    round_media = await _reserve_next_loop_media(
                        db, loop, media_pool
                    )
                selected_media = round_media
                queue_sequence = _take_queue_sequence(loop)
                db.add(
                    InstagramPublicationJob(
                        workspace_id=loop.workspace_id,
                        loop_id=loop.id,
                        account_id=account.id,
                        media_id=selected_media.id if selected_media else None,
                        queue_sequence=queue_sequence,
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
            scheduled_for += timedelta(minutes=interval_minutes)
            catch_up_runs += 1

        loop.next_run_at = scheduled_for

    await db.commit()
    return created_jobs
