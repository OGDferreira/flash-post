"""Partner (sócio) panel, commission acceptance, shared templates and the chief's
read-only view of each partner's operation.

Permissions are enforced here, never only in the UI:
* a partner only sees their own operation and the templates their chief shared;
* a chief only sees direct partners, and never a bot token or account credential;
* the commission comes from the database, never from the request.
"""

import uuid
from datetime import date
from typing import Literal
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update

from app.analytics.periods import AnalyticsPeriod, period_bounds, period_label
from app.auth.dependencies import AuthenticatedUser, DbSession, OwnerAccess, require_csrf
from app.core.time import utc_now
from app.models import (
    Affiliation,
    AppNotification,
    InstagramLoop,
    InstagramLoopAccount,
    InstagramLoopMedia,
    InstagramPublicationJob,
    TgBot,
    TgFlow,
    TgFlowShare,
    TgLead,
    TgOrder,
    User,
    Workspace,
)
from app.bots.hidden import not_hidden_bot
from app.partners import service

router = APIRouter(prefix="/api/partners", tags=["Partners"])

SPLIT_BASIS = (
    "O split é feito pelo gateway na cobrança: do valor líquido após a taxa, o percentual definido "
    "pelo sócio que convida vai para ele e o restante fica para o sócio dono da operação."
)


class AcceptRequest(BaseModel):
    percent: Decimal = Field(ge=0, le=100, decimal_places=2)


class ShareRequest(BaseModel):
    shared: bool
    # None = every partner; otherwise only these partners (user ids).
    partner_ids: list[uuid.UUID] | None = Field(default=None, max_length=500)


class ShareFlowRequest(ShareRequest):
    # Optional loop that goes out together with the funnel, so the partner gets everything ready.
    loop_id: uuid.UUID | None = None


def _f(value: Decimal | None) -> float:
    return float(value or 0)


def _pct(value: Decimal) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".").replace(".", ",") + "%"


async def _sales(db, workspace_id: uuid.UUID, start, end, *, chief_user_id: uuid.UUID | None = None) -> dict:
    """Paid Falcon Bot sales of a workspace with fee, commission and partner net."""
    where = [TgOrder.workspace_id == workspace_id, TgOrder.status == "paid", TgOrder.paid_at >= start, TgOrder.paid_at < end,
             not_hidden_bot(TgOrder.bot_id)]
    if chief_user_id is not None:
        where.append(TgOrder.split_chief_user_id == chief_user_id)
    row = (
        await db.execute(
            select(
                func.count(TgOrder.id),
                func.coalesce(func.sum(TgOrder.amount), 0),
                func.coalesce(func.sum(TgOrder.gateway_fee), 0),
                func.coalesce(func.sum(TgOrder.split_amount), 0),
                func.coalesce(func.sum(func.coalesce(TgOrder.partner_net, TgOrder.net_amount)), 0),
            ).where(*where)
        )
    ).one()
    return {"sales": int(row[0]), "gross": _f(row[1]), "fees": _f(row[2]), "commission": _f(row[3]), "net": _f(row[4])}


def _order_out(order: TgOrder) -> dict:
    return {
        "id": str(order.id), "offer_name": order.offer_name, "paid_at": order.paid_at.isoformat() if order.paid_at else None,
        "gross": _f(order.amount), "fee": _f(order.gateway_fee), "percent": _f(order.split_percent) if order.split_percent is not None else None,
        "commission": _f(order.split_amount), "net": _f(order.partner_net if order.partner_net is not None else order.net_amount),
    }


async def _recent_orders(db, workspace_id: uuid.UUID, start, end, limit: int = 50) -> list[dict]:
    rows = await db.scalars(
        select(TgOrder)
        .where(TgOrder.workspace_id == workspace_id, TgOrder.status == "paid", TgOrder.paid_at >= start, TgOrder.paid_at < end,
               not_hidden_bot(TgOrder.bot_id))
        .order_by(TgOrder.paid_at.desc())
        .limit(limit)
    )
    return [_order_out(o) for o in rows]


# ------------------------------------------------------------------ partner


@router.get("/me")
async def my_partnership(
    user: AuthenticatedUser, db: DbSession, period: AnalyticsPeriod = "30d",
    start_date: date | None = None, end_date: date | None = None,
) -> dict:
    start, end = period_bounds(period, start_date, end_date, utc_now())
    role = await service.role_of(db, user)
    link = await service.partner_link(db, user.id)
    workspace = await service.owner_workspace(db, user.id)
    chief = await db.get(User, link.chief_user_id) if link else None
    out: dict = {
        "role": role,
        "period_label": period_label(start, end),
        "basis": SPLIT_BASIS,
        "shop_ref": service.shop_ref(workspace.id) if workspace and user.platform_role != "SUPER_ADMIN" else None,
        "partnership": None,
        "totals": await _sales(db, workspace.id, start, end) if workspace else None,
        "sales": await _recent_orders(db, workspace.id, start, end) if workspace else [],
    }
    if link and chief:
        out["partnership"] = {
            "chief_name": chief.full_name, "chief_nickname": chief.nickname,
            "proposed_percent": _f(link.participation_percent),
            "accepted_percent": _f(link.participation_percent),
            "accepted_at": link.accepted_at.isoformat() if link.accepted_at else None,
            "pending_acceptance": service.pending_acceptance(link),
            "since": link.created_at.isoformat(),
        }
    return out


