"""One-time pop-ups (release notes, reinstall the app): which ones the user already saw.

Additive only: a nullable JSON list on ``users``.

Revision ID: 20261108_75
Revises: 20261102_74
Create Date: 2026-11-08 12:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261108_75"
down_revision: Union[str, None] = "20261102_74"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("seen_notices", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "seen_notices")
