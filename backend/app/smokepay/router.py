import hashlib
import hmac
import json
import logging
import secrets
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.auth.dependencies import DbSession, OwnerAccess, require_csrf
from app.core.config import get_settings
from app.core.crypto import decrypt_value, encrypt_value
from app.core.time import BRAZIL_TIME_ZONE, local_day_bounds_utc, utc_now
from app.models import SharkEvent, SmokepayOperation
from app.models import Workspace
from app.schemas.smokepay import (
    SmokepayDailyGoalUpdate,
    SmokepayFinanceSummary,
    SmokepayOperationCreate,
    SmokepayOperationRevenue,
    SmokepayOperationResponse,
    SmokepayOperationUpdate,
    SmokepayOperationsResponse,
    SmokepaySaleItem,
    SmokepayWebhookResult,
)

router = APIRouter(tags=["Smokepay"])
logger = logging.getLogger(__name__)
MAX_WEBHOOK_BYTES = 1_048_576
APPROVED_EVENTS = {
    "approved",
    "sale_approved",
    "payment_approved",
    "transaction_approved",
    "order_approved",
    "payment_paid",
    "pix_paid",
    "pix_pago",
    "pagamento_aprovado",
    "paid",
    "success",
}


def _normalize(value: object) -> str:
    return str(value or "").strip().casefold().replace(".", "_").replace("-", "_").replace(" ", "_")


def _event_list(payload: object) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("data", "payload", "event_data"):
        nested = payload.get(key)
        if isinstance(nested, dict):
            event = {**payload, **nested}
            event["data"] = nested
            return [event]
        if isinstance(nested, list):
            return [item for item in nested if isinstance(item, dict)]
    return [payload]


def _event_value(event: dict[str, Any]) -> dict[str, Any]:
    for key in ("data", "payload", "event_data"):
        value = event.get(key)
        if isinstance(value, dict):
            return {**event, **value}
    return event


def _is_approved(event: dict[str, Any], value: dict[str, Any]) -> bool:
    states = (
        event.get("event"),
        event.get("event_type"),
        event.get("event_name"),
        event.get("type"),
        value.get("event"),
        value.get("event_type"),
        value.get("status"),
        value.get("payment_status"),
        value.get("transaction_status"),
    )
    normalized = {_normalize(state) for state in states if state is not None}
    if normalized.intersection(APPROVED_EVENTS):
        return True
    return any(
        state.endswith("_approved") or state.endswith("_paid")
        for state in normalized
    )


def _nested_objects(value: dict[str, Any]) -> list[dict[str, Any]]:
    result = [value]
    for key in ("payment", "transaction", "sale", "order", "product", "customer"):
        nested = value.get(key)
        if isinstance(nested, dict):
            result.append(nested)
    return result


