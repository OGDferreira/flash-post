"""IG Extension config — per-workspace password and profile settings."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.models import Base


class IgExtensionConfig(Base):
    __tablename__ = "ig_extension_configs"
    __table_args__ = (UniqueConstraint("workspace_id", name="uq_ig_extension_workspace"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    # Auth
    password_hash: Mapped[str | None] = mapped_column(String(255))
    config_token: Mapped[str | None] = mapped_column(String(64))

    # Profile fields
    full_name: Mapped[str | None] = mapped_column(String(200))
    username: Mapped[str | None] = mapped_column(String(100))
    bio: Mapped[str | None] = mapped_column(String(500))
    profile_photo_url: Mapped[str | None] = mapped_column(Text)
    story_photo_url: Mapped[str | None] = mapped_column(Text)

    # Sticker / link
    link_url: Mapped[str | None] = mapped_column(Text)
    sticker_text: Mapped[str | None] = mapped_column(String(200))
    highlight_title: Mapped[str | None] = mapped_column(String(100))
    sticker_size: Mapped[float | None] = mapped_column(Float)
    sticker_x: Mapped[float | None] = mapped_column(Float)
    sticker_y: Mapped[float | None] = mapped_column(Float)
    sticker_rotation: Mapped[float | None] = mapped_column(Float)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
