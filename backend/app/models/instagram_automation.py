import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON, Uuid

from app.models import Base

_JSON = JSON().with_variant(JSONB, "postgresql")


class InstagramCommentAutomation(Base):
    """A ManyChat-style rule: when a comment (or DM) matches a keyword, reply on
    the comment and/or send a DM. Lives on a workspace; an optional
    ``instagram_account_id`` scopes it to one account (null = every account of the
    workspace), and an optional ``media_id`` scopes a comment rule to one post."""

    __tablename__ = "instagram_automations"
    __table_args__ = (
        CheckConstraint(
            "trigger_type IN ('comment', 'dm')",
            name="ck_instagram_automations_trigger",
        ),
        CheckConstraint(
            "match_mode IN ('any', 'exact')",
            name="ck_instagram_automations_match",
        ),
        Index("ix_instagram_automations_workspace", "workspace_id"),
        Index("ix_instagram_automations_account", "instagram_account_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    instagram_account_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("instagram_accounts.id", ondelete="CASCADE"),
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    trigger_type: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'comment'")
    )
    # Lower-cased keywords; an empty list matches any comment/DM.
    keywords: Mapped[list[str]] = mapped_column(_JSON, nullable=False, default=list)
    match_mode: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'any'")
    )
    # Comment rules only: restrict to a single post (Instagram media id); null = all.
    media_id: Mapped[str | None] = mapped_column(String(191))

    public_reply_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    # One is picked at random per fire, so repeated public replies look less spammy.
    public_replies: Mapped[list[str]] = mapped_column(_JSON, nullable=False, default=list)

    dm_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    dm_text: Mapped[str | None] = mapped_column(Text)
    # [{"label": str, "url": str}] rendered as a button template on the DM.
    dm_buttons: Mapped[list[dict[str, Any]]] = mapped_column(
        _JSON, nullable=False, default=list
    )

    fired_count: Mapped[int] = mapped_column(
        nullable=False, default=0, server_default=text("0")
    )
    last_fired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class InstagramAutomationEvent(Base):
    """One fire of a rule against one comment/message. The unique
    (automation_id, object_id) stops a webhook retry from double-replying."""

    __tablename__ = "instagram_automation_events"
    __table_args__ = (
        UniqueConstraint(
            "automation_id", "object_id", name="uq_instagram_automation_event_object"
        ),
        CheckConstraint(
            "status IN ('sent', 'simulated', 'skipped', 'failed')",
            name="ck_instagram_automation_event_status",
        ),
        Index("ix_instagram_automation_events_automation", "automation_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    automation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("instagram_automations.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Instagram comment id (comment rules) or sender id + mid (dm rules).
    object_id: Mapped[str] = mapped_column(String(191), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    detail: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
