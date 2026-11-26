"""Platform subscription: authorized recurring card billing (Stripe).

Additive only. Adds the columns that let an owner's platform subscription be
charged automatically each cycle on a saved card (Stripe subscription), instead
of generating a fresh PIX per cycle:

- billing_method: how the current window was last paid ("pix" | "card").
- stripe_customer_id / stripe_subscription_id: the Stripe handles used to debit
  the saved card automatically and to cancel the authorization.

Revision ID: 20261119_86
Revises: 20261115_85
Create Date: 2026-11-19 21:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261119_86"
down_revision: Union[str, None] = "20261115_85"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "platform_subscriptions",
        sa.Column("billing_method", sa.String(length=16), nullable=True),
    )
    op.add_column(
        "platform_subscriptions",
        sa.Column("stripe_customer_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "platform_subscriptions",
        sa.Column("stripe_subscription_id", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_platform_subscriptions_stripe_sub",
        "platform_subscriptions",
        ["stripe_subscription_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_platform_subscriptions_stripe_sub", table_name="platform_subscriptions")
    op.drop_column("platform_subscriptions", "stripe_subscription_id")
    op.drop_column("platform_subscriptions", "stripe_customer_id")
    op.drop_column("platform_subscriptions", "billing_method")
