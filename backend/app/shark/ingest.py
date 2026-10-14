"""SharkBot webhook ingestion: events -> one lead / one transaction each.

What the integration can rely on (from the payloads SharkBot sends):
- ``event``: user_joined (lead), payment_created (PIX generated, pending),
  payment_approved (paid). ``timestamp`` is a unix time.
- ``webhook_id`` is NOT an event id: the same value appears in different
  events, so it is never used for de-duplication.
- Leads are identified by ``data.bot.id`` + ``data.customer.id`` (falling
  back to ``customer.telegram_id``); payments by ``data.transaction.id``
  (falling back to ``external_id``).
- There is no signature/HMAC in the payload; authenticity comes from the
  secret token in the webhook URL.
- No Instagram account id is sent. A sale is only attributed to an account
  when the owner configured the per-account webhook URL (``?account=``).

Guarantees:
- Re-deliveries never create a second lead, transaction or revenue.
- A paid transaction never goes back to pending, whatever the order.
- PIX generated is counted when generated; revenue only when paid.
- Missing amounts stay NULL (shown as unavailable, never as R$ 0).
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import APP_TIME_ZONE
from app.models import SharkEvent, SharkLead, SharkTransaction

logger = logging.getLogger(__name__)

EVENT_TYPE_ALIASES = {
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
SUPPORTED_EVENTS = frozenset(EVENT_TYPE_ALIASES.values())
_PAYMENT_EVENTS = frozenset({"pix_generated", "pix_pending", "pix_paid"})
_PAID_STATUSES = frozenset({"paid", "approved", "aprovado", "pago", "completed", "confirmed"})


def normalize_event_type(value: object) -> str:
    normalized = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    return EVENT_TYPE_ALIASES.get(normalized, normalized)


def event_batches(payload: Any) -> list[dict[str, Any]]:
    """Flatten a delivery (object or list) into individual events."""
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
    return []


def _text(value: object, limit: int) -> str | None:
    if value is None or isinstance(value, (dict, list)):
        return None
    text = str(value).strip()
    return text[:limit] if text else None


def _dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def parse_datetime(value: object) -> datetime | None:
    """Unix seconds/ms or ISO-8601. Naive ISO times are app local time."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        seconds = value / 1000 if value > 10_000_000_000 else value
        try:
            return datetime.fromtimestamp(seconds, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str) and value.strip():
        raw = value.strip()
        if raw.isdigit():
            return parse_datetime(int(raw))
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=APP_TIME_ZONE)
        return parsed.astimezone(timezone.utc)
    return None


def parse_amount(*candidates: object) -> Decimal | None:
    for raw in candidates:
        if raw is None or isinstance(raw, (bool, dict, list)):
            continue
        try:
            amount = Decimal(str(raw).strip().replace(",", ".")).quantize(Decimal("0.01"))
        except (InvalidOperation, ValueError):
            continue
        if amount.is_finite() and amount >= 0:
            return amount
    return None


@dataclass
class ParsedEvent:
    event_type: str
    raw: dict[str, Any]
    occurred_at: datetime | None
    bot_id: str | None
    bot_name: str | None
    flow_id: str | None
    flow_name: str | None
    customer_id: str | None
    telegram_id: str | None
    customer_name: str | None
    customer_username: str | None
    utm_source: str | None
    utm_campaign: str | None
    lead_key: str
    # payment fields
    transaction_key: str | None = None
    transaction_id: str | None = None
    external_id: str | None = None
    paid: bool = False
    amount: Decimal | None = None
    currency: str | None = None
    gateway: str | None = None
    payment_method: str | None = None
    plan_name: str | None = None
    sales_code: str | None = None
    created_at: datetime | None = None
    paid_at: datetime | None = None
    joined_at: datetime | None = None


