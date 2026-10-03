"""Store Instagram professional accounts per workspace.

Revision ID: 20261003_04
Revises: 20261002_03
Create Date: 2026-10-03
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261003_04"
down_revision: Union[str, None] = "20261002_03"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "instagram_accounts",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("workspace_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("instagram_user_id", sa.String(length=128), nullable=False),
        sa.Column("username", sa.String(length=100), nullable=False),
        sa.Column("encrypted_access_token", sa.String(length=2048), nullable=False),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("connected_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "instagram_user_id",
            name="uq_instagram_accounts_workspace_user",
        ),
    )
    op.create_index(
        "ix_instagram_accounts_workspace_id",
        "instagram_accounts",
        ["workspace_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_instagram_accounts_workspace_id", table_name="instagram_accounts")
    op.drop_table("instagram_accounts")
