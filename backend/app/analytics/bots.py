"""SharkBot performance by bot and by flow (owner only)."""

from datetime import date
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import String, and_, exists, func, select

from app.analytics.periods import AnalyticsPeriod, period_bounds, period_label
from app.auth.dependencies import DbSession, OwnerAccess
from app.core.time import APP_TIME_ZONE_NAME, utc_now
from app.models import SharkAccount, SharkLead, SharkTransaction

router = APIRouter(prefix="/api/analytics", tags=["Bot performance"])

UNKNOWN = "__none__"


class BotPerformanceRow(BaseModel):
    key: str
    shark_account_id: str | None = None
    shark_account_name: str | None = None
    bot_id: str | None
    bot_name: str | None
    flow_id: str | None
    flow_name: str | None
    # Event counts inside the period (each by its own date).
    leads: int
    pix_generated: int
    payments_approved: int
    revenue: Decimal
    payments_without_amount: int
    # Cohorts: of the leads that joined / PIX generated in the period, how many
    # became paid (at any time up to now). Rates are None when the base is 0.
    lead_buyers: int
    lead_to_buyer_rate: float | None
    pix_paid_from_period: int
    pix_to_paid_rate: float | None
    average_ticket: Decimal | None


class BotPerformanceResponse(BaseModel):
    group_by: Literal["bot", "flow"]
    period: str
    period_label: str
    time_zone: str
    totals: BotPerformanceRow
    rows: list[BotPerformanceRow]
    criteria: dict[str, str]


def _rate(part: int, base: int) -> float | None:
    return round(part / base * 100, 1) if base else None


