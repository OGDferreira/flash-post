"""Funnel scheduling: auto activate/deactivate a bot's funnel.

A launch funnel can be held "aguardando" (bot inactive) until a set time, then turned on
automatically, and turned off again at a set time or once it reaches a sales target. Runs
on the bot tick (every few seconds), so activation lands within seconds of the set time.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import TgBot, TgOrder

logger = logging.getLogger(__name__)


async def _paid_sales_since(db: AsyncSession, bot_id, since: datetime | None) -> int:
    query = select(func.count()).select_from(TgOrder).where(
        TgOrder.bot_id == bot_id, TgOrder.status == "paid"
    )
    if since is not None:
        query = query.where(func.coalesce(TgOrder.paid_at, TgOrder.created_at) >= since)
    return int(await db.scalar(query) or 0)


async def apply_bot_schedules(db: AsyncSession) -> int:
    """Flip bots whose scheduled activation/deactivation is due. Returns how many changed."""
    now = datetime.now(timezone.utc)
    changed = 0

    # 1) Activate bots whose start time has arrived (they were held inactive until now).
    due_on = (
        await db.scalars(
            select(TgBot).where(
                TgBot.is_active.is_(False),
                TgBot.scheduled_activate_at.is_not(None),
                TgBot.scheduled_activate_at <= now,
            )
        )
    ).all()
    for bot in due_on:
        bot.is_active = True
        bot.schedule_activated_at = now
        bot.scheduled_activate_at = None
        changed += 1
        logger.info("Funnel schedule: bot %s auto-activated.", bot.id)

    # 2) Deactivate bots whose end time has arrived.
    due_off = (
        await db.scalars(
            select(TgBot).where(
                TgBot.is_active.is_(True),
                TgBot.scheduled_deactivate_at.is_not(None),
                TgBot.scheduled_deactivate_at <= now,
            )
        )
    ).all()
    for bot in due_off:
        _deactivate(bot, "tempo")
        changed += 1

    # 3) Deactivate bots that hit their sales target.
    capped = (
        await db.scalars(
            select(TgBot).where(
                TgBot.is_active.is_(True),
                TgBot.auto_deactivate_after_sales.is_not(None),
            )
        )
    ).all()
    for bot in capped:
        target = bot.auto_deactivate_after_sales or 0
        if target <= 0:
            continue
        sales = await _paid_sales_since(db, bot.id, bot.schedule_activated_at)
        if sales >= target:
            _deactivate(bot, f"{sales} vendas")

            changed += 1

    if changed:
        await db.commit()
    return changed


def _deactivate(bot: TgBot, why: str) -> None:
    bot.is_active = False
    bot.scheduled_deactivate_at = None
    bot.auto_deactivate_after_sales = None
    bot.schedule_activated_at = None
    logger.info("Funnel schedule: bot %s auto-deactivated (%s).", bot.id, why)
