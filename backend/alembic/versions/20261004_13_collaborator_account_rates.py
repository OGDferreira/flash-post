"""Snapshot collaborator rate for each connected account.

Revision ID: 20261004_13
Revises: 20261003_12
Create Date: 2026-10-04
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261004_13"
down_revision: Union[str, None] = "20261003_12"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.add_column(
        "instagram_accounts",
        sa.Column("collaborator_rate_at_connection", sa.Numeric(10, 2), nullable=True),
    )
    op.execute(
        sa.text(
            """
            UPDATE instagram_accounts
            SET collaborator_rate_at_connection = (
                SELECT workspace_members.rate_per_connection
                FROM workspace_members
                WHERE workspace_members.workspace_id = instagram_accounts.workspace_id
                  AND workspace_members.user_id = instagram_accounts.connected_by_user_id
                  AND workspace_members.role = 'COLLABORATOR'
                  AND workspace_members.status = 'ACTIVE'
            )
            WHERE instagram_accounts.connected_by_user_id IS NOT NULL
            """
        )
    )


def downgrade() -> None:
    op.drop_column("instagram_accounts", "collaborator_rate_at_connection")