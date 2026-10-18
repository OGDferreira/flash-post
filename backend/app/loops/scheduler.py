"""Loop scheduling: every account walks the loop's playlist on its own.

Rules (per account, per loop):
- Videos are published in playlist order 1, 2, ..., N and then the cycle
  restarts at 1. Each account keeps its own position
  (``InstagramLoopAccountState``); accounts never share a cursor.
- The position only advances when Meta confirms the publication
  (:func:`record_publication_confirmed`). Failures and uncertain responses do
  not advance it, so the same video is retried instead of being skipped.
- At most one unfinished job exists per (loop, account) — enforced by a
  partial unique index — and an account only has one job in flight across all
  loops, so concurrent ticks/workers cannot queue duplicates.
- The next publication is scheduled ``random(min, max)`` minutes after the
  confirmed one (fixed when min == max).
- ``daily_limit_per_account`` caps confirmed + in-flight publications per
  calendar day in the application time zone; once reached the account waits
  until the next local midnight keeping its position. The count is derived
  from persisted jobs, so restarts and retries cannot reset or exceed it.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import as_utc, local_day_bounds_utc, next_local_midnight_utc
from app.models import (
    InstagramAccount,
    InstagramLoop,
    InstagramLoopAccount,
    InstagramLoopAccountState,
    InstagramLoopMedia,
    InstagramMedia,
    InstagramPublicationJob,
    User,
    Workspace,
)

ACTIVE_JOB_STATUSES = ("waiting_for_media", "queued", "publishing")
_ACTIVE_JOB_STATUSES = ACTIVE_JOB_STATUSES  # backwards-compatible name
# Instagram Content Publishing API limit (rolling 24 h, all loops together).
INSTAGRAM_MAX_POSTS_PER_24_HOURS = 100
INSTAGRAM_CAP_RECHECK = timedelta(minutes=15)

BLOCKED_DAILY_LIMIT = "daily_limit"
BLOCKED_NO_MEDIA = "no_media"
BLOCKED_INSTAGRAM_CAP = "instagram_cap"
BLOCKED_NEEDS_REVIEW = "needs_review"


def _as_utc(value: datetime) -> datetime:
    return as_utc(value)


def random_interval(loop: InstagramLoop) -> timedelta:
    low = max(int(loop.interval_min_minutes), 1)
    high = max(int(loop.interval_max_minutes), low)
    return timedelta(minutes=low if low == high else random.randint(low, high))


def next_loop_run_time(loop: InstagramLoop, from_time: datetime) -> datetime:
    return from_time + random_interval(loop)


async def loop_media_pool(db: AsyncSession, loop: InstagramLoop) -> list[InstagramMedia]:
    """Ordered playlist of the loop (upload order, then id)."""
    query = (
        select(InstagramMedia)
        .join(InstagramLoopMedia, InstagramLoopMedia.media_id == InstagramMedia.id)
        .where(
            InstagramLoopMedia.loop_id == loop.id,
            InstagramMedia.workspace_id == loop.workspace_id,
        )
    )
    if loop.post_type == "reels":
        query = query.where(InstagramMedia.media_type == "video")
    elif loop.post_type == "images":
        query = query.where(InstagramMedia.media_type == "image")
    return list(
        (await db.scalars(query.order_by(InstagramMedia.created_at, InstagramMedia.id))).all()
    )


_loop_media_pool = loop_media_pool  # backwards-compatible name


def next_media_index(state: InstagramLoopAccountState, pool: list[InstagramMedia]) -> int:
    """Index of the account's next media, resilient to playlist edits."""
    if not pool:
        return 0
    if state.last_media_id is not None:
        for index, item in enumerate(pool):
            if item.id == state.last_media_id:
                return (index + 1) % len(pool)
    return state.next_position % len(pool)


