"""Re-send, as push notifications, the sales of a past period ("Receber notificações de
vendas passadas" in Configurações). Same look as the live ones — "⚡ Nova venda!",
"🦈 Nova venda - Shark Bot!", "💰 Comissão recebida!" — plus the sale's time, since the
phone shows when the notice arrived. Push only: nothing is added to the in-app list.

Each notice gets its own tag and topic: with the shared ones of the live notices the phone
(or the push service) would keep only the last.
"""

import asyncio
import logging
import uuid
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.bots.hidden import not_hidden_bot
from app.core.time import as_utc
from app.models import PushSubscription, TgOrder, User, Workspace
from app.models.sharkbot import SharkTransaction

logger = logging.getLogger(__name__)
MAX_NOTICES = 100
PAUSE_SECONDS = 0.35  # oldest first, a little apart, so the newest ends on top


def _brl(value: Decimal | None) -> str:
    return f"R$ {Decimal(value or 0):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


async def collect(db, user: User, workspace: Workspace | None, start: datetime, end: datetime, zone: ZoneInfo) -> list[dict]:
    """The user's sales of [start, end): their operation's Flash sales, its SharkBot sales and
    the commissions they received; oldest first, at most MAX_NOTICES (the newest kept)."""
    items: list[tuple[datetime, dict]] = []

    def when(moment: datetime) -> str:
        return as_utc(moment).astimezone(zone).strftime("%d/%m às %H:%M")

    if workspace is not None:
        for paid_at, amount in (await db.execute(
            select(TgOrder.paid_at, TgOrder.amount).where(
                TgOrder.workspace_id == workspace.id, TgOrder.status == "paid", TgOrder.seller_hidden.is_(False),
                TgOrder.paid_at >= start, TgOrder.paid_at < end, not_hidden_bot(TgOrder.bot_id),
            )
        )).all():
            items.append((as_utc(paid_at), {"kind": "sale", "title": "⚡ Nova venda!",
                                            "body": f"Venda de {_brl(amount)} 🤑 · {when(paid_at)}", "url": "/bot"}))
        for paid_at, amount in (await db.execute(
            select(SharkTransaction.paid_at, SharkTransaction.amount).where(
                SharkTransaction.workspace_id == workspace.id, SharkTransaction.status == "paid",
                SharkTransaction.paid_at >= start, SharkTransaction.paid_at < end,
            )
        )).all():
            text = f"Você recebeu {_brl(amount)} 🤑" if amount else "Pagamento aprovado 🤑"
            items.append((as_utc(paid_at), {"kind": "sale", "title": "🦈 Nova venda - Shark Bot!",
                                            "body": f"{text} · {when(paid_at)}", "url": "/dashboard"}))
    sellers: dict[uuid.UUID, str] = {}
    for paid_at, amount, workspace_id in (await db.execute(
        select(TgOrder.paid_at, TgOrder.split_amount, TgOrder.workspace_id).where(
            TgOrder.split_chief_user_id == user.id, TgOrder.status == "paid", TgOrder.split_amount.is_not(None),
            TgOrder.paid_at >= start, TgOrder.paid_at < end, not_hidden_bot(TgOrder.bot_id, seller=False),
        )
    )).all():
        if workspace is not None and workspace_id == workspace.id:
            continue  # their own sale, already listed
        if workspace_id not in sellers:
            seller = await db.scalar(select(User.full_name).join(Workspace, Workspace.owner_id == User.id).where(Workspace.id == workspace_id))
            sellers[workspace_id] = ((seller or "sócio").split() or ["sócio"])[0]
        items.append((as_utc(paid_at), {"kind": "commission", "title": "💰 Comissão recebida!",
                                        "body": f"Você recebeu {_brl(amount)} 🤑 da venda de {sellers[workspace_id]} · {when(paid_at)}",
                                        "url": "/carteira"}))
    items.sort(key=lambda pair: pair[0])
    return [item for _moment, item in items[-MAX_NOTICES:]]


async def send(user_id: uuid.UUID, notices: list[dict]) -> int:
    """Push each notice to every device of the user (own session: runs after the request)."""
    from app.bots import http
    from app.core.database import get_session_factory
    from app.notifications.milestones import push_to
    from app.notifications.webpush import get_vapid_keys

    delivered = 0
    async with get_session_factory()() as db:
        try:
            subscriptions = list(await db.scalars(select(PushSubscription).where(PushSubscription.user_id == user_id)))
            if not subscriptions:
                return 0
            keys = await get_vapid_keys(db)
            batch = uuid.uuid4().hex[:8]
            async with http.client(15.0) as session:
                for index, notice in enumerate(notices):
                    tag = f"past-{batch}-{index}"
                    payload = {"title": notice["title"], "body": notice["body"], "url": notice["url"], "tag": tag,
                               "brand": "flashbot-dark"}
                    ok, _transient = await push_to(db, subscriptions, payload, keys, session, tag[:32])
                    delivered += 1 if ok else 0
                    await asyncio.sleep(PAUSE_SECONDS)
            await db.commit()
        except Exception:
            await db.rollback()
            logger.exception("Past sales notifications failed")
    return delivered
