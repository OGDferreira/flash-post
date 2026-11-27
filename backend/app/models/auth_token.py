import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.models import Base


class AuthToken(Base):
    """One-time tokens for email verification and password reset."""

    __tablename__ = "auth_tokens"
    __table_args__ = (
        Index("ix_auth_tokens_token_hash", "token_hash", unique=True),
        Index("ix_auth_tokens_user_type", "user_id", "token_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # "email_verification" or "password_reset"
    token_type: Mapped[str] = mapped_column(String(32), nullable=False)
    # SHA-256 hex of the raw token (never store the raw value)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
