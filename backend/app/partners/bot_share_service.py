"""Bot partnership rules: sharing a whole bot (and the funnel it runs) with an independent
user, the per-sale split and the finance panel both sides read.

A bot has at most one ACTIVE partner at a time (the split ledger keys one row per order).
The owner may invite another while one is active, but it only becomes ACTIVE once the first
is paused/revoked.
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


async def record_sale_split(db: AsyncSession, order: TgOrder) -> BotPartnerSale | None:
    """On a paid order, record the partner split once. Caller commits.

    net = order net after the gateway fee, minus the partnership's bot fee; the partner's
    percent of that net is theirs, the owner keeps the rest. Returns None when the bot has
    no active partner or the sale is already recorded.
    """
    part = await db.scalar(
        select(BotPartner).where(BotPartner.bot_id == order.bot_id, BotPartner.status == "ACTIVE")
    )
    if part is None:
        return None
    if await db.scalar(select(BotPartnerSale.id).where(BotPartnerSale.order_id == order.id)):
        return None
    gross = money(order.amount)
    gateway_fee = money(order.gateway_fee) if order.gateway_fee is not None else Decimal("0.00")
    net_after_gateway = money(order.net_amount) if order.net_amount is not None else gross - gateway_fee
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
    return sale


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
        }
        for s in rows
    ]

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
        "sales": sales,
        "payouts": payouts,
    }


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
