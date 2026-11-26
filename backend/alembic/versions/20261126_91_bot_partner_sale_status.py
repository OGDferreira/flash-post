"""Per-sale commission status for bot partnerships: each recorded split can be marked
pending / paid / denied by the owner, so the partner sees which commissions were settled.

Additive only. Adds to bot_partner_sales:
- payout_status: 'pending' (default) | 'paid' | 'denied'
- status_note, status_changed_at, status_by_user_id (who last changed it).

Revision ID: 20261126_91
Revises: 20261126_90
Create Date: 2026-11-26 09:30:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261126_91"
down_revision: Union[str, None] = "20261126_90"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Plain ALTERs (no FK / no check constraint) so neither SQLite nor Postgres needs a
    # batch recreate of a table that already carries unnamed foreign keys. ``payout_status``
    # is validated at the API/service layer; ``status_by_user_id`` is an audit reference
    # without a DB-level foreign key.
    op.add_column(
        "bot_partner_sales",
        sa.Column("payout_status", sa.String(length=8), nullable=False, server_default="pending"),
    )
    op.add_column("bot_partner_sales", sa.Column("status_note", sa.Text(), nullable=True))
    op.add_column(
        "bot_partner_sales", sa.Column("status_changed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("bot_partner_sales", sa.Column("status_by_user_id", sa.Uuid(), nullable=True))
    op.create_index(
        "ix_bot_partner_sales_status", "bot_partner_sales", ["partnership_id", "payout_status"]
    )


def downgrade() -> None:
    op.drop_index("ix_bot_partner_sales_status", table_name="bot_partner_sales")
    op.drop_column("bot_partner_sales", "status_by_user_id")
    op.drop_column("bot_partner_sales", "status_changed_at")
    op.drop_column("bot_partner_sales", "status_note")
    op.drop_column("bot_partner_sales", "payout_status")
