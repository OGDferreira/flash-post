"""The iPhone widget's look, saved on the account (picked with a tap on the site or phone).

Additive only: a nullable short text on ``users``.

Revision ID: 20261101_72
Revises: 20261030_71
Create Date: 2026-11-01 14:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261101_72"
down_revision: Union[str, None] = "20261030_71"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("widget_theme", sa.String(length=16), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "widget_theme")
