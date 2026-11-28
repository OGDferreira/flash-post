"""Scheduled publications: optional thumbnail (Reels cover) + linked ManyChat rule.

Additive only: two nullable id columns on instagram_scheduled_posts. The ORM
declares the foreign keys; we skip the DB-level constraint so the same migration
runs on SQLite (tests) and Postgres (prod). A deleted media/automation just
leaves a dangling id, which the scheduler null-checks before use.

Revision ID: 20261115_85
Revises: 20261115_84
Create Date: 2026-11-15 04:05:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261115_85"
down_revision: Union[str, None] = "20261115_84"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "instagram_scheduled_posts",
        sa.Column("thumbnail_media_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "instagram_scheduled_posts",
        sa.Column("automation_id", sa.Uuid(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("instagram_scheduled_posts", "automation_id")
    op.drop_column("instagram_scheduled_posts", "thumbnail_media_id")
