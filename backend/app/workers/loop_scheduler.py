import asyncio
import logging

from app.core.database import get_session_factory
from app.loops.scheduler import enqueue_due_loop_publications

logger = logging.getLogger(__name__)


async def run_loop_scheduler_tick() -> int:
    async with get_session_factory()() as db:
        created_jobs = await enqueue_due_loop_publications(db)
    logger.info("Loop scheduler prepared %s publication jobs.", created_jobs)
    return created_jobs


if __name__ == "__main__":
    asyncio.run(run_loop_scheduler_tick())
