"""Wallet: revenue, balance to withdraw, withdrawals and revenue goals.

Money from FlashBot sales sits in SmokePay: the platform owner's main account
(Super Admin) or each operation's subaccount. The balance shown here is what
the sales left for this user after fees and the partner split, minus what was
withdrawn or is waiting. Partners/users *request* a withdrawal; the Super
Admin pays it in SmokePay and marks it paid. Amounts always come from the
database, never from the browser.
"""

import uuid
from datetime import timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select

from app.auth.dependencies import AuthenticatedUser, DbSession, SuperAdminUser, require_csrf
from app.core.time import BRAZIL_TIME_ZONE, utc_now
from app.models import FinancialWithdrawal, TgOrder, User, Workspace
from app.partners.service import notify_user, owner_workspace

router = APIRouter(prefix="/api/wallet", tags=["Wallet"])

CENT = Decimal("0.01")
MIN_WITHDRAWAL = Decimal("10.00")
GOALS = [Decimal(v) for v in ("10000", "50000", "100000", "500000", "1000000")]
GOAL_PRIZES = {10000: "Pulseira", 50000: "Caneca", 100000: "Placa", 500000: "Placa", 1000000: "Quadro, cordão e pingente de ouro"}


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


class Decision(BaseModel):
    action: Literal["paid", "rejected"]
    note: str | None = Field(default=None, max_length=240)


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
    withdrawn, pending = _money(sums.get("PAID")), _money(sums.get("REQUESTED"))
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


@router.get("")
async def wallet(user: AuthenticatedUser, db: DbSession) -> dict:
    workspace = await _workspace_for(db, user)
    revenue = await month_revenue(db, workspace.id)
    balance = await balances(db, user, workspace.id)
    history = await db.scalars(
        select(FinancialWithdrawal)
        .where(FinancialWithdrawal.workspace_id == workspace.id)
        .order_by(FinancialWithdrawal.created_at.desc())
        .limit(50)
    )
    goal = goal_progress(revenue)
    return {
        "is_main_account": user.platform_role == "SUPER_ADMIN",
        "month_revenue": float(revenue),
        "goal": {**goal, "target": float(goal["target"])},
        **{k: float(v) for k, v in balance.items()},
        "min_withdrawal": float(MIN_WITHDRAWAL),
        "withdrawals": [_withdrawal_out(item) for item in history],
    }


@router.post("/withdrawals", status_code=201, dependencies=[Depends(require_csrf)])
async def request_withdrawal(payload: WithdrawalRequest, user: AuthenticatedUser, db: DbSession) -> dict:
    workspace = await _workspace_for(db, user)
    balance = await balances(db, user, workspace.id)
    amount = payload.amount.quantize(CENT)
    main_account = user.platform_role == "SUPER_ADMIN"
    if not main_account:
        if amount < MIN_WITHDRAWAL:
            raise HTTPException(status_code=422, detail=f"O saque mínimo é R$ {MIN_WITHDRAWAL:.2f}.".replace(".", ","))
        if not payload.pix_key or not payload.pix_key_type:
            raise HTTPException(status_code=422, detail="Informe a chave Pix que vai receber.")
    if amount > balance["available"]:
        raise HTTPException(status_code=422, detail="Valor maior que o saldo disponível.")
    item = FinancialWithdrawal(
        workspace_id=workspace.id, created_by_user_id=user.id, amount=amount, note=payload.note,
        # The platform owner withdraws in SmokePay itself and only records it here.
        status="PAID" if main_account else "REQUESTED",
        pix_key_type=payload.pix_key_type, pix_key=payload.pix_key,
        processed_at=utc_now() if main_account else None,
        processed_by_user_id=user.id if main_account else None,
    )
    db.add(item)
    if not main_account:
        admins = list(await db.scalars(select(User.id).where(User.platform_role == "SUPER_ADMIN", User.is_active.is_(True))))
        for admin_id in admins:
            await notify_user(
                db, admin_id, "withdrawal-request", "Novo pedido de saque",
                f"{user.full_name} pediu R$ {amount:.2f} via Pix.".replace(".", ","), "/carteira",
            )
    await db.commit()
    await db.refresh(item)
    return _withdrawal_out(item)


@router.delete("/withdrawals/{withdrawal_id}", status_code=204, dependencies=[Depends(require_csrf)])
async def cancel_withdrawal(withdrawal_id: uuid.UUID, user: AuthenticatedUser, db: DbSession) -> None:
    workspace = await _workspace_for(db, user)
    item = await db.scalar(
        select(FinancialWithdrawal).where(
            FinancialWithdrawal.id == withdrawal_id, FinancialWithdrawal.workspace_id == workspace.id
        )
    )
    if item is None or item.status != "REQUESTED":
        raise HTTPException(status_code=404, detail="Pedido não encontrado ou já processado.")
    await db.delete(item)
    await db.commit()


# ------------------------------------------------------------------ super admin


@router.get("/requests")
async def pending_requests(_admin: SuperAdminUser, db: DbSession) -> dict:
    rows = (
        await db.execute(
            select(FinancialWithdrawal, User.full_name)
            .join(Workspace, Workspace.id == FinancialWithdrawal.workspace_id)
            .join(User, User.id == Workspace.owner_id)
            .where(FinancialWithdrawal.status == "REQUESTED")
            .order_by(FinancialWithdrawal.created_at)
        )
    ).all()
    out = []
    for item, name in rows:
        data = _withdrawal_out(item, name)
        workspace = await db.get(Workspace, item.workspace_id)
        owner = await db.get(User, workspace.owner_id) if workspace else None
        data["shop_ref"] = f"fp-{item.workspace_id.hex}"
        data["owner_available"] = float((await balances(db, owner, item.workspace_id))["available"] + item.amount) if owner else None
        out.append(data)
    return {"items": out}


@router.post("/requests/{withdrawal_id}", dependencies=[Depends(require_csrf)])
async def decide_request(withdrawal_id: uuid.UUID, payload: Decision, admin: SuperAdminUser, db: DbSession) -> dict:
    item = await db.get(FinancialWithdrawal, withdrawal_id)
    if item is None or item.status != "REQUESTED":
        raise HTTPException(status_code=404, detail="Pedido não encontrado ou já processado.")
    item.status = "PAID" if payload.action == "paid" else "REJECTED"
    item.processed_at = utc_now()
    item.processed_by_user_id = admin.id
    if payload.note:
        item.note = payload.note
    workspace = await db.get(Workspace, item.workspace_id)
    if workspace is not None:
        paid = payload.action == "paid"
        await notify_user(
            db, workspace.owner_id, "withdrawal-" + payload.action,
            "Saque pago ✅" if paid else "Saque recusado",
            (f"R$ {item.amount:.2f} foi enviado para sua chave Pix." if paid
             else f"O pedido de R$ {item.amount:.2f} foi recusado. {payload.note or ''}").replace(".", ",", 1),
            "/carteira",
        )
    await db.commit()
    return _withdrawal_out(item)
