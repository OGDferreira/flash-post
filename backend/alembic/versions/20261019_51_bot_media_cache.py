"""Media cache channel per bot: files are uploaded there once and reused by file_id.

Additive only.

Revision ID: 20261019_51
Revises: 20261019_50
Create Date: 2026-10-19 21:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261019_51"
down_revision: Union[str, None] = "20261019_50"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("tg_bots") as batch:
        batch.add_column(sa.Column("cache_chat_id", sa.BigInteger(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("tg_bots") as batch:
        batch.drop_column("cache_chat_id")
