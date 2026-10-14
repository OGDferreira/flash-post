"""SharkBot leads and transactions (one row per lead / per payment).

Backfills from shark_events rows that came from SharkBot (operation_id IS
NULL; Smokepay rows are finance data and stay where they are).

Revision ID: 20261014_30
Revises: 20261014_29
Create Date: 2026-10-14
"""

from collections import defaultdict
from typing import Sequence, Union
import uuid

import sqlalchemy as sa
from alembic import op

revision: str = "20261014_30"
down_revision: Union[str, None] = "20261014_29"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "shark_leads",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("lead_key", sa.String(240), nullable=False),
        sa.Column("bot_id", sa.String(120)),
        sa.Column("bot_name", sa.String(160)),
        sa.Column("flow_id", sa.String(120)),
        sa.Column("flow_name", sa.String(160)),
        sa.Column("customer_id", sa.String(120)),
        sa.Column("telegram_id", sa.String(64)),
        sa.Column("customer_name", sa.String(240)),
        sa.Column("customer_username", sa.String(120)),
        sa.Column("account_id", sa.Uuid(), sa.ForeignKey("instagram_accounts.id", ondelete="SET NULL")),
        sa.Column("utm_source", sa.String(120)),
        sa.Column("utm_campaign", sa.String(160)),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("first_received_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_received_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("workspace_id", "lead_key", name="uq_shark_leads_workspace_key"),
    )
    op.create_index("ix_shark_leads_workspace_joined", "shark_leads", ["workspace_id", "joined_at"])
    op.create_index("ix_shark_leads_workspace_bot", "shark_leads", ["workspace_id", "bot_id", "flow_id"])
    op.create_table(
        "shark_transactions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("transaction_key", sa.String(240), nullable=False),
        sa.Column("transaction_id", sa.String(160)),
        sa.Column("external_id", sa.String(160)),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2)),
        sa.Column("currency", sa.String(8)),
        sa.Column("gateway", sa.String(60)),
        sa.Column("payment_method", sa.String(40)),
        sa.Column("plan_name", sa.String(160)),
        sa.Column("sales_code", sa.String(120)),
        sa.Column("bot_id", sa.String(120)),
        sa.Column("bot_name", sa.String(160)),
        sa.Column("flow_id", sa.String(120)),
        sa.Column("flow_name", sa.String(160)),
        sa.Column("customer_id", sa.String(120)),
        sa.Column("customer_name", sa.String(240)),
        sa.Column("customer_username", sa.String(120)),
        sa.Column("lead_key", sa.String(240)),
        sa.Column("account_id", sa.Uuid(), sa.ForeignKey("instagram_accounts.id", ondelete="SET NULL")),
        sa.Column("utm_source", sa.String(120)),
        sa.Column("utm_campaign", sa.String(160)),
        sa.Column("created_at_source", sa.DateTime(timezone=True), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True)),
        sa.Column("first_received_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("workspace_id", "transaction_key", name="uq_shark_transactions_workspace_key"),
        sa.CheckConstraint("status IN ('pending', 'paid')", name="ck_shark_transactions_status"),
    )
    op.create_index(
        "ix_shark_transactions_workspace_created", "shark_transactions", ["workspace_id", "created_at_source"]
    )
    op.create_index("ix_shark_transactions_workspace_paid", "shark_transactions", ["workspace_id", "paid_at"])
    op.create_index(
        "ix_shark_transactions_workspace_bot", "shark_transactions", ["workspace_id", "bot_id", "flow_id"]
    )

    bind = op.get_bind()
    events = sa.table(
        "shark_events",
        sa.column("workspace_id", sa.Uuid()),
        sa.column("account_id", sa.Uuid()),
        sa.column("operation_id", sa.Uuid()),
        sa.column("event_type", sa.String()),
        sa.column("source_event_key", sa.String()),
        sa.column("transaction_id", sa.String()),
        sa.column("customer_name", sa.String()),
        sa.column("customer_username", sa.String()),
        sa.column("bot_name", sa.String()),
        sa.column("plan_name", sa.String()),
        sa.column("amount", sa.Numeric(12, 2)),
        sa.column("occurred_at", sa.DateTime(timezone=True)),
    )
    leads = sa.table(
        "shark_leads",
        *(sa.column(name) for name in (
            "id", "workspace_id", "lead_key", "bot_name", "customer_name", "customer_username",
            "account_id", "joined_at",
        )),
    )
    transactions = sa.table(
        "shark_transactions",
        *(sa.column(name) for name in (
            "id", "workspace_id", "transaction_key", "transaction_id", "status", "amount",
            "plan_name", "bot_name", "customer_name", "customer_username", "account_id",
            "created_at_source", "paid_at",
        )),
    )
    rows = bind.execute(
        sa.select(events).where(events.c.operation_id.is_(None)).order_by(events.c.occurred_at)
    ).all()
    lead_rows = []
    grouped: dict[tuple, list] = defaultdict(list)
    for row in rows:
        if row.event_type == "lead_initiated":
            lead_rows.append(
                {
                    "id": uuid.uuid4(),
                    "workspace_id": row.workspace_id,
                    "lead_key": f"legacy:{row.source_event_key}"[:240],
                    "bot_name": row.bot_name,
                    "customer_name": row.customer_name,
                    "customer_username": row.customer_username,
                    "account_id": row.account_id,
                    "joined_at": row.occurred_at,
                }
            )
        elif row.event_type in {"pix_generated", "pix_pending", "pix_paid"}:
            key = row.transaction_id or f"legacy:{row.source_event_key}"
            grouped[(row.workspace_id, key)].append(row)
    transaction_rows = []
    for (workspace_id, key), items in grouped.items():
        paid = [item for item in items if item.event_type == "pix_paid"]
        created = [item for item in items if item.event_type != "pix_paid"] or items
        reference = paid[0] if paid else created[0]
        amount = reference.amount
        if amount is not None and amount == 0:
            amount = None  # the old code stored a missing amount as 0
        transaction_rows.append(
            {
                "id": uuid.uuid4(),
                "workspace_id": workspace_id,
                "transaction_key": (key if key.startswith("legacy:") else f"tx:{key}")[:240],
                "transaction_id": None if key.startswith("legacy:") else key[:160],
                "status": "paid" if paid else "pending",
                "amount": amount,
                "plan_name": reference.plan_name,
                "bot_name": reference.bot_name,
                "customer_name": reference.customer_name,
                "customer_username": reference.customer_username,
                "account_id": reference.account_id,
                "created_at_source": min(item.occurred_at for item in created),
                "paid_at": min(item.occurred_at for item in paid) if paid else None,
            }
        )
    for start in range(0, len(lead_rows), 500):
        bind.execute(leads.insert(), lead_rows[start : start + 500])
    for start in range(0, len(transaction_rows), 500):
        bind.execute(transactions.insert(), transaction_rows[start : start + 500])


def downgrade() -> None:
    op.drop_index("ix_shark_transactions_workspace_bot", table_name="shark_transactions")
    op.drop_index("ix_shark_transactions_workspace_paid", table_name="shark_transactions")
    op.drop_index("ix_shark_transactions_workspace_created", table_name="shark_transactions")
    op.drop_table("shark_transactions")
    op.drop_index("ix_shark_leads_workspace_bot", table_name="shark_leads")
    op.drop_index("ix_shark_leads_workspace_joined", table_name="shark_leads")
    op.drop_table("shark_leads")
