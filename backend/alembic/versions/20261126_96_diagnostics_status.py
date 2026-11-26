"""Diagnostics events: resolved/pending status for the per-account health panel.

Additive only. Every existing event becomes 'pending'; the owner (and Super Admin)
can mark one resolved, and the connect flow auto-resolves token/connection events
when the account reconnects.

Revision ID: 20261126_96
Revises: 20261126_95
Create Date: 2026-11-26 11:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261126_96"
down_revision: Union[str, None] = "20261126_95"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "diagnostics_events",
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default="pending",
        ),
    )
    op.add_column(
        "diagnostics_events",
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_diagnostics_events_account_status",
        "diagnostics_events",
        ["account_id", "status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_diagnostics_events_account_status", table_name="diagnostics_events")
    op.drop_column("diagnostics_events", "resolved_at")
    op.drop_column("diagnostics_events", "status")
