"""The chief can change a partner's copy of a shared loop without touching the main loop.

Additive only.

Revision ID: 20261023_59
Revises: 20261022_58
Create Date: 2026-10-23 10:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261023_59"
down_revision: Union[str, None] = "20261022_58"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("instagram_loops") as batch:
        batch.add_column(sa.Column("owner_overrides", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("instagram_loops") as batch:
        batch.drop_column("owner_overrides")
