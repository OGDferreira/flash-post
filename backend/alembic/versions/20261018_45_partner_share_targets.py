"""Share funnels/loops with all partners or chosen ones; linked shared loops.

* ``shared_with`` (loops and funnels): NULL = every partner of the chief, or a
  list of partner user ids.
* ``instagram_loops.linked``: the partner's copy follows the chief's loop
  (same media and schedule) and only gets the partner's own accounts.
* ``instagram_media.template_media_id``: which chief media a copy came from,
  so the linked copy can follow additions and removals.

Additive only.

Revision ID: 20261018_45
Revises: 20261017_44
Create Date: 2026-10-18 01:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261018_45"
down_revision: Union[str, None] = "20261017_44"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("instagram_loops") as batch:
        batch.add_column(sa.Column("shared_with", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("linked", sa.Boolean(), nullable=False, server_default=sa.false()))
    with op.batch_alter_table("tg_flows") as batch:
        batch.add_column(sa.Column("shared_with", sa.JSON(), nullable=True))
    with op.batch_alter_table("instagram_media") as batch:
        batch.add_column(sa.Column("template_media_id", sa.Uuid(), nullable=True))
    op.create_index("ix_instagram_loops_template", "instagram_loops", ["template_loop_id"])


def downgrade() -> None:
    op.drop_index("ix_instagram_loops_template", table_name="instagram_loops")
    with op.batch_alter_table("instagram_media") as batch:
        batch.drop_column("template_media_id")
    with op.batch_alter_table("tg_flows") as batch:
        batch.drop_column("shared_with")
    with op.batch_alter_table("instagram_loops") as batch:
        batch.drop_column("linked")
        batch.drop_column("shared_with")
