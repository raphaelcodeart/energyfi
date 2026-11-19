"""Shop Sosnet Partner (Marketplace 1): CJ Dropshipping integration.

Own tables: nothing here touches catalog.products, orders or
imported_products, so the feature can be disabled or removed cleanly.
Products are imported from CJ's API with their variants and priced from the
USD cost by the administrator's rules; paid orders are sent to CJ, paid
from the CJ balance and tracked to delivery. Purchases only SPEND
SosnetCash, never earn cashback.
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
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.foundation.db import Base, TimestampMixin, UUIDPKMixin
from app.modules.marketplaces.models import SHOP_ORDER_NUMBER_SEQ

#: Customer price rounding: up to x,90 / x,99, or none.
PRICE_ROUNDINGS = ("90", "99", "NONE")
#: Who pays CJ's shipping: added at checkout, or built into the price.
SHIPPING_MODES = ("CUSTOMER_PAYS", "INCLUDED")

CJ_PRODUCT_STATUSES = ("ACTIVE", "INACTIVE")

CJ_ORDER_STATUSES = ("AWAITING_PAYMENT", "PAID", "CANCELLED")
CJ_ORDER_PAYMENT_METHODS = ("BANK_TRANSFER", "CARD")

#: Status of a paid order on CJ.
#:   NOT_SENT      -- paid (or awaiting payment), not yet sent to CJ
#:   SENDING       -- claimed by one sender; nobody else may send it
#:   SENT          -- created on CJ, not yet paid there
#:   PROCESSING    -- paid on CJ, being prepared (CJ: UNSHIPPED)
#:   SHIPPED       -- in transit, tracking number known
#:   DELIVERED     -- delivered
#:   ERROR         -- rejected by CJ (balance, stock, address...), see forward_error
#:   CJ_CANCELLED  -- cancelled on CJ
FULFILLMENT_STATUSES = (
    "NOT_SENT", "SENDING", "SENT", "PROCESSING", "SHIPPED", "DELIVERED", "ERROR", "CJ_CANCELLED",
)
#: Payment to CJ, tracked apart from creation so an order awaiting funds
#: never looks "in preparation".
#:   NOT_REQUIRED       nothing to pay yet (customer not paid / not on CJ)
#:   PENDING            on CJ, payment not attempted yet
#:   PAYMENT_REQUIRED   CJ balance insufficient: pay on CJ's payment page or
#:                      top up the balance (not an error)
#:   PAID               CJ has the money (per CJ's own order status)
#:   FAILED             payment attempt failed for another reason
CJ_PAYMENT_STATUSES = ("NOT_REQUIRED", "PENDING", "PAYMENT_REQUIRED", "PAID", "FAILED")
#: Category of the last error; decides whether a retry makes sense.
CJ_ERROR_KINDS = ("TEMPORARY", "AUTHENTICATION", "VALIDATION", "INSUFFICIENT_BALANCE", "FATAL")


class CjSettings(UUIDPKMixin, TimestampMixin, Base):
    """An organization's CJ account and pricing rules (one row). A dedicated
    table because the integration rotates the tokens itself. `api_key` and
    tokens are never returned by any endpoint."""

    __tablename__ = "sn_cj_config"
    __table_args__ = (
        UniqueConstraint("organization_id"),
        CheckConstraint("default_credit_percentage BETWEEN 0 AND 99", name="default_credit_below_100"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_tenants.id"))
    api_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    access_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    access_token_expires_at: Mapped[datetime | None] = mapped_column(nullable=True)
    refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    refresh_token_expires_at: Mapped[datetime | None] = mapped_column(nullable=True)
    #: CJ account id, returned with the token; also the webhook signing secret.
    open_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    #: Sandbox orders (nothing charged or shipped); on by default so a new
    #: setup starts with dry runs.
    sandbox: Mapped[bool] = mapped_column(Boolean, default=True)
    #: EUR per 1 USD.
    usd_eur_rate: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=Decimal("0.92"))
    markup_percentage: Mapped[int] = mapped_column(Integer, default=100)
    markup_fixed_cents: Mapped[int] = mapped_column(Integer, default=0)
    price_rounding: Mapped[str] = mapped_column(String(8), default="90")
    shipping_mode: Mapped[str] = mapped_column(String(16), default="CUSTOMER_PAYS")
    #: Default SosnetCash percentage for new imports (never 100).
    default_credit_percentage: Mapped[int] = mapped_column(Integer, default=30)
    destination_country: Mapped[str] = mapped_column(String(2), default="IT")
    #: Auto-create paid orders on CJ and pay from the balance when it
    #: suffices (otherwise PAYMENT_REQUIRED).
    auto_forward: Mapped[bool] = mapped_column(Boolean, default=True)
    last_balance_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    last_balance_at: Mapped[datetime | None] = mapped_column(nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(nullable=True)


class CjProduct(UUIDPKMixin, TimestampMixin, Base):
    """A CJ product chosen for sale, with an admin-set Italian name and
    description. Prices live on the variants."""

    __tablename__ = "sn_cj_items"
    __table_args__ = (
        UniqueConstraint("organization_id", "cj_pid"),
        CheckConstraint("credit_discount_percentage BETWEEN 0 AND 99", name="credit_below_100"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_tenants.id"), index=True
    )
    cj_pid: Mapped[str] = mapped_column(String(64))
    cj_sku: Mapped[str | None] = mapped_column(String(64), nullable=True)
    name: Mapped[str] = mapped_column(String(255))
    #: CJ's own (English) name, kept to recognize the product on CJ.
    name_en: Mapped[str | None] = mapped_column(String(500), nullable=True)
    description: Mapped[str] = mapped_column(String(8000), default="")
    image_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    images: Mapped[list] = mapped_column(JSONB, default=list)
    category_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    #: CJ ship-from warehouse (CN, US, DE...), chosen at import based on stock.
    origin_country: Mapped[str] = mapped_column(String(2), default="CN")
    #: Cheapest shipping estimate to the destination at the last sync.
    shipping_estimate_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    shipping_days: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE", index=True)
    credit_discount_percentage: Mapped[int] = mapped_column(Integer, default=30)
    #: Per-product markup override.
    markup_percentage: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(nullable=True)
    sync_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_accounts.id"))
    updated_at: Mapped[datetime | None] = mapped_column(nullable=True)


class CjVariant(UUIDPKMixin, TimestampMixin, Base):
    """A buyable variant. `cost_usd` is CJ's price; `price_cents` is
    recomputed on every sync unless `price_override_cents` is set."""

    __tablename__ = "sn_cj_item_variants"
    __table_args__ = (UniqueConstraint("product_id", "cj_vid"),)

    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_cj_items.id"), index=True)
    cj_vid: Mapped[str] = mapped_column(String(64))
    cj_sku: Mapped[str | None] = mapped_column(String(128), nullable=True)
    label: Mapped[str] = mapped_column(String(255), default="")
    image_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    weight_g: Mapped[int] = mapped_column(Integer, default=0)
    price_cents: Mapped[int] = mapped_column(BigInteger)
    price_override_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    inventory: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    #: Still offered by CJ at the last sync.
    available_on_cj: Mapped[bool] = mapped_column(Boolean, default=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(nullable=True)


class CjOrder(UUIDPKMixin, TimestampMixin, Base):
    """A customer purchase: the common checkout plus delivery address,
    shipping cost and its lifecycle on CJ. Amounts are frozen at order time
    with the CJ cost and exchange rate, so each order's margin can be read
    back later."""

    __tablename__ = "sn_cj_orders"
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
    cj_product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_cj_items.id"))
    cj_variant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_cj_item_variants.id"))
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
    logistic_name: Mapped[str] = mapped_column(String(64))
    origin_country: Mapped[str] = mapped_column(String(2), default="CN")
    shipping_days: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # --- CJ cost at order time ---
    unit_cost_usd: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    shipping_cost_usd: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal(0))
    usd_eur_rate: Mapped[Decimal] = mapped_column(Numeric(10, 6))

    # --- Lifecycle on CJ ---
    fulfillment_status: Mapped[str] = mapped_column(String(16), default="NOT_SENT", index=True)
    sandbox: Mapped[bool] = mapped_column(Boolean, default=False)
    cj_order_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    cj_order_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    cj_amount_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    forwarded_at: Mapped[datetime | None] = mapped_column(nullable=True)
    forwarded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_accounts.id"), nullable=True
    )
    forward_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    tracking_number: Mapped[str | None] = mapped_column(String(128), nullable=True)
    tracking_provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    shipped_at: Mapped[datetime | None] = mapped_column(nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_cj_sync_at: Mapped[datetime | None] = mapped_column(nullable=True)
    # --- Payment to CJ, tracked separately --------------------------------
    #: CJ's "SD..." order code; cj_order_id holds CJ's numeric order id.
    cj_order_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    cj_shipment_order_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    #: CJ's page to pay this single order (card/PayPal), when CJ provides it.
    cj_pay_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    cj_payment_status: Mapped[str] = mapped_column(String(24), default="NOT_REQUIRED", index=True)
    cj_product_amount_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    cj_postage_amount_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    cj_ioss_amount_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    cj_paid_at: Mapped[datetime | None] = mapped_column(nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    last_attempt_at: Mapped[datetime | None] = mapped_column(nullable=True)
    next_retry_at: Mapped[datetime | None] = mapped_column(nullable=True, index=True)
    last_error_kind: Mapped[str | None] = mapped_column(String(24), nullable=True)


class CjOrderItem(UUIDPKMixin, TimestampMixin, Base):
    """One line of a CJ order (cart), shaped like `AliexpressOrderItem`.

    Money stays on the header. Product name, variant label and SosnetCash cap
    are **frozen**. Supplier order number and tracking live on the line
    because one order may ship in several parcels (e.g. two warehouses).
    """

    __tablename__ = "sn_cj_order_lines"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="quantity_positive"),
        UniqueConstraint("order_id", "variant_id", name="uq_sn_cj_order_lines_variant"),
    )

    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_cj_orders.id", ondelete="CASCADE"), index=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_cj_items.id"))
    variant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_cj_item_variants.id"))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    unit_price_cents: Mapped[int] = mapped_column(BigInteger)
    product_name: Mapped[str] = mapped_column(String(255))
    variant_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    credit_discount_percentage: Mapped[int] = mapped_column(Integer, default=0)
    supplier_order_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    tracking_number: Mapped[str | None] = mapped_column(String(128), nullable=True)
    tracking_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    tracking_company: Mapped[str | None] = mapped_column(String(128), nullable=True)
    #: CJ cost and ship-from warehouse per line, so an order mixing
    #: warehouses (which CJ cannot ship at once) is caught in time.
    unit_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    origin_country: Mapped[str | None] = mapped_column(String(8), nullable=True)
