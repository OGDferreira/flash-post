"""LTV do lead: quanto cada lead que entrou no período rende ao longo de TODA a vida dele,
não só no período. Enquanto `analytics_full` conta o dinheiro que entrou na janela, aqui a
janela só escolhe a safra de leads (quem deu /start no período); depois somamos cada venda
paga desses leads em qualquer data — plano principal + upsell + downsell + remarketing.

Assim dá pra ver, além do valor da primeira venda, quanto o lead ainda rende depois dela
(a "expansão": upsell, remarketing e recompra). Filtrável por período e por bot/funil.
"""

import uuid
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bots.hidden import not_hidden_bot
from app.core.time import as_utc
from app.models import TgLead, TgOrder

KINDS = ("plan", "upsell", "downsell", "remarketing")


def _f(value) -> float:
    return round(float(value or 0), 2)


def _pct(part: float, whole: float) -> float:
    return round(100 * part / whole, 1) if whole else 0.0


def _kind(kind: str | None) -> str:
    return kind if kind in KINDS else "plan"


def _lead_name(first_name: str | None, username: str | None) -> str:
    name = (first_name or "").strip()
    if name:
        return name
    if username:
        return f"@{username}"
    return "Lead"


async def lead_ltv(
    db: AsyncSession, workspace_id: uuid.UUID, start: datetime, end: datetime, zone: ZoneInfo, *,
    bot_id: uuid.UUID | None = None, flow_id: uuid.UUID | None = None, hide: bool = False,
    top: int = 20,
) -> dict:
    # A safra: leads que entraram na janela, com os filtros de bot/funil.
    lead_filters = [TgLead.workspace_id == workspace_id, TgLead.created_at >= start, TgLead.created_at < end]
    if hide:
        lead_filters.append(not_hidden_bot(TgLead.bot_id))
    if bot_id:
        lead_filters.append(TgLead.bot_id == bot_id)
    if flow_id:
        lead_filters.append(TgLead.flow_id == flow_id)
    cohort_size = len((await db.execute(select(TgLead.id).where(*lead_filters))).all())

    # Toda venda paga desses leads, em QUALQUER data (vida inteira).
    order_rows = (await db.execute(
        select(
            TgOrder.lead_id, TgOrder.kind, TgOrder.amount, TgOrder.paid_at, TgOrder.offer_name,
            TgLead.first_name, TgLead.username,
        )
        .join(TgLead, TgLead.id == TgOrder.lead_id)
        .where(*lead_filters, TgOrder.status == "paid")
    )).all()

    per_lead: dict[uuid.UUID, dict] = defaultdict(
        lambda: {"name": "Lead", "total": Decimal("0"), "orders": 0, "first_amount": None,
                 "first_at": None, "kinds": set()}
    )
    by_kind: dict[str, list] = {k: [0, Decimal("0")] for k in KINDS}
    total_ltv = Decimal("0")
    for row in order_rows:
        amount = Decimal(row.amount or 0)
        kind = _kind(row.kind)
        total_ltv += amount
        by_kind[kind][0] += 1
        by_kind[kind][1] += amount
        lead = per_lead[row.lead_id]
        lead["name"] = _lead_name(row.first_name, row.username)
        lead["total"] += amount
        lead["orders"] += 1
        lead["kinds"].add(kind)
        moment = as_utc(row.paid_at) if row.paid_at else None
        if moment is not None and (lead["first_at"] is None or moment < lead["first_at"]):
            lead["first_at"] = moment
            lead["first_amount"] = amount

    buyers = len(per_lead)
    first_sale_total = sum((v["first_amount"] or Decimal("0") for v in per_lead.values()), Decimal("0"))
    expansion = total_ltv - first_sale_total
    avg_ltv = total_ltv / buyers if buyers else Decimal("0")
    avg_first = first_sale_total / buyers if buyers else Decimal("0")

    ranked = sorted(per_lead.values(), key=lambda v: v["total"], reverse=True)[: max(1, top)]
    top_leads = [
        {
            "name": v["name"],
            "ltv": _f(v["total"]),
            "first_sale": _f(v["first_amount"]),
            "first_at": v["first_at"].astimezone(zone).date().isoformat() if v["first_at"] else None,
            "orders": v["orders"],
            "kinds": sorted(v["kinds"]),
        }
        for v in ranked
    ]

    return {
        "summary": {
            "cohort": cohort_size,
            "buyers": buyers,
            "conversion": _pct(buyers, cohort_size),
            "total_ltv": _f(total_ltv),
            "avg_ltv": _f(avg_ltv),
            "avg_first_sale": _f(avg_first),
            "avg_ltv_per_lead": _f(total_ltv / cohort_size) if cohort_size else 0.0,
            # Quanto a vida do lead rende além da 1ª venda (ex.: 1,6× = +60% depois da entrada).
            "uplift": round(float(avg_ltv / avg_first), 2) if avg_first else 0.0,
            "expansion_revenue": _f(expansion),
            "orders": sum(v[0] for v in by_kind.values()),
        },
        "by_kind": [
            {"kind": k, "sales": by_kind[k][0], "revenue": _f(by_kind[k][1])}
            for k in KINDS
        ],
        "top_leads": top_leads,
    }
