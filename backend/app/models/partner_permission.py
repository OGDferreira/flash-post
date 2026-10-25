"""Permissões granulares para sócios (partners) por plataforma."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.models import Base


class PartnerPermission(Base):
    """Permissões individuais de um sócio para Flash Post e Flash Bot."""

    __tablename__ = "partner_permissions"
    __table_args__ = (
        CheckConstraint("platform IN ('flashpost', 'flashbot')", name="ck_partner_permissions_platform"),
        Index("uq_partner_permissions_user_platform", "user_id", "platform", unique=True),
        Index("ix_partner_permissions_user", "user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    platform: Mapped[str] = mapped_column(String(16), nullable=False)  # 'flashpost' | 'flashbot'

    # Flash Post permissions
    can_view_dashboard: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    can_view_ranking: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    can_view_accounts: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    can_view_meta_apps: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    can_view_settings: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    can_view_contact: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")

    # Flash Bot permissions
    can_view_bot_dashboard: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    can_view_leads: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    can_view_wallets: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")

    # Metadata for future extensibility
    extra_permissions: Mapped[dict | None] = mapped_column(JSONB)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class FeeChangeLog(Base):
    """Histórico de alterações na taxa de transação (transaction_fee) dos usuários."""

    __tablename__ = "fee_change_logs"
    __table_args__ = (
        Index("ix_fee_change_logs_user", "user_id"),
        Index("ix_fee_change_logs_changed_by", "changed_by_user_id"),
        Index("ix_fee_change_logs_created", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    changed_by_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # Previous and new fee values (in BRL)
    old_fee: Mapped[float | None] = mapped_column()  # None means platform default
    new_fee: Mapped[float | None] = mapped_column()  # None means platform default

    # Whether this was a global change
    is_global_change: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")

    # Reason/notes for the change
    reason: Mapped[str | None] = mapped_column(String(500))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
