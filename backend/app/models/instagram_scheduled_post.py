"""One-off scheduled publications (feed posts and stories), separate from loops.

An owner picks a media, a set of accounts (directly or via folders), a moment and
a kind (feed post or story). One parent row holds the content; one target row per
account carries that account's own status, so one account failing never blocks the
rest. A background tick publishes the due targets through the same publishing engine
the loops use.
"""
import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.models import Base

# Parent status
POST_SCHEDULED = "scheduled"
POST_PUBLISHING = "publishing"
POST_DONE = "done"  # every target reached a terminal state (published or failed)
POST_CANCELED = "canceled"

# Target (per-account) status
TARGET_QUEUED = "queued"
TARGET_PUBLISHING = "publishing"
TARGET_PUBLISHED = "published"
TARGET_FAILED = "failed"
TARGET_CANCELED = "canceled"

KIND_POST = "post"
KIND_STORY = "story"


class InstagramScheduledPost(Base):
    __tablename__ = "instagram_scheduled_posts"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('post', 'story')", name="ck_instagram_scheduled_posts_kind"
        ),
        CheckConstraint(
            "status IN ('scheduled', 'publishing', 'done', 'canceled')",
            name="ck_instagram_scheduled_posts_status",
        ),
        Index(
            "ix_instagram_scheduled_posts_workspace_status",
            "workspace_id",
            "status",
            "scheduled_for",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    media_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("instagram_media.id", ondelete="SET NULL")
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default=KIND_POST)
    caption: Mapped[str | None] = mapped_column(Text)
    scheduled_for: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=POST_SCHEDULED
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class InstagramScheduledPostTarget(Base):
    __tablename__ = "instagram_scheduled_post_targets"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'publishing', 'published', 'failed', 'canceled')",
            name="ck_instagram_scheduled_post_targets_status",
        ),
        Index(
            "ix_instagram_scheduled_post_targets_due",
            "status",
            "post_id",
        ),
        Index(
            "ix_instagram_scheduled_post_targets_account",
            "account_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    post_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("instagram_scheduled_posts.id", ondelete="CASCADE"),
        nullable=False,
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("instagram_accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=TARGET_QUEUED
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    published_media_id: Mapped[str | None] = mapped_column(String(191))
    last_error: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