async def get_or_create_state(
    db: AsyncSession,
    loop: InstagramLoop,
    account_id,
    now: datetime,
) -> InstagramLoopAccountState:
    state = await db.get(InstagramLoopAccountState, (loop.id, account_id))
    if state is not None:
        return state
    # First time under the per-account model: continue after the last video
    # this account actually published in this loop (no reset to video 1).
    last_published = (
        await db.execute(
            select(InstagramPublicationJob.media_id, InstagramPublicationJob.published_at,
                   InstagramPublicationJob.updated_at)
            .where(
                InstagramPublicationJob.loop_id == loop.id,
                InstagramPublicationJob.account_id == account_id,
                InstagramPublicationJob.status == "published",
            )
            .order_by(
                func.coalesce(
                    InstagramPublicationJob.published_at, InstagramPublicationJob.updated_at
                ).desc(),
                InstagramPublicationJob.id.desc(),
            )
            .limit(1)
        )
    ).first()
    state = InstagramLoopAccountState(
        loop_id=loop.id,
        account_id=account_id,
        next_position=0,
        cycles_completed=0,
        last_media_id=last_published[0] if last_published else None,
        last_published_at=(
            as_utc(last_published[1] or last_published[2]) if last_published else None
        ),
        next_run_at=None,
    )
    if state.last_published_at is not None:
        state.next_run_at = state.last_published_at + timedelta(
            minutes=int(loop.interval_min_minutes)
        )
    try:
        async with db.begin_nested():
            db.add(state)
            await db.flush()
    except IntegrityError:
        state = await db.get(InstagramLoopAccountState, (loop.id, account_id), populate_existing=True)
        if state is None:  # pragma: no cover - defensive
            raise
    return state


async def count_publications_today(
    db: AsyncSession, loop_id, account_id, now: datetime
) -> int:
    """Confirmed publications of the local day plus jobs still in flight."""
    day_start, day_end = local_day_bounds_utc(now)
    job = InstagramPublicationJob
    return (
        await db.scalar(
            select(func.count(job.id)).where(
                job.loop_id == loop_id,
                job.account_id == account_id,
                or_(
                    and_(
                        job.status == "published",
                        job.published_at >= day_start,
                        job.published_at < day_end,
                    ),
                    job.status.in_(ACTIVE_JOB_STATUSES),
                ),
            )
        )
        or 0
    )


async def _rolling_account_publications(db: AsyncSession, account_id, now: datetime) -> int:
    job = InstagramPublicationJob
    return (
        await db.scalar(
            select(func.count(job.id)).where(
                job.account_id == account_id,
                or_(
                    and_(job.status == "published", job.published_at >= now - timedelta(hours=24)),
                    job.status.in_(ACTIVE_JOB_STATUSES),
                ),
            )
        )
        or 0
    )


def _take_queue_sequence(loop: InstagramLoop) -> int:
    queue_sequence = loop.next_queue_sequence
    loop.next_queue_sequence += 1
    return queue_sequence


async def _enqueue_for_account(
    db: AsyncSession,
    loop: InstagramLoop,
    account: InstagramAccount,
    state: InstagramLoopAccountState,
    pool: list[InstagramMedia],
    now: datetime,
) -> bool:
    if state.blocked_reason == BLOCKED_NEEDS_REVIEW:
        return False
    if state.next_run_at is not None and as_utc(state.next_run_at) > now:
        return False
    in_flight = await db.scalar(
        select(InstagramPublicationJob.id)
        .where(
            InstagramPublicationJob.account_id == account.id,
            InstagramPublicationJob.status.in_(ACTIVE_JOB_STATUSES),
        )
        .limit(1)
    )
    if in_flight is not None:
        return False
    if not pool:
        state.blocked_reason = BLOCKED_NO_MEDIA
        return False
    if await count_publications_today(db, loop.id, account.id, now) >= loop.daily_limit_per_account:
        state.blocked_reason = BLOCKED_DAILY_LIMIT
        state.next_run_at = next_local_midnight_utc(now)
        return False
    if await _rolling_account_publications(db, account.id, now) >= INSTAGRAM_MAX_POSTS_PER_24_HOURS:
        state.blocked_reason = BLOCKED_INSTAGRAM_CAP
        state.next_run_at = now + INSTAGRAM_CAP_RECHECK
        return False

    index = next_media_index(state, pool)
    job = InstagramPublicationJob(
        workspace_id=loop.workspace_id,
        loop_id=loop.id,
        account_id=account.id,
        media_id=pool[index].id,
        queue_sequence=_take_queue_sequence(loop),
        scheduled_for=now,
        status="queued",
    )
    try:
        async with db.begin_nested():
            db.add(job)
            await db.flush()
    except IntegrityError:
        # Another worker queued this account first (partial unique index).
        return False
    state.next_position = index
    state.blocked_reason = None
    return True


