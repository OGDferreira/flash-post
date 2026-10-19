"""FlashBot > Gateways: each operation picks the PIX gateway of its bots; the Super Admin
turns SnakePay on once its key and webhook secret are set on the server."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update

from app.auth.dependencies import AuthenticatedUser, DbSession, OwnerAccess, SuperAdminUser, require_csrf
from app.bots import engine, gateways, snakepay
from app.core.config import get_settings
from app.models import SystemSetting, TgBot, TgFlow, TgOrder, User, Workspace

router = APIRouter(prefix="/api/payment-gateways", tags=["Payment gateways"])


class GatewayChoice(BaseModel):
    gateway: str = Field(pattern="^(smokepay|snakepay)$")
    snakepay_recipient_id: str | None = Field(default=None, max_length=64)
    # True: every funnel follows this gateway (clears the per-funnel choices).
    apply_to_all: bool = False


class FlowGateway(BaseModel):
    gateway: str | None = Field(default=None, pattern="^(smokepay|snakepay)$")  # None = operation default


class SnakepaySwitch(BaseModel):
    enabled: bool


def _smokepay_configured() -> bool:
    key = get_settings().smokepay_api_key
    return bool(key and key.get_secret_value().strip())


def _brl(value) -> str:
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


async def _smokepay_fee_text(db) -> str:
    """SmokePay's fee depends on the account's contract: show the average it really charged
    on the platform's latest paid sales, plus the withdrawal fee."""
    recent = (
        select(TgOrder.amount, TgOrder.gateway_fee)
        .where(TgOrder.gateway == "smokepay", TgOrder.status == "paid", TgOrder.gateway_fee.is_not(None), TgOrder.amount > 0)
        .order_by(TgOrder.paid_at.desc())
        .limit(100)
        .subquery()
    )
    total, fees = (await db.execute(select(func.sum(recent.c.amount), func.sum(recent.c.gateway_fee)))).one()
    withdraw = f"saque {_brl(get_settings().smokepay_withdraw_fee)}"
    if not total or fees is None:
        return f"Taxa por venda conforme seu contrato SmokePay · {withdraw}"
    percent = f"{float(fees) * 100 / float(total):.1f}".replace(".", ",")
    return f"≈ {percent}% por venda (média das últimas vendas) · {withdraw}"


async def _state(db, user, workspace) -> dict:
    admin = user.platform_role == "SUPER_ADMIN"
    enabled = await gateways.snakepay_enabled(db)
    state = {
        "current": workspace.payment_gateway if workspace.payment_gateway in gateways.GATEWAYS else "smokepay",
        "snakepay_recipient_id": workspace.snakepay_recipient_id,
        "is_admin": admin,
        "flows": [
            {"id": str(flow.id), "name": flow.name, "gateway": flow.payment_gateway}
            for flow in await db.scalars(
                select(TgFlow).where(TgFlow.workspace_id == workspace.id).order_by(TgFlow.name, TgFlow.id)
            )
        ],
        # The platform's own sales need no recipient: everything stays in its account.
        "needs_recipient": not admin,
        "gateways": [
            {
                "id": "smokepay", "name": "SmokePay", "available": _smokepay_configured(),
                "fee": await _smokepay_fee_text(db), "description": "Pix com subconta própria e saque pelo FlashPost.",
            },
            {
                "id": "snakepay", "name": "SnakePay", "available": snakepay.configured() and enabled,
                "fee": "3% + R$ 0,25 por venda · saque pela SnakePay",
                "description": "Pix com repasse automático (split) para a sua conta SnakePay.",
            },
        ],
    }
    state["shared_flows"] = await _shared_flows(db, workspace)
    state["partners_without_shop_id"] = await _partners_without_shop_id(db, workspace)
    if admin:
        state["admin"] = {
            "snakepay_key_set": bool(get_settings().snakepay_api_key and get_settings().snakepay_api_key.get_secret_value().strip()),
            "snakepay_secret_set": bool(
                get_settings().snakepay_webhook_secret and get_settings().snakepay_webhook_secret.get_secret_value().strip()
            ),
            "snakepay_enabled": enabled,
            "snakepay_webhook_url": f"{get_settings().public_base_url.rstrip('/')}/api/bots/pay/snakepay",
        }
    return state


async def _shared_flows(db, workspace) -> list[dict]:
    """Funnels shared by a chief that this operation's bots run: they charge with the
    gateway the chief picked for them, not with this operation's choice."""
    flows = list(await db.scalars(
        select(TgFlow).join(TgBot, TgBot.flow_id == TgFlow.id).where(TgBot.workspace_id == workspace.id).distinct()
    ))
    shared = []
    for flow in flows:
        source = flow
        if flow.workspace_id == workspace.id and flow.template_flow_id is not None:
            source = await db.get(TgFlow, flow.template_flow_id) or flow
        if source.workspace_id == workspace.id:
            continue
        shared.append({"name": flow.name, "gateway": await gateways.gateway_choice(db, workspace, flow)})
    return shared


