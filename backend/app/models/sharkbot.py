"""SharkBot entities derived from webhook events.

``shark_events`` stays as the raw event log. Dashboards read these tables,
where every lead and every payment exists once no matter how many times (or in
which order) SharkBot delivers the events about it.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.models import Base


class SharkLead(Base):
    __tablename__ = "shark_leads"
    __table_args__ = (
        UniqueConstraint("workspace_id", "lead_key", name="uq_shark_leads_workspace_key"),
        Index("ix_shark_leads_workspace_joined", "workspace_id", "joined_at"),
        Index("ix_shark_leads_workspace_bot", "workspace_id", "bot_id", "flow_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    # bot id + customer id (or telegram id); identifies the lead within a bot.
    lead_key: Mapped[str] = mapped_column(String(240), nullable=False)
    bot_id: Mapped[str | None] = mapped_column(String(120))
    bot_name: Mapped[str | None] = mapped_column(String(160))
    flow_id: Mapped[str | None] = mapped_column(String(120))
    flow_name: Mapped[str | None] = mapped_column(String(160))
    customer_id: Mapped[str | None] = mapped_column(String(120))
    telegram_id: Mapped[str | None] = mapped_column(String(64))
    customer_name: Mapped[str | None] = mapped_column(String(240))
    customer_username: Mapped[str | None] = mapped_column(String(120))
    # Set only when the webhook URL carried a verified account of the workspace.
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("instagram_accounts.id", ondelete="SET NULL")
    )
    # Which SharkBot account (webhook URL) delivered the first event; None = main URL.
    shark_account_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("shark_accounts.id", ondelete="SET NULL")
    )
    utm_source: Mapped[str | None] = mapped_column(String(120))
    utm_campaign: Mapped[str | None] = mapped_column(String(160))
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    first_received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class SharkTransaction(Base):
    __tablename__ = "shark_transactions"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "transaction_key", name="uq_shark_transactions_workspace_key"
        ),
        CheckConstraint("status IN ('pending', 'paid')", name="ck_shark_transactions_status"),
        Index("ix_shark_transactions_workspace_created", "workspace_id", "created_at_source"),
        Index("ix_shark_transactions_workspace_paid", "workspace_id", "paid_at"),
        Index("ix_shark_transactions_workspace_bot", "workspace_id", "bot_id", "flow_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    transaction_key: Mapped[str] = mapped_column(String(240), nullable=False)
    transaction_id: Mapped[str | None] = mapped_column(String(160))
    external_id: Mapped[str | None] = mapped_column(String(160))
    # pending = PIX generated, not paid. paid never goes back to pending.
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    # None when SharkBot did not send a valid amount (never assumed to be 0).
    amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    currency: Mapped[str | None] = mapped_column(String(8))
    gateway: Mapped[str | None] = mapped_column(String(60))
    payment_method: Mapped[str | None] = mapped_column(String(40))
    plan_name: Mapped[str | None] = mapped_column(String(160))
    sales_code: Mapped[str | None] = mapped_column(String(120))
    bot_id: Mapped[str | None] = mapped_column(String(120))
    bot_name: Mapped[str | None] = mapped_column(String(160))
    flow_id: Mapped[str | None] = mapped_column(String(120))
    flow_name: Mapped[str | None] = mapped_column(String(160))
    customer_id: Mapped[str | None] = mapped_column(String(120))
    customer_name: Mapped[str | None] = mapped_column(String(240))
    customer_username: Mapped[str | None] = mapped_column(String(120))
    # Same key as SharkLead.lead_key, used for lead -> buyer cohorts.
    lead_key: Mapped[str | None] = mapped_column(String(240))
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("instagram_accounts.id", ondelete="SET NULL")
    )
    shark_account_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("shark_accounts.id", ondelete="SET NULL")
    )
    utm_source: Mapped[str | None] = mapped_column(String(120))
    utm_campaign: Mapped[str | None] = mapped_column(String(160))
    # When the PIX was generated / approved (from the payload when present).
    created_at_source: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
