import json
import logging
import secrets
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import func, select

from app.auth.dependencies import DbSession, OwnerAccess, require_csrf
from app.core.config import get_settings
from app.analytics.periods import AnalyticsPeriod, period_bounds, period_label
from app.core.time import APP_TIME_ZONE_NAME, utc_now
from app.models import InstagramAccount, SharkAccount, SharkLead, SharkTransaction, Workspace
from app.shark.metrics import CRITERIA, compute_shark_metrics, scope_conditions, window
from app.shark.ingest import (
    event_batches,
    log_event,
    parse_event,
    upsert_lead,
    upsert_transaction,
)

router = APIRouter(prefix="/api/sharkbot", tags=["Sharkbot"])
logger = logging.getLogger(__name__)
_MAX_WEBHOOK_BYTES = 1_048_576


class SharkbotAccountWebhook(BaseModel):
    account_id: UUID
    username: str
    webhook_url: str


class SharkbotWebhookSettings(BaseModel):
    # One URL per workspace. Several bots/flows may use it: events are told
    # apart by bot.id / flow.id. Use an account URL only to attribute a bot's
    # sales to a specific Instagram account.
    webhook_url: str
    account_webhooks: list[SharkbotAccountWebhook] = []


class SharkbotWebhookResponse(BaseModel):
    accepted: int
    duplicates: int
    ignored: int = 0


async def _settings_response(db: DbSession, workspace: Workspace) -> SharkbotWebhookSettings:
    base_url = f"{get_settings().public_base_url.rstrip('/')}/api/sharkbot/webhook/{workspace.sharkbot_webhook_token}"
    accounts = (
        await db.execute(
            select(InstagramAccount.id, InstagramAccount.username)
            .where(InstagramAccount.workspace_id == workspace.id)
            .order_by(InstagramAccount.username)
        )
    ).all()
    return SharkbotWebhookSettings(
        webhook_url=base_url,
        account_webhooks=[
            SharkbotAccountWebhook(
                account_id=account_id, username=username, webhook_url=f"{base_url}?account={account_id}"
            )
            for account_id, username in accounts
        ],
    )


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
    return await _settings_response(db, workspace)


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
    return await _settings_response(db, workspace)


@router.post(
    "/webhook/{webhook_token}",
    response_model=SharkbotWebhookResponse,
)
async def receive_sharkbot_webhook(
    webhook_token: str,
    request: Request,
    db: DbSession,
    account: UUID | None = Query(default=None),
) -> SharkbotWebhookResponse:
    # Authentication: SharkBot sends no signature, so the secret token in the
    # URL is the credential. It is checked before the body is read.
    if not 16 <= len(webhook_token) <= 128:
        raise HTTPException(status_code=404, detail="Sharkbot webhook not found.")
    shark_account = await db.scalar(
        select(SharkAccount).where(SharkAccount.webhook_token == webhook_token)
    )
    if shark_account is not None:
        if not secrets.compare_digest(shark_account.webhook_token, webhook_token) or not shark_account.is_active:
            raise HTTPException(status_code=404, detail="Sharkbot webhook not found.")
        workspace = await db.get(Workspace, shark_account.workspace_id)
        if workspace is None or workspace.status != "ACTIVE":
            raise HTTPException(status_code=404, detail="Sharkbot webhook not found.")
    else:
        workspace = await db.scalar(
            select(Workspace).where(Workspace.sharkbot_webhook_token == webhook_token)
        )
        if workspace is None or not secrets.compare_digest(
            workspace.sharkbot_webhook_token or "", webhook_token
        ):
            raise HTTPException(status_code=404, detail="Sharkbot webhook not found.")
    shark_account_id = shark_account.id if shark_account is not None else None
    account_id: UUID | None = None
    if account is not None:
        # Only accounts of this workspace; otherwise the URL is misconfigured.
        account_id = await db.scalar(
            select(InstagramAccount.id).where(
                InstagramAccount.id == account,
                InstagramAccount.workspace_id == workspace.id,
            )
        )
        if account_id is None:
            raise HTTPException(status_code=404, detail="Sharkbot webhook not found.")

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
    events = event_batches(payload)
    if not events:
        raise HTTPException(status_code=422, detail="No recognizable Sharkbot events found.")

    now = datetime.now(timezone.utc)
    accepted = duplicates = ignored = 0
    newly_paid = []
    for raw_event in events:
        parsed = parse_event(raw_event)
        if parsed is None:
            ignored += 1
            continue
        if parsed.event_type == "lead_initiated":
            changed = await upsert_lead(
                db, workspace.id, parsed, account_id, now, shark_account_id
            )
        elif parsed.transaction_key is not None:
            changed = await upsert_transaction(
                db, workspace.id, parsed, account_id, now, shark_account_id
            )
            if changed and parsed.paid:
                newly_paid.append(parsed)
        else:  # link_click: logged only
            changed = False
        await log_event(db, workspace.id, parsed, account_id)
        if changed:
            accepted += 1
        else:
            duplicates += 1
    if shark_account is not None:
        shark_account.last_event_at = now
    await db.commit()
    if newly_paid:
        await _notify_shark_sales(db, workspace, newly_paid, now)
    # Unknown event types are acknowledged (200) so SharkBot does not retry
    # them forever; they are reported as ignored.
    return SharkbotWebhookResponse(accepted=accepted, duplicates=duplicates, ignored=ignored)


