"""Flash > Gateways: the Super Admin releases centrally managed gateways and configures
which PIX gateway charges each operation's bots."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select, update

from app.auth.dependencies import AuthenticatedUser, DbSession, OwnerAccess, SuperAdminUser, require_csrf
from app.bots import atenaspay, engine, gateways, snakepay
from app.core.config import get_settings
from app.core.crypto import encrypt_value
from app.models import SystemSetting, TgBot, TgFlow, TgGatewaySetting, TgOrder, User, Workspace
from app.partners.service import active_share, audit, default_transaction_fee, transaction_fee_for

router = APIRouter(prefix="/api/payment-gateways", tags=["Payment gateways"])


class GatewayChoice(BaseModel):
    gateway: str = Field(pattern="^(smokepay|snakepay|atenaspay)$")
    snakepay_recipient_id: str | None = Field(default=None, max_length=64)
    # True: every funnel follows this gateway (clears the per-funnel choices).
    apply_to_all: bool = False


class FlowGateway(BaseModel):
    gateway: str | None = Field(default=None, pattern="^(smokepay|snakepay|atenaspay)$")  # None = operation default


class SnakepaySwitch(BaseModel):
    enabled: bool


class AtenaspaySwitch(BaseModel):
    enabled: bool


class SnakepayCredentials(BaseModel):
    api_key: str | None = Field(default=None, max_length=512)
    webhook_secret: str | None = Field(default=None, max_length=512)
    # Signs the account's withdrawals (Cash Out); optional, saved on its own too.
    cashout_secret: str | None = Field(default=None, max_length=512)
    clear: bool = False


class PriorityItem(BaseModel):
    gateway: str = Field(pattern="^(smokepay|snakepay|atenaspay)$")
    enabled: bool
    # None = every funnel of the operation; else only these own funnels.
    flow_ids: list[uuid.UUID] | None = Field(default=None, max_length=500)


class PriorityRequest(BaseModel):
    # In order: the first enabled one is the principal, the next ones are backups.
    items: list[PriorityItem] = Field(min_length=1, max_length=len(gateways.GATEWAYS))


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


async def _has_own_flow(db, workspace_id) -> bool:
    """Whether the operation has a funnel of its own (not a copy received from a chief)."""
    own_ids = select(TgFlow.id).where(TgFlow.workspace_id == workspace_id)
    row = await db.scalar(
        select(TgFlow.id).where(
            TgFlow.workspace_id == workspace_id,
            or_(TgFlow.template_flow_id.is_(None), TgFlow.template_flow_id.in_(own_ids)),
        ).limit(1)
    )
    return row is not None


async def _state(db, user, workspace) -> dict:
    admin = user.platform_role == "SUPER_ADMIN"
    enabled = await gateways.snakepay_enabled(db)
    atenas_enabled = await gateways.atenaspay_enabled(db)
    state = {
        "current": workspace.payment_gateway if workspace.payment_gateway in gateways.GATEWAYS else "smokepay",
        "snakepay_recipient_id": workspace.snakepay_recipient_id,
        "snakepay_account_key_set": bool(workspace.snakepay_api_key_encrypted),
        "snakepay_account_secret_set": bool(workspace.snakepay_webhook_secret_encrypted),
        "snakepay_cashout_secret_set": bool(workspace.snakepay_cashout_secret_encrypted),
        # The platform's own withdrawals use the server settings.
        "snakepay_platform_cashout_configured": admin and bool(get_settings().snakepay_cashout_secret),
        "snakepay_webhook_url": f"{get_settings().public_base_url.rstrip('/')}/api/bots/pay/snakepay",
        "atenaspay_webhook_url": engine.atenaspay_webhook_url(),
        "is_admin": admin,
        "flows": [
            {"id": str(flow.id), "name": flow.name, "gateway": flow.payment_gateway}
            for flow in await db.scalars(
                select(TgFlow).where(TgFlow.workspace_id == workspace.id).order_by(TgFlow.name, TgFlow.id)
            )
        ],
        # The platform's own sales need no recipient: everything stays in its account.
        "needs_recipient": not admin and not (
            workspace.snakepay_api_key_encrypted and workspace.snakepay_webhook_secret_encrypted
        ),
        # The ShopID (platform-key split) only matters for the operation's own funnels; a partner
        # that only runs the chief's shared funnels never needs it.
        "has_own_flow": admin or await _has_own_flow(db, workspace.id),
        "gateways": [
            {
                "id": "smokepay", "name": "SmokePay", "available": _smokepay_configured(),
                "fee": await _smokepay_fee_text(db), "description": "Pix com subconta própria e saque pelo Flash.",
            },
            {
                "id": "snakepay", "name": "SnakePay", "available": snakepay.configured() and enabled,
                "fee": "3% + R$ 0,25 por venda · saque pela SnakePay",
                "description": "Pix com repasse automático (split) para a sua conta SnakePay.",
            },
            {
                "id": "atenaspay", "name": "Athenas Pay", "available": atenaspay.configured() and atenas_enabled,
                "fee": "Taxas conforme seu contrato Atenas Pay",
                "description": "Pix com subcontas e divisão automática das vendas.",
            },
        ],
    }
    state["priority"] = await _priority(db, workspace, state["gateways"], admin)
    state["shared_flows"] = await _shared_flows(db, workspace)
    state["partners_without_shop_id"] = await _partners_without_shop_id(db, workspace)
    owner = await db.get(User, workspace.owner_id)
    fee = transaction_fee_for(owner, await default_transaction_fee(db))
    if not admin and fee > 0:  # the Super Admin's own bots do not pay it
        for gateway in state["gateways"]:
            gateway["fee"] += f" · taxa Flash {_brl(fee)} por venda"
    if admin:
        state["admin"] = {
            "snakepay_key_set": bool(get_settings().snakepay_api_key and get_settings().snakepay_api_key.get_secret_value().strip()),
            "snakepay_secret_set": bool(
                get_settings().snakepay_webhook_secret and get_settings().snakepay_webhook_secret.get_secret_value().strip()
            ),
            "snakepay_enabled": enabled,
            "snakepay_webhook_url": f"{get_settings().public_base_url.rstrip('/')}/api/bots/pay/snakepay",
            "atenaspay_key_set": bool(
                get_settings().atenaspay_api_key and get_settings().atenaspay_api_key.get_secret_value().strip()
            ),
            "atenaspay_secret_set": bool(
                get_settings().atenaspay_webhook_secret
                and get_settings().atenaspay_webhook_secret.get_secret_value().strip()
            ),
            "atenaspay_enabled": atenas_enabled,
            "atenaspay_webhook_url": engine.atenaspay_webhook_url(),
        }
    return state


def _snake_ready(workspace, admin: bool) -> bool:
    return admin or bool(
        workspace.snakepay_recipient_id
        or (workspace.snakepay_api_key_encrypted and workspace.snakepay_webhook_secret_encrypted)
    )


async def _priority(db, workspace, catalog: list[dict], admin: bool) -> list[dict]:
    """Principal and backups of the operation's own funnels, with each gateway's status.
    With nothing saved yet it shows what already happens: the chosen gateway, and SmokePay
    behind SnakePay."""
    rows = await gateways.gateway_settings(db, workspace.id)
    if rows:
        items = [{"gateway": r.gateway, "enabled": r.enabled, "flow_ids": r.flow_ids} for r in rows]
        for name in gateways.GATEWAYS:
            if name not in {r.gateway for r in rows}:
                items.append({"gateway": name, "enabled": False, "flow_ids": None})
    elif not admin:
        automatic = await gateways.automatic_order(db)
        items = [{"gateway": name, "enabled": True, "flow_ids": None} for name in automatic]
        items += [{"gateway": name, "enabled": False, "flow_ids": None} for name in gateways.GATEWAYS if name not in automatic]
    else:
        first = workspace.payment_gateway if workspace.payment_gateway in gateways.GATEWAYS else "smokepay"
        items = [{"gateway": first, "enabled": True, "flow_ids": None}]
        for name in gateways.GATEWAYS:
            if name != first:
                items.append({"gateway": name, "enabled": first == "snakepay" and name == "smokepay", "flow_ids": None})
    available = {g["id"]: g["available"] for g in catalog}
    paused = engine.snakepay_paused(workspace.id)
    out = []
    for index, item in enumerate(items, start=1):
        name = item["gateway"]
        if not available.get(name):
            status = "indisponivel"
        elif name == "snakepay" and not _snake_ready(workspace, admin):
            status = "configurar"
        elif name == "snakepay" and paused:
            status = "pausado"
        else:
            status = "ativo" if item["enabled"] else "desligado"
        out.append({
            "gateway": name, "enabled": item["enabled"], "priority": index,
            "flow_ids": [str(v) for v in item["flow_ids"]] if item["flow_ids"] is not None else None, "status": status,
        })
    return out


@router.put("/priority", dependencies=[Depends(require_csrf)])
async def save_priority(payload: PriorityRequest, access: OwnerAccess, user: AuthenticatedUser, db: DbSession) -> dict:
    """Order, on/off and funnel association of the operation's gateways. Shared funnels are
    not touched: they always follow their owner's rules."""
    workspace = access.workspace
    admin = user.platform_role == "SUPER_ADMIN"
    names = [item.gateway for item in payload.items]
    if len(set(names)) != len(names):
        raise HTTPException(status_code=422, detail="Cada gateway aparece uma vez só.")
    if not any(item.enabled and item.flow_ids is None for item in payload.items):
        raise HTTPException(
            status_code=422, detail="Deixe pelo menos um gateway ligado para todos os funis, para nenhuma venda ficar sem Pix."
        )
    own = set(await db.scalars(select(TgFlow.id).where(TgFlow.workspace_id == workspace.id)))
    for item in payload.items:
        if item.flow_ids is not None:
            if not item.flow_ids:
                raise HTTPException(status_code=422, detail="Escolha pelo menos um funil ou deixe para todos.")
            if not set(item.flow_ids) <= own:
                raise HTTPException(status_code=422, detail="Associe só funis próprios desta operação.")
        if item.enabled and item.gateway == "snakepay":
            if not await gateways.snakepay_available(db):
                raise HTTPException(status_code=409, detail="A SnakePay ainda não foi liberada pelo administrador.")
            if not _snake_ready(workspace, admin):
                raise HTTPException(status_code=422, detail="Configure a SnakePay (ShopID ou credenciais) antes de ligá-la.")
        if item.enabled and item.gateway == "atenaspay" and not await gateways.atenaspay_available(db):
            raise HTTPException(status_code=409, detail="A Athenas Pay ainda não foi liberada pelo administrador.")
        if item.enabled and item.gateway == "smokepay" and not _smokepay_configured():
            raise HTTPException(status_code=409, detail="A SmokePay não está configurada no servidor.")
    before = await _priority(db, workspace, (await _state_catalog(db)), admin)
    current = {row.gateway: row for row in await gateways.gateway_settings(db, workspace.id)}
    for index, item in enumerate(payload.items, start=1):
        row = current.get(item.gateway)
        if row is None:
            row = TgGatewaySetting(workspace_id=workspace.id, gateway=item.gateway)
            db.add(row)
        row.enabled = item.enabled
        row.priority = index
        row.flow_ids = sorted(str(v) for v in item.flow_ids) if item.flow_ids is not None else None
    principal = next(item.gateway for item in payload.items if item.enabled and item.flow_ids is None)
    workspace.payment_gateway = principal  # the legacy default follows the principal
    await db.flush()
    audit(
        db, actor=user, workspace_id=workspace.id, action="gateways.priority", entity="workspace", entity_id=workspace.id,
        details={
            "before": [{k: v for k, v in i.items() if k != "status"} for i in before],
            "after": [{"gateway": i.gateway, "enabled": i.enabled, "flow_ids": [str(v) for v in i.flow_ids] if i.flow_ids is not None else None} for i in payload.items],
        },
    )
    await db.commit()
    engine.resume_snakepay()
    return await _state(db, user, workspace)


