import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import text

from app.core.database import get_engine
from app.workers.loop_scheduler import run_loop_scheduler_tick

logger = logging.getLogger(__name__)
_POSTGRES_ADVISORY_LOCK_KEY = 731904281
_LOOP_TICK_INTERVAL_SECONDS = 60


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
    return scheduler