def _extract_amount(value: dict[str, Any]) -> Decimal:
    candidates = _nested_objects(value)
    raw_amount: object | None = None
    for item in candidates:
        raw_amount = next(
            (
                item[key]
                for key in ("gross_amount", "amount", "value", "total_amount", "total", "price")
                if item.get(key) is not None
            ),
            None,
        )
        if raw_amount is not None:
            break
    if isinstance(raw_amount, dict):
        raw_amount = raw_amount.get("value") or raw_amount.get("amount")
    try:
        amount = Decimal(str(raw_amount)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
    except (InvalidOperation, ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="O evento aprovado precisa informar um valor de venda válido.",
        ) from None
    if not amount.is_finite() or amount < 0 or amount > Decimal("9999999999.99"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="O valor de venda está fora do limite permitido.",
        )
    return amount


def _sale_identity(event: dict[str, Any], value: dict[str, Any]) -> str:
    candidates = _nested_objects(value)
    identifiers = (
        "transaction_id",
        "payment_id",
        "sale_id",
        "order_id",
        "id",
        "code",
    )
    for item in candidates:
        for key in identifiers:
            identifier = item.get(key)
            if identifier is not None and str(identifier).strip():
                return str(identifier).strip()[:160]
    serialized = json.dumps(event, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _occurred_at(event: dict[str, Any], value: dict[str, Any]) -> datetime:
    raw = next(
        (
            item[key]
            for item in _nested_objects(value)
            for key in ("approved_at", "paid_at", "created_at", "timestamp", "date")
            if item.get(key) is not None
        ),
        event.get("timestamp"),
    )
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return datetime.fromtimestamp(raw, tz=timezone.utc)
    if isinstance(raw, str):
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=BRAZIL_TIME_ZONE)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            logger.warning("Smokepay sent an invalid sale timestamp.")
    return utc_now()


def _customer_name(value: dict[str, Any]) -> str | None:
    for item in _nested_objects(value):
        name = item.get("name") or item.get("full_name")
        customer = item.get("customer")
        if isinstance(customer, dict):
            name = name or customer.get("name") or customer.get("full_name")
        if isinstance(name, str) and name.strip():
            return name.strip()[:240]
    return None


def _operation_response(
    operation: SmokepayOperation,
) -> SmokepayOperationResponse:
    try:
        secret = decrypt_value(operation.encrypted_webhook_key)
    except ValueError as exc:
        logger.error(
            "Smokepay webhook key could not be decrypted (operation_id=%s).",
            operation.id,
        )
        raise HTTPException(
            status_code=500,
            detail="Não foi possível carregar a URL deste webhook.",
        ) from exc
    base_url = get_settings().public_base_url.rstrip("/")
    return SmokepayOperationResponse(
        id=operation.id,
        name=operation.name,
        split_percent=operation.split_percent,
        is_active=operation.is_active,
        webhook_url=(
            f"{base_url}/api/webhooks/smokepay/"
            f"{operation.id}/{secret}"
        ),
        created_at=operation.created_at,
        updated_at=operation.updated_at,
    )


@router.get(
    "/api/integrations/smokepay",
    response_model=SmokepayOperationsResponse,
)
async def list_smokepay_operations(
    access: OwnerAccess,
    db: DbSession,
) -> SmokepayOperationsResponse:
    operations = (
        await db.scalars(
            select(SmokepayOperation)
            .where(SmokepayOperation.workspace_id == access.workspace.id)
            .order_by(SmokepayOperation.created_at.desc(), SmokepayOperation.id)
        )
    ).all()
    return SmokepayOperationsResponse(
        operations=[_operation_response(item) for item in operations]
    )


@router.post(
    "/api/integrations/smokepay",
    response_model=SmokepayOperationResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
async def create_smokepay_operation(
    payload: SmokepayOperationCreate,
    access: OwnerAccess,
    db: DbSession,
) -> SmokepayOperationResponse:
    webhook_key = secrets.token_urlsafe(36)
    try:
        operation = SmokepayOperation(
            workspace_id=access.workspace.id,
            name=payload.name,
            split_percent=payload.split_percent,
            webhook_key_hash=hashlib.sha256(webhook_key.encode("utf-8")).hexdigest(),
            encrypted_webhook_key=encrypt_value(webhook_key),
        )
    except RuntimeError as exc:
        logger.error("Smokepay key encryption is not configured (%s).", type(exc).__name__)
        raise HTTPException(
            status_code=503,
            detail="O armazenamento seguro de chaves não está configurado.",
        ) from None
    db.add(operation)
    try:
        await db.commit()
        await db.refresh(operation)
    except (RuntimeError, SQLAlchemyError) as exc:
        await db.rollback()
        logger.error("Smokepay operation could not be created (%s).", type(exc).__name__)
        raise HTTPException(
            status_code=500,
            detail="Não foi possível criar a integração Smokepay.",
        ) from None
    return _operation_response(operation)


@router.put(
    "/api/integrations/smokepay/{operation_id}",
    response_model=SmokepayOperationResponse,
    dependencies=[Depends(require_csrf)],
)
async def update_smokepay_operation(
    operation_id: UUID,
    payload: SmokepayOperationUpdate,
    access: OwnerAccess,
    db: DbSession,
) -> SmokepayOperationResponse:
    operation = await db.scalar(
        select(SmokepayOperation).where(
            SmokepayOperation.id == operation_id,
            SmokepayOperation.workspace_id == access.workspace.id,
        )
    )
    if operation is None:
        raise HTTPException(status_code=404, detail="Operação não encontrada.")
    operation.name = payload.name
    operation.split_percent = payload.split_percent
    operation.is_active = payload.is_active
    try:
        await db.commit()
        await db.refresh(operation)
    except SQLAlchemyError:
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Não foi possível atualizar a operação.",
        ) from None
    return _operation_response(operation)


@router.post(
    "/api/integrations/smokepay/{operation_id}/rotate-key",
    response_model=SmokepayOperationResponse,
    dependencies=[Depends(require_csrf)],
)
async def rotate_smokepay_webhook_key(
    operation_id: UUID,
    access: OwnerAccess,
    db: DbSession,
) -> SmokepayOperationResponse:
    operation = await db.scalar(
        select(SmokepayOperation).where(
            SmokepayOperation.id == operation_id,
            SmokepayOperation.workspace_id == access.workspace.id,
        )
    )
    if operation is None:
        raise HTTPException(status_code=404, detail="Operação não encontrada.")
    webhook_key = secrets.token_urlsafe(36)
    operation.webhook_key_hash = hashlib.sha256(webhook_key.encode("utf-8")).hexdigest()
    operation.encrypted_webhook_key = encrypt_value(webhook_key)
    await db.commit()
    await db.refresh(operation)
    return _operation_response(operation)


@router.delete(
    "/api/integrations/smokepay/{operation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf)],
)
async def delete_smokepay_operation(
    operation_id: UUID,
    access: OwnerAccess,
    db: DbSession,
) -> None:
    operation = await db.scalar(
        select(SmokepayOperation).where(
            SmokepayOperation.id == operation_id,
            SmokepayOperation.workspace_id == access.workspace.id,
        )
    )
    if operation is None:
        raise HTTPException(status_code=404, detail="Operação não encontrada.")
    await db.delete(operation)
    await db.commit()


@router.get(
    "/api/analytics/smokepay",
    response_model=SmokepayFinanceSummary,
)
async def get_smokepay_finance(
    access: OwnerAccess,
    db: DbSession,
) -> SmokepayFinanceSummary:
    now = utc_now()
    day_start, day_end = local_day_bounds_utc(now)
    operations = list(
        (
            await db.scalars(
                select(SmokepayOperation)
                .where(SmokepayOperation.workspace_id == access.workspace.id)
                .order_by(SmokepayOperation.name, SmokepayOperation.id)
            )
        ).all()
    )
    operation_sales = (
        await db.execute(
            select(SharkEvent, SmokepayOperation)
            .join(SmokepayOperation, SmokepayOperation.id == SharkEvent.operation_id)
            .where(
                SharkEvent.workspace_id == access.workspace.id,
                SharkEvent.event_type == "pix_paid",
                SharkEvent.occurred_at >= day_start,
                SharkEvent.occurred_at < day_end,
            )
            .order_by(SharkEvent.occurred_at.desc(), SharkEvent.id.desc())
        )
    ).all()
    totals: dict[UUID, tuple[int, Decimal, Decimal]] = {
        operation.id: (0, Decimal("0.00"), Decimal("0.00"))
        for operation in operations
    }
    for sale, operation in operation_sales:
        count, gross, net = totals[operation.id]
        totals[operation.id] = (
            count + 1,
            gross + Decimal(str(sale.amount)),
            net
            + Decimal(str(sale.net_amount))
            if sale.net_amount is not None
            else net + Decimal(str(sale.amount)),
        )
    by_operation = [
        SmokepayOperationRevenue(
            operation_id=operation.id,
            name=operation.name,
            split_percent=operation.split_percent,
            sale_count=totals[operation.id][0],
            gross_amount=totals[operation.id][1].quantize(Decimal("0.01")),
            net_amount=totals[operation.id][2].quantize(Decimal("0.01")),
        )
        for operation in operations
    ]
    recent_sales = [
        SmokepaySaleItem(
            id=sale.id,
            operation_id=operation.id,
            operation_name=operation.name,
            transaction_id=sale.transaction_id,
            customer_name=sale.customer_name,
            plan_name=sale.plan_name,
            gross_amount=sale.amount,
            net_amount=sale.net_amount if sale.net_amount is not None else sale.amount,
            occurred_at=sale.occurred_at,
        )
        for sale, operation in operation_sales[:30]
    ]
    return SmokepayFinanceSummary(
        day=now.astimezone(BRAZIL_TIME_ZONE).date().isoformat(),
        daily_goal=access.workspace.smokepay_daily_goal,
        gross_total=sum((item.gross_amount for item in by_operation), Decimal("0.00")),
        net_total=sum((item.net_amount for item in by_operation), Decimal("0.00")),
        sale_count=sum(item.sale_count for item in by_operation),
        operations=by_operation,
        recent_sales=recent_sales,
    )


@router.put(
    "/api/analytics/smokepay/daily-goal",
    response_model=SmokepayFinanceSummary,
    dependencies=[Depends(require_csrf)],
)
async def update_smokepay_daily_goal(
    payload: SmokepayDailyGoalUpdate,
    access: OwnerAccess,
    db: DbSession,
) -> SmokepayFinanceSummary:
    workspace = await db.get(Workspace, access.workspace.id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace não encontrado.")
    workspace.smokepay_daily_goal = payload.daily_goal.quantize(Decimal("0.01"))
    await db.commit()
    await db.refresh(workspace)
    return await get_smokepay_finance(access, db)


@router.post(
    "/api/webhooks/smokepay/{operation_id}/{webhook_key}",
    response_model=SmokepayWebhookResult,
)
async def receive_smokepay_webhook(
    operation_id: UUID,
    webhook_key: str,
    request: Request,
    db: DbSession,
) -> SmokepayWebhookResult:
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_WEBHOOK_BYTES:
            raise HTTPException(status_code=413, detail="O evento é muito grande.")
        chunks.append(chunk)
    try:
        payload = json.loads(b"".join(chunks))
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(
            status_code=400,
            detail="O webhook precisa conter JSON válido.",
        ) from None
    if not isinstance(payload, (dict, list)):
        raise HTTPException(
            status_code=400,
            detail="O webhook precisa conter um objeto ou lista JSON.",
        )

    operation = await db.scalar(
        select(SmokepayOperation).where(
            SmokepayOperation.id == operation_id,
            SmokepayOperation.is_active.is_(True),
        )
    )
    if operation is None:
        raise HTTPException(status_code=404, detail="Webhook não encontrado.")
    supplied_hash = hashlib.sha256(webhook_key.encode("utf-8")).hexdigest()
    if not hmac.compare_digest(supplied_hash, operation.webhook_key_hash):
        raise HTTPException(status_code=404, detail="Webhook não encontrado.")

    if isinstance(payload, list):
        events = [item for item in payload if isinstance(item, dict)]
    else:
        events = _event_list(payload)
    if not events:
        raise HTTPException(status_code=422, detail="Nenhum evento reconhecido.")
    accepted = 0
    duplicates = 0
    ignored = 0
    for event in events:
        value = _event_value(event)
        if not _is_approved(event, value):
            ignored += 1
            continue
        gross = _extract_amount(value)
        net = (gross * operation.split_percent / Decimal("100")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        transaction_id = _sale_identity(event, value)
        identity = f"{operation.id}:{transaction_id}"
        source_key = hashlib.sha256(identity.encode("utf-8")).hexdigest()
        customer = value.get("customer")
        if not isinstance(customer, dict):
            customer = {}
        product = value.get("product") or value.get("plan")
        if not isinstance(product, dict):
            product = {}
        event_id = event.get("event_id") or event.get("webhook_id")
        sale = SharkEvent(
            workspace_id=operation.workspace_id,
            operation_id=operation.id,
            event_type="pix_paid",
            source_event_key=source_key,
            webhook_id=str(event_id)[:160] if event_id is not None else None,
            transaction_id=transaction_id[:160],
            customer_name=_customer_name(value),
            customer_username=(
                str(customer.get("username"))[:120]
                if customer.get("username")
                else None
            ),
            bot_name=None,
            plan_name=(
                str(
                    product.get("name")
                    or product.get("title")
                    or value.get("product_name")
                    or value.get("plan_name")
                )[:160]
                if (
                    product.get("name")
                    or product.get("title")
                    or value.get("product_name")
                    or value.get("plan_name")
                )
                else None
            ),
            amount=gross,
            net_amount=net,
            occurred_at=_occurred_at(event, value),
        )
        try:
            async with db.begin_nested():
                db.add(sale)
                await db.flush()
        except IntegrityError:
            duplicates += 1
        else:
            accepted += 1
    if accepted or duplicates:
        try:
            await db.commit()
        except SQLAlchemyError:
            await db.rollback()
            logger.exception("Smokepay sale events could not be persisted.")
            raise HTTPException(
                status_code=500,
                detail="Não foi possível registrar as vendas recebidas.",
            ) from None
    return SmokepayWebhookResult(
        accepted=accepted,
        duplicates=duplicates,
        ignored=ignored,
    )
