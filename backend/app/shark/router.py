import hashlib
import json
import logging
import secrets
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.auth.dependencies import DbSession, OwnerAccess, require_csrf
from app.core.config import get_settings
from app.models import InstagramAccount, SharkEvent, Workspace

router = APIRouter(prefix="/api/sharkbot", tags=["Sharkbot"])
logger = logging.getLogger(__name__)

_EVENT_TYPE_ALIASES = {
    "lead": "lead_initiated",
    "novo_lead": "lead_initiated",
    "new_lead": "lead_initiated",
    "lead_iniciado": "lead_initiated",
    "user_joined": "lead_initiated",
    "user_join": "lead_initiated",
    "clique": "link_click",
    "link_click": "link_click",
    "click": "link_click",
    "link_clicked": "link_click",
    "pagamento_criado": "pix_generated",
    "payment_created": "pix_generated",
    "pix_created": "pix_generated",
    "pix_gerado": "pix_generated",
    "pix_gerado_com_sucesso": "pix_generated",
    "pix": "pix_generated",
    "pagamento_aprovado": "pix_paid",
    "payment_approved": "pix_paid",
    "payment_paid": "pix_paid",
    "paid": "pix_paid",
    "pix_pago": "pix_paid",
    "pix_pendente": "pix_pending",
    "payment_pending": "pix_pending",
}
_SUPPORTED_EVENTS = frozenset(_EVENT_TYPE_ALIASES.values())
_MAX_WEBHOOK_BYTES = 1_048_576


class SharkbotWebhookSettings(BaseModel):
    webhook_url: str


class SharkbotWebhookResponse(BaseModel):
    accepted: int
    duplicates: int


def _normalize_event_type(value: object) -> str:
    normalized = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    return _EVENT_TYPE_ALIASES.get(normalized, normalized)