async def _state_catalog(db) -> list[dict]:
    enabled = await gateways.snakepay_enabled(db)
    return [
        {"id": "smokepay", "available": _smokepay_configured()},
        {"id": "snakepay", "available": snakepay.configured() and enabled},
        {"id": "atenaspay", "available": atenaspay.configured() and await gateways.atenaspay_enabled(db)},
    ]


async def _shared_flows(db, workspace) -> list[dict]:
    """Funnels shared by a chief that this operation's bots run: they charge with the
    gateway the chief picked for them, not with this operation's choice."""
    # DISTINCT on ids only: Postgres cannot compare the funnels' json definition
    flow_ids = list(await db.scalars(
        select(TgBot.flow_id).where(TgBot.workspace_id == workspace.id, TgBot.flow_id.is_not(None)).distinct()
    ))
    shared = []
    for flow_id in flow_ids:
        flow = await db.get(TgFlow, flow_id)
        if flow is None:
            continue
        source = flow
        if flow.workspace_id == workspace.id and flow.template_flow_id is not None:
            source = await db.get(TgFlow, flow.template_flow_id) or flow
        if source.workspace_id == workspace.id:
            continue
        rule = await active_share(db, flow, workspace.id)
        shared.append({
            "name": flow.name, "gateway": await gateways.gateway_choice(db, workspace, flow),
            # read-only: the owner's rules for this partner (the seller sets nothing here)
            "set_by_owner": rule is not None,
            "seller_percent": float(rule.seller_percent) if rule else None,
            "owner_percent": float(rule.owner_percent) if rule else None,
            "shop_id_ready": bool(rule and rule.gateway == "snakepay" and gateways.valid_recipient(rule.seller_shop_id or "")),
        })
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
        .where((TgFlow.id.in_(list(own))) | (TgFlow.template_flow_id.in_(list(own))))
    )
    names: list[str] = []
    for partner_ws_id, flow in rows.all():
        partner_ws = await db.get(Workspace, partner_ws_id)
        if partner_ws is None or (
            partner_ws.snakepay_api_key_encrypted and partner_ws.snakepay_webhook_secret_encrypted
        ) or gateways.valid_recipient(partner_ws.snakepay_recipient_id or ""):
            continue
        rule = await active_share(db, flow, partner_ws.id)
        if rule is not None:
            continue  # the share's own ShopIDs were validated when the owner saved it
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
        if user.platform_role != "SUPER_ADMIN" and recipient is None and not (
            workspace.snakepay_api_key_encrypted and workspace.snakepay_webhook_secret_encrypted
        ):
            raise HTTPException(status_code=422, detail="Cole o seu ShopID da SnakePay para receber suas vendas.")
    if payload.gateway == "atenaspay" and not await gateways.atenaspay_available(db):
        raise HTTPException(status_code=409, detail="A Athenas Pay ainda não foi liberada pelo administrador.")
    workspace.payment_gateway = payload.gateway
    workspace.snakepay_recipient_id = recipient
    rows = await gateways.gateway_settings(db, workspace.id)
    if rows:  # the chosen gateway becomes the principal; the others keep their order as backups
        rows.sort(key=lambda row: (row.gateway != payload.gateway, row.priority))
        for index, row in enumerate(rows, start=1):
            row.priority = index
        rows[0].enabled, rows[0].flow_ids = True, None
    if payload.apply_to_all:
        await db.execute(update(TgFlow).where(TgFlow.workspace_id == workspace.id).values(payment_gateway=None))
    await db.commit()
    engine.resume_snakepay()  # a new ShopID/choice gets a fresh try right away
    return await _state(db, user, workspace)


