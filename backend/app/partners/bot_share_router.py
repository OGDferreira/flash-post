"""Bot partnership API.

Owner side (``/api/bot-partners/bots/...``): the owner of a bot invites a partner, sets the
split, pauses or removes them, reads the finance panel and logs payouts.

Partner side (``/api/bot-partners/shared/...``): the partner reads the shared bots, accepts
or declines, edits the bot's funnel and media, and reads Análises and the finance panel. The
partner only ever reaches the one bot's funnel(s) and the owner workspace's media, never the
rest of the owner's operation.
"""

import logging
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import PurePosixPath
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.analytics.periods import (
    AnalyticsPeriod,
    period_bounds,
    period_label,
    user_time_zone,
)
from app.auth.dependencies import (
    AuthenticatedUser,
    DbSession,
    OwnerAccess,
    require_csrf,
)
from app.bots import engine
from app.bots.router import (
    MEDIA_TYPES,
    _flow_out,
    _media_out,
    _validate_definition,
)
from app.core.security import PlatformRole
from app.core.time import utc_now
from app.models import (
    BotPartner,
    BotPartnerPayout,
    BotPartnerSale,
    TgBot,
    TgFlow,
    TgFlowFolderItem,
    TgGroup,
    TgLead,
    TgMedia,
    TgOrder,
    TgSubscription,
    User,
)
from app.partners import bot_share_service as svc

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/bot-partners", tags=["Bot partners"])
csrf = [Depends(require_csrf)]


def _is_super_admin(user: User) -> bool:
    return user.platform_role == PlatformRole.SUPER_ADMIN.value


# =====================================================================  owner side


class InvitePayload(BaseModel):
    identifier: Annotated[str, Field(min_length=1, max_length=320)]  # e-mail, @username or nickname
    partner_percent: Annotated[Decimal, Field(ge=0, le=100)]
    bot_fee: Annotated[Decimal | None, Field(default=None, ge=0)] = None  # Super Admin only
    access_level: Annotated[str, Field(pattern="^(operational|read_only)$")] = "operational"
    invite_expiry_days: Annotated[int, Field(default=7)] = 7


INVITE_EXPIRY_CHOICES = (1, 3, 7, 30)


def _expiry_days(days: int) -> int:
    return days if days in INVITE_EXPIRY_CHOICES else 7


class PartnershipUpdate(BaseModel):
    partner_percent: Annotated[Decimal | None, Field(default=None, ge=0, le=100)] = None
    bot_fee: Annotated[Decimal | None, Field(default=None, ge=0)] = None  # Super Admin only
    status: Annotated[str | None, Field(default=None)] = None  # ACTIVE | PAUSED | REVOKED
    access_level: Annotated[str | None, Field(default=None, pattern="^(operational|read_only)$")] = None
    # Per-offer-kind percent overrides, e.g. {"plan": 50, "upsell": 30}; null/absent clears.
    split_by_kind: Annotated[dict[str, Decimal | None] | None, Field(default=None)] = None


def _clean_split_by_kind(raw: dict[str, Decimal | None] | None) -> dict[str, float] | None:
    """Keep only known kinds with a 0–100 value; drop nulls. Empty → None (use general %)."""
    if not raw:
        return None
    out: dict[str, float] = {}
    for kind, value in raw.items():
        if kind not in svc.SPLIT_KINDS or value is None:
            continue
        v = Decimal(str(value))
        if v < 0 or v > 100:
            raise HTTPException(status_code=422, detail="Cada porcentagem por plano deve ficar entre 0 e 100.")
        out[kind] = float(svc.money(v))
    return out or None


class PayoutPayload(BaseModel):
    party: Annotated[str, Field(pattern="^(owner|partner)$")]
    amount: Annotated[Decimal, Field(gt=0)]
    note: Annotated[str | None, Field(default=None, max_length=500)] = None
    paid_at: date | None = None


class SaleStatusPayload(BaseModel):
    status: Annotated[str, Field(pattern="^(pending|paid|denied)$")]
    note: Annotated[str | None, Field(default=None, max_length=500)] = None


