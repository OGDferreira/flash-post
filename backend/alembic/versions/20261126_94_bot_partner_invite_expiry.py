"""Invite expiry for bot partnerships: a PENDING invite expires after N days (default 7,
owner-configurable), shows as "Expirado" and can be resent.

Additive only. Adds bot_partners.invite_expiry_days (default 7) and invite_expires_at.
Expiry is computed on read while PENDING; no background sweep.

Revision ID: 20261126_94
Revises: 20261126_93
Create Date: 2026-11-26 11:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261126_94"
down_revision: Union[str, None] = "20261126_93"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "bot_partners",
        sa.Column("invite_expiry_days", sa.Integer(), nullable=False, server_default="7"),
    )
    op.add_column(
        "bot_partners", sa.Column("invite_expires_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("bot_partners", "invite_expires_at")
    op.drop_column("bot_partners", "invite_expiry_days")
