"""Index SharkBot payments by lead (the bot performance "lead bought?" lookup).

Additive only. Built CONCURRENTLY so the table stays writable.

Revision ID: 20261030_71
Revises: 20261030_70
Create Date: 2026-10-30 13:00:00
"""
from typing import Sequence, Union

from alembic import op


revision: str = "20261030_71"
down_revision: Union[str, None] = "20261030_70"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        with op.get_context().autocommit_block():
            op.create_index(
                "ix_shark_transactions_workspace_lead",
                "shark_transactions",
                ["workspace_id", "lead_key", "status"],
                postgresql_concurrently=True,
                if_not_exists=True,
            )
    else:
        op.create_index("ix_shark_transactions_workspace_lead", "shark_transactions", ["workspace_id", "lead_key", "status"])


def downgrade() -> None:
    op.drop_index("ix_shark_transactions_workspace_lead", table_name="shark_transactions")