async def _owned_bot_or_404(db, owner_user_id: uuid.UUID, bot_id: uuid.UUID) -> TgBot:
    bot = await svc.owner_bot(db, owner_user_id, bot_id)
    if bot is None:
        raise HTTPException(status_code=404, detail="Bot não encontrado.")
    return bot


async def _partnership_for_owner(db, owner: User, partnership_id: uuid.UUID) -> BotPartner:
    part = await db.get(BotPartner, partnership_id)
    if part is None or part.owner_user_id != owner.id:
        raise HTTPException(status_code=404, detail="Parceria não encontrada.")
    return part


@router.get("/bots/{bot_id}")
async def bot_partners(bot_id: uuid.UUID, access: OwnerAccess, user: AuthenticatedUser, db: DbSession) -> dict:
    """The partners of a bot the owner manages, plus the default bot fee and whether the
    caller may zero it (Super Admin only)."""
    bot = await _owned_bot_or_404(db, access.workspace.owner_id, bot_id)
    parts = await svc.partnerships_of_bot(db, bot.id)
    owner_user = await db.get(User, access.workspace.owner_id)
    out = []
    for part in parts:
        partner = await db.get(User, part.partner_user_id)
        out.append(svc.partnership_out(part, owner_user, partner))
    active_percent = await svc.active_percent_sum(db, bot.id)
    return {
        "bot": {"id": str(bot.id), "name": bot.name, "username": bot.username},
        "partners": out,
        "default_bot_fee": float(await svc.default_bot_fee(db, owner_user)),
        "can_zero_fee": _is_super_admin(user),
        "has_active": any(p["status"] == "ACTIVE" for p in out),
        "active_percent": float(active_percent),
        "active_percent_remaining": float(max(Decimal("0"), Decimal("100") - active_percent)),
    }


@router.post("/bots/{bot_id}/invite", status_code=201, dependencies=csrf)
async def invite_partner(
    bot_id: uuid.UUID, payload: InvitePayload, access: OwnerAccess, user: AuthenticatedUser, db: DbSession
) -> dict:
    bot = await _owned_bot_or_404(db, access.workspace.owner_id, bot_id)
    owner_user = await db.get(User, access.workspace.owner_id)
    target = await svc.find_user_by_identifier(db, payload.identifier)
    if target is None:
        raise HTTPException(status_code=404, detail="Nenhum usuário da Flash com esse e-mail, @usuário ou apelido.")
    if target.id == owner_user.id:
        raise HTTPException(status_code=422, detail="Você não pode ser parceiro do seu próprio bot.")
    existing = await db.scalar(
        select(BotPartner).where(BotPartner.bot_id == bot.id, BotPartner.partner_user_id == target.id)
    )
    # An expired PENDING invite may be re-sent; an active/paused or still-valid PENDING one may not.
    if existing is not None and existing.status in ("PENDING", "ACTIVE", "PAUSED") and not svc.invite_expired(existing):
        raise HTTPException(status_code=409, detail="Esse usuário já é parceiro (ou foi convidado) deste bot.")

    bot_fee = await svc.default_bot_fee(db, owner_user)
    if payload.bot_fee is not None:
        if not _is_super_admin(user):
            raise HTTPException(status_code=403, detail="Só o super admin pode alterar a taxa do bot.")
        bot_fee = svc.money(payload.bot_fee)

    days = _expiry_days(payload.invite_expiry_days)
    expires_at = utc_now() + timedelta(days=days)
    if existing is not None:  # re-invite a previously declined/revoked/expired user
        existing.status = "PENDING"
        existing.partner_percent = svc.money(payload.partner_percent)
        existing.bot_fee = bot_fee
        existing.access_level = payload.access_level
        existing.invite_expiry_days = days
        existing.invite_expires_at = expires_at
        existing.invited_by_user_id = user.id
        existing.accepted_at = None
        part = existing
    else:
        part = BotPartner(
            bot_id=bot.id, owner_user_id=owner_user.id, partner_user_id=target.id,
            partner_percent=svc.money(payload.partner_percent), bot_fee=bot_fee,
            access_level=payload.access_level,
            invite_expiry_days=days, invite_expires_at=expires_at,
            status="PENDING", invited_by_user_id=user.id,
        )
        db.add(part)
    await db.flush()
    await svc.notify_partner_invite(db, part, owner_user, bot)
    await db.commit()
    await db.refresh(part)
    return svc.partnership_out(part, owner_user, target, bot)


