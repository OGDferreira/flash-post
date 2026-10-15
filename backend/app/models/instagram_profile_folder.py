import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.models import Base


class InstagramProfileFolder(Base):
    __tablename__ = "instagram_profile_folders"
    __table_args__ = (
        UniqueConstraint("workspace_id", "name", name="uq_instagram_profile_folders_name"),
        Index("ix_instagram_profile_folders_workspace_id", "workspace_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    color: Mapped[str] = mapped_column(String(7), nullable=False, default="#00c9d8")
    # Auto-detect: new connected accounts whose @username starts with one of
    # these prefixes are filed here. `auto_enabled` is the on/off switch.
    auto_prefixes: Mapped[list] = mapped_column(
        JSON, nullable=False, default=list, server_default=text("'[]'")
    )
    auto_enabled: Mapped[bool] = mapped_column(
        nullable=False, default=True, server_default=text("true")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
