"""Restricted access for bot partners: the owner chooses, per partner, whether they edit
the funnel (operational) or only read analytics + finance (read_only).

Additive only. Adds bot_partners.access_level (default 'operational'). Validated in the app
(no DB check constraint, to avoid a batch recreate of a table with unnamed foreign keys).

Revision ID: 20261126_93
Revises: 20261126_92
Create Date: 2026-11-26 10:30:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261126_93"
down_revision: Union[str, None] = "20261126_92"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "bot_partners",
        sa.Column("access_level", sa.String(length=16), nullable=False, server_default="operational"),
    )


def downgrade() -> None:
    op.drop_column("bot_partners", "access_level")
