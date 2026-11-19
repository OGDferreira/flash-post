"""Global chat messages (self-destruct after 36h).

New table ``global_chat_messages``. Additive only.

Revision ID: 20261113_76
Revises: 20261108_75
Create Date: 2026-11-13 03:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261113_76"
down_revision: Union[str, None] = "20261108_75"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "global_chat_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("author_user_id", sa.Uuid(), nullable=False),
        sa.Column("author_nickname", sa.String(length=40), nullable=False),
        sa.Column("author_avatar_url", sa.String(length=2048), nullable=True),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("image_data", sa.LargeBinary(), nullable=True),
        sa.Column("image_content_type", sa.String(length=40), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["author_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("body IS NOT NULL OR image_data IS NOT NULL", name="ck_global_chat_body_or_image"),
    )
    op.create_index("ix_global_chat_created_at", "global_chat_messages", ["created_at"])
    op.create_index("ix_global_chat_expires_at", "global_chat_messages", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_global_chat_expires_at", table_name="global_chat_messages")
    op.drop_index("ix_global_chat_created_at", table_name="global_chat_messages")
    op.drop_table("global_chat_messages")
