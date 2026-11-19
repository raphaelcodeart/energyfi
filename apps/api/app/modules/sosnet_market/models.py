"""Marketplace 4: «Fai la Spesa con Sosnet».

Behaves like the other imported-product shops for the customer (cart,
SosnetCash spend-only, bank-transfer discount, VAT added), but products
**do not come from a supplier**: the administrator enters them by hand.
Own tables, as `marketplaces/rules.py` requires, so disabling this shop
affects no other.

**Producers have their own table**, entered once and picked from a list;
showing who made the goods is the point of this shop. Order lines freeze the
producer name like the product name (see `SosnetMarketOrderItem`).
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.foundation.db import Base, TimestampMixin, UUIDPKMixin
from app.modules.marketplaces.models import SHOP_ORDER_NUMBER_SEQ

#: Stable shop key (cart, categories, labels); the display name is a setting.
SHOP = "sosnet_market"

#: Customer pays shipping, or it is already in the list price.
SHIPPING_MODES = ("CUSTOMER_PAYS", "INCLUDED")
PRODUCT_STATUSES = ("ACTIVE", "INACTIVE")
SOSNET_MARKET_ORDER_PAYMENT_METHODS = ("BANK_TRANSFER", "CARD")
MAX_QUANTITY = 10


class SosnetMarketSettings(UUIDPKMixin, TimestampMixin, Base):
    """Shop settings, one row per organization. No supplier, exchange rate or
    markup: the administrator enters the selling price directly."""

    __tablename__ = "sn_market_config"
    __table_args__ = (UniqueConstraint("organization_id"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_tenants.id"), index=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    shipping_mode: Mapped[str] = mapped_column(String(16), default="CUSTOMER_PAYS")
    #: Flat per-order shipping: with no supplier to query there is no real
    #: cost to compare against.
    shipping_flat_cents: Mapped[int] = mapped_column(Integer, default=0)
    shipping_days: Mapped[str | None] = mapped_column(String(32), nullable=True, default="3-5")
    ship_to_country: Mapped[str] = mapped_column(String(2), default="IT")
    #: Auto-forward paid orders to the producer. Off by default: emailing a
    #: real company is worth reviewing the first time.
    auto_forward: Mapped[bool] = mapped_column(Boolean, default=False)


class SosnetMarketProducer(UUIDPKMixin, TimestampMixin, Base):
    """A producing company, entered once for all its products. `name` is
    unique per organization to prevent near-duplicates."""

    __tablename__ = "sn_market_producers"
    __table_args__ = (UniqueConstraint("organization_id", "name", name="uq_sn_market_producers_name"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_tenants.id"), index=True
    )
    name: Mapped[str] = mapped_column(String(160))
    #: Shown on the product page: who they are, what they make, where.
    description: Mapped[str] = mapped_column(String(4000), default="")
    website_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    logo_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    #: Contact details for administration, not the customer.
    vat_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_accounts.id"))
    updated_at: Mapped[datetime | None] = mapped_column(nullable=True)


class SosnetMarketProduct(UUIDPKMixin, TimestampMixin, Base):
    """A shop product entered by hand, shaped like a supplier-imported one so
    it behaves the same for the customer. `producer_id` is **nullable** so a
    product can be entered before its producer; the customer page shows the
    producer only when set."""

    __tablename__ = "sn_market_items"
    __table_args__ = (
        CheckConstraint("credit_discount_percentage BETWEEN 0 AND 99", name="credit_percentage_range"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_tenants.id"), index=True
    )
    producer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_market_producers.id"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(String(8000), default="")
    image_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    images: Mapped[list] = mapped_column(JSONB, default=list)
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE", index=True)
    #: Share payable in SosnetCash; never 100% (marketplaces/rules.py).
    credit_discount_percentage: Mapped[int] = mapped_column(Integer, default=30)
    #: Our cost, if known: admin margin only, never shown to the customer.
    unit_cost_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_accounts.id"))
    updated_at: Mapped[datetime | None] = mapped_column(nullable=True)


class SosnetMarketVariant(UUIDPKMixin, TimestampMixin, Base):
    """A sellable variant (size, colour, format). Every product has at least
    one, so cart, quote and order always reference a variant; a lone variant
    is named «Unica» and hidden from the customer."""

    __tablename__ = "sn_market_item_variants"
    __table_args__ = (
        CheckConstraint("price_cents > 0", name="price_positive"),
        UniqueConstraint("product_id", "sku", name="uq_sn_market_item_variants_sku"),
    )

    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_market_items.id", ondelete="CASCADE"), index=True
    )
    label: Mapped[str] = mapped_column(String(255), default="Unica")
    sku: Mapped[str | None] = mapped_column(String(128), nullable=True)
    image_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    price_cents: Mapped[int] = mapped_column(BigInteger)
    #: `None` = stock not tracked (always sellable); zero = sold out.
    inventory: Mapped[int | None] = mapped_column(Integer, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class SosnetMarketOrder(UUIDPKMixin, TimestampMixin, Base):
    """A shop order, shaped like the other shops' so "I miei Ordini", the
    admin panel and accounting show one list. Lines live on
    `sosnet_market_order_items`; money stays on the header."""

    __tablename__ = "sn_market_orders"
    __table_args__ = (
        CheckConstraint("credit_applied_cents >= 0", name="credit_applied_non_negative"),
        CheckConstraint("credit_applied_cents <= amount_cents", name="credit_applied_not_over_amount"),
        CheckConstraint("vat_mode IN ('INCLUDED', 'ADDED')", name="vat_mode"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_tenants.id"), index=True
    )
    customer_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_accounts.id"), index=True)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_accounts.id"))
    #: Customer-facing number from the sequence shared by all shops.
    number: Mapped[int] = mapped_column(
        BigInteger, SHOP_ORDER_NUMBER_SEQ, server_default=SHOP_ORDER_NUMBER_SEQ.next_value(), unique=True
    )

    items_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    shipping_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    #: goods + VAT + shipping.
    amount_cents: Mapped[int] = mapped_column(BigInteger)
    credit_applied_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    bank_transfer_discount_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    #: VAT **added** to the goods, frozen at creation (marketplaces/rules.py).
    vat_percentage: Mapped[int] = mapped_column(Integer, default=0)
    vat_amount_cents: Mapped[int] = mapped_column(BigInteger, default=0)
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

    # --- Fulfilment (manual: the administrator records dispatch) ---
    fulfillment_status: Mapped[str] = mapped_column(String(16), default="NOT_SENT", index=True)
    #: Forwarding to the companies: when, by whom, last error. One timestamp
    #: covers all emails; recipients are the line producers.
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


class SosnetMarketOrderItem(UUIDPKMixin, TimestampMixin, Base):
    """Order line with product, variant and **producer** names, unit price and
    SosnetCash cap all frozen, so it reads the same regardless of later
    catalog changes."""

    __tablename__ = "sn_market_order_lines"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="quantity_positive"),
        UniqueConstraint("order_id", "variant_id", name="uq_sn_market_order_lines_variant"),
    )

    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_market_orders.id", ondelete="CASCADE"), index=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_market_items.id"))
    variant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_market_item_variants.id"))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    unit_price_cents: Mapped[int] = mapped_column(BigInteger)
    unit_cost_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    product_name: Mapped[str] = mapped_column(String(255))
    variant_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    #: Frozen so renaming a company never rewrites an order.
    producer_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    credit_discount_percentage: Mapped[int] = mapped_column(Integer, default=0)
