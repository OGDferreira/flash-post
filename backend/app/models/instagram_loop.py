import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.models import Base


class InstagramLoop(Base):
    __tablename__ = "instagram_loops"
    __table_args__ = (
        CheckConstraint(
            "interval_min_minutes >= 1 AND interval_max_minutes >= interval_min_minutes",
            name="ck_instagram_loops_interval_range",
        ),
        CheckConstraint(
            "daily_limit_per_account >= 1",
            name="ck_instagram_loops_daily_limit",
        ),
        CheckConstraint(
            "status IN ('active', 'paused')",
            name="ck_instagram_loops_status",
        ),
        CheckConstraint(
            "post_type IN ('reels', 'images', 'both')",
            name="ck_instagram_loops_post_type",
        ),
        CheckConstraint(
            "caption_mode IN ('per_media', 'all')",
            name="ck_instagram_loops_caption_mode",
        ),
        CheckConstraint(
            "cover_mode IN ('auto', 'all', 'per_media')",
            name="ck_instagram_loops_cover_mode",
        ),
        Index("ix_instagram_loops_due", "status", "next_run_at"),
        Index("ix_instagram_loops_workspace_id", "workspace_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    interval_min_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    interval_max_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    daily_limit_per_account: Mapped[int] = mapped_column(
        Integer, nullable=False, default=100
    )
    post_type: Mapped[str] = mapped_column(String(16), nullable=False, default="reels")
    repeat_media: Mapped[bool] = mapped_column(
        nullable=False, default=True, server_default=text("true")
    )
    # per_media: each video keeps its own caption; all: ``caption`` goes on every post.
    caption_mode: Mapped[str] = mapped_column(
        String(16), nullable=False, default="per_media", server_default=text("'per_media'")
    )
    caption: Mapped[str | None] = mapped_column(String(2200))
    # Reels cover: auto (Instagram picks a frame), all (``cover_media_id`` on every
    # video) or per_media (each video's own ``InstagramMedia.cover_media_id``).
    cover_mode: Mapped[str] = mapped_column(
        String(16), nullable=False, default="auto", server_default=text("'auto'")
    )
    cover_media_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    # Folders whose accounts join this loop automatically.
    auto_folder_ids: Mapped[list] = mapped_column(
        JSON, nullable=False, default=list, server_default=text("'[]'")
    )
    next_media_index: Mapped[int | None] = mapped_column(Integer)
    next_queue_sequence: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="active", server_default=text("'active'")
    )
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # A chief's loop offered to their partners, and the template a copy came from.
    shared: Mapped[bool] = mapped_column(nullable=False, default=False, server_default=text("false"))
    # Who it is shared with: None = every partner, else a list of partner user ids.
    shared_with: Mapped[list | None] = mapped_column(JSON)
    # A partner's copy that follows the chief's loop (media and schedule); only accounts are the partner's.
    linked: Mapped[bool] = mapped_column(nullable=False, default=False, server_default=text("false"))
    template_loop_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("instagram_loops.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class InstagramLoopAccount(Base):
    __tablename__ = "instagram_loop_accounts"
    __table_args__ = (
        Index("ix_instagram_loop_accounts_account_id", "account_id"),
    )

    loop_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("instagram_loops.id", ondelete="CASCADE"), primary_key=True
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("instagram_accounts.id", ondelete="CASCADE"),
        primary_key=True,
    )


class InstagramMedia(Base):
    __tablename__ = "instagram_media"
    __table_args__ = (
        CheckConstraint("media_type IN ('image', 'video')", name="ck_instagram_media_type"),
        CheckConstraint("size_bytes > 0", name="ck_instagram_media_size"),
        Index("ix_instagram_media_workspace_id", "workspace_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    storage_path: Mapped[str] = mapped_column(String(500), unique=True, nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    media_type: Mapped[str] = mapped_column(String(16), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    caption: Mapped[str | None] = mapped_column(String(2200))
    # A JPEG uploaded only to be a Reels cover: never posted, kept out of the pool.
    is_cover: Mapped[bool] = mapped_column(
        nullable=False, default=False, server_default=text("false")
    )
    # This video's own Reels cover (used when its loop's cover_mode is per_media).
    cover_media_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    # copied from a chief's shared loop: posts normally, but the partner never sees it
    locked: Mapped[bool] = mapped_column(nullable=False, default=False, server_default=text("false"))
    # the chief's media this copy came from (lets a linked loop follow the original)
    template_media_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class InstagramLoopMedia(Base):
    __tablename__ = "instagram_loop_media"
    __table_args__ = (Index("ix_instagram_loop_media_media_id", "media_id"),)

    loop_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("instagram_loops.id", ondelete="CASCADE"), primary_key=True
    )
    media_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("instagram_media.id", ondelete="CASCADE"), primary_key=True
    )


