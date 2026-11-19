"""Mamify: update of a single person's branch ("Aggiorna rete"); indexes
for the paged collaborator list.

Revision ID: 0010
Revises: 0009
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '0010'
down_revision: Union[str, None] = '0009'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('sn_mamify_members', sa.Column('branch_sync_requested_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('sn_mamify_members', sa.Column('branch_synced_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('sn_mamify_members', sa.Column('branch_sync_result', postgresql.JSONB(astext_type=sa.Text()),
                                                 nullable=False, server_default='{}'))
    op.create_index('ix_sn_mamify_members_org_agent', 'sn_mamify_members', ['organization_id', 'agent_id'])
    op.create_index('ix_sn_promoter_profiles_org_joined', 'sn_promoter_profiles', ['organization_id', 'joined_at'])


def downgrade() -> None:
    op.drop_index('ix_sn_promoter_profiles_org_joined', table_name='sn_promoter_profiles')
    op.drop_index('ix_sn_mamify_members_org_agent', table_name='sn_mamify_members')
    op.drop_column('sn_mamify_members', 'branch_sync_result')
    op.drop_column('sn_mamify_members', 'branch_synced_at')
    op.drop_column('sn_mamify_members', 'branch_sync_requested_at')
