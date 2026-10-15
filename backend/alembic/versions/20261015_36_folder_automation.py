"""Folder auto-detect rules and loop auto folders.

Additive only: three new columns with defaults.

Revision ID: 20261015_36
Revises: 20261015_35
Create Date: 2026-10-15
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261015_36"
down_revision: Union[str, None] = "20261015_35"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "instagram_profile_folders",
        sa.Column("auto_prefixes", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )
    op.add_column(
        "instagram_profile_folders",
        sa.Column("auto_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.add_column(
        "instagram_loops",
        sa.Column("auto_folder_ids", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )


def downgrade() -> None:
    op.drop_column("instagram_loops", "auto_folder_ids")
    op.drop_column("instagram_profile_folders", "auto_enabled")
    op.drop_column("instagram_profile_folders", "auto_prefixes")
