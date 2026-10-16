"""Owner-entered expenses for the monthly profit.

Additive only: new table.

Revision ID: 20261016_38
Revises: 20261016_37
Create Date: 2026-10-16 18:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261016_38"
down_revision: Union[str, None] = "20261016_37"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "financial_expenses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("description", sa.String(length=160), nullable=False),
        sa.Column("spent_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.CheckConstraint("amount > 0", name="ck_financial_expenses_amount_positive"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_financial_expenses_workspace_spent_at", "financial_expenses", ["workspace_id", "spent_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_financial_expenses_workspace_spent_at", table_name="financial_expenses")
    op.drop_table("financial_expenses")
