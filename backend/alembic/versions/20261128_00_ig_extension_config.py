"""IG Extension config — per-workspace password and profile settings for the FlashPost Chrome extension.

Revision ID: 20261128_00
Revises: 20261127_01
Create Date: 2026-11-28 20:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20261128_00"
down_revision: Union[str, None] = "20261127_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ig_extension_configs",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("workspace_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=True),
        sa.Column("config_token", sa.String(64), nullable=True),
        sa.Column("full_name", sa.String(200), nullable=True),
        sa.Column("username", sa.String(100), nullable=True),
        sa.Column("bio", sa.String(500), nullable=True),
        sa.Column("profile_photo_url", sa.Text(), nullable=True),
        sa.Column("story_photo_url", sa.Text(), nullable=True),
        sa.Column("link_url", sa.Text(), nullable=True),
        sa.Column("sticker_text", sa.String(200), nullable=True),
        sa.Column("highlight_title", sa.String(100), nullable=True),
        sa.Column("sticker_size", sa.Float(), nullable=True),
        sa.Column("sticker_x", sa.Float(), nullable=True),
        sa.Column("sticker_y", sa.Float(), nullable=True),
        sa.Column("sticker_rotation", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", name="uq_ig_extension_workspace"),
    )
    op.create_index("ix_ig_extension_config_token", "ig_extension_configs", ["config_token"])


def downgrade() -> None:
    op.drop_index("ix_ig_extension_config_token", table_name="ig_extension_configs")
    op.drop_table("ig_extension_configs")
