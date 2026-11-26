"""Multiple active partners per bot: a paid order now splits to every active partner, so the
per-sale ledger is keyed by (order_id, partnership_id) instead of order_id alone.

Additive/relaxing only. Replaces the unique constraint uq_bot_partner_sales_order (order_id)
with uq_bot_partner_sales_order_part (order_id, partnership_id). Existing rows are unaffected
(each order had at most one row before).

Revision ID: 20261126_90
Revises: 20261126_89
Create Date: 2026-11-26 09:00:00
"""
from typing import Sequence, Union

from alembic import op


revision: str = "20261126_90"
down_revision: Union[str, None] = "20261126_89"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("bot_partner_sales") as batch:
        batch.drop_constraint("uq_bot_partner_sales_order", type_="unique")
        batch.create_unique_constraint(
            "uq_bot_partner_sales_order_part", ["order_id", "partnership_id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("bot_partner_sales") as batch:
        batch.drop_constraint("uq_bot_partner_sales_order_part", type_="unique")
        batch.create_unique_constraint("uq_bot_partner_sales_order", ["order_id"])
