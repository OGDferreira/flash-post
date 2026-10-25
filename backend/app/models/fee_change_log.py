"""Historical transaction-fee changes."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.models import Base


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
