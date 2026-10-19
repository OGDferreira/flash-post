"""FlashBot > Gateways: each operation picks the PIX gateway of its bots; the Super Admin
turns SnakePay on once its key and webhook secret are set on the server."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth.dependencies import AuthenticatedUser, DbSession, OwnerAccess, SuperAdminUser, require_csrf
from app.bots import gateways, snakepay
from app.core.config import get_settings
from app.models import SystemSetting

router = APIRouter(prefix="/api/payment-gateways", tags=["Payment gateways"])


class GatewayChoice(BaseModel):
    gateway: str = Field(pattern="^(smokepay|snakepay)$")
    snakepay_recipient_id: str | None = Field(default=None, max_length=64)


class SnakepaySwitch(BaseModel):
    enabled: bool


def _smokepay_configured() -> bool:
    key = get_settings().smokepay_api_key
    return bool(key and key.get_secret_value().strip())


async def _state(db, user, workspace) -> dict:
    admin = user.platform_role == "SUPER_ADMIN"
    enabled = await gateways.snakepay_enabled(db)
    state = {
        "current": workspace.payment_gateway if workspace.payment_gateway in gateways.GATEWAYS else "smokepay",
        "snakepay_recipient_id": workspace.snakepay_recipient_id,
        "is_admin": admin,
        # The platform's own sales need no recipient: everything stays in its account.
        "needs_recipient": not admin,
        "gateways": [
            {
                "id": "smokepay", "name": "SmokePay", "available": _smokepay_configured(),
                "fee": "Taxa da SmokePay", "description": "Pix com subconta própria e saque pelo FlashPost.",
            },
            {
                "id": "snakepay", "name": "SnakePay", "available": snakepay.configured() and enabled,
                "fee": "3% + R$ 0,25 por venda",
                "description": "Pix com repasse automático (split) para a sua conta SnakePay.",
            },
        ],
    }
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
            detail="ID do recebedor inválido. Copie o identificador em SnakePay → Conta → Split (formato 8-4-4-4-12).",
        )
    if payload.gateway == "snakepay":
        if not await gateways.snakepay_available(db):
            raise HTTPException(status_code=409, detail="A SnakePay ainda não foi liberada pelo administrador.")
        if user.platform_role != "SUPER_ADMIN" and recipient is None:
            raise HTTPException(status_code=422, detail="Cole o ID do recebedor da sua conta SnakePay para receber suas vendas.")
    workspace.payment_gateway = payload.gateway
    workspace.snakepay_recipient_id = recipient
    await db.commit()
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
    return {"enabled": payload.enabled}

