"""Wallet: revenue, balance to withdraw, withdrawals and revenue goals.

Money from FlashBot sales sits in SmokePay: the platform owner's main account
(Super Admin) or each operation's subaccount. The balance shown here is what
the sales left for this user after fees and the partner split. Withdrawals go
straight to SmokePay: a subaccount pays out with POST /api/shops/{ref}/withdraw
(idempotent on our row id), the main wallet with POST /api/withdrawals. The
balance shown is SmokePay's own when reachable. Amounts are checked on the
server, never trusted from the browser.
"""

import uuid
from datetime import timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select

from app.auth.dependencies import AuthenticatedUser, DbSession, require_csrf
from app.core.time import BRAZIL_TIME_ZONE, utc_now
from app.bots import smokepay
from app.core.config import get_settings
from app.models import FinancialWithdrawal, TgOrder, User, Workspace
from app.partners.service import owner_workspace, shop_ref

router = APIRouter(prefix="/api/wallet", tags=["Wallet"])

CENT = Decimal("0.01")
MIN_WITHDRAWAL = Decimal("10.00")
GOALS = [Decimal(v) for v in ("10000", "50000", "100000", "500000", "1000000")]
GOAL_PRIZES = {10000: "Pulseira", 50000: "Caneca", 100000: "Placa", 500000: "Placa", 1000000: "Quadro, cordão e pingente de ouro"}


def _brl(value: Decimal) -> str:
    return f"R$ {value:.2f}".replace(".", ",")


def _money(value: object) -> Decimal:
    return Decimal(str(value or 0)).quantize(CENT, rounding=ROUND_HALF_UP)


class WithdrawalRequest(BaseModel):
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    pix_key_type: Literal["cpf", "cnpj", "email", "phone", "random"] | None = None
    pix_key: str | None = Field(default=None, max_length=140)
    note: str | None = Field(default=None, max_length=240)

    @field_validator("pix_key", "note")
    @classmethod
    def _strip(cls, value: str | None) -> str | None:
        value = (value or "").strip()
        return value or None


async def _workspace_for(db, user: User) -> Workspace:
    workspace = await owner_workspace(db, user.id)
    if workspace is None:
        raise HTTPException(status_code=403, detail="A carteira é da operação do dono da conta.")
    return workspace


async def balances(db, user: User, workspace_id: uuid.UUID) -> dict:
    """What the sales left for this user (after fee and split) and what is free to withdraw."""
    own = await db.scalar(
        select(func.coalesce(func.sum(func.coalesce(TgOrder.partner_net, TgOrder.net_amount, TgOrder.amount)), 0)).where(
            TgOrder.workspace_id == workspace_id, TgOrder.status == "paid"
        )
    )
    commissions = await db.scalar(
        select(func.coalesce(func.sum(TgOrder.split_amount), 0)).where(
            TgOrder.split_chief_user_id == user.id, TgOrder.status == "paid"
        )
    )
    sums = dict(
        (
            await db.execute(
                select(FinancialWithdrawal.status, func.coalesce(func.sum(FinancialWithdrawal.amount), 0))
                .where(FinancialWithdrawal.workspace_id == workspace_id)
                .group_by(FinancialWithdrawal.status)
            )
        ).all()
    )
    earned = _money(own) + _money(commissions)
    withdrawn = _money(sums.get("PAID"))
    pending = _money(sums.get("PROCESSING")) + _money(sums.get("REQUESTED"))
    return {
        "earned": earned,
        "commissions_received": _money(commissions),
        "withdrawn": withdrawn,
        "pending": pending,
        "available": max(Decimal("0.00"), earned - withdrawn - pending),
    }


