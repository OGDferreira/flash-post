"""Flash bot funnel by bot: leads -> Pix -> sale -> each upsell step (offered, Pix, paid).

Headline "Vendas" and "Pix gerados" per bot are TOTALS: the entry sale plus every paid
upsell step (each upsell step is its own paid order, its own money). The entry conversion
(lead -> entry Pix -> entry sale) is kept separately so the funnel rates stay honest.
"""

import uuid
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.analytics.periods import AnalyticsPeriod, period_bounds, period_label
from app.auth.dependencies import DbSession, OwnerAccess
from app.bots.hidden import admin_view, not_hidden_bot
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
    bot_id: uuid.UUID | None = None,
    flow_id: uuid.UUID | None = None,
) -> dict:
    start, end = period_bounds(period, start_date, end_date, utc_now())
    workspace_id = access.workspace.id
    hide = not admin_view()

    def window(column):
        return [c for c in ((column >= start) if start else None, (column < end) if end else None) if c is not None]

    bot_query = select(TgBot.id, TgBot.name).where(TgBot.workspace_id == workspace_id)
    if hide:
        bot_query = bot_query.where(not_hidden_bot(TgBot.id))
    if bot_id:
        bot_query = bot_query.where(TgBot.id == bot_id)
    bots = {row_id: name for row_id, name in await db.execute(bot_query)}
    rows: dict[uuid.UUID, dict] = {
        row_id: {"leads": 0, "pix": 0, "sales": 0, "revenue": Decimal("0.00"), "upsells": {}} for row_id in bots
    }

    def step(row_id, index: int) -> dict:
        return rows[row_id]["upsells"].setdefault(index, {"offered": 0, "pix": 0, "paid": 0, "revenue": Decimal("0.00")})

    lead_filters = [TgLead.workspace_id == workspace_id, *window(TgLead.created_at)]
    order_filters = [TgOrder.workspace_id == workspace_id]
    paid_filters = [TgOrder.workspace_id == workspace_id, TgOrder.status == "paid", *window(TgOrder.paid_at)]
    if flow_id:
        lead_filters.append(TgLead.flow_id == flow_id)
        order_filters.append(TgOrder.flow_id == flow_id)
        paid_filters.append(TgOrder.flow_id == flow_id)

    for row_id, total in await db.execute(
        select(TgLead.bot_id, func.count(TgLead.id)).where(*lead_filters).group_by(TgLead.bot_id)
    ):
        if row_id in rows:
            rows[row_id]["leads"] = total
    # Orders generated: main offers (plan/downsell) feed the funnel; upsell orders feed their step.
    for row_id, kind, offer_id, total in await db.execute(
        select(TgOrder.bot_id, TgOrder.kind, TgOrder.offer_id, func.count(TgOrder.id))
        .where(*order_filters, *window(TgOrder.created_at))
        .group_by(TgOrder.bot_id, TgOrder.kind, TgOrder.offer_id)
    ):
        if row_id not in rows:
            continue
        if kind == "upsell" and offer_id.startswith("up") and offer_id[2:].isdigit():
            step(row_id, int(offer_id[2:]))["pix"] += total
        elif kind != "upsell":
            rows[row_id]["pix"] += total
    for row_id, kind, offer_id, total, amount in await db.execute(
        select(TgOrder.bot_id, TgOrder.kind, TgOrder.offer_id, func.count(TgOrder.id), func.coalesce(func.sum(TgOrder.amount), 0))
        .where(*paid_filters)
        .group_by(TgOrder.bot_id, TgOrder.kind, TgOrder.offer_id)
    ):
        if row_id not in rows:
            continue
        if kind == "upsell" and offer_id.startswith("up") and offer_id[2:].isdigit():
            item = step(row_id, int(offer_id[2:]))
            item["paid"] += total
            item["revenue"] += Decimal(str(amount or 0))
        elif kind != "upsell":
            rows[row_id]["sales"] += total
            rows[row_id]["revenue"] += Decimal(str(amount or 0))
    # Each sent upsell step is one finished "send_upsell" job.
    for row_id, payload in await db.execute(
        select(TgJob.bot_id, TgJob.payload).where(
            TgJob.bot_id.in_(list(bots)), TgJob.kind == "send_upsell", TgJob.status == "done", *window(TgJob.run_at)
        )
    ) if bots else []:
        index = (payload or {}).get("index")
        if row_id in rows and isinstance(index, int):
            step(row_id, index)["offered"] += 1

    result = []
    for row_id, data in rows.items():
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
        upsell_pix = sum(step["pix"] for step in upsells)
        upsell_sales = sum(step["paid"] for step in upsells)
        upsell_revenue = sum((Decimal(str(step["revenue"])) for step in upsells), Decimal("0"))
        result.append(
            {
                "bot_id": str(row_id),
                "bot_name": bots[row_id],
                "leads": data["leads"],
                # entry funnel (one order per lead) keeps the honest conversion rates
                "entry_pix": data["pix"],
                "entry_sales": data["sales"],
                # totals = entry + every paid upsell step (each one is its own money)
                "pix": data["pix"] + upsell_pix,
                "sales": data["sales"] + upsell_sales,
                "upsell_sales": upsell_sales,
                "revenue": float(data["revenue"] + upsell_revenue),
                "lead_to_pix": _rate(data["pix"], data["leads"]),
                "pix_to_sale": _rate(data["sales"], data["pix"]),
                "upsells": upsells,
            }
        )
    result.sort(key=lambda row: row["revenue"], reverse=True)
    return {"period_label": period_label(start, end), "bots": result}
