import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.models import Base


class EmailAccount(Base):
    __tablename__ = "email_accounts"
    __table_args__ = (
        CheckConstraint(
            "status IN ('available', 'in_use', 'completed', 'error', 'returned')",
            name="ck_email_accounts_status",
        ),
        Index("ix_email_accounts_workspace_status", "workspace_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    supplier: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    encrypted_password: Mapped[str] = mapped_column(String(4096), nullable=False)
    responsible: Mapped[str | None] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="available", server_default="available"
    )
    observation: Mapped[str | None] = mapped_column(Text)
    encrypted_two_factor_code: Mapped[str] = mapped_column(
        String(4096), nullable=False
    )
    encrypted_two_factor_password: Mapped[str | None] = mapped_column(String(4096))
    error_attachment_path: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
