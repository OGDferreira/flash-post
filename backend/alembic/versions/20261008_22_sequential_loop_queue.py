"""Track sequential media allocation and publication queue order.

Revision ID: 20261008_22
Revises: 20261008_21
Create Date: 2026-10-08
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261008_22"
down_revision: Union[str, None] = "20261008_21"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "instagram_loops",
        sa.Column("next_media_index", sa.Integer(), nullable=True),
    )
    op.add_column(
        "instagram_loops",
        sa.Column(
            "next_queue_sequence",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )
    op.add_column(
        "instagram_publication_jobs",
        sa.Column("queue_sequence", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("instagram_publication_jobs", "queue_sequence")
    op.drop_column("instagram_loops", "next_queue_sequence")
    op.drop_column("instagram_loops", "next_media_index")
