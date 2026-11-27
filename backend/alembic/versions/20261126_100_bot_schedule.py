"""Funnel scheduling: auto activate/deactivate a bot's funnel by time or sales.

Additive only. All columns optional; a bot with no schedule behaves exactly as before.

Revision ID: 20261126_100
Revises: 20261126_99
Create Date: 2026-11-27 05:20:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261126_100"
down_revision: Union[str, None] = "20261126_99"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("tg_bots") as batch_op:
        batch_op.add_column(
            sa.Column("scheduled_activate_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column("scheduled_deactivate_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column("auto_deactivate_after_sales", sa.Integer(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("schedule_activated_at", sa.DateTime(timezone=True), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("tg_bots") as batch_op:
        batch_op.drop_column("schedule_activated_at")
        batch_op.drop_column("auto_deactivate_after_sales")
        batch_op.drop_column("scheduled_deactivate_at")
        batch_op.drop_column("scheduled_activate_at")