@router.patch("/{partnership_id}", dependencies=csrf)
async def update_partnership(
    partnership_id: uuid.UUID, payload: PartnershipUpdate, access: OwnerAccess, user: AuthenticatedUser, db: DbSession
) -> dict:
    part = await _partnership_for_owner(db, await db.get(User, access.workspace.owner_id), partnership_id)
    # The cut this partner would take once the change is applied (new percent if given).
    new_percent = svc.money(payload.partner_percent) if payload.partner_percent is not None else part.partner_percent
    new_split = _clean_split_by_kind(payload.split_by_kind) if "split_by_kind" in payload.model_fields_set else part.split_by_kind
    # Whether this partner counts as active after the change.
    will_be_active = (payload.status == "ACTIVE") or (payload.status is None and part.status == "ACTIVE")
    if will_be_active:
        others = await svc.active_percent_sum(db, part.bot_id, exclude=part.id)
        if others + new_percent > Decimal("100"):
            raise HTTPException(
                status_code=409,
                detail=(
                    f"A soma das porcentagens dos parceiros ativos passaria de 100% "
                    f"(outros ativos: {others:.2f}% + este: {new_percent:.2f}%). "
                    f"Reduza alguma porcentagem ou pause outro parceiro."
                ),
            )
        # Each offer kind must also stay within 100% across active partners.
        kind_others = await svc.active_kind_percent_sums(db, part.bot_id, exclude=part.id)
        proposed = BotPartner(partner_percent=new_percent, split_by_kind=new_split)
        for kind in svc.SPLIT_KINDS:
            total = kind_others[kind] + svc.effective_percent(proposed, kind)
            if total > Decimal("100"):
                label = {"plan": "plano principal", "upsell": "upsell", "downsell": "downsell", "remarketing": "remarketing"}[kind]
                raise HTTPException(
                    status_code=409,
                    detail=f"A soma das porcentagens de '{label}' dos parceiros ativos passaria de 100% ({total:.2f}%).",
                )
    if payload.partner_percent is not None:
        part.partner_percent = new_percent
    if "split_by_kind" in payload.model_fields_set:
        part.split_by_kind = new_split
    if payload.bot_fee is not None:
        if not _is_super_admin(user):
            raise HTTPException(status_code=403, detail="Só o super admin pode alterar a taxa do bot.")
        part.bot_fee = svc.money(payload.bot_fee)
    if payload.access_level is not None:
        part.access_level = payload.access_level
    if payload.status is not None:
        if payload.status not in ("ACTIVE", "PAUSED", "REVOKED"):
            raise HTTPException(status_code=422, detail="Status inválido.")
        if payload.status == "ACTIVE":
            if part.status not in ("PAUSED", "PENDING", "ACTIVE"):
                raise HTTPException(status_code=409, detail="A parceria não pode ser ativada neste estado.")
            if part.accepted_at is None:
                raise HTTPException(status_code=409, detail="O parceiro ainda não aceitou o convite.")
        part.status = payload.status
    await db.commit()
    await db.refresh(part)
    partner = await db.get(User, part.partner_user_id)
    owner_user = await db.get(User, part.owner_user_id)
    return svc.partnership_out(part, owner_user, partner)


@router.delete("/{partnership_id}", status_code=204, dependencies=csrf)
async def remove_partnership(partnership_id: uuid.UUID, access: OwnerAccess, db: DbSession) -> None:
    part = await _partnership_for_owner(db, await db.get(User, access.workspace.owner_id), partnership_id)
    part.status = "REVOKED"
    await db.commit()


