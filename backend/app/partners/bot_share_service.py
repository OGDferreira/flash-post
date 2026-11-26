"""Bot partnership rules: sharing a whole bot (and the funnel it runs) with an independent
user, the per-sale split and the finance panel both sides read.

A bot may have several ACTIVE partners at once, each with their own cut. The split ledger
keys one row per (order, partnership), so a paid sale records one line per active partner.
The sum of all active partners' percentages may not exceed 100%.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_DOWN, Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.nickname import nickname_key
from app.core.security import WorkspaceRole
from app.core.time import utc_now
from app.models import (
    BotPartner,
    BotPartnerPayout,
    BotPartnerSale,
    TgBot,
    TgOrder,
    User,
    Workspace,
    WorkspaceMember,
)
from app.partners.service import (
    default_transaction_fee,
    money,
    notify_user,
    transaction_fee_for,
)

CENT = Decimal("0.01")
ACTIVE_STATES = ("PENDING", "ACTIVE", "PAUSED")


def _floor(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_DOWN)


def user_brief(user: User | None) -> dict | None:
    if user is None:
        return None
    return {
        "id": str(user.id),
        "name": user.full_name or user.nickname,
        "nickname": user.nickname,
        "username": user.username,
        "email": user.email,
    }


def partnership_out(part: BotPartner, owner: User | None, partner: User | None, bot: TgBot | None = None) -> dict:
    data = {
        "id": str(part.id),
        "bot_id": str(part.bot_id),
        "status": part.status,
        "access_level": part.access_level,
        "partner_percent": float(part.partner_percent),
        "bot_fee": float(part.bot_fee),
        "accepted_at": part.accepted_at.isoformat() if part.accepted_at else None,
        "created_at": part.created_at.isoformat(),
        "owner": user_brief(owner),
        "partner": user_brief(partner),
    }
    if bot is not None:
        data["bot"] = {"id": str(bot.id), "name": bot.name, "username": bot.username}
    return data


async def find_user_by_identifier(db: AsyncSession, identifier: str) -> User | None:
    """Look an existing Flash user up by e-mail, @username or nickname."""
    raw = identifier.strip()
    if not raw:
        return None
    handle = raw.lstrip("@")
    user = await db.scalar(select(User).where(func.lower(User.email) == raw.lower()))
    if user:
        return user
    user = await db.scalar(select(User).where(func.lower(User.username) == handle.lower()))
    if user:
        return user
    try:
        key = nickname_key(handle)
    except Exception:
        return None
    return await db.scalar(select(User).where(User.nickname_normalized == key))


async def owner_bot(db: AsyncSession, owner_user_id: uuid.UUID, bot_id: uuid.UUID) -> TgBot | None:
    """A bot the user owns (OWNER of the workspace it lives in)."""
    return await db.scalar(
        select(TgBot)
        .join(WorkspaceMember, WorkspaceMember.workspace_id == TgBot.workspace_id)
        .where(
            TgBot.id == bot_id,
            WorkspaceMember.user_id == owner_user_id,
            WorkspaceMember.role == WorkspaceRole.OWNER.value,
            WorkspaceMember.status == "ACTIVE",
        )
    )


async def default_bot_fee(db: AsyncSession, owner: User) -> Decimal:
    """The per-sale fee a partnership deducts by default: the owner's normal Flash fee."""
    return transaction_fee_for(owner, await default_transaction_fee(db))


async def active_partner_count(db: AsyncSession, bot_id: uuid.UUID, exclude: uuid.UUID | None = None) -> int:
    query = select(func.count(BotPartner.id)).where(
        BotPartner.bot_id == bot_id, BotPartner.status == "ACTIVE"
    )
    if exclude is not None:
        query = query.where(BotPartner.id != exclude)
    return int(await db.scalar(query) or 0)


