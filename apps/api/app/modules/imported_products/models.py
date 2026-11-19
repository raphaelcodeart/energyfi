import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.foundation.db import Base, TimestampMixin, UUIDPKMixin
from app.modules.marketplaces.models import SHOP_ORDER_NUMBER_SEQ

# Provider types offered in the admin "tipo di servizio" dropdown. A plain
# String column, not a DB constraint, so adding a value here is enough.
IMPORT_PROVIDER_TYPES = ["ALIEXPRESS"]


class ImportProvider(UUIDPKMixin, TimestampMixin, Base):
    """A configured external catalog source feeding the Shop's
    'Acquisti SOSNET' subcategory. A table rather than Organization.settings
    keys because an organization may have several (one per supplier/API).
    api_key is never returned raw (see service.py::to_provider_read_dict)."""

    __tablename__ = "sn_supplier_sources"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_tenants.id"), index=True
    )
    provider_type: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(128))
    base_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    api_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_accounts.id"))
    # AliExpress Dropshipping API app credentials plus the seller's expiring
    # access token and refresh token; none is ever returned raw.
    app_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    app_secret: Mapped[str | None] = mapped_column(String(255), nullable=True)
    access_token: Mapped[str | None] = mapped_column(String(500), nullable=True)
    refresh_token: Mapped[str | None] = mapped_column(String(500), nullable=True)
    token_expires_at: Mapped[datetime | None] = mapped_column(nullable=True)
    #: The AliExpress account the token belongs to, as reported by the API.
    account_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_connected_at: Mapped[datetime | None] = mapped_column(nullable=True)


class ImportedProduct(UUIDPKMixin, TimestampMixin, Base):
    """An imported catalog item. Looks like a normal Shop product to the
    customer (never labelled "AliExpress") but is deliberately not a
    catalog.products row, so the feature is removable without touching
    Product/ProductVersion. external_id/external_url allow sync dedupe. No
    cashback: these products only spend SosnetCash."""

    __tablename__ = "sn_supplier_items"
    __table_args__ = (
        CheckConstraint("credit_discount_percentage BETWEEN 0 AND 99", name="credit_below_100"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_tenants.id"), index=True
    )
    provider_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_supplier_sources.id"), index=True)
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Admin-only link to the original listing; excluded from the customer schema.
    external_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(String(2000), default="")
    image_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    price_cents: Mapped[int] = mapped_column(BigInteger)
    # 0-100: share of price_cents payable from wallet SosnetCash.
    #: 30 for a new product, never 100 (marketplaces/rules.py).
    credit_discount_percentage: Mapped[int] = mapped_column(Integer, default=30)
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE")  # ACTIVE / INACTIVE
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_accounts.id"))


# Same lifecycle as orders/models.py::ORDER_STATUSES, duplicated so this
# domain has no import dependency on `orders`.
IMPORTED_ORDER_STATUSES = ["AWAITING_PAYMENT", "PAID", "CANCELLED"]
IMPORTED_ORDER_PAYMENT_METHODS = ["BANK_TRANSFER", "CARD"]


class ImportedProductOrder(UUIDPKMixin, TimestampMixin, Base):
    """Order for an ImportedProduct, mirroring orders/models.py::Order's
    checkout (credit discount, OTP, bank transfer/card, Stripe webhook,
    payment proof) without cashback fields. Kept apart from `orders` so the
    feature stays removable."""

    __tablename__ = "sn_supplier_item_orders"
    __table_args__ = (
        CheckConstraint("credit_applied_cents >= 0", name="credit_applied_non_negative"),
        CheckConstraint("credit_applied_cents <= amount_cents", name="credit_applied_not_over_amount"),
        CheckConstraint("vat_mode IN ('INCLUDED', 'ADDED')", name="vat_mode"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_tenants.id"), index=True
    )
    customer_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_accounts.id"), index=True)
    imported_product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_supplier_items.id"))
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_accounts.id"))
    #: Customer-facing number from the sequence shared by all shops.
    number: Mapped[int] = mapped_column(
        BigInteger, SHOP_ORDER_NUMBER_SEQ, server_default=SHOP_ORDER_NUMBER_SEQ.next_value(), unique=True
    )

    amount_cents: Mapped[int] = mapped_column(BigInteger)
    credit_applied_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    #: Bank-transfer discount on the residual, frozen whenever the method is
    #: (re)chosen; 0 for card.
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
