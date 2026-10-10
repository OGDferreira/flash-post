"""Track an independent media cursor for each account in a loop.

Revision ID: 20261010_24
Revises: 20261008_23
Create Date: 2026-10-10
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261010_24"
down_revision: Union[str, None] = "20261008_23"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "instagram_loop_accounts",
        sa.Column("next_media_index", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("instagram_loop_accounts", "next_media_index")
