"""Mamify read only: order apps and product catalog, order poller state,
progress of a network sync; the saved payout password is wiped (SOS no
longer logs into a company account to credit wallets).

Revision ID: 0009
Revises: 0008
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '0009'
down_revision: Union[str, None] = '0008'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('sn_mamify_config', sa.Column('order_apps', postgresql.JSONB(astext_type=sa.Text()),
                                                nullable=False, server_default='["sos-affiliate", "digitalambassador"]'))
    op.add_column('sn_mamify_config', sa.Column('product_catalog', postgresql.JSONB(astext_type=sa.Text()),
                                                nullable=False, server_default='{}'))
    op.add_column('sn_mamify_config', sa.Column('orders_calls_per_minute', sa.Integer(), nullable=False,
                                                server_default='30'))
    op.add_column('sn_mamify_config', sa.Column('last_new_members_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('sn_mamify_config', sa.Column('network_sync_progress', postgresql.JSONB(astext_type=sa.Text()),
                                                nullable=False, server_default='{}'))
    op.add_column('sn_mamify_members', sa.Column('direct_count', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('sn_mamify_members', sa.Column('orders_checked_at', sa.DateTime(timezone=True), nullable=True))
    op.create_index('ix_sn_mamify_members_orders_checked', 'sn_mamify_members',
                    ['organization_id', 'orders_checked_at'], unique=False)
    op.execute("UPDATE sn_mamify_config SET payout_password = NULL, payout_mode = 'MANUAL', auto_payout = false")
    for column in ('order_apps', 'product_catalog', 'network_sync_progress'):
        op.alter_column('sn_mamify_config', column, server_default=None)


def downgrade() -> None:
    op.drop_index('ix_sn_mamify_members_orders_checked', table_name='sn_mamify_members')
    op.drop_column('sn_mamify_members', 'orders_checked_at')
    op.drop_column('sn_mamify_members', 'direct_count')
    op.drop_column('sn_mamify_config', 'network_sync_progress')
    op.drop_column('sn_mamify_config', 'last_new_members_at')
    op.drop_column('sn_mamify_config', 'orders_calls_per_minute')
    op.drop_column('sn_mamify_config', 'product_catalog')
    op.drop_column('sn_mamify_config', 'order_apps')
