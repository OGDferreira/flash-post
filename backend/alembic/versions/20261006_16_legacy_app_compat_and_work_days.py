"""Preserve legacy Instagram credentials and track collaborator workdays.

Revision ID: 20261006_16
Revises: 20261005_15
Create Date: 2026-10-06
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261006_16"
down_revision: Union[str, None] = "20261005_15"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "instagram_meta_apps",
        sa.Column(
            "credential_kind",
            sa.String(length=32),
            server_default=sa.text("'legacy'"),
            nullable=False,
        ),
    )
    op.create_table(
        "collaborator_work_days",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("workspace_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("workspace_member_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("work_date", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["workspace_member_id"], ["workspace_members.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_member_id",
            "work_date",
            name="uq_collaborator_work_days_member_date",
        ),
    )
    op.create_index(
        "ix_collaborator_work_days_workspace_member_date",
        "collaborator_work_days",
        ["workspace_member_id", "work_date"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_collaborator_work_days_workspace_member_date",
        table_name="collaborator_work_days",
    )
    op.drop_table("collaborator_work_days")
    op.drop_column("instagram_meta_apps", "credential_kind")
