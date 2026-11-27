"""Native A/B test of two funnel versions on a bot.

While a test is active on a bot, each new lead is drawn once into variant A or B by ``weight_a``
(percent) and keeps that funnel. Both variants are ordinary funnels, so the lead's whole journey —
leads, orders, sales — is already keyed by ``flow_id``; :func:`results` just splits those metrics
by the test's two funnels so the owner can see which version converts better."""
import secrets
from datetime import timedelta
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import TgAbTest, TgBot, TgLead, TgOrder


async def active_test_for(db: AsyncSession, bot: TgBot) -> TgAbTest | None:
    """The bot's running A/B test, or None."""
    if bot.ab_test_id is None:
        return None
    test = await db.get(TgAbTest, bot.ab_test_id)
    if test is None or test.status != "active" or test.bot_id != bot.id:
        return None
    return test


def draw_variant(test: TgAbTest) -> uuid.UUID:
    """Pick variant A or B for a new lead, weighted by ``weight_a`` (percent)."""
    return test.flow_a_id if secrets.randbelow(100) < test.weight_a else test.flow_b_id


async def draw_ab_flow(db: AsyncSession, bot: TgBot, lead: TgLead, *, force: bool = False) -> uuid.UUID | None:
    """Give an A/B bot's lead a variant: drawn once and kept. Redrawn for a brand-new lead
    (``force``) or when the lead's funnel is no longer one of the two variants (e.g. the test was
    replaced). No-op if the bot has no active test."""
    test = await active_test_for(db, bot)
    if test is None:
        return lead.flow_id
    variants = (test.flow_a_id, test.flow_b_id)
    if force or lead.flow_id not in variants:
        lead.flow_id = draw_variant(test)
    return lead.flow_id


async def _variant_metrics(db: AsyncSession, bot: TgBot, test: TgAbTest, flow_id: uuid.UUID) -> dict:
    """Leads, Pix generated, sales, revenue and conversion of one variant since the test started."""
    # Count only traffic from when the test began, so a variant that is a pre-existing funnel does
    # not drag its old numbers in. The 2s guard absorbs the second-precision timestamps SQLite
    # stores for server-side defaults (Postgres keeps full precision, so the guard is harmless).
    since = (test.created_at - timedelta(seconds=2)) if test.created_at else None
    if since is None:
        return {"flow_id": str(flow_id), "leads": 0, "pix": 0, "sales": 0, "buyers": 0, "revenue": "0.00", "conversion": 0.0}
    leads = await db.scalar(
        select(func.count(TgLead.id)).where(
            TgLead.bot_id == bot.id, TgLead.flow_id == flow_id, TgLead.created_at >= since
        )
    )
    # One lead can open several orders; count the distinct leads who generated a Pix / who paid.
    pix = await db.scalar(
        select(func.count(func.distinct(TgOrder.lead_id))).where(
            TgOrder.bot_id == bot.id, TgOrder.flow_id == flow_id, TgOrder.created_at >= since
        )
    )
    sales = await db.scalar(
        select(func.count(TgOrder.id)).where(
            TgOrder.bot_id == bot.id, TgOrder.flow_id == flow_id,
            TgOrder.status == "paid", TgOrder.paid_at >= since,
        )
    )
    buyers = await db.scalar(
        select(func.count(func.distinct(TgOrder.lead_id))).where(
            TgOrder.bot_id == bot.id, TgOrder.flow_id == flow_id,
            TgOrder.status == "paid", TgOrder.paid_at >= since,
        )
    )
    revenue = await db.scalar(
        select(func.coalesce(func.sum(TgOrder.amount), 0)).where(
            TgOrder.bot_id == bot.id, TgOrder.flow_id == flow_id,
            TgOrder.status == "paid", TgOrder.paid_at >= since,
        )
    )
    leads_n = int(leads or 0)
    buyers_n = int(buyers or 0)
    conversion = round(buyers_n / leads_n * 100, 1) if leads_n else 0.0
    return {
        "flow_id": str(flow_id),
        "leads": leads_n,
        "pix": int(pix or 0),
        "sales": int(sales or 0),
        "buyers": buyers_n,
        "revenue": f"{revenue or 0:.2f}",
        "conversion": conversion,
    }


async def results(db: AsyncSession, bot: TgBot, test: TgAbTest) -> dict:
    """Side-by-side metrics of the two variants."""
    a = await _variant_metrics(db, bot, test, test.flow_a_id)
    b = await _variant_metrics(db, bot, test, test.flow_b_id)
    return {"a": a, "b": b}
