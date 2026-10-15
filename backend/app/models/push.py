import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.models import Base


class PushSubscription(Base):
    """A browser/PWA Web Push subscription owned by one user in one workspace."""

    __tablename__ = "push_subscriptions"
    __table_args__ = (
        UniqueConstraint("endpoint", name="uq_push_subscriptions_endpoint"),
        Index("ix_push_subscriptions_user_workspace", "user_id", "workspace_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    endpoint: Mapped[str] = mapped_column(Text, nullable=False)
    p256dh: Mapped[str] = mapped_column(String(200), nullable=False)
    auth: Mapped[str] = mapped_column(String(100), nullable=False)
    user_agent: Mapped[str | None] = mapped_column(String(300))
    failure_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class DailyViewsGoal(Base):
    """Per-user daily views target. Progress is cached from Meta Insights."""

    __tablename__ = "daily_views_goals"
    __table_args__ = (
        UniqueConstraint("workspace_id", "user_id", name="uq_daily_views_goals_workspace_user"),
        CheckConstraint("target_views > 0", name="ck_daily_views_goals_target_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    target_views: Mapped[int] = mapped_column(Integer, nullable=False)
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    timezone: Mapped[str] = mapped_column(
        String(64), nullable=False, default="America/Sao_Paulo", server_default="America/Sao_Paulo"
    )
    # Cached progress for the local day in `progress_date` (None = unknown).
    progress_date: Mapped[date | None] = mapped_column(Date)
    progress_views: Mapped[int | None] = mapped_column(Integer)
    progress_accounts: Mapped[int | None] = mapped_column(Integer)
    progress_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    progress_error: Mapped[str | None] = mapped_column(String(500))
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class DailyViewsGoalNotification(Base):
    """One row per goal, local day and target: the push de-duplication key."""

    __tablename__ = "daily_views_goal_notifications"
    __table_args__ = (
        UniqueConstraint(
            "goal_id",
            "local_date",
            "target_views",
            name="uq_daily_views_goal_notifications_goal_day_target",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    goal_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("daily_views_goals.id", ondelete="CASCADE"), nullable=False
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    local_date: Mapped[date] = mapped_column(Date, nullable=False)
    target_views: Mapped[int] = mapped_column(Integer, nullable=False)
    views: Mapped[int] = mapped_column(Integer, nullable=False)
    delivered: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class MilestoneNotification(Base):
    """One row per user, workspace, local day, kind and threshold: milestone push de-dup."""

    __tablename__ = "milestone_notifications"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "user_id",
            "local_date",
            "kind",
            "threshold",
            name="uq_milestone_notifications_scope",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    local_date: Mapped[date] = mapped_column(Date, nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    threshold: Mapped[int] = mapped_column(Integer, nullable=False)
    value: Mapped[int] = mapped_column(Integer, nullable=False)
    delivered: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