_NOTIFY_MAX_AGE = timedelta(minutes=30)
_NOTIFY_MAX_PER_DELIVERY = 3


async def _notify_shark_sales(db, workspace: Workspace, sales: list, now: datetime) -> None:
    """Approved SharkBot sale -> the same "Nova venda" notice (and cash sound) as Flash.
    Old payments re-sent by SharkBot (history backfills) do not notify."""
    from app.partners.service import notify_user

    fresh = [
        sale for sale in sales
        if (sale.paid_at or sale.occurred_at or now) >= now - _NOTIFY_MAX_AGE
    ]
    try:
        for sale in fresh[:_NOTIFY_MAX_PER_DELIVERY]:
            amount = f"R$ {sale.amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") if sale.amount else None
            # Same short notice as any sale; plan and bot stay in the sales screen.
            body = f"Você recebeu {amount} 🤑" if amount else "Pagamento aprovado 🤑"
            await notify_user(db, workspace.owner_id, "sale", "🦈 Nova venda - Shark Bot!", body, "/dashboard")
        if len(fresh) > _NOTIFY_MAX_PER_DELIVERY:
            extra = len(fresh) - _NOTIFY_MAX_PER_DELIVERY
            await notify_user(db, workspace.owner_id, "sale", "🦈 Novas vendas - Shark Bot!", f"Mais {extra} venda(s) aprovada(s).", "/dashboard")
        await db.commit()
    except Exception as exc:  # a notice must never fail the webhook
        await db.rollback()
        logger.warning("SharkBot sale notice failed (%s).", type(exc).__name__)


# ---------------------------------------------------------------- accounts
_MAX_SHARK_ACCOUNTS = 10


class SharkAccountPayload(BaseModel):
    name: str
    external_account_id: str | None = None

    def cleaned(self) -> tuple[str, str | None]:
        name = " ".join(self.name.split())
        if not 1 <= len(name) <= 80:
            raise HTTPException(status_code=422, detail="Informe um nome de 1 a 80 caracteres.")
        external = (self.external_account_id or "").strip() or None
        if external is not None and len(external) > 120:
            raise HTTPException(status_code=422, detail="O ID da conta Shark deve ter até 120 caracteres.")
        return name, external


class SharkAccountResponse(BaseModel):
    id: UUID | None
    name: str
    external_account_id: str | None
    webhook_url: str
    is_active: bool
    is_default: bool
    last_event_at: datetime | None


def _account_url(token: str) -> str:
    return f"{get_settings().public_base_url.rstrip('/')}/api/sharkbot/webhook/{token}"


def _account_response(account: SharkAccount) -> SharkAccountResponse:
    return SharkAccountResponse(
        id=account.id,
        name=account.name,
        external_account_id=account.external_account_id,
        webhook_url=_account_url(account.webhook_token),
        is_active=account.is_active,
        is_default=False,
        last_event_at=account.last_event_at,
    )


