"""The Super Admin can hide a bot and a funnel from the operation that owns them.

Additive only.

Revision ID: 20261023_60
Revises: 20261023_59
Create Date: 2026-10-23 12:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261023_60"
down_revision: Union[str, None] = "20261023_59"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for table in ("tg_bots", "tg_flows"):
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column("hidden_by_admin", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    for table in ("tg_bots", "tg_flows"):
        with op.batch_alter_table(table) as batch:
            batch.drop_column("hidden_by_admin")
