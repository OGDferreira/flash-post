"""Add private Instagram media metadata and loop media assignments.

Revision ID: 20261003_08
Revises: 20261003_07
Create Date: 2026-10-03
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261003_08"
down_revision: Union[str, None] = "20261003_07"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("instagram_accounts") as batch_op:
        batch_op.add_column(
            sa.Column("token_refresh_checked_at", sa.DateTime(timezone=True), nullable=True)
        )

    op.create_table(
        "instagram_media",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("workspace_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("storage_path", sa.String(length=500), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=False),
        sa.Column("media_type", sa.String(length=16), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("caption", sa.String(length=2200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("media_type IN ('image', 'video')", name="ck_instagram_media_type"),
        sa.CheckConstraint("size_bytes > 0", name="ck_instagram_media_size"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_path"),
    )
    op.create_index("ix_instagram_media_workspace_id", "instagram_media", ["workspace_id"])

    op.create_table(
        "instagram_loop_media",
        sa.Column("loop_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("media_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["loop_id"], ["instagram_loops.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["media_id"], ["instagram_media.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("loop_id", "media_id"),
    )
    op.create_index("ix_instagram_loop_media_media_id", "instagram_loop_media", ["media_id"])

    with op.batch_alter_table("instagram_publication_jobs") as batch_op:
        batch_op.add_column(sa.Column("media_id", sa.Uuid(as_uuid=True), nullable=True))
        batch_op.add_column(sa.Column("published_media_id", sa.String(length=128), nullable=True))
        batch_op.create_foreign_key(
            "fk_instagram_publication_jobs_media_id",
            "instagram_media",
            ["media_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("instagram_publication_jobs") as batch_op:
        batch_op.drop_constraint(
            "fk_instagram_publication_jobs_media_id",
            type_="foreignkey",
        )
        batch_op.drop_column("published_media_id")
        batch_op.drop_column("media_id")
    op.drop_index("ix_instagram_loop_media_media_id", table_name="instagram_loop_media")
    op.drop_table("instagram_loop_media")
    op.drop_index("ix_instagram_media_workspace_id", table_name="instagram_media")
    op.drop_table("instagram_media")
    with op.batch_alter_table("instagram_accounts") as batch_op:
        batch_op.drop_column("token_refresh_checked_at")