@router.post("/me/accept", dependencies=[Depends(require_csrf)])
async def accept_commission(payload: AcceptRequest, user: AuthenticatedUser, db: DbSession) -> dict:
    """Legacy endpoint kept for existing clients; the chief-set percentage is already active."""
    link = await service.partner_link(db, user.id)
    if link is None:
        raise HTTPException(status_code=404, detail="Você não tem uma sociedade ativa.")
    if payload.percent != link.participation_percent:
        raise HTTPException(status_code=409, detail="O percentual foi atualizado pelo sócio que convidou.")
    return {"accepted_percent": _f(link.participation_percent), "accepted_at": None}


async def _partner_context(db, user: User, access) -> tuple[Affiliation, Workspace]:
    link = await service.partner_link(db, user.id)
    if link is None:
        raise HTTPException(status_code=404, detail="Modelos compartilhados são só para sócios.")
    if not service.accepted(link):
        raise HTTPException(status_code=403, detail="Aceite a comissão da sociedade antes de usar os modelos.")
    if access.workspace.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Use os modelos na sua própria operação.")
    chief_workspace = await service.owner_workspace(db, link.chief_user_id)
    if chief_workspace is None:
        raise HTTPException(status_code=404, detail="Operação do chefe não encontrada.")
    return link, chief_workspace


@router.get("/shared")
async def shared_templates(access: OwnerAccess, user: AuthenticatedUser, db: DbSession) -> dict:
    link = await service.partner_link(db, user.id)
    chief_workspace = await service.owner_workspace(db, link.chief_user_id) if link else None
    if chief_workspace is None:
        return {"available": False, "accepted": False, "loops": [], "flows": []}
    loops = [
        loop
        for loop in await db.scalars(
            select(InstagramLoop)
            .where(InstagramLoop.workspace_id == chief_workspace.id, InstagramLoop.shared.is_(True))
            .order_by(InstagramLoop.name)
        )
        if service.shares_with(loop, user.id)
    ]
    flows = [
        flow
        for flow in await db.scalars(
            select(TgFlow).where(TgFlow.workspace_id == chief_workspace.id, TgFlow.shared.is_(True)).order_by(TgFlow.name)
        )
        if await service.flow_offered_to(db, flow, user.id)
    ]
    rules = {
        rule.flow_id: rule
        for rule in await db.scalars(
            select(TgFlowShare).where(
                TgFlowShare.partner_user_id == user.id, TgFlowShare.flow_id.in_([flow.id for flow in flows] or [uuid.uuid4()])
            )
        )
    }
    default_percent = min(link.participation_percent, service.MAX_COMMISSION)
    chief_ws_gateway = chief_workspace.payment_gateway or "smokepay"
    # The partner's area of shared loops: linked copies are created/refreshed here too
    # (the periodic job does the same for partners who never open the app).
    linked = await service.sync_partner_loops(db, link) if access.workspace.owner_id == user.id else []
    await db.commit()
    used_loops = set(
        await db.scalars(
            select(InstagramLoop.template_loop_id).where(
                InstagramLoop.workspace_id == access.workspace.id, InstagramLoop.template_loop_id.is_not(None)
            )
        )
    )
    used_flows = set(
        await db.scalars(select(TgBot.flow_id).where(TgBot.workspace_id == access.workspace.id, TgBot.flow_id.is_not(None)))
    )
    linked_ids = {copy.template_loop_id for copy in linked}
    loop_names = {loop.id: loop.name for loop in loops}
    media_counts = dict(
        (
            await db.execute(
                select(InstagramLoopMedia.loop_id, func.count(InstagramLoopMedia.media_id))
                .where(InstagramLoopMedia.loop_id.in_([loop.id for loop in loops] or [uuid.uuid4()]))
                .group_by(InstagramLoopMedia.loop_id)
            )
        ).all()
    )
    return {
        "available": True,
        "accepted": service.accepted(link),
        "loops": [
            {
                "id": str(loop.id), "name": loop.name, "post_type": loop.post_type,
                "interval_min_minutes": loop.interval_min_minutes, "interval_max_minutes": loop.interval_max_minutes,
                "daily_limit_per_account": loop.daily_limit_per_account, "media_count": media_counts.get(loop.id, 0),
                "in_use": loop.id in used_loops or loop.id in linked_ids,
            }
            for loop in loops
        ],
        # Only the name and the paired loop: the funnel's content never leaves the chief.
        "flows": [
            {
                "id": str(flow.id), "name": flow.name, "in_use": flow.id in used_flows,
                "loop_id": str(flow.shared_loop_id) if flow.shared_loop_id in loop_names else None,
                "loop_name": loop_names.get(flow.shared_loop_id),
                "loop_in_use": flow.shared_loop_id in used_loops or flow.shared_loop_id in linked_ids,
                # The owner's rules, read-only for the seller (no ShopID of the owner, ever).
                "rules": _seller_rules(rules.get(flow.id), flow, default_percent, chief_ws_gateway),
            }
            # the paired loop only counts when it is shared with this partner too
            for flow in flows
        ],
    }


