"""Mimo: per-lead pending-input flag.

Additive only: one nullable String column on tg_leads. NULL means the lead is not
waiting to type anything (the default for every existing lead), so behavior is
unchanged. Set to "mimo" while the lead is expected to type the value of a mimo.

Revision ID: 20261126_97
Revises: 20261126_96
Create Date: 2026-11-26 11:10:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261126_97"
down_revision: Union[str, None] = "20261126_96"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tg_leads", sa.Column("awaiting", sa.String(length=32), nullable=True))


def downgrade() -> None:
    op.drop_column("tg_leads", "awaiting")