async def _eligible_loop_accounts(
    db: AsyncSession, loop: InstagramLoop, now: datetime, account_ids=None
) -> list[InstagramAccount]:
    query = (
        select(InstagramAccount)
        .join(InstagramLoopAccount, InstagramLoopAccount.account_id == InstagramAccount.id)
        .where(
            InstagramLoopAccount.loop_id == loop.id,
            InstagramAccount.workspace_id == loop.workspace_id,
            InstagramAccount.status == "connected",
            InstagramAccount.encrypted_access_token.is_not(None),
            InstagramAccount.token_expires_at > now,
        )
        .order_by(InstagramAccount.id)
    )
    if account_ids is not None:
        query = query.where(InstagramAccount.id.in_(account_ids))
    return list((await db.scalars(query)).all())


async def _refresh_loop_schedule(db: AsyncSession, loop: InstagramLoop, now: datetime) -> None:
    """Loop-level next_run_at (display only): the earliest upcoming publication
    among member accounts that are not already publishing."""
    busy = select(InstagramPublicationJob.account_id).where(
        InstagramPublicationJob.status.in_(ACTIVE_JOB_STATUSES)
    )
    rows = (
        await db.execute(
            select(InstagramLoopAccount.account_id, InstagramLoopAccountState.next_run_at, InstagramLoopAccountState.blocked_reason)
            .outerjoin(
                InstagramLoopAccountState,
                and_(
                    InstagramLoopAccountState.loop_id == InstagramLoopAccount.loop_id,
                    InstagramLoopAccountState.account_id == InstagramLoopAccount.account_id,
                ),
            )
            .where(
                InstagramLoopAccount.loop_id == loop.id,
                InstagramLoopAccount.account_id.not_in(busy),
            )
        )
    ).all()
    upcoming = [
        as_utc(next_run) if next_run is not None else now
        for _account_id, next_run, blocked in rows
        if blocked != BLOCKED_NEEDS_REVIEW
    ]
    loop.next_run_at = max(min(upcoming), now) if upcoming else None


async def reschedule_loop_accounts(db: AsyncSession, loop: InstagramLoop, now: datetime) -> int:
    """Apply a new interval to every account of the loop right away.

    Each account's next publication was drawn with the interval in force when
    it last published; after an edit it is drawn again from the new interval
    (counted from that last publication, never earlier than now), so a shorter
    or longer interval takes effect on the next post of every account instead
    of one cycle later. Accounts waiting on the daily limit, the Instagram cap
    or a manual review keep their wait.
    """
    states = (
        await db.scalars(
            select(InstagramLoopAccountState).where(InstagramLoopAccountState.loop_id == loop.id)
        )
    ).all()
    changed = 0
    for state in states:
        if state.blocked_reason in (BLOCKED_DAILY_LIMIT, BLOCKED_INSTAGRAM_CAP, BLOCKED_NEEDS_REVIEW):
            continue
        if state.last_published_at is None or state.next_run_at is None:
            continue
        state.next_run_at = max(now, as_utc(state.last_published_at) + random_interval(loop))
        changed += 1
    return changed