def _seller_rules(rule: TgFlowShare | None, flow: TgFlow, default_percent: Decimal, default_gateway: str) -> dict:
    if rule is not None:
        return {
            "set_by_owner": True, "gateway": rule.gateway, "seller_percent": _f(rule.seller_percent),
            "owner_percent": _f(rule.owner_percent), "seller_shop_id": service.mask_shop_id(rule.seller_shop_id),
            "basis": SHARE_BASIS,
        }
    return {
        "set_by_owner": False, "gateway": flow.payment_gateway or default_gateway,
        "seller_percent": _f(HUNDRED - default_percent), "owner_percent": _f(default_percent),
        "seller_shop_id": None, "basis": SHARE_BASIS,
    }


@router.post("/shared/loops/{loop_id}/use", status_code=201, dependencies=[Depends(require_csrf)])
async def use_shared_loop(loop_id: uuid.UUID, access: OwnerAccess, user: AuthenticatedUser, db: DbSession) -> dict:
    _link, chief_workspace = await _partner_context(db, user, access)
    source = await db.scalar(
        select(InstagramLoop).where(
            InstagramLoop.id == loop_id, InstagramLoop.workspace_id == chief_workspace.id, InstagramLoop.shared.is_(True)
        )
    )
    if source is None or not service.shares_with(source, user.id):
        raise HTTPException(status_code=404, detail="Loop compartilhado não encontrado.")
    copy = await service.ensure_linked_loop(db, source, access.workspace.id)
    await db.commit()
    return {"id": str(copy.id), "name": copy.name}


@router.post("/shared/flows/{flow_id}/use", status_code=201, dependencies=[Depends(require_csrf)])
async def use_shared_flow(flow_id: uuid.UUID, access: OwnerAccess, user: AuthenticatedUser, db: DbSession) -> dict:
    _link, chief_workspace = await _partner_context(db, user, access)
    source = await db.scalar(
        select(TgFlow).where(TgFlow.id == flow_id, TgFlow.workspace_id == chief_workspace.id, TgFlow.shared.is_(True))
    )
    if source is None or not await service.flow_offered_to(db, source, user.id):
        raise HTTPException(status_code=404, detail="Funil compartilhado não encontrado.")
    # The funnel itself is never copied: the partner's bot runs it as is. The paired
    # loop (when there is one) arrives as a linked copy with zero accounts.
    loop_out = None
    if source.shared_loop_id:
        template = await db.get(InstagramLoop, source.shared_loop_id)
        if template is not None and template.workspace_id == chief_workspace.id and service.shares_with(template, user.id):
            copy = await service.ensure_linked_loop(db, template, access.workspace.id)
            loop_out = {"id": str(copy.id), "name": copy.name}
    await db.commit()
    return {"id": str(source.id), "name": source.name, "loop": loop_out}


# ------------------------------------------------------------------ chief


async def _owned_workspace(access, user: User) -> None:
    if access.workspace.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Somente o dono da operação compartilha modelos.")


async def _targets(db, user: User, partner_ids: list[uuid.UUID] | None) -> list[str] | None:
    """None = every partner; a list must name the chief's own active partners."""
    if partner_ids is None:
        return None
    targets = sorted({str(value) for value in partner_ids})
    if not targets:
        raise HTTPException(status_code=422, detail="Escolha pelo menos um sócio ou compartilhe com todos.")
    if not set(targets) <= await service.partner_ids(db, user.id):
        raise HTTPException(status_code=422, detail="Escolha apenas os seus sócios.")
    return targets


def _share_out(item: InstagramLoop | TgFlow) -> list[str] | None:
    return [str(target) for target in item.shared_with] if item.shared and item.shared_with is not None else None


@router.get("/mine")
async def my_partners(access: OwnerAccess, user: AuthenticatedUser, db: DbSession) -> dict:
    """The chief's active partners, to pick who receives a funnel or a loop."""
    await _owned_workspace(access, user)
    rows = await db.execute(
        select(User.id, User.full_name, User.nickname)
        .join(Affiliation, Affiliation.affiliate_user_id == User.id)
        .where(Affiliation.chief_user_id == user.id, Affiliation.status == "ACTIVE")
        .order_by(User.full_name)
    )
    return {"partners": [{"id": str(pid), "name": name or nickname, "nickname": nickname} for pid, name, nickname in rows]}


@router.post("/loops/{loop_id}/share", dependencies=[Depends(require_csrf)])
async def share_loop(loop_id: uuid.UUID, payload: ShareRequest, access: OwnerAccess, user: AuthenticatedUser, db: DbSession) -> dict:
    await _owned_workspace(access, user)
    loop = await db.scalar(select(InstagramLoop).where(InstagramLoop.id == loop_id, InstagramLoop.workspace_id == access.workspace.id))
    if loop is None or loop.linked:
        raise HTTPException(status_code=404, detail="Loop não encontrado.")
    loop.shared_with = await _targets(db, user, payload.partner_ids) if payload.shared else None
    loop.shared = payload.shared
    await db.commit()
    return {"id": str(loop.id), "shared": loop.shared, "shared_with": _share_out(loop)}


class LoopCopyOverrides(BaseModel):
    """What the chief changes on one partner's copy; the main loop stays as it is."""

    interval_min_minutes: int = Field(ge=1, le=1440)
    interval_max_minutes: int = Field(ge=1, le=1440)
    daily_limit_per_account: int = Field(ge=1, le=100)
    caption_mode: Literal["per_media", "all"] | None = None  # None = follow the main loop's caption
    caption: str | None = Field(default=None, max_length=2200)


