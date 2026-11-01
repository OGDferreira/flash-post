"""Análises: the full sales analysis of one operation's Flash bots, with filters.

Filters (all optional): one bot, one funnel, one plan (the plan's name, with or without its
order bump). Every number covers the chosen period; the same numbers for the period just
before it come along for the "vs anterior" comparison.

* leads (starts)   = leads that entered in the period
* generated        = Pix charges created in the period (with a gateway charge)
* sales            = orders paid in the period; revenue = their gross amount
* approval         = paid ÷ generated in the period (late payments can pass 100%)
* lead conversion  = distinct buyers ÷ leads
* offer types      = plano, upsell, downsell, remarketing; order bump = paid sales with an
                     extra added (its rate is over the plan sales)
"""

import uuid
from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bots.hidden import not_hidden_bot
from app.core.time import as_utc
from app.models import TgBot, TgFlow, TgLead, TgOrder, TgSubscription

KINDS = ("plan", "upsell", "downsell", "remarketing")
WEEKDAYS = ("Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom")


def _f(value) -> float:
    return round(float(value or 0), 2)


def _pct(part: float, whole: float) -> float:
    return round(100 * part / whole, 1) if whole else 0.0


def base_plan(name: str) -> str:
    """"VIP + Pack" → "VIP": the plan without its order bump."""
    return (name or "").split(" + ", 1)[0].strip() or "Sem nome"


def _has_bump(offer_id: str, name: str) -> bool:
    return (offer_id or "").endswith("+bump") or " + " in (name or "")


def _kind(kind: str | None) -> str:
    return kind if kind in KINDS else "plan"


