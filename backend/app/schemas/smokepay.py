from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class SmokepayOperationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    split_percent: Decimal = Field(
        default=Decimal("100.00"),
        ge=0,
        le=100,
        max_digits=5,
        decimal_places=2,
    )

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        name = value.strip()
        if not name:
            raise ValueError("Informe o nome da operação.")
        return name


class SmokepayOperationUpdate(SmokepayOperationCreate):
    is_active: bool = True


class SmokepayOperationResponse(BaseModel):
    id: UUID
    name: str
    split_percent: Decimal
    is_active: bool
    webhook_url: str
    created_at: datetime
    updated_at: datetime


class SmokepayOperationsResponse(BaseModel):
    operations: list[SmokepayOperationResponse]


class SmokepayWebhookResult(BaseModel):
    accepted: int
    duplicates: int
    ignored: int


class SmokepayOperationRevenue(BaseModel):
    operation_id: UUID
    name: str
    split_percent: Decimal
    sale_count: int
    gross_amount: Decimal
    net_amount: Decimal


class SmokepaySaleItem(BaseModel):
    id: UUID
    operation_id: UUID
    operation_name: str
    transaction_id: str | None
    customer_name: str | None
    plan_name: str | None
    gross_amount: Decimal
    net_amount: Decimal
    occurred_at: datetime


class SmokepayFinanceSummary(BaseModel):
    day: str
    daily_goal: Decimal
    gross_total: Decimal
    net_total: Decimal
    sale_count: int
    operations: list[SmokepayOperationRevenue]
    recent_sales: list[SmokepaySaleItem]


class SmokepayDailyGoalUpdate(BaseModel):
    daily_goal: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
