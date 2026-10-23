"""Falcon Bot conversion numbers for one operation (never mixes workspaces).

* leads      = leads that entered in the period (one per Telegram user per bot)
* sales      = paid orders in the period (upsells count as sales)
* buyers     = distinct leads with a paid order in the period
* totals.conversion = PIX paid in the period ÷ PIX generated in the period × 100
* flows/bots/series.conversion retain the existing lead conversion
* ticket     = confirmed gross revenue ÷ sales
* pix_generated = Pix charges created in the period (any status)
"""

import uuid
from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bots.hidden import not_hidden_bot
from app.core.time import BRAZIL_TIME_ZONE, as_utc
from app.models import Affiliation, TgBot, TgLead, TgOrder, User, Workspace, WorkspaceMember


def _f(value) -> float:
    return round(float(value or 0), 2)


def _rate(buyers: int, leads: int) -> float:
    return round(min(100.0, 100 * buyers / leads), 1) if leads else 0.0


async def conversion_stats(
    db: AsyncSession, workspace_id: uuid.UUID, start: datetime, end: datetime, zone: ZoneInfo = BRAZIL_TIME_ZONE, *, hide: bool = False
) -> dict:
    """``hide``: leave out bots the Super Admin hid from this operation."""
    lead_shown = (not_hidden_bot(TgLead.bot_id),) if hide else ()
    order_shown = (not_hidden_bot(TgOrder.bot_id),) if hide else ()
    lead_rows = (
        await db.execute(
            select(TgLead.id, TgLead.bot_id, TgLead.flow_id, TgLead.created_at).where(
                TgLead.workspace_id == workspace_id, TgLead.created_at >= start, TgLead.created_at < end, *lead_shown
            )
        )
    ).all()
    order_rows = (
        await db.execute(
            select(TgOrder.lead_id, TgOrder.bot_id, TgOrder.flow_id, TgOrder.amount, TgOrder.paid_at).where(
                TgOrder.workspace_id == workspace_id, TgOrder.status == "paid",
                TgOrder.paid_at >= start, TgOrder.paid_at < end, *order_shown,
            )
        )
    ).all()

    pix_generated = await db.scalar(
        select(func.count(TgOrder.id)).where(
            TgOrder.workspace_id == workspace_id, TgOrder.created_at >= start, TgOrder.created_at < end,
            TgOrder.gateway_transaction_id.is_not(None), TgOrder.gateway_transaction_id != "", *order_shown,
        )
    )

    # Count persisted orders, not webhook deliveries. Both event windows are [start, end):
    # generated uses created_at and paid uses paid_at, matching the revenue indicator.
    # Late payments can make the ratio exceed 100%; never silently cap the number.
    pix_paid = await db.scalar(select(func.count(TgOrder.id)).where(
        TgOrder.workspace_id == workspace_id, TgOrder.status == "paid",
        TgOrder.paid_at >= start, TgOrder.paid_at < end,
        TgOrder.gateway_transaction_id.is_not(None), TgOrder.gateway_transaction_id != "", *order_shown,
    )) or 0

    def bucket():
        return {"leads": 0, "sales": 0, "revenue": Decimal("0"), "buyers": set()}

    total, per_flow, per_bot, per_day = bucket(), defaultdict(bucket), defaultdict(bucket), defaultdict(bucket)
    for _lead_id, bot_id, flow_id, created in lead_rows:
        day = as_utc(created).astimezone(zone).date().isoformat()
        for target in (total, per_bot[bot_id], per_day[day]) + ((per_flow[flow_id],) if flow_id else ()):
            target["leads"] += 1
    for lead_id, bot_id, flow_id, amount, paid in order_rows:
        day = as_utc(paid).astimezone(zone).date().isoformat()
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

    days, cursor = [], as_utc(start).astimezone(zone).date()
    last = as_utc(end - timedelta(microseconds=1)).astimezone(zone).date()
    while cursor <= last and len(days) < 400:
        key = cursor.isoformat()
        days.append({"date": key, **out(per_day[key])})
        cursor += timedelta(days=1)
    return {
        "totals": {**out(total), "pix_generated": int(pix_generated or 0), "pix_paid": pix_paid,
                   "conversion": round(100 * pix_paid / pix_generated, 2) if pix_generated else 0.0},
        "series": days,
        "flows": {str(k): out(v) for k, v in per_flow.items()},
        "bots": {str(k): out(v) for k, v in per_bot.items()},
    }


def _public_avatar(user: User) -> str | None:
    # Stored avatars are only served to members of the same workspace; partners
    # live in other workspaces, so only external photo links are shared here.
    url = user.avatar_url or ""
    return url if url.startswith(("https://", "http://")) else None


