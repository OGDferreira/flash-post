"""Athenas Pay subaccount withdrawals from a workspace's own wallet."""

import logging
import uuid
from datetime import timedelta
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select

from app.bots import atenaspay
from app.core.time import utc_now
from app.models import FinancialWithdrawal, User, Workspace

logger = logging.getLogger(__name__)
MIN_AMOUNT = Decimal("10.00")
CHECK_EVERY = timedelta(seconds=30)


def _apply(item: FinancialWithdrawal, payout: atenaspay.ShopPayout) -> None:
    item.gateway_withdrawal_id = payout.withdrawal_id[:64]
    item.fee = payout.fee
    item.amount = payout.amount if payout.amount > 0 else item.amount
    item.gateway_e2e_id = payout.e2e_id[:64] if payout.e2e_id else None
    if payout.status == "completed":
        item.status, item.processed_at, item.note = "PAID", utc_now(), None
    elif payout.status == "failed":
        item.status, item.processed_at = "FAILED", utc_now()
        item.note = (payout.failure_reason or "A Atenas Pay não concluiu o saque.")[:240]
    elif payout.status not in {"pending", "processing"}:
        logger.warning(
            "Athenas Pay returned unknown withdrawal status %s for %s.",
            payout.status,
            item.id,
        )


async def withdraw(
    db,
    actor: User,
    workspace: Workspace,
    *,
    amount: Decimal,
    shop_ref: str,
    pix_key: str,
    key_type: str,
) -> FinancialWithdrawal:
    if amount < MIN_AMOUNT:
        raise HTTPException(status_code=422, detail="O saque mínimo pela Atenas Pay é R$ 10,00.")
    if not atenaspay.api_configured():
        raise HTTPException(status_code=503, detail="Saque pela Atenas Pay não está configurado no servidor.")
    if await db.scalar(
        select(FinancialWithdrawal.id).where(
            FinancialWithdrawal.workspace_id == workspace.id,
            FinancialWithdrawal.gateway == "atenaspay",
            FinancialWithdrawal.status == "PROCESSING",
        )
    ):
        raise HTTPException(status_code=409, detail="Há um saque Atenas Pay em andamento. Aguarde a confirmação.")
    try:
        available = await atenaspay.shop_balance(shop_ref)
    except atenaspay.AtenaspayError as exc:
        logger.warning("Athenas Pay balance lookup failed (HTTP %s).", exc.status)
        raise HTTPException(status_code=502, detail="Não foi possível consultar o saldo Atenas Pay.") from None
    if available is None or amount > available:
        raise HTTPException(status_code=422, detail="Saldo Atenas Pay insuficiente para esse valor.")

    item = FinancialWithdrawal(
        workspace_id=workspace.id,
        created_by_user_id=actor.id,
        amount=amount,
        status="PROCESSING",
        gateway="atenaspay",
        request_id=str(uuid.uuid4()),
        pix_key_type=key_type,
        pix_key=pix_key,
        processed_by_user_id=actor.id,
    )
    db.add(item)
    await db.commit()
    try:
        payout = await atenaspay.withdraw_shop(
            shop_ref=shop_ref,
            amount=amount,
            pix_key=pix_key,
            pix_key_type=key_type,
            correlation_id=item.request_id,
            sub_shop_id=str(workspace.owner_id),
        )
    except atenaspay.AtenaspayError as exc:
        item.last_checked_at = utc_now()
        if exc.status == 0 or exc.status >= 500:
            item.note = "Atenas Pay ainda não confirmou o saque; a Flash vai consultar o resultado."
            await db.commit()
            return item
        item.status, item.processed_at = "FAILED", utc_now()
        item.note = str(exc)[:240]
        await db.commit()
        if exc.status == 429:
            seconds = max(1, exc.cooldown_seconds or 300)
            minutes = max(1, (seconds + 59) // 60)
            raise HTTPException(
                status_code=429,
                detail=f"A Atenas Pay exige intervalo entre saques. Tente novamente em {minutes} min.",
            ) from None
        status = 422 if exc.status in {400, 403, 404} else 502
        raise HTTPException(status_code=status, detail=str(exc)) from None

    item.last_checked_at = utc_now()
    _apply(item, payout)
    await db.commit()
    await db.refresh(item)
    return item


async def reconcile(db, workspace: Workspace, shop_ref: str) -> None:
    now = utc_now()
    waiting = list(
        await db.scalars(
            select(FinancialWithdrawal).where(
                FinancialWithdrawal.workspace_id == workspace.id,
                FinancialWithdrawal.gateway == "atenaspay",
                FinancialWithdrawal.status == "PROCESSING",
                (FinancialWithdrawal.last_checked_at.is_(None))
                | (FinancialWithdrawal.last_checked_at <= now - CHECK_EVERY),
            )
        )
    )
    if not waiting or not atenaspay.api_configured():
        return
    for item in waiting:
        item.last_checked_at = now
    await db.commit()
    try:
        remote = await atenaspay.shop_withdrawals(shop_ref)
    except atenaspay.AtenaspayError as exc:
        logger.warning("Athenas Pay withdrawal reconciliation failed (HTTP %s).", exc.status)
        return
    by_id = {payout.withdrawal_id: payout for payout in remote if payout.withdrawal_id}
    for item in waiting:
        payout = by_id.get(item.gateway_withdrawal_id or "")
        if payout is None:
            if not item.gateway_withdrawal_id and item.request_id and item.pix_key and item.pix_key_type:
                try:
                    payout = await atenaspay.withdraw_shop(
                        shop_ref=shop_ref,
                        amount=item.amount,
                        pix_key=item.pix_key,
                        pix_key_type=item.pix_key_type,
                        correlation_id=item.request_id,
                        sub_shop_id=str(workspace.owner_id),
                    )
                except atenaspay.AtenaspayError as exc:
                    if exc.status not in {0, 429} and exc.status < 500:
                        item.status, item.processed_at = "FAILED", now
                        item.note = str(exc)[:240]
                    continue
            else:
                continue
        if payout is None:
            continue
        _apply(item, payout)
    await db.commit()
