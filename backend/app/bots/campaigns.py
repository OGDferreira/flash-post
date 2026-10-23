"""Falcon Bot remarketing: broadcasts to one funnel's leads, each through the bot it came from.

Every funnel has its own campaigns (SharkBot's "Remarketing" per flow). A campaign is
built in five steps in the panel: campaign and funnel, audience, message, offer and
delivery, review. Sending runs from the bots worker tick in small batches, walking
the audience in lead id order so a restart never repeats a lead; the audience is
re-checked at send time (a lead who bought meanwhile drops out of "não compraram").
Purchases are normal orders (kind ``remarketing``) and deliver like any plan.
"""

import logging
import time
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, ValidationError, model_validator
from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import DbSession, OwnerAccess, require_csrf
from app.bots import engine
from app.bots.flow_schema import ButtonStyle, Delivery, FlowDefinition, LinkButton, MediaList3, Money, OrderBump, Plan, Text, _Model
from app.bots.telegram import TelegramClient, TelegramError
from app.core.time import BRAZIL_TIME_ZONE
from app.bots.hidden import admin_view, mark_admin_view
from app.models import TgBot, TgCampaign, TgFlow, TgLead, TgMedia, TgOrder, TgSubscription

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/bots/campaigns", tags=["Bots"], dependencies=[Depends(mark_admin_view)])
csrf = [Depends(require_csrf)]

BATCH = 25
TICK_BUDGET_SECONDS = 4.0

Target = Literal["all", "not_bought", "bought", "pix_generated", "vip_expired", "group_members"]
Period = Literal["total", "today", "yesterday", "7d", "30d", "custom"]


# ---------------------------------------------------------------- definition


class CampaignAudience(_Model):
    target: Target = "not_bought"
    period: Period = "total"  # by the date the lead entered the funnel
    start: date | None = None
    end: date | None = None

    @model_validator(mode="after")
    def _check(self) -> "CampaignAudience":
        if self.period == "custom" and not (self.start and self.end and self.start <= self.end):
            raise ValueError("Escolha as datas de início e fim do período.")
        return self


class CampaignMessage(_Model):
    text: Annotated[str, Field(min_length=1, max_length=4000)]
    media_ids: MediaList3
    spoiler: bool = False
    buttons: list[LinkButton] = Field(default_factory=list, max_length=3)


class CampaignPlan(_Model):
    name: Annotated[str, Field(min_length=1, max_length=60)]
    price: Money
    duration_days: Annotated[int, Field(ge=1, le=3650)] | None = 30
    delivery: Delivery | None = None  # None = the funnel's default delivery
    button_style: ButtonStyle = "success"


class CampaignOffer(_Model):
    plans: list[CampaignPlan] = Field(default_factory=list, max_length=10)
    order_bump: OrderBump | None = None
    redirect: LinkButton | None = None  # e.g. a free previews channel


class CampaignDefinition(_Model):
    audience: CampaignAudience = Field(default_factory=CampaignAudience)
    # Variants rotate between leads (lead 1 gets A, lead 2 gets B, ...).
    messages: list[CampaignMessage] = Field(min_length=1, max_length=3)
    offer: CampaignOffer = Field(default_factory=CampaignOffer)

    def media_ids(self) -> set[uuid.UUID]:
        found = {m for message in self.messages for m in message.media_ids}
        deliveries = [plan.delivery for plan in self.offer.plans]
        if self.offer.order_bump:
            found.update(self.offer.order_bump.media_ids)
            deliveries.append(self.offer.order_bump.delivery)
        for delivery in deliveries:
            if delivery:
                found.update(delivery.media_ids)
        return found


# ---------------------------------------------------------------- audience


def _period_bounds(audience: CampaignAudience, now: datetime) -> tuple[datetime | None, datetime | None]:
    today = now.astimezone(BRAZIL_TIME_ZONE).date()

    def at(day: date) -> datetime:
        return datetime.combine(day, datetime.min.time(), tzinfo=BRAZIL_TIME_ZONE)

    match audience.period:
        case "today":
            return at(today), None
        case "yesterday":
            return at(today - timedelta(days=1)), at(today)
        case "7d":
            return at(today - timedelta(days=6)), None
        case "30d":
            return at(today - timedelta(days=29)), None
        case "custom":
            return at(audience.start), at(audience.end + timedelta(days=1))
    return None, None


