import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
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
    daily_limit_per_account: Mapped[int] = mapped_column(Integer, nullable=False)
    post_type: Mapped[str] = mapped_column(String(16), nullable=False, default="reels")
    repeat_media: Mapped[bool] = mapped_column(
        nullable=False, default=True, server_default=text("true")
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="active", server_default=text("'active'")
    )
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
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
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default="waiting_for_media",
        server_default=text("'waiting_for_media'"),
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    last_error: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