@router.get("/bots", response_model=BotPerformanceResponse)
async def bot_performance(
    access: OwnerAccess,
    db: DbSession,
    period: AnalyticsPeriod = "30d",
    start_date: date | None = None,
    end_date: date | None = None,
    group_by: Literal["bot", "flow"] = "bot",
    sort: Literal["revenue", "sales", "leads", "conversion"] = "revenue",
    order: Literal["desc", "asc"] = "desc",
) -> BotPerformanceResponse:
    start, end = period_bounds(period, start_date, end_date, utc_now())
    workspace_id = access.workspace.id

    def keys(model):
        # Shark accounts are separate systems: their bot/flow ids must never merge.
        account = func.coalesce(func.cast(model.shark_account_id, String), UNKNOWN)
        bot = func.coalesce(model.bot_id, UNKNOWN)
        flow = func.coalesce(model.flow_id, UNKNOWN)
        return (account, bot, flow) if group_by == "flow" else (account, bot)

    def window(column):
        conditions = []
        if start is not None:
            conditions.append(column >= start)
        if end is not None:
            conditions.append(column < end)
        return conditions

    rows: dict[tuple, dict] = {}

    def row(key: tuple) -> dict:
        return rows.setdefault(
            key,
            {
                "leads": 0, "pix_generated": 0, "payments_approved": 0,
                "revenue": Decimal("0.00"), "payments_without_amount": 0,
                "lead_buyers": 0, "pix_paid_from_period": 0,
                "bot_name": None, "flow_name": None,
            },
        )

    lead_keys = keys(SharkLead)
    paid_for_lead = exists().where(
        and_(
            SharkTransaction.workspace_id == SharkLead.workspace_id,
            SharkTransaction.lead_key == SharkLead.lead_key,
            SharkTransaction.status == "paid",
        )
    )
    for *key, count, buyers, bot_name, flow_name in await db.execute(
        select(
            *lead_keys,
            func.count(SharkLead.id),
            func.count(SharkLead.id).filter(paid_for_lead),
            func.max(SharkLead.bot_name),
            func.max(SharkLead.flow_name),
        )
        .where(SharkLead.workspace_id == workspace_id, *window(SharkLead.joined_at))
        .group_by(*lead_keys)
    ):
        item = row(tuple(key))
        item["leads"] = count
        item["lead_buyers"] = buyers
        item["bot_name"] = item["bot_name"] or bot_name
        item["flow_name"] = item["flow_name"] or flow_name

    tx_keys = keys(SharkTransaction)
    for *key, count, paid_count, bot_name, flow_name in await db.execute(
        select(
            *tx_keys,
            func.count(SharkTransaction.id),
            func.count(SharkTransaction.id).filter(SharkTransaction.status == "paid"),
            func.max(SharkTransaction.bot_name),
            func.max(SharkTransaction.flow_name),
        )
        .where(SharkTransaction.workspace_id == workspace_id, *window(SharkTransaction.created_at_source))
        .group_by(*tx_keys)
    ):
        item = row(tuple(key))
        item["pix_generated"] = count
        item["pix_paid_from_period"] = paid_count
        item["bot_name"] = item["bot_name"] or bot_name
        item["flow_name"] = item["flow_name"] or flow_name

    for *key, count, revenue, missing, bot_name, flow_name in await db.execute(
        select(
            *tx_keys,
            func.count(SharkTransaction.id),
            func.coalesce(func.sum(SharkTransaction.amount), 0),
            func.count(SharkTransaction.id).filter(SharkTransaction.amount.is_(None)),
            func.max(SharkTransaction.bot_name),
            func.max(SharkTransaction.flow_name),
        )
        .where(
            SharkTransaction.workspace_id == workspace_id,
            SharkTransaction.status == "paid",
            SharkTransaction.paid_at.is_not(None),
            *window(SharkTransaction.paid_at),
        )
        .group_by(*tx_keys)
    ):
        item = row(tuple(key))
        item["payments_approved"] = count
        item["revenue"] = Decimal(str(revenue or 0)).quantize(Decimal("0.01"))
        item["payments_without_amount"] = missing
        item["bot_name"] = item["bot_name"] or bot_name
        item["flow_name"] = item["flow_name"] or flow_name

    account_names = {
        str(account_id): name
        for account_id, name in await db.execute(
            select(SharkAccount.id, SharkAccount.name).where(SharkAccount.workspace_id == workspace_id)
        )
    }

    def build(key: tuple, data: dict) -> BotPerformanceRow:
        if key[0] == "__total__":
            key = (UNKNOWN, UNKNOWN)
        account_key = None if key[0] == UNKNOWN else key[0]
        bot_id = None if key[1] == UNKNOWN else key[1]
        flow_id = None if len(key) < 3 or key[2] == UNKNOWN else key[2]
        priced = data["payments_approved"] - data["payments_without_amount"]
        return BotPerformanceRow(
            key="|".join(key),
            shark_account_id=account_key,
            shark_account_name=account_names.get(account_key) if account_key else None,
            bot_id=bot_id,
            bot_name=data["bot_name"],
            flow_id=flow_id,
            flow_name=data["flow_name"],
            leads=data["leads"],
            pix_generated=data["pix_generated"],
            payments_approved=data["payments_approved"],
            revenue=data["revenue"],
            payments_without_amount=data["payments_without_amount"],
            lead_buyers=data["lead_buyers"],
            lead_to_buyer_rate=_rate(data["lead_buyers"], data["leads"]),
            pix_paid_from_period=data["pix_paid_from_period"],
            pix_to_paid_rate=_rate(data["pix_paid_from_period"], data["pix_generated"]),
            average_ticket=(data["revenue"] / priced).quantize(Decimal("0.01")) if priced > 0 else None,
        )

    built = [build(key, data) for key, data in rows.items()]
    sort_key = {
        "revenue": lambda item: (item.revenue, item.payments_approved),
        "sales": lambda item: (item.payments_approved, item.revenue),
        "leads": lambda item: (item.leads, item.payments_approved),
        "conversion": lambda item: (
            item.lead_to_buyer_rate if item.lead_to_buyer_rate is not None else -1,
            item.leads,
        ),
    }[sort]
    built.sort(key=sort_key, reverse=order == "desc")

    # Totals are sums of disjoint groups: each lead/transaction has exactly one
    # bot (and flow), so nothing is counted twice.
    total = {
        "leads": sum(r.leads for r in built),
        "pix_generated": sum(r.pix_generated for r in built),
        "payments_approved": sum(r.payments_approved for r in built),
        "revenue": sum((r.revenue for r in built), Decimal("0.00")),
        "payments_without_amount": sum(r.payments_without_amount for r in built),
        "lead_buyers": sum(r.lead_buyers for r in built),
        "pix_paid_from_period": sum(r.pix_paid_from_period for r in built),
        "bot_name": "Total",
        "flow_name": None,
    }
    totals = build(("__total__",), total)
    totals.bot_id = None
    return BotPerformanceResponse(
        group_by=group_by,
        period=period,
        period_label=period_label(start, end),
        time_zone=APP_TIME_ZONE_NAME,
        totals=totals,
        rows=built,
        criteria={
            "leads": "Leads (user_joined) com data de entrada no período.",
            "pix_generated": "PIX gerados (payment_created) com data de geração no período, pagos ou não.",
            "payments_approved": "Pagamentos aprovados (payment_approved) com data de aprovação no período.",
            "revenue": "Soma dos valores dos pagamentos aprovados no período. PIX pendente não entra.",
            "lead_to_buyer_rate": "Coorte: dos leads que entraram no período, % que já tem um pagamento aprovado (mesmo bot e cliente).",
            "pix_to_paid_rate": "Coorte: dos PIX gerados no período, % que já foi aprovado.",
            "average_ticket": "Receita ÷ pagamentos aprovados com valor informado.",
        },
    )



