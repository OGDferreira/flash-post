"""Persisted per-publication Instagram Insights and account sync status.

Revision ID: 20261014_31
Revises: 20261014_30
Create Date: 2026-10-14
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261014_31"
down_revision: Union[str, None] = "20261014_30"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("instagram_accounts", sa.Column("insights_synced_at", sa.DateTime(timezone=True)))
    op.add_column("instagram_accounts", sa.Column("insights_sync_error", sa.String(500)))
    op.create_table(
        "instagram_media_insights",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "account_id", sa.Uuid(), sa.ForeignKey("instagram_accounts.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("ig_media_id", sa.String(64), nullable=False),
        sa.Column("media_type", sa.String(32)),
        sa.Column("media_product_type", sa.String(32)),
        sa.Column("permalink", sa.String(500)),
        sa.Column("thumbnail_url", sa.String(2048)),
        sa.Column("caption", sa.String(300)),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("views", sa.Integer()),
        sa.Column("reach", sa.Integer()),
        sa.Column("likes", sa.Integer()),
        sa.Column("comments", sa.Integer()),
        sa.Column("shares", sa.Integer()),
        sa.Column("saves", sa.Integer()),
        sa.Column("metrics_error", sa.String(300)),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("account_id", "ig_media_id", name="uq_instagram_media_insights_account_media"),
    )
    op.create_index(
        "ix_instagram_media_insights_workspace_posted", "instagram_media_insights", ["workspace_id", "posted_at"]
    )
    op.create_index(
        "ix_instagram_media_insights_account_posted", "instagram_media_insights", ["account_id", "posted_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_instagram_media_insights_account_posted", table_name="instagram_media_insights")
    op.drop_index("ix_instagram_media_insights_workspace_posted", table_name="instagram_media_insights")
    op.drop_table("instagram_media_insights")
    op.drop_column("instagram_accounts", "insights_sync_error")
    op.drop_column("instagram_accounts", "insights_synced_at")
