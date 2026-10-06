"""Store encrypted email two-factor passwords.

Revision ID: 20261006_18
Revises: 20261006_17
Create Date: 2026-10-07
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261006_18"
down_revision: Union[str, None] = "20261006_17"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "email_accounts",
        sa.Column(
            "encrypted_two_factor_password",
            sa.String(length=4096),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("email_accounts", "encrypted_two_factor_password")
