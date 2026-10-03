from datetime import datetime, timedelta, timezone
import random

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    InstagramAccount,
    InstagramLoop,
    InstagramLoopAccount,
    InstagramPublicationJob,
)

_ACTIVE_JOB_STATUSES = ("waiting_for_media", "queued", "publishing")


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


async def enqueue_due_loop_publications(
    db: AsyncSession,
    now: datetime | None = None,
) -> int:
    """Persist one idempotent publication intent per eligible account and due loop."""
    current = now or datetime.now(timezone.utc)
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
            midnight = scheduled_for.replace(hour=0, minute=0, second=0, microsecond=0)
            tomorrow = midnight + timedelta(days=1)
            daily_jobs = await db.scalar(
                select(func.count(InstagramPublicationJob.id)).where(
                    InstagramPublicationJob.loop_id == loop.id,
                    InstagramPublicationJob.account_id == account.id,
                    InstagramPublicationJob.scheduled_for >= midnight,
                    InstagramPublicationJob.scheduled_for < tomorrow,
                    InstagramPublicationJob.status.in_(
                        (*_ACTIVE_JOB_STATUSES, "published")
                    ),
                )
            )
            if (daily_jobs or 0) >= loop.daily_limit_per_account:
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

            db.add(
                InstagramPublicationJob(
                    workspace_id=loop.workspace_id,
                    loop_id=loop.id,
                    account_id=account.id,
                    scheduled_for=scheduled_for,
                    status="waiting_for_media",
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
