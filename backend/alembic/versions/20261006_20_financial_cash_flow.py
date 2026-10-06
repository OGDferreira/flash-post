"""Add cash-flow withdrawals and preserve Smokepay operation names.

Revision ID: 20261006_20
Revises: 20261007_19
Create Date: 2026-10-06
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261006_20"
down_revision: Union[str, None] = "20261007_19"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "shark_events",
        sa.Column("operation_name", sa.String(length=120), nullable=True),
    )
    op.execute(
        """
        UPDATE shark_events
        SET operation_name = (
            SELECT smokepay_operations.name
            FROM smokepay_operations
            WHERE smokepay_operations.id = shark_events.operation_id
        )
        WHERE operation_id IS NOT NULL
        """
    )
    op.create_table(
        "financial_withdrawals",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("workspace_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("note", sa.String(length=240), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("amount > 0", name="ck_financial_withdrawals_amount_positive"),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_financial_withdrawals_workspace_created_at",
        "financial_withdrawals",
        ["workspace_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_financial_withdrawals_workspace_created_at",
        table_name="financial_withdrawals",
    )
    op.drop_table("financial_withdrawals")
    op.drop_column("shark_events", "operation_name")