class ResendPayload(BaseModel):
    invite_expiry_days: Annotated[int | None, Field(default=None)] = None


@router.post("/{partnership_id}/resend", dependencies=csrf)
async def resend_invite(
    partnership_id: uuid.UUID, payload: ResendPayload, access: OwnerAccess, user: AuthenticatedUser, db: DbSession
) -> dict:
    """Re-send an invite (typically an expired one): reset it to PENDING with a fresh expiry."""
    owner_user = await db.get(User, access.workspace.owner_id)
    part = await _partnership_for_owner(db, owner_user, partnership_id)
    if part.status in ("ACTIVE", "PAUSED") and part.accepted_at is not None:
        raise HTTPException(status_code=409, detail="Este parceiro já aceitou; não há convite para reenviar.")
    days = _expiry_days(payload.invite_expiry_days if payload.invite_expiry_days is not None else part.invite_expiry_days)
    part.status = "PENDING"
    part.accepted_at = None
    part.invite_expiry_days = days
    part.invite_expires_at = utc_now() + timedelta(days=days)
    part.invited_by_user_id = user.id
    bot = await db.get(TgBot, part.bot_id)
    if bot is not None:
        await svc.notify_partner_invite(db, part, owner_user, bot)
    await db.commit()
    await db.refresh(part)
    partner = await db.get(User, part.partner_user_id)
    return svc.partnership_out(part, owner_user, partner, bot)


@router.get("/bots/{bot_id}/finance")
async def owner_finance(
    bot_id: uuid.UUID, access: OwnerAccess, user: AuthenticatedUser, db: DbSession,
    period: AnalyticsPeriod = "30d", start_date: date | None = None, end_date: date | None = None,
    partnership_id: uuid.UUID | None = None,
) -> dict:
    bot = await _owned_bot_or_404(db, access.workspace.owner_id, bot_id)
    if partnership_id is not None:
        part = await db.get(BotPartner, partnership_id)
        if part is None or part.bot_id != bot.id or part.owner_user_id != access.workspace.owner_id:
            raise HTTPException(status_code=404, detail="Parceria não encontrada.")
    else:
        part = await db.scalar(
            select(BotPartner).where(
                BotPartner.bot_id == bot.id, BotPartner.status.in_(("ACTIVE", "PAUSED"))
            ).order_by(BotPartner.status)  # ACTIVE sorts before PAUSED
        )
    if part is None:
        return {"has_partner": False}
    return await _finance_payload(db, part, access.workspace.id, user.id, period, start_date, end_date, as_owner=True)


@router.post("/{partnership_id}/payouts", status_code=201, dependencies=csrf)
async def add_payout(partnership_id: uuid.UUID, payload: PayoutPayload, access: OwnerAccess, user: AuthenticatedUser, db: DbSession) -> dict:
    part = await _partnership_for_owner(db, await db.get(User, access.workspace.owner_id), partnership_id)
    when = datetime.combine(payload.paid_at, datetime.min.time()).replace(tzinfo=utc_now().tzinfo) if payload.paid_at else utc_now()
    payout = BotPartnerPayout(
        partnership_id=part.id, party=payload.party, amount=svc.money(payload.amount),
        note=(payload.note or "").strip() or None, paid_at=when, created_by_user_id=user.id,
    )
    db.add(payout)
    await db.commit()
    await db.refresh(payout)
    return {
        "id": str(payout.id), "party": payout.party, "amount": float(payout.amount),
        "note": payout.note, "paid_at": payout.paid_at.isoformat(),
    }


