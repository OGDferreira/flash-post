"""Flash bot funnel by bot: leads -> Pix -> sale -> each upsell step (offered, Pix, paid)."""

import uuid
from datetime import date
from decimal import Decimal

from fastapi import APIRouter
from sqlalchemy import func, select

from app.analytics.periods import AnalyticsPeriod, period_bounds, period_label
from app.auth.dependencies import DbSession, OwnerAccess
from app.core.time import utc_now
from app.models import TgBot, TgJob, TgLead, TgOrder

router = APIRouter(prefix="/api/analytics", tags=["Flash bot funnel"])


def _rate(part: int, base: int) -> float | None:
    return round(part / base * 100, 1) if base else None


@router.get("/flash-funnel")
async def flash_funnel(
    access: OwnerAccess,
    db: DbSession,
    period: AnalyticsPeriod = "30d",
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict:
    start, end = period_bounds(period, start_date, end_date, utc_now())
    workspace_id = access.workspace.id

    def window(column):
        return [c for c in ((column >= start) if start else None, (column < end) if end else None) if c is not None]

    bots = {
        bot_id: name
        for bot_id, name in await db.execute(select(TgBot.id, TgBot.name).where(TgBot.workspace_id == workspace_id))
    }
    rows: dict[uuid.UUID, dict] = {
        bot_id: {"leads": 0, "pix": 0, "sales": 0, "revenue": Decimal("0.00"), "upsells": {}} for bot_id in bots
    }

    def step(bot_id, index: int) -> dict:
        return rows[bot_id]["upsells"].setdefault(index, {"offered": 0, "pix": 0, "paid": 0, "revenue": Decimal("0.00")})

    for bot_id, total in await db.execute(
        select(TgLead.bot_id, func.count(TgLead.id))
        .where(TgLead.workspace_id == workspace_id, *window(TgLead.created_at))
        .group_by(TgLead.bot_id)
    ):
        if bot_id in rows:
            rows[bot_id]["leads"] = total
    # Orders: main offers (plan/downsell) feed the funnel; upsell orders feed their step.
    for bot_id, kind, offer_id, total in await db.execute(
        select(TgOrder.bot_id, TgOrder.kind, TgOrder.offer_id, func.count(TgOrder.id))
        .where(TgOrder.workspace_id == workspace_id, *window(TgOrder.created_at))
        .group_by(TgOrder.bot_id, TgOrder.kind, TgOrder.offer_id)
    ):
        if bot_id not in rows:
            continue
        if kind == "upsell" and offer_id.startswith("up") and offer_id[2:].isdigit():
            step(bot_id, int(offer_id[2:]))["pix"] += total
        elif kind != "upsell":
            rows[bot_id]["pix"] += total
    for bot_id, kind, offer_id, total, amount in await db.execute(
        select(TgOrder.bot_id, TgOrder.kind, TgOrder.offer_id, func.count(TgOrder.id), func.coalesce(func.sum(TgOrder.amount), 0))
        .where(TgOrder.workspace_id == workspace_id, TgOrder.status == "paid", *window(TgOrder.paid_at))
        .group_by(TgOrder.bot_id, TgOrder.kind, TgOrder.offer_id)
    ):
        if bot_id not in rows:
            continue
        if kind == "upsell" and offer_id.startswith("up") and offer_id[2:].isdigit():
            item = step(bot_id, int(offer_id[2:]))
            item["paid"] += total
            item["revenue"] += Decimal(str(amount or 0))
        elif kind != "upsell":
            rows[bot_id]["sales"] += total
            rows[bot_id]["revenue"] += Decimal(str(amount or 0))
    # Each sent upsell step is one finished "send_upsell" job.
    for bot_id, payload in await db.execute(
        select(TgJob.bot_id, TgJob.payload).where(
            TgJob.bot_id.in_(list(bots)), TgJob.kind == "send_upsell", TgJob.status == "done", *window(TgJob.run_at)
        )
    ) if bots else []:
        index = (payload or {}).get("index")
        if bot_id in rows and isinstance(index, int):
            step(bot_id, index)["offered"] += 1

    result = []
    for bot_id, data in rows.items():
        if not (data["leads"] or data["pix"] or data["upsells"]):
            continue
        upsells = [
            {
                "step": index + 1,
                "offered": item["offered"],
                "pix": item["pix"],
                "paid": item["paid"],
                "revenue": float(item["revenue"]),
                "take_rate": _rate(item["paid"], item["offered"]),
            }
            for index, item in sorted(data["upsells"].items())
        ]
        result.append(
            {
                "bot_id": str(bot_id),
                "bot_name": bots[bot_id],
                "leads": data["leads"],
                "pix": data["pix"],
                "sales": data["sales"],
                "revenue": float(data["revenue"] + sum((Decimal(str(u["revenue"])) for u in upsells), Decimal("0"))),
                "lead_to_pix": _rate(data["pix"], data["leads"]),
                "pix_to_sale": _rate(data["sales"], data["pix"]),
                "upsells": upsells,
            }
        )
    result.sort(key=lambda row: row["revenue"], reverse=True)
    return {"period_label": period_label(start, end), "bots": result}