async def _window(
    db: AsyncSession, workspace_id: uuid.UUID, start: datetime, end: datetime, zone: ZoneInfo, *,
    bot_id: uuid.UUID | None, flow_id: uuid.UUID | None, plan: str | None, hide: bool, detail: bool,
) -> dict:
    lead_filters = [TgLead.workspace_id == workspace_id, TgLead.created_at >= start, TgLead.created_at < end]
    order_filters = [
        TgOrder.workspace_id == workspace_id,
        or_(and_(TgOrder.created_at >= start, TgOrder.created_at < end),
            and_(TgOrder.paid_at >= start, TgOrder.paid_at < end)),
    ]
    if hide:
        lead_filters.append(not_hidden_bot(TgLead.bot_id))
        order_filters.append(not_hidden_bot(TgOrder.bot_id))
    if bot_id:
        lead_filters.append(TgLead.bot_id == bot_id)
        order_filters.append(TgOrder.bot_id == bot_id)
    if flow_id:
        lead_filters.append(TgLead.flow_id == flow_id)
        order_filters.append(TgOrder.flow_id == flow_id)

    leads = (await db.execute(
        select(TgLead.id, TgLead.bot_id, TgLead.flow_id, TgLead.source, TgLead.blocked_bot).where(*lead_filters)
    )).all()
    orders = (await db.execute(
        select(
            TgOrder.lead_id, TgOrder.bot_id, TgOrder.flow_id, TgOrder.kind, TgOrder.offer_id, TgOrder.offer_name,
            TgOrder.amount, TgOrder.status, TgOrder.created_at, TgOrder.paid_at, TgOrder.gateway,
            TgOrder.gateway_transaction_id, TgLead.created_at.label("lead_started"), TgLead.source.label("lead_source"),
        ).join(TgLead, TgLead.id == TgOrder.lead_id).where(*order_filters)
    )).all()
    if plan:
        orders = [row for row in orders if base_plan(row.offer_name) == plan]

    def inside(moment) -> bool:
        return moment is not None and start <= as_utc(moment) < end

    generated = [o for o in orders if inside(o.created_at) and o.gateway_transaction_id and o.status != "failed"]
    paid = [o for o in orders if o.status == "paid" and inside(o.paid_at)]
    revenue = sum((Decimal(o.amount or 0) for o in paid), Decimal("0"))
    generated_value = sum((Decimal(o.amount or 0) for o in generated), Decimal("0"))
    buyers = {o.lead_id for o in paid}
    lead_count = len(leads)
    summary = {
        "leads": lead_count,
        "generated": len(generated),
        "generated_value": _f(generated_value),
        "sales": len(paid),
        "revenue": _f(revenue),
        "ticket": _f(revenue / len(paid)) if paid else 0.0,
        "approval": _pct(len(paid), len(generated)),
        "buyers": len(buyers),
        "lead_conversion": _pct(len(buyers), lead_count),
        "leads_with_pix": len({o.lead_id for o in generated}),
    }
    if not detail:
        return {"summary": summary}

    # ---- when it sells: per day, hour of the day and weekday (local time)
    per_day: dict[str, list] = defaultdict(lambda: [0, Decimal("0")])
    per_hour = [[0, Decimal("0")] for _ in range(24)]
    per_weekday = [[0, Decimal("0")] for _ in range(7)]
    for o in paid:
        local = as_utc(o.paid_at).astimezone(zone)
        amount = Decimal(o.amount or 0)
        for bucket in (per_day[local.date().isoformat()], per_hour[local.hour], per_weekday[local.weekday()]):
            bucket[0] += 1
            bucket[1] += amount
    generated_per_day: dict[str, int] = defaultdict(int)
    for o in generated:
        generated_per_day[as_utc(o.created_at).astimezone(zone).date().isoformat()] += 1
    leads_per_day: dict[str, int] = defaultdict(int)
    days, cursor = [], as_utc(start).astimezone(zone).date()
    last = as_utc(end - timedelta(microseconds=1)).astimezone(zone).date()
    while cursor <= last and len(days) < 400:
        key = cursor.isoformat()
        days.append({"date": key, "sales": per_day[key][0], "revenue": _f(per_day[key][1]),
                     "generated": generated_per_day[key]})
        cursor += timedelta(days=1)

    # ---- rankings: bots, funnels, plans (what sells and what doesn't)
    def row():
        return {"leads": 0, "generated": 0, "sales": 0, "revenue": Decimal("0"), "buyers": set()}

    by_bot, by_flow, by_plan, by_source = defaultdict(row), defaultdict(row), defaultdict(row), defaultdict(row)
    for lead in leads:
        by_bot[lead.bot_id]["leads"] += 1
        if lead.flow_id:
            by_flow[lead.flow_id]["leads"] += 1
        by_source[(lead.source or "").strip() or "direto"]["leads"] += 1
    for o in generated:
        by_bot[o.bot_id]["generated"] += 1
        if o.flow_id:
            by_flow[o.flow_id]["generated"] += 1
        by_plan[base_plan(o.offer_name)]["generated"] += 1
        by_source[(o.lead_source or "").strip() or "direto"]["generated"] += 1
    for o in paid:
        amount = Decimal(o.amount or 0)
        targets = [by_bot[o.bot_id], by_plan[base_plan(o.offer_name)], by_source[(o.lead_source or "").strip() or "direto"]]
        if o.flow_id:
            targets.append(by_flow[o.flow_id])
        for target in targets:
            target["sales"] += 1
            target["revenue"] += amount
            target["buyers"].add(o.lead_id)

    bot_names = {
        bid: name for bid, name in (await db.execute(
            select(TgBot.id, TgBot.name).where(TgBot.workspace_id == workspace_id)
        )).all()
    }
    flow_names = {
        fid: name for fid, name in (await db.execute(
            select(TgFlow.id, TgFlow.name).where(TgFlow.workspace_id == workspace_id)
        )).all()
    }

    def out(key, name, data) -> dict:
        return {
            "id": str(key), "name": name, "leads": data["leads"], "generated": data["generated"],
            "sales": data["sales"], "revenue": _f(data["revenue"]), "buyers": len(data["buyers"]),
            "approval": _pct(data["sales"], data["generated"]),
            "conversion": _pct(len(data["buyers"]), data["leads"]),
            "ticket": _f(data["revenue"] / data["sales"]) if data["sales"] else 0.0,
        }

    def ranked(rows: list[dict]) -> list[dict]:
        return sorted(rows, key=lambda r: (-r["revenue"], -r["sales"], -r["generated"], -r["leads"]))

    bots = ranked([out(k, bot_names.get(k, "Bot removido"), v) for k, v in by_bot.items()])
    flows = ranked([out(k, flow_names.get(k, "Funil removido"), v) for k, v in by_flow.items()])
    plans = ranked([out(k, k, v) for k, v in by_plan.items()])
    sources = ranked([out(k, k, v) for k, v in by_source.items()])

    # ---- offer types: plano, upsell, downsell, remarketing, order bump
    kinds = {k: {"generated": 0, "sales": 0, "revenue": Decimal("0")} for k in KINDS}
    for o in generated:
        kinds[_kind(o.kind)]["generated"] += 1
    for o in paid:
        kinds[_kind(o.kind)]["sales"] += 1
        kinds[_kind(o.kind)]["revenue"] += Decimal(o.amount or 0)
    bump_paid = [o for o in paid if _has_bump(o.offer_id, o.offer_name)]
    plan_sales = kinds["plan"]["sales"] + kinds["remarketing"]["sales"]
    offer_types = [
        {"kind": k, "generated": v["generated"], "sales": v["sales"], "revenue": _f(v["revenue"]),
         "approval": _pct(v["sales"], v["generated"])}
        for k, v in kinds.items()
    ]
    bump = {"sales": len(bump_paid), "revenue": _f(sum((Decimal(o.amount or 0) for o in bump_paid), Decimal("0"))),
            "rate": _pct(len(bump_paid), plan_sales)}

    # ---- customers
    purchases: dict[uuid.UUID, list[datetime]] = defaultdict(list)
    kinds_by_buyer: dict[uuid.UUID, set[str]] = defaultdict(set)
    waits = []
    for o in paid:
        purchases[o.lead_id].append(as_utc(o.paid_at))
        kinds_by_buyer[o.lead_id].add(_kind(o.kind))
    first_paid: dict[uuid.UUID, tuple[datetime, datetime]] = {}
    for o in paid:
        moment = as_utc(o.paid_at)
        if o.lead_id not in first_paid or moment < first_paid[o.lead_id][0]:
            first_paid[o.lead_id] = (moment, as_utc(o.lead_started))
    for paid_moment, started in first_paid.values():
        if paid_moment >= started:
            waits.append((paid_moment - started).total_seconds())
    gaps = []
    for moments in purchases.values():
        moments.sort()
        gaps += [(b - a).total_seconds() for a, b in zip(moments, moments[1:])]
    recurring = sum(1 for moments in purchases.values() if len(moments) > 1)
    vip_filters = [TgSubscription.workspace_id == workspace_id, TgSubscription.status == "active"]
    if bot_id:
        vip_filters.append(TgSubscription.bot_id == bot_id)
    if hide:
        vip_filters.append(not_hidden_bot(TgSubscription.bot_id))
    vip_query = select(TgSubscription.lead_id).where(*vip_filters)
    if flow_id:
        vip_query = vip_query.join(TgLead, TgLead.id == TgSubscription.lead_id).where(TgLead.flow_id == flow_id)
    vips = len(set(await db.scalars(vip_query)))
    customers = {
        "buyers": len(buyers),
        "recurring": recurring,
        "upsellers": sum(1 for k in kinds_by_buyer.values() if "upsell" in k),
        "downsellers": sum(1 for k in kinds_by_buyer.values() if "downsell" in k),
        "remarketing": sum(1 for k in kinds_by_buyer.values() if "remarketing" in k),
        "bump_buyers": len({o.lead_id for o in bump_paid}),
        "vips_active": vips,
        "ltv": _f(revenue / len(buyers)) if buyers else 0.0,
        "purchases_per_buyer": round(len(paid) / len(buyers), 2) if buyers else 0.0,
        "avg_seconds_to_pay": int(sum(waits) / len(waits)) if waits else None,
        "avg_seconds_between_purchases": int(sum(gaps) / len(gaps)) if gaps else None,
        "blocked": sum(1 for lead in leads if lead.blocked_bot),
        "blocked_rate": _pct(sum(1 for lead in leads if lead.blocked_bot), lead_count),
        "abandoned_pix": max(0, len(generated) - sum(1 for o in generated if o.status == "paid")),
        "abandoned_value": _f(sum((Decimal(o.amount or 0) for o in generated if o.status != "paid"), Decimal("0"))),
    }

    gateways: dict[str, list] = defaultdict(lambda: [0, Decimal("0")])
    for o in paid:
        gateways[o.gateway or "smokepay"][0] += 1
        gateways[o.gateway or "smokepay"][1] += Decimal(o.amount or 0)

    return {
        "summary": summary,
        "series": days,
        "hours": [{"hour": h, "sales": v[0], "revenue": _f(v[1])} for h, v in enumerate(per_hour)],
        "weekdays": [{"day": WEEKDAYS[d], "sales": v[0], "revenue": _f(v[1])} for d, v in enumerate(per_weekday)],
        "bots": bots,
        "flows": flows,
        "plans": plans,
        "sources": sources,
        "offer_types": offer_types,
        "order_bump": bump,
        "customers": customers,
        "gateways": sorted(
            ({"gateway": g, "sales": v[0], "revenue": _f(v[1])} for g, v in gateways.items()),
            key=lambda r: -r["revenue"],
        ),
    }


