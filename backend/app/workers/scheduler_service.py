import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import text

from app.core.config import get_settings
from app.core.database import get_engine, get_session_factory
from app.instagram.insights_sync import sync_workspace_accounts
from app.models import InstagramAccount
from app.notifications.goals import run_daily_views_goal_tick
from app.workers.loop_scheduler import run_loop_scheduler_tick

logger = logging.getLogger(__name__)
_POSTGRES_ADVISORY_LOCK_KEY = 731904281
_GOALS_ADVISORY_LOCK_KEY = 731904282
_INSIGHTS_ADVISORY_LOCK_KEY = 731904283
INSIGHTS_SYNC_HOURS = 3


async def _sync_insights_once() -> None:
    from datetime import datetime, timezone

    from sqlalchemy import select

    async with get_session_factory()() as db:
        account_ids = (
            await db.scalars(
                select(InstagramAccount.id).where(
                    InstagramAccount.status == "connected",
                    InstagramAccount.encrypted_access_token.is_not(None),
                    InstagramAccount.token_expires_at > datetime.now(timezone.utc),
                )
            )
        ).all()
    for account_id in account_ids:
        # One session per account so a failure never blocks the others.
        async with get_session_factory()() as db:
            try:
                await sync_workspace_accounts(db, [account_id])
            except Exception as exc:
                await db.rollback()
                logger.warning("Insights sync skipped account %s (%s).", account_id, type(exc).__name__)


async def _run_insights_sync_with_database_lock() -> None:
    engine = get_engine()
    try:
        if engine.dialect.name != "postgresql":
            await _sync_insights_once()
            return
        async with engine.connect() as connection:
            acquired = await connection.scalar(
                text("SELECT pg_try_advisory_lock(:lock_key)"),
                {"lock_key": _INSIGHTS_ADVISORY_LOCK_KEY},
            )
            if not acquired:
                return
            try:
                await _sync_insights_once()
            finally:
                await connection.execute(
                    text("SELECT pg_advisory_unlock(:lock_key)"),
                    {"lock_key": _INSIGHTS_ADVISORY_LOCK_KEY},
                )
    except Exception as exc:
        logger.error("Insights sync failed (%s); it will retry.", type(exc).__name__)
_LOOP_TICK_INTERVAL_SECONDS = 60


async def _run_goals_once() -> None:
    async with get_session_factory()() as db:
        delivered = await run_daily_views_goal_tick(db)
    if delivered:
        logger.info("Daily views goals: %s push notification(s) delivered.", delivered)


async def _run_goals_tick_with_database_lock() -> None:
    """Separate lock from the loop worker so goal checks never delay publishing."""
    engine = get_engine()
    try:
        if engine.dialect.name != "postgresql":
            await _run_goals_once()
            return
        async with engine.connect() as connection:
            acquired = await connection.scalar(
                text("SELECT pg_try_advisory_lock(:lock_key)"),
                {"lock_key": _GOALS_ADVISORY_LOCK_KEY},
            )
            if not acquired:
                return
            try:
                await _run_goals_once()
            finally:
                await connection.execute(
                    text("SELECT pg_advisory_unlock(:lock_key)"),
                    {"lock_key": _GOALS_ADVISORY_LOCK_KEY},
                )
    except Exception as exc:
        logger.error("Daily views goal tick failed (%s); it will retry.", type(exc).__name__)


async def _run_tick_with_database_lock() -> None:
    engine = get_engine()
    if engine.dialect.name != "postgresql":
        try:
            await run_loop_scheduler_tick()
        except Exception as exc:
            logger.error(
                "Loop scheduler tick failed before completion (%s); "
                "the next scheduled tick will retry.",
                type(exc).__name__,
            )
        return

    try:
        async with engine.connect() as connection:
            acquired = await connection.scalar(
                text("SELECT pg_try_advisory_lock(:lock_key)"),
                {"lock_key": _POSTGRES_ADVISORY_LOCK_KEY},
            )
            if not acquired:
                logger.debug("Another FlashPost instance owns the scheduler lock.")
                return
            try:
                await run_loop_scheduler_tick()
            except Exception as exc:
                logger.error(
                    "Loop scheduler tick failed before completion (%s); "
                    "the next scheduled tick will retry.",
                    type(exc).__name__,
                )
            finally:
                await connection.execute(
                    text("SELECT pg_advisory_unlock(:lock_key)"),
                    {"lock_key": _POSTGRES_ADVISORY_LOCK_KEY},
                )
    except Exception as exc:
        logger.error(
            "Loop scheduler could not acquire or release its database lock (%s).",
            type(exc).__name__,
        )


def create_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        _run_tick_with_database_lock,
        trigger="interval",
        seconds=_LOOP_TICK_INTERVAL_SECONDS,
        id="flashpost-loop-and-token-worker",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=30,
    )
    scheduler.add_job(
        _run_insights_sync_with_database_lock,
        trigger="interval",
        hours=INSIGHTS_SYNC_HOURS,
        id="flashpost-insights-sync",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=600,
    )
    scheduler.add_job(
        _run_goals_tick_with_database_lock,
        trigger="interval",
        minutes=get_settings().daily_views_goal_check_minutes,
        id="flashpost-daily-views-goals",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=120,
    )
    return scheduler
