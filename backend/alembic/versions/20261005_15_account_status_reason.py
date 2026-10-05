"""Store account connection failure details.

Revision ID: 20261005_15
Revises: 20261005_14
Create Date: 2026-10-05
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261005_15"
down_revision: Union[str, None] = "20261005_14"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "instagram_accounts",
        sa.Column("status_reason", sa.String(length=500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("instagram_accounts", "status_reason")