async def month_revenue(db, workspace_id: uuid.UUID) -> Decimal:
    """Gross revenue (SharkBot + FlashBot) since the 1st of the current month, Brazil time."""
    from app.finance.router import _revenue_between

    now = utc_now()
    month_start = (
        now.astimezone(BRAZIL_TIME_ZONE).replace(day=1, hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
    )
    gross, *_ = await _revenue_between(db, workspace_id, month_start, now)
    return _money(gross)


def goal_progress(revenue: Decimal) -> dict:
    target = next((goal for goal in GOALS if revenue < goal), GOALS[-1])
    reached = [int(goal) for goal in GOALS if revenue >= goal]
    return {
        "target": target,
        "percent": round(float(min(revenue / target, Decimal(1)) * 100), 1),
        "prize": GOAL_PRIZES[int(target)],
        "reached": reached,
        "goals": [{"amount": int(g), "prize": GOAL_PRIZES[int(g)], "reached": revenue >= g} for g in GOALS],
    }


def _withdrawal_out(item: FinancialWithdrawal, owner: str | None = None) -> dict:
    return {
        "id": str(item.id), "amount": float(item.amount), "status": item.status, "note": item.note,
        "pix_key_type": item.pix_key_type, "pix_key": item.pix_key, "owner": owner,
        "fee": float(item.fee) if item.fee is not None else None,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "processed_at": item.processed_at.isoformat() if item.processed_at else None,
    }


@router.get("/summary")
async def summary(user: AuthenticatedUser, db: DbSession) -> dict:
    """Small payload for the floating revenue badge."""
    workspace = await owner_workspace(db, user.id)
    if workspace is None:
        return {"available": False}
    revenue = await month_revenue(db, workspace.id)
    return {"available": True, "month_revenue": float(revenue), **{k: float(v) if isinstance(v, Decimal) else v for k, v in goal_progress(revenue).items() if k in ("target", "percent", "prize")}}


def _shop_for(user: User, workspace: Workspace) -> str | None:
    """None = the platform owner's main SmokePay wallet."""
    return None if user.platform_role == "SUPER_ADMIN" else shop_ref(workspace.id)


async def _gateway_balance(shop: str | None) -> Decimal | None:
    try:
        if shop is None:
            return await smokepay.main_balance()
        value = await smokepay.shop_balance(shop)
        return value if value is not None else Decimal("0.00")
    except smokepay.SmokepayError:
        return None


async def _reconcile(db, workspace_id: uuid.UUID, shop: str | None) -> None:
    """Settle PROCESSING withdrawals with SmokePay's final status."""
    waiting = list(
        await db.scalars(
            select(FinancialWithdrawal).where(
                FinancialWithdrawal.workspace_id == workspace_id, FinancialWithdrawal.status == "PROCESSING",
                FinancialWithdrawal.gateway_withdrawal_id.is_not(None),
            )
        )
    )
    if not waiting:
        return
    try:
        remote = {p.withdrawal_id: p for p in await smokepay.withdrawals(shop)}
    except smokepay.SmokepayError:
        return
    for item in waiting:
        payout = remote.get(item.gateway_withdrawal_id or "")
        if payout is None:
            continue
        if payout.status == "completed":
            item.status, item.processed_at = "PAID", utc_now()
        elif payout.status == "failed":
            item.status, item.processed_at = "FAILED", utc_now()
            item.note = (f"SmokePay: {payout.failure_reason}" if payout.failure_reason else "Falhou na SmokePay")[:240]
    await db.commit()


@router.get("")
async def wallet(user: AuthenticatedUser, db: DbSession) -> dict:
    workspace = await _workspace_for(db, user)
    shop = _shop_for(user, workspace)
    await _reconcile(db, workspace.id, shop)
    revenue = await month_revenue(db, workspace.id)
    balance = await balances(db, user, workspace.id)
    gateway = await _gateway_balance(shop)
    history = await db.scalars(
        select(FinancialWithdrawal)
        .where(FinancialWithdrawal.workspace_id == workspace.id)
        .order_by(FinancialWithdrawal.created_at.desc())
        .limit(50)
    )
    goal = goal_progress(revenue)
    out = {k: float(v) for k, v in balance.items()}
    if gateway is not None:  # SmokePay's own number wins over our estimate
        out["available"] = float(gateway)
    fee = get_settings().smokepay_withdraw_fee
    out["withdraw_fee"] = float(fee)
    # what can actually leave: SmokePay debits the fee from the balance too
    out["withdrawable"] = float(max(Decimal("0.00"), Decimal(str(out["available"])) - fee))
    return {
        "is_main_account": shop is None,
        "shop_ref": shop,
        "balance_source": "smokepay" if gateway is not None else "estimate",
        "month_revenue": float(revenue),
        "goal": {**goal, "target": float(goal["target"])},
        **out,
        "min_withdrawal": float(MIN_WITHDRAWAL),
        "withdrawals": [_withdrawal_out(item) for item in history],
    }


def _gateway_message(exc: smokepay.SmokepayError) -> tuple[int, str]:
    if exc.status == 429:
        minutes = max(1, round((exc.cooldown_seconds or 300) / 60))
        return 429, f"A SmokePay só permite um saque a cada 5 minutos. Tente de novo em {minutes} min."
    if exc.status == 403:
        if exc.requires_kyc:
            return 422, "A conta SmokePay precisa concluir a verificação de identidade (KYC) para sacar."
        return 422, "A SmokePay recusou o saque: confira se a chave de API tem permissão de saque."
    if exc.status == 404:
        return 422, "Sua subconta ainda não recebeu nenhuma venda, então não há saldo para sacar."
    if exc.status == 400 and "insuficiente" in (exc.detail or "").lower():
        return 422, "Saldo insuficiente: a SmokePay desconta a taxa de saque do saldo. Use o botão MAX, que já desconta a taxa."
    if exc.status == 400:
        return 422, f"A SmokePay recusou o saque: {exc.detail or 'dados inválidos'}."
    return 502, "A SmokePay não conseguiu processar o saque agora. Tente de novo em alguns minutos."


@router.post("/withdrawals", status_code=201, dependencies=[Depends(require_csrf)])
async def request_withdrawal(payload: WithdrawalRequest, user: AuthenticatedUser, db: DbSession) -> dict:
    workspace = await _workspace_for(db, user)
    shop = _shop_for(user, workspace)
    amount = payload.amount.quantize(CENT)
    if shop is not None and amount < MIN_WITHDRAWAL:
        raise HTTPException(status_code=422, detail=f"O saque mínimo é R$ {MIN_WITHDRAWAL:.2f}".replace(".", ",") + ".")
    if not payload.pix_key or not payload.pix_key_type:
        raise HTTPException(status_code=422, detail="Informe a chave Pix que vai receber.")
    if await db.scalar(
        select(FinancialWithdrawal.id).where(
            FinancialWithdrawal.workspace_id == workspace.id, FinancialWithdrawal.status == "PROCESSING",
            FinancialWithdrawal.gateway_withdrawal_id.is_(None),
            FinancialWithdrawal.created_at > utc_now() - timedelta(minutes=10),
        )
    ):
        raise HTTPException(status_code=409, detail="Há um saque em andamento. Aguarde a confirmação.")
    try:
        available = await (smokepay.main_balance() if shop is None else smokepay.shop_balance(shop))
    except smokepay.SmokepayNotConfigured:
        raise HTTPException(status_code=503, detail="Saque automático não configurado no servidor.") from None
    except smokepay.SmokepayError as exc:
        status, message = _gateway_message(exc)
        raise HTTPException(status_code=status, detail=message) from None
    fee = get_settings().smokepay_withdraw_fee
    if amount + fee > (available or Decimal("0.00")):
        most = max(Decimal("0.00"), (available or Decimal("0.00")) - fee)
        raise HTTPException(
            status_code=422,
            detail=f"A SmokePay desconta {_brl(fee)} de taxa do saldo: dá para sacar até {_brl(most)}.",
        )

    # Saved first: its id is the idempotency key SmokePay uses for subaccounts.
    item = FinancialWithdrawal(
        workspace_id=workspace.id, created_by_user_id=user.id, amount=amount, note=payload.note,
        status="PROCESSING", pix_key_type=payload.pix_key_type, pix_key=payload.pix_key,
    )
    db.add(item)
    await db.commit()
    try:
        payout = await smokepay.withdraw(
            amount=amount, pix_key=payload.pix_key, pix_key_type=payload.pix_key_type,
            correlation_id=str(item.id), shop_ref=shop, sub_shop_id=str(user.id),
        )
    except smokepay.SmokepayError as exc:
        if exc.status == 0:  # no answer: the money may have left; keep it pending, never resend
            item.note = "Sem resposta da SmokePay; confira o extrato antes de tentar de novo."
            await db.commit()
            raise HTTPException(status_code=502, detail=item.note) from None
        status, message = _gateway_message(exc)
        item.status, item.processed_at, item.note = "FAILED", utc_now(), message[:240]
        await db.commit()
        raise HTTPException(status_code=status, detail=message) from None
    item.gateway_withdrawal_id = payout.withdrawal_id or None
    item.fee = payout.fee
    item.amount = payout.amount if payout.amount > 0 else amount  # SmokePay may cap it to the limit/balance
    if payout.status == "completed":
        item.status, item.processed_at = "PAID", utc_now()
    elif payout.status == "failed":
        item.status, item.processed_at = "FAILED", utc_now()
    item.processed_by_user_id = user.id
    await db.commit()
    await db.refresh(item)
    return _withdrawal_out(item)
