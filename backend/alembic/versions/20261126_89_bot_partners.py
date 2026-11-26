"""Bot partnerships: share a bot (and its funnel) with an independent user, split sales.

Additive only. Adds three tables:
- bot_partners: one row per (bot, partner), with the partner's cut, the per-sale bot fee
  and the status (PENDING/ACTIVE/PAUSED/DECLINED/REVOKED).
- bot_partner_sales: the split recorded for each paid order on a shared bot.
- bot_partner_payouts: logged withdrawals/payouts so each side sees when the other received.

Revision ID: 20261126_89
Revises: 20261124_88
Create Date: 2026-11-26 05:30:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261126_89"
down_revision: Union[str, None] = "20261124_88"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "bot_partners",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("bot_id", sa.Uuid(), sa.ForeignKey("tg_bots.id", ondelete="CASCADE"), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("partner_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("partner_percent", sa.Numeric(5, 2), nullable=False, server_default="0"),
        sa.Column("bot_fee", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="PENDING"),
        sa.Column("invited_by_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("bot_id", "partner_user_id", name="uq_bot_partners_bot_partner"),
        sa.CheckConstraint("owner_user_id <> partner_user_id", name="ck_bot_partners_not_self"),
        sa.CheckConstraint("partner_percent >= 0 AND partner_percent <= 100", name="ck_bot_partners_percent_range"),
        sa.CheckConstraint("bot_fee >= 0", name="ck_bot_partners_bot_fee"),
        sa.CheckConstraint(
            "status IN ('PENDING', 'ACTIVE', 'PAUSED', 'DECLINED', 'REVOKED')",
            name="ck_bot_partners_status",
        ),
    )
    op.create_index("ix_bot_partners_owner", "bot_partners", ["owner_user_id", "status"])
    op.create_index("ix_bot_partners_partner", "bot_partners", ["partner_user_id", "status"])

    op.create_table(
        "bot_partner_sales",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("partnership_id", sa.Uuid(), sa.ForeignKey("bot_partners.id", ondelete="CASCADE"), nullable=False),
        sa.Column("order_id", sa.Uuid(), sa.ForeignKey("tg_orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("bot_id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("partner_user_id", sa.Uuid(), nullable=False),
        sa.Column("gross", sa.Numeric(12, 2), nullable=False),
        sa.Column("gateway_fee", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("bot_fee", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("net", sa.Numeric(12, 2), nullable=False),
        sa.Column("partner_percent", sa.Numeric(5, 2), nullable=False),
        sa.Column("partner_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("owner_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("order_id", name="uq_bot_partner_sales_order"),
    )
    op.create_index("ix_bot_partner_sales_partnership_paid", "bot_partner_sales", ["partnership_id", "paid_at"])
    op.create_index("ix_bot_partner_sales_partner_paid", "bot_partner_sales", ["partner_user_id", "paid_at"])
    op.create_index("ix_bot_partner_sales_owner_paid", "bot_partner_sales", ["owner_user_id", "paid_at"])

    op.create_table(
        "bot_partner_payouts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("partnership_id", sa.Uuid(), sa.ForeignKey("bot_partners.id", ondelete="CASCADE"), nullable=False),
        sa.Column("party", sa.String(length=8), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("party IN ('owner', 'partner')", name="ck_bot_partner_payouts_party"),
        sa.CheckConstraint("amount > 0", name="ck_bot_partner_payouts_amount"),
    )
    op.create_index("ix_bot_partner_payouts_partnership_at", "bot_partner_payouts", ["partnership_id", "paid_at"])


def downgrade() -> None:
    op.drop_table("bot_partner_payouts")
    op.drop_table("bot_partner_sales")
    op.drop_table("bot_partners")
