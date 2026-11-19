import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class OrderRead(BaseModel):
    """Built from service.to_read_dict, since names come from joins."""

    id: uuid.UUID
    customer_user_id: uuid.UUID
    customer_display_name: str
    product_version_id: uuid.UUID
    product_name: str
    product_image_url: str | None = None
    created_by_user_id: uuid.UUID
    amount_cents: int
    credit_applied_cents: int
    residual_amount_cents: int
    cashback_requested: bool = False
    cashback_surcharge_cents: int = 0
    cashback_credited_at: datetime | None = None
    status: str
    payment_method: str
    stripe_checkout_session_id: str | None = None
    payment_proof_uploaded_at: datetime | None = None
    note: str | None
    paid_at: datetime | None
    cancelled_at: datetime | None
    cancellation_reason: str | None
    created_at: datetime


class OrderQuoteRead(BaseModel):
    """Pre-checkout quote: credit cap, wallet balance and which residual
    payment methods are enabled. The UI should hide disabled methods;
    create_order rejects them regardless."""

    product_version_id: uuid.UUID
    product_name: str
    amount_cents: int
    credit_discount_percentage: int
    max_creditable_cents: int
    customer_wallet_balance_cents: int
    bank_transfer_available: bool
    card_available: bool
    cashback_available: bool
    cashback_percentage: int


class OrderCreateRequest(BaseModel):
    customer_user_id: uuid.UUID
    product_version_id: uuid.UUID
    # Always explicit; never inferred from the balance.
    credit_applied_cents: int = Field(default=0, ge=0)
    # Ignored when credit covers the full amount.
    payment_method: str = "BANK_TRANSFER"
    # Instant cashback; valid only if the product allows it and a residual
    # remains after credit.
    cashback_requested: bool = False
    note: str | None = Field(default=None, max_length=1000)


class OrderSelfCreateRequest(BaseModel):
    """Self-checkout body. The customer is always the caller, never taken
    from the request."""

    product_version_id: uuid.UUID
    credit_applied_cents: int = Field(default=0, ge=0)
    payment_method: str = "BANK_TRANSFER"
    cashback_requested: bool = False
    # Emailed OTP, required and verified whenever wallet credit is spent.
    otp_code: str | None = None
    note: str | None = Field(default=None, max_length=1000)


class OrderCreditOtpRequest(BaseModel):
    """Request for a credit-spend OTP. Product name and price are resolved
    server-side so the email describes exactly what is being confirmed."""

    product_version_id: uuid.UUID
    credit_applied_cents: int = Field(gt=0)


class OrderCancelRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class OrderPaymentMethodUpdate(BaseModel):
    """Switch an AWAITING_PAYMENT order between BANK_TRANSFER and CARD."""

    payment_method: str


class PaymentProofUrlRead(BaseModel):
    url: str


class CheckoutSessionRead(BaseModel):
    checkout_url: str
