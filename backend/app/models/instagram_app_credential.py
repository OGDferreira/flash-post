import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.models import Base


class InstagramAppCredential(Base):
    __tablename__ = "instagram_meta_apps"
    __table_args__ = (
        UniqueConstraint("workspace_id", "app_id", name="uq_instagram_meta_apps_workspace_app"),
        Index(
            "uq_instagram_meta_apps_selected_workspace",
            "workspace_id",
            unique=True,
            postgresql_where=text("is_selected = true"),
            sqlite_where=text("is_selected = 1"),
        ),
        Index("ix_instagram_meta_apps_workspace_id", "workspace_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    meta_app_name: Mapped[str] = mapped_column(String(160), nullable=False)
    app_id: Mapped[str] = mapped_column(String(64), nullable=False)
    category: Mapped[str | None] = mapped_column(String(120))
    app_link: Mapped[str | None] = mapped_column(String(2048))
    encrypted_app_secret: Mapped[str] = mapped_column(String(2048), nullable=False)
    is_selected: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    revision: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False, default=uuid.uuid4
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
