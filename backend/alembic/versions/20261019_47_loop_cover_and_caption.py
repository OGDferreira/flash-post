"""Reels cover and one caption for every post of a loop.

* ``instagram_loops.caption_mode`` / ``caption``: per_media keeps each video's
  caption; all puts the loop caption on every post.
* ``instagram_loops.cover_mode`` / ``cover_media_id``: auto, one cover for every
  video, or each video's own ``instagram_media.cover_media_id``.
* ``instagram_media.is_cover``: a JPEG uploaded only to be a cover.

Additive only.

Revision ID: 20261019_47
Revises: 20261018_46
Create Date: 2026-10-19 00:30:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261019_47"
down_revision: Union[str, None] = "20261018_46"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("instagram_loops") as batch:
        batch.add_column(sa.Column("caption_mode", sa.String(16), nullable=False, server_default="per_media"))
        batch.add_column(sa.Column("caption", sa.String(2200), nullable=True))
        batch.add_column(sa.Column("cover_mode", sa.String(16), nullable=False, server_default="auto"))
        batch.add_column(sa.Column("cover_media_id", sa.Uuid(), nullable=True))
        batch.create_check_constraint(
            "ck_instagram_loops_caption_mode", "caption_mode IN ('per_media', 'all')"
        )
        batch.create_check_constraint(
            "ck_instagram_loops_cover_mode", "cover_mode IN ('auto', 'all', 'per_media')"
        )
    with op.batch_alter_table("instagram_media") as batch:
        batch.add_column(sa.Column("is_cover", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("cover_media_id", sa.Uuid(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("instagram_media") as batch:
        batch.drop_column("cover_media_id")
        batch.drop_column("is_cover")
    with op.batch_alter_table("instagram_loops") as batch:
        batch.drop_constraint("ck_instagram_loops_cover_mode", type_="check")
        batch.drop_constraint("ck_instagram_loops_caption_mode", type_="check")
        batch.drop_column("cover_media_id")
        batch.drop_column("cover_mode")
        batch.drop_column("caption")
        batch.drop_column("caption_mode")
