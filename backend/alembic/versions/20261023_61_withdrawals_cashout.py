"""SnakePay Cash Out withdrawals, withdrawal blocks and the partner-invite permission.

Additive only.

Revision ID: 20261023_61
Revises: 20261023_60
Create Date: 2026-10-23 14:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261023_61"
down_revision: Union[str, None] = "20261023_60"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("financial_withdrawals") as batch:
        batch.add_column(sa.Column("gateway", sa.String(16), nullable=False, server_default="smokepay"))
        batch.add_column(sa.Column("request_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("requested_max", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True))
        batch.create_unique_constraint("uq_financial_withdrawals_request_id", ["request_id"])
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("withdrawals_blocked", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("can_invite_partners", sa.Boolean(), nullable=False, server_default=sa.false()))
    with op.batch_alter_table("workspaces") as batch:
        batch.add_column(sa.Column("snakepay_cashout_secret_encrypted", sa.String(1024), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("workspaces") as batch:
        batch.drop_column("snakepay_cashout_secret_encrypted")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("can_invite_partners")
        batch.drop_column("withdrawals_blocked")
    with op.batch_alter_table("financial_withdrawals") as batch:
        batch.drop_constraint("uq_financial_withdrawals_request_id", type_="unique")
        batch.drop_column("last_checked_at")
        batch.drop_column("requested_max")
        batch.drop_column("request_id")
        batch.drop_column("gateway")
