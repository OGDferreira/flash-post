from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from app.auth.dependencies import AuthenticatedUser, DbSession, OwnerAccess, require_csrf
from app.core.time import local_day_bounds_utc
from app.models import (
    CollaboratorPayment,
    FinancialWithdrawal,
    SharkEvent,
    User,
    Workspace,
    WorkspaceMember,
)
from app.schemas.finance import (
    DailyWithdrawalGoalUpdate,
    FinanceOperationRevenue,
    FinanceSummaryResponse,
    FinancialCollaboratorPaymentResponse,
    FinancialTransactionResponse,
    FinancialWithdrawalCreate,
    FinancialWithdrawalResponse,
)

router = APIRouter(prefix="/api/finance", tags=["Finance"])
CENT = Decimal("0.01")


def _money(value: object) -> Decimal:
    return Decimal(str(value or 0)).quantize(CENT, rounding=ROUND_HALF_UP)


def _timestamp(value: datetime) -> float:
    aware = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
    return aware.timestamp()


@router.get("", response_model=FinanceSummaryResponse)
async def get_finance_summary(
    access: OwnerAccess,
    db: DbSession,
) -> FinanceSummaryResponse:
    workspace_id = access.workspace.id
    now = datetime.now(timezone.utc)
    day_start, day_end = local_day_bounds_utc(now)

    sales = list(
        (
            await db.scalars(
                select(SharkEvent)
                .where(
                    SharkEvent.workspace_id == workspace_id,
                    SharkEvent.event_type == "pix_paid",
                    SharkEvent.operation_name.is_not(None),
                )
                .order_by(SharkEvent.occurred_at.desc(), SharkEvent.id.desc())
                .limit(100)
            )
        ).all()
    )
    gross_sales = _money(
        await db.scalar(
            select(func.coalesce(func.sum(SharkEvent.amount), 0)).where(
                SharkEvent.workspace_id == workspace_id,
                SharkEvent.event_type == "pix_paid",
                SharkEvent.operation_name.is_not(None),
            )
        )
    )
    income = _money(
        await db.scalar(
            select(
                func.coalesce(
                    func.sum(func.coalesce(SharkEvent.net_amount, SharkEvent.amount)),
                    0,
                )
            ).where(
                SharkEvent.workspace_id == workspace_id,
                SharkEvent.event_type == "pix_paid",
                SharkEvent.operation_name.is_not(None),
            )
        )
    )
    operation_rows = (
        await db.execute(
            select(
                SharkEvent.operation_name,
                func.count(SharkEvent.id),
                func.coalesce(func.sum(SharkEvent.amount), 0),
                func.coalesce(
                    func.sum(func.coalesce(SharkEvent.net_amount, SharkEvent.amount)),
                    0,
                ),
            )
            .where(
                SharkEvent.workspace_id == workspace_id,
                SharkEvent.event_type == "pix_paid",
                SharkEvent.operation_name.is_not(None),
            )
            .group_by(SharkEvent.operation_name)
            .order_by(SharkEvent.operation_name)
        )
    ).all()
    operation_revenue = [
        FinanceOperationRevenue(
            operation_name=name or "Operação Smokepay",
            sale_count=int(count),
            gross_amount=_money(gross),
            net_amount=_money(net),
        )
        for name, count, gross, net in operation_rows
    ]

    withdrawals = list(
        (
            await db.scalars(
                select(FinancialWithdrawal)
                .where(FinancialWithdrawal.workspace_id == workspace_id)
                .order_by(
                    FinancialWithdrawal.created_at.desc(),
                    FinancialWithdrawal.id.desc(),
                )
            )
        ).all()
    )
    total_withdrawals = _money(
        await db.scalar(
            select(func.coalesce(func.sum(FinancialWithdrawal.amount), 0)).where(
                FinancialWithdrawal.workspace_id == workspace_id
            )
        )
    )
    withdrawals_today = _money(
        await db.scalar(
            select(func.coalesce(func.sum(FinancialWithdrawal.amount), 0)).where(
                FinancialWithdrawal.workspace_id == workspace_id,
                FinancialWithdrawal.created_at >= day_start,
                FinancialWithdrawal.created_at < day_end,
            )
        )
    )

    payment_rows = list(
        (
            await db.execute(
                select(CollaboratorPayment, User)
                .join(
                    WorkspaceMember,
                    WorkspaceMember.id == CollaboratorPayment.workspace_member_id,
                )
                .join(User, User.id == WorkspaceMember.user_id)
                .where(CollaboratorPayment.workspace_id == workspace_id)
                .order_by(
                    CollaboratorPayment.paid_at.desc(),
                    CollaboratorPayment.id.desc(),
                )
            )
        ).all()
    )
    total_collaborator_payments = _money(
        await db.scalar(
            select(func.coalesce(func.sum(CollaboratorPayment.amount), 0)).where(
                CollaboratorPayment.workspace_id == workspace_id
            )
        )
    )

    withdrawal_history = [
        FinancialWithdrawalResponse(
            id=item.id,
            amount=item.amount,
            note=item.note,
            created_at=item.created_at,
        )
        for item in withdrawals
    ]
    collaborator_history = [
        FinancialCollaboratorPaymentResponse(
            id=payment.id,
            collaborator_name=user.nickname or user.full_name,
            amount=payment.amount,
            period_start=payment.period_start,
            paid_at=payment.paid_at,
        )
        for payment, user in payment_rows
    ]
    transactions = [
        FinancialTransactionResponse(
            id=f"sale:{sale.id}",
            kind="sale",
            direction="inflow",
            description=f"Venda Smokepay · {sale.operation_name}",
            amount=_money(sale.net_amount if sale.net_amount is not None else sale.amount),
            occurred_at=sale.occurred_at,
        )
        for sale in sales
    ]
    transactions.extend(
        FinancialTransactionResponse(
            id=f"withdrawal:{item.id}",
            kind="withdrawal",
            direction="outflow",
            description=item.note or "Saque do administrador",
            amount=_money(item.amount),
            occurred_at=item.created_at,
        )
        for item in withdrawals
    )
    transactions.extend(
        FinancialTransactionResponse(
            id=f"collaborator-payment:{payment.id}",
            kind="collaborator_payment",
            direction="outflow",
            description=f"Pagamento · {user.nickname or user.full_name}",
            amount=_money(payment.amount),
            occurred_at=payment.paid_at,
        )
        for payment, user in payment_rows
    )
    transactions.sort(key=lambda item: _timestamp(item.occurred_at), reverse=True)

    return FinanceSummaryResponse(
        gross_sales=gross_sales,
        income=income,
        withdrawals=total_withdrawals,
        collaborator_payments=total_collaborator_payments,
        balance=_money(income - total_withdrawals - total_collaborator_payments),
        withdrawals_today=withdrawals_today,
        daily_withdrawal_goal=access.workspace.daily_withdrawal_goal,
        operation_revenue=operation_revenue,
        transactions=transactions[:100],
        withdrawal_history=withdrawal_history,
        collaborator_payment_history=collaborator_history,
    )