class InstagramPublicationJob(Base):
    __tablename__ = "instagram_publication_jobs"
    __table_args__ = (
        UniqueConstraint(
            "loop_id",
            "account_id",
            "scheduled_for",
            name="uq_instagram_publication_jobs_schedule_account",
        ),
        CheckConstraint(
            "status IN ('waiting_for_media', 'queued', 'publishing', 'published', 'failed')",
            name="ck_instagram_publication_jobs_status",
        ),
        Index(
            "ix_instagram_publication_jobs_account_status",
            "account_id",
            "status",
            "scheduled_for",
        ),
        # At most one unfinished job per account in each loop. This is what
        # makes concurrent workers/ticks unable to queue the same video twice.
        Index(
            "uq_instagram_publication_jobs_active_loop_account",
            "loop_id",
            "account_id",
            unique=True,
            postgresql_where=text("status IN ('waiting_for_media', 'queued', 'publishing')"),
            sqlite_where=text("status IN ('waiting_for_media', 'queued', 'publishing')"),
        ),
        Index("ix_instagram_publication_jobs_published_at", "account_id", "published_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    loop_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("instagram_loops.id", ondelete="CASCADE"), nullable=False
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("instagram_accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    media_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("instagram_media.id", ondelete="SET NULL")
    )
    queue_sequence: Mapped[int | None] = mapped_column(Integer)
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default="waiting_for_media",
        server_default=text("'waiting_for_media'"),
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    last_error: Mapped[str | None] = mapped_column(String(500))
    error_category: Mapped[str | None] = mapped_column(String(32))
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_media_id: Mapped[str | None] = mapped_column(String(128))
    # Publication bookkeeping used to reconcile uncertain Meta responses:
    # the container is saved and publish_requested_at is set *before*
    # media_publish is called, so a lost response is never blindly retried.
    container_id: Mapped[str | None] = mapped_column(String(128))
    publish_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reconcile_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class InstagramLoopAccountState(Base):
    """Per-account progress inside a loop.

    Kept apart from ``instagram_loop_accounts`` so that removing an account
    from a loop (or isolating it after an error) does not lose its place in the
    sequence: when it comes back it resumes from the next video.
    """

    __tablename__ = "instagram_loop_account_states"
    __table_args__ = (Index("ix_instagram_loop_account_states_account", "account_id"),)

    loop_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("instagram_loops.id", ondelete="CASCADE"), primary_key=True
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("instagram_accounts.id", ondelete="CASCADE"),
        primary_key=True,
    )
    # Position (0-based) of the next media to publish in the ordered pool.
    next_position: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    # Last media whose publication was confirmed; used to resync the position
    # when media are added or removed from the loop.
    last_media_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("instagram_media.id", ondelete="SET NULL")
    )
    cycles_completed: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Why the account is not publishing right now (daily_limit, no_media,
    # instagram_cap, needs_review). None = running normally.
    blocked_reason: Mapped[str | None] = mapped_column(String(32))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class SharkEvent(Base):
    __tablename__ = "shark_events"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "source_event_key",
            name="uq_shark_events_workspace_source_key",
        ),
        Index("ix_shark_events_workspace_occurred_at", "workspace_id", "occurred_at"),
        Index("ix_shark_events_account_occurred_at", "account_id", "occurred_at"),
        Index(
            "ix_shark_events_workspace_type_transaction",
            "workspace_id",
            "event_type",
            "transaction_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("instagram_accounts.id", ondelete="SET NULL")
    )
    operation_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("smokepay_operations.id", ondelete="SET NULL")
    )
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    source_event_key: Mapped[str] = mapped_column(String(64), nullable=False)
    webhook_id: Mapped[str | None] = mapped_column(String(160))
    transaction_id: Mapped[str | None] = mapped_column(String(160))
    operation_name: Mapped[str | None] = mapped_column(String(120))
    customer_name: Mapped[str | None] = mapped_column(String(240))
    customer_username: Mapped[str | None] = mapped_column(String(120))
    bot_name: Mapped[str | None] = mapped_column(String(160))
    plan_name: Mapped[str | None] = mapped_column(String(160))
    amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=0, server_default="0"
    )
    net_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
