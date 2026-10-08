"""Track the import batch of email accounts.

Revision ID: 20261008_23
Revises: 20261008_22
Create Date: 2026-10-08
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261008_23"
down_revision: Union[str, None] = "20261008_22"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "email_accounts",
        sa.Column("import_batch_id", sa.Uuid(as_uuid=True), nullable=True),
    )
    op.create_index(
        "ix_email_accounts_import_batch_id",
        "email_accounts",
        ["import_batch_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_email_accounts_import_batch_id", table_name="email_accounts")
    op.drop_column("email_accounts", "import_batch_id")
