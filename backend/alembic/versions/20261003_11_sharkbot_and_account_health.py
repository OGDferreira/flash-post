"""Add workspace Sharkbot events and account health state.

Revision ID: 20261003_11
Revises: 20261003_10
Create Date: 2026-10-03
"""

from typing import Sequence, Union

import secrets
import sqlalchemy as sa
from alembic import op

revision: str = "20261003_11"
down_revision: Union[str, None] = "20261003_10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("instagram_accounts") as batch_op:
        batch_op.drop_constraint("ck_instagram_accounts_status", type_="check")
        batch_op.create_check_constraint(
            "ck_instagram_accounts_status",
            "status IN ('connected', 'disconnected', 'error')",
        )

    with op.batch_alter_table("workspaces") as batch_op:
        batch_op.add_column(sa.Column("sharkbot_webhook_token", sa.String(128), nullable=True))
        batch_op.create_index(
            "ix_workspaces_sharkbot_webhook_token",
            ["sharkbot_webhook_token"],
            unique=True,
        )

    connection = op.get_bind()
    workspaces = connection.execute(sa.text("SELECT id FROM workspaces")).all()
    for (workspace_id,) in workspaces:
        connection.execute(
            sa.text(
                "UPDATE workspaces SET sharkbot_webhook_token = :token WHERE id = :id"
            ),
            {"token": secrets.token_urlsafe(32), "id": workspace_id},
        )

    op.create_table(
        "shark_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=True),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("source_event_key", sa.String(length=64), nullable=False),
        sa.Column("webhook_id", sa.String(length=160), nullable=True),
        sa.Column("transaction_id", sa.String(length=160), nullable=True),
        sa.Column("customer_name", sa.String(length=240), nullable=True),
        sa.Column("customer_username", sa.String(length=120), nullable=True),
        sa.Column("bot_name", sa.String(length=160), nullable=True),
        sa.Column("plan_name", sa.String(length=160), nullable=True),
        sa.Column("amount", sa.Numeric(12, 2), server_default="0", nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["account_id"], ["instagram_accounts.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "source_event_key",
            name="uq_shark_events_workspace_source_key",
        ),
    )
    op.create_index(
        "ix_shark_events_workspace_occurred_at",
        "shark_events",
        ["workspace_id", "occurred_at"],
    )
    op.create_index(
        "ix_shark_events_account_occurred_at",
        "shark_events",
        ["account_id", "occurred_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_shark_events_account_occurred_at", table_name="shark_events")
    op.drop_index("ix_shark_events_workspace_occurred_at", table_name="shark_events")
    op.drop_table("shark_events")
    with op.batch_alter_table("workspaces") as batch_op:
        batch_op.drop_index("ix_workspaces_sharkbot_webhook_token")
        batch_op.drop_column("sharkbot_webhook_token")
    with op.batch_alter_table("instagram_accounts") as batch_op:
        batch_op.drop_constraint("ck_instagram_accounts_status", type_="check")
        batch_op.create_check_constraint(
            "ck_instagram_accounts_status",
            "status IN ('connected', 'disconnected')",
        )
