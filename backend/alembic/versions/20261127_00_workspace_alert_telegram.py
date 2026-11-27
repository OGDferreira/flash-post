"""Workspace-level Telegram alert channel for operational notices (account disconnected).

Additive only. Both columns are optional; when unset, the owner still gets the in-app
notice and web push, just not a Telegram message.

Revision ID: 20261127_97
Revises: 20261126_96
Create Date: 2026-11-27 00:30:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261127_00"
down_revision: Union[str, None] = "20261126_99"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("workspaces") as batch_op:
        batch_op.add_column(
            sa.Column("alerts_telegram_chat_id", sa.BigInteger(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("alerts_telegram_bot_id", sa.Uuid(), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_workspaces_alerts_bot",
            "tg_bots",
            ["alerts_telegram_bot_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("workspaces") as batch_op:
        batch_op.drop_constraint("fk_workspaces_alerts_bot", type_="foreignkey")
        batch_op.drop_column("alerts_telegram_bot_id")
        batch_op.drop_column("alerts_telegram_chat_id")
