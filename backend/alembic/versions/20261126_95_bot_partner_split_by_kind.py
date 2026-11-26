"""Split per offer type for bot partnerships: the owner can set a different partner percent
per kind of sale (plan / upsell / downsell / remarketing); the general percent is the
fallback for any kind left unset.

Additive only. Adds bot_partners.split_by_kind (JSON, nullable).

Revision ID: 20261126_95
Revises: 20261126_94
Create Date: 2026-11-26 11:30:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261126_95"
down_revision: Union[str, None] = "20261126_94"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("bot_partners", sa.Column("split_by_kind", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("bot_partners", "split_by_kind")