def _hash(material: object) -> str:
    return hashlib.sha256(
        json.dumps(material, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    ).hexdigest()


def parse_event(event: dict[str, Any]) -> ParsedEvent | None:
    data = _dict(event.get("data")) or event
    event_type = normalize_event_type(
        event.get("event")
        or event.get("event_type")
        or event.get("event_name")
        or data.get("event_type")
        or data.get("event_name")
        or data.get("type")
        or data.get("name")
    )
    if event_type not in SUPPORTED_EVENTS:
        return None
    customer = _dict(data.get("customer"))
    bot = _dict(data.get("bot"))
    flow = _dict(data.get("flow"))
    tracking = _dict(data.get("tracking"))
    transaction = _dict(data.get("transaction"))
    occurred_at = parse_datetime(event.get("timestamp", data.get("timestamp")))
    customer_name = " ".join(
        str(part).strip() for part in (customer.get("first_name"), customer.get("last_name")) if part
    ) or None
    bot_id = _text(bot.get("id"), 120)
    customer_id = _text(customer.get("id"), 120)
    telegram_id = _text(customer.get("telegram_id"), 64)
    if customer_id:
        lead_key = f"bot:{bot_id or '-'}|cust:{customer_id}"
    elif telegram_id:
        lead_key = f"bot:{bot_id or '-'}|tg:{telegram_id}"
    else:
        # No identity at all: only an identical re-delivery can be recognised.
        lead_key = f"evt:{_hash({k: v for k, v in event.items() if k != 'webhook_id'})}"
    parsed = ParsedEvent(
        event_type=event_type,
        raw=event,
        occurred_at=occurred_at,
        bot_id=bot_id,
        bot_name=_text(bot.get("name") or bot.get("username"), 160),
        flow_id=_text(flow.get("id"), 120),
        flow_name=_text(flow.get("name"), 160),
        customer_id=customer_id,
        telegram_id=telegram_id,
        customer_name=customer_name[:240] if customer_name else None,
        customer_username=_text(customer.get("username"), 120),
        utm_source=_text(tracking.get("utm_source"), 120),
        utm_campaign=_text(tracking.get("utm_campaign"), 160),
        lead_key=lead_key[:240],
        joined_at=parse_datetime(data.get("joined_at")) or occurred_at,
    )
    if event_type in _PAYMENT_EVENTS:
        transaction_id = _text(transaction.get("id"), 160)
        external_id = _text(transaction.get("external_id"), 160)
        if transaction_id:
            parsed.transaction_key = f"tx:{transaction_id}"
        elif external_id:
            parsed.transaction_key = f"ext:{external_id}"
        else:
            parsed.transaction_key = f"evt:{_hash({k: v for k, v in event.items() if k != 'webhook_id'})}"
        parsed.transaction_id = transaction_id
        parsed.external_id = external_id
        status_text = str(transaction.get("status") or "").strip().lower()
        parsed.paid = event_type == "pix_paid" or status_text in _PAID_STATUSES
        parsed.amount = parse_amount(
            transaction.get("amount"), data.get("amount"), data.get("value"), data.get("price")
        )
        parsed.currency = _text(transaction.get("currency"), 8)
        parsed.gateway = _text(transaction.get("gateway"), 60)
        parsed.payment_method = _text(transaction.get("payment_method"), 40)
        parsed.plan_name = _text(transaction.get("plan_name"), 160)
        parsed.sales_code = _text(transaction.get("sales_code"), 120)
        parsed.created_at = parse_datetime(transaction.get("created_at"))
        parsed.paid_at = parse_datetime(transaction.get("paid_at"))
        if parsed.paid and parsed.paid_at is None:
            parsed.paid_at = occurred_at
        if parsed.created_at is None and not parsed.paid:
            parsed.created_at = occurred_at
    return parsed


def _fill(target, field: str, value) -> bool:
    if value is not None and getattr(target, field) in (None, ""):
        setattr(target, field, value)
        return True
    return False


async def upsert_lead(
    db: AsyncSession, workspace_id: UUID, event: ParsedEvent, account_id: UUID | None, now: datetime
) -> bool:
    """Returns True when the lead is new."""
    lead = await db.scalar(
        select(SharkLead).where(SharkLead.workspace_id == workspace_id, SharkLead.lead_key == event.lead_key)
    )
    if lead is None:
        candidate = SharkLead(
            workspace_id=workspace_id,
            lead_key=event.lead_key,
            bot_id=event.bot_id,
            bot_name=event.bot_name,
            flow_id=event.flow_id,
            flow_name=event.flow_name,
            customer_id=event.customer_id,
            telegram_id=event.telegram_id,
            customer_name=event.customer_name,
            customer_username=event.customer_username,
            account_id=account_id,
            utm_source=event.utm_source,
            utm_campaign=event.utm_campaign,
            joined_at=event.joined_at or now,
            first_received_at=now,
            last_received_at=now,
        )
        try:
            async with db.begin_nested():
                db.add(candidate)
                await db.flush()
            return True
        except IntegrityError:
            lead = await db.scalar(
                select(SharkLead).where(
                    SharkLead.workspace_id == workspace_id, SharkLead.lead_key == event.lead_key
                )
            )
            if lead is None:  # pragma: no cover - defensive
                raise
    lead.last_received_at = now
    # Earliest known join time wins (re-deliveries may carry a later timestamp).
    if event.joined_at is not None and event.joined_at < _aware(lead.joined_at):
        lead.joined_at = event.joined_at
    for field in ("bot_name", "flow_id", "flow_name", "customer_name", "customer_username",
                  "utm_source", "utm_campaign", "telegram_id"):
        _fill(lead, field, getattr(event, field))
    _fill(lead, "account_id", account_id)
    return False


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


async def upsert_transaction(
    db: AsyncSession, workspace_id: UUID, event: ParsedEvent, account_id: UUID | None, now: datetime
) -> bool:
    """Create or advance a payment. Returns True when something changed
    (new transaction or pending -> paid); False for a pure re-delivery."""
    assert event.transaction_key is not None
    query = select(SharkTransaction).where(
        SharkTransaction.workspace_id == workspace_id,
        SharkTransaction.transaction_key == event.transaction_key,
    ).with_for_update()
    transaction = await db.scalar(query)
    if transaction is None:
        candidate = SharkTransaction(
            workspace_id=workspace_id,
            transaction_key=event.transaction_key,
            transaction_id=event.transaction_id,
            external_id=event.external_id,
            status="paid" if event.paid else "pending",
            amount=event.amount,
            currency=event.currency,
            gateway=event.gateway,
            payment_method=event.payment_method,
            plan_name=event.plan_name,
            sales_code=event.sales_code,
            bot_id=event.bot_id,
            bot_name=event.bot_name,
            flow_id=event.flow_id,
            flow_name=event.flow_name,
            customer_id=event.customer_id,
            customer_name=event.customer_name,
            customer_username=event.customer_username,
            lead_key=event.lead_key if not event.lead_key.startswith("evt:") else None,
            account_id=account_id,
            utm_source=event.utm_source,
            utm_campaign=event.utm_campaign,
            created_at_source=event.created_at or event.paid_at or event.occurred_at or now,
            paid_at=(event.paid_at or event.occurred_at or now) if event.paid else None,
            first_received_at=now,
        )
        try:
            async with db.begin_nested():
                db.add(candidate)
                await db.flush()
            return True
        except IntegrityError:
            transaction = await db.scalar(query)
            if transaction is None:  # pragma: no cover - defensive
                raise
    changed = False
    if event.paid and transaction.status != "paid":
        transaction.status = "paid"
        transaction.paid_at = event.paid_at or event.occurred_at or now
        changed = True
    elif event.paid and event.paid_at is not None and transaction.paid_at is not None:
        # Keep the earliest confirmed approval time across re-deliveries.
        if event.paid_at < _aware(transaction.paid_at):
            transaction.paid_at = event.paid_at
    # A pending event never downgrades a paid transaction (out-of-order safe).
    if event.created_at is not None and event.created_at < _aware(transaction.created_at_source):
        transaction.created_at_source = event.created_at
    if event.amount is not None and (event.paid or transaction.amount is None):
        transaction.amount = event.amount
    for field in ("transaction_id", "external_id", "currency", "gateway", "payment_method",
                  "plan_name", "sales_code", "bot_id", "bot_name", "flow_id", "flow_name",
                  "customer_id", "customer_name", "customer_username", "utm_source", "utm_campaign"):
        _fill(transaction, field, getattr(event, field))
    if not event.lead_key.startswith("evt:"):
        _fill(transaction, "lead_key", event.lead_key)
    _fill(transaction, "account_id", account_id)
    return changed


async def log_event(
    db: AsyncSession, workspace_id: UUID, event: ParsedEvent, account_id: UUID | None
) -> None:
    """Raw audit log; identical re-deliveries are stored once."""
    entity = event.transaction_key or event.lead_key
    status = "paid" if event.paid else event.event_type
    source_key = _hash({"event_type": event.event_type, "entity": entity, "status": status})
    row = SharkEvent(
        workspace_id=workspace_id,
        account_id=account_id,
        event_type=event.event_type,
        source_event_key=source_key,
        webhook_id=_text(event.raw.get("webhook_id"), 160),
        transaction_id=event.transaction_id or event.external_id,
        customer_name=event.customer_name,
        customer_username=event.customer_username,
        bot_name=event.bot_name,
        plan_name=event.plan_name,
        amount=event.amount if event.amount is not None else Decimal("0.00"),
        occurred_at=event.paid_at or event.created_at or event.joined_at or event.occurred_at
        or datetime.now(timezone.utc),
    )
    try:
        async with db.begin_nested():
            db.add(row)
            await db.flush()
    except IntegrityError:
        pass