async def _partners_without_shop_id(db, workspace) -> list[str]:
    """Partners whose bots run this operation's funnels set to SnakePay but who have no
    ShopID yet: their sales keep going through SmokePay until they add it."""
    own = {flow.id: flow for flow in await db.scalars(select(TgFlow).where(TgFlow.workspace_id == workspace.id))}
    if not own:
        return []
    rows = await db.execute(
        select(TgBot.workspace_id, TgFlow)
        .join(TgFlow, TgFlow.id == TgBot.flow_id)
        .where(TgBot.workspace_id != workspace.id)
        .where((TgFlow.id.in_(own)) | (TgFlow.template_flow_id.in_(own)))
    )
    names: list[str] = []
    for partner_ws_id, flow in rows.all():
        partner_ws = await db.get(Workspace, partner_ws_id)
        if partner_ws is None or gateways.valid_recipient(partner_ws.snakepay_recipient_id or ""):
            continue
        if await gateways.gateway_choice(db, partner_ws, flow) != "snakepay":
            continue
        owner = await db.get(User, partner_ws.owner_id)
        name = (owner.full_name if owner else None) or partner_ws.name
        if name not in names:
            names.append(name)
    return names


@router.get("")
async def get_gateways(access: OwnerAccess, user: AuthenticatedUser, db: DbSession) -> dict:
    return await _state(db, user, access.workspace)


@router.put("", dependencies=[Depends(require_csrf)])
async def choose_gateway(payload: GatewayChoice, access: OwnerAccess, user: AuthenticatedUser, db: DbSession) -> dict:
    workspace = access.workspace
    recipient = (payload.snakepay_recipient_id or "").strip() or None
    if recipient is not None and not gateways.valid_recipient(recipient):
        raise HTTPException(
            status_code=422,
            detail="ShopID inválido. Copie o \"Seu ShopID\" em SnakePay → Split da conta (começa com snakepay_).",
        )
    if recipient is not None and user.platform_role != "SUPER_ADMIN" and any(
        gateways.same_recipient(recipient, own) for own in await gateways.platform_recipients(db)
    ):
        raise HTTPException(
            status_code=422,
            detail="Esse é o ShopID da conta da plataforma. Cole o ShopID da SUA conta SnakePay (Split da conta → Seu ShopID).",
        )
    if payload.gateway == "snakepay":
        if not await gateways.snakepay_available(db):
            raise HTTPException(status_code=409, detail="A SnakePay ainda não foi liberada pelo administrador.")
        if user.platform_role != "SUPER_ADMIN" and recipient is None:
            raise HTTPException(status_code=422, detail="Cole o seu ShopID da SnakePay para receber suas vendas.")
    workspace.payment_gateway = payload.gateway
    workspace.snakepay_recipient_id = recipient
    if payload.apply_to_all:
        await db.execute(update(TgFlow).where(TgFlow.workspace_id == workspace.id).values(payment_gateway=None))
    await db.commit()
    engine.resume_snakepay()  # a new ShopID/choice gets a fresh try right away
    return await _state(db, user, workspace)


@router.put("/flows/{flow_id}", dependencies=[Depends(require_csrf)])
async def flow_gateway(
    flow_id: uuid.UUID, payload: FlowGateway, access: OwnerAccess, user: AuthenticatedUser, db: DbSession
) -> dict:
    """One funnel uses a gateway other than the operation's default."""
    workspace = access.workspace
    flow = await db.scalar(select(TgFlow).where(TgFlow.id == flow_id, TgFlow.workspace_id == workspace.id))
    if flow is None:
        raise HTTPException(status_code=404, detail="Fluxo não encontrado.")
    if payload.gateway == "snakepay":
        if not await gateways.snakepay_available(db):
            raise HTTPException(status_code=409, detail="A SnakePay ainda não foi liberada pelo administrador.")
        if user.platform_role != "SUPER_ADMIN" and not workspace.snakepay_recipient_id:
            raise HTTPException(status_code=422, detail="Cadastre o seu ShopID da SnakePay antes de usar a SnakePay num fluxo.")
    flow.payment_gateway = payload.gateway
    await db.commit()
    engine.resume_snakepay()  # a new ShopID/choice gets a fresh try right away
    return await _state(db, user, workspace)


@router.put("/snakepay/enabled", dependencies=[Depends(require_csrf)])
async def switch_snakepay(payload: SnakepaySwitch, user: SuperAdminUser, db: DbSession) -> dict:
    if payload.enabled and not snakepay.configured():
        raise HTTPException(
            status_code=409,
            detail="Configure SNAKEPAY_API_KEY e SNAKEPAY_WEBHOOK_SECRET no Render antes de liberar a SnakePay.",
        )
    row = await db.get(SystemSetting, gateways.SNAKEPAY_ENABLED_KEY)
    if row is None:
        db.add(SystemSetting(key=gateways.SNAKEPAY_ENABLED_KEY, value={"enabled": payload.enabled}, updated_by_user_id=user.id))
    else:
        row.value = {"enabled": payload.enabled}
        row.updated_by_user_id = user.id
    await db.commit()
    engine.resume_snakepay()  # a new ShopID/choice gets a fresh try right away
    return {"enabled": payload.enabled}

