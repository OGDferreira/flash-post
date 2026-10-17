"""Partners platform: commission acceptance, shared templates, split records, in-app notices.

Additive only: new nullable columns and one new table.

Revision ID: 20261016_39
Revises: 20261016_38
Create Date: 2026-10-16 22:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261016_39"
down_revision: Union[str, None] = "20261016_38"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("affiliations") as batch:
        batch.add_column(sa.Column("accepted_percent", sa.Numeric(precision=5, scale=2), nullable=True))
        batch.add_column(sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True))
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("invited_by_user_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key("fk_users_invited_by", "users", ["invited_by_user_id"], ["id"], ondelete="SET NULL")
    with op.batch_alter_table("instagram_loops") as batch:
        batch.add_column(sa.Column("shared", sa.Boolean(), server_default=sa.text("false"), nullable=False))
        batch.add_column(sa.Column("template_loop_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key(
            "fk_instagram_loops_template", "instagram_loops", ["template_loop_id"], ["id"], ondelete="SET NULL"
        )
    with op.batch_alter_table("tg_flows") as batch:
        batch.add_column(sa.Column("shared", sa.Boolean(), server_default=sa.text("false"), nullable=False))
        batch.add_column(sa.Column("template_flow_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("customized_at", sa.DateTime(timezone=True), nullable=True))
        batch.create_foreign_key("fk_tg_flows_template", "tg_flows", ["template_flow_id"], ["id"], ondelete="SET NULL")
    with op.batch_alter_table("tg_orders") as batch:
        batch.add_column(sa.Column("shop_ref", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("split_chief_user_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("split_percent", sa.Numeric(precision=5, scale=2), nullable=True))
        batch.add_column(sa.Column("split_amount", sa.Numeric(precision=12, scale=2), nullable=True))
        batch.add_column(sa.Column("partner_net", sa.Numeric(precision=12, scale=2), nullable=True))
        batch.create_foreign_key(
            "fk_tg_orders_split_chief", "users", ["split_chief_user_id"], ["id"], ondelete="SET NULL"
        )
    op.create_index("ix_tg_orders_split_chief", "tg_orders", ["split_chief_user_id", "paid_at"], unique=False)
    op.create_table(
        "app_notifications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("body", sa.String(length=500), nullable=False),
        sa.Column("url", sa.String(length=255), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_app_notifications_user_created", "app_notifications", ["user_id", "created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_app_notifications_user_created", table_name="app_notifications")
    op.drop_table("app_notifications")
    op.drop_index("ix_tg_orders_split_chief", table_name="tg_orders")
    with op.batch_alter_table("tg_orders") as batch:
        batch.drop_constraint("fk_tg_orders_split_chief", type_="foreignkey")
        for column in ("partner_net", "split_amount", "split_percent", "split_chief_user_id", "shop_ref"):
            batch.drop_column(column)
    with op.batch_alter_table("tg_flows") as batch:
        batch.drop_constraint("fk_tg_flows_template", type_="foreignkey")
        for column in ("customized_at", "template_flow_id", "shared"):
            batch.drop_column(column)
    with op.batch_alter_table("instagram_loops") as batch:
        batch.drop_constraint("fk_instagram_loops_template", type_="foreignkey")
        batch.drop_column("template_loop_id")
        batch.drop_column("shared")
    with op.batch_alter_table("users") as batch:
        batch.drop_constraint("fk_users_invited_by", type_="foreignkey")
        batch.drop_column("invited_by_user_id")
    with op.batch_alter_table("affiliations") as batch:
        batch.drop_column("accepted_at")
        batch.drop_column("accepted_percent")
