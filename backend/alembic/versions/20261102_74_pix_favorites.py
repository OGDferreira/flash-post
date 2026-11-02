"""Favorite Pix keys for withdrawals, saved on the account.

Additive only: a nullable JSON list on ``users``.

Revision ID: 20261102_74
Revises: 20261101_73
Create Date: 2026-11-02 09:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261102_74"
down_revision: Union[str, None] = "20261101_73"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("pix_favorites", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "pix_favorites")
