from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class FinancialWithdrawalCreate(BaseModel):
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    note: str | None = Field(default=None, max_length=240)

    @field_validator("note")
    @classmethod
    def normalize_note(cls, value: str | None) -> str | None:
        if value is None:
            return None
        note = value.strip()
        return note or None


class DailyWithdrawalGoalUpdate(BaseModel):
    amount: Decimal = Field(ge=0, max_digits=12, decimal_places=2)


class FinancialWithdrawalResponse(BaseModel):
    id: UUID
    amount: Decimal
    note: str | None
    created_at: datetime


class FinancialCollaboratorPaymentResponse(BaseModel):
    id: UUID
    collaborator_name: str
    amount: Decimal
    period_start: date
    paid_at: datetime


class FinancialTransactionResponse(BaseModel):
    id: str
    kind: Literal["sale", "withdrawal", "collaborator_payment"]
    direction: Literal["inflow", "outflow"]
    description: str
    amount: Decimal
    occurred_at: datetime


class FinanceOperationRevenue(BaseModel):
    operation_name: str
    sale_count: int
    gross_amount: Decimal
    net_amount: Decimal


class FinanceSummaryResponse(BaseModel):
    gross_sales: Decimal
    income: Decimal
    withdrawals: Decimal
    collaborator_payments: Decimal
    balance: Decimal
    withdrawals_today: Decimal
    daily_withdrawal_goal: Decimal
    operation_revenue: list[FinanceOperationRevenue]
    transactions: list[FinancialTransactionResponse]
    withdrawal_history: list[FinancialWithdrawalResponse]
    collaborator_payment_history: list[FinancialCollaboratorPaymentResponse]
