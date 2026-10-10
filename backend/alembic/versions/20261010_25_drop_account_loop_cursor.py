"""Drop the per-account loop cursor; loops share one media cursor per round.

Revision ID: 20261010_25
Revises: 20261010_24
Create Date: 2026-10-10
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261010_25"
down_revision: Union[str, None] = "20261010_24"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("instagram_loop_accounts", "next_media_index")


def downgrade() -> None:
    op.add_column(
        "instagram_loop_accounts",
        sa.Column("next_media_index", sa.Integer(), nullable=True),
    )