async def enqueue_loop_publications_now(
    db: AsyncSession,
    loop: InstagramLoop,
    accounts: list[InstagramAccount],
    now: datetime | None = None,
) -> int:
    """Queue the next video for the given accounts if their interval elapsed.

    Used when a loop is created/resumed or accounts are attached. It never
    re-posts the previous video: each account continues from its own position.
    """
    loop = await db.scalar(
        select(InstagramLoop)
        .where(InstagramLoop.id == loop.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if loop is None or loop.status != "active":
        return 0
    current = now or datetime.now(timezone.utc)
    pool = await loop_media_pool(db, loop)
    created = 0
    for account in accounts:
        state = await get_or_create_state(db, loop, account.id, current)
        if state.blocked_reason in (BLOCKED_DAILY_LIMIT, BLOCKED_INSTAGRAM_CAP, BLOCKED_NO_MEDIA):
            state.blocked_reason = None
            if state.next_run_at is not None and state.last_published_at is not None:
                state.next_run_at = max(
                    current,
                    as_utc(state.last_published_at)
                    + timedelta(minutes=int(loop.interval_min_minutes)),
                )
        if await _enqueue_for_account(db, loop, account, state, pool, current):
            created += 1
    if created:
        loop.last_run_at = current
    await db.flush()
    await _refresh_loop_schedule(db, loop, current)
    await db.flush()
    return created


def workspaces_allowed_to_post():
    """Workspaces whose owner is approved and not blocked by the Super Admin."""
    return (
        select(Workspace.id)
        .join(User, User.id == Workspace.owner_id)
        .where(User.is_active.is_(True), User.is_approved.is_(True))
    )


async def enqueue_due_loop_publications(
    db: AsyncSession,
    now: datetime | None = None,
) -> int:
    """Queue the next video for every account whose own schedule is due."""
    current = now or datetime.now(timezone.utc)
    loops = (
        await db.scalars(
            select(InstagramLoop)
            .where(
                InstagramLoop.status == "active",
                InstagramLoop.workspace_id.in_(workspaces_allowed_to_post()),
            )
            .order_by(InstagramLoop.id)
            .with_for_update(skip_locked=True)
        )
    ).all()
    created = 0
    for loop in loops:
        accounts = await _eligible_loop_accounts(db, loop, current)
        if not accounts:
            continue
        pool = await loop_media_pool(db, loop)
        loop_created = 0
        for account in accounts:
            state = await get_or_create_state(db, loop, account.id, current)
            if (
                state.blocked_reason == BLOCKED_NO_MEDIA
                and pool
            ):
                state.blocked_reason = None
            if await _enqueue_for_account(db, loop, account, state, pool, current):
                loop_created += 1
        if loop_created:
            loop.last_run_at = current
        created += loop_created
        await db.flush()
        await _refresh_loop_schedule(db, loop, current)
    await db.commit()
    return created


async def record_publication_confirmed(
    db: AsyncSession,
    job: InstagramPublicationJob,
    published_at: datetime,
) -> None:
    """Mark the job published and advance only that account's position."""
    job.status = "published"
    job.published_at = published_at
    job.last_error = None
    job.error_category = None
    job.next_retry_at = None
    loop = await db.get(InstagramLoop, job.loop_id)
    if loop is None:
        return
    state = await get_or_create_state(db, loop, job.account_id, published_at)
    pool = await loop_media_pool(db, loop)
    index = next((i for i, item in enumerate(pool) if item.id == job.media_id), None)
    if index is not None:
        following = index + 1
        if following >= len(pool):
            following = 0
            state.cycles_completed += 1
        state.next_position = following
        state.last_media_id = job.media_id
    state.last_published_at = published_at
    state.blocked_reason = None
    state.next_run_at = published_at + random_interval(loop)


async def record_publication_given_up(
    db: AsyncSession,
    job: InstagramPublicationJob,
    now: datetime,
    *,
    skip_media: bool = False,
    needs_review: bool = False,
) -> None:
    """Final failure: keep the position (retry the same video later).

    ``skip_media`` is used only for videos Meta can never process (format
    errors) so one broken file cannot block the account forever.
    ``needs_review`` blocks the account until someone checks Instagram,
    because the publication may have happened.
    """
    loop = await db.get(InstagramLoop, job.loop_id)
    if loop is None:
        return
    state = await get_or_create_state(db, loop, job.account_id, now)
    if needs_review:
        state.blocked_reason = BLOCKED_NEEDS_REVIEW
        state.next_run_at = None
        return
    if skip_media and job.media_id is not None:
        pool = await loop_media_pool(db, loop)
        index = next((i for i, item in enumerate(pool) if item.id == job.media_id), None)
        if index is not None:
            following = index + 1
            if following >= len(pool):
                following = 0
                state.cycles_completed += 1
            state.next_position = following
            state.last_media_id = job.media_id
    state.next_run_at = now + timedelta(minutes=int(loop.interval_min_minutes))