@router.put("/snakepay/credentials", dependencies=[Depends(require_csrf)])
async def save_snakepay_credentials(
    payload: SnakepayCredentials, access: OwnerAccess, user: AuthenticatedUser, db: DbSession
) -> dict:
    if user.platform_role == "SUPER_ADMIN":
        raise HTTPException(status_code=403, detail="Use a configuração de servidor da SnakePay.")
    workspace = access.workspace
    if payload.clear:
        if payload.api_key or payload.webhook_secret or payload.cashout_secret:
            raise HTTPException(status_code=422, detail="Não envie credenciais junto com a solicitação para remover.")
        workspace.snakepay_api_key_encrypted = None
        workspace.snakepay_webhook_secret_encrypted = None
        workspace.snakepay_cashout_secret_encrypted = None
    else:
        api_key = payload.api_key.strip() if payload.api_key and payload.api_key.strip() else None
        webhook_secret = payload.webhook_secret.strip() if payload.webhook_secret and payload.webhook_secret.strip() else None
        cashout_secret = payload.cashout_secret.strip() if payload.cashout_secret and payload.cashout_secret.strip() else None
        if api_key is None and webhook_secret is None and cashout_secret is None:
            raise HTTPException(status_code=422, detail="Informe a chave API, o segredo de webhook ou o segredo de saque.")
        if not (workspace.snakepay_api_key_encrypted or api_key) or not (
            workspace.snakepay_webhook_secret_encrypted or webhook_secret
        ):
            raise HTTPException(status_code=422, detail="Configure a chave API e o segredo de webhook da sua conta.")
        try:
            if api_key:
                workspace.snakepay_api_key_encrypted = encrypt_value(api_key)
            if webhook_secret:
                workspace.snakepay_webhook_secret_encrypted = encrypt_value(webhook_secret)
            if cashout_secret:
                workspace.snakepay_cashout_secret_encrypted = encrypt_value(cashout_secret)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail="A criptografia de credenciais não está configurada.") from exc
    audit(
        db, actor=user, workspace_id=workspace.id, action="gateways.credentials", entity="workspace",
        entity_id=workspace.id, details={"gateway": "snakepay", "cleared": payload.clear},  # never the values
    )
    await db.commit()
    engine.resume_snakepay()
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
        if user.platform_role != "SUPER_ADMIN" and not (
            workspace.snakepay_recipient_id
            or (workspace.snakepay_api_key_encrypted and workspace.snakepay_webhook_secret_encrypted)
        ):
            raise HTTPException(status_code=422, detail="Cadastre o seu ShopID da SnakePay antes de usar a SnakePay num fluxo.")
    if payload.gateway == "atenaspay" and not await gateways.atenaspay_available(db):
        raise HTTPException(status_code=409, detail="A Athenas Pay ainda não foi liberada pelo administrador.")
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


@router.put("/atenaspay/enabled", dependencies=[Depends(require_csrf)])
async def switch_atenaspay(payload: AtenaspaySwitch, user: SuperAdminUser, db: DbSession) -> dict:
    if payload.enabled and not atenaspay.configured():
        raise HTTPException(
            status_code=409,
            detail="Configure ATENASPAY_API_KEY e ATENASPAY_WEBHOOK_SECRET no servidor antes de liberar a Athenas Pay.",
        )
    row = await db.get(SystemSetting, gateways.ATENASPAY_ENABLED_KEY)
    if row is None:
        db.add(
            SystemSetting(
                key=gateways.ATENASPAY_ENABLED_KEY,
                value={"enabled": payload.enabled},
                updated_by_user_id=user.id,
            )
        )
    else:
        row.value = {"enabled": payload.enabled}
        row.updated_by_user_id = user.id
    await db.commit()
    return {"enabled": payload.enabled}