async def active_percent_sum(
    db: AsyncSession, bot_id: uuid.UUID, exclude: uuid.UUID | None = None
) -> Decimal:
    """Sum of the cut of every ACTIVE partner of a bot (optionally excluding one partnership)."""
    query = select(func.coalesce(func.sum(BotPartner.partner_percent), 0)).where(
        BotPartner.bot_id == bot_id, BotPartner.status == "ACTIVE"
    )
    if exclude is not None:
        query = query.where(BotPartner.id != exclude)
    return Decimal(str(await db.scalar(query) or 0))


async def active_partners_of_bot(db: AsyncSession, bot_id: uuid.UUID) -> list[BotPartner]:
    return list(
        await db.scalars(
            select(BotPartner)
            .where(BotPartner.bot_id == bot_id, BotPartner.status == "ACTIVE")
            .order_by(BotPartner.created_at)
        )
    )


async def partnerships_of_bot(db: AsyncSession, bot_id: uuid.UUID) -> list[BotPartner]:
    return list(
        await db.scalars(
            select(BotPartner)
            .where(BotPartner.bot_id == bot_id, BotPartner.status != "REVOKED")
            .order_by(BotPartner.created_at)
        )
    )


async def shared_with(db: AsyncSession, partner_user_id: uuid.UUID) -> list[BotPartner]:
    """Partnerships where this user is the partner (shared bots in their panel)."""
    return list(
        await db.scalars(
            select(BotPartner)
            .where(
                BotPartner.partner_user_id == partner_user_id,
                BotPartner.status.in_(("PENDING", "ACTIVE", "PAUSED")),
            )
            .order_by(BotPartner.created_at.desc())
        )
    )


@dataclass(frozen=True)
class PartnerAccess:
    partnership: BotPartner
    bot: TgBot
    owner_workspace: Workspace


async def partner_access(
    db: AsyncSession, user_id: uuid.UUID, bot_id: uuid.UUID, *, require_active: bool = True
) -> PartnerAccess | None:
    """The shared bot a user may act on as its partner, with the owner workspace it lives in."""
    states = ("ACTIVE",) if require_active else ("PENDING", "ACTIVE", "PAUSED")
    part = await db.scalar(
        select(BotPartner).where(
            BotPartner.bot_id == bot_id,
            BotPartner.partner_user_id == user_id,
            BotPartner.status.in_(states),
        )
    )
    if part is None:
        return None
    bot = await db.get(TgBot, bot_id)
    if bot is None:
        return None
    workspace = await db.get(Workspace, bot.workspace_id)
    if workspace is None:
        return None
    return PartnerAccess(partnership=part, bot=bot, owner_workspace=workspace)


async def record_sale_split(db: AsyncSession, order: TgOrder) -> list[BotPartnerSale]:
    """On a paid order, record the split for every active partner of the bot, once each.

    One ledger row per (order, partnership). ``net`` is the order net after the gateway fee
    minus that partnership's bot fee; the partner's percent of that net is theirs and the
    owner keeps the rest (per row, relative to that partner). Idempotent: a partner already
    recorded for this order is skipped. Returns the rows created (empty when the bot has no
    active partner or everything was already recorded). Caller commits.
    """
    parts = await active_partners_of_bot(db, order.bot_id)
    if not parts:
        return []
    gross = money(order.amount)
    gateway_fee = money(order.gateway_fee) if order.gateway_fee is not None else Decimal("0.00")
    net_after_gateway = money(order.net_amount) if order.net_amount is not None else gross - gateway_fee
    created: list[BotPartnerSale] = []
    for part in parts:
        already = await db.scalar(
            select(BotPartnerSale.id).where(
                BotPartnerSale.order_id == order.id, BotPartnerSale.partnership_id == part.id
            )
        )
        if already:
            continue
        bot_fee = money(part.bot_fee)
        net = net_after_gateway - bot_fee
        if net < 0:
            net = Decimal("0.00")
        partner_amount = _floor(net * part.partner_percent / Decimal(100))
        owner_amount = net - partner_amount
        sale = BotPartnerSale(
            partnership_id=part.id,
            order_id=order.id,
            bot_id=order.bot_id,
            owner_user_id=part.owner_user_id,
            partner_user_id=part.partner_user_id,
            gross=gross,
            gateway_fee=gateway_fee,
            bot_fee=bot_fee,
            net=net,
            partner_percent=part.partner_percent,
            partner_amount=partner_amount,
            owner_amount=owner_amount,
            paid_at=order.paid_at or utc_now(),
        )
        db.add(sale)
        created.append(sale)
    return created