def _copy_out(copy: InstagramLoop, partner: User | None, accounts: int) -> dict:
    return {
        "id": str(copy.id),
        "partner_id": str(partner.id) if partner else None,
        "partner_name": (partner.full_name or partner.nickname or "Sócio") if partner else "Sócio",
        "customized": bool(copy.owner_overrides),
        "interval_min_minutes": copy.interval_min_minutes,
        "interval_max_minutes": copy.interval_max_minutes,
        "daily_limit_per_account": copy.daily_limit_per_account,
        "caption_mode": copy.caption_mode,
        "caption": copy.caption,
        "accounts_count": accounts,
        "status": copy.status,
    }


async def _chief_loop(db, access, user: User, loop_id: uuid.UUID) -> InstagramLoop:
    await _owned_workspace(access, user)
    loop = await db.scalar(select(InstagramLoop).where(InstagramLoop.id == loop_id, InstagramLoop.workspace_id == access.workspace.id))
    if loop is None or loop.linked:
        raise HTTPException(status_code=404, detail="Loop não encontrado.")
    return loop


async def _partner_copies(db, loop: InstagramLoop, copy_id: uuid.UUID | None = None) -> list[dict]:
    query = (
        select(InstagramLoop, User)
        .join(Workspace, Workspace.id == InstagramLoop.workspace_id)
        .join(User, User.id == Workspace.owner_id)
        .where(InstagramLoop.template_loop_id == loop.id, InstagramLoop.linked.is_(True))
        .order_by(User.full_name)
    )
    if copy_id is not None:
        query = query.where(InstagramLoop.id == copy_id)
    out = []
    for copy, partner in (await db.execute(query)).all():
        accounts = await db.scalar(select(func.count()).select_from(InstagramLoopAccount).where(InstagramLoopAccount.loop_id == copy.id)) or 0
        out.append(_copy_out(copy, partner, int(accounts)))
    return out


@router.get("/loops/{loop_id}/copies")
async def loop_copies(loop_id: uuid.UUID, access: OwnerAccess, user: AuthenticatedUser, db: DbSession) -> dict:
    """The partners' copies of a shared loop, each with what the chief changed for that partner."""
    loop = await _chief_loop(db, access, user, loop_id)
    return {"copies": await _partner_copies(db, loop)}


@router.put("/loops/{loop_id}/copies/{copy_id}", dependencies=[Depends(require_csrf)])
async def customize_loop_copy(
    loop_id: uuid.UUID, copy_id: uuid.UUID, payload: LoopCopyOverrides, access: OwnerAccess, user: AuthenticatedUser, db: DbSession
) -> dict:
    """Change one partner's copy only (schedule, daily limit, caption). The main loop and the
    other partners don't change; media keep following the main loop."""
    if payload.interval_max_minutes < payload.interval_min_minutes:
        raise HTTPException(status_code=422, detail="O intervalo máximo precisa ser maior ou igual ao mínimo.")
    overrides = payload.model_dump(exclude={"caption_mode", "caption"})
    if payload.caption_mode is not None:
        caption = (payload.caption or "").strip() or None
        if payload.caption_mode == "all" and caption is None:
            raise HTTPException(status_code=422, detail="Escreva a legenda usada em todos os posts.")
        overrides.update(caption_mode=payload.caption_mode, caption=caption)
    return await _set_overrides(db, access, user, loop_id, copy_id, overrides)


@router.delete("/loops/{loop_id}/copies/{copy_id}/customization", dependencies=[Depends(require_csrf)])
async def reset_loop_copy(loop_id: uuid.UUID, copy_id: uuid.UUID, access: OwnerAccess, user: AuthenticatedUser, db: DbSession) -> dict:
    """The partner's copy follows the main loop again."""
    return await _set_overrides(db, access, user, loop_id, copy_id, None)


async def _set_overrides(db, access, user: User, loop_id: uuid.UUID, copy_id: uuid.UUID, overrides: dict | None) -> dict:
    loop = await _chief_loop(db, access, user, loop_id)
    copy = await db.scalar(
        select(InstagramLoop).where(InstagramLoop.id == copy_id, InstagramLoop.template_loop_id == loop.id, InstagramLoop.linked.is_(True))
    )
    if copy is None:
        raise HTTPException(status_code=404, detail="Este sócio não tem cópia deste loop.")
    copy.owner_overrides = overrides
    await service.sync_linked_loop(db, loop, copy)
    await db.commit()
    return (await _partner_copies(db, loop, copy.id))[0]


@router.post("/flows/{flow_id}/share", dependencies=[Depends(require_csrf)])
async def share_flow(flow_id: uuid.UUID, payload: ShareFlowRequest, access: OwnerAccess, user: AuthenticatedUser, db: DbSession) -> dict:
    await _owned_workspace(access, user)
    flow = await db.scalar(select(TgFlow).where(TgFlow.id == flow_id, TgFlow.workspace_id == access.workspace.id))
    if flow is None:
        raise HTTPException(status_code=404, detail="Funil não encontrado.")
    if payload.shared:
        targets = await _targets(db, user, payload.partner_ids)
        loop = None
        if payload.loop_id:
            loop = await db.scalar(
                select(InstagramLoop).where(
                    InstagramLoop.id == payload.loop_id, InstagramLoop.workspace_id == access.workspace.id,
                    InstagramLoop.linked.is_(False),
                )
            )
            if loop is None:
                raise HTTPException(status_code=404, detail="Loop não encontrado.")
            # The loop goes to the same partners (it may already be shared with others too).
            loop.shared_with = service.merge_targets(loop.shared_with, targets) if loop.shared else targets
            loop.shared = True
        flow.shared_loop_id = loop.id if loop else None
        flow.shared_with = targets
    else:
        flow.shared_with = None
    flow.shared = payload.shared
    await db.commit()
    return {
        "id": str(flow.id), "shared": flow.shared, "shared_with": _share_out(flow),
        "loop_id": str(flow.shared_loop_id) if flow.shared_loop_id else None,
    }


