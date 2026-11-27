"""Native A/B test of two funnel versions on a bot.

Additive only. Creates ``tg_ab_tests`` and adds ``tg_bots.ab_test_id`` (nullable FK). While a
test is active on a bot, each new lead is drawn into variant A or B by ``weight_a`` and the bot
runs the lead's own drawn funnel. Both variants are ordinary funnels, so leads/orders stay keyed
by ``flow_id`` and the results view splits those metrics by the two funnels.

Revision ID: 20261126_96
Revises: 20261126_95
Create Date: 2026-11-26 12:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261126_96"
down_revision: Union[str, None] = "20261126_95"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tg_ab_tests",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("bot_id", sa.Uuid(), sa.ForeignKey("tg_bots.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("flow_a_id", sa.Uuid(), sa.ForeignKey("tg_flows.id", ondelete="CASCADE"), nullable=False),
        sa.Column("flow_b_id", sa.Uuid(), sa.ForeignKey("tg_flows.id", ondelete="CASCADE"), nullable=False),
        sa.Column("weight_a", sa.Integer(), nullable=False, server_default="50"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("stopped_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_tg_ab_tests_workspace", "tg_ab_tests", ["workspace_id"])
    # Plain column, no DB-level FK: SQLite cannot ALTER-ADD a constraint, and the app already
    # clears ``ab_test_id`` when a test is stopped or deleted. The ORM still declares the FK.
    op.add_column("tg_bots", sa.Column("ab_test_id", sa.Uuid(), nullable=True))


def downgrade() -> None:
    op.drop_column("tg_bots", "ab_test_id")
    op.drop_index("ix_tg_ab_tests_workspace", table_name="tg_ab_tests")
    op.drop_table("tg_ab_tests")
