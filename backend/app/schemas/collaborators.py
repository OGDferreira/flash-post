from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.core.nickname import normalize_nickname


class CollaboratorCreateRequest(BaseModel):
    full_name: str = Field(min_length=1, max_length=160)
    nickname: str
    email: EmailStr
    password: str = Field(min_length=8, max_length=256)
    rate_per_connection: Decimal = Field(ge=0, max_digits=10, decimal_places=2)
    daily_connection_goal: int = Field(ge=0, le=100000)
    monthly_connection_goal: int = Field(ge=0, le=1000000)
    monthly_bonus: Decimal = Field(ge=0, max_digits=10, decimal_places=2)

    @field_validator("full_name")
    @classmethod
    def normalize_full_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Informe o nome completo.")
        return cleaned

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: object) -> object:
        return value.strip().casefold() if isinstance(value, str) else value

    @field_validator("nickname")
    @classmethod
    def validate_nickname(cls, value: str) -> str:
        return normalize_nickname(value)

    @field_validator("rate_per_connection", "monthly_bonus")
    @classmethod
    def quantize_money(cls, value: Decimal) -> Decimal:
        return value.quantize(Decimal("0.01"))


class CollaboratorUpdateRequest(BaseModel):
    rate_per_connection: Decimal = Field(ge=0, max_digits=10, decimal_places=2)
    daily_connection_goal: int = Field(ge=0, le=100000)
    monthly_connection_goal: int = Field(ge=0, le=1000000)
    monthly_bonus: Decimal = Field(ge=0, max_digits=10, decimal_places=2)
    apply_rate_to_existing_accounts: bool = False

    @field_validator("rate_per_connection", "monthly_bonus")
    @classmethod
    def quantize_money(cls, value: Decimal) -> Decimal:
        return value.quantize(Decimal("0.01"))


class CollaboratorAccessRequest(BaseModel):
    enabled: bool


class CollaboratorPaymentResponse(BaseModel):
    id: UUID
    amount: Decimal
    period_start: date
    paid_at: datetime


class CollaboratorAccountEarning(BaseModel):
    account_id: UUID
    username: str
    connected_at: datetime | None
    rate_per_connection: Decimal


class CollaboratorReportItem(BaseModel):
    member_id: UUID
    user_id: UUID
    membership_started_at: datetime
    access_status: Literal["ACTIVE", "SUSPENDED"]
    full_name: str
    nickname: str
    email: EmailStr
    rate_per_connection: Decimal
    daily_connection_goal: int
    monthly_connection_goal: int
    monthly_bonus: Decimal
    connections_today: int
    connections_month: int
    earnings_today: Decimal
    earnings_month: Decimal
    paid_month: Decimal
    due_month: Decimal
    projected_month: Decimal
    recent_days: list[int]
    recent_earnings: list[Decimal]
    account_earnings: list[CollaboratorAccountEarning]


class CollaboratorsResponse(BaseModel):
    collaborators: list[CollaboratorReportItem]
    owner_connections_today: int
    team_connections_today: int


class CollaboratorRankingItem(BaseModel):
    user_id: UUID
    full_name: str
    nickname: str
    connections: int
    average_daily_connections: Decimal
    position: int


class CollaboratorRankingResponse(BaseModel):
    month: str
    period: str
    days_in_period: int
    total_connections: int
    collaborators: list[CollaboratorRankingItem]


class CollaboratorDashboardResponse(BaseModel):
    full_name: str
    nickname: str
    avatar_url: str | None
    rate_per_connection: Decimal
    daily_connection_goal: int
    monthly_connection_goal: int
    monthly_bonus: Decimal
    connections_today: int
    connections_month: int
    earnings_today: Decimal
    earnings_month: Decimal
    paid_month: Decimal
    due_month: Decimal
    paid_total: Decimal
    projected_month: Decimal
    daily_progress: int
    monthly_progress: int
    recent_days: list[int]
    recent_earnings: list[Decimal]
    recent_payments: list[Decimal]
    account_earnings: list[CollaboratorAccountEarning]


class CollaboratorPaymentActionResponse(BaseModel):
    message: str
    payment: CollaboratorPaymentResponse
