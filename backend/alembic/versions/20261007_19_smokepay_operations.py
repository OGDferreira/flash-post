"""Add Smokepay webhook operations and sale splits.

Revision ID: 20261007_19
Revises: 20261006_18
Create Date: 2026-10-07
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261007_19"
down_revision: Union[str, None] = "20261006_18"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "workspaces",
        sa.Column(
            "smokepay_daily_goal",
            sa.Numeric(12, 2),
            server_default="0",
            nullable=False,
        ),
    )
    op.create_table(
        "smokepay_operations",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("workspace_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column(
            "split_percent",
            sa.Numeric(5, 2),
            server_default="100",
            nullable=False,
        ),
        sa.Column("webhook_key_hash", sa.String(length=64), nullable=False),
        sa.Column("encrypted_webhook_key", sa.String(length=4096), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ),
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
            "split_percent >= 0 AND split_percent <= 100",
            name="ck_smokepay_operations_split_percent",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("webhook_key_hash", name="uq_smokepay_operations_key_hash"),
    )
    op.create_index(
        "ix_smokepay_operations_workspace",
        "smokepay_operations",
        ["workspace_id"],
    )
    op.add_column(
        "shark_events",
        sa.Column("operation_id", sa.Uuid(as_uuid=True), nullable=True),
    )
    op.add_column(
        "shark_events",
        sa.Column("net_amount", sa.Numeric(12, 2), nullable=True),
    )
    with op.batch_alter_table("shark_events") as batch_op:
        batch_op.create_foreign_key(
            "fk_shark_events_operation_id_smokepay_operations",
            "smokepay_operations",
            ["operation_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.create_index(
        "ix_shark_events_operation_occurred_at",
        "shark_events",
        ["operation_id", "occurred_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_shark_events_operation_occurred_at", table_name="shark_events")
    with op.batch_alter_table("shark_events") as batch_op:
        batch_op.drop_constraint(
            "fk_shark_events_operation_id_smokepay_operations",
            type_="foreignkey",
        )
    op.drop_column("shark_events", "net_amount")
    op.drop_column("shark_events", "operation_id")
    op.drop_index("ix_smokepay_operations_workspace", table_name="smokepay_operations")
    op.drop_table("smokepay_operations")
    op.drop_column("workspaces", "smokepay_daily_goal")
