"""Per-partner funnel share rules, gateway priority (principal + backups) and audit events.

Only new tables: existing shares, choices and orders are left as they are. A funnel shared
before this has no row and keeps following the partnership's percentage until its owner
sets the rules for that partner; an operation with no gateway rows keeps its current choice.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261022_57"
down_revision: Union[str, None] = "20261022_56"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tg_flow_shares",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("flow_id", sa.Uuid(), sa.ForeignKey("tg_flows.id", ondelete="CASCADE"), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("partner_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("gateway", sa.String(16), nullable=False),
        sa.Column("owner_percent", sa.Numeric(5, 2), nullable=False),
        sa.Column("seller_percent", sa.Numeric(5, 2), nullable=False),
        sa.Column("seller_shop_id", sa.String(64), nullable=True),
        sa.Column("owner_shop_id", sa.String(64), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="ACTIVE"),
        sa.Column("updated_by_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("flow_id", "partner_user_id", name="uq_tg_flow_shares_flow_partner"),
        sa.CheckConstraint("owner_percent >= 0 AND owner_percent < 100", name="ck_tg_flow_shares_owner_percent"),
        sa.CheckConstraint("seller_percent > 0 AND seller_percent <= 100", name="ck_tg_flow_shares_seller_percent"),
        sa.CheckConstraint("owner_percent + seller_percent = 100", name="ck_tg_flow_shares_total"),
        sa.CheckConstraint("status IN ('ACTIVE', 'REVOKED')", name="ck_tg_flow_shares_status"),
        sa.CheckConstraint("gateway IN ('smokepay', 'snakepay')", name="ck_tg_flow_shares_gateway"),
    )
    op.create_index("ix_tg_flow_shares_owner", "tg_flow_shares", ["owner_user_id", "status"])
    op.create_index("ix_tg_flow_shares_partner", "tg_flow_shares", ["partner_user_id", "status"])

    op.add_column("tg_orders", sa.Column("share_id", sa.Uuid(), nullable=True))
    op.add_column("tg_orders", sa.Column("gateway_attempts", sa.JSON(), nullable=True))

    op.create_table(
        "tg_gateway_settings",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("gateway", sa.String(16), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("flow_ids", sa.JSON(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("workspace_id", "gateway", name="uq_tg_gateway_settings_workspace_gateway"),
        sa.CheckConstraint("gateway IN ('smokepay', 'snakepay')", name="ck_tg_gateway_settings_gateway"),
        sa.CheckConstraint("priority >= 1", name="ck_tg_gateway_settings_priority"),
    )

    op.create_table(
        "audit_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), sa.ForeignKey("workspaces.id", ondelete="SET NULL"), nullable=True),
        sa.Column("actor_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("action", sa.String(48), nullable=False),
        sa.Column("entity", sa.String(32), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_audit_events_workspace_created", "audit_events", ["workspace_id", "created_at"])
    op.create_index("ix_audit_events_entity", "audit_events", ["entity", "entity_id"])


def downgrade() -> None:
    op.drop_index("ix_audit_events_entity", table_name="audit_events")
    op.drop_index("ix_audit_events_workspace_created", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_table("tg_gateway_settings")
    with op.batch_alter_table("tg_orders") as batch:
        batch.drop_column("gateway_attempts")
        batch.drop_column("share_id")
    op.drop_index("ix_tg_flow_shares_partner", table_name="tg_flow_shares")
    op.drop_index("ix_tg_flow_shares_owner", table_name="tg_flow_shares")
    op.drop_table("tg_flow_shares")
