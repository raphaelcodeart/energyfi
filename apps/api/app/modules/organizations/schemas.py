import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.foundation.normalization import normalize_email


class OrganizationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    status: str


class OrganizationSettingsRead(BaseModel):
    """Typed subset of Organization.settings (JSONB) that admins may edit, such
    as the bank account for bonifico payments (see invoice_redemptions/router.py
    GET /payment-info). Only these fields are read or written, so arbitrary
    JSON cannot be stored through this endpoint."""

    bank_iban: str | None
    bank_account_holder: str | None
    # Free text shown next to the IBAN wherever customers are asked to pay by
    # bank transfer, editable without retyping the account number.
    bank_transfer_instructions: str | None
    # Recipient of the new-ticket admin alert; falls back to
    # info@sosnet.mamify.ai when unset
    # (organizations/service.py::get_admin_notification_email).
    admin_notification_email: str | None
    #: PER_INSTALMENT (default) / UPFRONT: how an instalment contract earns its
    #: cashback; see organizations/service.py.
    contract_instalment_cashback_mode: str | None = None
    #: Discount (%) on a contract paid in one go; None = default (32).
    contract_full_payment_discount_percentage: int | None = None


class OrganizationSettingsUpdate(BaseModel):
    bank_iban: str | None = Field(default=None, max_length=42)
    bank_account_holder: str | None = Field(default=None, max_length=255)
    bank_transfer_instructions: str | None = Field(default=None, max_length=2000)
    admin_notification_email: str | None = Field(default=None, max_length=255)
    contract_instalment_cashback_mode: Literal["PER_INSTALMENT", "UPFRONT"] | None = None
    contract_full_payment_discount_percentage: int | None = Field(default=None, ge=0, le=90)

    @field_validator("admin_notification_email", mode="before")
    @classmethod
    def normalize_email_field(cls, v: object) -> object:
        return normalize_email(v) if isinstance(v, str) else v


class PaymentSettingsRead(BaseModel):
    """Secrets are never echoed: `stripe_secret_key` and `stripe_webhook_secret`
    are write-only, returning only whether they are set and a last-4 hint.
    `stripe_publishable_key` is public by design and returned whole."""

    stripe_publishable_key: str | None
    stripe_secret_key_configured: bool
    stripe_secret_key_last4: str | None
    stripe_webhook_secret_configured: bool


class PaymentSettingsUpdate(BaseModel):
    stripe_publishable_key: str | None = Field(default=None, max_length=255)
    stripe_secret_key: str | None = Field(default=None, max_length=255)
    stripe_webhook_secret: str | None = Field(default=None, max_length=255)