@router.patch("/sales/{sale_id}/status", dependencies=csrf)
async def set_commission_status(
    sale_id: uuid.UUID, payload: SaleStatusPayload, access: OwnerAccess, user: AuthenticatedUser, db: DbSession
) -> dict:
    """The owner marks one recorded commission as paid / denied / pending."""
    owner_id = access.workspace.owner_id
    sale = await db.get(BotPartnerSale, sale_id)
    if sale is None or sale.owner_user_id != owner_id:
        raise HTTPException(status_code=404, detail="Comissão não encontrada.")
    prev = sale.payout_status
    await svc.set_sale_status(db, sale, payload.status, by_user_id=user.id, note=payload.note)
    if payload.status != prev and payload.status in ("paid", "denied"):
        label = "paga" if payload.status == "paid" else "negada"
        await svc.notify_user(
            db,
            sale.partner_user_id,
            "bot_partner_commission",
            f"Comissão {label}",
            f"Uma comissão de {svc.money(sale.partner_amount)} foi marcada como {label}.",
            url="/bot/parceiros",
        )
    await db.commit()
    await db.refresh(sale)
    return {
        "id": str(sale.id),
        "payout_status": sale.payout_status,
        "status_note": sale.status_note,
        "status_changed_at": sale.status_changed_at.isoformat() if sale.status_changed_at else None,
    }


# =====================================================================  partner side


async def _access_or_404(db, user: User, bot_id: uuid.UUID, *, require_active: bool = True) -> svc.PartnerAccess:
    access = await svc.partner_access(db, user.id, bot_id, require_active=require_active)
    if access is None:
        raise HTTPException(status_code=404, detail="Bot compartilhado não encontrado.")
    return access


def _require_operational(access: svc.PartnerAccess) -> None:
    """Editing the funnel/media is only for operational partners, not read-only ones."""
    if access.partnership.access_level != "operational":
        raise HTTPException(
            status_code=403,
            detail="Seu acesso a este bot é somente leitura. Peça ao dono para liberar a edição.",
        )


@router.get("/shared")
async def my_shared_bots(user: AuthenticatedUser, db: DbSession) -> dict:
    parts = await svc.shared_with(db, user.id)
    out = []
    for part in parts:
        bot = await db.get(TgBot, part.bot_id)
        if bot is None:
            continue
        owner = await db.get(User, part.owner_user_id)
        out.append(svc.partnership_out(part, owner, user, bot))
    return {"shared": out}


@router.post("/{partnership_id}/accept", dependencies=csrf)
async def accept_invite(partnership_id: uuid.UUID, user: AuthenticatedUser, db: DbSession) -> dict:
    part = await db.get(BotPartner, partnership_id)
    if part is None or part.partner_user_id != user.id:
        raise HTTPException(status_code=404, detail="Convite não encontrado.")
    if part.status not in ("PENDING", "PAUSED", "ACTIVE"):
        raise HTTPException(status_code=409, detail="Este convite não está mais disponível.")
    if svc.invite_expired(part):
        raise HTTPException(status_code=409, detail="Este convite expirou. Peça ao dono para reenviar.")
    if part.accepted_at is None:
        part.accepted_at = utc_now()
    # Activate on accept only if the active partners' percentages still fit within 100%;
    # otherwise the partnership waits PAUSED until the owner frees up room.
    if part.status == "PENDING":
        others = await svc.active_percent_sum(db, part.bot_id, exclude=part.id)
        part.status = "ACTIVE" if others + part.partner_percent <= Decimal("100") else "PAUSED"
    bot = await db.get(TgBot, part.bot_id)
    owner = await db.get(User, part.owner_user_id)
    if bot is not None and owner is not None:
        await svc.notify_owner_accepted(db, part, user, bot)
    await db.commit()
    await db.refresh(part)
    return svc.partnership_out(part, owner, user, bot)


@router.post("/{partnership_id}/decline", dependencies=csrf)
async def decline_invite(partnership_id: uuid.UUID, user: AuthenticatedUser, db: DbSession) -> dict:
    part = await db.get(BotPartner, partnership_id)
    if part is None or part.partner_user_id != user.id:
        raise HTTPException(status_code=404, detail="Convite não encontrado.")
    part.status = "DECLINED"
    await db.commit()
    return {"ok": True}


def _bot_flow_ids(bot: TgBot) -> set[uuid.UUID]:
    return {bot.flow_id} if bot.flow_id else set()