async def finance_summary(
    db: AsyncSession, part: BotPartner, start: datetime | None, end: datetime | None, limit: int = 200
) -> dict:
    """Totals and the per-sale ledger for one partnership, optionally within a period."""
    conds = [BotPartnerSale.partnership_id == part.id]
    if start is not None:
        conds.append(BotPartnerSale.paid_at >= start)
    if end is not None:
        conds.append(BotPartnerSale.paid_at < end)

    totals = (
        await db.execute(
            select(
                func.count(BotPartnerSale.id),
                func.coalesce(func.sum(BotPartnerSale.gross), 0),
                func.coalesce(func.sum(BotPartnerSale.gateway_fee), 0),
                func.coalesce(func.sum(BotPartnerSale.bot_fee), 0),
                func.coalesce(func.sum(BotPartnerSale.net), 0),
                func.coalesce(func.sum(BotPartnerSale.partner_amount), 0),
                func.coalesce(func.sum(BotPartnerSale.owner_amount), 0),
            ).where(*conds)
        )
    ).one()
    count, gross, gateway_fee, bot_fee, net, partner_amount, owner_amount = totals

    rows = list(await db.scalars(select(BotPartnerSale).where(*conds).order_by(BotPartnerSale.paid_at.desc()).limit(limit)))
    sales = [
        {
            "id": str(s.id),
            "order_id": str(s.order_id),
            "paid_at": s.paid_at.isoformat(),
            "gross": float(s.gross),
            "gateway_fee": float(s.gateway_fee),
            "bot_fee": float(s.bot_fee),
            "net": float(s.net),
            "partner_percent": float(s.partner_percent),
            "partner_amount": float(s.partner_amount),
            "owner_amount": float(s.owner_amount),
            "payout_status": s.payout_status,
            "status_note": s.status_note,
            "status_changed_at": s.status_changed_at.isoformat() if s.status_changed_at else None,
        }
        for s in rows
    ]

    # Partner commission totalled by settlement status (over the whole period, not just the
    # page shown above).
    status_rows = (
        await db.execute(
            select(
                BotPartnerSale.payout_status,
                func.count(BotPartnerSale.id),
                func.coalesce(func.sum(BotPartnerSale.partner_amount), 0),
            )
            .where(*conds)
            .group_by(BotPartnerSale.payout_status)
        )
    ).all()
    by_status = {
        s: {"count": 0, "partner_amount": 0.0} for s in ("pending", "paid", "denied")
    }
    for status, cnt, amount in status_rows:
        by_status[status] = {"count": int(cnt or 0), "partner_amount": float(amount)}

    # Withdrawals / payouts, filtered to the same period.
    pconds = [BotPartnerPayout.partnership_id == part.id]
    if start is not None:
        pconds.append(BotPartnerPayout.paid_at >= start)
    if end is not None:
        pconds.append(BotPartnerPayout.paid_at < end)
    payout_rows = list(
        await db.scalars(select(BotPartnerPayout).where(*pconds).order_by(BotPartnerPayout.paid_at.desc()).limit(limit))
    )
    payouts = [
        {
            "id": str(p.id),
            "party": p.party,
            "amount": float(p.amount),
            "note": p.note,
            "paid_at": p.paid_at.isoformat(),
        }
        for p in payout_rows
    ]
    withdrawn = {"owner": Decimal("0.00"), "partner": Decimal("0.00")}
    for p in payout_rows:
        withdrawn[p.party] = withdrawn.get(p.party, Decimal("0.00")) + p.amount

    return {
        "partner_percent": float(part.partner_percent),
        "bot_fee": float(part.bot_fee),
        "totals": {
            "sales": int(count or 0),
            "gross": float(gross),
            "gateway_fee": float(gateway_fee),
            "bot_fee": float(bot_fee),
            "net": float(net),
            "partner_amount": float(partner_amount),
            "owner_amount": float(owner_amount),
            "partner_withdrawn": float(money(withdrawn["partner"])),
            "owner_withdrawn": float(money(withdrawn["owner"])),
            "partner_balance": float(money(Decimal(str(partner_amount)) - withdrawn["partner"])),
            "owner_balance": float(money(Decimal(str(owner_amount)) - withdrawn["owner"])),
        },
        "by_status": by_status,
        "sales": sales,
        "payouts": payouts,
    }