class PartnerShareRequest(BaseModel):
    kind: Literal["flow", "loop"]
    id: uuid.UUID
    shared: bool


def _with_partner(item: InstagramLoop | TgFlow, partner_id: str, everyone: set[str], on: bool) -> None:
    """Turn one partner on or off for a funnel/loop, keeping everyone else as they were."""
    if on:
        if not item.shared:
            item.shared, item.shared_with = True, [partner_id]
        elif item.shared_with is not None:
            item.shared_with = service.merge_targets(item.shared_with, [partner_id])
        return
    if not item.shared:
        return
    current = everyone if item.shared_with is None else {str(t) for t in item.shared_with}
    remaining = sorted(current - {partner_id})
    item.shared, item.shared_with = (True, remaining) if remaining else (False, None)


@router.post("/{affiliation_id}/shares", dependencies=[Depends(require_csrf)])
async def share_with_partner(
    affiliation_id: uuid.UUID, payload: PartnerShareRequest, access: OwnerAccess, user: AuthenticatedUser, db: DbSession,
) -> dict:
    """From the partner's row: share (or stop sharing) one funnel or loop with just this partner."""
    await _owned_workspace(access, user)
    link = await db.scalar(
        select(Affiliation).where(
            Affiliation.id == affiliation_id, Affiliation.chief_user_id == user.id, Affiliation.status == "ACTIVE"
        )
    )
    if link is None:
        raise HTTPException(status_code=404, detail="Sócio não encontrado.")
    model = TgFlow if payload.kind == "flow" else InstagramLoop
    where = [model.id == payload.id, model.workspace_id == access.workspace.id]
    if model is InstagramLoop:
        where.append(InstagramLoop.linked.is_(False))
    item = await db.scalar(select(model).where(*where))
    if item is None:
        raise HTTPException(status_code=404, detail="Funil não encontrado." if payload.kind == "flow" else "Loop não encontrado.")
    _with_partner(item, str(link.affiliate_user_id), await service.partner_ids(db, user.id), payload.shared)
    await db.commit()
    return {"id": str(item.id), "shared": item.shared, "shared_with": _share_out(item)}


# ------------------------------------------------------------------ share rules (owner only)

SHARE_BASIS = (
    "Base de cálculo: valor líquido da venda (bruto menos a taxa do gateway). A comissão do dono "
    "sai dessa base pelo split do gateway; a taxa Falcon Bot por venda sai da parte do vendedor. "
    "Vendas estornadas não geram comissão."
)
HUNDRED = Decimal("100")


class FlowShareRequest(BaseModel):
    flow_id: uuid.UUID
    partner_id: uuid.UUID
    gateway: Literal["smokepay", "snakepay"]
    seller_percent: Decimal = Field(gt=0, le=100, decimal_places=2)
    owner_percent: Decimal = Field(ge=0, lt=100, decimal_places=2)
    # None keeps the saved ShopID (when editing); "" clears it.
    seller_shop_id: str | None = Field(default=None, max_length=64)
    owner_shop_id: str | None = Field(default=None, max_length=64)
    # A loop of mine that goes out with the funnel to this partner; left out = unchanged, null = none.
    loop_id: uuid.UUID | None = None


def _share_rule_out(rule: TgFlowShare, flow: TgFlow, partner: User | None, stats: dict | None = None) -> dict:
    return {
        "id": str(rule.id), "flow_id": str(flow.id), "flow_name": flow.name,
        "partner_id": str(rule.partner_user_id), "partner_name": (partner.full_name or partner.nickname) if partner else None,
        "gateway": rule.gateway, "seller_percent": _f(rule.seller_percent), "owner_percent": _f(rule.owner_percent),
        "seller_shop_id": service.mask_shop_id(rule.seller_shop_id), "owner_shop_id": service.mask_shop_id(rule.owner_shop_id),
        "loop_id": str(flow.shared_loop_id) if flow.shared_loop_id else None,
        "status": rule.status, "rule": "share", "updated_at": rule.updated_at.isoformat() if rule.updated_at else None,
        "stats": stats or {"sales": 0, "gross": 0.0, "commission": 0.0},
    }


async def _share_stats(db, share_ids: list[uuid.UUID]) -> dict[uuid.UUID, dict]:
    if not share_ids:
        return {}
    rows = await db.execute(
        select(
            TgOrder.share_id, func.count(TgOrder.id), func.coalesce(func.sum(TgOrder.amount), 0),
            func.coalesce(func.sum(TgOrder.split_amount), 0),
        )
        .where(TgOrder.share_id.in_(share_ids), TgOrder.status == "paid")
        .group_by(TgOrder.share_id)
    )
    return {sid: {"sales": int(n), "gross": _f(gross), "commission": _f(commission)} for sid, n, gross, commission in rows.all()}