async def _bot_flows(db, bot: TgBot) -> list[TgFlow]:
    """Every funnel this bot runs: its single flow, or each funnel in its folder."""
    ids: set[uuid.UUID] = set(_bot_flow_ids(bot))
    if bot.folder_id:
        ids |= set(await db.scalars(select(TgFlowFolderItem.flow_id).where(TgFlowFolderItem.folder_id == bot.folder_id)))
    if not ids:
        return []
    return list(await db.scalars(select(TgFlow).where(TgFlow.id.in_(ids), TgFlow.workspace_id == bot.workspace_id)))


async def _partner_flow_or_404(db, bot: TgBot, flow_id: uuid.UUID) -> TgFlow:
    flows = {f.id: f for f in await _bot_flows(db, bot)}
    flow = flows.get(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Esse funil não pertence a este bot.")
    return flow


@router.get("/shared/{bot_id}")
async def shared_bot_detail(bot_id: uuid.UUID, user: AuthenticatedUser, db: DbSession) -> dict:
    access = await _access_or_404(db, user, bot_id, require_active=False)
    bot, part = access.bot, access.partnership
    owner = await db.get(User, part.owner_user_id)
    flows = await _bot_flows(db, bot)
    return {
        **svc.partnership_out(part, owner, user, bot),
        "can_edit": part.status == "ACTIVE" and part.access_level == "operational",
        "notify_webhook_url": part.notify_webhook_url,
        "flows": [{"id": str(f.id), "name": f.name} for f in flows],
    }


class NotifyWebhookPayload(BaseModel):
    notify_webhook_url: Annotated[str | None, Field(default=None, max_length=500)] = None


@router.patch("/shared/{bot_id}/notify", dependencies=csrf)
async def set_partner_webhook(
    bot_id: uuid.UUID, payload: NotifyWebhookPayload, user: AuthenticatedUser, db: DbSession
) -> dict:
    """The partner sets (or clears) the webhook that receives a sale ping for this bot."""
    access = await _access_or_404(db, user, bot_id, require_active=False)
    url = (payload.notify_webhook_url or "").strip() or None
    if url is not None and not (url.startswith("https://") or url.startswith("http://")):
        raise HTTPException(status_code=422, detail="O webhook deve ser uma URL http(s) válida.")
    access.partnership.notify_webhook_url = url
    await db.commit()
    return {"notify_webhook_url": url}


@router.get("/shared/{bot_id}/flows/{flow_id}")
async def shared_get_flow(bot_id: uuid.UUID, flow_id: uuid.UUID, user: AuthenticatedUser, db: DbSession) -> dict:
    access = await _access_or_404(db, user, bot_id, require_active=False)
    flow = await _partner_flow_or_404(db, access.bot, flow_id)
    return _flow_out(flow)


@router.get("/shared/{bot_id}/flows/{flow_id}/summary")
async def shared_flow_summary(bot_id: uuid.UUID, flow_id: uuid.UUID, user: AuthenticatedUser, db: DbSession) -> dict:
    access = await _access_or_404(db, user, bot_id, require_active=False)
    flow = await _partner_flow_or_404(db, access.bot, flow_id)
    leads = await db.scalar(select(func.count(TgLead.id)).where(TgLead.flow_id == flow.id))
    vips = await db.scalar(
        select(func.count(func.distinct(TgSubscription.lead_id)))
        .join(TgLead, TgLead.id == TgSubscription.lead_id)
        .where(TgLead.flow_id == flow.id, TgSubscription.status == "active")
    )
    revenue = await db.scalar(
        select(func.coalesce(func.sum(TgOrder.amount), 0)).where(TgOrder.flow_id == flow.id, TgOrder.status == "paid")
    )
    return {"leads": int(leads or 0), "vips": int(vips or 0), "revenue": f"{Decimal(revenue or 0):.2f}"}


class SharedFlowSave(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=120)]
    definition: dict[str, Any]


