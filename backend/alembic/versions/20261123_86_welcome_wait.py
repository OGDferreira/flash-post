"""Humanized conversation: per-lead pause state for the welcome sequence.

Additive only: one nullable JSON column on tg_leads. NULL means the lead is not
paused (the default for every existing lead), so behavior is unchanged.

Revision ID: 20261123_86
Revises: 20261115_85
Create Date: 2026-11-23 22:50:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "20261123_86"
down_revision: Union[str, None] = "20261115_85"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_JSON = sa.JSON().with_variant(JSONB, "postgresql")


def upgrade() -> None:
    op.add_column("tg_leads", sa.Column("welcome_wait", _JSON, nullable=True))


def downgrade() -> None:
    op.drop_column("tg_leads", "welcome_wait")
