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
    text,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.models import Base


class InstagramAccount(Base):
    __tablename__ = "instagram_accounts"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "instagram_user_id",
            name="uq_instagram_accounts_workspace_user",
        ),
        CheckConstraint(
            "status IN ('connected', 'disconnected', 'error')",
            name="ck_instagram_accounts_status",
        ),
        Index("ix_instagram_accounts_workspace_id", "workspace_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    profile_folder_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("instagram_profile_folders.id", ondelete="SET NULL")
    )
    connected_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    first_connected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    collaborator_rate_at_connection: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2)
    )
    app_credential_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("instagram_meta_apps.id", ondelete="SET NULL"),
    )
    instagram_user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    username: Mapped[str] = mapped_column(String(100), nullable=False)
    profile_picture_url: Mapped[str | None] = mapped_column(String(2048))
    follower_count: Mapped[int | None] = mapped_column()
    media_count: Mapped[int | None] = mapped_column()
    encrypted_access_token: Mapped[str | None] = mapped_column(String(2048))
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'connected'")
    )
    has_highlights: Mapped[bool] = mapped_column(
        nullable=False, default=False, server_default=text("false")
    )
    token_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    token_refresh_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    connected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
