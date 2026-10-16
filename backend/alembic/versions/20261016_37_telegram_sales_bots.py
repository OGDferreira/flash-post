"""Telegram sales bots: flows, bots, groups, media, leads, orders, subscriptions, jobs.

Additive only: new tables.

Revision ID: 20261016_37
Revises: 20261015_36
Create Date: 2026-10-16 15:42:57.666685
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '20261016_37'
down_revision: Union[str, None] = '20261015_36'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('tg_flows',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('workspace_id', sa.Uuid(), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('definition', sa.JSON(), nullable=False),
    sa.Column('version', sa.Integer(), server_default='1', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_tg_flows_workspace', 'tg_flows', ['workspace_id'], unique=False)
    op.create_table('tg_media',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('workspace_id', sa.Uuid(), nullable=False),
    sa.Column('kind', sa.String(length=16), nullable=False),
    sa.Column('file_name', sa.String(length=255), nullable=False),
    sa.Column('content_type', sa.String(length=100), nullable=False),
    sa.Column('size_bytes', sa.Integer(), nullable=False),
    sa.Column('storage_path', sa.String(length=500), nullable=False),
    sa.Column('file_ids', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_tg_media_workspace', 'tg_media', ['workspace_id'], unique=False)
    op.create_table('tg_bots',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('workspace_id', sa.Uuid(), nullable=False),
    sa.Column('flow_id', sa.Uuid(), nullable=True),
    sa.Column('tg_bot_id', sa.BigInteger(), nullable=False),
    sa.Column('username', sa.String(length=64), nullable=False),
    sa.Column('name', sa.String(length=128), nullable=False),
    sa.Column('encrypted_token', sa.String(length=4096), nullable=False),
    sa.Column('webhook_secret', sa.String(length=64), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default=sa.text('(true)'), nullable=False),
    sa.Column('status', sa.String(length=16), server_default='online', nullable=False),
    sa.Column('last_error', sa.String(length=500), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['flow_id'], ['tg_flows.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tg_bot_id', name='uq_tg_bots_tg_bot_id')
    )
    op.create_index('ix_tg_bots_workspace', 'tg_bots', ['workspace_id'], unique=False)
    op.create_table('tg_groups',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('workspace_id', sa.Uuid(), nullable=False),
    sa.Column('bot_id', sa.Uuid(), nullable=False),
    sa.Column('chat_id', sa.BigInteger(), nullable=False),
    sa.Column('title', sa.String(length=255), nullable=False),
    sa.Column('chat_type', sa.String(length=16), nullable=False),
    sa.Column('can_invite', sa.Boolean(), server_default=sa.text('(false)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['bot_id'], ['tg_bots.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('bot_id', 'chat_id', name='uq_tg_groups_bot_chat')
    )
    op.create_index('ix_tg_groups_workspace', 'tg_groups', ['workspace_id'], unique=False)
    op.create_table('tg_leads',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('workspace_id', sa.Uuid(), nullable=False),
    sa.Column('bot_id', sa.Uuid(), nullable=False),
    sa.Column('flow_id', sa.Uuid(), nullable=True),
    sa.Column('tg_user_id', sa.BigInteger(), nullable=False),
    sa.Column('chat_id', sa.BigInteger(), nullable=False),
    sa.Column('first_name', sa.String(length=255), nullable=True),
    sa.Column('username', sa.String(length=64), nullable=True),
    sa.Column('source', sa.String(length=64), nullable=True),
    sa.Column('age_confirmed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('blocked_bot', sa.Boolean(), server_default=sa.text('(false)'), nullable=False),
    sa.Column('stage', sa.String(length=32), server_default='new', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('last_seen_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['bot_id'], ['tg_bots.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['flow_id'], ['tg_flows.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('bot_id', 'tg_user_id', name='uq_tg_leads_bot_user')
    )
    op.create_index('ix_tg_leads_workspace_created', 'tg_leads', ['workspace_id', 'created_at'], unique=False)
    op.create_table('tg_updates_seen',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('bot_id', sa.Uuid(), nullable=False),
    sa.Column('update_id', sa.BigInteger(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['bot_id'], ['tg_bots.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('bot_id', 'update_id', name='uq_tg_updates_seen')
    )
    op.create_table('tg_jobs',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('workspace_id', sa.Uuid(), nullable=False),
    sa.Column('bot_id', sa.Uuid(), nullable=False),
    sa.Column('lead_id', sa.Uuid(), nullable=True),
    sa.Column('kind', sa.String(length=32), nullable=False),
    sa.Column('payload', sa.JSON(), nullable=False),
    sa.Column('run_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('status', sa.String(length=16), server_default='pending', nullable=False),
    sa.Column('attempts', sa.Integer(), server_default='0', nullable=False),
    sa.Column('last_error', sa.String(length=500), nullable=True),
    sa.Column('idempotency_key', sa.String(length=200), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['bot_id'], ['tg_bots.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['lead_id'], ['tg_leads.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('idempotency_key', name='uq_tg_jobs_idempotency')
    )
    op.create_index('ix_tg_jobs_due', 'tg_jobs', ['status', 'run_at'], unique=False)
    op.create_table('tg_orders',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('workspace_id', sa.Uuid(), nullable=False),
    sa.Column('bot_id', sa.Uuid(), nullable=False),
    sa.Column('lead_id', sa.Uuid(), nullable=False),
    sa.Column('flow_id', sa.Uuid(), nullable=True),
    sa.Column('kind', sa.String(length=16), server_default='plan', nullable=False),
    sa.Column('offer_id', sa.String(length=64), nullable=False),
    sa.Column('offer_name', sa.String(length=120), nullable=False),
    sa.Column('offer_snapshot', sa.JSON(), nullable=False),
    sa.Column('amount', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('gateway', sa.String(length=32), server_default='smokepay', nullable=False),
    sa.Column('gateway_transaction_id', sa.String(length=64), nullable=True),
    sa.Column('gateway_fee', sa.Numeric(precision=12, scale=2), nullable=True),
    sa.Column('net_amount', sa.Numeric(precision=12, scale=2), nullable=True),
    sa.Column('pix_copy_paste', sa.Text(), nullable=True),
    sa.Column('status', sa.String(length=16), server_default='pending', nullable=False),
    sa.Column('payer_name', sa.String(length=255), nullable=True),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('paid_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['bot_id'], ['tg_bots.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['flow_id'], ['tg_flows.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['lead_id'], ['tg_leads.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('gateway', 'gateway_transaction_id', name='uq_tg_orders_gateway_tx')
    )
    op.create_index('ix_tg_orders_status_expires', 'tg_orders', ['status', 'expires_at'], unique=False)
    op.create_index('ix_tg_orders_workspace_created', 'tg_orders', ['workspace_id', 'created_at'], unique=False)
    op.create_table('tg_subscriptions',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('workspace_id', sa.Uuid(), nullable=False),
    sa.Column('bot_id', sa.Uuid(), nullable=False),
    sa.Column('lead_id', sa.Uuid(), nullable=False),
    sa.Column('order_id', sa.Uuid(), nullable=False),
    sa.Column('chat_id', sa.BigInteger(), nullable=False),
    sa.Column('starts_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('ends_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('status', sa.String(length=16), server_default='active', nullable=False),
    sa.Column('invite_link', sa.String(length=255), nullable=True),
    sa.ForeignKeyConstraint(['bot_id'], ['tg_bots.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['lead_id'], ['tg_leads.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['order_id'], ['tg_orders.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_tg_subscriptions_status_ends', 'tg_subscriptions', ['status', 'ends_at'], unique=False)
    op.create_index('ix_tg_subscriptions_workspace', 'tg_subscriptions', ['workspace_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_tg_subscriptions_workspace', table_name='tg_subscriptions')
    op.drop_index('ix_tg_subscriptions_status_ends', table_name='tg_subscriptions')
    op.drop_table('tg_subscriptions')
    op.drop_index('ix_tg_orders_workspace_created', table_name='tg_orders')
    op.drop_index('ix_tg_orders_status_expires', table_name='tg_orders')
    op.drop_table('tg_orders')
    op.drop_index('ix_tg_jobs_due', table_name='tg_jobs')
    op.drop_table('tg_jobs')
    op.drop_table('tg_updates_seen')
    op.drop_index('ix_tg_leads_workspace_created', table_name='tg_leads')
    op.drop_table('tg_leads')
    op.drop_index('ix_tg_groups_workspace', table_name='tg_groups')
    op.drop_table('tg_groups')
    op.drop_index('ix_tg_bots_workspace', table_name='tg_bots')
    op.drop_table('tg_bots')
    op.drop_index('ix_tg_media_workspace', table_name='tg_media')
    op.drop_table('tg_media')
    op.drop_index('ix_tg_flows_workspace', table_name='tg_flows')
    op.drop_table('tg_flows')
