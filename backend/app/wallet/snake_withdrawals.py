"""SnakePay withdrawals (Cash Out) of an operation's own SnakePay account.

The money of SnakePay sales sits in each account at SnakePay (the seller's share, the
owner's commission). Falcon withdraws it with that account's key and Cash Out secret: the
platform's (server settings) for the Super Admin, the ones the user saved in Gateways for
everyone else. There is no balance API, so the balance shown is our estimate (what SnakePay
sent to the account minus what was withdrawn through Falcon); SnakePay checks the real one.

Every withdrawal is saved with its ``request_id`` BEFORE the first call and the same id is
reused on retries, so a lost answer can never pay twice.
"""

import logging
import uuid
from datetime import timedelta
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import func, select

from app.bots import snakepay_cashout as cashout
from app.core.config import get_settings
from app.core.crypto import decrypt_value
from app.core.time import utc_now
from app.models import FinancialWithdrawal, User, Workspace

logger = logging.getLogger(__name__)
CHECK_EVERY = timedelta(seconds=30)  # SnakePay asks for 30 s or more between status checks
GIVE_UP_AFTER = timedelta(hours=24)


async def credentials(db, workspace: Workspace) -> tuple[str, str] | None:
    """(api key, Cash Out secret) of the workspace's SnakePay account, or None."""
    owner = await db.get(User, workspace.owner_id)
    if owner is not None and owner.platform_role == "SUPER_ADMIN":
        settings = get_settings()
        key, secret = settings.snakepay_api_key, settings.snakepay_cashout_secret
        if key and secret and key.get_secret_value().strip() and secret.get_secret_value().strip():
            return key.get_secret_value().strip(), secret.get_secret_value().strip()
        return None
    if not (workspace.snakepay_api_key_encrypted and workspace.snakepay_cashout_secret_encrypted):
        return None
    try:
        return decrypt_value(workspace.snakepay_api_key_encrypted), decrypt_value(workspace.snakepay_cashout_secret_encrypted)
    except (RuntimeError, ValueError):
        logger.exception("Could not decrypt SnakePay Cash Out credentials of workspace %s", workspace.id)
        return None


async def estimated_balance(db, workspace_id: uuid.UUID, received: Decimal) -> Decimal:
    """What SnakePay sent to the account minus what left through Falcon (paid or on the way)."""
    out = await db.scalar(
        select(func.coalesce(func.sum(FinancialWithdrawal.amount), 0)).where(
            FinancialWithdrawal.workspace_id == workspace_id, FinancialWithdrawal.gateway == "snakepay",
            FinancialWithdrawal.status.in_(("PAID", "PROCESSING")),
        )
    )
    return max(Decimal("0.00"), (received - Decimal(str(out or 0))).quantize(Decimal("0.01")))


def _apply(item: FinancialWithdrawal, result: cashout.Cashout) -> None:
    if result.withdrawal_id:
        item.gateway_withdrawal_id = result.withdrawal_id[:64]
    if item.requested_max and result.total_debit:
        item.amount = result.total_debit
    if result.status == "paid":
        item.status, item.processed_at = "PAID", utc_now()
    elif result.status == "failed":
        item.status, item.processed_at = "FAILED", utc_now()
        item.note = "A SnakePay não concluiu o saque; o valor voltou para o saldo."


