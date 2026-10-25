"""fee_change_log

Revision ID: 20261025_67
Revises: 20261025_66
Create Date: 2026-10-25 15:32:57.267000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20261025_67"
down_revision: Union[str, None] = "20261025_66"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "fee_change_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("changed_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("old_fee", sa.Float(), nullable=True),
        sa.Column("new_fee", sa.Float(), nullable=True),
        sa.Column("is_global_change", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["changed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_fee_change_logs_changed_by", "fee_change_logs", ["changed_by_user_id"], unique=False)
    op.create_index("ix_fee_change_logs_created", "fee_change_logs", ["created_at"], unique=False)
    op.create_index("ix_fee_change_logs_user", "fee_change_logs", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_fee_change_logs_user", table_name="fee_change_logs")
    op.drop_index("ix_fee_change_logs_created", table_name="fee_change_logs")
    op.drop_index("ix_fee_change_logs_changed_by", table_name="fee_change_logs")
    op.drop_table("fee_change_logs")
