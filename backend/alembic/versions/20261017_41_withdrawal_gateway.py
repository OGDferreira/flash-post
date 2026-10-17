"""Automatic SmokePay withdrawals: gateway id and PROCESSING/FAILED states.

Revision ID: 20261017_41
Revises: 20261017_40
Create Date: 2026-10-17 03:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261017_41"
down_revision: Union[str, None] = "20261017_40"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("financial_withdrawals") as batch:
        batch.add_column(sa.Column("gateway_withdrawal_id", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("fee", sa.Numeric(precision=12, scale=2), nullable=True))
        batch.drop_constraint("ck_financial_withdrawals_status", type_="check")
        batch.create_check_constraint(
            "ck_financial_withdrawals_status", "status IN ('PAID', 'REQUESTED', 'REJECTED', 'PROCESSING', 'FAILED')"
        )


def downgrade() -> None:
    with op.batch_alter_table("financial_withdrawals") as batch:
        batch.drop_constraint("ck_financial_withdrawals_status", type_="check")
        batch.create_check_constraint("ck_financial_withdrawals_status", "status IN ('PAID', 'REQUESTED', 'REJECTED')")
        batch.drop_column("fee")
        batch.drop_column("gateway_withdrawal_id")
