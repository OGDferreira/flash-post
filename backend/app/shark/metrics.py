"""SharkBot sales metrics for one workspace and period (single source of truth).

Used by the sales panel and by the affiliates tab, so both show the same
numbers for the same period. Attribution rule (also returned to the client):

* leads            -> by the time the lead joined (user_joined)
* PIX generated    -> by the time the PIX was generated (payment_created)
* purchases/revenue-> by the time the payment was approved (payment_approved)
* conversions      -> cohorts: of the PIX generated / leads that joined in the
  period, how many were paid (at any time up to now).
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import and_, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SharkLead, SharkTransaction

CRITERIA: dict[str, str] = {
    "leads": "Leads (user_joined) pela data em que entraram no período.",
    "pix_generated": "PIX gerados (payment_created) pela data de geração no período, pagos ou não.",
    "purchases": "Compras pagas (payment_approved) pela data de aprovação no período. PIX pendente não é venda.",
    "revenue": "Soma dos valores das compras pagas no período. Compras sem valor informado não entram na soma.",
    "pix_to_paid_rate": "Coorte: dos PIX gerados no período, % que já foi pago (em qualquer data até agora). Pagos ÷ gerados.",
    "lead_to_purchase_rate": "Coorte: dos leads que entraram no período, % que já tem uma compra paga (mesmo bot e cliente).",
    "leads_per_purchase": "Leads do período ÷ compras pagas do período. Sem compras no período, fica indisponível.",
    "average_ticket": "Receita ÷ compras pagas com valor informado (apenas vendas pagas).",
}


@dataclass
class SharkMetrics:
    leads: int = 0
    lead_buyers: int = 0
    pix_generated: int = 0
    pix_paid_from_period: int = 0
    purchases: int = 0
    purchases_without_amount: int = 0
    revenue: Decimal = Decimal("0.00")
    pix_to_paid_rate: float | None = None
    lead_to_purchase_rate: float | None = None
    leads_per_purchase: float | None = None
    average_ticket: Decimal | None = None


def _rate(part: int, base: int) -> float | None:
    return round(part / base * 100, 1) if base else None


def window(column, start: datetime | None, end: datetime | None) -> list:
    conditions = []
    if start is not None:
        conditions.append(column >= start)
    if end is not None:
        conditions.append(column < end)
    return conditions


def scope_conditions(
    model,
    workspace_id: UUID,
    account_id: UUID | None = None,
    shark_account_id: UUID | None = None,
) -> list:
    conditions = [model.workspace_id == workspace_id]
    if account_id is not None:
        conditions.append(model.account_id == account_id)
    if shark_account_id is not None:
        conditions.append(model.shark_account_id == shark_account_id)
    return conditions


async def compute_shark_metrics(
    db: AsyncSession,
    workspace_id: UUID,
    start: datetime | None,
    end: datetime | None,
    *,
    account_id: UUID | None = None,
    shark_account_id: UUID | None = None,
) -> SharkMetrics:
    lead_scope = scope_conditions(SharkLead, workspace_id, account_id, shark_account_id)
    tx_scope = scope_conditions(SharkTransaction, workspace_id, account_id, shark_account_id)
    paid_for_lead = exists().where(
        and_(
            SharkTransaction.workspace_id == SharkLead.workspace_id,
            SharkTransaction.lead_key == SharkLead.lead_key,
            SharkTransaction.status == "paid",
        )
    )
    leads, lead_buyers = (
        await db.execute(
            select(
                func.count(SharkLead.id),
                func.count(SharkLead.id).filter(paid_for_lead),
            ).where(*lead_scope, *window(SharkLead.joined_at, start, end))
        )
    ).one()
    pix_generated, pix_paid = (
        await db.execute(
            select(
                func.count(SharkTransaction.id),
                func.count(SharkTransaction.id).filter(SharkTransaction.status == "paid"),
            ).where(*tx_scope, *window(SharkTransaction.created_at_source, start, end))
        )
    ).one()
    purchases, revenue, without_amount = (
        await db.execute(
            select(
                func.count(SharkTransaction.id),
                func.coalesce(func.sum(SharkTransaction.amount), 0),
                func.count(SharkTransaction.id).filter(SharkTransaction.amount.is_(None)),
            ).where(
                *tx_scope,
                SharkTransaction.status == "paid",
                SharkTransaction.paid_at.is_not(None),
                *window(SharkTransaction.paid_at, start, end),
            )
        )
    ).one()
    revenue = Decimal(str(revenue or 0)).quantize(Decimal("0.01"))
    priced = purchases - without_amount
    return SharkMetrics(
        leads=leads,
        lead_buyers=lead_buyers,
        pix_generated=pix_generated,
        pix_paid_from_period=pix_paid,
        purchases=purchases,
        purchases_without_amount=without_amount,
        revenue=revenue,
        pix_to_paid_rate=_rate(pix_paid, pix_generated),
        lead_to_purchase_rate=_rate(lead_buyers, leads),
        leads_per_purchase=round(leads / purchases, 2) if purchases else None,
        average_ticket=(revenue / priced).quantize(Decimal("0.01")) if priced > 0 else None,
    )
