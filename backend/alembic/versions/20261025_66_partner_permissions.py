"""Per-partner feature permissions: which Flash Post / Flash Bot tabs a sócio may use.

Additive only: a nullable JSON column on ``affiliations`` (null = the default set).

Revision ID: 20261025_66
Revises: 20261024_65
Create Date: 2026-10-25 00:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261025_66"
down_revision: Union[str, None] = "20261024_65"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("affiliations", sa.Column("permissions", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("affiliations", "permissions")
