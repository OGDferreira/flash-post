"""Instagram API with Unified Login support.

Additive only. Adds:
- instagram_meta_apps.config_id: the Facebook Login for Business configuration ID
  (not a secret), only set for Unified Login apps.
- instagram_accounts.login_kind: how the account was connected. Existing rows keep
  the Instagram Login flow ("instagram_login"); Unified Login accounts use
  "unified_login" (graph.facebook.com + Business Integration System User token).
- instagram_accounts.client_business_id: the client's business ID for Unified Login
  accounts, kept for the Business Integration System User token management API.

Nothing existing changes behaviour: the defaults preserve the current flow.

Revision ID: 20261124_88
Revises: 20261123_87
Create Date: 2026-11-24 18:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261124_88"
down_revision: Union[str, None] = "20261123_87"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "instagram_meta_apps",
        sa.Column("config_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "instagram_accounts",
        sa.Column(
            "login_kind",
            sa.String(length=32),
            nullable=False,
            server_default="instagram_login",
        ),
    )
    op.add_column(
        "instagram_accounts",
        sa.Column("client_business_id", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("instagram_accounts", "client_business_id")
    op.drop_column("instagram_accounts", "login_kind")
    op.drop_column("instagram_meta_apps", "config_id")
