"""Users can hide themselves from the platform rankings.

Additive only: a boolean on ``users`` defaulting to false (everyone stays listed).

Revision ID: 20261030_70
Revises: 20261030_69
Create Date: 2026-10-30 12:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261030_70"
down_revision: Union[str, None] = "20261030_69"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("hide_from_rankings", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("users", "hide_from_rankings")