def _event_batches(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    if isinstance(payload.get("data"), dict):
        data = payload["data"]
        return [{
            **payload,
            **data,
            "data": data,
            "event": (
                payload.get("event")
                or payload.get("event_type")
                or payload.get("event_name")
                or data.get("event")
                or data.get("event_type")
            ),
        }]
    if isinstance(payload.get("payload"), dict):
        nested = payload["payload"]
        return [{
            **payload,
            **nested,
            "event": (
                payload.get("event")
                or payload.get("event_type")
                or nested.get("event")
                or nested.get("event_type")
            ),
        }]
    if any(payload.get(key) for key in ("event", "event_type", "event_name", "type", "name")):
        return [payload]

    batches: list[dict[str, Any]] = []
    entries = payload.get("entry")
    if isinstance(entries, list):
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            for event in entry.get("messaging", []):
                if isinstance(event, dict):
                    batches.append({"entry_id": entry.get("id"), **event})
            for change in entry.get("changes", []):
                if isinstance(change, dict):
                    value = change.get("value")
                    batches.append({
                        "entry_id": entry.get("id"),
                        **(value if isinstance(value, dict) else change),
                    })
    return batches


def _event_source_key(event: dict[str, Any], event_type: str) -> str:
    data = event.get("data")
    value = data if isinstance(data, dict) else event
    transaction = value.get("transaction")
    transaction = transaction if isinstance(transaction, dict) else {}
    transaction_id = transaction.get("id") or transaction.get("external_id")
    explicit_id = event.get("webhook_id") or event.get("id")
    if explicit_id:
        material: Any = {
            "webhook_id": str(explicit_id),
            "event_type": event_type,
            "transaction_id": str(transaction_id) if transaction_id else None,
            "timestamp": event.get("timestamp") or value.get("timestamp"),
        }
    else:
        material = {"event_type": event_type, "event": event}
    serialized = json.dumps(
        material, sort_keys=True, ensure_ascii=False, default=str
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def _event_timestamp(event: dict[str, Any], value: dict[str, Any]) -> datetime:
    raw_timestamp = event.get("timestamp", value.get("timestamp"))
    if isinstance(raw_timestamp, (int, float)) and not isinstance(raw_timestamp, bool):
        return datetime.fromtimestamp(raw_timestamp, tz=timezone.utc)
    if isinstance(raw_timestamp, str):
        try:
            parsed = datetime.fromisoformat(raw_timestamp.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            logger.warning("Sharkbot sent an invalid event timestamp.")
    return datetime.now(timezone.utc)


def _event_amount(value: dict[str, Any], transaction: dict[str, Any]) -> Decimal:
    raw_amount = value.get(
        "value",
        value.get("amount", value.get("price", transaction.get("amount", 0))),
    )
    try:
        amount = Decimal(str(raw_amount or 0)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Sharkbot event amount must be a valid number.",
        ) from None
    if not amount.is_finite() or amount < 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Sharkbot event amount must be a non-negative number.",
        )
    return amount


async def _event_account(
    workspace_id: UUID,
    event: dict[str, Any],
    value: dict[str, Any],
    db: DbSession,
) -> InstagramAccount | None:
    recipient = value.get("recipient")
    recipient_id = recipient.get("id") if isinstance(recipient, dict) else None
    raw_id = (
        value.get("account_id")
        or value.get("instagram_user_id")
        or event.get("entry_id")
        or recipient_id
    )
    if raw_id is None:
        return None
    query = select(InstagramAccount).where(
        InstagramAccount.workspace_id == workspace_id
    )
    try:
        account_id = UUID(str(raw_id))
    except (ValueError, TypeError):
        query = query.where(InstagramAccount.instagram_user_id == str(raw_id))
    else:
        query = query.where(
            (InstagramAccount.id == account_id)
            | (InstagramAccount.instagram_user_id == str(raw_id))
        )
    return await db.scalar(query)


@router.get("/webhook/config", response_model=SharkbotWebhookSettings)
async def get_webhook_settings(
    access: OwnerAccess,
    db: DbSession,
) -> SharkbotWebhookSettings:
    workspace = await db.get(Workspace, access.workspace.id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found.")
    if not workspace.sharkbot_webhook_token:
        workspace.sharkbot_webhook_token = secrets.token_urlsafe(32)
        await db.commit()
    base_url = get_settings().public_base_url.rstrip("/")
    return SharkbotWebhookSettings(
        webhook_url=(
            f"{base_url}/api/sharkbot/webhook/"
            f"{workspace.sharkbot_webhook_token}"
        )
    )


@router.post(
    "/webhook/rotate",
    response_model=SharkbotWebhookSettings,
    dependencies=[Depends(require_csrf)],
)
async def rotate_webhook_settings(
    access: OwnerAccess,
    db: DbSession,
) -> SharkbotWebhookSettings:
    workspace = await db.get(Workspace, access.workspace.id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found.")
    workspace.sharkbot_webhook_token = secrets.token_urlsafe(32)
    await db.commit()
    base_url = get_settings().public_base_url.rstrip("/")
    return SharkbotWebhookSettings(
        webhook_url=(
            f"{base_url}/api/sharkbot/webhook/"
            f"{workspace.sharkbot_webhook_token}"
        )
    )


@router.post(
    "/webhook/{webhook_token}",
    response_model=SharkbotWebhookResponse,
)
async def receive_sharkbot_webhook(
    webhook_token: str,
    request: Request,
    db: DbSession,
) -> SharkbotWebhookResponse:
    chunks: list[bytes] = []
    content_size = 0
    async for chunk in request.stream():
        content_size += len(chunk)
        if content_size > _MAX_WEBHOOK_BYTES:
            raise HTTPException(status_code=413, detail="Sharkbot payload is too large.")
        chunks.append(chunk)
    try:
        payload = json.loads(b"".join(chunks))
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(status_code=400, detail="Sharkbot payload must be valid JSON.") from None
    if not isinstance(payload, (dict, list)):
        raise HTTPException(
            status_code=400,
            detail="Sharkbot payload must be a JSON object or event list.",
        )
    events = _event_batches(payload)
    if not events:
        raise HTTPException(status_code=422, detail="No recognizable Sharkbot events found.")

    workspace = await db.scalar(
        select(Workspace).where(Workspace.sharkbot_webhook_token == webhook_token)
    )
    if workspace is None:
        raise HTTPException(status_code=404, detail="Sharkbot webhook not found.")

    accepted = 0
    duplicates = 0
    for event in events:
        nested_data = event.get("data")
        value = nested_data if isinstance(nested_data, dict) else event
        event_type = _normalize_event_type(
            event.get("event")
            or event.get("event_type")
            or event.get("event_name")
            or value.get("event_type")
            or value.get("event_name")
            or value.get("type")
            or value.get("name")
        )
        if event_type not in _SUPPORTED_EVENTS:
            continue
        transaction = value.get("transaction")
        transaction = transaction if isinstance(transaction, dict) else {}
        customer = value.get("customer")
        customer = customer if isinstance(customer, dict) else {}
        bot = value.get("bot")
        bot = bot if isinstance(bot, dict) else {}
        first_name = customer.get("first_name")
        last_name = customer.get("last_name")
        customer_name = " ".join(
            str(part).strip() for part in (first_name, last_name) if part
        ) or None
        webhook_id = event.get("webhook_id")
        transaction_id = transaction.get("id") or transaction.get("external_id")
        source_key = _event_source_key(event, event_type)
        account = await _event_account(workspace.id, event, value, db)
        row = SharkEvent(
            workspace_id=workspace.id,
            account_id=account.id if account else None,
            event_type=event_type,
            source_event_key=source_key,
            webhook_id=str(webhook_id)[:160] if webhook_id is not None else None,
            transaction_id=str(transaction_id)[:160] if transaction_id is not None else None,
            customer_name=customer_name[:240] if customer_name else None,
            customer_username=(
                str(customer["username"])[:120] if customer.get("username") else None
            ),
            bot_name=str(bot["name"])[:160] if bot.get("name") else None,
            plan_name=(
                str(transaction["plan_name"])[:160]
                if transaction.get("plan_name")
                else None
            ),
            amount=_event_amount(value, transaction),
            occurred_at=_event_timestamp(event, value),
        )
        try:
            async with db.begin_nested():
                db.add(row)
                await db.flush()
        except IntegrityError:
            duplicates += 1
        else:
            accepted += 1

    if accepted == 0 and duplicates == 0:
        raise HTTPException(
            status_code=422,
            detail="Payload contains no supported Sharkbot event types.",
        )
    await db.commit()
    return SharkbotWebhookResponse(accepted=accepted, duplicates=duplicates)
