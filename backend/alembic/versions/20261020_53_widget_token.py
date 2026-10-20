"""Read-only token for the iPhone (Scriptable) widget: only its SHA-256 is stored.

Additive only.

Revision ID: 20261020_53
Revises: 20261020_52
Create Date: 2026-10-20 03:30:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261020_53"
down_revision: Union[str, None] = "20261020_52"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("widget_token_hash", sa.String(64), nullable=True))
        batch.create_index("ix_users_widget_token_hash", ["widget_token_hash"], unique=True)


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_index("ix_users_widget_token_hash")
        batch.drop_column("widget_token_hash")
