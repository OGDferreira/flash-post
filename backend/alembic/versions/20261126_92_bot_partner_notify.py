"""Sale notifications for bot partners: an optional webhook URL the partner configures to
receive a sale ping (Telegram bot webhook, Zapier, etc.) on top of the in-app/push notice.

Additive only. Adds bot_partners.notify_webhook_url.

Revision ID: 20261126_92
Revises: 20261126_91
Create Date: 2026-11-26 10:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261126_92"
down_revision: Union[str, None] = "20261126_91"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "bot_partners", sa.Column("notify_webhook_url", sa.String(length=500), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("bot_partners", "notify_webhook_url")
