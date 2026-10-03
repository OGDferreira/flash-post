"""Store Instagram app credentials per workspace.

Revision ID: 20261003_05
Revises: 20261003_04
Create Date: 2026-10-03
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261003_05"
down_revision: Union[str, None] = "20261003_04"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "instagram_app_credentials",
        sa.Column("workspace_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("app_id", sa.String(length=64), nullable=False),
        sa.Column("encrypted_app_secret", sa.String(length=2048), nullable=False),
        sa.Column("revision", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("workspace_id"),
    )


def downgrade() -> None:
    op.drop_table("instagram_app_credentials")
