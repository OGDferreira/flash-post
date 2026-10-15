"""Collaborator invite links.

Additive only: creates one new table.

Revision ID: 20261015_33
Revises: 20261015_32
Create Date: 2026-10-15
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261015_33"
down_revision: Union[str, None] = "20261015_32"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "collaborator_invites",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("rate_per_connection", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("daily_connection_goal", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("monthly_connection_goal", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("monthly_bonus", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("max_uses", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("uses", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("uq_collaborator_invites_token_hash", "collaborator_invites", ["token_hash"], unique=True)
    op.create_index("ix_collaborator_invites_workspace", "collaborator_invites", ["workspace_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_collaborator_invites_workspace", table_name="collaborator_invites")
    op.drop_index("uq_collaborator_invites_token_hash", table_name="collaborator_invites")
    op.drop_table("collaborator_invites")
