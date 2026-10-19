"""PIX gateway choice per operation (SmokePay or SnakePay).

* ``workspaces.payment_gateway``: "smokepay" (default) or "snakepay".
* ``workspaces.snakepay_recipient_id``: the SnakePay account that receives the
  operation's share of SnakePay sales through the split.

Additive only.

Revision ID: 20261019_48
Revises: 20261019_47
Create Date: 2026-10-19 15:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261019_48"
down_revision: Union[str, None] = "20261019_47"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("workspaces") as batch:
        batch.add_column(sa.Column("payment_gateway", sa.String(16), nullable=False, server_default="smokepay"))
        batch.add_column(sa.Column("snakepay_recipient_id", sa.String(64), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("workspaces") as batch:
        batch.drop_column("snakepay_recipient_id")
        batch.drop_column("payment_gateway")
