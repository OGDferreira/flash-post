"""Automation scope by folders/accounts + DM message variations.

Additive only: three JSONB columns on instagram_automations. Old rules keep
working — empty scope lists mean "every account" (same as before), and the
legacy instagram_account_id is still honored by the engine.

Revision ID: 20261115_84
Revises: 20261115_83
Create Date: 2026-11-15 03:45:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "20261115_84"
down_revision: Union[str, None] = "20261115_83"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_JSON = sa.JSON().with_variant(JSONB, "postgresql")


def upgrade() -> None:
    op.add_column(
        "instagram_automations",
        sa.Column("scope_account_ids", _JSON, nullable=False, server_default="[]"),
    )
    op.add_column(
        "instagram_automations",
        sa.Column("scope_folder_ids", _JSON, nullable=False, server_default="[]"),
    )
    op.add_column(
        "instagram_automations",
        sa.Column("dm_texts", _JSON, nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("instagram_automations", "dm_texts")
    op.drop_column("instagram_automations", "scope_folder_ids")
    op.drop_column("instagram_automations", "scope_account_ids")
