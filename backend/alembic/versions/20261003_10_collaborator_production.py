"""Track collaborator connection production and payments.

Revision ID: 20261003_10
Revises: 20261003_09
Create Date: 2026-10-03
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261003_10"
down_revision: Union[str, None] = "20261003_09"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("workspace_members") as batch_op:
        batch_op.add_column(
            sa.Column(
                "rate_per_connection",
                sa.Numeric(10, 2),
                nullable=False,
                server_default="0",
            )
        )
        batch_op.add_column(
            sa.Column(
                "daily_connection_goal",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )
        batch_op.add_column(
            sa.Column(
                "monthly_connection_goal",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )
        batch_op.add_column(
            sa.Column("monthly_bonus", sa.Numeric(10, 2), nullable=False, server_default="0")
        )

    with op.batch_alter_table("instagram_accounts") as batch_op:
        batch_op.add_column(
            sa.Column("connected_by_user_id", sa.Uuid(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("first_connected_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_instagram_accounts_connected_by_user_id_users",
            "users",
            ["connected_by_user_id"],
            ["id"],
            ondelete="SET NULL",
        )

    op.create_table(
        "collaborator_payments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_member_id", sa.Uuid(), nullable=False),
        sa.Column("paid_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column(
            "paid_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["workspace_member_id"], ["workspace_members.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["paid_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_collaborator_payments_member_period",
        "collaborator_payments",
        ["workspace_member_id", "period_start"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_collaborator_payments_member_period",
        table_name="collaborator_payments",
    )
    op.drop_table("collaborator_payments")
    with op.batch_alter_table("instagram_accounts") as batch_op:
        batch_op.drop_constraint(
            "fk_instagram_accounts_connected_by_user_id_users",
            type_="foreignkey",
        )
        batch_op.drop_column("first_connected_at")
        batch_op.drop_column("connected_by_user_id")
    with op.batch_alter_table("workspace_members") as batch_op:
        batch_op.drop_column("monthly_bonus")
        batch_op.drop_column("monthly_connection_goal")
        batch_op.drop_column("daily_connection_goal")
        batch_op.drop_column("rate_per_connection")
