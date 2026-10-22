"""Folders of funnels: a bot connected to a folder gives each new lead one of its funnels at random."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261022_58"
down_revision: Union[str, None] = "20261022_57"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tg_flow_folders",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_tg_flow_folders_workspace", "tg_flow_folders", ["workspace_id"])
    op.create_table(
        "tg_flow_folder_items",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("folder_id", sa.Uuid(), sa.ForeignKey("tg_flow_folders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("flow_id", sa.Uuid(), sa.ForeignKey("tg_flows.id", ondelete="CASCADE"), nullable=False),
        sa.UniqueConstraint("folder_id", "flow_id", name="uq_tg_flow_folder_items"),
    )
    with op.batch_alter_table("tg_bots") as batch:
        batch.add_column(sa.Column("folder_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key("fk_tg_bots_folder", "tg_flow_folders", ["folder_id"], ["id"], ondelete="SET NULL")


def downgrade() -> None:
    with op.batch_alter_table("tg_bots") as batch:
        batch.drop_constraint("fk_tg_bots_folder", type_="foreignkey")
        batch.drop_column("folder_id")
    op.drop_table("tg_flow_folder_items")
    op.drop_index("ix_tg_flow_folders_workspace", table_name="tg_flow_folders")
    op.drop_table("tg_flow_folders")
