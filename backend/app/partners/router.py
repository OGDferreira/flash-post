"""Partner (sócio) panel, commission acceptance, shared templates and the chief's
read-only view of each partner's operation.

Permissions are enforced here, never only in the UI:
* a partner only sees their own operation and the templates their chief shared;
* a chief only sees direct partners, and never a bot token or account credential;
* the commission comes from the database, never from the request.
"""

import uuid
from datetime import date
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
    TgLead,
    TgOrder,
    User,
    Workspace,
)
from app.partners import service

router = APIRouter(prefix="/api/partners", tags=["Partners"])

SPLIT_BASIS = (
    "O split é feito pela própria SmokePay na cobrança: do valor líquido (bruto menos a taxa "
    "da SmokePay), o percentual aceito vai para o chefe e o restante fica na subconta do sócio."
)


class AcceptRequest(BaseModel):
    percent: Decimal = Field(ge=0, le=100, decimal_places=2)


class ShareRequest(BaseModel):
    shared: bool


def _f(value: Decimal | None) -> float:
    return float(value or 0)


async def _sales(db, workspace_id: uuid.UUID, start, end, *, chief_user_id: uuid.UUID | None = None) -> dict:
    """Paid FlashBot sales of a workspace with fee, commission and partner net."""
    where = [TgOrder.workspace_id == workspace_id, TgOrder.status == "paid", TgOrder.paid_at >= start, TgOrder.paid_at < end]
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
        .where(TgOrder.workspace_id == workspace_id, TgOrder.status == "paid", TgOrder.paid_at >= start, TgOrder.paid_at < end)
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
            "accepted_percent": _f(link.accepted_percent) if link.accepted_percent is not None else None,
            "accepted_at": link.accepted_at.isoformat() if link.accepted_at else None,
            "pending_acceptance": service.pending_acceptance(link),
            "since": link.created_at.isoformat(),
        }
    return out


@router.post("/me/accept", dependencies=[Depends(require_csrf)])
async def accept_commission(payload: AcceptRequest, user: AuthenticatedUser, db: DbSession) -> dict:
    """The partner confirms the percentage they are seeing; it must match the current proposal."""
    link = await service.partner_link(db, user.id)
    if link is None:
        raise HTTPException(status_code=404, detail="Você não tem uma sociedade ativa.")
    if payload.percent != link.participation_percent:
        raise HTTPException(status_code=409, detail="O percentual mudou. Atualize a página e confira de novo.")
    link.accepted_percent = link.participation_percent
    link.accepted_at = utc_now()
    await service.notify_user(
        db, link.chief_user_id, "partner-accepted", "Sócio aceitou a comissão",
        f"{user.full_name} aceitou {float(link.participation_percent):g}% de comissão. Vale para as próximas vendas.", "/feature/affiliates",
    )
    await db.commit()
    return {"accepted_percent": _f(link.accepted_percent), "accepted_at": link.accepted_at.isoformat()}


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
    loops = list(
        await db.scalars(
            select(InstagramLoop)
            .where(InstagramLoop.workspace_id == chief_workspace.id, InstagramLoop.shared.is_(True))
            .order_by(InstagramLoop.name)
        )
    )
    flows = list(
        await db.scalars(
            select(TgFlow).where(TgFlow.workspace_id == chief_workspace.id, TgFlow.shared.is_(True)).order_by(TgFlow.name)
        )
    )
    used_loops = set(
        await db.scalars(
            select(InstagramLoop.template_loop_id).where(
                InstagramLoop.workspace_id == access.workspace.id, InstagramLoop.template_loop_id.is_not(None)
            )
        )
    )
    used_flows = set(
        await db.scalars(
            select(TgFlow.template_flow_id).where(
                TgFlow.workspace_id == access.workspace.id, TgFlow.template_flow_id.is_not(None)
            )
        )
    )
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
                "in_use": loop.id in used_loops,
            }
            for loop in loops
        ],
        "flows": [
            {
                "id": str(flow.id), "name": flow.name,
                "plans": len((flow.definition or {}).get("plans") or []),
                "upsells": len((flow.definition or {}).get("upsells") or []),
                "downsells": len((flow.definition or {}).get("downsells") or []),
                "in_use": flow.id in used_flows,
            }
            for flow in flows
        ],
    }


@router.post("/shared/loops/{loop_id}/use", status_code=201, dependencies=[Depends(require_csrf)])
async def use_shared_loop(loop_id: uuid.UUID, access: OwnerAccess, user: AuthenticatedUser, db: DbSession) -> dict:
    _link, chief_workspace = await _partner_context(db, user, access)
    source = await db.scalar(
        select(InstagramLoop).where(
            InstagramLoop.id == loop_id, InstagramLoop.workspace_id == chief_workspace.id, InstagramLoop.shared.is_(True)
        )
    )
    if source is None:
        raise HTTPException(status_code=404, detail="Loop compartilhado não encontrado.")
    clone = await service.clone_loop(db, source, access.workspace.id)
    await db.commit()
    return {"id": str(clone.id), "name": clone.name}


@router.post("/shared/flows/{flow_id}/use", status_code=201, dependencies=[Depends(require_csrf)])
async def use_shared_flow(flow_id: uuid.UUID, access: OwnerAccess, user: AuthenticatedUser, db: DbSession) -> dict:
    _link, chief_workspace = await _partner_context(db, user, access)
    source = await db.scalar(
        select(TgFlow).where(TgFlow.id == flow_id, TgFlow.workspace_id == chief_workspace.id, TgFlow.shared.is_(True))
    )
    if source is None:
        raise HTTPException(status_code=404, detail="Funil compartilhado não encontrado.")
    clone = await service.clone_flow(db, source, access.workspace.id)
    await db.commit()
    return {"id": str(clone.id), "name": clone.name}


# ------------------------------------------------------------------ chief


async def _owned_workspace(access, user: User) -> None:
    if access.workspace.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Somente o dono da operação compartilha modelos.")


@router.post("/loops/{loop_id}/share", dependencies=[Depends(require_csrf)])
async def share_loop(loop_id: uuid.UUID, payload: ShareRequest, access: OwnerAccess, user: AuthenticatedUser, db: DbSession) -> dict:
    await _owned_workspace(access, user)
    loop = await db.scalar(select(InstagramLoop).where(InstagramLoop.id == loop_id, InstagramLoop.workspace_id == access.workspace.id))
    if loop is None:
        raise HTTPException(status_code=404, detail="Loop não encontrado.")
    loop.shared = payload.shared
    await db.commit()
    return {"id": str(loop.id), "shared": loop.shared}


@router.post("/flows/{flow_id}/share", dependencies=[Depends(require_csrf)])
async def share_flow(flow_id: uuid.UUID, payload: ShareRequest, access: OwnerAccess, user: AuthenticatedUser, db: DbSession) -> dict:
    await _owned_workspace(access, user)
    flow = await db.scalar(select(TgFlow).where(TgFlow.id == flow_id, TgFlow.workspace_id == access.workspace.id))
    if flow is None:
        raise HTTPException(status_code=404, detail="Funil não encontrado.")
    flow.shared = payload.shared
    await db.commit()
    return {"id": str(flow.id), "shared": flow.shared}


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
