"""FlashBot conversion numbers for one operation (never mixes workspaces).

* leads      = leads that entered in the period (one per Telegram user per bot)
* sales      = paid orders in the period (upsells count as sales)
* buyers     = distinct leads with a paid order in the period
* conversion = buyers ÷ leads × 100 (each lead counts once, so it stays ≤ 100%)
* ticket     = confirmed gross revenue ÷ sales
"""

import uuid
from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import BRAZIL_TIME_ZONE
from app.models import TgLead, TgOrder


def _f(value) -> float:
    return round(float(value or 0), 2)


def _rate(buyers: int, leads: int) -> float:
    return round(min(100.0, 100 * buyers / leads), 1) if leads else 0.0


async def conversion_stats(db: AsyncSession, workspace_id: uuid.UUID, start: datetime, end: datetime) -> dict:
    lead_rows = (
        await db.execute(
            select(TgLead.id, TgLead.bot_id, TgLead.flow_id, TgLead.created_at).where(
                TgLead.workspace_id == workspace_id, TgLead.created_at >= start, TgLead.created_at < end
            )
        )
    ).all()
    order_rows = (
        await db.execute(
            select(TgOrder.lead_id, TgOrder.bot_id, TgOrder.flow_id, TgOrder.amount, TgOrder.paid_at).where(
                TgOrder.workspace_id == workspace_id, TgOrder.status == "paid",
                TgOrder.paid_at >= start, TgOrder.paid_at < end,
            )
        )
    ).all()

    def bucket():
        return {"leads": 0, "sales": 0, "revenue": Decimal("0"), "buyers": set()}

    total, per_flow, per_bot, per_day = bucket(), defaultdict(bucket), defaultdict(bucket), defaultdict(bucket)
    for _lead_id, bot_id, flow_id, created in lead_rows:
        day = created.astimezone(BRAZIL_TIME_ZONE).date().isoformat()
        for target in (total, per_bot[bot_id], per_day[day]) + ((per_flow[flow_id],) if flow_id else ()):
            target["leads"] += 1
    for lead_id, bot_id, flow_id, amount, paid in order_rows:
        day = paid.astimezone(BRAZIL_TIME_ZONE).date().isoformat()
        for target in (total, per_bot[bot_id], per_day[day]) + ((per_flow[flow_id],) if flow_id else ()):
            target["sales"] += 1
            target["revenue"] += Decimal(amount or 0)
            target["buyers"].add(lead_id)

    def out(data: dict) -> dict:
        sales = data["sales"]
        return {
            "leads": data["leads"], "sales": sales, "buyers": len(data["buyers"]),
            "revenue": _f(data["revenue"]), "conversion": _rate(len(data["buyers"]), data["leads"]),
            "ticket": _f(data["revenue"] / sales) if sales else 0.0,
        }

    days, cursor = [], start.astimezone(BRAZIL_TIME_ZONE).date()
    last = (end - timedelta(microseconds=1)).astimezone(BRAZIL_TIME_ZONE).date()
    while cursor <= last and len(days) < 400:
        key = cursor.isoformat()
        days.append({"date": key, **out(per_day[key])})
        cursor += timedelta(days=1)
    return {
        "totals": out(total),
        "series": days,
        "flows": {str(k): out(v) for k, v in per_flow.items()},
        "bots": {str(k): out(v) for k, v in per_bot.items()},
    }
