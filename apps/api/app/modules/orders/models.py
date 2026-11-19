import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.foundation.db import Base, TimestampMixin, UUIDPKMixin

# AWAITING_PAYMENT: initial state whenever a residual is owed after credit.
# PAID: terminal; residual confirmed (admin or Stripe), or credit covered the
#   full amount at creation.
# CANCELLED: terminal, only from AWAITING_PAYMENT; any applied credit is
#   refunded by reversing the PURCHASE_DEBIT row (see service.cancel_order).
ORDER_STATUSES = ["AWAITING_PAYMENT", "PAID", "CANCELLED"]

# How the residual is settled (irrelevant when it is 0). BANK_TRANSFER needs
# manual admin confirmation; CARD is marked PAID by the Stripe webhook.
ORDER_PAYMENT_METHODS = ["BANK_TRANSFER", "CARD"]


class Order(UUIDPKMixin, TimestampMixin, Base):
    """A purchase of a DROPSHIPPING/PARTNER product.

    Kept separate from Contract because contracts always require a supply
    point. Created either by the customer (self-checkout) or by an admin on
    the customer's behalf; both paths share one service function.
    """

    __tablename__ = "sn_shop_orders"
    __table_args__ = (
        CheckConstraint("credit_applied_cents >= 0", name="credit_applied_non_negative"),
        CheckConstraint("credit_applied_cents <= amount_cents", name="credit_applied_not_over_amount"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_tenants.id"), index=True
    )
    customer_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_accounts.id"), index=True)
    product_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_offer_versions.id"))
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_accounts.id"))

    # Frozen at creation so later price changes never rewrite past orders.
    amount_cents: Mapped[int] = mapped_column(BigInteger)
    credit_applied_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    # The PURCHASE_DEBIT row, so cancellation can reverse exactly that entry.
    credit_debit_transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_credit_ledger.id"), nullable=True
    )

    # Instant-cashback option (only if the product version enables it): the
    # customer pays an extra ORDER_CASHBACK_PERCENTAGE on the new-money
    # residual and receives that surcharge back as wallet credit once the
    # order is PAID. The surcharge is frozen at creation.
    cashback_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    cashback_surcharge_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    cashback_credited_at: Mapped[datetime | None] = mapped_column(nullable=True)

    status: Mapped[str] = mapped_column(String(16), default="AWAITING_PAYMENT", index=True)
    payment_method: Mapped[str] = mapped_column(String(16), default="BANK_TRANSFER")
    # Latest Stripe Checkout Session for a CARD residual; the webhook finds
    # the order through it. A retry overwrites it, so only the newest session
    # is valid. Unique so a session can never match two orders.
    stripe_checkout_session_id: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
    note: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    # Optional bank-transfer receipt uploaded by the customer. Advisory only:
    # it helps the admin confirm payment but never changes status by itself.
    # Stored in the private documents bucket via foundation/storage.py.
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
