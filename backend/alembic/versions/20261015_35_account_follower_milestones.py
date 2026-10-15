"""Follower milestones per Instagram account.

Additive only: creates one new table.

Revision ID: 20261015_35
Revises: 20261015_34
Create Date: 2026-10-15
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261015_35"
down_revision: Union[str, None] = "20261015_34"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "account_follower_milestones",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "account_id", sa.Uuid(), sa.ForeignKey("instagram_accounts.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("threshold", sa.Integer(), nullable=False),
        sa.Column("followers", sa.Integer(), nullable=False),
        sa.Column("delivered", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("account_id", "threshold", name="uq_account_follower_milestones"),
    )


def downgrade() -> None:
    op.drop_table("account_follower_milestones")
