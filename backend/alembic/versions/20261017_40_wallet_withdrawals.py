"""Wallet: withdrawal requests (status, Pix key, who processed).

Additive only. Existing rows are owner-registered withdrawals: status PAID.

Revision ID: 20261017_40
Revises: 20261016_39
Create Date: 2026-10-17 01:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261017_40"
down_revision: Union[str, None] = "20261016_39"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("financial_withdrawals") as batch:
        batch.add_column(sa.Column("status", sa.String(length=16), server_default="PAID", nullable=False))
        batch.add_column(sa.Column("pix_key_type", sa.String(length=16), nullable=True))
        batch.add_column(sa.Column("pix_key", sa.String(length=140), nullable=True))
        batch.add_column(sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("processed_by_user_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key(
            "fk_financial_withdrawals_processed_by", "users", ["processed_by_user_id"], ["id"], ondelete="SET NULL"
        )
        batch.create_check_constraint("ck_financial_withdrawals_status", "status IN ('PAID', 'REQUESTED', 'REJECTED')")


def downgrade() -> None:
    with op.batch_alter_table("financial_withdrawals") as batch:
        batch.drop_constraint("ck_financial_withdrawals_status", type_="check")
        batch.drop_constraint("fk_financial_withdrawals_processed_by", type_="foreignkey")
        for column in ("processed_by_user_id", "processed_at", "pix_key", "pix_key_type", "status"):
            batch.drop_column(column)