@router.put("/shared/{bot_id}/flows/{flow_id}", dependencies=csrf)
async def shared_save_flow(bot_id: uuid.UUID, flow_id: uuid.UUID, payload: SharedFlowSave, user: AuthenticatedUser, db: DbSession) -> dict:
    access = await _access_or_404(db, user, bot_id)  # editing requires an ACTIVE partnership
    _require_operational(access)
    flow = await _partner_flow_or_404(db, access.bot, flow_id)
    definition = _validate_definition(payload.definition)
    media_ids = definition.media_ids()
    if media_ids:
        found = set(await db.scalars(
            select(TgMedia.id).where(TgMedia.id.in_(media_ids), TgMedia.workspace_id == access.bot.workspace_id)
        ))
        if found != media_ids:
            raise HTTPException(status_code=422, detail="Alguma mídia do fluxo não existe mais. Envie de novo.")
    flow.name = payload.name.strip()
    flow.definition = definition.model_dump(mode="json")
    flow.version += 1
    await db.commit()
    engine.invalidate_flow(flow.id)
    await db.refresh(flow)
    return _flow_out(flow)


@router.get("/shared/{bot_id}/media/list")
async def shared_media_list(bot_id: uuid.UUID, user: AuthenticatedUser, db: DbSession) -> dict:
    access = await _access_or_404(db, user, bot_id, require_active=False)
    rows = await db.scalars(
        select(TgMedia).where(TgMedia.workspace_id == access.bot.workspace_id, TgMedia.locked.is_(False)).order_by(TgMedia.created_at.desc())
    )
    return {"media": [_media_out(m) for m in rows]}


@router.get("/shared/{bot_id}/media/{media_id}/preview")
async def shared_media_preview(bot_id: uuid.UUID, media_id: uuid.UUID, user: AuthenticatedUser, db: DbSession) -> dict:
    from app.instagram.storage import SupabaseStorage

    access = await _access_or_404(db, user, bot_id, require_active=False)
    media = await db.get(TgMedia, media_id)
    if media is None or media.workspace_id != access.bot.workspace_id or media.locked:
        raise HTTPException(status_code=404, detail="Mídia não encontrada.")
    try:
        url = await SupabaseStorage.from_settings().create_signed_url(media.storage_path)
    except Exception:
        raise HTTPException(status_code=502, detail="Prévia indisponível.") from None
    return {"url": url}


