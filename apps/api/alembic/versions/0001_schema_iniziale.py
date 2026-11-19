"""Initial SOSNET schema.

Creates the whole database structure. Reference data (permissions, roles,
career levels, commission plan, first administrator) is written by
`python -m app.seed.bootstrap`, not here.

Revision ID: 0001
Revises:
Create Date: 2026-09-22

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '0001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Shared order-number sequence for all shops. Must exist before the
    # tables that default to it; written by hand since autogenerate ignores
    # sequences.
    op.execute("CREATE SEQUENCE IF NOT EXISTS sn_order_number_seq START WITH 1000")
    op.create_table('sn_aliexpress_orders',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('customer_user_id', sa.UUID(), nullable=False),
    sa.Column('aliexpress_product_id', sa.UUID(), nullable=False),
    sa.Column('aliexpress_variant_id', sa.UUID(), nullable=False),
    sa.Column('created_by_user_id', sa.UUID(), nullable=False),
    sa.Column('number', sa.BigInteger(), server_default=sa.text("nextval('sn_order_number_seq')"), nullable=False),
    sa.Column('quantity', sa.Integer(), server_default=sa.text('1'), nullable=False),
    sa.Column('unit_price_cents', sa.BigInteger(), nullable=False),
    sa.Column('shipping_cents', sa.BigInteger(), server_default=sa.text("'0'::bigint"), nullable=False),
    sa.Column('supplier_shipping_cents', sa.BigInteger(), nullable=True),
    sa.Column('minimum_shipping_cents', sa.BigInteger(), nullable=True),
    sa.Column('amount_cents', sa.BigInteger(), nullable=False),
    sa.Column('credit_applied_cents', sa.BigInteger(), server_default=sa.text("'0'::bigint"), nullable=False),
    sa.Column('bank_transfer_discount_cents', sa.BigInteger(), server_default=sa.text("'0'::bigint"), nullable=False),
    sa.Column('vat_percentage', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('vat_amount_cents', sa.BigInteger(), server_default=sa.text("'0'::bigint"), nullable=False),
    sa.Column('vat_mode', sa.String(length=16), server_default='ADDED', nullable=False),
    sa.Column('credit_debit_transaction_id', sa.UUID(), nullable=True),
    sa.Column('status', sa.String(length=16), server_default=sa.text("'AWAITING_PAYMENT'::character varying"), nullable=False),
    sa.Column('payment_method', sa.String(length=16), server_default=sa.text("'BANK_TRANSFER'::character varying"), nullable=False),
    sa.Column('stripe_checkout_session_id', sa.String(length=255), nullable=True),
    sa.Column('note', sa.String(length=1000), nullable=True),
    sa.Column('payment_proof_storage_key', sa.String(length=500), nullable=True),
    sa.Column('payment_proof_original_filename', sa.String(length=255), nullable=True),
    sa.Column('payment_proof_uploaded_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('paid_by_user_id', sa.UUID(), nullable=True),
    sa.Column('paid_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('cancelled_by_user_id', sa.UUID(), nullable=True),
    sa.Column('cancelled_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('cancellation_reason', sa.String(length=500), nullable=True),
    sa.Column('recipient_name', sa.String(length=128), nullable=False),
    sa.Column('recipient_phone', sa.String(length=32), nullable=True),
    sa.Column('address_line1', sa.String(length=255), nullable=False),
    sa.Column('address_line2', sa.String(length=255), nullable=True),
    sa.Column('city', sa.String(length=128), nullable=False),
    sa.Column('province', sa.String(length=64), nullable=False),
    sa.Column('postal_code', sa.String(length=16), nullable=False),
    sa.Column('country_code', sa.String(length=2), server_default=sa.text("'IT'::character varying"), nullable=False),
    sa.Column('shipping_days', sa.String(length=32), nullable=True),
    sa.Column('unit_cost_amount', sa.Numeric(precision=12, scale=2), nullable=True),
    sa.Column('currency_rate', sa.Numeric(precision=10, scale=6), server_default=sa.text("'1'::numeric"), nullable=False),
    sa.Column('fulfillment_status', sa.String(length=16), server_default=sa.text("'NOT_SENT'::character varying"), nullable=False),
    sa.Column('out_order_id', sa.String(length=64), nullable=True),
    sa.Column('aliexpress_order_id', sa.String(length=128), nullable=True),
    sa.Column('aliexpress_order_status', sa.String(length=64), nullable=True),
    sa.Column('forwarded_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('forwarded_by_user_id', sa.UUID(), nullable=True),
    sa.Column('forward_error', sa.String(length=500), nullable=True),
    sa.Column('tracking_number', sa.String(length=128), nullable=True),
    sa.Column('tracking_url', sa.String(length=1000), nullable=True),
    sa.Column('tracking_company', sa.String(length=128), nullable=True),
    sa.Column('shipped_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_sync_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('attempt_count', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('last_attempt_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('next_retry_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_error_kind', sa.String(length=24), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("vat_mode IN ('INCLUDED', 'ADDED')", name=op.f('ck_sn_aliexpress_orders_vat_mode')),
    sa.CheckConstraint('credit_applied_cents <= amount_cents', name=op.f('ck_sn_aliexpress_orders_credit_applied_not_over_amount')),
    sa.CheckConstraint('credit_applied_cents >= 0', name=op.f('ck_sn_aliexpress_orders_credit_applied_non_negative')),
    sa.CheckConstraint('quantity > 0', name=op.f('ck_sn_aliexpress_orders_quantity_positive')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sn_aliexpress_orders')),
    sa.UniqueConstraint('number', name=op.f('uq_sn_aliexpress_orders_number')),
    sa.UniqueConstraint('stripe_checkout_session_id', name=op.f('uq_sn_aliexpress_orders_stripe_checkout_session_id'))
    )
    op.create_index(op.f('ix_sn_aliexpress_orders_aliexpress_order_id'), 'sn_aliexpress_orders', ['aliexpress_order_id'], unique=False)
    op.create_index(op.f('ix_sn_aliexpress_orders_customer_user_id'), 'sn_aliexpress_orders', ['customer_user_id'], unique=False)
    op.create_index(op.f('ix_sn_aliexpress_orders_fulfillment_status'), 'sn_aliexpress_orders', ['fulfillment_status'], unique=False)
    op.create_index(op.f('ix_sn_aliexpress_orders_next_retry_at'), 'sn_aliexpress_orders', ['next_retry_at'], unique=False)
    op.create_index(op.f('ix_sn_aliexpress_orders_organization_id'), 'sn_aliexpress_orders', ['organization_id'], unique=False)
    op.create_index(op.f('ix_sn_aliexpress_orders_out_order_id'), 'sn_aliexpress_orders', ['out_order_id'], unique=False)
    op.create_index(op.f('ix_sn_aliexpress_orders_status'), 'sn_aliexpress_orders', ['status'], unique=False)
    op.create_table('sn_cj_orders',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('customer_user_id', sa.UUID(), nullable=False),
    sa.Column('cj_product_id', sa.UUID(), nullable=False),
    sa.Column('cj_variant_id', sa.UUID(), nullable=False),
    sa.Column('created_by_user_id', sa.UUID(), nullable=False),
    sa.Column('number', sa.BigInteger(), server_default=sa.text("nextval('sn_order_number_seq')"), nullable=False),
    sa.Column('quantity', sa.Integer(), server_default=sa.text('1'), nullable=False),
    sa.Column('unit_price_cents', sa.BigInteger(), nullable=False),
    sa.Column('shipping_cents', sa.BigInteger(), server_default=sa.text("'0'::bigint"), nullable=False),
    sa.Column('amount_cents', sa.BigInteger(), nullable=False),
    sa.Column('credit_applied_cents', sa.BigInteger(), server_default=sa.text("'0'::bigint"), nullable=False),
    sa.Column('bank_transfer_discount_cents', sa.BigInteger(), server_default=sa.text("'0'::bigint"), nullable=False),
    sa.Column('vat_percentage', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('vat_amount_cents', sa.BigInteger(), server_default=sa.text("'0'::bigint"), nullable=False),
    sa.Column('vat_mode', sa.String(length=16), server_default='ADDED', nullable=False),
    sa.Column('credit_debit_transaction_id', sa.UUID(), nullable=True),
    sa.Column('status', sa.String(length=16), server_default=sa.text("'AWAITING_PAYMENT'::character varying"), nullable=False),
    sa.Column('payment_method', sa.String(length=16), server_default=sa.text("'BANK_TRANSFER'::character varying"), nullable=False),
    sa.Column('stripe_checkout_session_id', sa.String(length=255), nullable=True),
    sa.Column('note', sa.String(length=1000), nullable=True),
    sa.Column('payment_proof_storage_key', sa.String(length=500), nullable=True),
    sa.Column('payment_proof_original_filename', sa.String(length=255), nullable=True),
    sa.Column('payment_proof_uploaded_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('paid_by_user_id', sa.UUID(), nullable=True),
    sa.Column('paid_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('cancelled_by_user_id', sa.UUID(), nullable=True),
    sa.Column('cancelled_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('cancellation_reason', sa.String(length=500), nullable=True),
    sa.Column('recipient_name', sa.String(length=128), nullable=False),
    sa.Column('recipient_phone', sa.String(length=32), nullable=True),
    sa.Column('address_line1', sa.String(length=255), nullable=False),
    sa.Column('address_line2', sa.String(length=255), nullable=True),
    sa.Column('city', sa.String(length=128), nullable=False),
    sa.Column('province', sa.String(length=64), nullable=False),
    sa.Column('postal_code', sa.String(length=16), nullable=False),
    sa.Column('country_code', sa.String(length=2), server_default=sa.text("'IT'::character varying"), nullable=False),
    sa.Column('logistic_name', sa.String(length=64), nullable=False),
    sa.Column('origin_country', sa.String(length=2), server_default=sa.text("'CN'::character varying"), nullable=False),
    sa.Column('shipping_days', sa.String(length=32), nullable=True),
    sa.Column('unit_cost_usd', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.Column('shipping_cost_usd', sa.Numeric(precision=10, scale=2), server_default=sa.text("'0'::numeric"), nullable=False),
    sa.Column('usd_eur_rate', sa.Numeric(precision=10, scale=6), nullable=False),
    sa.Column('fulfillment_status', sa.String(length=16), server_default=sa.text("'NOT_SENT'::character varying"), nullable=False),
    sa.Column('sandbox', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('cj_order_id', sa.String(length=64), nullable=True),
    sa.Column('cj_order_status', sa.String(length=32), nullable=True),
    sa.Column('cj_amount_usd', sa.Numeric(precision=12, scale=2), nullable=True),
    sa.Column('forwarded_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('forwarded_by_user_id', sa.UUID(), nullable=True),
    sa.Column('forward_error', sa.String(length=500), nullable=True),
    sa.Column('tracking_number', sa.String(length=128), nullable=True),
    sa.Column('tracking_provider', sa.String(length=64), nullable=True),
    sa.Column('shipped_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_cj_sync_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('cj_order_code', sa.String(length=64), nullable=True),
    sa.Column('cj_shipment_order_id', sa.String(length=64), nullable=True),
    sa.Column('cj_pay_url', sa.String(length=1000), nullable=True),
    sa.Column('cj_payment_status', sa.String(length=24), server_default=sa.text("'NOT_REQUIRED'::character varying"), nullable=False),
    sa.Column('cj_product_amount_usd', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('cj_postage_amount_usd', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('cj_ioss_amount_usd', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('cj_paid_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('attempt_count', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('last_attempt_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('next_retry_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_error_kind', sa.String(length=24), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("vat_mode IN ('INCLUDED', 'ADDED')", name=op.f('ck_sn_cj_orders_vat_mode')),
    sa.CheckConstraint('credit_applied_cents <= amount_cents', name=op.f('ck_sn_cj_orders_credit_applied_not_over_amount')),
    sa.CheckConstraint('credit_applied_cents >= 0', name=op.f('ck_sn_cj_orders_credit_applied_non_negative')),
    sa.CheckConstraint('quantity > 0', name=op.f('ck_sn_cj_orders_quantity_positive')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sn_cj_orders')),
    sa.UniqueConstraint('number', name=op.f('uq_sn_cj_orders_number')),
    sa.UniqueConstraint('stripe_checkout_session_id', name=op.f('uq_sn_cj_orders_stripe_checkout_session_id'))
    )
    op.create_index(op.f('ix_sn_cj_orders_cj_order_id'), 'sn_cj_orders', ['cj_order_id'], unique=False)
    op.create_index(op.f('ix_sn_cj_orders_cj_payment_status'), 'sn_cj_orders', ['cj_payment_status'], unique=False)
    op.create_index(op.f('ix_sn_cj_orders_customer_user_id'), 'sn_cj_orders', ['customer_user_id'], unique=False)
    op.create_index(op.f('ix_sn_cj_orders_fulfillment_status'), 'sn_cj_orders', ['fulfillment_status'], unique=False)
    op.create_index(op.f('ix_sn_cj_orders_next_retry_at'), 'sn_cj_orders', ['next_retry_at'], unique=False)
    op.create_index(op.f('ix_sn_cj_orders_organization_id'), 'sn_cj_orders', ['organization_id'], unique=False)
    op.create_index(op.f('ix_sn_cj_orders_status'), 'sn_cj_orders', ['status'], unique=False)
    op.create_table('sn_credit_ledger',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('from_wallet_id', sa.UUID(), nullable=True),
    sa.Column('to_wallet_id', sa.UUID(), nullable=True),
    sa.Column('amount_cents', sa.BigInteger(), nullable=False),
    sa.Column('currency', sa.String(length=3), server_default=sa.text("'EUR'::character varying"), nullable=False),
    sa.Column('type', sa.String(length=16), nullable=False),
    sa.Column('reference_contract_id', sa.UUID(), nullable=True),
    sa.Column('source', sa.String(length=32), nullable=True),
    sa.Column('reference_invoice_redemption_id', sa.UUID(), nullable=True),
    sa.Column('reference_order_id', sa.UUID(), nullable=True),
    sa.Column('reference_imported_order_id', sa.UUID(), nullable=True),
    sa.Column('reference_cj_order_id', sa.UUID(), nullable=True),
    sa.Column('reference_shopify_order_id', sa.UUID(), nullable=True),
    sa.Column('reference_aliexpress_order_id', sa.UUID(), nullable=True),
    sa.Column('reference_sosnet_market_order_id', sa.UUID(), nullable=True),
    sa.Column('reverses_transaction_id', sa.UUID(), nullable=True),
    sa.Column('note', sa.String(length=500), nullable=True),
    sa.Column('actor_user_id', sa.UUID(), nullable=True),
    sa.Column('idempotency_key', sa.String(length=128), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint('from_wallet_id IS NOT NULL OR to_wallet_id IS NOT NULL', name=op.f('ck_sn_credit_ledger_has_a_side')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sn_credit_ledger')),
    sa.UniqueConstraint('idempotency_key', name='uq_sn_credit_ledger_idempotency_key')
    )
    op.create_index(op.f('ix_sn_credit_ledger_from_wallet_id'), 'sn_credit_ledger', ['from_wallet_id'], unique=False)
    op.create_index(op.f('ix_sn_credit_ledger_organization_id'), 'sn_credit_ledger', ['organization_id'], unique=False)
    op.create_index(op.f('ix_sn_credit_ledger_reference_sosnet_market_order_id'), 'sn_credit_ledger', ['reference_sosnet_market_order_id'], unique=False)
    op.create_index(op.f('ix_sn_credit_ledger_to_wallet_id'), 'sn_credit_ledger', ['to_wallet_id'], unique=False)
    op.create_index(op.f('ix_sn_credit_ledger_type'), 'sn_credit_ledger', ['type'], unique=False)
    op.create_table('sn_market_orders',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('customer_user_id', sa.UUID(), nullable=False),
    sa.Column('created_by_user_id', sa.UUID(), nullable=False),
    sa.Column('number', sa.BigInteger(), server_default=sa.text("nextval('sn_order_number_seq')"), nullable=False),
    sa.Column('items_cents', sa.BigInteger(), server_default=sa.text("'0'::bigint"), nullable=False),
    sa.Column('shipping_cents', sa.BigInteger(), server_default=sa.text("'0'::bigint"), nullable=False),
    sa.Column('amount_cents', sa.BigInteger(), nullable=False),
    sa.Column('credit_applied_cents', sa.BigInteger(), server_default=sa.text("'0'::bigint"), nullable=False),
    sa.Column('bank_transfer_discount_cents', sa.BigInteger(), server_default=sa.text("'0'::bigint"), nullable=False),
    sa.Column('vat_percentage', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('vat_amount_cents', sa.BigInteger(), server_default=sa.text("'0'::bigint"), nullable=False),
    sa.Column('vat_mode', sa.String(length=16), server_default='ADDED', nullable=False),
    sa.Column('credit_debit_transaction_id', sa.UUID(), nullable=True),
    sa.Column('status', sa.String(length=16), server_default=sa.text("'AWAITING_PAYMENT'::character varying"), nullable=False),
    sa.Column('payment_method', sa.String(length=16), server_default=sa.text("'BANK_TRANSFER'::character varying"), nullable=False),
    sa.Column('stripe_checkout_session_id', sa.String(length=255), nullable=True),
    sa.Column('note', sa.String(length=1000), nullable=True),
    sa.Column('payment_proof_storage_key', sa.String(length=500), nullable=True),
    sa.Column('payment_proof_original_filename', sa.String(length=255), nullable=True),
    sa.Column('payment_proof_uploaded_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('paid_by_user_id', sa.UUID(), nullable=True),
    sa.Column('paid_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('cancelled_by_user_id', sa.UUID(), nullable=True),
    sa.Column('cancelled_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('cancellation_reason', sa.String(length=500), nullable=True),
    sa.Column('recipient_name', sa.String(length=128), nullable=False),
    sa.Column('recipient_phone', sa.String(length=32), nullable=True),
    sa.Column('address_line1', sa.String(length=255), nullable=False),
    sa.Column('address_line2', sa.String(length=255), nullable=True),
    sa.Column('city', sa.String(length=128), nullable=False),
    sa.Column('province', sa.String(length=64), nullable=False),
    sa.Column('postal_code', sa.String(length=16), nullable=False),
    sa.Column('country_code', sa.String(length=2), server_default=sa.text("'IT'::character varying"), nullable=False),
    sa.Column('shipping_days', sa.String(length=32), nullable=True),
    sa.Column('fulfillment_status', sa.String(length=16), server_default=sa.text("'NOT_SENT'::character varying"), nullable=False),
    sa.Column('forwarded_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('forwarded_by_user_id', sa.UUID(), nullable=True),
    sa.Column('forward_error', sa.String(length=500), nullable=True),
    sa.Column('tracking_number', sa.String(length=128), nullable=True),
    sa.Column('tracking_url', sa.String(length=1000), nullable=True),
    sa.Column('tracking_company', sa.String(length=128), nullable=True),
    sa.Column('shipped_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("vat_mode IN ('INCLUDED', 'ADDED')", name=op.f('ck_sn_market_orders_vat_mode')),
    sa.CheckConstraint('credit_applied_cents <= amount_cents', name=op.f('ck_sn_market_orders_credit_applied_not_over_amount')),
    sa.CheckConstraint('credit_applied_cents >= 0', name=op.f('ck_sn_market_orders_credit_applied_non_negative')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sn_market_orders')),
    sa.UniqueConstraint('number', name=op.f('uq_sn_market_orders_number')),
    sa.UniqueConstraint('stripe_checkout_session_id', name=op.f('uq_sn_market_orders_stripe_checkout_session_id'))
    )
    op.create_index(op.f('ix_sn_market_orders_customer_user_id'), 'sn_market_orders', ['customer_user_id'], unique=False)
    op.create_index(op.f('ix_sn_market_orders_fulfillment_status'), 'sn_market_orders', ['fulfillment_status'], unique=False)
    op.create_index(op.f('ix_sn_market_orders_organization_id'), 'sn_market_orders', ['organization_id'], unique=False)
    op.create_index(op.f('ix_sn_market_orders_status'), 'sn_market_orders', ['status'], unique=False)
    op.create_table('sn_permissions',
    sa.Column('code', sa.String(length=64), nullable=False),
    sa.Column('description', sa.String(length=255), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sn_permissions')),
    sa.UniqueConstraint('code', name=op.f('uq_sn_permissions_code'))
    )
    op.create_table('sn_shop_orders',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('customer_user_id', sa.UUID(), nullable=False),
    sa.Column('product_version_id', sa.UUID(), nullable=False),
    sa.Column('created_by_user_id', sa.UUID(), nullable=False),
    sa.Column('amount_cents', sa.BigInteger(), nullable=False),
    sa.Column('credit_applied_cents', sa.BigInteger(), server_default=sa.text("'0'::bigint"), nullable=False),
    sa.Column('credit_debit_transaction_id', sa.UUID(), nullable=True),
    sa.Column('cashback_requested', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('cashback_surcharge_cents', sa.BigInteger(), server_default=sa.text("'0'::bigint"), nullable=False),
    sa.Column('cashback_credited_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('status', sa.String(length=16), server_default=sa.text("'AWAITING_PAYMENT'::character varying"), nullable=False),
    sa.Column('payment_method', sa.String(length=16), server_default=sa.text("'BANK_TRANSFER'::character varying"), nullable=False),
    sa.Column('stripe_checkout_session_id', sa.String(length=255), nullable=True),
    sa.Column('note', sa.String(length=1000), nullable=True),
    sa.Column('payment_proof_storage_key', sa.String(length=500), nullable=True),
    sa.Column('payment_proof_original_filename', sa.String(length=255), nullable=True),
    sa.Column('payment_proof_uploaded_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('paid_by_user_id', sa.UUID(), nullable=True),
    sa.Column('paid_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('cancelled_by_user_id', sa.UUID(), nullable=True),
    sa.Column('cancelled_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('cancellation_reason', sa.String(length=500), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint('credit_applied_cents <= amount_cents', name=op.f('ck_sn_shop_orders_credit_applied_not_over_amount')),
    sa.CheckConstraint('credit_applied_cents >= 0', name=op.f('ck_sn_shop_orders_credit_applied_non_negative')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sn_shop_orders')),
    sa.UniqueConstraint('stripe_checkout_session_id', name=op.f('uq_sn_shop_orders_stripe_checkout_session_id'))
    )
    op.create_index(op.f('ix_sn_shop_orders_customer_user_id'), 'sn_shop_orders', ['customer_user_id'], unique=False)
    op.create_index(op.f('ix_sn_shop_orders_organization_id'), 'sn_shop_orders', ['organization_id'], unique=False)
    op.create_index(op.f('ix_sn_shop_orders_status'), 'sn_shop_orders', ['status'], unique=False)
    op.create_table('sn_shopify_orders',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('customer_user_id', sa.UUID(), nullable=False),
    sa.Column('shopify_product_id', sa.UUID(), nullable=False),
    sa.Column('shopify_variant_id', sa.UUID(), nullable=False),
    sa.Column('created_by_user_id', sa.UUID(), nullable=False),
    sa.Column('number', sa.BigInteger(), server_default=sa.text("nextval('sn_order_number_seq')"), nullable=False),
    sa.Column('quantity', sa.Integer(), server_default=sa.text('1'), nullable=False),
    sa.Column('unit_price_cents', sa.BigInteger(), nullable=False),
    sa.Column('shipping_cents', sa.BigInteger(), server_default=sa.text("'0'::bigint"), nullable=False),
    sa.Column('amount_cents', sa.BigInteger(), nullable=False),
    sa.Column('credit_applied_cents', sa.BigInteger(), server_default=sa.text("'0'::bigint"), nullable=False),
    sa.Column('bank_transfer_discount_cents', sa.BigInteger(), server_default=sa.text("'0'::bigint"), nullable=False),
    sa.Column('vat_percentage', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('vat_amount_cents', sa.BigInteger(), server_default=sa.text("'0'::bigint"), nullable=False),
    sa.Column('vat_mode', sa.String(length=16), server_default='ADDED', nullable=False),
    sa.Column('credit_debit_transaction_id', sa.UUID(), nullable=True),
    sa.Column('status', sa.String(length=16), server_default=sa.text("'AWAITING_PAYMENT'::character varying"), nullable=False),
    sa.Column('payment_method', sa.String(length=16), server_default=sa.text("'BANK_TRANSFER'::character varying"), nullable=False),
    sa.Column('stripe_checkout_session_id', sa.String(length=255), nullable=True),
    sa.Column('note', sa.String(length=1000), nullable=True),
    sa.Column('payment_proof_storage_key', sa.String(length=500), nullable=True),
    sa.Column('payment_proof_original_filename', sa.String(length=255), nullable=True),
    sa.Column('payment_proof_uploaded_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('paid_by_user_id', sa.UUID(), nullable=True),
    sa.Column('paid_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('cancelled_by_user_id', sa.UUID(), nullable=True),
    sa.Column('cancelled_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('cancellation_reason', sa.String(length=500), nullable=True),
    sa.Column('recipient_name', sa.String(length=128), nullable=False),
    sa.Column('recipient_phone', sa.String(length=32), nullable=True),
    sa.Column('address_line1', sa.String(length=255), nullable=False),
    sa.Column('address_line2', sa.String(length=255), nullable=True),
    sa.Column('city', sa.String(length=128), nullable=False),
    sa.Column('province', sa.String(length=64), nullable=False),
    sa.Column('postal_code', sa.String(length=16), nullable=False),
    sa.Column('country_code', sa.String(length=2), server_default=sa.text("'IT'::character varying"), nullable=False),
    sa.Column('shipping_days', sa.String(length=32), nullable=True),
    sa.Column('unit_cost_amount', sa.Numeric(precision=12, scale=2), nullable=True),
    sa.Column('currency_rate', sa.Numeric(precision=10, scale=6), server_default=sa.text("'1'::numeric"), nullable=False),
    sa.Column('fulfillment_status', sa.String(length=16), server_default=sa.text("'NOT_SENT'::character varying"), nullable=False),
    sa.Column('shopify_draft_order_id', sa.String(length=128), nullable=True),
    sa.Column('shopify_order_id', sa.String(length=128), nullable=True),
    sa.Column('shopify_order_name', sa.String(length=64), nullable=True),
    sa.Column('shopify_fulfillment_status', sa.String(length=32), nullable=True),
    sa.Column('forwarded_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('forwarded_by_user_id', sa.UUID(), nullable=True),
    sa.Column('forward_error', sa.String(length=500), nullable=True),
    sa.Column('tracking_number', sa.String(length=128), nullable=True),
    sa.Column('tracking_url', sa.String(length=1000), nullable=True),
    sa.Column('tracking_company', sa.String(length=128), nullable=True),
    sa.Column('shipped_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_sync_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('attempt_count', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('last_attempt_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('next_retry_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_error_kind', sa.String(length=24), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("vat_mode IN ('INCLUDED', 'ADDED')", name=op.f('ck_sn_shopify_orders_vat_mode')),
    sa.CheckConstraint('credit_applied_cents <= amount_cents', name=op.f('ck_sn_shopify_orders_credit_applied_not_over_amount')),
    sa.CheckConstraint('credit_applied_cents >= 0', name=op.f('ck_sn_shopify_orders_credit_applied_non_negative')),
    sa.CheckConstraint('quantity > 0', name=op.f('ck_sn_shopify_orders_quantity_positive')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sn_shopify_orders')),
    sa.UniqueConstraint('number', name=op.f('uq_sn_shopify_orders_number')),
    sa.UniqueConstraint('stripe_checkout_session_id', name=op.f('uq_sn_shopify_orders_stripe_checkout_session_id'))
    )
    op.create_index(op.f('ix_sn_shopify_orders_customer_user_id'), 'sn_shopify_orders', ['customer_user_id'], unique=False)
    op.create_index(op.f('ix_sn_shopify_orders_fulfillment_status'), 'sn_shopify_orders', ['fulfillment_status'], unique=False)
    op.create_index(op.f('ix_sn_shopify_orders_next_retry_at'), 'sn_shopify_orders', ['next_retry_at'], unique=False)
    op.create_index(op.f('ix_sn_shopify_orders_organization_id'), 'sn_shopify_orders', ['organization_id'], unique=False)
    op.create_index(op.f('ix_sn_shopify_orders_shopify_order_id'), 'sn_shopify_orders', ['shopify_order_id'], unique=False)
    op.create_index(op.f('ix_sn_shopify_orders_status'), 'sn_shopify_orders', ['status'], unique=False)
    op.create_table('sn_supplier_item_orders',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('customer_user_id', sa.UUID(), nullable=False),
    sa.Column('imported_product_id', sa.UUID(), nullable=False),
    sa.Column('created_by_user_id', sa.UUID(), nullable=False),
    sa.Column('number', sa.BigInteger(), server_default=sa.text("nextval('sn_order_number_seq')"), nullable=False),
    sa.Column('amount_cents', sa.BigInteger(), nullable=False),
    sa.Column('credit_applied_cents', sa.BigInteger(), server_default=sa.text("'0'::bigint"), nullable=False),
    sa.Column('bank_transfer_discount_cents', sa.BigInteger(), server_default=sa.text("'0'::bigint"), nullable=False),
    sa.Column('vat_percentage', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('vat_amount_cents', sa.BigInteger(), server_default=sa.text("'0'::bigint"), nullable=False),
    sa.Column('vat_mode', sa.String(length=16), server_default='ADDED', nullable=False),
    sa.Column('credit_debit_transaction_id', sa.UUID(), nullable=True),
    sa.Column('status', sa.String(length=16), server_default=sa.text("'AWAITING_PAYMENT'::character varying"), nullable=False),
    sa.Column('payment_method', sa.String(length=16), server_default=sa.text("'BANK_TRANSFER'::character varying"), nullable=False),
    sa.Column('stripe_checkout_session_id', sa.String(length=255), nullable=True),
    sa.Column('note', sa.String(length=1000), nullable=True),
    sa.Column('payment_proof_storage_key', sa.String(length=500), nullable=True),
    sa.Column('payment_proof_original_filename', sa.String(length=255), nullable=True),
    sa.Column('payment_proof_uploaded_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('paid_by_user_id', sa.UUID(), nullable=True),
    sa.Column('paid_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('cancelled_by_user_id', sa.UUID(), nullable=True),
    sa.Column('cancelled_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('cancellation_reason', sa.String(length=500), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("vat_mode IN ('INCLUDED', 'ADDED')", name=op.f('ck_sn_supplier_item_orders_vat_mode')),
    sa.CheckConstraint('credit_applied_cents <= amount_cents', name=op.f('ck_sn_supplier_item_orders_credit_applied_not_over_amount')),
    sa.CheckConstraint('credit_applied_cents >= 0', name=op.f('ck_sn_supplier_item_orders_credit_applied_non_negative')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sn_supplier_item_orders')),
    sa.UniqueConstraint('number', name=op.f('uq_sn_supplier_item_orders_number')),
    sa.UniqueConstraint('stripe_checkout_session_id', name=op.f('uq_sn_supplier_item_orders_stripe_checkout_session_id'))
    )
    op.create_index(op.f('ix_sn_supplier_item_orders_customer_user_id'), 'sn_supplier_item_orders', ['customer_user_id'], unique=False)
    op.create_index(op.f('ix_sn_supplier_item_orders_organization_id'), 'sn_supplier_item_orders', ['organization_id'], unique=False)
    op.create_index(op.f('ix_sn_supplier_item_orders_status'), 'sn_supplier_item_orders', ['status'], unique=False)
    op.create_table('sn_tenants',
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('legal_name', sa.String(length=255), nullable=True),
    sa.Column('vat_number', sa.String(length=32), nullable=True),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('settings', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sn_tenants'))
    )
    op.create_table('sn_accounts',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('email', sa.String(length=255), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('email_verified_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('failed_login_attempts', sa.Integer(), nullable=False),
    sa.Column('locked_until', sa.DateTime(timezone=True), nullable=True),
    sa.Column('privacy_accepted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('fiscal_code', sa.String(length=16), nullable=True),
    sa.Column('residence_street', sa.String(length=255), nullable=True),
    sa.Column('residence_city', sa.String(length=100), nullable=True),
    sa.Column('residence_province', sa.String(length=2), nullable=True),
    sa.Column('residence_postal_code', sa.String(length=10), nullable=True),
    sa.Column('residence_country', sa.String(length=2), server_default=sa.text("'IT'::character varying"), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sn_accounts')),
    sa.UniqueConstraint('organization_id', 'email', name='uq_sn_accounts_org_email')
    )
    op.create_index(op.f('ix_sn_accounts_email'), 'sn_accounts', ['email'], unique=False)
    op.create_index(op.f('ix_sn_accounts_organization_id'), 'sn_accounts', ['organization_id'], unique=False)
    op.create_table('sn_aliexpress_config',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('app_key', sa.String(length=64), nullable=True),
    sa.Column('app_secret', sa.String(length=255), nullable=True),
    sa.Column('access_token', sa.String(length=500), nullable=True),
    sa.Column('refresh_token', sa.String(length=500), nullable=True),
    sa.Column('token_expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('account_label', sa.String(length=255), nullable=True),
    sa.Column('last_connected_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('enabled', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('ship_to_country', sa.String(length=2), server_default=sa.text("'IT'::character varying"), nullable=False),
    sa.Column('target_currency', sa.String(length=3), server_default=sa.text("'EUR'::character varying"), nullable=False),
    sa.Column('target_language', sa.String(length=8), server_default=sa.text("'it'::character varying"), nullable=False),
    sa.Column('currency_rate', sa.Numeric(precision=10, scale=6), server_default=sa.text("'1'::numeric"), nullable=False),
    sa.Column('price_basis', sa.String(length=8), server_default=sa.text("'COST'::character varying"), nullable=False),
    sa.Column('markup_percentage', sa.Integer(), server_default=sa.text('100'), nullable=False),
    sa.Column('markup_fixed_cents', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('price_rounding', sa.String(length=8), server_default=sa.text("'90'::character varying"), nullable=False),
    sa.Column('shipping_mode', sa.String(length=16), server_default=sa.text("'CUSTOMER_PAYS'::character varying"), nullable=False),
    sa.Column('shipping_minimum_cents', sa.Integer(), server_default=sa.text('590'), nullable=False),
    sa.Column('shipping_days', sa.String(length=32), server_default=sa.text("'10-20'::character varying"), nullable=True),
    sa.Column('default_credit_percentage', sa.Integer(), server_default=sa.text('30'), nullable=False),
    sa.Column('auto_forward', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sn_aliexpress_config')),
    sa.UniqueConstraint('organization_id', name=op.f('uq_sn_aliexpress_config_organization_id'))
    )
    op.create_table('sn_career_levels',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('code', sa.String(length=16), nullable=False),
    sa.Column('name', sa.String(length=128), nullable=False),
    sa.Column('level', sa.Integer(), nullable=False),
    sa.Column('personal_token_cents', sa.BigInteger(), nullable=False),
    sa.Column('energy_share_percentage', sa.Numeric(precision=5, scale=2), nullable=False),
    sa.Column('personal_volume_threshold_cents', sa.BigInteger(), nullable=False),
    sa.Column('group_volume_threshold_cents', sa.BigInteger(), nullable=False),
    sa.Column('evaluation_window_months', sa.Integer(), nullable=False),
    sa.Column('single_branch_cap_percentage', sa.Numeric(precision=5, scale=2), nullable=False),
    sa.Column('valid_from', sa.DateTime(timezone=True), nullable=False),
    sa.Column('valid_to', sa.DateTime(timezone=True), nullable=True),
    sa.Column('rule_version', sa.String(length=32), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sn_career_levels')),
    sa.UniqueConstraint('organization_id', 'code', 'rule_version', name='uq_sn_career_levels_org_code_version')
    )
    op.create_index(op.f('ix_sn_career_levels_organization_id'), 'sn_career_levels', ['organization_id'], unique=False)
    op.create_table('sn_catalog_sections',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('shop', sa.String(length=16), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('position', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sn_catalog_sections'))
    )
    op.create_index(op.f('ix_sn_catalog_sections_organization_id'), 'sn_catalog_sections', ['organization_id'], unique=False)
    op.create_index('uq_sn_catalog_sections_organization_id_shop_name', 'sn_catalog_sections', ['organization_id', 'shop', sa.literal_column('lower(name)')], unique=True)
    op.create_table('sn_cj_config',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('api_key', sa.String(length=255), nullable=True),
    sa.Column('access_token', sa.Text(), nullable=True),
    sa.Column('access_token_expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('refresh_token', sa.Text(), nullable=True),
    sa.Column('refresh_token_expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('open_id', sa.String(length=64), nullable=True),
    sa.Column('enabled', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('sandbox', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('usd_eur_rate', sa.Numeric(precision=10, scale=6), server_default=sa.text('0.92'), nullable=False),
    sa.Column('markup_percentage', sa.Integer(), server_default=sa.text('40'), nullable=False),
    sa.Column('markup_fixed_cents', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('price_rounding', sa.String(length=8), server_default=sa.text("'90'::character varying"), nullable=False),
    sa.Column('shipping_mode', sa.String(length=16), server_default=sa.text("'CUSTOMER_PAYS'::character varying"), nullable=False),
    sa.Column('default_credit_percentage', sa.Integer(), server_default=sa.text('30'), nullable=False),
    sa.Column('destination_country', sa.String(length=2), server_default=sa.text("'IT'::character varying"), nullable=False),
    sa.Column('auto_forward', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('last_balance_usd', sa.Numeric(precision=12, scale=2), nullable=True),
    sa.Column('last_balance_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('default_credit_percentage BETWEEN 0 AND 99', name=op.f('ck_sn_cj_config_default_credit_below_100')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sn_cj_config')),
    sa.UniqueConstraint('organization_id', name=op.f('uq_sn_cj_config_organization_id'))
    )
    op.create_table('sn_event_outbox',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('event_type', sa.String(length=64), nullable=False),
    sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sn_event_outbox'))
    )
    op.create_index(op.f('ix_sn_event_outbox_event_type'), 'sn_event_outbox', ['event_type'], unique=False)
    op.create_index(op.f('ix_sn_event_outbox_organization_id'), 'sn_event_outbox', ['organization_id'], unique=False)
    op.create_index(op.f('ix_sn_event_outbox_processed_at'), 'sn_event_outbox', ['processed_at'], unique=False)
    op.create_table('sn_market_config',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('enabled', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('shipping_mode', sa.String(length=16), server_default=sa.text("'CUSTOMER_PAYS'::character varying"), nullable=False),
    sa.Column('shipping_flat_cents', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('shipping_days', sa.String(length=32), nullable=True),
    sa.Column('ship_to_country', sa.String(length=2), server_default=sa.text("'IT'::character varying"), nullable=False),
    sa.Column('auto_forward', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sn_market_config')),
    sa.UniqueConstraint('organization_id', name=op.f('uq_sn_market_config_organization_id'))
    )
    op.create_index(op.f('ix_sn_market_config_organization_id'), 'sn_market_config', ['organization_id'], unique=False)
    op.create_table('sn_merchants',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('logo_url', sa.String(length=1000), nullable=True),
    sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sn_merchants')),
    sa.UniqueConstraint('organization_id', 'name', name='uq_sn_merchants_organization_name')
    )
    op.create_index(op.f('ix_sn_merchants_organization_id'), 'sn_merchants', ['organization_id'], unique=False)
    op.create_table('sn_offers',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('code', sa.String(length=64), nullable=False),
    sa.Column('product_type', sa.String(length=32), server_default=sa.text("'ENERGY_CONTRACT'::character varying"), nullable=False),
    sa.Column('energy_type', sa.String(length=16), nullable=True),
    sa.Column('customer_type', sa.String(length=32), nullable=False),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('category', sa.String(length=16), server_default=sa.text("'INTERNAL'::character varying"), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sn_offers'))
    )
    op.create_index(op.f('ix_sn_offers_organization_id'), 'sn_offers', ['organization_id'], unique=False)
    op.create_table('sn_payout_plans',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('version_label', sa.String(length=32), nullable=False),
    sa.Column('valid_from', sa.DateTime(timezone=True), nullable=False),
    sa.Column('valid_to', sa.DateTime(timezone=True), nullable=True),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sn_payout_plans'))
    )
    op.create_index(op.f('ix_sn_payout_plans_organization_id'), 'sn_payout_plans', ['organization_id'], unique=False)
    op.create_table('sn_roles',
    sa.Column('organization_id', sa.UUID(), nullable=True),
    sa.Column('code', sa.String(length=64), nullable=False),
    sa.Column('name', sa.String(length=128), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sn_roles')),
    sa.UniqueConstraint('organization_id', 'code', name='uq_sn_roles_org_code')
    )
    op.create_index(op.f('ix_sn_roles_organization_id'), 'sn_roles', ['organization_id'], unique=False)
    op.create_table('sn_shopify_config',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('shop_domain', sa.String(length=255), nullable=True),
    sa.Column('access_token', sa.String(length=255), nullable=True),
    sa.Column('client_id', sa.String(length=255), nullable=True),
    sa.Column('client_secret', sa.String(length=255), nullable=True),
    sa.Column('token_expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('api_version', sa.String(length=16), server_default=sa.text("'2025-07'::character varying"), nullable=False),
    sa.Column('enabled', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('shop_name', sa.String(length=255), nullable=True),
    sa.Column('shop_currency', sa.String(length=3), nullable=True),
    sa.Column('currency_rate', sa.Numeric(precision=10, scale=6), server_default=sa.text("'1'::numeric"), nullable=False),
    sa.Column('price_basis', sa.String(length=8), server_default=sa.text("'COST'::character varying"), nullable=False),
    sa.Column('markup_percentage', sa.Integer(), server_default=sa.text('100'), nullable=False),
    sa.Column('markup_fixed_cents', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('price_rounding', sa.String(length=8), server_default=sa.text("'90'::character varying"), nullable=False),
    sa.Column('shipping_mode', sa.String(length=16), server_default=sa.text("'CUSTOMER_PAYS'::character varying"), nullable=False),
    sa.Column('shipping_flat_cents', sa.Integer(), server_default=sa.text('590'), nullable=False),
    sa.Column('shipping_days', sa.String(length=32), server_default=sa.text("'7-15'::character varying"), nullable=True),
    sa.Column('default_credit_percentage', sa.Integer(), server_default=sa.text('30'), nullable=False),
    sa.Column('auto_forward', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('last_connected_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sn_shopify_config')),
    sa.UniqueConstraint('organization_id', name=op.f('uq_sn_shopify_config_organization_id'))
    )
    op.create_table('sn_stripe_events',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('stripe_event_id', sa.String(length=255), nullable=False),
    sa.Column('event_type', sa.String(length=64), nullable=False),
    sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('outcome', sa.String(length=255), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sn_stripe_events')),
    sa.UniqueConstraint('stripe_event_id', name='uq_sn_stripe_events_event_id')
    )
    op.create_index(op.f('ix_sn_stripe_events_event_type'), 'sn_stripe_events', ['event_type'], unique=False)
    op.create_index(op.f('ix_sn_stripe_events_organization_id'), 'sn_stripe_events', ['organization_id'], unique=False)
    op.create_table('sn_tree_snapshots',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('reason', sa.String(length=64), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sn_tree_snapshots'))
    )
    op.create_index(op.f('ix_sn_tree_snapshots_organization_id'), 'sn_tree_snapshots', ['organization_id'], unique=False)
    op.create_table('sn_account_roles',
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('role_id', sa.UUID(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sn_account_roles')),
    sa.UniqueConstraint('user_id', 'organization_id', 'role_id', name='uq_sn_account_roles')
    )
    op.create_index(op.f('ix_sn_account_roles_organization_id'), 'sn_account_roles', ['organization_id'], unique=False)
    op.create_index(op.f('ix_sn_account_roles_user_id'), 'sn_account_roles', ['user_id'], unique=False)
    op.create_table('sn_activity_log',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('actor_user_id', sa.UUID(), nullable=True),
    sa.Column('action', sa.String(length=128), nullable=False),
    sa.Column('entity_type', sa.String(length=64), nullable=False),
    sa.Column('entity_id', sa.String(length=64), nullable=False),
    sa.Column('previous_value', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('new_value', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('reason', sa.String(length=500), nullable=True),
    sa.Column('ip_address', sa.String(length=64), nullable=True),
    sa.Column('user_agent', sa.String(length=255), nullable=True),
    sa.Column('correlation_id', sa.String(length=64), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sn_activity_log'))
    )
    op.create_index(op.f('ix_sn_activity_log_action'), 'sn_activity_log', ['action'], unique=False)
    op.create_index(op.f('ix_sn_activity_log_correlation_id'), 'sn_activity_log', ['correlation_id'], unique=False)
    op.create_index(op.f('ix_sn_activity_log_organization_id'), 'sn_activity_log', ['organization_id'], unique=False)
    op.create_table('sn_aliexpress_items',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('aliexpress_product_id', sa.String(length=128), nullable=False),
    sa.Column('product_url', sa.String(length=1000), nullable=True),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('source_title', sa.String(length=500), nullable=True),
    sa.Column('vendor', sa.String(length=255), nullable=True),
    sa.Column('description', sa.String(length=8000), server_default=sa.text("''::character varying"), nullable=False),
    sa.Column('image_url', sa.String(length=1000), nullable=True),
    sa.Column('images', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
    sa.Column('status', sa.String(length=16), server_default=sa.text("'ACTIVE'::character varying"), nullable=False),
    sa.Column('credit_discount_percentage', sa.Integer(), server_default=sa.text('30'), nullable=False),
    sa.Column('markup_percentage', sa.Integer(), nullable=True),
    sa.Column('last_synced_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('sync_error', sa.String(length=500), nullable=True),
    sa.Column('created_by_user_id', sa.UUID(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('credit_discount_percentage >= 0 AND credit_discount_percentage <= 99', name=op.f('ck_sn_aliexpress_items_credit_discount_percentage_below_100')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sn_aliexpress_items')),
    sa.UniqueConstraint('organization_id', 'aliexpress_product_id', name=op.f('uq_sn_aliexpress_items_organization_id'))
    )
    op.create_index(op.f('ix_sn_aliexpress_items_organization_id'), 'sn_aliexpress_items', ['organization_id'], unique=False)
    op.create_index(op.f('ix_sn_aliexpress_items_status'), 'sn_aliexpress_items', ['status'], unique=False)
    op.create_table('sn_baskets',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('customer_user_id', sa.UUID(), nullable=False),
    sa.Column('shop', sa.String(length=16), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("shop IN ('aliexpress', 'cj', 'shopify', 'sosnet_market', 'catalog')", name=op.f('ck_sn_baskets_shop')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sn_baskets')),
    sa.UniqueConstraint('customer_user_id', 'shop', name='uq_sn_baskets_customer_shop')
    )
    op.create_index(op.f('ix_sn_baskets_customer_user_id'), 'sn_baskets', ['customer_user_id'], unique=False)
    op.create_index(op.f('ix_sn_baskets_organization_id'), 'sn_baskets', ['organization_id'], unique=False)
    op.create_table('sn_catalog_section_items',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('category_id', sa.UUID(), nullable=False),
    sa.Column('shop', sa.String(length=16), nullable=False),
    sa.Column('product_id', sa.UUID(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sn_catalog_section_items')),
    sa.UniqueConstraint('category_id', 'product_id', name='uq_sn_catalog_section_items_category_id')
    )
    op.create_index(op.f('ix_sn_catalog_section_items_category_id'), 'sn_catalog_section_items', ['category_id'], unique=False)
    op.create_index('ix_sn_catalog_section_items_organization_id_shop_product_id', 'sn_catalog_section_items', ['organization_id', 'shop', 'product_id'], unique=False)
    op.create_table('sn_cj_items',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('cj_pid', sa.String(length=64), nullable=False),
    sa.Column('cj_sku', sa.String(length=64), nullable=True),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('name_en', sa.String(length=500), nullable=True),
    sa.Column('description', sa.String(length=8000), server_default=sa.text("''::character varying"), nullable=False),
    sa.Column('image_url', sa.String(length=1000), nullable=True),
    sa.Column('images', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
    sa.Column('category_name', sa.String(length=255), nullable=True),
    sa.Column('origin_country', sa.String(length=2), server_default=sa.text("'CN'::character varying"), nullable=False),
    sa.Column('shipping_estimate_usd', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('shipping_days', sa.String(length=32), nullable=True),
    sa.Column('status', sa.String(length=16), server_default=sa.text("'ACTIVE'::character varying"), nullable=False),
    sa.Column('credit_discount_percentage', sa.Integer(), server_default=sa.text('100'), nullable=False),
    sa.Column('markup_percentage', sa.Integer(), nullable=True),
    sa.Column('last_synced_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('sync_error', sa.String(length=500), nullable=True),
    sa.Column('created_by_user_id', sa.UUID(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('credit_discount_percentage BETWEEN 0 AND 99', name=op.f('ck_sn_cj_items_credit_below_100')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sn_cj_items')),
    sa.UniqueConstraint('organization_id', 'cj_pid', name=op.f('uq_sn_cj_items_organization_id'))
    )
    op.create_index(op.f('ix_sn_cj_items_organization_id'), 'sn_cj_items', ['organization_id'], unique=False)
    op.create_index(op.f('ix_sn_cj_items_status'), 'sn_cj_items', ['status'], unique=False)
    op.create_table('sn_clients',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=True),
    sa.Column('kind', sa.String(length=32), nullable=False),
    sa.Column('fiscal_code', sa.String(length=32), nullable=True),
    sa.Column('vat_number', sa.String(length=32), nullable=True),
    sa.Column('email', sa.String(length=255), nullable=False),
    sa.Column('phone', sa.String(length=32), nullable=True),
    sa.Column('pec', sa.String(length=255), nullable=True),
    sa.Column('photo_url', sa.String(length=1000), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sn_clients')),
    sa.UniqueConstraint('user_id', name=op.f('uq_sn_clients_user_id'))
    )
    op.create_index(op.f('ix_sn_clients_organization_id'), 'sn_clients', ['organization_id'], unique=False)
    op.create_table('sn_credit_accounts',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('address', sa.String(length=42), nullable=False),
    sa.Column('balance_cents', sa.BigInteger(), server_default=sa.text("'0'::bigint"), nullable=False),
    sa.Column('currency', sa.String(length=3), server_default=sa.text("'EUR'::character varying"), nullable=False),
    sa.Column('can_transfer', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint('balance_cents >= 0', name=op.f('ck_sn_credit_accounts_balance_non_negative')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sn_credit_accounts')),
    sa.UniqueConstraint('address', name='uq_sn_credit_accounts_address'),
    sa.UniqueConstraint('user_id', name='uq_sn_credit_accounts_user_id')
    )
    op.create_index(op.f('ix_sn_credit_accounts_address'), 'sn_credit_accounts', ['address'], unique=False)
    op.create_index(op.f('ix_sn_credit_accounts_organization_id'), 'sn_credit_accounts', ['organization_id'], unique=False)
    op.create_index(op.f('ix_sn_credit_accounts_user_id'), 'sn_credit_accounts', ['user_id'], unique=False)
    op.create_table('sn_email_confirmations',
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sn_email_confirmations'))
    )
    op.create_index(op.f('ix_sn_email_confirmations_token_hash'), 'sn_email_confirmations', ['token_hash'], unique=True)
    op.create_index(op.f('ix_sn_email_confirmations_user_id'), 'sn_email_confirmations', ['user_id'], unique=False)
    op.create_table('sn_friend_invite_codes',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('code', sa.String(length=32), nullable=False),
    sa.Column('status', sa.String(length=16), server_default=sa.text("'ACTIVE'::character varying"), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sn_friend_invite_codes')),
    sa.UniqueConstraint('code', name='uq_sn_friend_invite_codes_code'),
    sa.UniqueConstraint('user_id', name='uq_sn_friend_invite_codes_user_id')
    )
    op.create_index(op.f('ix_sn_friend_invite_codes_organization_id'), 'sn_friend_invite_codes', ['organization_id'], unique=False)
    op.create_table('sn_friend_invite_rewards',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('referrer_user_id', sa.UUID(), nullable=False),
    sa.Column('milestone', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=16), server_default=sa.text("'REQUESTED'::character varying"), nullable=False),
    sa.Column('handled_by_user_id', sa.UUID(), nullable=True),
    sa.Column('handled_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('note', sa.String(length=500), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sn_friend_invite_rewards')),
    sa.UniqueConstraint('referrer_user_id', 'milestone', name='uq_sn_friend_invite_rewards_user_milestone')
    )
    op.create_index(op.f('ix_sn_friend_invite_rewards_organization_id'), 'sn_friend_invite_rewards', ['organization_id'], unique=False)
    op.create_index(op.f('ix_sn_friend_invite_rewards_referrer_user_id'), 'sn_friend_invite_rewards', ['referrer_user_id'], unique=False)
    op.create_index(op.f('ix_sn_friend_invite_rewards_status'), 'sn_friend_invite_rewards', ['status'], unique=False)
    op.create_table('sn_inbox_messages',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('recipient_user_id', sa.UUID(), nullable=False),
    sa.Column('type', sa.String(length=64), nullable=False),
    sa.Column('entity_type', sa.String(length=64), nullable=False),
    sa.Column('entity_id', sa.String(length=64), nullable=False),
    sa.Column('title', sa.String(length=255), nullable=False),
    sa.Column('body', sa.String(length=1000), nullable=True),
    sa.Column('is_read', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sn_inbox_messages'))
    )
    op.create_index(op.f('ix_sn_inbox_messages_is_read'), 'sn_inbox_messages', ['is_read'], unique=False)
    op.create_index(op.f('ix_sn_inbox_messages_organization_id'), 'sn_inbox_messages', ['organization_id'], unique=False)
    op.create_index(op.f('ix_sn_inbox_messages_recipient_user_id'), 'sn_inbox_messages', ['recipient_user_id'], unique=False)
    op.create_index(op.f('ix_sn_inbox_messages_type'), 'sn_inbox_messages', ['type'], unique=False)
    op.create_table('sn_knowledge_articles',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('body', sa.Text(), nullable=True),
    sa.Column('audience', sa.String(length=16), server_default=sa.text("'BOTH'::character varying"), nullable=False),
    sa.Column('status', sa.String(length=16), server_default=sa.text("'PUBLISHED'::character varying"), nullable=False),
    sa.Column('image_url', sa.String(length=500), nullable=True),
    sa.Column('pdf_url', sa.String(length=500), nullable=True),
    sa.Column('pdf_filename', sa.String(length=255), nullable=True),
    sa.Column('video_url', sa.String(length=500), nullable=True),
    sa.Column('created_by_user_id', sa.UUID(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sn_knowledge_articles'))
    )
    op.create_index(op.f('ix_sn_knowledge_articles_organization_id'), 'sn_knowledge_articles', ['organization_id'], unique=False)
    op.create_index(op.f('ix_sn_knowledge_articles_status'), 'sn_knowledge_articles', ['status'], unique=False)
    op.create_table('sn_login_sessions',
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('refresh_token_hash', sa.String(length=64), nullable=False),
    sa.Column('user_agent', sa.String(length=255), nullable=True),
    sa.Column('ip_address', sa.String(length=64), nullable=True),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sn_login_sessions'))
    )
    op.create_index(op.f('ix_sn_login_sessions_refresh_token_hash'), 'sn_login_sessions', ['refresh_token_hash'], unique=True)
    op.create_index(op.f('ix_sn_login_sessions_user_id'), 'sn_login_sessions', ['user_id'], unique=False)
    op.create_table('sn_market_producers',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(length=160), nullable=False),
    sa.Column('description', sa.String(length=4000), server_default=sa.text("''::character varying"), nullable=False),
    sa.Column('website_url', sa.String(length=1000), nullable=True),
    sa.Column('logo_url', sa.String(length=1000), nullable=True),
    sa.Column('vat_number', sa.String(length=32), nullable=True),
    sa.Column('email', sa.String(length=255), nullable=True),
    sa.Column('phone', sa.String(length=32), nullable=True),
    sa.Column('address', sa.String(length=500), nullable=True),
    sa.Column('active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('created_by_user_id', sa.UUID(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sn_market_producers')),
    sa.UniqueConstraint('organization_id', 'name', name='uq_sn_market_producers_name')
    )
    op.create_index(op.f('ix_sn_market_producers_organization_id'), 'sn_market_producers', ['organization_id'], unique=False)
    op.create_table('sn_offer_versions',
    sa.Column('product_id', sa.UUID(), nullable=False),
    sa.Column('version_label', sa.String(length=32), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('description', sa.String(length=2000), nullable=False),
    sa.Column('image_url', sa.String(length=1000), nullable=True),
    sa.Column('base_price_cents', sa.BigInteger(), nullable=False),
    sa.Column('initial_fee_cents', sa.BigInteger(), nullable=False),
    sa.Column('recurring_fee_cents', sa.BigInteger(), nullable=False),
    sa.Column('billing_period', sa.String(length=16), nullable=False),
    sa.Column('contract_duration_months', sa.Integer(), server_default=sa.text('12'), nullable=True),
    sa.Column('tax_configuration', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('commission_plan_version_id', sa.UUID(), nullable=True),
    sa.Column('commission_tokens', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('required_documents', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('terms_version', sa.String(length=32), nullable=False),
    sa.Column('valid_from', sa.DateTime(timezone=True), nullable=False),
    sa.Column('valid_to', sa.DateTime(timezone=True), nullable=True),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('credit_discount_percentage', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('cashback_enabled', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('contract_cashback_percentage', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('first_referrer_bonus_enabled', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('first_referrer_bonus_cents', sa.BigInteger(), server_default=sa.text("'0'::bigint"), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sn_offer_versions'))
    )
    op.create_index(op.f('ix_sn_offer_versions_product_id'), 'sn_offer_versions', ['product_id'], unique=False)
    op.create_table('sn_one_time_codes',
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('purpose', sa.String(length=32), nullable=False),
    sa.Column('code_hash', sa.String(length=64), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sn_one_time_codes'))
    )
    op.create_index(op.f('ix_sn_one_time_codes_code_hash'), 'sn_one_time_codes', ['code_hash'], unique=False)
    op.create_index(op.f('ix_sn_one_time_codes_purpose'), 'sn_one_time_codes', ['purpose'], unique=False)
    op.create_index(op.f('ix_sn_one_time_codes_user_id'), 'sn_one_time_codes', ['user_id'], unique=False)
    op.create_table('sn_password_recoveries',
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sn_password_recoveries'))
    )
    op.create_index(op.f('ix_sn_password_recoveries_token_hash'), 'sn_password_recoveries', ['token_hash'], unique=True)
    op.create_index(op.f('ix_sn_password_recoveries_user_id'), 'sn_password_recoveries', ['user_id'], unique=False)
    op.create_table('sn_payout_rules',
    sa.Column('commission_plan_version_id', sa.UUID(), nullable=False),
    sa.Column('rule_type', sa.String(length=64), nullable=False),
    sa.Column('parameters', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('valid_from', sa.DateTime(timezone=True), nullable=False),
    sa.Column('valid_to', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sn_payout_rules'))
    )
    op.create_index(op.f('ix_sn_payout_rules_commission_plan_version_id'), 'sn_payout_rules', ['commission_plan_version_id'], unique=False)
    op.create_table('sn_promoter_profiles',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=True),
    sa.Column('display_name', sa.String(length=255), nullable=False),
    sa.Column('first_name', sa.String(length=120), nullable=True),
    sa.Column('last_name', sa.String(length=120), nullable=True),
    sa.Column('promoter_code', sa.String(length=32), nullable=False),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('photo_url', sa.String(length=1000), nullable=True),
    sa.Column('joined_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('current_rank_id', sa.UUID(), nullable=True),
    sa.Column('approved_by_user_id', sa.UUID(), nullable=True),
    sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('rejection_reason', sa.String(length=500), nullable=True),
    sa.Column('is_blacklisted', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('collaboration_contract_version', sa.String(length=32), nullable=True),
    sa.Column('collaboration_accepted_documents', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('collaboration_accepted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('collaboration_otp_verified_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sn_promoter_profiles')),
    sa.UniqueConstraint('organization_id', 'promoter_code', name='uq_sn_invite_codes_agent')
    )
    op.create_index(op.f('ix_sn_promoter_profiles_organization_id'), 'sn_promoter_profiles', ['organization_id'], unique=False)
    op.create_table('sn_receipt_claims',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('customer_user_id', sa.UUID(), nullable=False),
    sa.Column('partner_id', sa.UUID(), nullable=False),
    sa.Column('storage_key', sa.String(length=500), nullable=False),
    sa.Column('original_filename', sa.String(length=255), nullable=False),
    sa.Column('content_type', sa.String(length=100), nullable=False),
    sa.Column('size_bytes', sa.BigInteger(), nullable=False),
    sa.Column('declared_amount_cents', sa.BigInteger(), nullable=False),
    sa.Column('confirmed_amount_cents', sa.BigInteger(), nullable=True),
    sa.Column('payment_reference_code', sa.String(length=32), nullable=True),
    sa.Column('status', sa.String(length=16), server_default=sa.text("'SUBMITTED'::character varying"), nullable=False),
    sa.Column('rejection_reason', sa.String(length=500), nullable=True),
    sa.Column('payment_method', sa.String(length=16), nullable=True),
    sa.Column('stripe_checkout_session_id', sa.String(length=255), nullable=True),
    sa.Column('payment_proof_storage_key', sa.String(length=500), nullable=True),
    sa.Column('payment_proof_original_filename', sa.String(length=255), nullable=True),
    sa.Column('payment_proof_uploaded_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('verified_by_user_id', sa.UUID(), nullable=True),
    sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('credited_by_user_id', sa.UUID(), nullable=True),
    sa.Column('credited_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint('confirmed_amount_cents IS NULL OR confirmed_amount_cents > 0', name=op.f('ck_sn_receipt_claims_confirmed_amount_positive')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sn_receipt_claims')),
    sa.UniqueConstraint('payment_reference_code', name=op.f('uq_sn_receipt_claims_payment_reference_code')),
    sa.UniqueConstraint('storage_key', name=op.f('uq_sn_receipt_claims_storage_key')),
    sa.UniqueConstraint('stripe_checkout_session_id', name=op.f('uq_sn_receipt_claims_stripe_checkout_session_id'))
    )
    op.create_index(op.f('ix_sn_receipt_claims_customer_user_id'), 'sn_receipt_claims', ['customer_user_id'], unique=False)
    op.create_index(op.f('ix_sn_receipt_claims_organization_id'), 'sn_receipt_claims', ['organization_id'], unique=False)
    op.create_index(op.f('ix_sn_receipt_claims_status'), 'sn_receipt_claims', ['status'], unique=False)
    op.create_table('sn_role_grants',
    sa.Column('role_id', sa.UUID(), nullable=False),
    sa.Column('permission_id', sa.UUID(), nullable=False),
    sa.PrimaryKeyConstraint('role_id', 'permission_id', name=op.f('pk_sn_role_grants'))
    )
    op.create_table('sn_shopify_items',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('shopify_product_id', sa.String(length=128), nullable=False),
    sa.Column('handle', sa.String(length=255), nullable=True),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('source_title', sa.String(length=500), nullable=True),
    sa.Column('vendor', sa.String(length=255), nullable=True),
    sa.Column('description', sa.String(length=8000), server_default=sa.text("''::character varying"), nullable=False),
    sa.Column('image_url', sa.String(length=1000), nullable=True),
    sa.Column('images', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
    sa.Column('status', sa.String(length=16), server_default=sa.text("'ACTIVE'::character varying"), nullable=False),
    sa.Column('credit_discount_percentage', sa.Integer(), server_default=sa.text('30'), nullable=False),
    sa.Column('markup_percentage', sa.Integer(), nullable=True),
    sa.Column('last_synced_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('sync_error', sa.String(length=500), nullable=True),
    sa.Column('created_by_user_id', sa.UUID(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('credit_discount_percentage >= 0 AND credit_discount_percentage <= 99', name=op.f('ck_sn_shopify_items_credit_discount_percentage_below_100')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sn_shopify_items')),
    sa.UniqueConstraint('organization_id', 'shopify_product_id', name=op.f('uq_sn_shopify_items_organization_id'))
    )
    op.create_index(op.f('ix_sn_shopify_items_organization_id'), 'sn_shopify_items', ['organization_id'], unique=False)
    op.create_index(op.f('ix_sn_shopify_items_status'), 'sn_shopify_items', ['status'], unique=False)
    op.create_table('sn_supplier_sources',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('provider_type', sa.String(length=32), nullable=False),
    sa.Column('name', sa.String(length=128), nullable=False),
    sa.Column('base_url', sa.String(length=500), nullable=True),
    sa.Column('api_key', sa.String(length=500), nullable=True),
    sa.Column('enabled', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('created_by_user_id', sa.UUID(), nullable=False),
    sa.Column('app_key', sa.String(length=64), nullable=True),
    sa.Column('app_secret', sa.String(length=255), nullable=True),
    sa.Column('access_token', sa.String(length=500), nullable=True),
    sa.Column('refresh_token', sa.String(length=500), nullable=True),
    sa.Column('token_expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('account_label', sa.String(length=255), nullable=True),
    sa.Column('last_connected_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sn_supplier_sources'))
    )
    op.create_index(op.f('ix_sn_supplier_sources_organization_id'), 'sn_supplier_sources', ['organization_id'], unique=False)
    op.create_table('sn_agreement_attributions',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('producer_agent_id', sa.UUID(), nullable=False),
    sa.Column('attributed_promoter_id', sa.UUID(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sn_agreement_attributions'))
    )
    op.create_index(op.f('ix_sn_agreement_attributions_organization_id'), 'sn_agreement_attributions', ['organization_id'], unique=False)
    op.create_table('sn_agreement_requests',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('customer_id', sa.UUID(), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('holder_first_name', sa.String(length=128), nullable=True),
    sa.Column('holder_last_name', sa.String(length=128), nullable=True),
    sa.Column('email', sa.String(length=320), nullable=True),
    sa.Column('pec', sa.String(length=320), nullable=True),
    sa.Column('iban', sa.String(length=34), nullable=True),
    sa.Column('street', sa.String(length=255), nullable=True),
    sa.Column('city', sa.String(length=128), nullable=True),
    sa.Column('province', sa.String(length=8), nullable=True),
    sa.Column('postal_code', sa.String(length=16), nullable=True),
    sa.Column('created_by_user_id', sa.UUID(), nullable=True),
    sa.Column('created_by_role', sa.String(length=32), nullable=True),
    sa.Column('activated_by_promoter_id', sa.UUID(), nullable=True),
    sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('cancelled_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('bank_transfer_requested_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('bank_transfer_total_cents', sa.BigInteger(), nullable=True),
    sa.Column('bank_transfer_confirmed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('bank_transfer_confirmed_by_user_id', sa.UUID(), nullable=True),
    sa.Column('payment_proof_storage_key', sa.String(length=500), nullable=True),
    sa.Column('payment_proof_original_filename', sa.String(length=255), nullable=True),
    sa.Column('payment_proof_uploaded_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sn_agreement_requests'))
    )
    op.create_index(op.f('ix_sn_agreement_requests_customer_id'), 'sn_agreement_requests', ['customer_id'], unique=False)
    op.create_index(op.f('ix_sn_agreement_requests_organization_id'), 'sn_agreement_requests', ['organization_id'], unique=False)
    op.create_index(op.f('ix_sn_agreement_requests_status'), 'sn_agreement_requests', ['status'], unique=False)
    op.create_table('sn_aliexpress_item_variants',
    sa.Column('product_id', sa.UUID(), nullable=False),
    sa.Column('aliexpress_sku_id', sa.String(length=128), nullable=False),
    sa.Column('sku_attr', sa.String(length=500), nullable=True),
    sa.Column('sku', sa.String(length=128), nullable=True),
    sa.Column('label', sa.String(length=255), server_default=sa.text("''::character varying"), nullable=False),
    sa.Column('image_url', sa.String(length=1000), nullable=True),
    sa.Column('cost_amount', sa.Numeric(precision=12, scale=2), nullable=True),
    sa.Column('source_price_amount', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('price_cents', sa.BigInteger(), nullable=False),
    sa.Column('price_override_cents', sa.BigInteger(), nullable=True),
    sa.Column('inventory', sa.Integer(), nullable=True),
    sa.Column('active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('available_in_store', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('last_synced_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sn_aliexpress_item_variants')),
    sa.UniqueConstraint('product_id', 'aliexpress_sku_id', name=op.f('uq_sn_aliexpress_item_variants_product_id'))
    )
    op.create_index(op.f('ix_sn_aliexpress_item_variants_product_id'), 'sn_aliexpress_item_variants', ['product_id'], unique=False)
    op.create_table('sn_businesses',
    sa.Column('customer_id', sa.UUID(), nullable=False),
    sa.Column('company_name', sa.String(length=255), nullable=False),
    sa.Column('legal_form', sa.String(length=64), nullable=True),
    sa.Column('sdi_code', sa.String(length=16), nullable=True),
    sa.PrimaryKeyConstraint('customer_id', name=op.f('pk_sn_businesses'))
    )
    op.create_table('sn_cj_item_variants',
    sa.Column('product_id', sa.UUID(), nullable=False),
    sa.Column('cj_vid', sa.String(length=64), nullable=False),
    sa.Column('cj_sku', sa.String(length=128), nullable=True),
    sa.Column('label', sa.String(length=255), server_default=sa.text("''::character varying"), nullable=False),
    sa.Column('image_url', sa.String(length=1000), nullable=True),
    sa.Column('cost_usd', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.Column('weight_g', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('price_cents', sa.BigInteger(), nullable=False),
    sa.Column('price_override_cents', sa.BigInteger(), nullable=True),
    sa.Column('inventory', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('available_on_cj', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('last_synced_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sn_cj_item_variants')),
    sa.UniqueConstraint('product_id', 'cj_vid', name=op.f('uq_sn_cj_item_variants_product_id'))
    )
    op.create_index(op.f('ix_sn_cj_item_variants_product_id'), 'sn_cj_item_variants', ['product_id'], unique=False)
    op.create_table('sn_client_profiles',
    sa.Column('customer_id', sa.UUID(), nullable=False),
    sa.Column('first_name', sa.String(length=128), nullable=False),
    sa.Column('last_name', sa.String(length=128), nullable=False),
    sa.PrimaryKeyConstraint('customer_id', name=op.f('pk_sn_client_profiles'))
    )
    op.create_table('sn_friend_invites',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('referrer_user_id', sa.UUID(), nullable=False),
    sa.Column('referred_customer_id', sa.UUID(), nullable=False),
    sa.Column('code_used', sa.String(length=32), nullable=False),
    sa.Column('source', sa.String(length=16), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sn_friend_invites')),
    sa.UniqueConstraint('referred_customer_id', name='uq_sn_friend_invites_referred_customer_id')
    )
    op.create_index(op.f('ix_sn_friend_invites_organization_id'), 'sn_friend_invites', ['organization_id'], unique=False)
    op.create_index(op.f('ix_sn_friend_invites_referrer_user_id'), 'sn_friend_invites', ['referrer_user_id'], unique=False)
    op.create_table('sn_invite_codes',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('agent_id', sa.UUID(), nullable=False),
    sa.Column('code', sa.String(length=32), nullable=False),
    sa.Column('personal_link', sa.String(length=500), nullable=False),
    sa.Column('qr_code_url', sa.String(length=500), nullable=True),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('valid_from', sa.DateTime(timezone=True), nullable=False),
    sa.Column('valid_to', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sn_invite_codes'))
    )
    op.create_index(op.f('ix_sn_invite_codes_agent_id'), 'sn_invite_codes', ['agent_id'], unique=False)
    op.create_index(op.f('ix_sn_invite_codes_code'), 'sn_invite_codes', ['code'], unique=True)
    op.create_index(op.f('ix_sn_invite_codes_organization_id'), 'sn_invite_codes', ['organization_id'], unique=False)
    op.create_table('sn_market_items',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('producer_id', sa.UUID(), nullable=True),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('description', sa.String(length=8000), server_default=sa.text("''::character varying"), nullable=False),
    sa.Column('image_url', sa.String(length=1000), nullable=True),
    sa.Column('images', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
    sa.Column('status', sa.String(length=16), server_default=sa.text("'ACTIVE'::character varying"), nullable=False),
    sa.Column('credit_discount_percentage', sa.Integer(), server_default=sa.text('30'), nullable=False),
    sa.Column('unit_cost_cents', sa.BigInteger(), nullable=True),
    sa.Column('created_by_user_id', sa.UUID(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint('credit_discount_percentage BETWEEN 0 AND 99', name=op.f('ck_sn_market_items_credit_percentage_range')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sn_market_items'))
    )
    op.create_index(op.f('ix_sn_market_items_organization_id'), 'sn_market_items', ['organization_id'], unique=False)
    op.create_index(op.f('ix_sn_market_items_producer_id'), 'sn_market_items', ['producer_id'], unique=False)
    op.create_index(op.f('ix_sn_market_items_status'), 'sn_market_items', ['status'], unique=False)
    op.create_table('sn_postal_addresses',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('customer_id', sa.UUID(), nullable=False),
    sa.Column('kind', sa.String(length=32), nullable=False),
    sa.Column('street', sa.String(length=255), nullable=False),
    sa.Column('city', sa.String(length=128), nullable=False),
    sa.Column('province', sa.String(length=8), nullable=False),
    sa.Column('postal_code', sa.String(length=16), nullable=False),
    sa.Column('country', sa.String(length=2), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sn_postal_addresses'))
    )
    op.create_index(op.f('ix_sn_postal_addresses_customer_id'), 'sn_postal_addresses', ['customer_id'], unique=False)
    op.create_index(op.f('ix_sn_postal_addresses_organization_id'), 'sn_postal_addresses', ['organization_id'], unique=False)
    op.create_table('sn_promoter_level_log',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('agent_id', sa.UUID(), nullable=False),
    sa.Column('rank_id', sa.UUID(), nullable=False),
    sa.Column('effective_from', sa.DateTime(timezone=True), nullable=False),
    sa.Column('effective_to', sa.DateTime(timezone=True), nullable=True),
    sa.Column('calculation_source', sa.String(length=32), nullable=False),
    sa.Column('rule_version_id', sa.String(length=32), nullable=False),
    sa.Column('approved_by', sa.UUID(), nullable=True),
    sa.Column('reason', sa.String(length=500), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sn_promoter_level_log'))
    )
    op.create_index(op.f('ix_sn_promoter_level_log_agent_id'), 'sn_promoter_level_log', ['agent_id'], unique=False)
    op.create_index(op.f('ix_sn_promoter_level_log_organization_id'), 'sn_promoter_level_log', ['organization_id'], unique=False)
    op.create_table('sn_shopify_item_variants',
    sa.Column('product_id', sa.UUID(), nullable=False),
    sa.Column('shopify_variant_id', sa.String(length=128), nullable=False),
    sa.Column('sku', sa.String(length=128), nullable=True),
    sa.Column('label', sa.String(length=255), server_default=sa.text("''::character varying"), nullable=False),
    sa.Column('image_url', sa.String(length=1000), nullable=True),
    sa.Column('cost_amount', sa.Numeric(precision=12, scale=2), nullable=True),
    sa.Column('source_price_amount', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('price_cents', sa.BigInteger(), nullable=False),
    sa.Column('price_override_cents', sa.BigInteger(), nullable=True),
    sa.Column('inventory', sa.Integer(), nullable=True),
    sa.Column('active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('available_in_store', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('last_synced_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sn_shopify_item_variants')),
    sa.UniqueConstraint('product_id', 'shopify_variant_id', name=op.f('uq_sn_shopify_item_variants_product_id'))
    )
    op.create_index(op.f('ix_sn_shopify_item_variants_product_id'), 'sn_shopify_item_variants', ['product_id'], unique=False)
    op.create_table('sn_supplier_items',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('provider_id', sa.UUID(), nullable=False),
    sa.Column('external_id', sa.String(length=255), nullable=True),
    sa.Column('external_url', sa.String(length=1000), nullable=True),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('description', sa.String(length=2000), server_default=sa.text("''::character varying"), nullable=False),
    sa.Column('image_url', sa.String(length=1000), nullable=True),
    sa.Column('price_cents', sa.BigInteger(), nullable=False),
    sa.Column('credit_discount_percentage', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('status', sa.String(length=16), server_default=sa.text("'ACTIVE'::character varying"), nullable=False),
    sa.Column('created_by_user_id', sa.UUID(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint('credit_discount_percentage BETWEEN 0 AND 99', name=op.f('ck_sn_supplier_items_credit_below_100')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sn_supplier_items'))
    )
    op.create_index(op.f('ix_sn_supplier_items_organization_id'), 'sn_supplier_items', ['organization_id'], unique=False)
    op.create_index(op.f('ix_sn_supplier_items_provider_id'), 'sn_supplier_items', ['provider_id'], unique=False)
    op.create_table('sn_tree_links',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('parent_agent_id', sa.UUID(), nullable=False),
    sa.Column('child_agent_id', sa.UUID(), nullable=False),
    sa.Column('effective_from', sa.DateTime(timezone=True), nullable=False),
    sa.Column('effective_to', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sn_tree_links'))
    )
    op.create_index(op.f('ix_sn_tree_links_child_agent_id'), 'sn_tree_links', ['child_agent_id'], unique=False)
    op.create_index(op.f('ix_sn_tree_links_organization_id'), 'sn_tree_links', ['organization_id'], unique=False)
    op.create_index(op.f('ix_sn_tree_links_parent_agent_id'), 'sn_tree_links', ['parent_agent_id'], unique=False)
    op.create_table('sn_tree_moves',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('agent_id', sa.UUID(), nullable=False),
    sa.Column('old_parent_agent_id', sa.UUID(), nullable=True),
    sa.Column('new_parent_agent_id', sa.UUID(), nullable=True),
    sa.Column('requested_by', sa.UUID(), nullable=False),
    sa.Column('approved_by', sa.UUID(), nullable=True),
    sa.Column('reason', sa.String(length=500), nullable=False),
    sa.Column('effective_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sn_tree_moves'))
    )
    op.create_index(op.f('ix_sn_tree_moves_organization_id'), 'sn_tree_moves', ['organization_id'], unique=False)
    op.create_table('sn_tree_nodes',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('agent_id', sa.UUID(), nullable=False),
    sa.Column('direct_parent_agent_id', sa.UUID(), nullable=True),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('effective_from', sa.DateTime(timezone=True), nullable=False),
    sa.Column('effective_to', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sn_tree_nodes'))
    )
    op.create_index(op.f('ix_sn_tree_nodes_agent_id'), 'sn_tree_nodes', ['agent_id'], unique=False)
    op.create_index(op.f('ix_sn_tree_nodes_organization_id'), 'sn_tree_nodes', ['organization_id'], unique=False)
    op.create_index('uq_sn_tree_nodes_active_agent', 'sn_tree_nodes', ['organization_id', 'agent_id'], unique=True, postgresql_where=sa.text('effective_to IS NULL'))
    op.create_table('sn_tree_paths',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('ancestor_agent_id', sa.UUID(), nullable=False),
    sa.Column('descendant_agent_id', sa.UUID(), nullable=False),
    sa.Column('effective_from', sa.DateTime(timezone=True), nullable=False),
    sa.Column('depth', sa.Integer(), nullable=False),
    sa.Column('effective_to', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('organization_id', 'ancestor_agent_id', 'descendant_agent_id', 'effective_from', name=op.f('pk_sn_tree_paths'))
    )
    op.create_index('ix_sn_tree_paths_org_ancestor', 'sn_tree_paths', ['organization_id', 'ancestor_agent_id'], unique=False)
    op.create_index('ix_sn_tree_paths_org_ancestor_depth', 'sn_tree_paths', ['organization_id', 'ancestor_agent_id', 'depth'], unique=False)
    op.create_index('ix_sn_tree_paths_org_descendant', 'sn_tree_paths', ['organization_id', 'descendant_agent_id'], unique=False)
    op.create_index('ix_sn_tree_paths_org_descendant_depth', 'sn_tree_paths', ['organization_id', 'descendant_agent_id', 'depth'], unique=False)
    op.create_table('sn_tree_snapshot_nodes',
    sa.Column('snapshot_id', sa.UUID(), nullable=False),
    sa.Column('ancestor_agent_id', sa.UUID(), nullable=False),
    sa.Column('depth', sa.Integer(), nullable=False),
    sa.Column('rank_id_at_snapshot', sa.UUID(), nullable=True),
    sa.PrimaryKeyConstraint('snapshot_id', 'ancestor_agent_id', name=op.f('pk_sn_tree_snapshot_nodes'))
    )
    op.create_table('sn_agreement_checkouts',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('contract_request_id', sa.UUID(), nullable=False),
    sa.Column('stripe_checkout_session_id', sa.String(length=255), nullable=False),
    sa.Column('payment_plan', sa.String(length=16), nullable=False),
    sa.Column('lines', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('total_cents', sa.BigInteger(), nullable=False),
    sa.Column('instalment_cents', sa.BigInteger(), nullable=False),
    sa.Column('created_by_user_id', sa.UUID(), nullable=True),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('stripe_subscription_id', sa.String(length=255), nullable=True),
    sa.Column('stripe_customer_id', sa.String(length=255), nullable=True),
    sa.Column('outcome', sa.String(length=255), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sn_agreement_checkouts')),
    sa.UniqueConstraint('stripe_checkout_session_id', name=op.f('uq_sn_agreement_checkouts_stripe_checkout_session_id'))
    )
    op.create_index(op.f('ix_sn_agreement_checkouts_contract_request_id'), 'sn_agreement_checkouts', ['contract_request_id'], unique=False)
    op.create_index(op.f('ix_sn_agreement_checkouts_organization_id'), 'sn_agreement_checkouts', ['organization_id'], unique=False)
    op.create_table('sn_aliexpress_order_lines',
    sa.Column('order_id', sa.UUID(), nullable=False),
    sa.Column('aliexpress_product_id', sa.UUID(), nullable=False),
    sa.Column('aliexpress_variant_id', sa.UUID(), nullable=False),
    sa.Column('quantity', sa.Integer(), nullable=False),
    sa.Column('unit_price_cents', sa.BigInteger(), nullable=False),
    sa.Column('unit_cost_amount', sa.Numeric(precision=12, scale=2), nullable=True),
    sa.Column('supplier_shipping_cents', sa.BigInteger(), nullable=True),
    sa.Column('product_name', sa.String(length=255), nullable=False),
    sa.Column('variant_label', sa.String(length=255), nullable=True),
    sa.Column('credit_discount_percentage', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('aliexpress_order_id', sa.String(length=128), nullable=True),
    sa.Column('tracking_number', sa.String(length=128), nullable=True),
    sa.Column('tracking_url', sa.String(length=1000), nullable=True),
    sa.Column('tracking_company', sa.String(length=128), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint('quantity > 0', name=op.f('ck_sn_aliexpress_order_lines_quantity_positive')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sn_aliexpress_order_lines')),
    sa.UniqueConstraint('order_id', 'aliexpress_variant_id', name='uq_sn_aliexpress_order_lines_variant')
    )
    op.create_index(op.f('ix_sn_aliexpress_order_lines_aliexpress_order_id'), 'sn_aliexpress_order_lines', ['aliexpress_order_id'], unique=False)
    op.create_index(op.f('ix_sn_aliexpress_order_lines_order_id'), 'sn_aliexpress_order_lines', ['order_id'], unique=False)
    op.create_table('sn_cj_order_lines',
    sa.Column('order_id', sa.UUID(), nullable=False),
    sa.Column('product_id', sa.UUID(), nullable=False),
    sa.Column('variant_id', sa.UUID(), nullable=False),
    sa.Column('quantity', sa.Integer(), nullable=False),
    sa.Column('unit_price_cents', sa.BigInteger(), nullable=False),
    sa.Column('product_name', sa.String(length=255), nullable=False),
    sa.Column('variant_label', sa.String(length=255), nullable=True),
    sa.Column('credit_discount_percentage', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('supplier_order_id', sa.String(length=128), nullable=True),
    sa.Column('tracking_number', sa.String(length=128), nullable=True),
    sa.Column('tracking_url', sa.String(length=1000), nullable=True),
    sa.Column('tracking_company', sa.String(length=128), nullable=True),
    sa.Column('unit_cost_usd', sa.Numeric(precision=12, scale=2), nullable=True),
    sa.Column('origin_country', sa.String(length=8), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint('quantity > 0', name=op.f('ck_sn_cj_order_lines_quantity_positive')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sn_cj_order_lines')),
    sa.UniqueConstraint('order_id', 'variant_id', name='uq_sn_cj_order_lines_variant')
    )
    op.create_index(op.f('ix_sn_cj_order_lines_order_id'), 'sn_cj_order_lines', ['order_id'], unique=False)
    op.create_table('sn_invite_events',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('promoter_code_id', sa.UUID(), nullable=False),
    sa.Column('ip_address', sa.String(length=64), nullable=True),
    sa.Column('user_agent', sa.String(length=255), nullable=True),
    sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sn_invite_events'))
    )
    op.create_index(op.f('ix_sn_invite_events_organization_id'), 'sn_invite_events', ['organization_id'], unique=False)
    op.create_index(op.f('ix_sn_invite_events_promoter_code_id'), 'sn_invite_events', ['promoter_code_id'], unique=False)
    op.create_table('sn_invite_visits',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('promoter_code_id', sa.UUID(), nullable=False),
    sa.Column('cookie_token_hash', sa.String(length=64), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sn_invite_visits'))
    )
    op.create_index(op.f('ix_sn_invite_visits_cookie_token_hash'), 'sn_invite_visits', ['cookie_token_hash'], unique=True)
    op.create_index(op.f('ix_sn_invite_visits_organization_id'), 'sn_invite_visits', ['organization_id'], unique=False)
    op.create_index(op.f('ix_sn_invite_visits_promoter_code_id'), 'sn_invite_visits', ['promoter_code_id'], unique=False)
    op.create_table('sn_market_item_variants',
    sa.Column('product_id', sa.UUID(), nullable=False),
    sa.Column('label', sa.String(length=255), server_default=sa.text("'Unica'::character varying"), nullable=False),
    sa.Column('sku', sa.String(length=128), nullable=True),
    sa.Column('image_url', sa.String(length=1000), nullable=True),
    sa.Column('price_cents', sa.BigInteger(), nullable=False),
    sa.Column('inventory', sa.Integer(), nullable=True),
    sa.Column('active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint('price_cents > 0', name=op.f('ck_sn_market_item_variants_price_positive')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sn_market_item_variants')),
    sa.UniqueConstraint('product_id', 'sku', name='uq_sn_market_item_variants_sku')
    )
    op.create_index(op.f('ix_sn_market_item_variants_product_id'), 'sn_market_item_variants', ['product_id'], unique=False)
    op.create_table('sn_shopify_order_lines',
    sa.Column('order_id', sa.UUID(), nullable=False),
    sa.Column('product_id', sa.UUID(), nullable=False),
    sa.Column('variant_id', sa.UUID(), nullable=False),
    sa.Column('quantity', sa.Integer(), nullable=False),
    sa.Column('unit_price_cents', sa.BigInteger(), nullable=False),
    sa.Column('product_name', sa.String(length=255), nullable=False),
    sa.Column('variant_label', sa.String(length=255), nullable=True),
    sa.Column('credit_discount_percentage', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('supplier_order_id', sa.String(length=128), nullable=True),
    sa.Column('tracking_number', sa.String(length=128), nullable=True),
    sa.Column('tracking_url', sa.String(length=1000), nullable=True),
    sa.Column('tracking_company', sa.String(length=128), nullable=True),
    sa.Column('unit_cost_amount', sa.Numeric(precision=12, scale=2), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint('quantity > 0', name=op.f('ck_sn_shopify_order_lines_quantity_positive')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sn_shopify_order_lines')),
    sa.UniqueConstraint('order_id', 'variant_id', name='uq_sn_shopify_order_lines_variant')
    )
    op.create_index(op.f('ix_sn_shopify_order_lines_order_id'), 'sn_shopify_order_lines', ['order_id'], unique=False)
    op.create_table('sn_utility_points',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('customer_id', sa.UUID(), nullable=False),
    sa.Column('label', sa.String(length=255), nullable=True),
    sa.Column('energy_type', sa.String(length=16), nullable=True),
    sa.Column('pod_code', sa.String(length=32), nullable=True),
    sa.Column('pdr_code', sa.String(length=32), nullable=True),
    sa.Column('meter_number', sa.String(length=64), nullable=True),
    sa.Column('supply_address_id', sa.UUID(), nullable=False),
    sa.Column('estimated_consumption', sa.BigInteger(), nullable=True),
    sa.Column('actual_consumption', sa.BigInteger(), nullable=True),
    sa.Column('provider_reference', sa.String(length=128), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sn_utility_points'))
    )
    op.create_index(op.f('ix_sn_utility_points_customer_id'), 'sn_utility_points', ['customer_id'], unique=False)
    op.create_index(op.f('ix_sn_utility_points_organization_id'), 'sn_utility_points', ['organization_id'], unique=False)
    op.create_table('sn_agreements',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('customer_id', sa.UUID(), nullable=False),
    sa.Column('contract_request_id', sa.UUID(), nullable=False),
    sa.Column('supply_point_id', sa.UUID(), nullable=False),
    sa.Column('product_version_id', sa.UUID(), nullable=True),
    sa.Column('contract_attribution_id', sa.UUID(), nullable=True),
    sa.Column('network_snapshot_id', sa.UUID(), nullable=True),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('notes', sa.String(length=2000), nullable=True),
    sa.Column('iban', sa.String(length=34), nullable=True),
    sa.Column('email', sa.String(length=320), nullable=True),
    sa.Column('holder_first_name', sa.String(length=128), nullable=True),
    sa.Column('holder_last_name', sa.String(length=128), nullable=True),
    sa.Column('pec', sa.String(length=320), nullable=True),
    sa.Column('activated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_by_user_id', sa.UUID(), nullable=True),
    sa.Column('created_by_role', sa.String(length=32), nullable=True),
    sa.Column('activated_by_promoter_id', sa.UUID(), nullable=True),
    sa.Column('first_referrer_agent_id', sa.UUID(), nullable=True),
    sa.Column('customer_kind', sa.String(length=32), nullable=True),
    sa.Column('net_amount_cents', sa.BigInteger(), nullable=True),
    sa.Column('vat_rate', sa.Numeric(precision=5, scale=2), nullable=True),
    sa.Column('vat_amount_cents', sa.BigInteger(), nullable=True),
    sa.Column('gross_amount_cents', sa.BigInteger(), nullable=True),
    sa.Column('payment_plan', sa.String(length=16), nullable=True),
    sa.Column('payment_discount_cents', sa.Integer(), server_default='0', nullable=False),
    sa.Column('payment_method', sa.String(length=16), nullable=True),
    sa.Column('stripe_checkout_session_id', sa.String(length=255), nullable=True),
    sa.Column('stripe_customer_id', sa.String(length=255), nullable=True),
    sa.Column('stripe_subscription_id', sa.String(length=255), nullable=True),
    sa.Column('stripe_subscription_item_id', sa.String(length=255), nullable=True),
    sa.Column('billing_stopped_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('paid_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('cashback_credited_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('terms_accepted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('terms_accepted_by_user_id', sa.UUID(), nullable=True),
    sa.Column('terms_version', sa.String(length=32), nullable=True),
    sa.Column('terms_accepted_ip', sa.String(length=45), nullable=True),
    sa.Column('terms_accepted_user_agent', sa.String(length=500), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("product_version_id IS NOT NULL OR status IN ('DRAFT', 'CANCELLED')", name=op.f('ck_sn_agreements_product_required')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sn_agreements')),
    sa.UniqueConstraint('stripe_checkout_session_id', name=op.f('uq_sn_agreements_stripe_checkout_session_id')),
    sa.UniqueConstraint('stripe_subscription_item_id', name=op.f('uq_sn_agreements_stripe_subscription_item_id'))
    )
    op.create_index(op.f('ix_sn_agreements_contract_request_id'), 'sn_agreements', ['contract_request_id'], unique=False)
    op.create_index(op.f('ix_sn_agreements_customer_id'), 'sn_agreements', ['customer_id'], unique=False)
    op.create_index(op.f('ix_sn_agreements_expires_at'), 'sn_agreements', ['expires_at'], unique=False)
    op.create_index(op.f('ix_sn_agreements_organization_id'), 'sn_agreements', ['organization_id'], unique=False)
    op.create_index(op.f('ix_sn_agreements_status'), 'sn_agreements', ['status'], unique=False)
    op.create_table('sn_basket_lines',
    sa.Column('cart_id', sa.UUID(), nullable=False),
    sa.Column('quantity', sa.BigInteger(), nullable=False),
    sa.Column('aliexpress_variant_id', sa.UUID(), nullable=True),
    sa.Column('cj_variant_id', sa.UUID(), nullable=True),
    sa.Column('shopify_variant_id', sa.UUID(), nullable=True),
    sa.Column('sosnet_market_variant_id', sa.UUID(), nullable=True),
    sa.Column('product_version_id', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint('num_nonnulls(aliexpress_variant_id, cj_variant_id, shopify_variant_id, sosnet_market_variant_id, product_version_id) = 1', name=op.f('ck_sn_basket_lines_exactly_one_reference')),
    sa.CheckConstraint('quantity <= 99', name=op.f('ck_sn_basket_lines_quantity_max')),
    sa.CheckConstraint('quantity > 0', name=op.f('ck_sn_basket_lines_quantity_positive')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sn_basket_lines')),
    sa.UniqueConstraint('cart_id', 'sosnet_market_variant_id', name='uq_sn_basket_lines_sosnet_market_variant'),
    sa.UniqueConstraint('cart_id', 'aliexpress_variant_id', name='uq_sn_basket_lines_aliexpress_variant'),
    sa.UniqueConstraint('cart_id', 'cj_variant_id', name='uq_sn_basket_lines_cj_variant'),
    sa.UniqueConstraint('cart_id', 'product_version_id', name='uq_sn_basket_lines_product_version'),
    sa.UniqueConstraint('cart_id', 'shopify_variant_id', name='uq_sn_basket_lines_shopify_variant')
    )
    op.create_index(op.f('ix_sn_basket_lines_cart_id'), 'sn_basket_lines', ['cart_id'], unique=False)
    op.create_table('sn_client_attributions',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('customer_id', sa.UUID(), nullable=False),
    sa.Column('promoter_code_id', sa.UUID(), nullable=False),
    sa.Column('referral_session_id', sa.UUID(), nullable=True),
    sa.Column('attributed_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sn_client_attributions'))
    )
    op.create_index(op.f('ix_sn_client_attributions_customer_id'), 'sn_client_attributions', ['customer_id'], unique=False)
    op.create_index(op.f('ix_sn_client_attributions_organization_id'), 'sn_client_attributions', ['organization_id'], unique=False)
    op.create_table('sn_market_order_lines',
    sa.Column('order_id', sa.UUID(), nullable=False),
    sa.Column('product_id', sa.UUID(), nullable=False),
    sa.Column('variant_id', sa.UUID(), nullable=False),
    sa.Column('quantity', sa.Integer(), nullable=False),
    sa.Column('unit_price_cents', sa.BigInteger(), nullable=False),
    sa.Column('unit_cost_cents', sa.BigInteger(), nullable=True),
    sa.Column('product_name', sa.String(length=255), nullable=False),
    sa.Column('variant_label', sa.String(length=255), nullable=True),
    sa.Column('producer_name', sa.String(length=160), nullable=True),
    sa.Column('credit_discount_percentage', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint('quantity > 0', name=op.f('ck_sn_market_order_lines_quantity_positive')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sn_market_order_lines')),
    sa.UniqueConstraint('order_id', 'variant_id', name='uq_sn_market_order_lines_variant')
    )
    op.create_index(op.f('ix_sn_market_order_lines_order_id'), 'sn_market_order_lines', ['order_id'], unique=False)
    op.create_table('sn_agreement_events',
    sa.Column('contract_id', sa.UUID(), nullable=False),
    sa.Column('event_type', sa.String(length=64), nullable=False),
    sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sn_agreement_events'))
    )
    op.create_index(op.f('ix_sn_agreement_events_contract_id'), 'sn_agreement_events', ['contract_id'], unique=False)
    op.create_table('sn_agreement_payout_plans',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('contract_id', sa.UUID(), nullable=False),
    sa.Column('accepted_by_user_id', sa.UUID(), nullable=False),
    sa.Column('accepted_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('payment_plan', sa.String(length=16), nullable=True),
    sa.Column('total_commission_cents', sa.BigInteger(), nullable=False),
    sa.Column('preview', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('checksum', sa.String(length=64), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sn_agreement_payout_plans')),
    sa.UniqueConstraint('contract_id', name=op.f('uq_sn_agreement_payout_plans_contract_id'))
    )
    op.create_index(op.f('ix_sn_agreement_payout_plans_organization_id'), 'sn_agreement_payout_plans', ['organization_id'], unique=False)
    op.create_table('sn_agreement_status_log',
    sa.Column('contract_id', sa.UUID(), nullable=False),
    sa.Column('from_status', sa.String(length=32), nullable=True),
    sa.Column('to_status', sa.String(length=32), nullable=False),
    sa.Column('actor_user_id', sa.UUID(), nullable=False),
    sa.Column('reason', sa.String(length=500), nullable=True),
    sa.Column('notes', sa.String(length=2000), nullable=True),
    sa.Column('correlation_id', sa.String(length=64), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sn_agreement_status_log'))
    )
    op.create_index(op.f('ix_sn_agreement_status_log_contract_id'), 'sn_agreement_status_log', ['contract_id'], unique=False)
    op.create_table('sn_attribution_fixes',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('customer_attribution_id', sa.UUID(), nullable=False),
    sa.Column('previous_promoter_code_id', sa.UUID(), nullable=False),
    sa.Column('new_promoter_code_id', sa.UUID(), nullable=False),
    sa.Column('requested_by', sa.UUID(), nullable=False),
    sa.Column('approved_by', sa.UUID(), nullable=True),
    sa.Column('reason', sa.String(length=500), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sn_attribution_fixes'))
    )
    op.create_index(op.f('ix_sn_attribution_fixes_organization_id'), 'sn_attribution_fixes', ['organization_id'], unique=False)
    op.create_table('sn_payout_runs',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('contract_id', sa.UUID(), nullable=False),
    sa.Column('network_snapshot_id', sa.UUID(), nullable=False),
    sa.Column('commission_plan_version_id', sa.UUID(), nullable=True),
    sa.Column('trigger_event_id', sa.UUID(), nullable=False),
    sa.Column('input_snapshot', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('output_snapshot', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('checksum', sa.String(length=64), nullable=False),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sn_payout_runs')),
    sa.UniqueConstraint('contract_id', 'trigger_event_id', name='uq_sn_payout_runs_contract_trigger')
    )
    op.create_index(op.f('ix_sn_payout_runs_contract_id'), 'sn_payout_runs', ['contract_id'], unique=False)
    op.create_index(op.f('ix_sn_payout_runs_organization_id'), 'sn_payout_runs', ['organization_id'], unique=False)
    op.create_table('sn_stored_files',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('contract_id', sa.UUID(), nullable=True),
    sa.Column('contract_request_id', sa.UUID(), nullable=True),
    sa.Column('document_type', sa.String(length=32), nullable=False),
    sa.Column('description', sa.String(length=120), nullable=True),
    sa.Column('original_filename', sa.String(length=255), nullable=False),
    sa.Column('storage_key', sa.String(length=500), nullable=False),
    sa.Column('content_type', sa.String(length=100), nullable=False),
    sa.Column('size_bytes', sa.BigInteger(), nullable=False),
    sa.Column('uploaded_by_user_id', sa.UUID(), nullable=False),
    sa.Column('uploaded_by_role', sa.String(length=32), nullable=False),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('reviewed_by_user_id', sa.UUID(), nullable=True),
    sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('review_note', sa.String(length=1000), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint('num_nonnulls(contract_id, contract_request_id) = 1', name=op.f('ck_sn_stored_files_one_owner')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sn_stored_files')),
    sa.UniqueConstraint('storage_key', name=op.f('uq_sn_stored_files_storage_key'))
    )
    op.create_index(op.f('ix_sn_stored_files_contract_id'), 'sn_stored_files', ['contract_id'], unique=False)
    op.create_index(op.f('ix_sn_stored_files_contract_request_id'), 'sn_stored_files', ['contract_request_id'], unique=False)
    op.create_index(op.f('ix_sn_stored_files_organization_id'), 'sn_stored_files', ['organization_id'], unique=False)
    op.create_index(op.f('ix_sn_stored_files_status'), 'sn_stored_files', ['status'], unique=False)
    op.create_table('sn_support_cases',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('opened_by_user_id', sa.UUID(), nullable=False),
    sa.Column('opened_by_role', sa.String(length=32), nullable=False),
    sa.Column('subject', sa.String(length=255), nullable=False),
    sa.Column('category', sa.String(length=32), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('contract_id', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sn_support_cases'))
    )
    op.create_index(op.f('ix_sn_support_cases_opened_by_user_id'), 'sn_support_cases', ['opened_by_user_id'], unique=False)
    op.create_index(op.f('ix_sn_support_cases_organization_id'), 'sn_support_cases', ['organization_id'], unique=False)
    op.create_index(op.f('ix_sn_support_cases_status'), 'sn_support_cases', ['status'], unique=False)
    op.create_table('sn_agreement_instalments',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('contract_id', sa.UUID(), nullable=False),
    sa.Column('number', sa.Integer(), nullable=False),
    sa.Column('instalments_total', sa.Integer(), nullable=False),
    sa.Column('due_date', sa.Date(), nullable=False),
    sa.Column('amount_cents', sa.BigInteger(), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('paid_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('payment_source', sa.String(length=16), nullable=True),
    sa.Column('confirmed_by_user_id', sa.UUID(), nullable=True),
    sa.Column('stripe_invoice_id', sa.String(length=255), nullable=True),
    sa.Column('commission_event_id', sa.UUID(), nullable=True),
    sa.Column('commission_released_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('commission_calculation_id', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sn_agreement_instalments')),
    sa.UniqueConstraint('contract_id', 'number', name='uq_sn_agreement_instalments_contract_number'),
    sa.UniqueConstraint('contract_id', 'stripe_invoice_id', name=op.f('uq_sn_agreement_instalments_contract_id'))
    )
    op.create_index(op.f('ix_sn_agreement_instalments_contract_id'), 'sn_agreement_instalments', ['contract_id'], unique=False)
    op.create_index(op.f('ix_sn_agreement_instalments_organization_id'), 'sn_agreement_instalments', ['organization_id'], unique=False)
    op.create_table('sn_payout_entries',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('agent_id', sa.UUID(), nullable=False),
    sa.Column('contract_id', sa.UUID(), nullable=False),
    sa.Column('origin_event_id', sa.UUID(), nullable=False),
    sa.Column('calculation_id', sa.UUID(), nullable=False),
    sa.Column('movement_type', sa.String(length=32), nullable=False),
    sa.Column('amount_cents', sa.BigInteger(), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('effective_date', sa.Date(), nullable=False),
    sa.Column('scheduled_date', sa.Date(), nullable=True),
    sa.Column('paid_date', sa.Date(), nullable=True),
    sa.Column('rule_version_id', sa.String(length=32), nullable=False),
    sa.Column('network_snapshot_id', sa.UUID(), nullable=False),
    sa.Column('idempotency_key', sa.String(length=128), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sn_payout_entries')),
    sa.UniqueConstraint('idempotency_key', name='uq_sn_payout_entries_idempotency_key')
    )
    op.create_index(op.f('ix_sn_payout_entries_agent_id'), 'sn_payout_entries', ['agent_id'], unique=False)
    op.create_index(op.f('ix_sn_payout_entries_contract_id'), 'sn_payout_entries', ['contract_id'], unique=False)
    op.create_index(op.f('ix_sn_payout_entries_organization_id'), 'sn_payout_entries', ['organization_id'], unique=False)
    op.create_table('sn_payout_run_steps',
    sa.Column('calculation_id', sa.UUID(), nullable=False),
    sa.Column('step_order', sa.Integer(), nullable=False),
    sa.Column('beneficiary_agent_id', sa.UUID(), nullable=False),
    sa.Column('rank_at_calculation', sa.String(length=16), nullable=True),
    sa.Column('base_amount_cents', sa.BigInteger(), nullable=False),
    sa.Column('already_distributed_cents', sa.BigInteger(), nullable=False),
    sa.Column('entrepreneurial_difference_cents', sa.BigInteger(), nullable=False),
    sa.Column('personal_bonus_cents', sa.BigInteger(), nullable=False),
    sa.Column('gross_amount_cents', sa.BigInteger(), nullable=False),
    sa.Column('movement_type', sa.String(length=32), nullable=False),
    sa.Column('explanation', sa.String(length=1000), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sn_payout_run_steps'))
    )
    op.create_index(op.f('ix_sn_payout_run_steps_calculation_id'), 'sn_payout_run_steps', ['calculation_id'], unique=False)
    op.create_table('sn_support_replies',
    sa.Column('ticket_id', sa.UUID(), nullable=False),
    sa.Column('author_user_id', sa.UUID(), nullable=False),
    sa.Column('author_role', sa.String(length=32), nullable=False),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sn_support_replies'))
    )
    op.create_index(op.f('ix_sn_support_replies_ticket_id'), 'sn_support_replies', ['ticket_id'], unique=False)
    op.create_table('sn_payout_adjustments',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('original_movement_id', sa.UUID(), nullable=False),
    sa.Column('new_movement_id', sa.UUID(), nullable=False),
    sa.Column('reason', sa.String(length=500), nullable=False),
    sa.Column('requested_by', sa.UUID(), nullable=False),
    sa.Column('approved_by', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sn_payout_adjustments'))
    )
    op.create_index(op.f('ix_sn_payout_adjustments_organization_id'), 'sn_payout_adjustments', ['organization_id'], unique=False)
    op.create_table('sn_payout_offsets',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('debit_movement_id', sa.UUID(), nullable=False),
    sa.Column('credit_movement_id', sa.UUID(), nullable=False),
    sa.Column('reason', sa.String(length=500), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sn_payout_offsets'))
    )
    op.create_index(op.f('ix_sn_payout_offsets_organization_id'), 'sn_payout_offsets', ['organization_id'], unique=False)
    op.create_table('sn_payout_reversals',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('original_movement_id', sa.UUID(), nullable=False),
    sa.Column('new_movement_id', sa.UUID(), nullable=False),
    sa.Column('reason', sa.String(length=500), nullable=False),
    sa.Column('requested_by', sa.UUID(), nullable=False),
    sa.Column('approved_by', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sn_payout_reversals'))
    )
    op.create_index(op.f('ix_sn_payout_reversals_organization_id'), 'sn_payout_reversals', ['organization_id'], unique=False)

    # Foreign keys are added after all tables: orders and wallet movements
    # reference each other, so no creation order satisfies them all.
    op.create_foreign_key(op.f('fk_sn_aliexpress_orders_aliexpress_product_id_sn_aliexpress_items'), 'sn_aliexpress_orders', 'sn_aliexpress_items', ['aliexpress_product_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_aliexpress_orders_aliexpress_variant_id_sn_aliexpress_item_variants'), 'sn_aliexpress_orders', 'sn_aliexpress_item_variants', ['aliexpress_variant_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_aliexpress_orders_cancelled_by_user_id_sn_accounts'), 'sn_aliexpress_orders', 'sn_accounts', ['cancelled_by_user_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_aliexpress_orders_created_by_user_id_sn_accounts'), 'sn_aliexpress_orders', 'sn_accounts', ['created_by_user_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_aliexpress_orders_credit_debit_transaction_id_sn_credit_ledger'), 'sn_aliexpress_orders', 'sn_credit_ledger', ['credit_debit_transaction_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_aliexpress_orders_customer_user_id_sn_accounts'), 'sn_aliexpress_orders', 'sn_accounts', ['customer_user_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_aliexpress_orders_forwarded_by_user_id_sn_accounts'), 'sn_aliexpress_orders', 'sn_accounts', ['forwarded_by_user_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_aliexpress_orders_organization_id_sn_tenants'), 'sn_aliexpress_orders', 'sn_tenants', ['organization_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_aliexpress_orders_paid_by_user_id_sn_accounts'), 'sn_aliexpress_orders', 'sn_accounts', ['paid_by_user_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_cj_orders_cancelled_by_user_id_sn_accounts'), 'sn_cj_orders', 'sn_accounts', ['cancelled_by_user_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_cj_orders_cj_product_id_sn_cj_items'), 'sn_cj_orders', 'sn_cj_items', ['cj_product_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_cj_orders_cj_variant_id_sn_cj_item_variants'), 'sn_cj_orders', 'sn_cj_item_variants', ['cj_variant_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_cj_orders_created_by_user_id_sn_accounts'), 'sn_cj_orders', 'sn_accounts', ['created_by_user_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_cj_orders_credit_debit_transaction_id_sn_credit_ledger'), 'sn_cj_orders', 'sn_credit_ledger', ['credit_debit_transaction_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_cj_orders_customer_user_id_sn_accounts'), 'sn_cj_orders', 'sn_accounts', ['customer_user_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_cj_orders_forwarded_by_user_id_sn_accounts'), 'sn_cj_orders', 'sn_accounts', ['forwarded_by_user_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_cj_orders_organization_id_sn_tenants'), 'sn_cj_orders', 'sn_tenants', ['organization_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_cj_orders_paid_by_user_id_sn_accounts'), 'sn_cj_orders', 'sn_accounts', ['paid_by_user_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_credit_ledger_actor_user_id_sn_accounts'), 'sn_credit_ledger', 'sn_accounts', ['actor_user_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_credit_ledger_from_wallet_id_sn_credit_accounts'), 'sn_credit_ledger', 'sn_credit_accounts', ['from_wallet_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_credit_ledger_organization_id_sn_tenants'), 'sn_credit_ledger', 'sn_tenants', ['organization_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_credit_ledger_reference_sosnet_market_order_id_sn_market_orders'), 'sn_credit_ledger', 'sn_market_orders', ['reference_sosnet_market_order_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_credit_ledger_reference_aliexpress_order_id_sn_aliexpress_orders'), 'sn_credit_ledger', 'sn_aliexpress_orders', ['reference_aliexpress_order_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_credit_ledger_reference_cj_order_id_sn_cj_orders'), 'sn_credit_ledger', 'sn_cj_orders', ['reference_cj_order_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_credit_ledger_reference_contract_id_sn_agreements'), 'sn_credit_ledger', 'sn_agreements', ['reference_contract_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_credit_ledger_reference_imported_order_id_sn_supplier_item_orders'), 'sn_credit_ledger', 'sn_supplier_item_orders', ['reference_imported_order_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_credit_ledger_reference_invoice_redemption_id_sn_receipt_claims'), 'sn_credit_ledger', 'sn_receipt_claims', ['reference_invoice_redemption_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_credit_ledger_reference_order_id_sn_shop_orders'), 'sn_credit_ledger', 'sn_shop_orders', ['reference_order_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_credit_ledger_reference_shopify_order_id_sn_shopify_orders'), 'sn_credit_ledger', 'sn_shopify_orders', ['reference_shopify_order_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_credit_ledger_reverses_transaction_id_sn_credit_ledger'), 'sn_credit_ledger', 'sn_credit_ledger', ['reverses_transaction_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_credit_ledger_to_wallet_id_sn_credit_accounts'), 'sn_credit_ledger', 'sn_credit_accounts', ['to_wallet_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_market_orders_cancelled_by_user_id_sn_accounts'), 'sn_market_orders', 'sn_accounts', ['cancelled_by_user_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_market_orders_created_by_user_id_sn_accounts'), 'sn_market_orders', 'sn_accounts', ['created_by_user_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_market_orders_credit_debit_transaction_id_sn_credit_ledger'), 'sn_market_orders', 'sn_credit_ledger', ['credit_debit_transaction_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_market_orders_customer_user_id_sn_accounts'), 'sn_market_orders', 'sn_accounts', ['customer_user_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_market_orders_forwarded_by_user_id_sn_accounts'), 'sn_market_orders', 'sn_accounts', ['forwarded_by_user_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_market_orders_organization_id_sn_tenants'), 'sn_market_orders', 'sn_tenants', ['organization_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_market_orders_paid_by_user_id_sn_accounts'), 'sn_market_orders', 'sn_accounts', ['paid_by_user_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_shop_orders_cancelled_by_user_id_sn_accounts'), 'sn_shop_orders', 'sn_accounts', ['cancelled_by_user_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_shop_orders_created_by_user_id_sn_accounts'), 'sn_shop_orders', 'sn_accounts', ['created_by_user_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_shop_orders_credit_debit_transaction_id_sn_credit_ledger'), 'sn_shop_orders', 'sn_credit_ledger', ['credit_debit_transaction_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_shop_orders_customer_user_id_sn_accounts'), 'sn_shop_orders', 'sn_accounts', ['customer_user_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_shop_orders_organization_id_sn_tenants'), 'sn_shop_orders', 'sn_tenants', ['organization_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_shop_orders_paid_by_user_id_sn_accounts'), 'sn_shop_orders', 'sn_accounts', ['paid_by_user_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_shop_orders_product_version_id_sn_offer_versions'), 'sn_shop_orders', 'sn_offer_versions', ['product_version_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_shopify_orders_cancelled_by_user_id_sn_accounts'), 'sn_shopify_orders', 'sn_accounts', ['cancelled_by_user_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_shopify_orders_created_by_user_id_sn_accounts'), 'sn_shopify_orders', 'sn_accounts', ['created_by_user_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_shopify_orders_credit_debit_transaction_id_sn_credit_ledger'), 'sn_shopify_orders', 'sn_credit_ledger', ['credit_debit_transaction_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_shopify_orders_customer_user_id_sn_accounts'), 'sn_shopify_orders', 'sn_accounts', ['customer_user_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_shopify_orders_forwarded_by_user_id_sn_accounts'), 'sn_shopify_orders', 'sn_accounts', ['forwarded_by_user_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_shopify_orders_organization_id_sn_tenants'), 'sn_shopify_orders', 'sn_tenants', ['organization_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_shopify_orders_paid_by_user_id_sn_accounts'), 'sn_shopify_orders', 'sn_accounts', ['paid_by_user_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_shopify_orders_shopify_product_id_sn_shopify_items'), 'sn_shopify_orders', 'sn_shopify_items', ['shopify_product_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_shopify_orders_shopify_variant_id_sn_shopify_item_variants'), 'sn_shopify_orders', 'sn_shopify_item_variants', ['shopify_variant_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_supplier_item_orders_cancelled_by_user_id_sn_accounts'), 'sn_supplier_item_orders', 'sn_accounts', ['cancelled_by_user_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_supplier_item_orders_created_by_user_id_sn_accounts'), 'sn_supplier_item_orders', 'sn_accounts', ['created_by_user_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_supplier_item_orders_credit_debit_transaction_id_sn_credit_ledger'), 'sn_supplier_item_orders', 'sn_credit_ledger', ['credit_debit_transaction_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_supplier_item_orders_customer_user_id_sn_accounts'), 'sn_supplier_item_orders', 'sn_accounts', ['customer_user_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_supplier_item_orders_imported_product_id_sn_supplier_items'), 'sn_supplier_item_orders', 'sn_supplier_items', ['imported_product_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_supplier_item_orders_organization_id_sn_tenants'), 'sn_supplier_item_orders', 'sn_tenants', ['organization_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_supplier_item_orders_paid_by_user_id_sn_accounts'), 'sn_supplier_item_orders', 'sn_accounts', ['paid_by_user_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_accounts_organization_id_sn_tenants'), 'sn_accounts', 'sn_tenants', ['organization_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_aliexpress_config_organization_id_sn_tenants'), 'sn_aliexpress_config', 'sn_tenants', ['organization_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_career_levels_organization_id_sn_tenants'), 'sn_career_levels', 'sn_tenants', ['organization_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_catalog_sections_organization_id_sn_tenants'), 'sn_catalog_sections', 'sn_tenants', ['organization_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_cj_config_organization_id_sn_tenants'), 'sn_cj_config', 'sn_tenants', ['organization_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_event_outbox_organization_id_sn_tenants'), 'sn_event_outbox', 'sn_tenants', ['organization_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_market_config_organization_id_sn_tenants'), 'sn_market_config', 'sn_tenants', ['organization_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_merchants_organization_id_sn_tenants'), 'sn_merchants', 'sn_tenants', ['organization_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_offers_organization_id_sn_tenants'), 'sn_offers', 'sn_tenants', ['organization_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_payout_plans_organization_id_sn_tenants'), 'sn_payout_plans', 'sn_tenants', ['organization_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_roles_organization_id_sn_tenants'), 'sn_roles', 'sn_tenants', ['organization_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_shopify_config_organization_id_sn_tenants'), 'sn_shopify_config', 'sn_tenants', ['organization_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_stripe_events_organization_id_sn_tenants'), 'sn_stripe_events', 'sn_tenants', ['organization_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_tree_snapshots_organization_id_sn_tenants'), 'sn_tree_snapshots', 'sn_tenants', ['organization_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_account_roles_organization_id_sn_tenants'), 'sn_account_roles', 'sn_tenants', ['organization_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_account_roles_role_id_sn_roles'), 'sn_account_roles', 'sn_roles', ['role_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_account_roles_user_id_sn_accounts'), 'sn_account_roles', 'sn_accounts', ['user_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_activity_log_actor_user_id_sn_accounts'), 'sn_activity_log', 'sn_accounts', ['actor_user_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_activity_log_organization_id_sn_tenants'), 'sn_activity_log', 'sn_tenants', ['organization_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_aliexpress_items_created_by_user_id_sn_accounts'), 'sn_aliexpress_items', 'sn_accounts', ['created_by_user_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_aliexpress_items_organization_id_sn_tenants'), 'sn_aliexpress_items', 'sn_tenants', ['organization_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_baskets_customer_user_id_sn_accounts'), 'sn_baskets', 'sn_accounts', ['customer_user_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_baskets_organization_id_sn_tenants'), 'sn_baskets', 'sn_tenants', ['organization_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_catalog_section_items_category_id_sn_catalog_sections'), 'sn_catalog_section_items', 'sn_catalog_sections', ['category_id'], ['id'], ondelete='CASCADE')
    op.create_foreign_key(op.f('fk_sn_catalog_section_items_organization_id_sn_tenants'), 'sn_catalog_section_items', 'sn_tenants', ['organization_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_cj_items_created_by_user_id_sn_accounts'), 'sn_cj_items', 'sn_accounts', ['created_by_user_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_cj_items_organization_id_sn_tenants'), 'sn_cj_items', 'sn_tenants', ['organization_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_clients_organization_id_sn_tenants'), 'sn_clients', 'sn_tenants', ['organization_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_clients_user_id_sn_accounts'), 'sn_clients', 'sn_accounts', ['user_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_credit_accounts_organization_id_sn_tenants'), 'sn_credit_accounts', 'sn_tenants', ['organization_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_credit_accounts_user_id_sn_accounts'), 'sn_credit_accounts', 'sn_accounts', ['user_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_email_confirmations_user_id_sn_accounts'), 'sn_email_confirmations', 'sn_accounts', ['user_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_friend_invite_codes_organization_id_sn_tenants'), 'sn_friend_invite_codes', 'sn_tenants', ['organization_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_friend_invite_codes_user_id_sn_accounts'), 'sn_friend_invite_codes', 'sn_accounts', ['user_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_friend_invite_rewards_handled_by_user_id_sn_accounts'), 'sn_friend_invite_rewards', 'sn_accounts', ['handled_by_user_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_friend_invite_rewards_organization_id_sn_tenants'), 'sn_friend_invite_rewards', 'sn_tenants', ['organization_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_friend_invite_rewards_referrer_user_id_sn_accounts'), 'sn_friend_invite_rewards', 'sn_accounts', ['referrer_user_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_inbox_messages_organization_id_sn_tenants'), 'sn_inbox_messages', 'sn_tenants', ['organization_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_inbox_messages_recipient_user_id_sn_accounts'), 'sn_inbox_messages', 'sn_accounts', ['recipient_user_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_knowledge_articles_created_by_user_id_sn_accounts'), 'sn_knowledge_articles', 'sn_accounts', ['created_by_user_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_knowledge_articles_organization_id_sn_tenants'), 'sn_knowledge_articles', 'sn_tenants', ['organization_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_login_sessions_user_id_sn_accounts'), 'sn_login_sessions', 'sn_accounts', ['user_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_market_producers_created_by_user_id_sn_accounts'), 'sn_market_producers', 'sn_accounts', ['created_by_user_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_market_producers_organization_id_sn_tenants'), 'sn_market_producers', 'sn_tenants', ['organization_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_offer_versions_commission_plan_version_id_sn_payout_plans'), 'sn_offer_versions', 'sn_payout_plans', ['commission_plan_version_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_offer_versions_product_id_sn_offers'), 'sn_offer_versions', 'sn_offers', ['product_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_one_time_codes_user_id_sn_accounts'), 'sn_one_time_codes', 'sn_accounts', ['user_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_password_recoveries_user_id_sn_accounts'), 'sn_password_recoveries', 'sn_accounts', ['user_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_payout_rules_commission_plan_version_id_sn_payout_plans'), 'sn_payout_rules', 'sn_payout_plans', ['commission_plan_version_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_promoter_profiles_approved_by_user_id_sn_accounts'), 'sn_promoter_profiles', 'sn_accounts', ['approved_by_user_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_promoter_profiles_current_rank_id_sn_career_levels'), 'sn_promoter_profiles', 'sn_career_levels', ['current_rank_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_promoter_profiles_organization_id_sn_tenants'), 'sn_promoter_profiles', 'sn_tenants', ['organization_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_promoter_profiles_user_id_sn_accounts'), 'sn_promoter_profiles', 'sn_accounts', ['user_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_receipt_claims_credited_by_user_id_sn_accounts'), 'sn_receipt_claims', 'sn_accounts', ['credited_by_user_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_receipt_claims_customer_user_id_sn_accounts'), 'sn_receipt_claims', 'sn_accounts', ['customer_user_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_receipt_claims_organization_id_sn_tenants'), 'sn_receipt_claims', 'sn_tenants', ['organization_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_receipt_claims_partner_id_sn_merchants'), 'sn_receipt_claims', 'sn_merchants', ['partner_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_receipt_claims_verified_by_user_id_sn_accounts'), 'sn_receipt_claims', 'sn_accounts', ['verified_by_user_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_role_grants_permission_id_sn_permissions'), 'sn_role_grants', 'sn_permissions', ['permission_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_role_grants_role_id_sn_roles'), 'sn_role_grants', 'sn_roles', ['role_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_shopify_items_created_by_user_id_sn_accounts'), 'sn_shopify_items', 'sn_accounts', ['created_by_user_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_shopify_items_organization_id_sn_tenants'), 'sn_shopify_items', 'sn_tenants', ['organization_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_supplier_sources_created_by_user_id_sn_accounts'), 'sn_supplier_sources', 'sn_accounts', ['created_by_user_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_supplier_sources_organization_id_sn_tenants'), 'sn_supplier_sources', 'sn_tenants', ['organization_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_agreement_attributions_attributed_promoter_id_sn_promoter_profiles'), 'sn_agreement_attributions', 'sn_promoter_profiles', ['attributed_promoter_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_agreement_attributions_organization_id_sn_tenants'), 'sn_agreement_attributions', 'sn_tenants', ['organization_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_agreement_attributions_producer_agent_id_sn_promoter_profiles'), 'sn_agreement_attributions', 'sn_promoter_profiles', ['producer_agent_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_agreement_requests_activated_by_promoter_id_sn_promoter_profiles'), 'sn_agreement_requests', 'sn_promoter_profiles', ['activated_by_promoter_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_agreement_requests_bank_transfer_confirmed_by_user_id_sn_accounts'), 'sn_agreement_requests', 'sn_accounts', ['bank_transfer_confirmed_by_user_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_agreement_requests_created_by_user_id_sn_accounts'), 'sn_agreement_requests', 'sn_accounts', ['created_by_user_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_agreement_requests_customer_id_sn_clients'), 'sn_agreement_requests', 'sn_clients', ['customer_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_agreement_requests_organization_id_sn_tenants'), 'sn_agreement_requests', 'sn_tenants', ['organization_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_aliexpress_item_variants_product_id_sn_aliexpress_items'), 'sn_aliexpress_item_variants', 'sn_aliexpress_items', ['product_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_businesses_customer_id_sn_clients'), 'sn_businesses', 'sn_clients', ['customer_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_cj_item_variants_product_id_sn_cj_items'), 'sn_cj_item_variants', 'sn_cj_items', ['product_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_client_profiles_customer_id_sn_clients'), 'sn_client_profiles', 'sn_clients', ['customer_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_friend_invites_organization_id_sn_tenants'), 'sn_friend_invites', 'sn_tenants', ['organization_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_friend_invites_referred_customer_id_sn_clients'), 'sn_friend_invites', 'sn_clients', ['referred_customer_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_friend_invites_referrer_user_id_sn_accounts'), 'sn_friend_invites', 'sn_accounts', ['referrer_user_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_invite_codes_agent_id_sn_promoter_profiles'), 'sn_invite_codes', 'sn_promoter_profiles', ['agent_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_invite_codes_organization_id_sn_tenants'), 'sn_invite_codes', 'sn_tenants', ['organization_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_market_items_created_by_user_id_sn_accounts'), 'sn_market_items', 'sn_accounts', ['created_by_user_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_market_items_organization_id_sn_tenants'), 'sn_market_items', 'sn_tenants', ['organization_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_market_items_producer_id_sn_market_producers'), 'sn_market_items', 'sn_market_producers', ['producer_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_postal_addresses_customer_id_sn_clients'), 'sn_postal_addresses', 'sn_clients', ['customer_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_postal_addresses_organization_id_sn_tenants'), 'sn_postal_addresses', 'sn_tenants', ['organization_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_promoter_level_log_agent_id_sn_promoter_profiles'), 'sn_promoter_level_log', 'sn_promoter_profiles', ['agent_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_promoter_level_log_approved_by_sn_accounts'), 'sn_promoter_level_log', 'sn_accounts', ['approved_by'], ['id'])
    op.create_foreign_key(op.f('fk_sn_promoter_level_log_organization_id_sn_tenants'), 'sn_promoter_level_log', 'sn_tenants', ['organization_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_promoter_level_log_rank_id_sn_career_levels'), 'sn_promoter_level_log', 'sn_career_levels', ['rank_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_shopify_item_variants_product_id_sn_shopify_items'), 'sn_shopify_item_variants', 'sn_shopify_items', ['product_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_supplier_items_created_by_user_id_sn_accounts'), 'sn_supplier_items', 'sn_accounts', ['created_by_user_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_supplier_items_organization_id_sn_tenants'), 'sn_supplier_items', 'sn_tenants', ['organization_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_supplier_items_provider_id_sn_supplier_sources'), 'sn_supplier_items', 'sn_supplier_sources', ['provider_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_tree_links_child_agent_id_sn_promoter_profiles'), 'sn_tree_links', 'sn_promoter_profiles', ['child_agent_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_tree_links_organization_id_sn_tenants'), 'sn_tree_links', 'sn_tenants', ['organization_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_tree_links_parent_agent_id_sn_promoter_profiles'), 'sn_tree_links', 'sn_promoter_profiles', ['parent_agent_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_tree_moves_agent_id_sn_promoter_profiles'), 'sn_tree_moves', 'sn_promoter_profiles', ['agent_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_tree_moves_approved_by_sn_accounts'), 'sn_tree_moves', 'sn_accounts', ['approved_by'], ['id'])
    op.create_foreign_key(op.f('fk_sn_tree_moves_new_parent_agent_id_sn_promoter_profiles'), 'sn_tree_moves', 'sn_promoter_profiles', ['new_parent_agent_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_tree_moves_old_parent_agent_id_sn_promoter_profiles'), 'sn_tree_moves', 'sn_promoter_profiles', ['old_parent_agent_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_tree_moves_organization_id_sn_tenants'), 'sn_tree_moves', 'sn_tenants', ['organization_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_tree_moves_requested_by_sn_accounts'), 'sn_tree_moves', 'sn_accounts', ['requested_by'], ['id'])
    op.create_foreign_key(op.f('fk_sn_tree_nodes_agent_id_sn_promoter_profiles'), 'sn_tree_nodes', 'sn_promoter_profiles', ['agent_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_tree_nodes_direct_parent_agent_id_sn_promoter_profiles'), 'sn_tree_nodes', 'sn_promoter_profiles', ['direct_parent_agent_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_tree_nodes_organization_id_sn_tenants'), 'sn_tree_nodes', 'sn_tenants', ['organization_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_tree_paths_ancestor_agent_id_sn_promoter_profiles'), 'sn_tree_paths', 'sn_promoter_profiles', ['ancestor_agent_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_tree_paths_descendant_agent_id_sn_promoter_profiles'), 'sn_tree_paths', 'sn_promoter_profiles', ['descendant_agent_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_tree_paths_organization_id_sn_tenants'), 'sn_tree_paths', 'sn_tenants', ['organization_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_tree_snapshot_nodes_ancestor_agent_id_sn_promoter_profiles'), 'sn_tree_snapshot_nodes', 'sn_promoter_profiles', ['ancestor_agent_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_tree_snapshot_nodes_rank_id_at_snapshot_sn_career_levels'), 'sn_tree_snapshot_nodes', 'sn_career_levels', ['rank_id_at_snapshot'], ['id'])
    op.create_foreign_key(op.f('fk_sn_tree_snapshot_nodes_snapshot_id_sn_tree_snapshots'), 'sn_tree_snapshot_nodes', 'sn_tree_snapshots', ['snapshot_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_agreement_checkouts_contract_request_id_sn_agreement_requests'), 'sn_agreement_checkouts', 'sn_agreement_requests', ['contract_request_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_agreement_checkouts_created_by_user_id_sn_accounts'), 'sn_agreement_checkouts', 'sn_accounts', ['created_by_user_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_agreement_checkouts_organization_id_sn_tenants'), 'sn_agreement_checkouts', 'sn_tenants', ['organization_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_aliexpress_order_lines_aliexpress_product_id_sn_aliexpress_items'), 'sn_aliexpress_order_lines', 'sn_aliexpress_items', ['aliexpress_product_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_aliexpress_order_lines_aliexpress_variant_id_sn_aliexpress_item_variants'), 'sn_aliexpress_order_lines', 'sn_aliexpress_item_variants', ['aliexpress_variant_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_aliexpress_order_lines_order_id_sn_aliexpress_orders'), 'sn_aliexpress_order_lines', 'sn_aliexpress_orders', ['order_id'], ['id'], ondelete='CASCADE')
    op.create_foreign_key(op.f('fk_sn_cj_order_lines_order_id_sn_cj_orders'), 'sn_cj_order_lines', 'sn_cj_orders', ['order_id'], ['id'], ondelete='CASCADE')
    op.create_foreign_key(op.f('fk_sn_cj_order_lines_product_id_sn_cj_items'), 'sn_cj_order_lines', 'sn_cj_items', ['product_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_cj_order_lines_variant_id_sn_cj_item_variants'), 'sn_cj_order_lines', 'sn_cj_item_variants', ['variant_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_invite_events_organization_id_sn_tenants'), 'sn_invite_events', 'sn_tenants', ['organization_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_invite_events_promoter_code_id_sn_invite_codes'), 'sn_invite_events', 'sn_invite_codes', ['promoter_code_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_invite_visits_organization_id_sn_tenants'), 'sn_invite_visits', 'sn_tenants', ['organization_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_invite_visits_promoter_code_id_sn_invite_codes'), 'sn_invite_visits', 'sn_invite_codes', ['promoter_code_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_market_item_variants_product_id_sn_market_items'), 'sn_market_item_variants', 'sn_market_items', ['product_id'], ['id'], ondelete='CASCADE')
    op.create_foreign_key(op.f('fk_sn_shopify_order_lines_order_id_sn_shopify_orders'), 'sn_shopify_order_lines', 'sn_shopify_orders', ['order_id'], ['id'], ondelete='CASCADE')
    op.create_foreign_key(op.f('fk_sn_shopify_order_lines_product_id_sn_shopify_items'), 'sn_shopify_order_lines', 'sn_shopify_items', ['product_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_shopify_order_lines_variant_id_sn_shopify_item_variants'), 'sn_shopify_order_lines', 'sn_shopify_item_variants', ['variant_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_utility_points_customer_id_sn_clients'), 'sn_utility_points', 'sn_clients', ['customer_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_utility_points_organization_id_sn_tenants'), 'sn_utility_points', 'sn_tenants', ['organization_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_utility_points_supply_address_id_sn_postal_addresses'), 'sn_utility_points', 'sn_postal_addresses', ['supply_address_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_agreements_activated_by_promoter_id_sn_promoter_profiles'), 'sn_agreements', 'sn_promoter_profiles', ['activated_by_promoter_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_agreements_contract_attribution_id_sn_agreement_attributions'), 'sn_agreements', 'sn_agreement_attributions', ['contract_attribution_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_agreements_contract_request_id_sn_agreement_requests'), 'sn_agreements', 'sn_agreement_requests', ['contract_request_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_agreements_created_by_user_id_sn_accounts'), 'sn_agreements', 'sn_accounts', ['created_by_user_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_agreements_customer_id_sn_clients'), 'sn_agreements', 'sn_clients', ['customer_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_agreements_first_referrer_agent_id_sn_promoter_profiles'), 'sn_agreements', 'sn_promoter_profiles', ['first_referrer_agent_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_agreements_network_snapshot_id_sn_tree_snapshots'), 'sn_agreements', 'sn_tree_snapshots', ['network_snapshot_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_agreements_organization_id_sn_tenants'), 'sn_agreements', 'sn_tenants', ['organization_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_agreements_product_version_id_sn_offer_versions'), 'sn_agreements', 'sn_offer_versions', ['product_version_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_agreements_supply_point_id_sn_utility_points'), 'sn_agreements', 'sn_utility_points', ['supply_point_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_agreements_terms_accepted_by_user_id_sn_accounts'), 'sn_agreements', 'sn_accounts', ['terms_accepted_by_user_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_basket_lines_sosnet_market_variant_id_sn_market_item_variants'), 'sn_basket_lines', 'sn_market_item_variants', ['sosnet_market_variant_id'], ['id'], ondelete='CASCADE')
    op.create_foreign_key(op.f('fk_sn_basket_lines_aliexpress_variant_id_sn_aliexpress_item_variants'), 'sn_basket_lines', 'sn_aliexpress_item_variants', ['aliexpress_variant_id'], ['id'], ondelete='CASCADE')
    op.create_foreign_key(op.f('fk_sn_basket_lines_cart_id_sn_baskets'), 'sn_basket_lines', 'sn_baskets', ['cart_id'], ['id'], ondelete='CASCADE')
    op.create_foreign_key(op.f('fk_sn_basket_lines_cj_variant_id_sn_cj_item_variants'), 'sn_basket_lines', 'sn_cj_item_variants', ['cj_variant_id'], ['id'], ondelete='CASCADE')
    op.create_foreign_key(op.f('fk_sn_basket_lines_product_version_id_sn_offer_versions'), 'sn_basket_lines', 'sn_offer_versions', ['product_version_id'], ['id'], ondelete='CASCADE')
    op.create_foreign_key(op.f('fk_sn_basket_lines_shopify_variant_id_sn_shopify_item_variants'), 'sn_basket_lines', 'sn_shopify_item_variants', ['shopify_variant_id'], ['id'], ondelete='CASCADE')
    op.create_foreign_key(op.f('fk_sn_client_attributions_customer_id_sn_clients'), 'sn_client_attributions', 'sn_clients', ['customer_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_client_attributions_organization_id_sn_tenants'), 'sn_client_attributions', 'sn_tenants', ['organization_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_client_attributions_promoter_code_id_sn_invite_codes'), 'sn_client_attributions', 'sn_invite_codes', ['promoter_code_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_client_attributions_referral_session_id_sn_invite_visits'), 'sn_client_attributions', 'sn_invite_visits', ['referral_session_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_market_order_lines_order_id_sn_market_orders'), 'sn_market_order_lines', 'sn_market_orders', ['order_id'], ['id'], ondelete='CASCADE')
    op.create_foreign_key(op.f('fk_sn_market_order_lines_product_id_sn_market_items'), 'sn_market_order_lines', 'sn_market_items', ['product_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_market_order_lines_variant_id_sn_market_item_variants'), 'sn_market_order_lines', 'sn_market_item_variants', ['variant_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_agreement_events_contract_id_sn_agreements'), 'sn_agreement_events', 'sn_agreements', ['contract_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_agreement_payout_plans_accepted_by_user_id_sn_accounts'), 'sn_agreement_payout_plans', 'sn_accounts', ['accepted_by_user_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_agreement_payout_plans_contract_id_sn_agreements'), 'sn_agreement_payout_plans', 'sn_agreements', ['contract_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_agreement_payout_plans_organization_id_sn_tenants'), 'sn_agreement_payout_plans', 'sn_tenants', ['organization_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_agreement_status_log_actor_user_id_sn_accounts'), 'sn_agreement_status_log', 'sn_accounts', ['actor_user_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_agreement_status_log_contract_id_sn_agreements'), 'sn_agreement_status_log', 'sn_agreements', ['contract_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_attribution_fixes_approved_by_sn_accounts'), 'sn_attribution_fixes', 'sn_accounts', ['approved_by'], ['id'])
    op.create_foreign_key(op.f('fk_sn_attribution_fixes_customer_attribution_id_sn_client_attributions'), 'sn_attribution_fixes', 'sn_client_attributions', ['customer_attribution_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_attribution_fixes_new_promoter_code_id_sn_invite_codes'), 'sn_attribution_fixes', 'sn_invite_codes', ['new_promoter_code_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_attribution_fixes_organization_id_sn_tenants'), 'sn_attribution_fixes', 'sn_tenants', ['organization_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_attribution_fixes_previous_promoter_code_id_sn_invite_codes'), 'sn_attribution_fixes', 'sn_invite_codes', ['previous_promoter_code_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_attribution_fixes_requested_by_sn_accounts'), 'sn_attribution_fixes', 'sn_accounts', ['requested_by'], ['id'])
    op.create_foreign_key(op.f('fk_sn_payout_runs_commission_plan_version_id_sn_payout_plans'), 'sn_payout_runs', 'sn_payout_plans', ['commission_plan_version_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_payout_runs_contract_id_sn_agreements'), 'sn_payout_runs', 'sn_agreements', ['contract_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_payout_runs_network_snapshot_id_sn_tree_snapshots'), 'sn_payout_runs', 'sn_tree_snapshots', ['network_snapshot_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_payout_runs_organization_id_sn_tenants'), 'sn_payout_runs', 'sn_tenants', ['organization_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_stored_files_contract_id_sn_agreements'), 'sn_stored_files', 'sn_agreements', ['contract_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_stored_files_contract_request_id_sn_agreement_requests'), 'sn_stored_files', 'sn_agreement_requests', ['contract_request_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_stored_files_organization_id_sn_tenants'), 'sn_stored_files', 'sn_tenants', ['organization_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_stored_files_reviewed_by_user_id_sn_accounts'), 'sn_stored_files', 'sn_accounts', ['reviewed_by_user_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_stored_files_uploaded_by_user_id_sn_accounts'), 'sn_stored_files', 'sn_accounts', ['uploaded_by_user_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_support_cases_contract_id_sn_agreements'), 'sn_support_cases', 'sn_agreements', ['contract_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_support_cases_opened_by_user_id_sn_accounts'), 'sn_support_cases', 'sn_accounts', ['opened_by_user_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_support_cases_organization_id_sn_tenants'), 'sn_support_cases', 'sn_tenants', ['organization_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_agreement_instalments_commission_calculation_id_sn_payout_runs'), 'sn_agreement_instalments', 'sn_payout_runs', ['commission_calculation_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_agreement_instalments_confirmed_by_user_id_sn_accounts'), 'sn_agreement_instalments', 'sn_accounts', ['confirmed_by_user_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_agreement_instalments_contract_id_sn_agreements'), 'sn_agreement_instalments', 'sn_agreements', ['contract_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_agreement_instalments_organization_id_sn_tenants'), 'sn_agreement_instalments', 'sn_tenants', ['organization_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_payout_entries_agent_id_sn_promoter_profiles'), 'sn_payout_entries', 'sn_promoter_profiles', ['agent_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_payout_entries_calculation_id_sn_payout_runs'), 'sn_payout_entries', 'sn_payout_runs', ['calculation_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_payout_entries_contract_id_sn_agreements'), 'sn_payout_entries', 'sn_agreements', ['contract_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_payout_entries_network_snapshot_id_sn_tree_snapshots'), 'sn_payout_entries', 'sn_tree_snapshots', ['network_snapshot_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_payout_entries_organization_id_sn_tenants'), 'sn_payout_entries', 'sn_tenants', ['organization_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_payout_run_steps_beneficiary_agent_id_sn_promoter_profiles'), 'sn_payout_run_steps', 'sn_promoter_profiles', ['beneficiary_agent_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_payout_run_steps_calculation_id_sn_payout_runs'), 'sn_payout_run_steps', 'sn_payout_runs', ['calculation_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_support_replies_author_user_id_sn_accounts'), 'sn_support_replies', 'sn_accounts', ['author_user_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_support_replies_ticket_id_sn_support_cases'), 'sn_support_replies', 'sn_support_cases', ['ticket_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_payout_adjustments_approved_by_sn_accounts'), 'sn_payout_adjustments', 'sn_accounts', ['approved_by'], ['id'])
    op.create_foreign_key(op.f('fk_sn_payout_adjustments_new_movement_id_sn_payout_entries'), 'sn_payout_adjustments', 'sn_payout_entries', ['new_movement_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_payout_adjustments_organization_id_sn_tenants'), 'sn_payout_adjustments', 'sn_tenants', ['organization_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_payout_adjustments_original_movement_id_sn_payout_entries'), 'sn_payout_adjustments', 'sn_payout_entries', ['original_movement_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_payout_adjustments_requested_by_sn_accounts'), 'sn_payout_adjustments', 'sn_accounts', ['requested_by'], ['id'])
    op.create_foreign_key(op.f('fk_sn_payout_offsets_credit_movement_id_sn_payout_entries'), 'sn_payout_offsets', 'sn_payout_entries', ['credit_movement_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_payout_offsets_debit_movement_id_sn_payout_entries'), 'sn_payout_offsets', 'sn_payout_entries', ['debit_movement_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_payout_offsets_organization_id_sn_tenants'), 'sn_payout_offsets', 'sn_tenants', ['organization_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_payout_reversals_approved_by_sn_accounts'), 'sn_payout_reversals', 'sn_accounts', ['approved_by'], ['id'])
    op.create_foreign_key(op.f('fk_sn_payout_reversals_new_movement_id_sn_payout_entries'), 'sn_payout_reversals', 'sn_payout_entries', ['new_movement_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_payout_reversals_organization_id_sn_tenants'), 'sn_payout_reversals', 'sn_tenants', ['organization_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_payout_reversals_original_movement_id_sn_payout_entries'), 'sn_payout_reversals', 'sn_payout_entries', ['original_movement_id'], ['id'])
    op.create_foreign_key(op.f('fk_sn_payout_reversals_requested_by_sn_accounts'), 'sn_payout_reversals', 'sn_accounts', ['requested_by'], ['id'])


def downgrade() -> None:
    op.drop_index(op.f('ix_sn_payout_reversals_organization_id'), table_name='sn_payout_reversals')
    op.drop_table('sn_payout_reversals')
    op.drop_index(op.f('ix_sn_payout_offsets_organization_id'), table_name='sn_payout_offsets')
    op.drop_table('sn_payout_offsets')
    op.drop_index(op.f('ix_sn_payout_adjustments_organization_id'), table_name='sn_payout_adjustments')
    op.drop_table('sn_payout_adjustments')
    op.drop_index(op.f('ix_sn_support_replies_ticket_id'), table_name='sn_support_replies')
    op.drop_table('sn_support_replies')
    op.drop_index(op.f('ix_sn_payout_run_steps_calculation_id'), table_name='sn_payout_run_steps')
    op.drop_table('sn_payout_run_steps')
    op.drop_index(op.f('ix_sn_payout_entries_organization_id'), table_name='sn_payout_entries')
    op.drop_index(op.f('ix_sn_payout_entries_contract_id'), table_name='sn_payout_entries')
    op.drop_index(op.f('ix_sn_payout_entries_agent_id'), table_name='sn_payout_entries')
    op.drop_table('sn_payout_entries')
    op.drop_index(op.f('ix_sn_agreement_instalments_organization_id'), table_name='sn_agreement_instalments')
    op.drop_index(op.f('ix_sn_agreement_instalments_contract_id'), table_name='sn_agreement_instalments')
    op.drop_table('sn_agreement_instalments')
    op.drop_index(op.f('ix_sn_support_cases_status'), table_name='sn_support_cases')
    op.drop_index(op.f('ix_sn_support_cases_organization_id'), table_name='sn_support_cases')
    op.drop_index(op.f('ix_sn_support_cases_opened_by_user_id'), table_name='sn_support_cases')
    op.drop_table('sn_support_cases')
    op.drop_index(op.f('ix_sn_stored_files_status'), table_name='sn_stored_files')
    op.drop_index(op.f('ix_sn_stored_files_organization_id'), table_name='sn_stored_files')
    op.drop_index(op.f('ix_sn_stored_files_contract_request_id'), table_name='sn_stored_files')
    op.drop_index(op.f('ix_sn_stored_files_contract_id'), table_name='sn_stored_files')
    op.drop_table('sn_stored_files')
    op.drop_index(op.f('ix_sn_payout_runs_organization_id'), table_name='sn_payout_runs')
    op.drop_index(op.f('ix_sn_payout_runs_contract_id'), table_name='sn_payout_runs')
    op.drop_table('sn_payout_runs')
    op.drop_index(op.f('ix_sn_attribution_fixes_organization_id'), table_name='sn_attribution_fixes')
    op.drop_table('sn_attribution_fixes')
    op.drop_index(op.f('ix_sn_agreement_status_log_contract_id'), table_name='sn_agreement_status_log')
    op.drop_table('sn_agreement_status_log')
    op.drop_index(op.f('ix_sn_agreement_payout_plans_organization_id'), table_name='sn_agreement_payout_plans')
    op.drop_table('sn_agreement_payout_plans')
    op.drop_index(op.f('ix_sn_agreement_events_contract_id'), table_name='sn_agreement_events')
    op.drop_table('sn_agreement_events')
    op.drop_index(op.f('ix_sn_market_order_lines_order_id'), table_name='sn_market_order_lines')
    op.drop_table('sn_market_order_lines')
    op.drop_index(op.f('ix_sn_client_attributions_organization_id'), table_name='sn_client_attributions')
    op.drop_index(op.f('ix_sn_client_attributions_customer_id'), table_name='sn_client_attributions')
    op.drop_table('sn_client_attributions')
    op.drop_index(op.f('ix_sn_basket_lines_cart_id'), table_name='sn_basket_lines')
    op.drop_table('sn_basket_lines')
    op.drop_index(op.f('ix_sn_agreements_status'), table_name='sn_agreements')
    op.drop_index(op.f('ix_sn_agreements_organization_id'), table_name='sn_agreements')
    op.drop_index(op.f('ix_sn_agreements_expires_at'), table_name='sn_agreements')
    op.drop_index(op.f('ix_sn_agreements_customer_id'), table_name='sn_agreements')
    op.drop_index(op.f('ix_sn_agreements_contract_request_id'), table_name='sn_agreements')
    op.drop_table('sn_agreements')
    op.drop_index(op.f('ix_sn_utility_points_organization_id'), table_name='sn_utility_points')
    op.drop_index(op.f('ix_sn_utility_points_customer_id'), table_name='sn_utility_points')
    op.drop_table('sn_utility_points')
    op.drop_index(op.f('ix_sn_shopify_order_lines_order_id'), table_name='sn_shopify_order_lines')
    op.drop_table('sn_shopify_order_lines')
    op.drop_index(op.f('ix_sn_market_item_variants_product_id'), table_name='sn_market_item_variants')
    op.drop_table('sn_market_item_variants')
    op.drop_index(op.f('ix_sn_invite_visits_promoter_code_id'), table_name='sn_invite_visits')
    op.drop_index(op.f('ix_sn_invite_visits_organization_id'), table_name='sn_invite_visits')
    op.drop_index(op.f('ix_sn_invite_visits_cookie_token_hash'), table_name='sn_invite_visits')
    op.drop_table('sn_invite_visits')
    op.drop_index(op.f('ix_sn_invite_events_promoter_code_id'), table_name='sn_invite_events')
    op.drop_index(op.f('ix_sn_invite_events_organization_id'), table_name='sn_invite_events')
    op.drop_table('sn_invite_events')
    op.drop_index(op.f('ix_sn_cj_order_lines_order_id'), table_name='sn_cj_order_lines')
    op.drop_table('sn_cj_order_lines')
    op.drop_index(op.f('ix_sn_aliexpress_order_lines_order_id'), table_name='sn_aliexpress_order_lines')
    op.drop_index(op.f('ix_sn_aliexpress_order_lines_aliexpress_order_id'), table_name='sn_aliexpress_order_lines')
    op.drop_table('sn_aliexpress_order_lines')
    op.drop_index(op.f('ix_sn_agreement_checkouts_organization_id'), table_name='sn_agreement_checkouts')
    op.drop_index(op.f('ix_sn_agreement_checkouts_contract_request_id'), table_name='sn_agreement_checkouts')
    op.drop_table('sn_agreement_checkouts')
    op.drop_table('sn_tree_snapshot_nodes')
    op.drop_index('ix_sn_tree_paths_org_descendant_depth', table_name='sn_tree_paths')
    op.drop_index('ix_sn_tree_paths_org_descendant', table_name='sn_tree_paths')
    op.drop_index('ix_sn_tree_paths_org_ancestor_depth', table_name='sn_tree_paths')
    op.drop_index('ix_sn_tree_paths_org_ancestor', table_name='sn_tree_paths')
    op.drop_table('sn_tree_paths')
    op.drop_index('uq_sn_tree_nodes_active_agent', table_name='sn_tree_nodes', postgresql_where=sa.text('effective_to IS NULL'))
    op.drop_index(op.f('ix_sn_tree_nodes_organization_id'), table_name='sn_tree_nodes')
    op.drop_index(op.f('ix_sn_tree_nodes_agent_id'), table_name='sn_tree_nodes')
    op.drop_table('sn_tree_nodes')
    op.drop_index(op.f('ix_sn_tree_moves_organization_id'), table_name='sn_tree_moves')
    op.drop_table('sn_tree_moves')
    op.drop_index(op.f('ix_sn_tree_links_parent_agent_id'), table_name='sn_tree_links')
    op.drop_index(op.f('ix_sn_tree_links_organization_id'), table_name='sn_tree_links')
    op.drop_index(op.f('ix_sn_tree_links_child_agent_id'), table_name='sn_tree_links')
    op.drop_table('sn_tree_links')
    op.drop_index(op.f('ix_sn_supplier_items_provider_id'), table_name='sn_supplier_items')
    op.drop_index(op.f('ix_sn_supplier_items_organization_id'), table_name='sn_supplier_items')
    op.drop_table('sn_supplier_items')
    op.drop_index(op.f('ix_sn_shopify_item_variants_product_id'), table_name='sn_shopify_item_variants')
    op.drop_table('sn_shopify_item_variants')
    op.drop_index(op.f('ix_sn_promoter_level_log_organization_id'), table_name='sn_promoter_level_log')
    op.drop_index(op.f('ix_sn_promoter_level_log_agent_id'), table_name='sn_promoter_level_log')
    op.drop_table('sn_promoter_level_log')
    op.drop_index(op.f('ix_sn_postal_addresses_organization_id'), table_name='sn_postal_addresses')
    op.drop_index(op.f('ix_sn_postal_addresses_customer_id'), table_name='sn_postal_addresses')
    op.drop_table('sn_postal_addresses')
    op.drop_index(op.f('ix_sn_market_items_status'), table_name='sn_market_items')
    op.drop_index(op.f('ix_sn_market_items_producer_id'), table_name='sn_market_items')
    op.drop_index(op.f('ix_sn_market_items_organization_id'), table_name='sn_market_items')
    op.drop_table('sn_market_items')
    op.drop_index(op.f('ix_sn_invite_codes_organization_id'), table_name='sn_invite_codes')
    op.drop_index(op.f('ix_sn_invite_codes_code'), table_name='sn_invite_codes')
    op.drop_index(op.f('ix_sn_invite_codes_agent_id'), table_name='sn_invite_codes')
    op.drop_table('sn_invite_codes')
    op.drop_index(op.f('ix_sn_friend_invites_referrer_user_id'), table_name='sn_friend_invites')
    op.drop_index(op.f('ix_sn_friend_invites_organization_id'), table_name='sn_friend_invites')
    op.drop_table('sn_friend_invites')
    op.drop_table('sn_client_profiles')
    op.drop_index(op.f('ix_sn_cj_item_variants_product_id'), table_name='sn_cj_item_variants')
    op.drop_table('sn_cj_item_variants')
    op.drop_table('sn_businesses')
    op.drop_index(op.f('ix_sn_aliexpress_item_variants_product_id'), table_name='sn_aliexpress_item_variants')
    op.drop_table('sn_aliexpress_item_variants')
    op.drop_index(op.f('ix_sn_agreement_requests_status'), table_name='sn_agreement_requests')
    op.drop_index(op.f('ix_sn_agreement_requests_organization_id'), table_name='sn_agreement_requests')
    op.drop_index(op.f('ix_sn_agreement_requests_customer_id'), table_name='sn_agreement_requests')
    op.drop_table('sn_agreement_requests')
    op.drop_index(op.f('ix_sn_agreement_attributions_organization_id'), table_name='sn_agreement_attributions')
    op.drop_table('sn_agreement_attributions')
    op.drop_index(op.f('ix_sn_supplier_sources_organization_id'), table_name='sn_supplier_sources')
    op.drop_table('sn_supplier_sources')
    op.drop_index(op.f('ix_sn_shopify_items_status'), table_name='sn_shopify_items')
    op.drop_index(op.f('ix_sn_shopify_items_organization_id'), table_name='sn_shopify_items')
    op.drop_table('sn_shopify_items')
    op.drop_table('sn_role_grants')
    op.drop_index(op.f('ix_sn_receipt_claims_status'), table_name='sn_receipt_claims')
    op.drop_index(op.f('ix_sn_receipt_claims_organization_id'), table_name='sn_receipt_claims')
    op.drop_index(op.f('ix_sn_receipt_claims_customer_user_id'), table_name='sn_receipt_claims')
    op.drop_table('sn_receipt_claims')
    op.drop_index(op.f('ix_sn_promoter_profiles_organization_id'), table_name='sn_promoter_profiles')
    op.drop_table('sn_promoter_profiles')
    op.drop_index(op.f('ix_sn_payout_rules_commission_plan_version_id'), table_name='sn_payout_rules')
    op.drop_table('sn_payout_rules')
    op.drop_index(op.f('ix_sn_password_recoveries_user_id'), table_name='sn_password_recoveries')
    op.drop_index(op.f('ix_sn_password_recoveries_token_hash'), table_name='sn_password_recoveries')
    op.drop_table('sn_password_recoveries')
    op.drop_index(op.f('ix_sn_one_time_codes_user_id'), table_name='sn_one_time_codes')
    op.drop_index(op.f('ix_sn_one_time_codes_purpose'), table_name='sn_one_time_codes')
    op.drop_index(op.f('ix_sn_one_time_codes_code_hash'), table_name='sn_one_time_codes')
    op.drop_table('sn_one_time_codes')
    op.drop_index(op.f('ix_sn_offer_versions_product_id'), table_name='sn_offer_versions')
    op.drop_table('sn_offer_versions')
    op.drop_index(op.f('ix_sn_market_producers_organization_id'), table_name='sn_market_producers')
    op.drop_table('sn_market_producers')
    op.drop_index(op.f('ix_sn_login_sessions_user_id'), table_name='sn_login_sessions')
    op.drop_index(op.f('ix_sn_login_sessions_refresh_token_hash'), table_name='sn_login_sessions')
    op.drop_table('sn_login_sessions')
    op.drop_index(op.f('ix_sn_knowledge_articles_status'), table_name='sn_knowledge_articles')
    op.drop_index(op.f('ix_sn_knowledge_articles_organization_id'), table_name='sn_knowledge_articles')
    op.drop_table('sn_knowledge_articles')
    op.drop_index(op.f('ix_sn_inbox_messages_type'), table_name='sn_inbox_messages')
    op.drop_index(op.f('ix_sn_inbox_messages_recipient_user_id'), table_name='sn_inbox_messages')
    op.drop_index(op.f('ix_sn_inbox_messages_organization_id'), table_name='sn_inbox_messages')
    op.drop_index(op.f('ix_sn_inbox_messages_is_read'), table_name='sn_inbox_messages')
    op.drop_table('sn_inbox_messages')
    op.drop_index(op.f('ix_sn_friend_invite_rewards_status'), table_name='sn_friend_invite_rewards')
    op.drop_index(op.f('ix_sn_friend_invite_rewards_referrer_user_id'), table_name='sn_friend_invite_rewards')
    op.drop_index(op.f('ix_sn_friend_invite_rewards_organization_id'), table_name='sn_friend_invite_rewards')
    op.drop_table('sn_friend_invite_rewards')
    op.drop_index(op.f('ix_sn_friend_invite_codes_organization_id'), table_name='sn_friend_invite_codes')
    op.drop_table('sn_friend_invite_codes')
    op.drop_index(op.f('ix_sn_email_confirmations_user_id'), table_name='sn_email_confirmations')
    op.drop_index(op.f('ix_sn_email_confirmations_token_hash'), table_name='sn_email_confirmations')
    op.drop_table('sn_email_confirmations')
    op.drop_index(op.f('ix_sn_credit_accounts_user_id'), table_name='sn_credit_accounts')
    op.drop_index(op.f('ix_sn_credit_accounts_organization_id'), table_name='sn_credit_accounts')
    op.drop_index(op.f('ix_sn_credit_accounts_address'), table_name='sn_credit_accounts')
    op.drop_table('sn_credit_accounts')
    op.drop_index(op.f('ix_sn_clients_organization_id'), table_name='sn_clients')
    op.drop_table('sn_clients')
    op.drop_index(op.f('ix_sn_cj_items_status'), table_name='sn_cj_items')
    op.drop_index(op.f('ix_sn_cj_items_organization_id'), table_name='sn_cj_items')
    op.drop_table('sn_cj_items')
    op.drop_index('ix_sn_catalog_section_items_organization_id_shop_product_id', table_name='sn_catalog_section_items')
    op.drop_index(op.f('ix_sn_catalog_section_items_category_id'), table_name='sn_catalog_section_items')
    op.drop_table('sn_catalog_section_items')
    op.drop_index(op.f('ix_sn_baskets_organization_id'), table_name='sn_baskets')
    op.drop_index(op.f('ix_sn_baskets_customer_user_id'), table_name='sn_baskets')
    op.drop_table('sn_baskets')
    op.drop_index(op.f('ix_sn_aliexpress_items_status'), table_name='sn_aliexpress_items')
    op.drop_index(op.f('ix_sn_aliexpress_items_organization_id'), table_name='sn_aliexpress_items')
    op.drop_table('sn_aliexpress_items')
    op.drop_index(op.f('ix_sn_activity_log_organization_id'), table_name='sn_activity_log')
    op.drop_index(op.f('ix_sn_activity_log_correlation_id'), table_name='sn_activity_log')
    op.drop_index(op.f('ix_sn_activity_log_action'), table_name='sn_activity_log')
    op.drop_table('sn_activity_log')
    op.drop_index(op.f('ix_sn_account_roles_user_id'), table_name='sn_account_roles')
    op.drop_index(op.f('ix_sn_account_roles_organization_id'), table_name='sn_account_roles')
    op.drop_table('sn_account_roles')
    op.drop_index(op.f('ix_sn_tree_snapshots_organization_id'), table_name='sn_tree_snapshots')
    op.drop_table('sn_tree_snapshots')
    op.drop_index(op.f('ix_sn_stripe_events_organization_id'), table_name='sn_stripe_events')
    op.drop_index(op.f('ix_sn_stripe_events_event_type'), table_name='sn_stripe_events')
    op.drop_table('sn_stripe_events')
    op.drop_table('sn_shopify_config')
    op.drop_index(op.f('ix_sn_roles_organization_id'), table_name='sn_roles')
    op.drop_table('sn_roles')
    op.drop_index(op.f('ix_sn_payout_plans_organization_id'), table_name='sn_payout_plans')
    op.drop_table('sn_payout_plans')
    op.drop_index(op.f('ix_sn_offers_organization_id'), table_name='sn_offers')
    op.drop_table('sn_offers')
    op.drop_index(op.f('ix_sn_merchants_organization_id'), table_name='sn_merchants')
    op.drop_table('sn_merchants')
    op.drop_index(op.f('ix_sn_market_config_organization_id'), table_name='sn_market_config')
    op.drop_table('sn_market_config')
    op.drop_index(op.f('ix_sn_event_outbox_processed_at'), table_name='sn_event_outbox')
    op.drop_index(op.f('ix_sn_event_outbox_organization_id'), table_name='sn_event_outbox')
    op.drop_index(op.f('ix_sn_event_outbox_event_type'), table_name='sn_event_outbox')
    op.drop_table('sn_event_outbox')
    op.drop_table('sn_cj_config')
    op.drop_index('uq_sn_catalog_sections_organization_id_shop_name', table_name='sn_catalog_sections')
    op.drop_index(op.f('ix_sn_catalog_sections_organization_id'), table_name='sn_catalog_sections')
    op.drop_table('sn_catalog_sections')
    op.drop_index(op.f('ix_sn_career_levels_organization_id'), table_name='sn_career_levels')
    op.drop_table('sn_career_levels')
    op.drop_table('sn_aliexpress_config')
    op.drop_index(op.f('ix_sn_accounts_organization_id'), table_name='sn_accounts')
    op.drop_index(op.f('ix_sn_accounts_email'), table_name='sn_accounts')
    op.drop_table('sn_accounts')
    op.drop_table('sn_tenants')
    op.drop_index(op.f('ix_sn_supplier_item_orders_status'), table_name='sn_supplier_item_orders')
    op.drop_index(op.f('ix_sn_supplier_item_orders_organization_id'), table_name='sn_supplier_item_orders')
    op.drop_index(op.f('ix_sn_supplier_item_orders_customer_user_id'), table_name='sn_supplier_item_orders')
    op.drop_table('sn_supplier_item_orders')
    op.drop_index(op.f('ix_sn_shopify_orders_status'), table_name='sn_shopify_orders')
    op.drop_index(op.f('ix_sn_shopify_orders_shopify_order_id'), table_name='sn_shopify_orders')
    op.drop_index(op.f('ix_sn_shopify_orders_organization_id'), table_name='sn_shopify_orders')
    op.drop_index(op.f('ix_sn_shopify_orders_next_retry_at'), table_name='sn_shopify_orders')
    op.drop_index(op.f('ix_sn_shopify_orders_fulfillment_status'), table_name='sn_shopify_orders')
    op.drop_index(op.f('ix_sn_shopify_orders_customer_user_id'), table_name='sn_shopify_orders')
    op.drop_table('sn_shopify_orders')
    op.drop_index(op.f('ix_sn_shop_orders_status'), table_name='sn_shop_orders')
    op.drop_index(op.f('ix_sn_shop_orders_organization_id'), table_name='sn_shop_orders')
    op.drop_index(op.f('ix_sn_shop_orders_customer_user_id'), table_name='sn_shop_orders')
    op.drop_table('sn_shop_orders')
    op.drop_table('sn_permissions')
    op.drop_index(op.f('ix_sn_market_orders_status'), table_name='sn_market_orders')
    op.drop_index(op.f('ix_sn_market_orders_organization_id'), table_name='sn_market_orders')
    op.drop_index(op.f('ix_sn_market_orders_fulfillment_status'), table_name='sn_market_orders')
    op.drop_index(op.f('ix_sn_market_orders_customer_user_id'), table_name='sn_market_orders')
    op.drop_table('sn_market_orders')
    op.drop_index(op.f('ix_sn_credit_ledger_type'), table_name='sn_credit_ledger')
    op.drop_index(op.f('ix_sn_credit_ledger_to_wallet_id'), table_name='sn_credit_ledger')
    op.drop_index(op.f('ix_sn_credit_ledger_reference_sosnet_market_order_id'), table_name='sn_credit_ledger')
    op.drop_index(op.f('ix_sn_credit_ledger_organization_id'), table_name='sn_credit_ledger')
    op.drop_index(op.f('ix_sn_credit_ledger_from_wallet_id'), table_name='sn_credit_ledger')
    op.drop_table('sn_credit_ledger')
    op.drop_index(op.f('ix_sn_cj_orders_status'), table_name='sn_cj_orders')
    op.drop_index(op.f('ix_sn_cj_orders_organization_id'), table_name='sn_cj_orders')
    op.drop_index(op.f('ix_sn_cj_orders_next_retry_at'), table_name='sn_cj_orders')
    op.drop_index(op.f('ix_sn_cj_orders_fulfillment_status'), table_name='sn_cj_orders')
    op.drop_index(op.f('ix_sn_cj_orders_customer_user_id'), table_name='sn_cj_orders')
    op.drop_index(op.f('ix_sn_cj_orders_cj_payment_status'), table_name='sn_cj_orders')
    op.drop_index(op.f('ix_sn_cj_orders_cj_order_id'), table_name='sn_cj_orders')
    op.drop_table('sn_cj_orders')
    op.drop_index(op.f('ix_sn_aliexpress_orders_status'), table_name='sn_aliexpress_orders')
    op.drop_index(op.f('ix_sn_aliexpress_orders_out_order_id'), table_name='sn_aliexpress_orders')
    op.drop_index(op.f('ix_sn_aliexpress_orders_organization_id'), table_name='sn_aliexpress_orders')
    op.drop_index(op.f('ix_sn_aliexpress_orders_next_retry_at'), table_name='sn_aliexpress_orders')
    op.drop_index(op.f('ix_sn_aliexpress_orders_fulfillment_status'), table_name='sn_aliexpress_orders')
    op.drop_index(op.f('ix_sn_aliexpress_orders_customer_user_id'), table_name='sn_aliexpress_orders')
    op.drop_index(op.f('ix_sn_aliexpress_orders_aliexpress_order_id'), table_name='sn_aliexpress_orders')
    op.drop_table('sn_aliexpress_orders')
    op.execute("DROP SEQUENCE IF EXISTS sn_order_number_seq")
