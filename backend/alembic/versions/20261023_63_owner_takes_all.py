"""Funnel owner takes 100% of a partner's sales; bots taken over by the Super Admin.

* ``tg_flow_shares.owner_takes_all``; ``tg_orders.seller_hidden`` and ``tg_leads.seller_hidden``.
* ``tg_bots.home_workspace_id``: a bot the Super Admin hid now runs in the Super Admin's own
  operation and goes back to this one when shown again. The bots already hidden move there now
  (with their leads, groups, subscriptions and jobs), keeping their funnel so they never stop.

Revision ID: 20261023_63
Revises: 20261023_62
Create Date: 2026-10-23 20:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261023_63"
down_revision: Union[str, None] = "20261023_62"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

BOT_TABLES = ("tg_leads", "tg_groups", "tg_subscriptions", "tg_jobs")


def upgrade() -> None:
    with op.batch_alter_table("tg_flow_shares") as batch:
        batch.add_column(sa.Column("owner_takes_all", sa.Boolean(), nullable=False, server_default=sa.false()))
    with op.batch_alter_table("tg_orders") as batch:
        batch.add_column(sa.Column("seller_hidden", sa.Boolean(), nullable=False, server_default=sa.false()))
    with op.batch_alter_table("tg_leads") as batch:
        batch.add_column(sa.Column("seller_hidden", sa.Boolean(), nullable=False, server_default=sa.false()))
    with op.batch_alter_table("tg_bots") as batch:
        batch.add_column(sa.Column("home_workspace_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key(
            "fk_tg_bots_home_workspace", "workspaces", ["home_workspace_id"], ["id"], ondelete="SET NULL"
        )

    bind = op.get_bind()
    admin = bind.execute(sa.text(
        "SELECT w.id FROM workspaces w JOIN users u ON u.id = w.owner_id "
        "WHERE u.platform_role = 'SUPER_ADMIN' ORDER BY w.created_at"
    )).fetchall()
    if len(admin) != 1:
        return  # no single Super Admin operation: the hidden bots stay hidden where they are
    admin_id = admin[0][0]
    bots = bind.execute(sa.text(
        "SELECT id, workspace_id FROM tg_bots WHERE hidden_by_admin AND workspace_id <> :admin"
    ), {"admin": admin_id}).fetchall()
    for bot_id, home in bots:
        for table in BOT_TABLES:
            bind.execute(sa.text(f"UPDATE {table} SET workspace_id = :admin WHERE bot_id = :bot"), {"admin": admin_id, "bot": bot_id})
        bind.execute(sa.text(
            "UPDATE tg_bots SET workspace_id = :admin, home_workspace_id = :home, hidden_by_admin = false WHERE id = :bot"
        ), {"admin": admin_id, "home": home, "bot": bot_id})


def downgrade() -> None:
    bind = op.get_bind()
    bots = bind.execute(sa.text("SELECT id, home_workspace_id FROM tg_bots WHERE home_workspace_id IS NOT NULL")).fetchall()
    for bot_id, home in bots:
        for table in BOT_TABLES:
            bind.execute(sa.text(f"UPDATE {table} SET workspace_id = :home WHERE bot_id = :bot"), {"home": home, "bot": bot_id})
        bind.execute(sa.text("UPDATE tg_bots SET workspace_id = :home, hidden_by_admin = true WHERE id = :bot"), {"home": home, "bot": bot_id})
    with op.batch_alter_table("tg_bots") as batch:
        batch.drop_constraint("fk_tg_bots_home_workspace", type_="foreignkey")
        batch.drop_column("home_workspace_id")
    with op.batch_alter_table("tg_leads") as batch:
        batch.drop_column("seller_hidden")
    with op.batch_alter_table("tg_orders") as batch:
        batch.drop_column("seller_hidden")
    with op.batch_alter_table("tg_flow_shares") as batch:
        batch.drop_column("owner_takes_all")