def audience_filter(workspace_id: uuid.UUID, flow_id: uuid.UUID, audience: CampaignAudience, now: datetime | None = None) -> list:
    """WHERE clauses selecting the funnel's leads in the audience (blocked ones included)."""
    paid = exists().where(TgOrder.lead_id == TgLead.id, TgOrder.status == "paid")
    any_order = exists().where(TgOrder.lead_id == TgLead.id)
    active = exists().where(TgSubscription.lead_id == TgLead.id, TgSubscription.status == "active")
    expired = exists().where(TgSubscription.lead_id == TgLead.id, TgSubscription.status == "expired")
    clauses = [TgLead.workspace_id == workspace_id, TgLead.flow_id == flow_id]
    clauses += {
        "all": [],
        "not_bought": [~paid],
        "bought": [paid],
        "pix_generated": [any_order, ~paid],
        "vip_expired": [expired, ~active],
        "group_members": [active],
    }[audience.target]
    start, end = _period_bounds(audience, now or engine.utcnow())
    if start is not None:
        clauses.append(TgLead.created_at >= start)
    if end is not None:
        clauses.append(TgLead.created_at < end)
    return clauses


async def estimate(db: AsyncSession, workspace_id: uuid.UUID, flow_id: uuid.UUID, audience: CampaignAudience) -> dict:
    clauses = audience_filter(workspace_id, flow_id, audience)
    total = await db.scalar(select(func.count(TgLead.id)).where(*clauses))
    blocked = await db.scalar(select(func.count(TgLead.id)).where(*clauses, TgLead.blocked_bot.is_(True)))
    return {"reach": int(total or 0) - int(blocked or 0), "blocked": int(blocked or 0)}


# ---------------------------------------------------------------- sending


def _offer_id(campaign_id: uuid.UUID, index: int) -> str:
    return f"rm{campaign_id.hex[:12]}-{index}"


def campaign_keyboard(campaign: TgCampaign, definition: CampaignDefinition, message: CampaignMessage) -> dict | None:
    rows = [
        [engine.button(f"{plan.name} · {engine.brl(plan.price)}", plan.button_style, callback_data=f"rmk:{campaign.id.hex}:{index}")]
        for index, plan in enumerate(definition.offer.plans)
    ]
    rows += [[engine.button(item.label, url=str(item.url))] for item in message.buttons]
    if definition.offer.redirect:
        rows.append([engine.button(definition.offer.redirect.label, url=str(definition.offer.redirect.url))])
    return {"inline_keyboard": rows} if rows else None


async def start_campaign(db: AsyncSession, campaign: TgCampaign, resume: bool = False) -> None:
    definition = CampaignDefinition.model_validate(campaign.definition)
    campaign.status = "sending"
    campaign.scheduled_at = None
    campaign.finished_at = None
    if resume and campaign.started_at is not None:
        return
    numbers = await estimate(db, campaign.workspace_id, campaign.flow_id, definition.audience)
    campaign.started_at = engine.utcnow()
    campaign.cursor_lead_id = None
    campaign.total = numbers["reach"]
    campaign.already_blocked = numbers["blocked"]
    campaign.sent = campaign.failed = campaign.blocked = 0
    campaign.runs += 1


