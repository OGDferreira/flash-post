"""Protected shared funnels (+ loop), bot delivery group, sale origin and platform fee.

Additive only.

Revision ID: 20261017_42
Revises: 20261017_41
Create Date: 2026-10-17 12:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261017_42"
down_revision: Union[str, None] = "20261017_41"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("tg_flows") as batch:
        batch.add_column(sa.Column("shared_loop_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key(
            "fk_tg_flows_shared_loop", "instagram_loops", ["shared_loop_id"], ["id"], ondelete="SET NULL"
        )
    with op.batch_alter_table("tg_bots") as batch:
        batch.add_column(sa.Column("delivery_group_chat_id", sa.BigInteger(), nullable=True))
    with op.batch_alter_table("tg_orders") as batch:
        batch.add_column(sa.Column("origin", sa.String(length=16), nullable=True))
        batch.add_column(sa.Column("platform_fee", sa.Numeric(precision=12, scale=2), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("tg_orders") as batch:
        batch.drop_column("platform_fee")
        batch.drop_column("origin")
    with op.batch_alter_table("tg_bots") as batch:
        batch.drop_column("delivery_group_chat_id")
    with op.batch_alter_table("tg_flows") as batch:
        batch.drop_constraint("fk_tg_flows_shared_loop", type_="foreignkey")
        batch.drop_column("shared_loop_id")
