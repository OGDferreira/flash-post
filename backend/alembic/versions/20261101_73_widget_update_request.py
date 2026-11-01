"""The "Atualizar widget" button: when the user asked the installed widget to update itself.

Additive only: a nullable timestamp on ``users``.

Revision ID: 20261101_73
Revises: 20261101_72
Create Date: 2026-11-01 15:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261101_73"
down_revision: Union[str, None] = "20261101_72"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("widget_update_requested_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "widget_update_requested_at")
