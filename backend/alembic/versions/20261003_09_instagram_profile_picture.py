"""Store Instagram profile picture URLs for account cards.

Revision ID: 20261003_09
Revises: 20261003_08
Create Date: 2026-10-03
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261003_09"
down_revision: Union[str, None] = "20261003_08"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("instagram_accounts") as batch_op:
        batch_op.add_column(sa.Column("profile_picture_url", sa.String(length=2048)))
        batch_op.add_column(sa.Column("follower_count", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("media_count", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("instagram_accounts") as batch_op:
        batch_op.drop_column("profile_picture_url")
        batch_op.drop_column("follower_count")
        batch_op.drop_column("media_count")