async def partners_ranking_of(db: AsyncSession, user_id: uuid.UUID, start: datetime, end: datetime) -> dict:
    """The chief and their active partners ordered by Falcon Bot revenue, with each one's
    revenue in the period (the owner's decision, 2026-10-23: the ranking shows the values).

    A partner sees their chief and sibling partners; a chief sees their partners.
    """
    link = await db.scalar(
        select(Affiliation).where(Affiliation.affiliate_user_id == user_id, Affiliation.status == "ACTIVE")
    )
    chief_id = link.chief_user_id if link else user_id
    partner_ids = list(
        await db.scalars(
            select(Affiliation.affiliate_user_id).where(
                Affiliation.chief_user_id == chief_id, Affiliation.status == "ACTIVE"
            )
        )
    )
    member_ids = [chief_id, *partner_ids] if partner_ids else [user_id]
    users = {u.id: u for u in await db.scalars(select(User).where(User.id.in_(member_ids)))}
    owned = (
        await db.execute(
            select(Workspace.owner_id, Workspace.id)
            .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
            .where(
                Workspace.owner_id.in_(member_ids),
                WorkspaceMember.user_id == Workspace.owner_id,
                WorkspaceMember.role == "OWNER",
                WorkspaceMember.status == "ACTIVE",
            )
        )
    ).all()
    workspace_owner = {ws_id: owner_id for owner_id, ws_id in owned}
    revenue: dict[uuid.UUID, Decimal] = defaultdict(Decimal)
    if workspace_owner:
        rows = await db.execute(
            select(TgOrder.workspace_id, func.coalesce(func.sum(TgOrder.amount), 0))
            .where(
                TgOrder.workspace_id.in_(list(workspace_owner)), TgOrder.status == "paid",
                TgOrder.paid_at >= start, TgOrder.paid_at < end, not_hidden_bot(TgOrder.bot_id),
            )
            .group_by(TgOrder.workspace_id)
        )
        for ws_id, amount in rows.all():
            revenue[workspace_owner[ws_id]] += Decimal(amount or 0)

    ordered = sorted(
        (uid for uid in member_ids if uid in users),
        key=lambda uid: (-revenue[uid], (users[uid].nickname or users[uid].full_name).lower()),
    )
    return {
        "members": [
            {
                "position": index,
                "name": users[uid].full_name,
                "nickname": users[uid].nickname,
                "avatar_url": _public_avatar(users[uid]),
                "is_chief": uid == chief_id and bool(partner_ids),
                "is_me": uid == user_id,
                "has_sales": revenue[uid] > 0,
                "revenue": float(revenue[uid].quantize(Decimal("0.01"))),
            }
            for index, uid in enumerate(ordered, start=1)
        ],
    }


async def recent_activity(db: AsyncSession, workspace_id: uuid.UUID, limit: int = 30, *, hide: bool = False) -> list[dict]:
    """Latest leads, Pix generated and approved sales of one operation, newest first.
    ``hide``: leave out bots the Super Admin hid from this operation."""
    shown = (TgBot.hidden_by_admin.is_(False),) if hide else ()
    leads = (
        await db.execute(
            select(TgLead.first_name, TgLead.username, TgLead.created_at, TgBot.username)
            .join(TgBot, TgBot.id == TgLead.bot_id)
            .where(TgLead.workspace_id == workspace_id, *shown)
            .order_by(TgLead.created_at.desc())
            .limit(limit)
        )
    ).all()
    order_cols = (TgLead.first_name, TgLead.username, TgOrder.amount, TgBot.username)
    pix = (
        await db.execute(
            select(*order_cols, TgOrder.created_at)
            .join(TgLead, TgLead.id == TgOrder.lead_id).join(TgBot, TgBot.id == TgOrder.bot_id)
            .where(TgOrder.workspace_id == workspace_id, *shown)
            .order_by(TgOrder.created_at.desc())
            .limit(limit)
        )
    ).all()
    paid = (
        await db.execute(
            select(*order_cols, TgOrder.paid_at)
            .join(TgLead, TgLead.id == TgOrder.lead_id).join(TgBot, TgBot.id == TgOrder.bot_id)
            .where(TgOrder.workspace_id == workspace_id, TgOrder.status == "paid", TgOrder.paid_at.is_not(None), *shown)
            .order_by(TgOrder.paid_at.desc())
            .limit(limit)
        )
    ).all()

    def who(first_name: str | None, username: str | None) -> str:
        return (first_name or "").strip() or (f"@{username}" if username else "Lead")

    events = [
        {"kind": "lead", "lead": who(first, user), "bot": bot, "amount": None, "at": at}
        for first, user, at, bot in leads
    ]
    events += [
        {"kind": kind, "lead": who(first, user), "bot": bot, "amount": _f(amount), "at": at}
        for kind, rows in (("pix", pix), ("sale", paid))
        for first, user, amount, bot, at in rows
    ]
    events.sort(key=lambda event: event["at"], reverse=True)
    return [{**event, "at": event["at"].isoformat()} for event in events[:limit]]
