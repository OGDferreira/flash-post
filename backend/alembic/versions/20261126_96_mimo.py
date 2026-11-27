"""Mimo (voluntary tip): per-lead "waiting for the amount" flag.

Additive only: one boolean column on tg_leads, default false, so every existing
lead is "not waiting for a mimo value" and behavior is unchanged.

Revision ID: 20261126_96
Revises: 20261126_95
Create Date: 2026-11-26 19:10:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261126_96"
down_revision: Union[str, None] = "20261126_95"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tg_leads",
        sa.Column("awaiting_mimo", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("tg_leads", "awaiting_mimo")