@router.post(
    "/withdrawals",
    response_model=FinancialWithdrawalResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
async def register_financial_withdrawal(
    payload: FinancialWithdrawalCreate,
    user: AuthenticatedUser,
    access: OwnerAccess,
    db: DbSession,
) -> FinancialWithdrawalResponse:
    withdrawal = FinancialWithdrawal(
        workspace_id=access.workspace.id,
        created_by_user_id=user.id,
        amount=payload.amount.quantize(CENT, rounding=ROUND_HALF_UP),
        note=payload.note,
    )
    db.add(withdrawal)
    try:
        await db.commit()
        await db.refresh(withdrawal)
    except SQLAlchemyError:
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Não foi possível registrar o saque.",
        ) from None
    return FinancialWithdrawalResponse(
        id=withdrawal.id,
        amount=withdrawal.amount,
        note=withdrawal.note,
        created_at=withdrawal.created_at,
    )


@router.put(
    "/daily-withdrawal-goal",
    response_model=FinanceSummaryResponse,
    dependencies=[Depends(require_csrf)],
)
async def update_daily_withdrawal_goal(
    payload: DailyWithdrawalGoalUpdate,
    access: OwnerAccess,
    db: DbSession,
) -> FinanceSummaryResponse:
    workspace = await db.get(Workspace, access.workspace.id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace não encontrado.")
    workspace.daily_withdrawal_goal = payload.amount.quantize(CENT, rounding=ROUND_HALF_UP)
    await db.commit()
    await db.refresh(workspace)
    return await get_finance_summary(access, db)