@router.get("/accounts", response_model=list[SharkAccountResponse])
async def list_shark_accounts(access: OwnerAccess, db: DbSession) -> list[SharkAccountResponse]:
    workspace = await db.get(Workspace, access.workspace.id)
    if workspace is not None and not workspace.sharkbot_webhook_token:
        workspace.sharkbot_webhook_token = secrets.token_urlsafe(32)
        await db.commit()
    accounts = (
        await db.scalars(
            select(SharkAccount)
            .where(SharkAccount.workspace_id == access.workspace.id)
            .order_by(SharkAccount.created_at, SharkAccount.id)
        )
    ).all()
    default = SharkAccountResponse(
        id=None,
        name="Conta principal",
        external_account_id=None,
        webhook_url=_account_url(workspace.sharkbot_webhook_token) if workspace else "",
        is_active=True,
        is_default=True,
        last_event_at=None,
    )
    return [default, *[_account_response(account) for account in accounts]]


@router.post(
    "/accounts",
    response_model=SharkAccountResponse,
    status_code=201,
    dependencies=[Depends(require_csrf)],
)
async def create_shark_account(
    payload: SharkAccountPayload, access: OwnerAccess, db: DbSession
) -> SharkAccountResponse:
    name, external = payload.cleaned()
    count = await db.scalar(
        select(func.count(SharkAccount.id)).where(SharkAccount.workspace_id == access.workspace.id)
    )
    if (count or 0) >= _MAX_SHARK_ACCOUNTS:
        raise HTTPException(status_code=409, detail="Limite de contas Shark atingido.")
    if await db.scalar(
        select(SharkAccount.id).where(
            SharkAccount.workspace_id == access.workspace.id, func.lower(SharkAccount.name) == name.lower()
        )
    ):
        raise HTTPException(status_code=409, detail="Já existe uma conta Shark com esse nome.")
    account = SharkAccount(
        workspace_id=access.workspace.id,
        name=name,
        external_account_id=external,
        webhook_token=secrets.token_urlsafe(32),
    )
    db.add(account)
    await db.commit()
    return _account_response(account)


async def _own_shark_account(db: DbSession, access: OwnerAccess, account_id: UUID) -> SharkAccount:
    account = await db.scalar(
        select(SharkAccount).where(
            SharkAccount.id == account_id, SharkAccount.workspace_id == access.workspace.id
        )
    )
    if account is None:
        raise HTTPException(status_code=404, detail="Conta Shark não encontrada.")
    return account


@router.patch(
    "/accounts/{account_id}",
    response_model=SharkAccountResponse,
    dependencies=[Depends(require_csrf)],
)
async def update_shark_account(
    account_id: UUID, payload: SharkAccountPayload, access: OwnerAccess, db: DbSession
) -> SharkAccountResponse:
    account = await _own_shark_account(db, access, account_id)
    name, external = payload.cleaned()
    clash = await db.scalar(
        select(SharkAccount.id).where(
            SharkAccount.workspace_id == access.workspace.id,
            func.lower(SharkAccount.name) == name.lower(),
            SharkAccount.id != account.id,
        )
    )
    if clash:
        raise HTTPException(status_code=409, detail="Já existe uma conta Shark com esse nome.")
    account.name, account.external_account_id = name, external
    await db.commit()
    return _account_response(account)


@router.post(
    "/accounts/{account_id}/rotate",
    response_model=SharkAccountResponse,
    dependencies=[Depends(require_csrf)],
)
async def rotate_shark_account(
    account_id: UUID, access: OwnerAccess, db: DbSession
) -> SharkAccountResponse:
    account = await _own_shark_account(db, access, account_id)
    account.webhook_token = secrets.token_urlsafe(32)
    await db.commit()
    return _account_response(account)


@router.delete("/accounts/{account_id}", status_code=204, dependencies=[Depends(require_csrf)])
async def delete_shark_account(account_id: UUID, access: OwnerAccess, db: DbSession) -> None:
    # Sales already received are kept (their origin becomes "removed").
    account = await _own_shark_account(db, access, account_id)
    await db.delete(account)
    await db.commit()