async def withdraw(
    db, actor: User, workspace: Workspace, *, amount: Decimal | None, pix_key: str, key_type: str, estimate: Decimal
) -> FinancialWithdrawal:
    """``amount`` None = everything available ("MAX")."""
    creds = await credentials(db, workspace)
    if creds is None:
        raise HTTPException(
            status_code=422,
            detail="Para sacar a SnakePay por aqui, cadastre em Gateways a chave API e o segredo de saque (Cash Out) da sua conta SnakePay.",
        )
    if amount is not None and not (cashout.MIN_AMOUNT <= amount <= cashout.MAX_AMOUNT):
        raise HTTPException(status_code=422, detail="Na SnakePay o saque vai de R$ 10,00 a R$ 100.000,00.")
    if await db.scalar(
        select(FinancialWithdrawal.id).where(
            FinancialWithdrawal.workspace_id == workspace.id, FinancialWithdrawal.gateway == "snakepay",
            FinancialWithdrawal.status == "PROCESSING",
        )
    ):
        raise HTTPException(status_code=409, detail="Há um saque da SnakePay em andamento. Aguarde a confirmação.")
    item = FinancialWithdrawal(
        workspace_id=workspace.id, created_by_user_id=actor.id, gateway="snakepay", status="PROCESSING",
        amount=amount if amount is not None else max(estimate, Decimal("0.01")), requested_max=amount is None,
        request_id=str(uuid.uuid4()), pix_key_type=key_type, pix_key=pix_key, processed_by_user_id=actor.id,
    )
    db.add(item)
    await db.commit()  # saved (with its request_id) before SnakePay hears about it
    try:
        result = await cashout.create(
            amount=amount, pix_key=pix_key, key_type=key_type, request_id=item.request_id, api_key=creds[0], secret=creds[1]
        )
    except cashout.CashoutError as exc:
        item.last_checked_at = utc_now()
        if exc.retryable:  # unknown outcome: retried later with the same request_id
            item.note = "Aguardando a SnakePay responder; o saque é conferido sozinho."
            await db.commit()
            return item
        logger.warning("SnakePay Cash Out refused: HTTP %s %s", exc.status, exc.detail)
        item.status, item.processed_at, item.note = "FAILED", utc_now(), cashout.message(exc)[:240]
        await db.commit()
        status = 409 if exc.status == 409 else 422
        raise HTTPException(status_code=status, detail=cashout.message(exc)) from None
    item.last_checked_at = utc_now()
    _apply(item, result)
    await db.commit()
    return item


async def reconcile(db, workspace: Workspace) -> None:
    """Settle this account's SnakePay withdrawals still on the way (at most every 30 s each)."""
    now = utc_now()
    waiting = [
        item
        for item in await db.scalars(
            select(FinancialWithdrawal).where(
                FinancialWithdrawal.workspace_id == workspace.id, FinancialWithdrawal.gateway == "snakepay",
                FinancialWithdrawal.status == "PROCESSING",
            )
        )
        if item.last_checked_at is None or now - _aware(item.last_checked_at) >= CHECK_EVERY
    ]
    if not waiting:
        return
    creds = await credentials(db, workspace)
    if creds is None:
        return
    for item in waiting:
        item.last_checked_at = now
        try:
            if item.gateway_withdrawal_id:
                result = await cashout.get(item.gateway_withdrawal_id, api_key=creds[0], secret=creds[1])
            elif now - _aware(item.created_at) > GIVE_UP_AFTER:
                item.status, item.processed_at = "FAILED", now
                item.note = "A SnakePay não confirmou o pedido em 24 h; confira o extrato da SnakePay."
                continue
            else:  # the first answer was lost: ask again with the same request_id (idempotent)
                result = await cashout.create(
                    amount=None if item.requested_max else item.amount, pix_key=item.pix_key or "",
                    key_type=item.pix_key_type or "", request_id=item.request_id or "", api_key=creds[0], secret=creds[1],
                )
        except cashout.CashoutError as exc:
            if exc.status == 409 and not item.gateway_withdrawal_id:
                # SnakePay may already hold this request_id: never mark it failed on our own
                item.note = "A SnakePay já recebeu um pedido com este código; confira o extrato da SnakePay."
            elif not exc.retryable and not item.gateway_withdrawal_id:
                item.status, item.processed_at, item.note = "FAILED", now, cashout.message(exc)[:240]
            continue
        _apply(item, result)
    await db.commit()


def _aware(value):
    from datetime import timezone

    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
