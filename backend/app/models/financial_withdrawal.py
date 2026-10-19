import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.models import Base


class FinancialWithdrawal(Base):
    __tablename__ = "financial_withdrawals"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_financial_withdrawals_amount_positive"),
        CheckConstraint(
            "status IN ('PAID', 'REQUESTED', 'REJECTED', 'PROCESSING', 'FAILED')", name="ck_financial_withdrawals_status"
        ),
        Index("ix_financial_withdrawals_workspace_created_at", "workspace_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    note: Mapped[str | None] = mapped_column(String(240))
    # PAID = money already out (owner records it, or Super Admin paid a request);
    # REQUESTED = a partner/user asked to withdraw their subaccount balance.
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="PAID", server_default="PAID")
    pix_key_type: Mapped[str | None] = mapped_column(String(16))
    pix_key: Mapped[str | None] = mapped_column(String(140))
    # Automatic payout through SmokePay: its withdrawal id and fee.
    gateway_withdrawal_id: Mapped[str | None] = mapped_column(String(64))
    # Pix end-to-end id from SmokePay: the bank receipt that traces where the money went.
    gateway_e2e_id: Mapped[str | None] = mapped_column(String(64))
    fee: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