@router.post("/shared/{bot_id}/media", status_code=201, dependencies=csrf)
async def shared_media_upload(
    bot_id: uuid.UUID, request: Request, user: AuthenticatedUser, db: DbSession,
    filename: str = Query(min_length=1, max_length=255),
) -> dict:
    from app.instagram.storage import SupabaseStorage, SupabaseStorageError

    access = await _access_or_404(db, user, bot_id)  # uploading requires an ACTIVE partnership
    _require_operational(access)
    workspace_id = access.bot.workspace_id
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type in ("video/quicktime", "video/x-m4v"):
        content_type = "video/mp4"
        filename = PurePosixPath(filename.replace("\\", "/")).stem + ".mp4"
    kind_limit = MEDIA_TYPES.get(content_type)
    if kind_limit is None:
        raise HTTPException(status_code=415, detail="Envie JPG, PNG, WEBP, MP4, MOV, OGG, MP3 ou M4A.")
    kind, limit = kind_limit
    chunks, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > limit:
            raise HTTPException(status_code=413, detail=f"Arquivo maior que {limit // (1024 * 1024)} MB.")
        chunks.append(chunk)
    if not size:
        raise HTTPException(status_code=400, detail="Arquivo vazio.")
    content = b"".join(chunks)
    signatures = {
        "image/jpeg": content.startswith(b"\xff\xd8\xff"),
        "image/png": content.startswith(b"\x89PNG"),
        "image/webp": content[:4] == b"RIFF" and content[8:12] == b"WEBP",
        "video/mp4": content[4:8] == b"ftyp",
        "audio/mp4": content[4:8] == b"ftyp",
        "audio/ogg": content.startswith(b"OggS"),
        "audio/mpeg": content.startswith(b"ID3") or content[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"),
    }
    if not signatures[content_type]:
        raise HTTPException(status_code=415, detail="O conteúdo do arquivo não corresponde ao tipo.")
    safe = PurePosixPath(filename.replace("\\", "/")).name.strip()[:200] or "arquivo"
    media_id = uuid.uuid4()
    path = f"{workspace_id}/bots/{media_id}/{SupabaseStorage.safe_object_name(safe)}"
    try:
        await SupabaseStorage.from_settings().upload(path, content, content_type)
    except (RuntimeError, SupabaseStorageError, httpx.HTTPError) as exc:
        logger.error("Partner bot media upload failed (%s).", type(exc).__name__)
        raise HTTPException(status_code=502, detail="Não foi possível salvar o arquivo.") from None
    media = TgMedia(
        id=media_id, workspace_id=workspace_id, kind=kind, file_name=safe,
        content_type=content_type, size_bytes=size, storage_path=path, file_ids={},
    )
    db.add(media)
    await db.commit()
    return _media_out(media)


@router.get("/shared/{bot_id}/groups/list")
async def shared_groups(bot_id: uuid.UUID, user: AuthenticatedUser, db: DbSession) -> dict:
    access = await _access_or_404(db, user, bot_id, require_active=False)
    rows = await db.scalars(
        select(TgGroup).where(TgGroup.workspace_id == access.bot.workspace_id).order_by(TgGroup.title)
    )
    return {"groups": [{"id": str(g.id), "chat_id": g.chat_id, "title": g.title, "can_invite": g.can_invite} for g in rows]}


@router.get("/shared/{bot_id}/analytics/full")
async def shared_analytics(
    bot_id: uuid.UUID, user: AuthenticatedUser, db: DbSession, period: AnalyticsPeriod = "today",
    start_date: date | None = None, end_date: date | None = None,
    flow_id: uuid.UUID | None = None, plan: str | None = Query(default=None, max_length=120),
) -> dict:
    from app.bots.analytics_full import full_analytics

    access = await _access_or_404(db, user, bot_id, require_active=False)
    zone = await user_time_zone(db, access.bot.workspace_id, user.id)
    start, end = period_bounds(period, start_date, end_date, utc_now(), zone)
    if start is None or end is None:
        raise HTTPException(status_code=422, detail="Escolha um período limitado.")
    data = await full_analytics(
        db, access.bot.workspace_id, start, end, zone, bot_id=access.bot.id, flow_id=flow_id,
        plan=(plan or "").strip() or None, hide=True,
    )
    data["period_label"] = period_label(start, end, zone)
    return data


@router.get("/shared/{bot_id}/finance")
async def partner_finance(
    bot_id: uuid.UUID, user: AuthenticatedUser, db: DbSession, period: AnalyticsPeriod = "30d",
    start_date: date | None = None, end_date: date | None = None,
) -> dict:
    access = await _access_or_404(db, user, bot_id, require_active=False)
    return await _finance_payload(
        db, access.partnership, access.bot.workspace_id, user.id, period, start_date, end_date, as_owner=False
    )


async def _finance_payload(
    db, part: BotPartner, workspace_id: uuid.UUID, user_id: uuid.UUID, period: AnalyticsPeriod,
    start_date: date | None, end_date: date | None, *, as_owner: bool,
) -> dict:
    zone = await user_time_zone(db, workspace_id, user_id)
    start, end = period_bounds(period, start_date, end_date, utc_now(), zone)
    summary = await svc.finance_summary(db, part, start, end)
    partner = await db.get(User, part.partner_user_id)
    owner = await db.get(User, part.owner_user_id)
    summary["has_partner"] = True
    summary["as_owner"] = as_owner
    summary["partnership_id"] = str(part.id)
    summary["status"] = part.status
    summary["partner"] = svc.user_brief(partner)
    summary["owner"] = svc.user_brief(owner)
    summary["period_label"] = period_label(start, end, zone) if start and end else "Todo o período"
    return summary
