"""Super Admin: every operation's loops, bots and funnels, funnel ranking by
template, bot conversion and revenue/commissions per user. Never returns tokens."""

import uuid
from datetime import date

from sqlalchemy import case, func, select

from app.analytics.periods import AnalyticsPeriod, period_bounds, period_label
from app.auth.dependencies import DbSession, SuperAdminUser
from app.core.time import utc_now
from app.models import (
    Affiliation,
    InstagramLoop,
    InstagramLoopAccount,
    InstagramPublicationJob,
    TgBot,
    TgFlow,
    TgLead,
    TgOrder,
    User,
    Workspace,
)
from fastapi import APIRouter

router = APIRouter(prefix="/api/admin", tags=["platform administration"])


def _f(value) -> float:
    return round(float(value or 0), 2)


@router.get("/operations")
async def operations(
    _admin: SuperAdminUser, db: DbSession, period: AnalyticsPeriod = "30d",
    start_date: date | None = None, end_date: date | None = None,
) -> dict:
    start, end = period_bounds(period, start_date, end_date, utc_now())
    users = {u.id: u for u in await db.scalars(select(User))}
    workspaces = {w.id: w for w in await db.scalars(select(Workspace))}
    links = {l.affiliate_user_id: l for l in await db.scalars(select(Affiliation).where(Affiliation.status == "ACTIVE"))}
    chiefs = {l.chief_user_id for l in links.values()}

    def owner_name(workspace_id) -> str:
        ws = workspaces.get(workspace_id)
        user = users.get(ws.owner_id) if ws else None
        return user.full_name if user else "—"

    def hierarchy(user_id) -> str:
        if user_id in links:
            return "partner"
        return "chief" if user_id in chiefs else "independent"

    in_period = (TgOrder.status == "paid", TgOrder.paid_at >= start, TgOrder.paid_at < end)

    # bots: leads, PIX generated and paid, revenue, conversion
    bots = list(await db.scalars(select(TgBot).order_by(TgBot.created_at)))
    flows = {f.id: f for f in await db.scalars(select(TgFlow))}
    leads = dict((await db.execute(
        select(TgLead.bot_id, func.count(TgLead.id)).where(TgLead.created_at >= start, TgLead.created_at < end).group_by(TgLead.bot_id)
    )).all())
    order_stats = {
        bot_id: (int(gen), int(paid), _f(revenue))
        for bot_id, gen, paid, revenue in (await db.execute(
            select(
                TgOrder.bot_id,
                func.count(TgOrder.id),
                func.coalesce(func.sum(case((TgOrder.status == "paid", 1), else_=0)), 0),
                func.coalesce(func.sum(case((TgOrder.status == "paid", TgOrder.amount), else_=0)), 0),
            ).where(TgOrder.created_at >= start, TgOrder.created_at < end).group_by(TgOrder.bot_id)
        )).all()
    }
    bot_rows = []
    for bot in bots:
        generated, paid, revenue = order_stats.get(bot.id, (0, 0, 0.0))
        lead_count = int(leads.get(bot.id, 0))
        bot_rows.append({
            "id": str(bot.id), "name": bot.name, "username": bot.username, "status": bot.status,
            "owner": owner_name(bot.workspace_id), "flow_name": flows[bot.flow_id].name if bot.flow_id in flows else None,
            "leads": lead_count, "pix_generated": generated, "sales": paid, "revenue": revenue,
            "conversion": round(100 * paid / lead_count, 1) if lead_count else 0.0,
            "pix_conversion": round(100 * paid / generated, 1) if generated else 0.0,
        })
    bot_rows.sort(key=lambda r: r["revenue"], reverse=True)

    # funnel ranking, grouped by the original template across partners
    def root(flow_id):
        seen, current = set(), flows.get(flow_id)
        while current and current.template_flow_id in flows and current.template_flow_id not in seen:
            seen.add(current.id)
            current = flows[current.template_flow_id]
        return current
    per_flow = (await db.execute(
        select(TgOrder.flow_id, TgOrder.workspace_id, func.count(TgOrder.id), func.coalesce(func.sum(TgOrder.amount), 0))
        .where(*in_period).group_by(TgOrder.flow_id, TgOrder.workspace_id)
    )).all()
    ranking: dict[uuid.UUID, dict] = {}
    for flow_id, workspace_id, sales, revenue in per_flow:
        origin = root(flow_id)
        if origin is None:
            continue
        entry = ranking.setdefault(origin.id, {
            "id": str(origin.id), "name": origin.name, "owner": owner_name(origin.workspace_id),
            "shared": bool(origin.shared), "sales": 0, "revenue": 0.0, "operations": set(),
        })
        entry["sales"] += int(sales)
        entry["revenue"] = round(entry["revenue"] + _f(revenue), 2)
        entry["operations"].add(workspace_id)
    funnel_rows = sorted(
        ({**e, "operations": len(e["operations"])} for e in ranking.values()), key=lambda r: r["revenue"], reverse=True
    )

    # revenue and commissions per user (owner of each workspace)
    gross = {
        ws_id: (_f(total), _f(fees), _f(paid_out))
        for ws_id, total, fees, paid_out in (await db.execute(
            select(
                TgOrder.workspace_id, func.coalesce(func.sum(TgOrder.amount), 0),
                func.coalesce(func.sum(TgOrder.gateway_fee), 0), func.coalesce(func.sum(TgOrder.split_amount), 0),
            ).where(*in_period).group_by(TgOrder.workspace_id)
        )).all()
    }
    received = dict((await db.execute(
        select(TgOrder.split_chief_user_id, func.coalesce(func.sum(TgOrder.split_amount), 0))
        .where(*in_period, TgOrder.split_chief_user_id.is_not(None)).group_by(TgOrder.split_chief_user_id)
    )).all())
    user_rows = []
    for ws in workspaces.values():
        owner = users.get(ws.owner_id)
        if owner is None:
            continue
        total, fees, paid_out = gross.get(ws.id, (0.0, 0.0, 0.0))
        link = links.get(owner.id)
        user_rows.append({
            "user_id": str(owner.id), "name": owner.full_name, "email": owner.email, "hierarchy": hierarchy(owner.id),
            "chief": users[link.chief_user_id].full_name if link and link.chief_user_id in users else None,
            "commission_percent": _f(link.accepted_percent) if link and link.accepted_percent is not None else None,
            "revenue": total, "fees": fees, "commission_paid": paid_out, "commission_received": _f(received.get(owner.id)),
        })
    user_rows.sort(key=lambda r: r["revenue"], reverse=True)

    # loops of every operation
    loops = list(await db.scalars(select(InstagramLoop).order_by(InstagramLoop.created_at)))
    accounts = dict((await db.execute(
        select(InstagramLoopAccount.loop_id, func.count(InstagramLoopAccount.account_id)).group_by(InstagramLoopAccount.loop_id)
    )).all())
    published_at = func.coalesce(InstagramPublicationJob.published_at, InstagramPublicationJob.updated_at)
    posts = dict((await db.execute(
        select(InstagramPublicationJob.loop_id, func.count(InstagramPublicationJob.id))
        .where(InstagramPublicationJob.status == "published", published_at >= start, published_at < end)
        .group_by(InstagramPublicationJob.loop_id)
    )).all())
    loop_rows = [
        {
            "id": str(loop.id), "name": loop.name, "owner": owner_name(loop.workspace_id), "status": loop.status,
            "accounts": int(accounts.get(loop.id, 0)), "posts": int(posts.get(loop.id, 0)),
            "shared": bool(loop.shared), "from_template": loop.template_loop_id is not None,
        }
        for loop in loops
    ]
    return {
        "period_label": period_label(start, end),
        "users": user_rows, "bots": bot_rows, "funnels": funnel_rows, "loops": loop_rows,
    }