async def set_sale_status(
    db: AsyncSession,
    sale: BotPartnerSale,
    status: str,
    *,
    by_user_id: uuid.UUID,
    note: str | None = None,
) -> BotPartnerSale:
    """Mark a recorded commission as paid/denied/pending. Caller commits."""
    sale.payout_status = status
    sale.status_note = (note or "").strip() or None
    sale.status_changed_at = utc_now()
    sale.status_by_user_id = by_user_id
    return sale


async def notify_partner_sales(db: AsyncSession, sales: list[BotPartnerSale]) -> None:
    """After a shared-bot sale is recorded, tell each partner their cut: in-app + web push
    (via notify_user) and, if they set one, an HTTP webhook. Best-effort; never raises."""
    import logging

    log = logging.getLogger(__name__)
    for sale in sales:
        try:
            part = await db.get(BotPartner, sale.partnership_id)
            bot = await db.get(TgBot, sale.bot_id)
            bot_name = bot.name if bot is not None else "bot"
            gross = money(sale.gross)
            share = money(sale.partner_amount)
            await notify_user(
                db,
                sale.partner_user_id,
                "bot_partner_sale",
                "Nova venda na parceria 💸",
                f"Venda de {gross} no {bot_name}. Sua parte ({sale.partner_percent}%): {share}.",
                url="/bot/parceiros",
            )
            await db.commit()
            if part is not None and part.notify_webhook_url:
                await _post_sale_webhook(part.notify_webhook_url, sale, bot_name)
        except Exception:
            await db.rollback()
            log.exception("Partner sale notification failed for sale %s.", sale.id)


async def _post_sale_webhook(url: str, sale: BotPartnerSale, bot_name: str) -> None:
    """POST a compact JSON about the sale to the partner's webhook. Best-effort, short timeout."""
    import logging

    from app.bots import http

    payload = {
        "event": "bot_partner_sale",
        "bot": bot_name,
        "gross": float(money(sale.gross)),
        "gateway_fee": float(money(sale.gateway_fee)),
        "bot_fee": float(money(sale.bot_fee)),
        "net": float(money(sale.net)),
        "partner_percent": float(sale.partner_percent),
        "partner_amount": float(money(sale.partner_amount)),
        "paid_at": sale.paid_at.isoformat(),
    }
    try:
        async with http.client(10.0) as session:
            await session.post(url, json=payload)
    except Exception:
        logging.getLogger(__name__).warning("Partner sale webhook POST failed (sale %s).", sale.id)


async def notify_partner_invite(db: AsyncSession, part: BotPartner, owner: User, bot: TgBot) -> None:
    await notify_user(
        db,
        part.partner_user_id,
        "bot_partner_invite",
        "Convite de parceria de bot",
        f"{owner.full_name or owner.nickname} quer dividir o bot {bot.name} com você ({part.partner_percent}%).",
        url="/bot/parceiros",
    )


async def notify_owner_accepted(db: AsyncSession, part: BotPartner, partner: User, bot: TgBot) -> None:
    await notify_user(
        db,
        part.owner_user_id,
        "bot_partner_accepted",
        "Parceria aceita",
        f"{partner.full_name or partner.nickname} aceitou a parceria do bot {bot.name}.",
        url="/bot",
    )
