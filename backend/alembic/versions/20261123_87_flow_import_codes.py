"""Short funnel import codes (FBF-XXX-XXX).

Additive only: a new table mapping a short code to a funnel, with an expiry. Old
long signed codes keep importing through the token fallback until they expire.

Revision ID: 20261123_87
Revises: 20261123_86
Create Date: 2026-11-23 22:55:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision: str = "20261123_87"
down_revision: Union[str, None] = "20261123_86"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tg_flow_import_codes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("flow_id", UUID(as_uuid=True), sa.ForeignKey("tg_flows.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("code", name="uq_tg_flow_import_codes_code"),
    )
    op.create_index("ix_tg_flow_import_codes_flow", "tg_flow_import_codes", ["flow_id"])


def downgrade() -> None:
    op.drop_index("ix_tg_flow_import_codes_flow", table_name="tg_flow_import_codes")
    op.drop_table("tg_flow_import_codes")
