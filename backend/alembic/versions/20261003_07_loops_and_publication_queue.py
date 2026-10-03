"""Add account state, Instagram loops, and a durable publication queue.

Revision ID: 20261003_07
Revises: 20261003_06
Create Date: 2026-10-03
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261003_07"
down_revision: Union[str, None] = "20261003_06"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("instagram_accounts") as batch_op:
        batch_op.alter_column(
            "encrypted_access_token",
            existing_type=sa.String(length=2048),
            nullable=True,
        )
        batch_op.add_column(
            sa.Column(
                "status",
                sa.String(length=20),
                server_default=sa.text("'connected'"),
                nullable=False,
            )
        )
        batch_op.create_check_constraint(
            "ck_instagram_accounts_status",
            "status IN ('connected', 'disconnected')",
        )

    op.create_table(
        "instagram_loops",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("workspace_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("interval_min_minutes", sa.Integer(), nullable=False),
        sa.Column("interval_max_minutes", sa.Integer(), nullable=False),
        sa.Column("daily_limit_per_account", sa.Integer(), nullable=False),
        sa.Column("post_type", sa.String(length=16), nullable=False),
        sa.Column("repeat_media", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("status", sa.String(length=16), server_default=sa.text("'active'"), nullable=False),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "interval_min_minutes >= 1 AND interval_max_minutes >= interval_min_minutes",
            name="ck_instagram_loops_interval_range",
        ),
        sa.CheckConstraint(
            "daily_limit_per_account >= 1",
            name="ck_instagram_loops_daily_limit",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'paused')",
            name="ck_instagram_loops_status",
        ),
        sa.CheckConstraint(
            "post_type IN ('reels', 'images', 'both')",
            name="ck_instagram_loops_post_type",
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_instagram_loops_due", "instagram_loops", ["status", "next_run_at"])
    op.create_index(
        "ix_instagram_loops_workspace_id", "instagram_loops", ["workspace_id"]
    )

    op.create_table(
        "instagram_loop_accounts",
        sa.Column("loop_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("account_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["instagram_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["loop_id"], ["instagram_loops.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("loop_id", "account_id"),
    )
    op.create_index(
        "ix_instagram_loop_accounts_account_id",
        "instagram_loop_accounts",
        ["account_id"],
    )

    op.create_table(
        "instagram_publication_jobs",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("workspace_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("loop_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("account_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status",
            sa.String(length=24),
            server_default=sa.text("'waiting_for_media'"),
            nullable=False,
        ),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("last_error", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "status IN ('waiting_for_media', 'queued', 'publishing', 'published', 'failed')",
            name="ck_instagram_publication_jobs_status",
        ),
        sa.ForeignKeyConstraint(["account_id"], ["instagram_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["loop_id"], ["instagram_loops.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "loop_id",
            "account_id",
            "scheduled_for",
            name="uq_instagram_publication_jobs_schedule_account",
        ),
    )
    op.create_index(
        "ix_instagram_publication_jobs_account_status",
        "instagram_publication_jobs",
        ["account_id", "status", "scheduled_for"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_instagram_publication_jobs_account_status",
        table_name="instagram_publication_jobs",
    )
    op.drop_table("instagram_publication_jobs")
    op.drop_index(
        "ix_instagram_loop_accounts_account_id",
        table_name="instagram_loop_accounts",
    )
    op.drop_table("instagram_loop_accounts")
    op.drop_index("ix_instagram_loops_workspace_id", table_name="instagram_loops")
    op.drop_index("ix_instagram_loops_due", table_name="instagram_loops")
    op.drop_table("instagram_loops")
    op.execute(
        sa.text("DELETE FROM instagram_accounts WHERE status = 'disconnected'")
    )
    with op.batch_alter_table("instagram_accounts") as batch_op:
        batch_op.drop_constraint("ck_instagram_accounts_status", type_="check")
        batch_op.drop_column("status")
        batch_op.alter_column(
            "encrypted_access_token",
            existing_type=sa.String(length=2048),
            nullable=False,
        )
