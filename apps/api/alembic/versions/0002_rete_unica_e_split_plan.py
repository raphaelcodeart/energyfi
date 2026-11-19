"""Single sponsorship network and Split Plan margin distribution.

Replaces the legacy token-per-rank model with configurable, time-versioned
commercial roles, product margins, versioned Split Plans (on
`sn_payout_plans` / `sn_payout_rules`), and payout entries that freeze plan,
rule, level, role and margin.

No data is deleted. Legacy plan rows are marked LEGACY and ignored by the
engine; existing entries are kept as is (ACCRUED counts as PENDING); every
existing collaborator gets the default role from their join date.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-22

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '0002'
down_revision: Union[str, None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('sn_commercial_roles',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('code', sa.String(length=32), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('description', sa.String(length=1000), nullable=False),
    sa.Column('commission_mode', sa.String(length=16), nullable=False),
    sa.Column('network_depth', sa.Integer(), nullable=True),
    sa.Column('allows_delegation', sa.Boolean(), nullable=False),
    sa.Column('allows_downline', sa.Boolean(), nullable=False),
    sa.Column('can_close_sales', sa.Boolean(), nullable=False),
    sa.Column('is_default', sa.Boolean(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('sort_order', sa.Integer(), nullable=False),
    sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['organization_id'], ['sn_tenants.id'], name=op.f('fk_sn_commercial_roles_organization_id_sn_tenants')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sn_commercial_roles')),
    sa.UniqueConstraint('organization_id', 'code', name='uq_sn_commercial_roles_org_code')
    )
    op.create_index(op.f('ix_sn_commercial_roles_organization_id'), 'sn_commercial_roles', ['organization_id'], unique=False)
    op.create_table('sn_product_categories',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('code', sa.String(length=32), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('requires_supply_point', sa.Boolean(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['organization_id'], ['sn_tenants.id'], name=op.f('fk_sn_product_categories_organization_id_sn_tenants')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sn_product_categories')),
    sa.UniqueConstraint('organization_id', 'code', name='uq_sn_product_categories_org_code')
    )
    op.create_index(op.f('ix_sn_product_categories_organization_id'), 'sn_product_categories', ['organization_id'], unique=False)
    op.create_table('sn_delegations',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('influencer_agent_id', sa.UUID(), nullable=False),
    sa.Column('delegate_agent_id', sa.UUID(), nullable=False),
    sa.Column('valid_from', sa.DateTime(timezone=True), nullable=False),
    sa.Column('valid_to', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_by_user_id', sa.UUID(), nullable=True),
    sa.Column('reason', sa.String(length=500), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['sn_accounts.id'], name=op.f('fk_sn_delegations_created_by_user_id_sn_accounts')),
    sa.ForeignKeyConstraint(['delegate_agent_id'], ['sn_promoter_profiles.id'], name=op.f('fk_sn_delegations_delegate_agent_id_sn_promoter_profiles')),
    sa.ForeignKeyConstraint(['influencer_agent_id'], ['sn_promoter_profiles.id'], name=op.f('fk_sn_delegations_influencer_agent_id_sn_promoter_profiles')),
    sa.ForeignKeyConstraint(['organization_id'], ['sn_tenants.id'], name=op.f('fk_sn_delegations_organization_id_sn_tenants')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sn_delegations'))
    )
    op.create_index(op.f('ix_sn_delegations_delegate_agent_id'), 'sn_delegations', ['delegate_agent_id'], unique=False)
    op.create_index(op.f('ix_sn_delegations_influencer_agent_id'), 'sn_delegations', ['influencer_agent_id'], unique=False)
    op.create_index(op.f('ix_sn_delegations_organization_id'), 'sn_delegations', ['organization_id'], unique=False)
    op.create_index('uq_sn_delegations_open_delegate', 'sn_delegations', ['delegate_agent_id'], unique=True, postgresql_where=sa.text('valid_to IS NULL'))
    op.create_table('sn_leads',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('promoter_agent_id', sa.UUID(), nullable=False),
    sa.Column('customer_id', sa.UUID(), nullable=True),
    sa.Column('product_id', sa.UUID(), nullable=True),
    sa.Column('contact_name', sa.String(length=200), nullable=False),
    sa.Column('contact_email', sa.String(length=255), nullable=True),
    sa.Column('contact_phone', sa.String(length=40), nullable=True),
    sa.Column('notes', sa.String(length=2000), server_default='', nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('assigned_agent_id', sa.UUID(), nullable=True),
    sa.Column('converted_contract_id', sa.UUID(), nullable=True),
    sa.Column('converted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('closed_reason', sa.String(length=500), nullable=True),
    sa.Column('created_by_user_id', sa.UUID(), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['assigned_agent_id'], ['sn_promoter_profiles.id'], name=op.f('fk_sn_leads_assigned_agent_id_sn_promoter_profiles')),
    sa.ForeignKeyConstraint(['converted_contract_id'], ['sn_agreements.id'], name=op.f('fk_sn_leads_converted_contract_id_sn_agreements'), use_alter=True),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['sn_accounts.id'], name=op.f('fk_sn_leads_created_by_user_id_sn_accounts')),
    sa.ForeignKeyConstraint(['customer_id'], ['sn_clients.id'], name=op.f('fk_sn_leads_customer_id_sn_clients')),
    sa.ForeignKeyConstraint(['organization_id'], ['sn_tenants.id'], name=op.f('fk_sn_leads_organization_id_sn_tenants')),
    sa.ForeignKeyConstraint(['product_id'], ['sn_offers.id'], name=op.f('fk_sn_leads_product_id_sn_offers')),
    sa.ForeignKeyConstraint(['promoter_agent_id'], ['sn_promoter_profiles.id'], name=op.f('fk_sn_leads_promoter_agent_id_sn_promoter_profiles')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sn_leads'))
    )
    op.create_index(op.f('ix_sn_leads_customer_id'), 'sn_leads', ['customer_id'], unique=False)
    op.create_index(op.f('ix_sn_leads_organization_id'), 'sn_leads', ['organization_id'], unique=False)
    op.create_index(op.f('ix_sn_leads_promoter_agent_id'), 'sn_leads', ['promoter_agent_id'], unique=False)
    op.create_index(op.f('ix_sn_leads_status'), 'sn_leads', ['status'], unique=False)
    op.create_table('sn_seller_role_history',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('agent_id', sa.UUID(), nullable=False),
    sa.Column('role_id', sa.UUID(), nullable=False),
    sa.Column('valid_from', sa.DateTime(timezone=True), nullable=False),
    sa.Column('valid_to', sa.DateTime(timezone=True), nullable=True),
    sa.Column('reason', sa.String(length=500), nullable=True),
    sa.Column('changed_by_user_id', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['agent_id'], ['sn_promoter_profiles.id'], name=op.f('fk_sn_seller_role_history_agent_id_sn_promoter_profiles')),
    sa.ForeignKeyConstraint(['changed_by_user_id'], ['sn_accounts.id'], name=op.f('fk_sn_seller_role_history_changed_by_user_id_sn_accounts')),
    sa.ForeignKeyConstraint(['organization_id'], ['sn_tenants.id'], name=op.f('fk_sn_seller_role_history_organization_id_sn_tenants')),
    sa.ForeignKeyConstraint(['role_id'], ['sn_commercial_roles.id'], name=op.f('fk_sn_seller_role_history_role_id_sn_commercial_roles')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sn_seller_role_history'))
    )
    op.create_index(op.f('ix_sn_seller_role_history_agent_id'), 'sn_seller_role_history', ['agent_id'], unique=False)
    op.create_index(op.f('ix_sn_seller_role_history_organization_id'), 'sn_seller_role_history', ['organization_id'], unique=False)
    op.create_index('uq_sn_seller_role_history_open', 'sn_seller_role_history', ['agent_id'], unique=True, postgresql_where=sa.text('valid_to IS NULL'))
    op.add_column('sn_agreements', sa.Column('sold_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('sn_agreements', sa.Column('sale_amount_cents', sa.BigInteger(), nullable=True))
    op.add_column('sn_agreements', sa.Column('reference_margin_cents', sa.BigInteger(), nullable=True))
    op.add_column('sn_agreements', sa.Column('split_plan_id', sa.UUID(), nullable=True))
    op.add_column('sn_agreements', sa.Column('seller_role_code', sa.String(length=32), nullable=True))
    op.add_column('sn_agreements', sa.Column('lead_id', sa.UUID(), nullable=True))
    op.alter_column('sn_agreements', 'supply_point_id',
               existing_type=sa.UUID(),
               nullable=True)
    op.create_index(op.f('ix_sn_agreements_lead_id'), 'sn_agreements', ['lead_id'], unique=False)
    op.create_index(op.f('ix_sn_agreements_split_plan_id'), 'sn_agreements', ['split_plan_id'], unique=False)
    op.create_foreign_key(op.f('fk_sn_agreements_split_plan_id_sn_payout_plans'), 'sn_agreements', 'sn_payout_plans', ['split_plan_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_agreements_lead_id_sn_leads'), 'sn_agreements', 'sn_leads', ['lead_id'], ['id'])
    op.add_column('sn_offer_versions', sa.Column('margin_type', sa.String(length=16), nullable=True))
    op.add_column('sn_offer_versions', sa.Column('margin_amount_cents', sa.BigInteger(), nullable=True))
    op.add_column('sn_offer_versions', sa.Column('margin_percentage', sa.Numeric(precision=7, scale=4), nullable=True))
    op.add_column('sn_offers', sa.Column('commercial_category_id', sa.UUID(), nullable=True))
    op.create_index(op.f('ix_sn_offers_commercial_category_id'), 'sn_offers', ['commercial_category_id'], unique=False)
    op.create_foreign_key(op.f('fk_sn_offers_commercial_category_id_sn_product_categories'), 'sn_offers', 'sn_product_categories', ['commercial_category_id'], ['id'])
    op.add_column('sn_payout_entries', sa.Column('beneficiary_kind', sa.String(length=8), server_default='AGENT', nullable=False))
    op.add_column('sn_payout_entries', sa.Column('split_plan_id', sa.UUID(), nullable=True))
    op.add_column('sn_payout_entries', sa.Column('plan_version', sa.Integer(), nullable=True))
    op.add_column('sn_payout_entries', sa.Column('rule_id', sa.UUID(), nullable=True))
    op.add_column('sn_payout_entries', sa.Column('beneficiary_type', sa.String(length=24), nullable=True))
    op.add_column('sn_payout_entries', sa.Column('network_level', sa.Integer(), nullable=True))
    op.add_column('sn_payout_entries', sa.Column('role_code_snapshot', sa.String(length=32), nullable=True))
    op.add_column('sn_payout_entries', sa.Column('calculation_type', sa.String(length=24), nullable=True))
    op.add_column('sn_payout_entries', sa.Column('calculation_value', sa.Numeric(precision=12, scale=4), nullable=True))
    op.add_column('sn_payout_entries', sa.Column('reference_margin_cents', sa.BigInteger(), nullable=True))
    op.add_column('sn_payout_entries', sa.Column('source_seller_agent_id', sa.UUID(), nullable=True))
    op.add_column('sn_payout_entries', sa.Column('product_id', sa.UUID(), nullable=True))
    op.add_column('sn_payout_entries', sa.Column('fallback_applied', sa.String(length=16), nullable=True))
    op.add_column('sn_payout_entries', sa.Column('snapshot', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False))
    op.add_column('sn_payout_entries', sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('sn_payout_entries', sa.Column('approved_by_user_id', sa.UUID(), nullable=True))
    op.alter_column('sn_payout_entries', 'agent_id',
               existing_type=sa.UUID(),
               nullable=True)
    op.create_index(op.f('ix_sn_payout_entries_product_id'), 'sn_payout_entries', ['product_id'], unique=False)
    op.create_index(op.f('ix_sn_payout_entries_source_seller_agent_id'), 'sn_payout_entries', ['source_seller_agent_id'], unique=False)
    op.create_index(op.f('ix_sn_payout_entries_split_plan_id'), 'sn_payout_entries', ['split_plan_id'], unique=False)
    op.create_foreign_key(op.f('fk_sn_payout_entries_product_id_sn_offers'), 'sn_payout_entries', 'sn_offers', ['product_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_payout_entries_rule_id_sn_payout_rules'), 'sn_payout_entries', 'sn_payout_rules', ['rule_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_payout_entries_source_seller_agent_id_sn_promoter_profiles'), 'sn_payout_entries', 'sn_promoter_profiles', ['source_seller_agent_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_payout_entries_split_plan_id_sn_payout_plans'), 'sn_payout_entries', 'sn_payout_plans', ['split_plan_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_payout_entries_approved_by_user_id_sn_accounts'), 'sn_payout_entries', 'sn_accounts', ['approved_by_user_id'], ['id'])
    op.add_column('sn_payout_plans', sa.Column('name', sa.String(length=160), nullable=True))
    op.add_column('sn_payout_plans', sa.Column('plan_key', sa.UUID(), nullable=True))
    op.add_column('sn_payout_plans', sa.Column('version', sa.Integer(), server_default='1', nullable=False))
    op.add_column('sn_payout_plans', sa.Column('product_id', sa.UUID(), nullable=True))
    op.add_column('sn_payout_plans', sa.Column('category_id', sa.UUID(), nullable=True))
    op.add_column('sn_payout_plans', sa.Column('seller_role_id', sa.UUID(), nullable=True))
    op.add_column('sn_payout_plans', sa.Column('fallback_strategy', sa.String(length=16), server_default='COMPANY', nullable=False))
    op.add_column('sn_payout_plans', sa.Column('distribution_mode', sa.String(length=8), server_default='FULL', nullable=False))
    op.add_column('sn_payout_plans', sa.Column('accrual_trigger', sa.String(length=16), server_default='PER_INSTALMENT', nullable=False))
    op.add_column('sn_payout_plans', sa.Column('notes', sa.String(length=2000), server_default='', nullable=False))
    op.add_column('sn_payout_plans', sa.Column('created_by_user_id', sa.UUID(), nullable=True))
    op.add_column('sn_payout_plans', sa.Column('activated_by_user_id', sa.UUID(), nullable=True))
    op.add_column('sn_payout_plans', sa.Column('activated_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('sn_payout_plans', sa.Column('retired_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('sn_payout_plans', sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True))
    op.create_index(op.f('ix_sn_payout_plans_category_id'), 'sn_payout_plans', ['category_id'], unique=False)
    op.create_index(op.f('ix_sn_payout_plans_plan_key'), 'sn_payout_plans', ['plan_key'], unique=False)
    op.create_index(op.f('ix_sn_payout_plans_product_id'), 'sn_payout_plans', ['product_id'], unique=False)
    op.create_index(op.f('ix_sn_payout_plans_seller_role_id'), 'sn_payout_plans', ['seller_role_id'], unique=False)
    op.create_foreign_key(op.f('fk_sn_payout_plans_category_id_sn_product_categories'), 'sn_payout_plans', 'sn_product_categories', ['category_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_payout_plans_activated_by_user_id_sn_accounts'), 'sn_payout_plans', 'sn_accounts', ['activated_by_user_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_payout_plans_product_id_sn_offers'), 'sn_payout_plans', 'sn_offers', ['product_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_payout_plans_created_by_user_id_sn_accounts'), 'sn_payout_plans', 'sn_accounts', ['created_by_user_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_payout_plans_seller_role_id_sn_commercial_roles'), 'sn_payout_plans', 'sn_commercial_roles', ['seller_role_id'], ['id'])
    op.alter_column('sn_payout_reversals', 'requested_by',
               existing_type=sa.UUID(),
               nullable=True)
    op.add_column('sn_payout_rules', sa.Column('sequence', sa.Integer(), server_default='0', nullable=False))
    op.add_column('sn_payout_rules', sa.Column('label', sa.String(length=120), nullable=True))
    op.add_column('sn_payout_rules', sa.Column('beneficiary_type', sa.String(length=24), nullable=True))
    op.add_column('sn_payout_rules', sa.Column('network_level', sa.Integer(), nullable=True))
    op.add_column('sn_payout_rules', sa.Column('required_role_id', sa.UUID(), nullable=True))
    op.add_column('sn_payout_rules', sa.Column('calculation_type', sa.String(length=24), nullable=True))
    op.add_column('sn_payout_rules', sa.Column('percentage', sa.Numeric(precision=7, scale=4), nullable=True))
    op.add_column('sn_payout_rules', sa.Column('amount_cents', sa.BigInteger(), nullable=True))
    op.add_column('sn_payout_rules', sa.Column('min_amount_cents', sa.BigInteger(), nullable=True))
    op.add_column('sn_payout_rules', sa.Column('max_amount_cents', sa.BigInteger(), nullable=True))
    op.add_column('sn_payout_rules', sa.Column('fallback_strategy', sa.String(length=16), nullable=True))
    op.alter_column('sn_payout_rules', 'valid_from',
               existing_type=postgresql.TIMESTAMP(timezone=True),
               nullable=True)
    op.create_foreign_key(op.f('fk_sn_payout_rules_required_role_id_sn_commercial_roles'), 'sn_payout_rules', 'sn_commercial_roles', ['required_role_id'], ['id'])
    op.add_column('sn_payout_run_steps', sa.Column('rule_id', sa.UUID(), nullable=True))
    op.alter_column('sn_payout_run_steps', 'beneficiary_agent_id',
               existing_type=sa.UUID(),
               nullable=True)
    op.create_foreign_key(op.f('fk_sn_payout_run_steps_rule_id_sn_payout_rules'), 'sn_payout_run_steps', 'sn_payout_rules', ['rule_id'], ['id'])
    op.add_column('sn_payout_runs', sa.Column('reference_margin_cents', sa.BigInteger(), nullable=True))
    op.add_column('sn_promoter_profiles', sa.Column('current_commercial_role_id', sa.UUID(), nullable=True))
    op.create_foreign_key(op.f('fk_sn_promoter_profiles_current_commercial_role_id_sn_commercial_roles'), 'sn_promoter_profiles', 'sn_commercial_roles', ['current_commercial_role_id'], ['id'])
    op.add_column('sn_tree_snapshot_nodes', sa.Column('commercial_role_id', sa.UUID(), nullable=True))
    op.add_column('sn_tree_snapshot_nodes', sa.Column('role_code', sa.String(length=32), nullable=True))
    op.add_column('sn_tree_snapshot_nodes', sa.Column('agent_status', sa.String(length=32), nullable=True))
    op.create_foreign_key(op.f('fk_sn_tree_snapshot_nodes_commercial_role_id_sn_commercial_roles'), 'sn_tree_snapshot_nodes', 'sn_commercial_roles', ['commercial_role_id'], ['id'])
    op.add_column('sn_tree_snapshots', sa.Column('as_of', sa.DateTime(timezone=True), nullable=True))

    # --- Constraints autogenerate cannot express --------------------------
    # Leads and contracts reference each other, so this FK comes last.
    op.create_foreign_key(
        op.f("fk_sn_leads_converted_contract_id_sn_agreements"), "sn_leads", "sn_agreements",
        ["converted_contract_id"], ["id"],
    )
    op.create_check_constraint(
        op.f("ck_sn_offer_versions_margin_consistent"), "sn_offer_versions",
        "margin_type IS NULL"
        " OR (margin_type = 'FIXED' AND margin_amount_cents IS NOT NULL AND margin_amount_cents >= 0)"
        " OR (margin_type = 'PERCENTAGE' AND margin_percentage IS NOT NULL"
        " AND margin_percentage >= 0 AND margin_percentage <= 100)",
    )
    op.create_check_constraint(
        op.f("ck_sn_payout_entries_beneficiary_consistent"), "sn_payout_entries",
        "(beneficiary_kind = 'AGENT' AND agent_id IS NOT NULL)"
        " OR (beneficiary_kind = 'COMPANY' AND agent_id IS NULL)",
    )
    # Legacy plan rows have neither product nor category: mark them LEGACY
    # before the constraint would reject them.
    op.execute("UPDATE sn_payout_plans SET status = 'LEGACY' WHERE seller_role_id IS NULL")
    op.create_check_constraint(
        op.f("ck_sn_payout_plans_one_scope"), "sn_payout_plans",
        "status = 'LEGACY' OR ((product_id IS NULL) <> (category_id IS NULL))",
    )
    op.create_check_constraint(op.f("ck_sn_payout_plans_valid_range"), "sn_payout_plans", "valid_to IS NULL OR valid_to > valid_from")
    for name, condition in (
        ("percentage_range", "percentage IS NULL OR (percentage >= 0 AND percentage <= 100)"),
        ("amount_non_negative", "amount_cents IS NULL OR amount_cents >= 0"),
        ("min_non_negative", "min_amount_cents IS NULL OR min_amount_cents >= 0"),
        ("max_non_negative", "max_amount_cents IS NULL OR max_amount_cents >= 0"),
        ("level_positive", "network_level IS NULL OR network_level >= 1"),
    ):
        op.create_check_constraint(op.f(f"ck_sn_payout_rules_{name}"), "sn_payout_rules", condition)

    # Database-enforced non-overlap: role periods of the same person, and
    # ACTIVE plans for the same product (or category) and role.
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    op.execute(
        "ALTER TABLE sn_seller_role_history ADD CONSTRAINT ex_sn_seller_role_history_no_overlap "
        "EXCLUDE USING gist (agent_id WITH =, tstzrange(valid_from, valid_to) WITH &&)"
    )
    op.execute(
        "ALTER TABLE sn_payout_plans ADD CONSTRAINT ex_sn_payout_plans_no_overlap "
        "EXCLUDE USING gist (organization_id WITH =, seller_role_id WITH =, "
        "(COALESCE(product_id, category_id)) WITH =, tstzrange(valid_from, valid_to) WITH &&) "
        "WHERE (status = 'ACTIVE')"
    )

    # --- Data -------------------------------------------------------------
    # Each organization gets the starting commercial roles and categories
    # (same structure as bootstrap, no percentages); each collaborator gets
    # the default role from their join date. Idempotent.
    roles = [
        ("NETWORKER", "Agente digitale / Networker", "PERCENTAGE", None, False, True, True, True, 10),
        ("AGENTE_PAP", "Agente porta a porta", "PERCENTAGE", 2, False, False, True, False, 20),
        ("DIRETTORE_COMMERCIALE", "Direttore commerciale", "PERCENTAGE", 2, False, True, True, False, 30),
        ("INFLUENCER", "Influencer", "MIXED", None, True, True, False, False, 40),
        ("DELEGATO_INFLUENCER", "Delegato dell'influencer", "PERCENTAGE", None, False, False, True, False, 50),
        ("PROMOTER", "Promoter (segnalatore)", "REFERRAL_FEE", 0, False, False, False, False, 60),
    ]
    for code, name, mode, depth, delegation, downline, close, default, order in roles:
        op.execute(sa.text(
            "INSERT INTO sn_commercial_roles (id, organization_id, code, name, description, commission_mode, "
            "network_depth, allows_delegation, allows_downline, can_close_sales, is_default, is_active, sort_order, "
            "metadata, created_at) "
            "SELECT gen_random_uuid(), o.id, :code, :name, '', :mode, :depth, :delegation, :downline, :close, "
            ":is_default, true, :sort_order, '{}'::jsonb, now() FROM sn_tenants o "
            "WHERE NOT EXISTS (SELECT 1 FROM sn_commercial_roles r WHERE r.organization_id = o.id AND r.code = :code)"
        ).bindparams(code=code, name=name, mode=mode, depth=depth, delegation=delegation, downline=downline,
                     close=close, is_default=default, sort_order=order))
    for code, name, supply in (("ENERGIA", "Energia", True), ("TLC", "Telecomunicazioni", False)):
        op.execute(sa.text(
            "INSERT INTO sn_product_categories (id, organization_id, code, name, requires_supply_point, is_active, created_at) "
            "SELECT gen_random_uuid(), o.id, :code, :name, :supply, true, now() FROM sn_tenants o "
            "WHERE NOT EXISTS (SELECT 1 FROM sn_product_categories c WHERE c.organization_id = o.id AND c.code = :code)"
        ).bindparams(code=code, name=name, supply=supply))
    op.execute(
        "INSERT INTO sn_seller_role_history (id, organization_id, agent_id, role_id, valid_from, reason, created_at) "
        "SELECT gen_random_uuid(), a.organization_id, a.id, r.id, a.joined_at, 'Ruolo assegnato dalla migrazione 0002', now() "
        "FROM sn_promoter_profiles a JOIN sn_commercial_roles r "
        "ON r.organization_id = a.organization_id AND r.code = 'NETWORKER' "
        "WHERE NOT EXISTS (SELECT 1 FROM sn_seller_role_history h WHERE h.agent_id = a.id)"
    )
    op.execute(
        "UPDATE sn_promoter_profiles a SET current_commercial_role_id = h.role_id "
        "FROM sn_seller_role_history h WHERE h.agent_id = a.id AND h.valid_to IS NULL"
    )
    # Existing contracts: sale date defaults to creation date.
    op.execute("UPDATE sn_agreements SET sold_at = created_at WHERE sold_at IS NULL")


def downgrade() -> None:
    op.drop_constraint(op.f("fk_sn_leads_converted_contract_id_sn_agreements"), "sn_leads", type_="foreignkey")
    op.execute("ALTER TABLE sn_payout_plans DROP CONSTRAINT IF EXISTS ex_sn_payout_plans_no_overlap")
    op.execute("ALTER TABLE sn_seller_role_history DROP CONSTRAINT IF EXISTS ex_sn_seller_role_history_no_overlap")
    for name in ("percentage_range", "amount_non_negative", "min_non_negative", "max_non_negative", "level_positive"):
        op.drop_constraint(op.f(f"ck_sn_payout_rules_{name}"), "sn_payout_rules", type_="check")
    op.drop_constraint(op.f("ck_sn_payout_plans_valid_range"), "sn_payout_plans", type_="check")
    op.drop_constraint(op.f("ck_sn_payout_plans_one_scope"), "sn_payout_plans", type_="check")
    op.drop_constraint(op.f("ck_sn_payout_entries_beneficiary_consistent"), "sn_payout_entries", type_="check")
    op.drop_constraint(op.f("ck_sn_offer_versions_margin_consistent"), "sn_offer_versions", type_="check")
    # Return LEGACY plans to ACTIVE.
    op.execute("UPDATE sn_payout_plans SET status = 'ACTIVE' WHERE status = 'LEGACY'")
    op.drop_column('sn_tree_snapshots', 'as_of')
    op.drop_constraint(op.f('fk_sn_tree_snapshot_nodes_commercial_role_id_sn_commercial_roles'), 'sn_tree_snapshot_nodes', type_='foreignkey')
    op.drop_column('sn_tree_snapshot_nodes', 'agent_status')
    op.drop_column('sn_tree_snapshot_nodes', 'role_code')
    op.drop_column('sn_tree_snapshot_nodes', 'commercial_role_id')
    op.drop_constraint(op.f('fk_sn_promoter_profiles_current_commercial_role_id_sn_commercial_roles'), 'sn_promoter_profiles', type_='foreignkey')
    op.drop_column('sn_promoter_profiles', 'current_commercial_role_id')
    op.drop_column('sn_payout_runs', 'reference_margin_cents')
    op.drop_constraint(op.f('fk_sn_payout_run_steps_rule_id_sn_payout_rules'), 'sn_payout_run_steps', type_='foreignkey')
    op.alter_column('sn_payout_run_steps', 'beneficiary_agent_id',
               existing_type=sa.UUID(),
               nullable=False)
    op.drop_column('sn_payout_run_steps', 'rule_id')
    op.drop_constraint(op.f('fk_sn_payout_rules_required_role_id_sn_commercial_roles'), 'sn_payout_rules', type_='foreignkey')
    op.alter_column('sn_payout_rules', 'valid_from',
               existing_type=postgresql.TIMESTAMP(timezone=True),
               nullable=False)
    op.drop_column('sn_payout_rules', 'fallback_strategy')
    op.drop_column('sn_payout_rules', 'max_amount_cents')
    op.drop_column('sn_payout_rules', 'min_amount_cents')
    op.drop_column('sn_payout_rules', 'amount_cents')
    op.drop_column('sn_payout_rules', 'percentage')
    op.drop_column('sn_payout_rules', 'calculation_type')
    op.drop_column('sn_payout_rules', 'required_role_id')
    op.drop_column('sn_payout_rules', 'network_level')
    op.drop_column('sn_payout_rules', 'beneficiary_type')
    op.drop_column('sn_payout_rules', 'label')
    op.drop_column('sn_payout_rules', 'sequence')
    op.alter_column('sn_payout_reversals', 'requested_by',
               existing_type=sa.UUID(),
               nullable=False)
    op.drop_constraint(op.f('fk_sn_payout_plans_seller_role_id_sn_commercial_roles'), 'sn_payout_plans', type_='foreignkey')
    op.drop_constraint(op.f('fk_sn_payout_plans_created_by_user_id_sn_accounts'), 'sn_payout_plans', type_='foreignkey')
    op.drop_constraint(op.f('fk_sn_payout_plans_product_id_sn_offers'), 'sn_payout_plans', type_='foreignkey')
    op.drop_constraint(op.f('fk_sn_payout_plans_activated_by_user_id_sn_accounts'), 'sn_payout_plans', type_='foreignkey')
    op.drop_constraint(op.f('fk_sn_payout_plans_category_id_sn_product_categories'), 'sn_payout_plans', type_='foreignkey')
    op.drop_index(op.f('ix_sn_payout_plans_seller_role_id'), table_name='sn_payout_plans')
    op.drop_index(op.f('ix_sn_payout_plans_product_id'), table_name='sn_payout_plans')
    op.drop_index(op.f('ix_sn_payout_plans_plan_key'), table_name='sn_payout_plans')
    op.drop_index(op.f('ix_sn_payout_plans_category_id'), table_name='sn_payout_plans')
    op.drop_column('sn_payout_plans', 'updated_at')
    op.drop_column('sn_payout_plans', 'retired_at')
    op.drop_column('sn_payout_plans', 'activated_at')
    op.drop_column('sn_payout_plans', 'activated_by_user_id')
    op.drop_column('sn_payout_plans', 'created_by_user_id')
    op.drop_column('sn_payout_plans', 'notes')
    op.drop_column('sn_payout_plans', 'accrual_trigger')
    op.drop_column('sn_payout_plans', 'distribution_mode')
    op.drop_column('sn_payout_plans', 'fallback_strategy')
    op.drop_column('sn_payout_plans', 'seller_role_id')
    op.drop_column('sn_payout_plans', 'category_id')
    op.drop_column('sn_payout_plans', 'product_id')
    op.drop_column('sn_payout_plans', 'version')
    op.drop_column('sn_payout_plans', 'plan_key')
    op.drop_column('sn_payout_plans', 'name')
    op.drop_constraint(op.f('fk_sn_payout_entries_approved_by_user_id_sn_accounts'), 'sn_payout_entries', type_='foreignkey')
    op.drop_constraint(op.f('fk_sn_payout_entries_split_plan_id_sn_payout_plans'), 'sn_payout_entries', type_='foreignkey')
    op.drop_constraint(op.f('fk_sn_payout_entries_source_seller_agent_id_sn_promoter_profiles'), 'sn_payout_entries', type_='foreignkey')
    op.drop_constraint(op.f('fk_sn_payout_entries_rule_id_sn_payout_rules'), 'sn_payout_entries', type_='foreignkey')
    op.drop_constraint(op.f('fk_sn_payout_entries_product_id_sn_offers'), 'sn_payout_entries', type_='foreignkey')
    op.drop_index(op.f('ix_sn_payout_entries_split_plan_id'), table_name='sn_payout_entries')
    op.drop_index(op.f('ix_sn_payout_entries_source_seller_agent_id'), table_name='sn_payout_entries')
    op.drop_index(op.f('ix_sn_payout_entries_product_id'), table_name='sn_payout_entries')
    op.alter_column('sn_payout_entries', 'agent_id',
               existing_type=sa.UUID(),
               nullable=False)
    op.drop_column('sn_payout_entries', 'approved_by_user_id')
    op.drop_column('sn_payout_entries', 'approved_at')
    op.drop_column('sn_payout_entries', 'snapshot')
    op.drop_column('sn_payout_entries', 'fallback_applied')
    op.drop_column('sn_payout_entries', 'product_id')
    op.drop_column('sn_payout_entries', 'source_seller_agent_id')
    op.drop_column('sn_payout_entries', 'reference_margin_cents')
    op.drop_column('sn_payout_entries', 'calculation_value')
    op.drop_column('sn_payout_entries', 'calculation_type')
    op.drop_column('sn_payout_entries', 'role_code_snapshot')
    op.drop_column('sn_payout_entries', 'network_level')
    op.drop_column('sn_payout_entries', 'beneficiary_type')
    op.drop_column('sn_payout_entries', 'rule_id')
    op.drop_column('sn_payout_entries', 'plan_version')
    op.drop_column('sn_payout_entries', 'split_plan_id')
    op.drop_column('sn_payout_entries', 'beneficiary_kind')
    op.drop_constraint(op.f('fk_sn_offers_commercial_category_id_sn_product_categories'), 'sn_offers', type_='foreignkey')
    op.drop_index(op.f('ix_sn_offers_commercial_category_id'), table_name='sn_offers')
    op.drop_column('sn_offers', 'commercial_category_id')
    op.drop_column('sn_offer_versions', 'margin_percentage')
    op.drop_column('sn_offer_versions', 'margin_amount_cents')
    op.drop_column('sn_offer_versions', 'margin_type')
    op.drop_constraint(op.f('fk_sn_agreements_lead_id_sn_leads'), 'sn_agreements', type_='foreignkey')
    op.drop_constraint(op.f('fk_sn_agreements_split_plan_id_sn_payout_plans'), 'sn_agreements', type_='foreignkey')
    op.drop_index(op.f('ix_sn_agreements_split_plan_id'), table_name='sn_agreements')
    op.drop_index(op.f('ix_sn_agreements_lead_id'), table_name='sn_agreements')
    op.alter_column('sn_agreements', 'supply_point_id',
               existing_type=sa.UUID(),
               nullable=False)
    op.drop_column('sn_agreements', 'lead_id')
    op.drop_column('sn_agreements', 'seller_role_code')
    op.drop_column('sn_agreements', 'split_plan_id')
    op.drop_column('sn_agreements', 'reference_margin_cents')
    op.drop_column('sn_agreements', 'sale_amount_cents')
    op.drop_column('sn_agreements', 'sold_at')
    op.drop_index('uq_sn_seller_role_history_open', table_name='sn_seller_role_history', postgresql_where=sa.text('valid_to IS NULL'))
    op.drop_index(op.f('ix_sn_seller_role_history_organization_id'), table_name='sn_seller_role_history')
    op.drop_index(op.f('ix_sn_seller_role_history_agent_id'), table_name='sn_seller_role_history')
    op.drop_table('sn_seller_role_history')
    op.drop_index(op.f('ix_sn_leads_status'), table_name='sn_leads')
    op.drop_index(op.f('ix_sn_leads_promoter_agent_id'), table_name='sn_leads')
    op.drop_index(op.f('ix_sn_leads_organization_id'), table_name='sn_leads')
    op.drop_index(op.f('ix_sn_leads_customer_id'), table_name='sn_leads')
    op.drop_table('sn_leads')
    op.drop_index('uq_sn_delegations_open_delegate', table_name='sn_delegations', postgresql_where=sa.text('valid_to IS NULL'))
    op.drop_index(op.f('ix_sn_delegations_organization_id'), table_name='sn_delegations')
    op.drop_index(op.f('ix_sn_delegations_influencer_agent_id'), table_name='sn_delegations')
    op.drop_index(op.f('ix_sn_delegations_delegate_agent_id'), table_name='sn_delegations')
    op.drop_table('sn_delegations')
    op.drop_index(op.f('ix_sn_product_categories_organization_id'), table_name='sn_product_categories')
    op.drop_table('sn_product_categories')
    op.drop_index(op.f('ix_sn_commercial_roles_organization_id'), table_name='sn_commercial_roles')
    op.drop_table('sn_commercial_roles')
