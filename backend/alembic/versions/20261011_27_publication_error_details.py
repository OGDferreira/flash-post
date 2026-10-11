"""Store error category on jobs and context on diagnostics events.

Revision ID: 20261011_27
Revises: 20261011_26
Create Date: 2026-10-11
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261011_27"
down_revision: Union[str, None] = "20261011_26"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "instagram_publication_jobs",
        sa.Column("error_category", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "instagram_publication_jobs",
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("diagnostics_events", sa.Column("account_id", sa.Uuid(), nullable=True))
    op.add_column("diagnostics_events", sa.Column("loop_id", sa.Uuid(), nullable=True))
    op.add_column("diagnostics_events", sa.Column("job_id", sa.Uuid(), nullable=True))
    op.add_column(
        "diagnostics_events", sa.Column("category", sa.String(length=32), nullable=True)
    )
    op.add_column("diagnostics_events", sa.Column("meta_code", sa.Integer(), nullable=True))


def downgrade() -> None:
    for column in ("meta_code", "category", "job_id", "loop_id", "account_id"):
        op.drop_column("diagnostics_events", column)
    op.drop_column("instagram_publication_jobs", "next_retry_at")
    op.drop_column("instagram_publication_jobs", "error_category")
