"""Instagram automations (ManyChat-style): keyword rules + fired-event log.

Additive only: two new tables. No existing table is touched.

Revision ID: 20261114_82
Revises: 20261114_81
Create Date: 2026-11-14 12:30:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "20261114_82"
down_revision: Union[str, None] = "20261114_81"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_JSON = sa.JSON().with_variant(JSONB, "postgresql")


def upgrade() -> None:
    op.create_table(
        "instagram_automations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("instagram_account_id", sa.Uuid(), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("trigger_type", sa.String(length=16), server_default=sa.text("'comment'"), nullable=False),
        sa.Column("keywords", _JSON, nullable=False),
        sa.Column("match_mode", sa.String(length=16), server_default=sa.text("'any'"), nullable=False),
        sa.Column("media_id", sa.String(length=191), nullable=True),
        sa.Column("public_reply_enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("public_replies", _JSON, nullable=False),
        sa.Column("dm_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("dm_text", sa.Text(), nullable=True),
        sa.Column("dm_buttons", _JSON, nullable=False),
        sa.Column("fired_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("last_fired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["instagram_account_id"], ["instagram_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.CheckConstraint("trigger_type IN ('comment', 'dm')", name="ck_instagram_automations_trigger"),
        sa.CheckConstraint("match_mode IN ('any', 'exact')", name="ck_instagram_automations_match"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_instagram_automations_workspace", "instagram_automations", ["workspace_id"])
    op.create_index("ix_instagram_automations_account", "instagram_automations", ["instagram_account_id"])

    op.create_table(
        "instagram_automation_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("automation_id", sa.Uuid(), nullable=False),
        sa.Column("object_id", sa.String(length=191), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("detail", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["automation_id"], ["instagram_automations.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "status IN ('sent', 'simulated', 'skipped', 'failed')",
            name="ck_instagram_automation_event_status",
        ),
        sa.UniqueConstraint("automation_id", "object_id", name="uq_instagram_automation_event_object"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_instagram_automation_events_automation",
        "instagram_automation_events",
        ["automation_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_instagram_automation_events_automation", table_name="instagram_automation_events")
    op.drop_table("instagram_automation_events")
    op.drop_index("ix_instagram_automations_account", table_name="instagram_automations")
    op.drop_index("ix_instagram_automations_workspace", table_name="instagram_automations")
    op.drop_table("instagram_automations")
