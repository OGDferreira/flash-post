"""A partner can customize their copy of a shared loop: it stops following the chief's.

Additive only.

Revision ID: 20261022_58
Revises: 20261022_57
Create Date: 2026-10-22 23:30:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261022_58"
down_revision: Union[str, None] = "20261022_57"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("instagram_loops") as batch:
        batch.add_column(sa.Column("customized_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("instagram_loops") as batch:
        batch.drop_column("customized_at")
