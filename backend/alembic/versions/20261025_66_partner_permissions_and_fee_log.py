"""partner_permissions_and_fee_log

Revision ID: 66
Revises: 65
Create Date: 2026-10-25 15:32:57.267000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '66'
down_revision: Union[str, None] = '65'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create partner_permissions table
    op.create_table(
        'partner_permissions',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('platform', sa.String(length=16), nullable=False),
        sa.Column('can_view_dashboard', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('can_view_ranking', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('can_view_accounts', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('can_view_meta_apps', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('can_view_settings', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('can_view_contact', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('can_view_bot_dashboard', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('can_view_leads', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('can_view_wallets', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('extra_permissions', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("platform IN ('flashpost', 'flashbot')", name='ck_partner_permissions_platform'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_partner_permissions_user', 'partner_permissions', ['user_id'], unique=False)
    op.create_index('uq_partner_permissions_user_platform', 'partner_permissions', ['user_id', 'platform'], unique=True)

    # Create fee_change_logs table
    op.create_table(
        'fee_change_logs',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('changed_by_user_id', sa.Uuid(), nullable=True),
        sa.Column('old_fee', sa.Float(), nullable=True),
        sa.Column('new_fee', sa.Float(), nullable=True),
        sa.Column('is_global_change', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('reason', sa.String(length=500), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['changed_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_fee_change_logs_changed_by', 'fee_change_logs', ['changed_by_user_id'], unique=False)
    op.create_index('ix_fee_change_logs_created', 'fee_change_logs', ['created_at'], unique=False)
    op.create_index('ix_fee_change_logs_user', 'fee_change_logs', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_fee_change_logs_user', table_name='fee_change_logs')
    op.drop_index('ix_fee_change_logs_created', table_name='fee_change_logs')
    op.drop_index('ix_fee_change_logs_changed_by', table_name='fee_change_logs')
    op.drop_table('fee_change_logs')
    op.drop_index('uq_partner_permissions_user_platform', table_name='partner_permissions')
    op.drop_index('ix_partner_permissions_user', table_name='partner_permissions')
    op.drop_table('partner_permissions')
