"""Affiliates, extra Shark accounts, extensions, support tickets, daily views, avatar fallback.

Additive only: no existing column or row is changed or removed.

Revision ID: 20261015_32
Revises: 20261014_31
Create Date: 2026-10-15
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261015_32"
down_revision: Union[str, None] = "20261014_31"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("invite_code", sa.String(16)))
    op.add_column("users", sa.Column("avatar_data", sa.LargeBinary()))
    op.add_column("users", sa.Column("avatar_content_type", sa.String(40)))
    op.create_index(
        "uq_users_invite_code",
        "users",
        ["invite_code"],
        unique=True,
        postgresql_where=sa.text("invite_code IS NOT NULL"),
        sqlite_where=sa.text("invite_code IS NOT NULL"),
    )

    op.create_table(
        "affiliations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("chief_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("affiliate_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("participation_percent", sa.Numeric(5, 2), nullable=False, server_default="0"),
        sa.Column("status", sa.String(16), nullable=False, server_default="ACTIVE"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("chief_user_id <> affiliate_user_id", name="ck_affiliations_not_self"),
        sa.CheckConstraint(
            "participation_percent >= 0 AND participation_percent <= 100",
            name="ck_affiliations_percent_range",
        ),
        sa.CheckConstraint("status IN ('ACTIVE', 'ENDED')", name="ck_affiliations_status"),
    )
    op.create_index("uq_affiliations_affiliate", "affiliations", ["affiliate_user_id"], unique=True)
    op.create_index("ix_affiliations_chief", "affiliations", ["chief_user_id", "status"])

    op.create_table(
        "shark_accounts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("external_account_id", sa.String(120)),
        sa.Column("webhook_token", sa.String(128), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("last_event_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("workspace_id", "name", name="uq_shark_accounts_workspace_name"),
    )
    op.create_index("ix_shark_accounts_workspace", "shark_accounts", ["workspace_id"])
    op.create_index("ix_shark_accounts_webhook_token", "shark_accounts", ["webhook_token"], unique=True)
    for table in ("shark_leads", "shark_transactions"):
        with op.batch_alter_table(table) as batch:
            batch.add_column(
                sa.Column(
                    "shark_account_id",
                    sa.Uuid(),
                    sa.ForeignKey(
                        "shark_accounts.id", name=f"fk_{table}_shark_account", ondelete="SET NULL"
                    ),
                )
            )
        op.create_index(f"ix_{table}_shark_account", table, ["shark_account_id"])

    op.create_table(
        "extensions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.String(1000)),
        sa.Column("instructions", sa.Text()),
        sa.Column("visible_to_collaborators", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("file_name", sa.String(200)),
        sa.Column("file_size", sa.Integer()),
        sa.Column("file_sha256", sa.String(64)),
        sa.Column("file_data", sa.LargeBinary()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_extensions_workspace_created", "extensions", ["workspace_id", "created_at"])

    op.create_table(
        "support_tickets",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("author_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False, server_default="QUESTION"),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="OPEN"),
        sa.Column("resolution_note", sa.Text()),
        sa.Column("resolved_by_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "status IN ('OPEN', 'IN_PROGRESS', 'RESOLVED', 'CLOSED')", name="ck_support_tickets_status"
        ),
        sa.CheckConstraint("kind IN ('QUESTION', 'PROBLEM')", name="ck_support_tickets_kind"),
    )
    op.create_index(
        "ix_support_tickets_workspace_status", "support_tickets", ["workspace_id", "status", "created_at"]
    )
    op.create_index("ix_support_tickets_author", "support_tickets", ["author_user_id", "created_at"])

    op.create_table(
        "instagram_account_daily_views",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "account_id", sa.Uuid(), sa.ForeignKey("instagram_accounts.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("views", sa.Integer(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("account_id", "day", name="uq_account_daily_views_account_day"),
    )
    op.create_index(
        "ix_account_daily_views_workspace_day", "instagram_account_daily_views", ["workspace_id", "day"]
    )


def downgrade() -> None:
    op.drop_table("instagram_account_daily_views")
    op.drop_table("support_tickets")
    op.drop_table("extensions")
    for table in ("shark_transactions", "shark_leads"):
        op.drop_index(f"ix_{table}_shark_account", table_name=table)
        with op.batch_alter_table(table) as batch:
            batch.drop_constraint(f"fk_{table}_shark_account", type_="foreignkey")
            batch.drop_column("shark_account_id")
    op.drop_table("shark_accounts")
    op.drop_table("affiliations")
    op.drop_index("uq_users_invite_code", table_name="users")
    op.drop_column("users", "avatar_content_type")
    op.drop_column("users", "avatar_data")
    op.drop_column("users", "invite_code")