async def _validate_shop_ids(db, user: User, gateway: str, owner_percent: Decimal, seller: str | None, owner: str | None) -> None:
    from app.bots import gateways

    if gateway != "snakepay":
        return
    if not await gateways.snakepay_available(db):
        raise HTTPException(status_code=409, detail="A SnakePay ainda não foi liberada pelo administrador.")
    platform = await gateways.platform_recipients(db)
    if not seller:
        raise HTTPException(status_code=422, detail="Informe o ShopID SnakePay do sócio vendedor.")
    if not gateways.valid_recipient(seller):
        raise HTTPException(status_code=422, detail="ShopID do vendedor inválido (começa com snakepay_).")
    if any(gateways.same_recipient(seller, own) for own in platform):
        raise HTTPException(status_code=422, detail="O ShopID do vendedor é o da conta da plataforma.")
    needs_owner = owner_percent > 0 and user.platform_role != "SUPER_ADMIN"
    if needs_owner and not owner:
        raise HTTPException(status_code=422, detail="Informe o seu ShopID SnakePay para receber a comissão.")
    if owner:
        if not gateways.valid_recipient(owner):
            raise HTTPException(status_code=422, detail="O seu ShopID é inválido (começa com snakepay_).")
        if gateways.same_recipient(seller, owner):
            raise HTTPException(status_code=422, detail="O ShopID do vendedor e o seu precisam ser contas diferentes.")
        if user.platform_role != "SUPER_ADMIN" and any(gateways.same_recipient(owner, own) for own in platform):
            raise HTTPException(status_code=422, detail="Esse é o ShopID da conta da plataforma, não o seu.")


@router.get("/flow-shares")
async def my_flow_shares(access: OwnerAccess, user: AuthenticatedUser, db: DbSession) -> dict:
    """Que compartilhei: every funnel of mine shared with a partner, with its rules and sales.
    Funnels shared before the per-partner rules show the partnership's percentage."""
    await _owned_workspace(access, user)
    flows = {
        flow.id: flow
        for flow in await db.scalars(select(TgFlow).where(TgFlow.workspace_id == access.workspace.id).order_by(TgFlow.name))
    }
    rules = list(
        await db.scalars(
            select(TgFlowShare).where(TgFlowShare.owner_user_id == user.id, TgFlowShare.flow_id.in_(list(flows) or [uuid.uuid4()]))
        )
    )
    partners = {
        link.affiliate_user_id: link
        for link in await db.scalars(select(Affiliation).where(Affiliation.chief_user_id == user.id, Affiliation.status == "ACTIVE"))
    }
    users = {
        u.id: u
        for u in await db.scalars(select(User).where(User.id.in_([*partners, *(r.partner_user_id for r in rules)] or [uuid.uuid4()])))
    }
    stats = await _share_stats(db, [rule.id for rule in rules])
    with_rules = {(rule.flow_id, rule.partner_user_id) for rule in rules}
    items = [_share_rule_out(rule, flows[rule.flow_id], users.get(rule.partner_user_id), stats.get(rule.id)) for rule in rules]
    for flow in flows.values():
        if not flow.shared:
            continue
        targets = set(partners) if flow.shared_with is None else {uuid.UUID(str(t)) for t in flow.shared_with} & set(partners)
        for partner_id in sorted(targets, key=str):
            if (flow.id, partner_id) in with_rules:
                continue
            link = partners[partner_id]
            percent = min(link.participation_percent, service.MAX_COMMISSION)
            person = users.get(partner_id)
            items.append({
                "id": None, "flow_id": str(flow.id), "flow_name": flow.name, "partner_id": str(partner_id),
                "partner_name": (person.full_name or person.nickname) if person else None,
                "gateway": flow.payment_gateway or access.workspace.payment_gateway or "smokepay",
                "seller_percent": _f(HUNDRED - percent), "owner_percent": _f(percent),
                "seller_shop_id": None, "owner_shop_id": None, "status": "ACTIVE", "rule": "partnership",
                "loop_id": str(flow.shared_loop_id) if flow.shared_loop_id else None,
                "updated_at": None, "stats": None,
            })
    items.sort(key=lambda item: (item["flow_name"].lower(), item["partner_name"] or "", item["status"]))
    return {"basis": SHARE_BASIS, "items": items}


