"""Pix end-to-end id (E2E) of each withdrawal, as SmokePay reports it.

The E2E is the bank-side receipt: with it the receiver's bank traces where the Pix went.
Additive only.

Revision ID: 20261019_50
Revises: 20261019_49
Create Date: 2026-10-19 19:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261019_50"
down_revision: Union[str, None] = "20261019_49"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("financial_withdrawals") as batch:
        batch.add_column(sa.Column("gateway_e2e_id", sa.String(64), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("financial_withdrawals") as batch:
        batch.drop_column("gateway_e2e_id")
