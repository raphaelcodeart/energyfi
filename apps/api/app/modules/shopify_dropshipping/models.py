"""Marketplace 2: Shopify dropshipping integration.

Built like CJ and equally isolated (own tables, no dependency on catalog,
orders, imported_products or cj_*). The supplier is an organization-owned
Shopify store where a dropshipping app (DSers, Syncee, Spocket...) maintains
the catalog and fulfils orders. We read the catalog via the Admin API, the
administrator imports products at our price, and a paid order is created in
the store as a completed draft order for the app to pass on. Tracking is
read back from the order's fulfillments.
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
#: Pricing base: the variant's unit cost (usually the supplier price, set by
#: the dropshipping app; falls back to price) or the store's selling price.
PRICE_BASES = ("COST", "PRICE")
#: Shipping: flat amount added at checkout, or built into the price.
SHIPPING_MODES = ("CUSTOMER_PAYS", "INCLUDED")

SHOPIFY_PRODUCT_STATUSES = ("ACTIVE", "INACTIVE")
SHOPIFY_ORDER_STATUSES = ("AWAITING_PAYMENT", "PAID", "CANCELLED")
SHOPIFY_ORDER_PAYMENT_METHODS = ("BANK_TRANSFER", "CARD")

#: Status of a paid order in the Shopify store.
#:   NOT_SENT   -- not yet created in the store
#:   SENDING    -- claimed by one sender; nobody else may send it
#:   SENT       -- created in the store, not yet fulfilled
#:   SHIPPED    -- fulfilled (at least partly); tracking when available
#:   DELIVERED  -- delivered
#:   ERROR      -- rejected by the store, see forward_error
#:   CANCELLED  -- cancelled in the store
FULFILLMENT_STATUSES = ("NOT_SENT", "SENDING", "SENT", "SHIPPED", "DELIVERED", "ERROR", "CANCELLED")
ERROR_KINDS = ("TEMPORARY", "AUTHENTICATION", "VALIDATION", "FATAL")


class ShopifySettings(UUIDPKMixin, TimestampMixin, Base):
    """An organization's Shopify store and pricing rules (one row).
    `access_token` is never returned by any endpoint."""

    __tablename__ = "sn_shopify_config"
    __table_args__ = (UniqueConstraint("organization_id"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_tenants.id"))
    #: xxx.myshopify.com
    shop_domain: Mapped[str | None] = mapped_column(String(255), nullable=True)
    #: A fixed Admin API token (legacy custom app, shpat_...) or a Dev
    #: Dashboard app's Client ID + secret, exchanged for 24-hour tokens that
    #: client.py renews before `token_expires_at`.
    access_token: Mapped[str | None] = mapped_column(String(255), nullable=True)
    client_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    client_secret: Mapped[str | None] = mapped_column(String(255), nullable=True)
    token_expires_at: Mapped[datetime | None] = mapped_column(nullable=True)
    api_version: Mapped[str] = mapped_column(String(16), default="2025-07")
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    #: Store details reported by the last connection test.
    shop_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    shop_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    #: EUR per unit of store currency (1 for a EUR store).
    currency_rate: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=Decimal(1))
    price_basis: Mapped[str] = mapped_column(String(8), default="COST")
    markup_percentage: Mapped[int] = mapped_column(Integer, default=100)
    markup_fixed_cents: Mapped[int] = mapped_column(Integer, default=0)
    price_rounding: Mapped[str] = mapped_column(String(8), default="90")
    shipping_mode: Mapped[str] = mapped_column(String(16), default="CUSTOMER_PAYS")
    #: Flat per-order shipping when the customer pays shipping.
    shipping_flat_cents: Mapped[int] = mapped_column(Integer, default=590)
    shipping_days: Mapped[str | None] = mapped_column(String(32), nullable=True, default="7-15")
    #: SosnetCash share for newly imported products (marketplaces/rules.py).
    default_credit_percentage: Mapped[int] = mapped_column(Integer, default=30)
    #: Auto-create the order in the store once paid.
    auto_forward: Mapped[bool] = mapped_column(Boolean, default=True)
    last_connected_at: Mapped[datetime | None] = mapped_column(nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(nullable=True)


class ShopifyProduct(UUIDPKMixin, TimestampMixin, Base):
    """A store product chosen for sale, with an admin-set Italian name and
    description. Prices live on the variants."""

    __tablename__ = "sn_shopify_items"
    __table_args__ = (
        UniqueConstraint("organization_id", "shopify_product_id"),
        CheckConstraint(
            "credit_discount_percentage >= 0 AND credit_discount_percentage <= 99",
            name="credit_discount_percentage_below_100",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_tenants.id"), index=True
    )
    #: gid://shopify/Product/123
    shopify_product_id: Mapped[str] = mapped_column(String(128))
    handle: Mapped[str | None] = mapped_column(String(255), nullable=True)
    name: Mapped[str] = mapped_column(String(255))
    #: The store's own title, kept to recognize the product there.
    source_title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    vendor: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str] = mapped_column(String(8000), default="")
    image_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    images: Mapped[list] = mapped_column(JSONB, default=list)
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE", index=True)
    credit_discount_percentage: Mapped[int] = mapped_column(Integer, default=30)
    #: Per-product markup override.
    markup_percentage: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(nullable=True)
    sync_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_accounts.id"))
    updated_at: Mapped[datetime | None] = mapped_column(nullable=True)


class ShopifyVariant(UUIDPKMixin, TimestampMixin, Base):
    """A buyable variant. Source amounts are in store currency; `price_cents`
    is recomputed on every sync unless `price_override_cents` is set."""

    __tablename__ = "sn_shopify_item_variants"
    __table_args__ = (UniqueConstraint("product_id", "shopify_variant_id"),)

    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_shopify_items.id"), index=True
    )
    #: gid://shopify/ProductVariant/456
    shopify_variant_id: Mapped[str] = mapped_column(String(128))
    sku: Mapped[str | None] = mapped_column(String(128), nullable=True)
    label: Mapped[str] = mapped_column(String(255), default="")
    image_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    cost_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    source_price_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    price_cents: Mapped[int] = mapped_column(BigInteger)
    price_override_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    #: None when the store does not track stock for this variant.
    inventory: Mapped[int | None] = mapped_column(Integer, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    #: Present in the store at the last sync.
    available_in_store: Mapped[bool] = mapped_column(Boolean, default=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(nullable=True)


class ShopifyOrder(UUIDPKMixin, TimestampMixin, Base):
    """A customer purchase: the common checkout plus delivery address and its
    lifecycle in the Shopify store. Amounts are frozen at order time."""

    __tablename__ = "sn_shopify_orders"
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
    shopify_product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_shopify_items.id"))
    shopify_variant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_shopify_item_variants.id"))
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_accounts.id"))
    #: Customer-facing number from the sequence shared by all shops.
    number: Mapped[int] = mapped_column(
        BigInteger, SHOP_ORDER_NUMBER_SEQ, server_default=SHOP_ORDER_NUMBER_SEQ.next_value(), unique=True
    )

    quantity: Mapped[int] = mapped_column(Integer, default=1)
    unit_price_cents: Mapped[int] = mapped_column(BigInteger)
    shipping_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    #: Goods + VAT + shipping.
    amount_cents: Mapped[int] = mapped_column(BigInteger)
    credit_applied_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    #: Bank-transfer discount on the residual, frozen; 0 for card. Paid in
    #: euro = amount - credit_applied - bank_transfer_discount.
    bank_transfer_discount_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    #: VAT on the goods at full price, frozen at creation (marketplaces/rules.py).
    vat_percentage: Mapped[int] = mapped_column(Integer, default=0)
    vat_amount_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    #: `INCLUDED` (VAT inside the price) or `ADDED` (default); the VAT
    #: columns above mean different things under each mode.
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

    # --- Store cost at order time (store currency) ---
    unit_cost_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    currency_rate: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=Decimal(1))

    # --- Lifecycle in the Shopify store ---
    fulfillment_status: Mapped[str] = mapped_column(String(16), default="NOT_SENT", index=True)
    #: Kept so a retry completes the same draft.
    shopify_draft_order_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    #: gid://shopify/Order/...
    shopify_order_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    shopify_order_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    shopify_fulfillment_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
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


class ShopifyOrderItem(UUIDPKMixin, TimestampMixin, Base):
    """One line of a Shopify order (cart), shaped like `AliexpressOrderItem`.

    Money stays on the header. Product name, variant label and SosnetCash cap
    are **frozen**. Supplier order number and tracking live on the line
    because one order may ship in several parcels.
    """

    __tablename__ = "sn_shopify_order_lines"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="quantity_positive"),
        UniqueConstraint("order_id", "variant_id", name="uq_sn_shopify_order_lines_variant"),
    )

    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_shopify_orders.id", ondelete="CASCADE"), index=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_shopify_items.id"))
    variant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_shopify_item_variants.id"))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    unit_price_cents: Mapped[int] = mapped_column(BigInteger)
    product_name: Mapped[str] = mapped_column(String(255))
    variant_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    credit_discount_percentage: Mapped[int] = mapped_column(Integer, default=0)
    supplier_order_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    tracking_number: Mapped[str | None] = mapped_column(String(128), nullable=True)
    tracking_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    tracking_company: Mapped[str | None] = mapped_column(String(128), nullable=True)
    #: Our cost in the Shopify store, frozen on the line.
    unit_cost_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
