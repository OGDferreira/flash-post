"""Bots and funnels the Super Admin hid from the operation that owns them.

They keep running, but the owner never sees them: not in the lists, the panels, the sales or
the revenue, and they get no notice about them. Only the Super Admin, inside the account
("Acessar conta"), sees and manages them.
"""
from contextvars import ContextVar

from fastapi import Request
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import aliased

from app.models import TgBot

_ADMIN_VIEW: ContextVar[bool] = ContextVar("bots_admin_view", default=False)


async def mark_admin_view(request: Request) -> None:
    """Router dependency: is the Super Admin looking at this account from the inside?"""
    _ADMIN_VIEW.set(isinstance(request.session.get("impersonator_id"), str))


def admin_view() -> bool:
    return _ADMIN_VIEW.get()


def not_hidden_bot(column, *, seller: bool = True):
    """Rows (leads, orders) the operation sees: not of a bot hidden from it, nor of a bot the
    Super Admin took over (it now lives in another operation), nor (``seller``) a sale or lead
    of a funnel whose owner takes 100%. Pass ``seller=False`` where the funnel's owner (chief)
    looks at their commissions: those sales are theirs."""
    rows = column.class_
    bot = aliased(TgBot)  # never correlated with a tg_bots the outer query may join
    gone = select(bot.id).where(or_(bot.hidden_by_admin.is_(True), bot.workspace_id != rows.workspace_id))
    shown = or_(column.is_(None), column.not_in(gone))
    if seller and hasattr(rows, "seller_hidden"):
        return and_(shown, rows.seller_hidden.is_(False))
    return shown
