"""Platform access subscription (owner pays to keep using FlashPost).

Distinct from TgSubscription, which is a recurring *product* sold through a bot
funnel. These models bill the operation owner for access to the platform:

- PlatformPlan: the weekly/monthly/annual plans, priced by the Super Admin.
- PlatformSubscription: one row per owner, with the current access window.
- PlatformSubscriptionCharge: each billing cycle's PIX charge (SmokePay).
- PlatformLiberationCode: a code the Super Admin hands out for free access.

SmokePay only does PIX (no card auto-debit), so "automatic billing" means a
fresh PIX is generated each cycle and the webhook extends access when it's paid.
"""
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.models import Base

# Status values for a subscription's access window.
SUB_TRIALING = "trialing"
SUB_ACTIVE = "active"
SUB_PAST_DUE = "past_due"
SUB_CANCELED = "canceled"

CHARGE_PENDING = "pending"
CHARGE_PAID = "paid"
CHARGE_EXPIRED = "expired"
CHARGE_CANCELED = "canceled"


class PlatformPlan(Base):
    __tablename__ = "platform_plans"
    __table_args__ = (
        CheckConstraint("price >= 0", name="ck_platform_plans_price"),
        CheckConstraint("period_days > 0", name="ck_platform_plans_period"),
        UniqueConstraint("code", name="uq_platform_plans_code"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Stable key: "weekly" | "monthly" | "annual" (what the UI groups by).
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal("0"))
    period_days: Mapped[int] = mapped_column(Integer, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class PlatformSubscription(Base):
    __tablename__ = "platform_subscriptions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('trialing', 'active', 'past_due', 'canceled')",
            name="ck_platform_subscriptions_status",
        ),
        UniqueConstraint("user_id", name="uq_platform_subscriptions_user"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # The operation owner who pays. Collaborators/partners don't get a row.
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=SUB_TRIALING)
    plan_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("platform_plans.id", ondelete="SET NULL")
    )
    # End of the free trial and of the current paid window; access = the later of
    # the two is still in the future (and status not canceled).
    trial_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class PlatformSubscriptionCharge(Base):
    __tablename__ = "platform_subscription_charges"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'paid', 'expired', 'canceled')",
            name="ck_platform_sub_charges_status",
        ),
        UniqueConstraint("external_id", name="uq_platform_sub_charges_external_id"),
        Index("ix_platform_sub_charges_subscription", "subscription_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    subscription_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("platform_subscriptions.id", ondelete="CASCADE"), nullable=False
    )
    plan_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("platform_plans.id", ondelete="SET NULL")
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    period_days: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=CHARGE_PENDING)
    # SmokePay idempotency key for this charge, and the PIX it returned.
    external_id: Mapped[str] = mapped_column(String(80), nullable=False)
    pix_copy_paste: Mapped[str | None] = mapped_column(Text)
    pix_txid: Mapped[str | None] = mapped_column(String(140))
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class PlatformLiberationCode(Base):
    __tablename__ = "platform_liberation_codes"
    __table_args__ = (
        CheckConstraint("days > 0", name="ck_platform_liberation_days"),
        UniqueConstraint("code", name="uq_platform_liberation_code"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    # Free access granted when redeemed, in days.
    days: Mapped[int] = mapped_column(Integer, nullable=False)
    note: Mapped[str | None] = mapped_column(String(160))
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    redeemed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    redeemed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Optional deadline for redeeming the code (null = never expires).
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
