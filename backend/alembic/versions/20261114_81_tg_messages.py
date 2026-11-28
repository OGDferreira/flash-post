"""Lead conversation log (live chat) + per-lead unread counter.

Additive only: a new ``tg_messages`` table and a non-null-with-default
``unread_count`` column on ``tg_leads``.

Revision ID: 20261114_81
Revises: 20261114_80
Create Date: 2026-11-14 06:40:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261114_81"
down_revision: Union[str, None] = "20261114_80"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tg_leads",
        sa.Column("unread_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_table(
        "tg_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("bot_id", sa.Uuid(), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=False),
        sa.Column("direction", sa.String(length=3), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("tg_file_id", sa.String(length=256), nullable=True),
        sa.Column("media_id", sa.Uuid(), nullable=True),
        sa.Column("sent_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["bot_id"], ["tg_bots.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["lead_id"], ["tg_leads.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["media_id"], ["tg_media.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["sent_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tg_messages_lead_created", "tg_messages", ["lead_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_tg_messages_lead_created", table_name="tg_messages")
    op.drop_table("tg_messages")
    op.drop_column("tg_leads", "unread_count")
