"""One-off scheduled publications (feed posts and stories) + per-account targets.

Additive only: two new tables. No existing table is touched.

Revision ID: 20261115_83
Revises: 20261114_82
Create Date: 2026-11-15 03:30:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261115_83"
down_revision: Union[str, None] = "20261114_82"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "instagram_scheduled_posts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("media_id", sa.Uuid(), nullable=True),
        sa.Column("kind", sa.String(length=16), server_default=sa.text("'post'"), nullable=False),
        sa.Column("caption", sa.Text(), nullable=True),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=16), server_default=sa.text("'scheduled'"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["media_id"], ["instagram_media.id"], ondelete="SET NULL"),
        sa.CheckConstraint("kind IN ('post', 'story')", name="ck_instagram_scheduled_posts_kind"),
        sa.CheckConstraint(
            "status IN ('scheduled', 'publishing', 'done', 'canceled')",
            name="ck_instagram_scheduled_posts_status",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_instagram_scheduled_posts_workspace_status",
        "instagram_scheduled_posts",
        ["workspace_id", "status", "scheduled_for"],
    )

    op.create_table(
        "instagram_scheduled_post_targets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("post_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default=sa.text("'queued'"), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("published_media_id", sa.String(length=191), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["post_id"], ["instagram_scheduled_posts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["account_id"], ["instagram_accounts.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "status IN ('queued', 'publishing', 'published', 'failed', 'canceled')",
            name="ck_instagram_scheduled_post_targets_status",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_instagram_scheduled_post_targets_due",
        "instagram_scheduled_post_targets",
        ["status", "post_id"],
    )
    op.create_index(
        "ix_instagram_scheduled_post_targets_account",
        "instagram_scheduled_post_targets",
        ["account_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_instagram_scheduled_post_targets_account", table_name="instagram_scheduled_post_targets")
    op.drop_index("ix_instagram_scheduled_post_targets_due", table_name="instagram_scheduled_post_targets")
    op.drop_table("instagram_scheduled_post_targets")
    op.drop_index("ix_instagram_scheduled_posts_workspace_status", table_name="instagram_scheduled_posts")
    op.drop_table("instagram_scheduled_posts")