async def full_analytics(
    db: AsyncSession, workspace_id: uuid.UUID, start: datetime, end: datetime, zone: ZoneInfo, *,
    bot_id: uuid.UUID | None = None, flow_id: uuid.UUID | None = None, plan: str | None = None, hide: bool = False,
) -> dict:
    current = await _window(db, workspace_id, start, end, zone, bot_id=bot_id, flow_id=flow_id, plan=plan,
                            hide=hide, detail=True)
    span = end - start
    previous = await _window(db, workspace_id, start - span, start, zone, bot_id=bot_id, flow_id=flow_id, plan=plan,
                             hide=hide, detail=False)
    current["previous"] = previous["summary"]
    current["options"] = await _options(db, workspace_id, hide=hide)
    return current


async def _options(db: AsyncSession, workspace_id: uuid.UUID, *, hide: bool) -> dict:
    """What the filters offer: the operation's bots and funnels, and the plans of its funnels
    plus any plan sold in the last 90 days."""
    bot_query = select(TgBot.id, TgBot.name).where(TgBot.workspace_id == workspace_id)
    if hide:
        bot_query = bot_query.where(not_hidden_bot(TgBot.id))
    bots = [{"id": str(i), "name": n} for i, n in (await db.execute(bot_query.order_by(TgBot.name))).all()]
    flow_rows = (await db.execute(
        select(TgFlow.id, TgFlow.name, TgFlow.definition).where(TgFlow.workspace_id == workspace_id).order_by(TgFlow.name)
    )).all()
    flows = [{"id": str(i), "name": n} for i, n, _d in flow_rows]
    plans: set[str] = set()
    for _i, _n, definition in flow_rows:
        for item in (definition or {}).get("plans", []) or []:
            if isinstance(item, dict) and item.get("name"):
                plans.add(str(item["name"]).strip())
    from app.core.time import utc_now

    recent = await db.scalars(
        select(TgOrder.offer_name).where(
            TgOrder.workspace_id == workspace_id, TgOrder.status == "paid",
            TgOrder.paid_at >= utc_now() - timedelta(days=90),
        ).distinct()
    )
    plans.update(base_plan(name) for name in recent if name)
    return {"bots": bots, "flows": flows, "plans": sorted(plans, key=str.lower)}
