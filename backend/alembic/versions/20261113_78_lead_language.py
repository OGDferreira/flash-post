"""Lead Telegram language code, for per-funnel auto-translation.

Additive only: a nullable string on ``tg_leads``.

Revision ID: 20261113_78
Revises: 20261113_77
Create Date: 2026-11-13 19:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261113_78"
down_revision: Union[str, None] = "20261113_77"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tg_leads", sa.Column("language_code", sa.String(length=16), nullable=True))


def downgrade() -> None:
    op.drop_column("tg_leads", "language_code")