async def run_campaign_batch(db: AsyncSession, campaign_id: uuid.UUID, deadline: float) -> None:
    campaign = await db.get(TgCampaign, campaign_id)
    if campaign is None or campaign.status != "sending":
        return
    try:
        definition = CampaignDefinition.model_validate(campaign.definition)
    except ValidationError:
        campaign.status = "paused"
        await db.commit()
        return
    query = (
        select(TgLead)
        .where(*audience_filter(campaign.workspace_id, campaign.flow_id, definition.audience), TgLead.blocked_bot.is_(False))
        .order_by(TgLead.id)
        .limit(BATCH)
    )
    if campaign.cursor_lead_id is not None:
        query = query.where(TgLead.id > campaign.cursor_lead_id)
    leads = list(await db.scalars(query))
    if not leads:
        campaign.status = "finished"
        campaign.finished_at = engine.utcnow()
        await db.commit()
        return
    bots: dict[uuid.UUID, tuple[TgBot, TelegramClient] | None] = {}
    for lead in leads:
        if time.monotonic() > deadline:
            break
        if lead.bot_id not in bots:
            bot = await db.get(TgBot, lead.bot_id)
            bots[lead.bot_id] = (bot, engine.telegram(bot)) if bot is not None and bot.is_active else None
        pair = bots[lead.bot_id]
        position = campaign.sent + campaign.failed + campaign.blocked
        try:
            if pair is None:
                raise LookupError("bot off")
            bot, tg = pair
            message = definition.messages[position % len(definition.messages)]
            await engine.send_media_then_text(
                db, tg, bot, lead.chat_id, message.media_ids, message.spoiler,
                engine.render(message.text, lead, bot=bot), campaign_keyboard(campaign, definition, message),
            )
            campaign.sent += 1
        except TelegramError as exc:
            if exc.blocked:
                lead.blocked_bot = True
                campaign.blocked += 1
            else:
                campaign.failed += 1
        except Exception:  # one bad lead never stops the campaign
            logger.exception("Remarketing send failed")
            campaign.failed += 1
        campaign.cursor_lead_id = lead.id
        await db.commit()


async def run_campaigns(db: AsyncSession, budget_seconds: float = TICK_BUDGET_SECONDS) -> None:
    """Worker tick: start the scheduled campaigns that are due, then send a batch of each."""
    now = engine.utcnow()
    for campaign in list(await db.scalars(
        select(TgCampaign).where(TgCampaign.status == "scheduled", TgCampaign.scheduled_at <= now)
    )):
        await start_campaign(db, campaign)
    await db.commit()
    deadline = time.monotonic() + budget_seconds
    for campaign_id in list(await db.scalars(select(TgCampaign.id).where(TgCampaign.status == "sending").order_by(TgCampaign.started_at))):
        if time.monotonic() > deadline:
            break
        await run_campaign_batch(db, campaign_id, deadline)


async def handle_campaign_tap(
    db: AsyncSession, tg: TelegramClient, bot: TgBot, lead: TgLead, flow: FlowDefinition, callback_id: str, data: str,
) -> uuid.UUID | None:
    """``rmk:<campaign>:<plan>`` buys a campaign plan; ``rmkb:y|n:<campaign>:<plan>`` answers its order bump."""
    gone = "Esta oferta não está mais disponível."
    parts = data.split(":")
    bump_answer = parts[1] if parts[0] == "rmkb" and len(parts) == 4 else None
    hex_id, raw_index = (parts[2], parts[3]) if bump_answer else ((parts[1], parts[2]) if len(parts) == 3 else ("", ""))
    try:
        campaign = await db.get(TgCampaign, uuid.UUID(hex=hex_id))
        index = int(raw_index)
        definition = CampaignDefinition.model_validate(campaign.definition) if campaign else None
    except (ValueError, ValidationError):
        campaign, definition, index = None, None, -1
    if campaign is None or definition is None or campaign.workspace_id != bot.workspace_id or not 0 <= index < len(definition.offer.plans):
        await tg.answer_callback(callback_id, gone)
        return None
    item = definition.offer.plans[index]
    plan = Plan(id=f"rm{index}", name=item.name, price=item.price, duration_days=item.duration_days, delivery=item.delivery)
    bump = definition.offer.order_bump
    if bump is not None and bump_answer is None:
        await tg.answer_callback(callback_id)
        await engine.send_bump_question(
            db, tg, bot, lead, plan, bump, (f"rmkb:y:{hex_id}:{index}", f"rmkb:n:{hex_id}:{index}"),
        )
        return None
    chosen = bump if bump_answer == "y" else None
    await tg.answer_callback(callback_id, "Gerando seu Pix…")
    offer_id = _offer_id(campaign.id, index) + ("+b" if chosen else "")
    await engine.create_order(db, tg, bot, lead, flow, plan, bump=chosen, kind="remarketing", offer_id=offer_id, retry=data)
    return lead.id


# ---------------------------------------------------------------- API


class CampaignIn(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=120)]
    flow_id: uuid.UUID
    definition: dict


class EstimateIn(BaseModel):
    flow_id: uuid.UUID
    audience: dict = Field(default_factory=dict)


class ScheduleIn(BaseModel):
    scheduled_at: datetime | None = None


