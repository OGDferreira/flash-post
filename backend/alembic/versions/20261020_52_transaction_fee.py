"""FlashBot transaction fee: per-user override and the fee recorded on each order.

Additive only.

Revision ID: 20261020_52
Revises: 20261019_51
Create Date: 2026-10-20 02:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261020_52"
down_revision: Union[str, None] = "20261019_51"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        # NULL = the platform default (Settings.flashbot_transaction_fee)
        batch.add_column(sa.Column("transaction_fee", sa.Numeric(10, 2), nullable=True))
    with op.batch_alter_table("tg_orders") as batch:
        batch.add_column(sa.Column("transaction_fee", sa.Numeric(10, 2), nullable=True))
    # Sales charged since the R$ 0,40 fee went live (2026-10-20 01:42 UTC, before this column):
    # every one outside the Super Admin's own operation (origin 'main') paid it.
    op.execute(
        "UPDATE tg_orders SET transaction_fee = 0.40 "
        "WHERE created_at >= '2026-10-20 01:42:00' AND origin <> 'main' AND gateway_transaction_id IS NOT NULL"
    )


def downgrade() -> None:
    with op.batch_alter_table("tg_orders") as batch:
        batch.drop_column("transaction_fee")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("transaction_fee")
