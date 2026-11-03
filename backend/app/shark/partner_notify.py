"""Tell a sócio's chief about a SharkBot sale paid in the sócio's workspace.

Money moves inside SharkBot (the chief configures the split there), so this is
only a notice: it never touches the wallet. The commission shown is an estimate
from the percentage agreed in the partner link.
"""

from __future__ import annotations

import logging
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Affiliation, User, Workspace
from app.partners.service import money, notify_user

logger = logging.getLogger(__name__)


def _brl(value: Decimal) -> str:
    text = f"{value:,.2f}"
    return "R$ " + text.replace(",", "X").replace(".", ",").replace("X", ".")


async def notify_chief_of_sale(db: AsyncSession, workspace: Workspace, amounts: list[Decimal | None]) -> int:
    """One push per newly paid sale. Returns how many notices were queued (caller commits)."""
    if not amounts:
        return 0
    link = await db.scalar(
        select(Affiliation).where(
            Affiliation.affiliate_user_id == workspace.owner_id, Affiliation.status == "ACTIVE"
        )
    )
    if link is None:
        return 0
    seller = await db.get(User, workspace.owner_id)
    first = ((seller.nickname or seller.full_name or "").split() or ["sócio"])[0] if seller else "sócio"
    percent = link.accepted_percent if link.accepted_percent is not None else link.participation_percent
    for amount in amounts:
        if amount is None:
            body = f"{first} fez uma venda na SharkBot 🤑"
        else:
            body = f"{first} vendeu {_brl(amount)} na SharkBot 🤑"
            if percent and percent > 0:
                commission = money((amount * percent / Decimal("100")).quantize(Decimal("0.01"), ROUND_HALF_UP))
                body += f" · comissão estimada {_brl(commission)}"
        await notify_user(db, link.chief_user_id, "commission", "💰 Venda do sócio!", body, "/dashboard")
    return len(amounts)
