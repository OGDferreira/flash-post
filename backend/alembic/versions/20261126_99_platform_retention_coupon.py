"""Anti-churn retention coupon for the FlashPost platform subscription.

When an owner signals they want to cancel, the platform can offer a discount coupon
(Super Admin sets percent / validity / on-off in system_settings) before blocking access.
Paying a charge with the coupon applies the discount and renews the subscription.

Additive only:
- new table platform_retention_coupons
- platform_subscription_charges.retention_coupon_id (plain Uuid, nullable, no FK)

Revision ID: 20261126_99
Revises: 20261126_98
Create Date: 2026-11-26 19:10:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261126_99"
down_revision: Union[str, None] = "20261126_98"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "platform_retention_coupons",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("percent", sa.Numeric(5, 2), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="offered"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("percent > 0 AND percent <= 90", name="ck_platform_retention_percent"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_platform_retention_user", "platform_retention_coupons", ["user_id"])
    op.add_column(
        "platform_subscription_charges",
        sa.Column("retention_coupon_id", sa.Uuid(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("platform_subscription_charges", "retention_coupon_id")
    op.drop_index("ix_platform_retention_user", table_name="platform_retention_coupons")
    op.drop_table("platform_retention_coupons")
