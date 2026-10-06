"""Persist Instagram account error timestamps and isolate inactive accounts.

Revision ID: 20261008_21
Revises: 20261006_20
Create Date: 2026-10-08
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261008_21"
down_revision: Union[str, None] = "20261006_20"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "instagram_accounts",
        sa.Column("error_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        """
        UPDATE instagram_accounts
        SET error_at = updated_at
        WHERE status <> 'connected'
        """
    )
    op.execute(
        """
        UPDATE instagram_accounts
        SET profile_folder_id = NULL
        WHERE status <> 'connected'
        """
    )
    op.execute(
        """
        DELETE FROM instagram_loop_accounts
        WHERE account_id IN (
            SELECT id FROM instagram_accounts WHERE status <> 'connected'
        )
        """
    )
    op.execute(
        """
        DELETE FROM instagram_publication_jobs
        WHERE account_id IN (
            SELECT id FROM instagram_accounts WHERE status <> 'connected'
        )
          AND status IN ('waiting_for_media', 'queued')
        """
    )
    op.execute(
        """
        UPDATE instagram_publication_jobs
        SET status = 'failed',
            last_error = 'Instagram account is inactive.'
        WHERE account_id IN (
            SELECT id FROM instagram_accounts WHERE status <> 'connected'
        )
          AND status = 'publishing'
        """
    )


def downgrade() -> None:
    op.drop_column("instagram_accounts", "error_at")
