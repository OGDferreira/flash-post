"""Push notifications choice saved on the user, and the activation prompt shown only once.

Additive only. Users that already have a device subscribed start as enabled and answered.

Revision ID: 20261023_62
Revises: 20261023_61
Create Date: 2026-10-23 16:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261023_62"
down_revision: Union[str, None] = "20261023_61"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("push_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("push_prompt_done", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.execute(
        "UPDATE users SET push_enabled = true, push_prompt_done = true "
        "WHERE id IN (SELECT DISTINCT user_id FROM push_subscriptions)"
    )


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_column("push_prompt_done")
        batch.drop_column("push_enabled")
