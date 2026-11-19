import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class InvoiceRedemptionRead(BaseModel):
    """Built from service.py::_to_read_dict because partner and customer names
    are resolved joins."""

    id: uuid.UUID
    partner_id: uuid.UUID
    partner_name: str
    customer_user_id: uuid.UUID
    customer_display_name: str
    original_filename: str
    content_type: str
    declared_amount_cents: int
    confirmed_amount_cents: int | None
    # Amount the customer must pay to reach CREDITED; None until an admin
    # confirms the invoice amount.
    payment_due_cents: int | None
    payment_reference_code: str | None
    payment_method: str | None = None
    stripe_checkout_session_id: str | None = None
    payment_proof_uploaded_at: datetime | None = None
    status: str
    rejection_reason: str | None
    created_at: datetime
    verified_at: datetime | None
    credited_at: datetime | None


class InvoiceRedemptionUrlRead(BaseModel):
    url: str


class PaymentInfoRead(BaseModel):
    iban: str | None
    holder: str
    instructions: str | None


class InvoiceRedemptionVerifyRequest(BaseModel):
    """The admin-confirmed invoice amount, which drives the fee and the credit."""

    confirmed_amount_cents: int = Field(gt=0)


class InvoiceRedemptionRejectRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class InvoiceRedemptionPaymentMethodUpdate(BaseModel):
    """Switch a PAYMENT_PENDING redemption between BANK_TRANSFER and CARD."""

    payment_method: str


class InvoiceRedemptionCheckoutSessionRead(BaseModel):
    checkout_url: str


class InvoiceRedemptionPaymentProofUrlRead(BaseModel):
    url: str
