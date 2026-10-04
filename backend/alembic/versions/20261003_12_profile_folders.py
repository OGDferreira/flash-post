"""Add colored Instagram profile folders.

Revision ID: 20261003_12
Revises: 20261003_11
Create Date: 2026-10-03
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261003_12"
down_revision: Union[str, None] = "20261003_11"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "instagram_profile_folders",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("color", sa.String(length=7), nullable=False, server_default="#00c9d8"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id", "name", name="uq_instagram_profile_folders_name"
        ),
    )
    op.create_index(
        "ix_instagram_profile_folders_workspace_id",
        "instagram_profile_folders",
        ["workspace_id"],
    )
    with op.batch_alter_table("instagram_accounts") as batch_op:
        batch_op.add_column(sa.Column("profile_folder_id", sa.Uuid(), nullable=True))
        batch_op.add_column(
            sa.Column("has_highlights", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch_op.create_foreign_key(
            "fk_instagram_accounts_profile_folder_id",
            "instagram_profile_folders",
            ["profile_folder_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("instagram_accounts") as batch_op:
        batch_op.drop_constraint(
            "fk_instagram_accounts_profile_folder_id", type_="foreignkey"
        )
        batch_op.drop_column("has_highlights")
        batch_op.drop_column("profile_folder_id")
    op.drop_index(
        "ix_instagram_profile_folders_workspace_id",
        table_name="instagram_profile_folders",
    )
    op.drop_table("instagram_profile_folders")
