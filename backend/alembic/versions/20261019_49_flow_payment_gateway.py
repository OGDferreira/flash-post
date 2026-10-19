"""PIX gateway per funnel: ``tg_flows.payment_gateway`` (None = operation default).

Additive only.

Revision ID: 20261019_49
Revises: 20261019_48
Create Date: 2026-10-19 17:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261019_49"
down_revision: Union[str, None] = "20261019_48"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("tg_flows") as batch:
        batch.add_column(sa.Column("payment_gateway", sa.String(16), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("tg_flows") as batch:
        batch.drop_column("payment_gateway")