@router.put("/flow-shares", dependencies=[Depends(require_csrf)])
async def save_flow_share(payload: FlowShareRequest, access: OwnerAccess, user: AuthenticatedUser, db: DbSession) -> dict:
    """Share one of my funnels with one partner, or change the rules of that share. Only the
    funnel's owner gets here: the funnel must be in the owner's own operation and the partner
    must be the owner's active partner; the seller can never change these rules."""
    await _owned_workspace(access, user)
    if payload.seller_percent + payload.owner_percent != HUNDRED:
        raise HTTPException(status_code=422, detail="A parte do vendedor e a comissão do dono precisam somar 100%.")
    flow = await db.scalar(select(TgFlow).where(TgFlow.id == payload.flow_id, TgFlow.workspace_id == access.workspace.id))
    if flow is None:
        raise HTTPException(status_code=404, detail="Funil não encontrado.")
    link = await db.scalar(
        select(Affiliation).where(
            Affiliation.chief_user_id == user.id, Affiliation.affiliate_user_id == payload.partner_id,
            Affiliation.status == "ACTIVE",
        )
    )
    if link is None:
        raise HTTPException(status_code=422, detail="Escolha um dos seus sócios ativos.")
    rule = await service.share_for_partner(db, flow.id, payload.partner_id)

    def pick(value: str | None, saved: str | None) -> str | None:
        if value is None:
            return saved
        return value.strip() or None

    seller_shop = owner_shop = None
    if payload.gateway == "snakepay":
        seller_shop = pick(payload.seller_shop_id, rule.seller_shop_id if rule else None)
        owner_shop = pick(payload.owner_shop_id, rule.owner_shop_id if rule else None)
    await _validate_shop_ids(db, user, payload.gateway, payload.owner_percent, seller_shop, owner_shop)

    before = None
    if rule is None:
        rule = TgFlowShare(flow_id=flow.id, owner_user_id=user.id, partner_user_id=payload.partner_id)
        db.add(rule)
    else:
        before = {
            "gateway": rule.gateway, "seller_percent": _f(rule.seller_percent), "owner_percent": _f(rule.owner_percent),
            "seller_shop_id": service.mask_shop_id(rule.seller_shop_id), "owner_shop_id": service.mask_shop_id(rule.owner_shop_id),
            "status": rule.status,
        }
    rule.gateway = payload.gateway
    rule.seller_percent = payload.seller_percent
    rule.owner_percent = payload.owner_percent
    rule.seller_shop_id = seller_shop
    rule.owner_shop_id = owner_shop
    rule.status = "ACTIVE"
    rule.updated_by_user_id = user.id
    everyone = await service.partner_ids(db, user.id)
    _with_partner(flow, str(payload.partner_id), everyone, True)
    if "loop_id" in payload.model_fields_set:
        loop = None
        if payload.loop_id is not None:
            loop = await db.scalar(
                select(InstagramLoop).where(
                    InstagramLoop.id == payload.loop_id, InstagramLoop.workspace_id == access.workspace.id,
                    InstagramLoop.linked.is_(False),
                )
            )
            if loop is None:
                raise HTTPException(status_code=404, detail="Loop não encontrado.")
            _with_partner(loop, str(payload.partner_id), everyone, True)
        flow.shared_loop_id = loop.id if loop else None
    await db.flush()
    after = {
        "flow": flow.name, "partner_id": str(payload.partner_id), "gateway": rule.gateway,
        "seller_percent": _f(rule.seller_percent), "owner_percent": _f(rule.owner_percent),
        "seller_shop_id": service.mask_shop_id(seller_shop), "owner_shop_id": service.mask_shop_id(owner_shop),
    }
    service.audit(
        db, actor=user, workspace_id=access.workspace.id, action="share.updated" if before else "share.created",
        entity="flow_share", entity_id=rule.id, details={"before": before, "after": after},
    )
    await db.commit()
    await db.refresh(rule)
    partner = await db.get(User, payload.partner_id)
    await service.notify_user(
        db, payload.partner_id, "share", "Funil compartilhado com você",
        f"{flow.name}: você fica com {_pct(rule.seller_percent)} do líquido de cada venda.",
        "/bot/compartilhados-comigo",
    )
    await db.commit()
    return _share_rule_out(rule, flow, partner, (await _share_stats(db, [rule.id])).get(rule.id))


@router.delete("/flow-shares/{share_id}", dependencies=[Depends(require_csrf)])
async def revoke_flow_share(share_id: uuid.UUID, access: OwnerAccess, user: AuthenticatedUser, db: DbSession) -> dict:
    """Stop sharing a funnel with one partner. The rules stay recorded for the audit and the
    sales already made keep the rules they were charged with."""
    await _owned_workspace(access, user)
    rule = await db.scalar(select(TgFlowShare).where(TgFlowShare.id == share_id, TgFlowShare.owner_user_id == user.id))
    flow = await db.get(TgFlow, rule.flow_id) if rule else None
    if rule is None or flow is None or flow.workspace_id != access.workspace.id:
        raise HTTPException(status_code=404, detail="Compartilhamento não encontrado.")
    rule.status = "REVOKED"
    rule.updated_by_user_id = user.id
    _with_partner(flow, str(rule.partner_user_id), await service.partner_ids(db, user.id), False)
    service.audit(
        db, actor=user, workspace_id=access.workspace.id, action="share.revoked", entity="flow_share",
        entity_id=rule.id, details={"flow": flow.name, "partner_id": str(rule.partner_user_id)},
    )
    await db.commit()
    await db.refresh(rule)
    return _share_rule_out(rule, flow, await db.get(User, rule.partner_user_id))


@router.get("/flow-shares/{share_id}/history")
async def flow_share_history(share_id: uuid.UUID, access: OwnerAccess, user: AuthenticatedUser, db: DbSession) -> dict:
    await _owned_workspace(access, user)
    rule = await db.scalar(select(TgFlowShare).where(TgFlowShare.id == share_id, TgFlowShare.owner_user_id == user.id))
    if rule is None:
        raise HTTPException(status_code=404, detail="Compartilhamento não encontrado.")
    from app.models import AuditEvent

    events = await db.scalars(
        select(AuditEvent)
        .where(AuditEvent.entity == "flow_share", AuditEvent.entity_id == rule.id)
        .order_by(AuditEvent.created_at.desc())
        .limit(50)
    )
    return {
        "items": [
            {"action": e.action, "details": e.details, "created_at": e.created_at.isoformat() if e.created_at else None}
            for e in events
        ]
    }


