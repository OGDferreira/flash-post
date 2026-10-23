"""Bots and funnels the Super Admin hid from the operation that owns them.

They keep running, but the owner never sees them: not in the lists, the panels, the sales or
the revenue, and they get no notice about them. Only the Super Admin, inside the account
("Acessar conta"), sees and manages them.
"""
from contextvars import ContextVar

from fastapi import Request
from sqlalchemy import or_, select

from app.models import TgBot

_ADMIN_VIEW: ContextVar[bool] = ContextVar("bots_admin_view", default=False)


async def mark_admin_view(request: Request) -> None:
    """Router dependency: is the Super Admin looking at this account from the inside?"""
    _ADMIN_VIEW.set(isinstance(request.session.get("impersonator_id"), str))


def admin_view() -> bool:
    return _ADMIN_VIEW.get()


def not_hidden_bot(column):
    """Rows (leads, orders) that don't belong to a hidden bot."""
    return or_(column.is_(None), column.not_in(select(TgBot.id).where(TgBot.hidden_by_admin.is_(True))))
