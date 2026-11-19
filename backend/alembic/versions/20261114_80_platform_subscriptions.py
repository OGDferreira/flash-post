"""Platform access subscriptions: plans, subscriptions, charges, liberation codes.

Additive only. Seeds three plans (weekly/monthly/annual) with placeholder prices
the Super Admin edits in the admin panel.

Revision ID: 20261114_80
Revises: 20261114_79
Create Date: 2026-11-14 05:00:00
"""
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261114_80"
down_revision: Union[str, None] = "20261114_79"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    plans = op.create_table(
        "platform_plans",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("price", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("period_days", sa.Integer(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_platform_plans_code"),
        sa.CheckConstraint("price >= 0", name="ck_platform_plans_price"),
        sa.CheckConstraint("period_days > 0", name="ck_platform_plans_period"),
    )

    op.create_table(
        "platform_subscriptions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("plan_id", sa.Uuid(), nullable=True),
        sa.Column("trial_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["plan_id"], ["platform_plans.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_platform_subscriptions_user"),
        sa.CheckConstraint(
            "status IN ('trialing', 'active', 'past_due', 'canceled')",
            name="ck_platform_subscriptions_status",
        ),
    )

    op.create_table(
        "platform_subscription_charges",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("subscription_id", sa.Uuid(), nullable=False),
        sa.Column("plan_id", sa.Uuid(), nullable=True),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("period_days", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("external_id", sa.String(length=80), nullable=False),
        sa.Column("pix_copy_paste", sa.Text(), nullable=True),
        sa.Column("pix_txid", sa.String(length=140), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["subscription_id"], ["platform_subscriptions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["plan_id"], ["platform_plans.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("external_id", name="uq_platform_sub_charges_external_id"),
        sa.CheckConstraint(
            "status IN ('pending', 'paid', 'expired', 'canceled')",
            name="ck_platform_sub_charges_status",
        ),
    )
    op.create_index("ix_platform_sub_charges_subscription", "platform_subscription_charges", ["subscription_id"])

    op.create_table(
        "platform_liberation_codes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("days", sa.Integer(), nullable=False),
        sa.Column("note", sa.String(length=160), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("redeemed_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("redeemed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["redeemed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_platform_liberation_code"),
        sa.CheckConstraint("days > 0", name="ck_platform_liberation_days"),
    )

    # Seed the three plans with placeholder prices (the Super Admin edits them).
    op.bulk_insert(
        plans,
        [
            {"id": uuid.uuid4(), "code": "weekly", "name": "Semanal", "price": "19.90", "period_days": 7, "sort_order": 1, "is_active": True},
            {"id": uuid.uuid4(), "code": "monthly", "name": "Mensal", "price": "59.90", "period_days": 30, "sort_order": 2, "is_active": True},
            {"id": uuid.uuid4(), "code": "annual", "name": "Anual", "price": "499.90", "period_days": 365, "sort_order": 3, "is_active": True},
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_platform_sub_charges_subscription", table_name="platform_subscription_charges")
    op.drop_table("platform_liberation_codes")
    op.drop_table("platform_subscription_charges")
    op.drop_table("platform_subscriptions")
    op.drop_table("platform_plans")
