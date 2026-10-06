"""Add workspace email account control.

Revision ID: 20261006_17
Revises: 20261006_16
Create Date: 2026-10-06
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261006_17"
down_revision: Union[str, None] = "20261006_16"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "email_accounts",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("workspace_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("supplier", sa.String(length=120), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("encrypted_password", sa.String(length=4096), nullable=False),
        sa.Column("responsible", sa.String(length=160), nullable=True),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default="available",
            nullable=False,
        ),
        sa.Column("observation", sa.Text(), nullable=True),
        sa.Column(
            "encrypted_two_factor_code",
            sa.String(length=4096),
            nullable=False,
        ),
        sa.Column("error_attachment_path", sa.String(length=512), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('available', 'in_use', 'completed', 'error', 'returned')",
            name="ck_email_accounts_status",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_email_accounts_workspace_status",
        "email_accounts",
        ["workspace_id", "status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_email_accounts_workspace_status", table_name="email_accounts"
    )
    op.drop_table("email_accounts")