async def operations_of(db, workspace_id: uuid.UUID, start, end) -> dict:
    """Read-only view of an operation: loops, bots (never tokens), funnels and sales."""
    loops = list(await db.scalars(select(InstagramLoop).where(InstagramLoop.workspace_id == workspace_id).order_by(InstagramLoop.name)))
    loop_ids = [loop.id for loop in loops] or [uuid.uuid4()]
    accounts = dict(
        (
            await db.execute(
                select(InstagramLoopAccount.loop_id, func.count(InstagramLoopAccount.account_id))
                .where(InstagramLoopAccount.loop_id.in_(loop_ids))
                .group_by(InstagramLoopAccount.loop_id)
            )
        ).all()
    )
    published_at = func.coalesce(InstagramPublicationJob.published_at, InstagramPublicationJob.updated_at)
    posts = dict(
        (
            await db.execute(
                select(InstagramPublicationJob.loop_id, func.count(InstagramPublicationJob.id))
                .where(
                    InstagramPublicationJob.loop_id.in_(loop_ids), InstagramPublicationJob.status == "published",
                    published_at >= start, published_at < end,
                )
                .group_by(InstagramPublicationJob.loop_id)
            )
        ).all()
    )
    flows = list(await db.scalars(select(TgFlow).where(TgFlow.workspace_id == workspace_id).order_by(TgFlow.name)))
    flow_names = {flow.id: flow.name for flow in flows}
    bots = list(await db.scalars(select(TgBot).where(TgBot.workspace_id == workspace_id).order_by(TgBot.created_at)))
    bot_ids = [bot.id for bot in bots] or [uuid.uuid4()]
    leads = dict(
        (
            await db.execute(
                select(TgLead.bot_id, func.count(TgLead.id))
                .where(TgLead.bot_id.in_(bot_ids), TgLead.created_at >= start, TgLead.created_at < end)
                .group_by(TgLead.bot_id)
            )
        ).all()
    )
    paid = {
        bot_id: (int(count), _f(total))
        for bot_id, count, total in (
            await db.execute(
                select(TgOrder.bot_id, func.count(TgOrder.id), func.coalesce(func.sum(TgOrder.amount), 0))
                .where(TgOrder.bot_id.in_(bot_ids), TgOrder.status == "paid", TgOrder.paid_at >= start, TgOrder.paid_at < end)
                .group_by(TgOrder.bot_id)
            )
        ).all()
    }
    return {
        "loops": [
            {
                "id": str(loop.id), "name": loop.name, "status": loop.status, "accounts": accounts.get(loop.id, 0),
                "posts": posts.get(loop.id, 0), "from_template": loop.template_loop_id is not None,
            }
            for loop in loops
        ],
        "bots": [
            {
                "id": str(bot.id), "name": bot.name, "username": bot.username, "status": bot.status, "is_active": bot.is_active,
                "flow_name": flow_names.get(bot.flow_id), "leads": leads.get(bot.id, 0),
                "sales": paid.get(bot.id, (0, 0.0))[0], "revenue": paid.get(bot.id, (0, 0.0))[1],
            }
            for bot in bots
        ],
        "flows": [
            {
                "id": str(flow.id), "name": flow.name, "from_template": flow.template_flow_id is not None,
                "customized_at": flow.customized_at.isoformat() if flow.customized_at else None, "shared": flow.shared,
            }
            for flow in flows
        ],
        "totals": await _sales(db, workspace_id, start, end),
        "sales": await _recent_orders(db, workspace_id, start, end, limit=20),
    }


@router.get("/{affiliation_id}/operations")
async def partner_operations(
    affiliation_id: uuid.UUID, access: OwnerAccess, user: AuthenticatedUser, db: DbSession,
    period: AnalyticsPeriod = "30d", start_date: date | None = None, end_date: date | None = None,
) -> dict:
    link = await db.scalar(
        select(Affiliation).where(Affiliation.id == affiliation_id, Affiliation.chief_user_id == user.id)
    )
    if link is None:  # also hides other chiefs' partners
        raise HTTPException(status_code=404, detail="Sócio não encontrado.")
    start, end = period_bounds(period, start_date, end_date, utc_now())
    workspace = await service.owner_workspace(db, link.affiliate_user_id)
    if workspace is None:
        return {"period_label": period_label(start, end), "loops": [], "bots": [], "flows": [], "totals": None, "sales": []}
    data = await operations_of(db, workspace.id, start, end)
    data["commission"] = await _sales(db, workspace.id, start, end, chief_user_id=user.id)
    data["period_label"] = period_label(start, end)
    return data


# ------------------------------------------------------------------ notices


@router.get("/notifications")
async def notifications(user: AuthenticatedUser, db: DbSession) -> dict:
    rows = await db.scalars(
        select(AppNotification).where(AppNotification.user_id == user.id).order_by(AppNotification.created_at.desc()).limit(30)
    )
    items = [
        {
            "id": str(n.id), "kind": n.kind, "title": n.title, "body": n.body, "url": n.url,
            "read": n.read_at is not None, "created_at": n.created_at.isoformat(),
        }
        for n in rows
    ]
    return {"items": items, "unread": sum(1 for i in items if not i["read"])}


@router.post("/notifications/read", status_code=204, dependencies=[Depends(require_csrf)])
async def mark_read(user: AuthenticatedUser, db: DbSession) -> None:
    await db.execute(
        update(AppNotification)
        .where(AppNotification.user_id == user.id, AppNotification.read_at.is_(None))
        .values(read_at=utc_now())
    )
    await db.commit()
