"""Super Admin can block the platform Instagram app for one user.

Additive only: a boolean on ``users`` defaulting to false (everyone keeps access).

Revision ID: 20261030_69
Revises: 20261028_68
Create Date: 2026-10-30 00:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261030_69"
down_revision: Union[str, None] = "20261028_68"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("platform_app_blocked", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("users", "platform_app_blocked")