# ------------------------------------------------------------------- sales
class SharkSale(BaseModel):
    id: UUID
    status: str
    amount: Decimal | None
    plan_name: str | None
    bot_name: str | None
    flow_name: str | None
    customer_name: str | None
    customer_username: str | None
    shark_account_id: UUID | None
    shark_account_name: str | None
    instagram_account_id: UUID | None
    instagram_username: str | None
    created_at: datetime
    paid_at: datetime | None


class SharkSalesSummary(BaseModel):
    leads: int
    lead_buyers: int
    pix_generated: int
    pix_paid_from_period: int
    purchases: int
    purchases_without_amount: int
    revenue: Decimal
    pix_to_paid_rate: float | None
    lead_to_purchase_rate: float | None
    leads_per_purchase: float | None
    average_ticket: Decimal | None


class SharkSalesResponse(BaseModel):
    period: str
    period_label: str
    time_zone: str
    status: str
    page: int
    page_size: int
    total: int
    items: list[SharkSale]
    summary: SharkSalesSummary
    criteria: dict[str, str]


@router.get("/sales", response_model=SharkSalesResponse)
async def list_sales(
    access: OwnerAccess,
    db: DbSession,
    period: AnalyticsPeriod = "30d",
    start_date: date | None = None,
    end_date: date | None = None,
    account_id: UUID | None = None,
    shark_account_id: UUID | None = None,
    status: Literal["paid", "pending", "all"] = "paid",
    page: int = Query(default=1, ge=1, le=10_000),
    page_size: int = Query(default=20, ge=5, le=100),
) -> SharkSalesResponse:
    start, end = period_bounds(period, start_date, end_date, utc_now())
    workspace_id = access.workspace.id
    if account_id is not None and not await db.scalar(
        select(InstagramAccount.id).where(
            InstagramAccount.id == account_id, InstagramAccount.workspace_id == workspace_id
        )
    ):
        raise HTTPException(status_code=404, detail="Conta do Instagram não encontrada.")
    if shark_account_id is not None and not await db.scalar(
        select(SharkAccount.id).where(
            SharkAccount.id == shark_account_id, SharkAccount.workspace_id == workspace_id
        )
    ):
        raise HTTPException(status_code=404, detail="Conta Shark não encontrada.")

    conditions = scope_conditions(SharkTransaction, workspace_id, account_id, shark_account_id)
    if status == "paid":
        conditions += [
            SharkTransaction.status == "paid",
            SharkTransaction.paid_at.is_not(None),
            *window(SharkTransaction.paid_at, start, end),
        ]
        order_column = SharkTransaction.paid_at
    else:
        if status == "pending":
            conditions.append(SharkTransaction.status == "pending")
        conditions += window(SharkTransaction.created_at_source, start, end)
        order_column = SharkTransaction.created_at_source
    total = await db.scalar(select(func.count(SharkTransaction.id)).where(*conditions)) or 0
    rows = (
        await db.execute(
            select(SharkTransaction, SharkAccount.name, InstagramAccount.username)
            .outerjoin(SharkAccount, SharkAccount.id == SharkTransaction.shark_account_id)
            .outerjoin(InstagramAccount, InstagramAccount.id == SharkTransaction.account_id)
            .where(*conditions)
            .order_by(order_column.desc(), SharkTransaction.id)
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
    ).all()
    metrics = await compute_shark_metrics(
        db, workspace_id, start, end, account_id=account_id, shark_account_id=shark_account_id
    )
    return SharkSalesResponse(
        period=period,
        period_label=period_label(start, end),
        time_zone=APP_TIME_ZONE_NAME,
        status=status,
        page=page,
        page_size=page_size,
        total=total,
        items=[
            SharkSale(
                id=tx.id,
                status=tx.status,
                amount=tx.amount,
                plan_name=tx.plan_name,
                bot_name=tx.bot_name,
                flow_name=tx.flow_name,
                customer_name=tx.customer_name,
                customer_username=tx.customer_username,
                shark_account_id=tx.shark_account_id,
                shark_account_name=shark_name,
                instagram_account_id=tx.account_id,
                instagram_username=ig_username,
                created_at=tx.created_at_source,
                paid_at=tx.paid_at,
            )
            for tx, shark_name, ig_username in rows
        ],
        summary=SharkSalesSummary(**metrics.__dict__),
        criteria=CRITERIA,
    )
