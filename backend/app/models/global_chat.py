"""Global chat shared by every platform user. Messages self-destruct after 36h."""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    LargeBinary,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, deferred, mapped_column
from sqlalchemy.types import Uuid

from app.models import Base

# How long a message stays visible before the cleanup job removes it.
MESSAGE_TTL_HOURS = 36


class GlobalChatMessage(Base):
    __tablename__ = "global_chat_messages"
    __table_args__ = (
        CheckConstraint(
            "body IS NOT NULL OR image_data IS NOT NULL",
            name="ck_global_chat_body_or_image",
        ),
        Index("ix_global_chat_created_at", "created_at"),
        Index("ix_global_chat_expires_at", "expires_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # The author; their messages go with the account if it is deleted.
    author_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # Name and avatar are snapshotted so the message list never joins users.
    author_nickname: Mapped[str] = mapped_column(String(40), nullable=False)
    author_avatar_url: Mapped[str | None] = mapped_column(String(2048))
    body: Mapped[str | None] = mapped_column(Text)
    # Photos are small and short-lived, so they live in the row and vanish with it.
    image_data: Mapped[bytes | None] = deferred(mapped_column(LargeBinary))
    image_content_type: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