async def _flow(db: AsyncSession, flow_id: uuid.UUID, access) -> TgFlow:
    flow = await db.get(TgFlow, flow_id)
    if flow is None or flow.workspace_id != access.workspace.id or (flow.hidden_by_admin and not admin_view()):
        raise HTTPException(status_code=404, detail="Funil não encontrado.")
    return flow


async def _campaign(db: AsyncSession, campaign_id: uuid.UUID, access) -> TgCampaign:
    campaign = await db.get(TgCampaign, campaign_id)
    if campaign is None or campaign.workspace_id != access.workspace.id:
        raise HTTPException(status_code=404, detail="Campanha não encontrada.")
    return campaign


def _error(exc: ValidationError) -> HTTPException:
    first = exc.errors()[0]
    where = ".".join(str(p) for p in first.get("loc", ()))
    message = str(first.get("msg", "")).removeprefix("Value error, ")
    return HTTPException(status_code=422, detail=f"{where}: {message}" if where else message)


async def _validate(db: AsyncSession, payload: CampaignIn, access) -> tuple[TgFlow, CampaignDefinition]:
    flow = await _flow(db, payload.flow_id, access)
    try:
        definition = CampaignDefinition.model_validate(payload.definition)
    except ValidationError as exc:
        raise _error(exc) from None
    needs_default = any(plan.delivery is None for plan in definition.offer.plans)
    if needs_default:
        try:
            has_default = FlowDefinition.model_validate(flow.definition).default_delivery is not None
        except ValidationError:
            has_default = False
        if not has_default:
            raise HTTPException(status_code=422, detail="Um plano usa a entrega padrão, mas o funil não tem entrega padrão.")
    media_ids = definition.media_ids()
    if media_ids:
        found = set(await db.scalars(select(TgMedia.id).where(TgMedia.id.in_(media_ids), TgMedia.workspace_id == access.workspace.id)))
        if found != media_ids:
            raise HTTPException(status_code=422, detail="Alguma mídia da campanha não existe mais. Envie de novo.")
    return flow, definition


async def _sales(db: AsyncSession, campaigns: list[TgCampaign]) -> dict[uuid.UUID, tuple[int, Decimal]]:
    out: dict[uuid.UUID, tuple[int, Decimal]] = {}
    for campaign in campaigns:
        row = (await db.execute(
            select(func.count(TgOrder.id), func.coalesce(func.sum(TgOrder.amount), 0)).where(
                TgOrder.workspace_id == campaign.workspace_id, TgOrder.kind == "remarketing", TgOrder.status == "paid",
                TgOrder.offer_id.like(f"rm{campaign.id.hex[:12]}-%"),
            )
        )).one()
        out[campaign.id] = (int(row[0] or 0), Decimal(row[1] or 0))
    return out


def _out(campaign: TgCampaign, flow_name: str, sales: tuple[int, Decimal]) -> dict:
    def iso(value: datetime | None) -> str | None:
        return engine.aware(value).isoformat() if value else None

    return {
        "id": str(campaign.id), "flow_id": str(campaign.flow_id), "flow_name": flow_name, "name": campaign.name,
        "status": campaign.status, "definition": campaign.definition,
        "scheduled_at": iso(campaign.scheduled_at), "started_at": iso(campaign.started_at), "finished_at": iso(campaign.finished_at),
        "total": campaign.total, "sent": campaign.sent, "failed": campaign.failed, "blocked": campaign.blocked,
        "already_blocked": campaign.already_blocked, "runs": campaign.runs,
        "sales": sales[0], "revenue": f"{sales[1]:.2f}",
        "created_at": iso(campaign.created_at),
    }


async def _one(db: AsyncSession, campaign: TgCampaign) -> dict:
    flow = await db.get(TgFlow, campaign.flow_id)
    return _out(campaign, flow.name if flow else "", (await _sales(db, [campaign]))[campaign.id])


@router.get("")
async def list_campaigns(access: OwnerAccess, db: DbSession, flow_id: uuid.UUID | None = None) -> dict:
    query = select(TgCampaign).where(TgCampaign.workspace_id == access.workspace.id).order_by(TgCampaign.created_at.desc())
    if flow_id is not None:
        query = query.where(TgCampaign.flow_id == flow_id)
    if not admin_view():
        query = query.where(TgCampaign.flow_id.not_in(select(TgFlow.id).where(TgFlow.hidden_by_admin.is_(True))))
    campaigns = list(await db.scalars(query))
    names = dict((await db.execute(select(TgFlow.id, TgFlow.name).where(TgFlow.workspace_id == access.workspace.id))).all())
    sales = await _sales(db, campaigns)
    return {"campaigns": [_out(c, names.get(c.flow_id, ""), sales[c.id]) for c in campaigns]}


