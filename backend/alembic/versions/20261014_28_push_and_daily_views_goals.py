"""Web Push subscriptions, daily views goals and their notification log.

Revision ID: 20261014_28
Revises: 20261011_27
Create Date: 2026-10-14
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261014_28"
down_revision: Union[str, None] = "20261011_27"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "push_subscriptions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "workspace_id", sa.Uuid(), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("endpoint", sa.Text(), nullable=False),
        sa.Column("p256dh", sa.String(length=200), nullable=False),
        sa.Column("auth", sa.String(length=100), nullable=False),
        sa.Column("user_agent", sa.String(length=300), nullable=True),
        sa.Column("failure_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("endpoint", name="uq_push_subscriptions_endpoint"),
    )
    op.create_index(
        "ix_push_subscriptions_user_workspace", "push_subscriptions", ["user_id", "workspace_id"]
    )
    op.create_table(
        "daily_views_goals",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "workspace_id", sa.Uuid(), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_views", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "timezone", sa.String(length=64), nullable=False, server_default="America/Sao_Paulo"
        ),
        sa.Column("progress_date", sa.Date(), nullable=True),
        sa.Column("progress_views", sa.Integer(), nullable=True),
        sa.Column("progress_accounts", sa.Integer(), nullable=True),
        sa.Column("progress_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("progress_error", sa.String(length=500), nullable=True),
        sa.Column(
            "updated_by_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("workspace_id", "user_id", name="uq_daily_views_goals_workspace_user"),
        sa.CheckConstraint("target_views > 0", name="ck_daily_views_goals_target_positive"),
    )
    op.create_table(
        "daily_views_goal_notifications",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "goal_id", sa.Uuid(), sa.ForeignKey("daily_views_goals.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "workspace_id", sa.Uuid(), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("local_date", sa.Date(), nullable=False),
        sa.Column("target_views", sa.Integer(), nullable=False),
        sa.Column("views", sa.Integer(), nullable=False),
        sa.Column("delivered", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "goal_id",
            "local_date",
            "target_views",
            name="uq_daily_views_goal_notifications_goal_day_target",
        ),
    )
    # Speeds up the Sharkbot transaction de-duplication lookup.
    op.create_index(
        "ix_shark_events_workspace_type_transaction",
        "shark_events",
        ["workspace_id", "event_type", "transaction_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_shark_events_workspace_type_transaction", table_name="shark_events")
    op.drop_table("daily_views_goal_notifications")
    op.drop_table("daily_views_goals")
    op.drop_index("ix_push_subscriptions_user_workspace", table_name="push_subscriptions")
    op.drop_table("push_subscriptions")
