"""Marketplace 3: AliExpress dropshipping integration.

Isolated like CJ (Marketplace 1) and Shopify (Marketplace 2): its own tables,
never touching catalog.products, orders, cj_*, shopify_* or the hand-curated
`imported_products`, so it can be disabled or removed independently.

Built on the AliExpress Open Platform DS API: search the catalog, import a
product with its SKUs and real cost, reprice on every sync, and forward paid
orders to AliExpress, tracking them until delivery.

Access requires an app on openservice.aliexpress.com (App Key + App Secret)
plus the seller account's authorisation, which yields the access token sent
with every call. Credentials live in `aliexpress_settings`, one row per
organization.

For the customer it is another Shop tab ("Marketplace 3", see
marketplaces/rules.py) with the shared checkout, SosnetCash rules, bank
transfer discount, order history and accounting.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.foundation.db import Base, TimestampMixin, UUIDPKMixin
from app.modules.marketplaces.models import SHOP_ORDER_NUMBER_SEQ

#: Customer price rounding: up to x,90 / x,99, or none.
PRICE_ROUNDINGS = ("90", "99", "NONE")
#: Pricing base: the SKU's dropshipping price (our cost, `offer_sale_price`,
#: falling back to the sale price when absent) or its list price.
PRICE_BASES = ("COST", "PRICE")
#: Shipping: charged at checkout, or built into the price.
SHIPPING_MODES = ("CUSTOMER_PAYS", "INCLUDED")

ALIEXPRESS_PRODUCT_STATUSES = ("ACTIVE", "INACTIVE")
ALIEXPRESS_ORDER_STATUSES = ("AWAITING_PAYMENT", "PAID", "CANCELLED")
ALIEXPRESS_ORDER_PAYMENT_METHODS = ("BANK_TRANSFER", "CARD")

#: Supplier-side state of a paid order.
#:   NOT_SENT   -- not placed on AliExpress yet
#:   SENDING    -- claimed by one sender; no one else may send it
#:   SENT       -- placed, not shipped yet
#:   SHIPPED    -- shipped; tracking set when the supplier provides it
#:   DELIVERED  -- delivered
#:   ERROR      -- refused, or the response was lost; see forward_error
#:   CANCELLED  -- cancelled on AliExpress
FULFILLMENT_STATUSES = ("NOT_SENT", "SENDING", "SENT", "SHIPPED", "DELIVERED", "ERROR", "CANCELLED")
ERROR_KINDS = ("TEMPORARY", "AUTHENTICATION", "VALIDATION", "FATAL")


class AliexpressSettings(UUIDPKMixin, TimestampMixin, Base):
    """Per-organization AliExpress app credentials, authorised account and
    pricing rules. `app_secret`, `access_token` and `refresh_token` are never
    returned by any endpoint."""

    __tablename__ = "sn_aliexpress_config"
    __table_args__ = (UniqueConstraint("organization_id"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_tenants.id"))
    #: App registered on openservice.aliexpress.com (category "Drop Shipping").
    app_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    app_secret: Mapped[str | None] = mapped_column(String(255), nullable=True)
    #: Issued by the seller-account authorisation; client.py renews the
    #: expiring access token with the refresh token.
    access_token: Mapped[str | None] = mapped_column(String(500), nullable=True)
    refresh_token: Mapped[str | None] = mapped_column(String(500), nullable=True)
    token_expires_at: Mapped[datetime | None] = mapped_column(nullable=True)
    #: Account the token belongs to, as reported by the API.
    account_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_connected_at: Mapped[datetime | None] = mapped_column(nullable=True)
    #: Customer-facing tab is shown only when enabled.
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    #: Sent on every catalog and order call. Prices come back already
    #: converted, so currency_rate is normally 1; it covers accounts that can
    #: only answer in another currency.
    ship_to_country: Mapped[str] = mapped_column(String(2), default="IT")
    target_currency: Mapped[str] = mapped_column(String(3), default="EUR")
    target_language: Mapped[str] = mapped_column(String(8), default="it")
    #: EUR per unit of target_currency.
    currency_rate: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=Decimal(1))
    price_basis: Mapped[str] = mapped_column(String(8), default="COST")
    markup_percentage: Mapped[int] = mapped_column(Integer, default=100)
    markup_fixed_cents: Mapped[int] = mapped_column(Integer, default=0)
    price_rounding: Mapped[str] = mapped_column(String(8), default="90")
    shipping_mode: Mapped[str] = mapped_column(String(16), default="CUSTOMER_PAYS")
    #: Minimum shipping charged per order: max(real AliExpress cost, this).
    #: With shipping_mode=INCLUDED it is the amount built into the list price.
    shipping_minimum_cents: Mapped[int] = mapped_column(Integer, default=590)
    shipping_days: Mapped[str | None] = mapped_column(String(32), nullable=True, default="10-20")
    #: SosnetCash usable on a newly imported product (marketplaces/rules.py).
    default_credit_percentage: Mapped[int] = mapped_column(Integer, default=30)
    #: Forward the order to AliExpress automatically once paid.
    auto_forward: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime | None] = mapped_column(nullable=True)


class AliexpressProduct(UUIDPKMixin, TimestampMixin, Base):
    """An AliExpress product selected for sale, with its own Italian name and
    description. Prices live on the variants."""

    __tablename__ = "sn_aliexpress_items"
    __table_args__ = (
        UniqueConstraint("organization_id", "aliexpress_product_id"),
        CheckConstraint(
            "credit_discount_percentage >= 0 AND credit_discount_percentage <= 99",
            name="credit_discount_percentage_below_100",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_tenants.id"), index=True
    )
    #: AliExpress numeric product id, stored as text (it is long).
    aliexpress_product_id: Mapped[str] = mapped_column(String(128))
    #: Product page on AliExpress, for administrators.
    product_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    name: Mapped[str] = mapped_column(String(255))
    #: Original AliExpress title, to recognise the product there.
    source_title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    #: The seller's store name.
    vendor: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str] = mapped_column(String(8000), default="")
    image_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    images: Mapped[list] = mapped_column(JSONB, default=list)
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE", index=True)
    credit_discount_percentage: Mapped[int] = mapped_column(Integer, default=30)
    #: Overrides the organization's markup for this product only.
    markup_percentage: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(nullable=True)
    sync_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_accounts.id"))
    updated_at: Mapped[datetime | None] = mapped_column(nullable=True)


class AliexpressVariant(UUIDPKMixin, TimestampMixin, Base):
    """One buyable SKU. `cost_amount`/`source_price_amount` are in the
    settings' target currency; `price_cents` is the customer price,
    recomputed on every sync unless `price_override_cents` is set.

    `sku_attr` is required by AliExpress to place an order for the SKU."""

    __tablename__ = "sn_aliexpress_item_variants"
    __table_args__ = (UniqueConstraint("product_id", "aliexpress_sku_id"),)

    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_aliexpress_items.id"), index=True
    )
    aliexpress_sku_id: Mapped[str] = mapped_column(String(128))
    #: e.g. "14:193;5:100014064"; identifies the SKU in ds.order.create.
    sku_attr: Mapped[str | None] = mapped_column(String(500), nullable=True)
    #: Seller's own SKU code, if published.
    sku: Mapped[str | None] = mapped_column(String(128), nullable=True)
    label: Mapped[str] = mapped_column(String(255), default="")
    image_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    cost_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    source_price_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    price_cents: Mapped[int] = mapped_column(BigInteger)
    price_override_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    #: None when AliExpress does not report a stock for this SKU.
    inventory: Mapped[int | None] = mapped_column(Integer, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    #: Still on sale on AliExpress at the last sync.
    available_in_store: Mapped[bool] = mapped_column(Boolean, default=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(nullable=True)


class AliexpressOrder(UUIDPKMixin, TimestampMixin, Base):
    """A customer order: shared checkout (SosnetCash with OTP, then card or
    discounted bank transfer), delivery address, and supplier-side lifecycle.
    Lines are in AliexpressOrderItem; every amount is frozen at creation."""

    __tablename__ = "sn_aliexpress_orders"
    __table_args__ = (
        CheckConstraint("credit_applied_cents >= 0", name="credit_applied_non_negative"),
        CheckConstraint("credit_applied_cents <= amount_cents", name="credit_applied_not_over_amount"),
        CheckConstraint("vat_mode IN ('INCLUDED', 'ADDED')", name="vat_mode"),
        CheckConstraint("quantity > 0", name="quantity_positive"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_tenants.id"), index=True
    )
    customer_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_accounts.id"), index=True)
    aliexpress_product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_aliexpress_items.id")
    )
    aliexpress_variant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_aliexpress_item_variants.id")
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_accounts.id"))

    #: Customer-facing order number from the shared `sn_order_number_seq`
    #: (see marketplaces/models.py); database-assigned so it stays unique
    #: under concurrency.
    number: Mapped[int] = mapped_column(
        BigInteger, SHOP_ORDER_NUMBER_SEQ, server_default=SHOP_ORDER_NUMBER_SEQ.next_value(), unique=True
    )
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    unit_price_cents: Mapped[int] = mapped_column(BigInteger)
    #: Shipping charged to the customer: max(real cost, minimum).
    shipping_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    #: Real AliExpress shipping cost and the minimum in force at order time;
    #: shipping margin is `shipping_cents - supplier_shipping_cents`. NULL
    #: means "not recorded", never zero, so margins are not inflated.
    supplier_shipping_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    minimum_shipping_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    #: unit_price_cents x quantity + shipping_cents.
    amount_cents: Mapped[int] = mapped_column(BigInteger)
    credit_applied_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    #: Bank-transfer discount on the residual (marketplaces/rules.py); 0 for
    #: card. Paid in euro = amount - credit_applied - bank_transfer_discount.
    bank_transfer_discount_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    #: VAT rate and amount frozen at creation; how they relate to the price
    #: depends on `vat_mode` (see marketplaces/rules.py). 0 on orders without VAT.
    vat_percentage: Mapped[int] = mapped_column(Integer, default=0)
    vat_amount_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    #: VAT rule for this order: `INCLUDED` (VAT inside the price) or `ADDED`
    #: (VAT on top). The VAT columns above are read according to it.
    vat_mode: Mapped[str] = mapped_column(String(16), server_default="ADDED", default="ADDED")
    credit_debit_transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_credit_ledger.id"), nullable=True
    )

    status: Mapped[str] = mapped_column(String(16), default="AWAITING_PAYMENT", index=True)
    payment_method: Mapped[str] = mapped_column(String(16), default="BANK_TRANSFER")
    stripe_checkout_session_id: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
    note: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    payment_proof_storage_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    payment_proof_original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    payment_proof_uploaded_at: Mapped[datetime | None] = mapped_column(nullable=True)
    paid_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_accounts.id"), nullable=True
    )
    paid_at: Mapped[datetime | None] = mapped_column(nullable=True)
    cancelled_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_accounts.id"), nullable=True
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # --- Delivery ---
    recipient_name: Mapped[str] = mapped_column(String(128))
    recipient_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    address_line1: Mapped[str] = mapped_column(String(255))
    address_line2: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str] = mapped_column(String(128))
    province: Mapped[str] = mapped_column(String(64))
    postal_code: Mapped[str] = mapped_column(String(16))
    country_code: Mapped[str] = mapped_column(String(2), default="IT")
    shipping_days: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # --- AliExpress cost at order time (target currency) ---
    unit_cost_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    currency_rate: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=Decimal(1))

    # --- AliExpress lifecycle ---
    fulfillment_status: Mapped[str] = mapped_column(String(16), default="NOT_SENT", index=True)
    #: Our reference, sent as `out_order_id` so an order is never placed
    #: twice and can be looked up on AliExpress manually.
    out_order_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    #: AliExpress' order number.
    aliexpress_order_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    #: Raw supplier status string.
    aliexpress_order_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    forwarded_at: Mapped[datetime | None] = mapped_column(nullable=True)
    forwarded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_accounts.id"), nullable=True
    )
    forward_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    tracking_number: Mapped[str | None] = mapped_column(String(128), nullable=True)
    tracking_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    tracking_company: Mapped[str | None] = mapped_column(String(128), nullable=True)
    shipped_at: Mapped[datetime | None] = mapped_column(nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    last_attempt_at: Mapped[datetime | None] = mapped_column(nullable=True)
    next_retry_at: Mapped[datetime | None] = mapped_column(nullable=True, index=True)
    last_error_kind: Mapped[str | None] = mapped_column(String(24), nullable=True)


class AliexpressOrderItem(UUIDPKMixin, TimestampMixin, Base):
    """One line of an AliExpress order, one per variant.

    **All money stays on the order header** (`amount_cents`,
    `shipping_cents`, `vat_amount_cents`, `bank_transfer_discount_cents`,
    `credit_applied_cents`, the Stripe session), so payments, webhooks,
    accounting, emails and the orders panel work on the header alone. The
    header's product/variant/quantity/unit price columns mirror the first
    line.

    `aliexpress_order_id` and tracking are per line because AliExpress
    splits an order spanning several sellers into multiple orders
    (`order_list` in the `aliexpress.ds.order.create` response), each with
    its own tracking.
    """

    __tablename__ = "sn_aliexpress_order_lines"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="quantity_positive"),
        UniqueConstraint("order_id", "aliexpress_variant_id", name="uq_sn_aliexpress_order_lines_variant"),
    )

    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_aliexpress_orders.id", ondelete="CASCADE"), index=True
    )
    aliexpress_product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_aliexpress_items.id")
    )
    aliexpress_variant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_aliexpress_item_variants.id")
    )
    quantity: Mapped[int] = mapped_column(Integer, default=1)

    # --- Frozen at order creation ---
    #: Unit list price at purchase time.
    unit_price_cents: Mapped[int] = mapped_column(BigInteger)
    #: Our AliExpress unit cost, for margin reporting.
    unit_cost_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    #: AliExpress freight for this line in EUR cents. AliExpress quotes
    #: freight per product; the order's real cost is the sum over lines.
    supplier_shipping_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    #: Snapshot, so renaming or removing the product never alters past
    #: orders or their emails.
    product_name: Mapped[str] = mapped_column(String(255))
    variant_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    #: The product's SosnetCash cap at purchase time. The order's cap is the
    #: sum of per-line caps, not one percentage of the total.
    credit_discount_percentage: Mapped[int] = mapped_column(Integer, default=0)

    # --- Per-line AliExpress lifecycle (see docstring) ---
    aliexpress_order_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    tracking_number: Mapped[str | None] = mapped_column(String(128), nullable=True)
    tracking_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    tracking_company: Mapped[str | None] = mapped_column(String(128), nullable=True)
