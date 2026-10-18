"""FlashBot remarketing campaigns, one list per funnel.

Additive only.

Revision ID: 20261018_46
Revises: 20261018_45
Create Date: 2026-10-18 20:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261018_46"
down_revision: Union[str, None] = "20261018_45"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tg_campaigns",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("flow_id", sa.Uuid(), sa.ForeignKey("tg_flows.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("definition", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("scheduled_at", sa.DateTime(timezone=True)),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("cursor_lead_id", sa.Uuid()),
        sa.Column("total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("blocked", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("already_blocked", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("runs", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_tg_campaigns_workspace_flow", "tg_campaigns", ["workspace_id", "flow_id"])
    op.create_index("ix_tg_campaigns_status_scheduled", "tg_campaigns", ["status", "scheduled_at"])
    if op.get_bind().dialect.name == "postgresql":
        # Same lock as 20261017_44: no access through Supabase's public REST API.
        op.execute("ALTER TABLE public.tg_campaigns ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.drop_index("ix_tg_campaigns_status_scheduled", table_name="tg_campaigns")
    op.drop_index("ix_tg_campaigns_workspace_flow", table_name="tg_campaigns")
    op.drop_table("tg_campaigns")
