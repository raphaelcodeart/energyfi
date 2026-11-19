import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.foundation.db import Base, TimestampMixin, UUIDPKMixin

# SUBMITTED: document uploaded, awaiting admin review.
# PAYMENT_PENDING: admin confirmed the amount and generated the payment
#   reference; the customer owes payment_due_cents().
# CREDITED (terminal): payment confirmed by an admin (bank transfer) or by
#   Stripe (card); the wallet received a base row and a bonus row.
# REJECTED (terminal): from SUBMITTED or PAYMENT_PENDING.
INVOICE_REDEMPTION_STATUSES = ["SUBMITTED", "PAYMENT_PENDING", "CREDITED", "REJECTED"]

# How payment_due_cents() is paid once PAYMENT_PENDING. BANK_TRANSFER is
# confirmed by an admin, CARD by the Stripe webhook (as for orders).
INVOICE_REDEMPTION_PAYMENT_METHODS = ["BANK_TRANSFER", "CARD"]

# Percentage of the confirmed invoice amount used both as the fee the
# customer pays and as the bonus credited: a 100.00 invoice costs 5.00 and
# yields 105.00 of credit. Same figure as
# orders/service.py::ORDER_CASHBACK_PERCENTAGE.
CASHBACK_PERCENTAGE = 5

ALLOWED_INVOICE_CONTENT_TYPES = {"application/pdf", "image/jpeg", "image/png"}
MAX_INVOICE_BYTES = 15 * 1024 * 1024  # a phone photo of a bill, not a video


class InvoiceRedemption(UUIDPKMixin, TimestampMixin, Base):
    """A customer's request to turn part of an energy bill paid to a partner
    supplier into internal wallet credit. Not stored in `documents`, whose
    contract_id is mandatory; the row holds its own storage_key in the private
    bucket. Credit is minted only against a real external payment (confirmed
    bank transfer or Stripe charge), never against spending credit; see
    docs/business-rules.md#internal-wallet."""

    __tablename__ = "sn_receipt_claims"
    __table_args__ = (
        CheckConstraint(
            "confirmed_amount_cents IS NULL OR confirmed_amount_cents > 0",
            name="confirmed_amount_positive",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_tenants.id"), index=True
    )
    customer_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_accounts.id"), index=True)
    partner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_merchants.id"))

    storage_key: Mapped[str] = mapped_column(String(500), unique=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(BigInteger)

    # Customer-declared amount: only a hint for the admin, never trusted.
    declared_amount_cents: Mapped[int] = mapped_column(BigInteger)
    # Set by the admin after reading the document; the payment and credit are
    # computed from this, never from declared_amount_cents.
    confirmed_amount_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    # Code the customer puts in the bank transfer reference, letting an admin
    # match a wire to this redemption without relying on the amount.
    payment_reference_code: Mapped[str | None] = mapped_column(String(32), nullable=True, unique=True)

    status: Mapped[str] = mapped_column(String(16), default="SUBMITTED", index=True)
    rejection_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # BANK_TRANSFER once verify() opens the payment window; switchable to CARD
    # while PAYMENT_PENDING.
    payment_method: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # The webhook finds the redemption by this id. Unique so one session can
    # never credit two redemptions; a new checkout replaces it.
    stripe_checkout_session_id: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)

    # Optional bank-transfer receipt uploaded by the customer: advisory
    # evidence for the admin, never changes status by itself.
    payment_proof_storage_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    payment_proof_original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    payment_proof_uploaded_at: Mapped[datetime | None] = mapped_column(nullable=True)

    verified_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_accounts.id"), nullable=True
    )
    verified_at: Mapped[datetime | None] = mapped_column(nullable=True)
    credited_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_accounts.id"), nullable=True
    )
    credited_at: Mapped[datetime | None] = mapped_column(nullable=True)
