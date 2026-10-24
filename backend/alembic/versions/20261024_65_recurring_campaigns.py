"""Recurring remarketing: a campaign can repeat (daily, every N hours, or on chosen
weekdays) and keep a per-send history.

Additive only: two nullable columns on ``tg_campaigns`` and a new ``tg_campaign_runs``
table, one row per send so the panel can show the history of disparos.

Revision ID: 20261024_65
Revises: 20261023_64
Create Date: 2026-10-24 00:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261024_65"
down_revision: Union[str, None] = "20261023_64"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("tg_campaigns") as batch:
        batch.add_column(sa.Column("recurrence", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "tg_campaign_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("campaign_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="sending"),
        sa.Column("total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("blocked", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("already_blocked", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["campaign_id"], ["tg_campaigns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tg_campaign_runs_campaign", "tg_campaign_runs", ["campaign_id", "started_at"])


def downgrade() -> None:
    op.drop_index("ix_tg_campaign_runs_campaign", table_name="tg_campaign_runs")
    op.drop_table("tg_campaign_runs")
    with op.batch_alter_table("tg_campaigns") as batch:
        batch.drop_column("last_run_at")
        batch.drop_column("recurrence")