@router.post("/estimate", dependencies=csrf)
async def estimate_reach(payload: EstimateIn, access: OwnerAccess, db: DbSession) -> dict:
    flow = await _flow(db, payload.flow_id, access)
    try:
        audience = CampaignAudience.model_validate(payload.audience)
    except ValidationError as exc:
        raise _error(exc) from None
    return await estimate(db, access.workspace.id, flow.id, audience)


@router.post("", status_code=201, dependencies=csrf)
async def create_campaign(payload: CampaignIn, access: OwnerAccess, db: DbSession) -> dict:
    flow, definition = await _validate(db, payload, access)
    campaign = TgCampaign(
        workspace_id=access.workspace.id, flow_id=flow.id, name=payload.name.strip(), definition=definition.model_dump(mode="json"),
    )
    db.add(campaign)
    await db.commit()
    await db.refresh(campaign)
    return await _one(db, campaign)


@router.get("/{campaign_id}")
async def get_campaign(campaign_id: uuid.UUID, access: OwnerAccess, db: DbSession) -> dict:
    return await _one(db, await _campaign(db, campaign_id, access))


@router.put("/{campaign_id}", dependencies=csrf)
async def update_campaign(campaign_id: uuid.UUID, payload: CampaignIn, access: OwnerAccess, db: DbSession) -> dict:
    campaign = await _campaign(db, campaign_id, access)
    flow, definition = await _validate(db, payload, access)
    campaign.name = payload.name.strip()
    campaign.flow_id = flow.id
    campaign.definition = definition.model_dump(mode="json")
    await db.commit()
    await db.refresh(campaign)
    return await _one(db, campaign)


@router.delete("/{campaign_id}", status_code=204, dependencies=csrf)
async def delete_campaign(campaign_id: uuid.UUID, access: OwnerAccess, db: DbSession) -> None:
    await db.delete(await _campaign(db, campaign_id, access))
    await db.commit()


@router.post("/{campaign_id}/send", dependencies=csrf)
async def send_campaign(campaign_id: uuid.UUID, access: OwnerAccess, db: DbSession, resume: bool = False) -> dict:
    """Start now (from the first lead) or, with ``resume``, continue a paused send."""
    campaign = await _campaign(db, campaign_id, access)
    if campaign.status == "sending":
        raise HTTPException(status_code=409, detail="A campanha já está sendo enviada.")
    await start_campaign(db, campaign, resume=resume and campaign.status == "paused")
    await db.commit()
    await db.refresh(campaign)
    return await _one(db, campaign)


@router.post("/{campaign_id}/schedule", dependencies=csrf)
async def schedule_campaign(campaign_id: uuid.UUID, payload: ScheduleIn, access: OwnerAccess, db: DbSession) -> dict:
    """Schedule the send; ``scheduled_at: null`` cancels the schedule."""
    campaign = await _campaign(db, campaign_id, access)
    if campaign.status == "sending":
        raise HTTPException(status_code=409, detail="Pause a campanha antes de agendar.")
    if payload.scheduled_at is None:
        campaign.status = "draft" if campaign.status == "scheduled" else campaign.status
        campaign.scheduled_at = None
    else:
        when = engine.aware(payload.scheduled_at)
        if when <= engine.utcnow():
            raise HTTPException(status_code=422, detail="Escolha um horário no futuro.")
        campaign.status, campaign.scheduled_at = "scheduled", when
    await db.commit()
    await db.refresh(campaign)
    return await _one(db, campaign)


@router.post("/{campaign_id}/pause", dependencies=csrf)
async def pause_campaign(campaign_id: uuid.UUID, access: OwnerAccess, db: DbSession) -> dict:
    campaign = await _campaign(db, campaign_id, access)
    if campaign.status == "sending":
        campaign.status = "paused"
        await db.commit()
        await db.refresh(campaign)
    return await _one(db, campaign)
