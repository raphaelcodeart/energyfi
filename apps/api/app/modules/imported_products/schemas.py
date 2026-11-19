import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ImportProviderCreate(BaseModel):
    provider_type: str
    name: str = Field(min_length=1, max_length=128)
    base_url: str | None = Field(default=None, max_length=500)
    api_key: str | None = Field(default=None, max_length=500)
    enabled: bool = True


class ImportProviderUpdate(BaseModel):
    """Partial update (exclude_unset): omitted fields, including api_key, keep
    their stored value, so renaming a provider never blanks its key."""

    name: str | None = Field(default=None, min_length=1, max_length=128)
    base_url: str | None = Field(default=None, max_length=500)
    api_key: str | None = Field(default=None, max_length=500)
    #: AliExpress DS app credentials; the secret is masked like api_key.
    app_key: str | None = Field(default=None, max_length=64)
    app_secret: str | None = Field(default=None, max_length=255)
    enabled: bool | None = None


class ImportProviderRead(BaseModel):
    """Never returns api_key raw: only a masked last-four, as for the Stripe
    secret key."""

    id: uuid.UUID
    provider_type: str
    name: str
    base_url: str | None
    api_key_configured: bool
    api_key_last4: str | None
    app_key: str | None
    app_secret_configured: bool
    app_secret_hint: str | None
    #: The seller account is authorized and the token is still valid.
    connected: bool
    account_label: str | None
    token_expires_at: datetime | None
    last_connected_at: datetime | None
    enabled: bool
    created_at: datetime


class AliexpressAuthorizeUrlRead(BaseModel):
    url: str
    #: Exact address to register as "Callback URL" in the AliExpress app.
    callback_url: str


class AliexpressTestRead(BaseModel):
    provider: ImportProviderRead
    #: Sample category names proving the DS permission works.
    sample_categories: list[str]


class ImportedProductCreate(BaseModel):
    provider_id: uuid.UUID
    external_id: str | None = Field(default=None, max_length=255)
    external_url: str | None = Field(default=None, max_length=1000)
    name: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=2000)
    image_url: str | None = Field(default=None, max_length=1000)
    price_cents: int = Field(gt=0)
    credit_discount_percentage: int = Field(default=30, ge=0, le=99)
    status: str = "ACTIVE"


class ImportedProductUpdate(BaseModel):
    external_id: str | None = Field(default=None, max_length=255)
    external_url: str | None = Field(default=None, max_length=1000)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    image_url: str | None = Field(default=None, max_length=1000)
    price_cents: int | None = Field(default=None, gt=0)
    credit_discount_percentage: int | None = Field(default=None, ge=0, le=99)
    status: str | None = None


class ImportedProductAdminRead(BaseModel):
    """Full admin detail including provider/external linkage; see
    ImportedProductRead for the customer shape."""

    id: uuid.UUID
    provider_id: uuid.UUID
    provider_name: str
    external_id: str | None
    external_url: str | None
    name: str
    description: str
    image_url: str | None
    price_cents: int
    credit_discount_percentage: int
    status: str
    created_at: datetime
    #: Shop categories of this product. They are shown in the AliExpress tab,
    #: so they are categorized under the "aliexpress" shop.
    category_ids: list[uuid.UUID] = []


class ImportedProductRead(BaseModel):
    """Customer-facing card. Omits provider_id/external_id/external_url so
    nothing in the response reveals the AliExpress source."""

    id: uuid.UUID
    name: str
    description: str
    image_url: str | None
    price_cents: int
    credit_discount_percentage: int
    #: price_cents is the full (card) price; bank transfer takes this % off.
    bank_transfer_discount_percentage: int = 0
    #: As in ImportedProductAdminRead.category_ids; lets the customer filter
    #: the grid without a call per product.
    category_ids: list[uuid.UUID] = []


class ImportedOrderRead(BaseModel):
    """Like orders/schemas.py::OrderRead without cashback fields: imported
    product orders never earn cashback."""

    id: uuid.UUID
    customer_user_id: uuid.UUID
    customer_display_name: str
    imported_product_id: uuid.UUID
    product_name: str
    product_image_url: str | None = None
    created_by_user_id: uuid.UUID
    amount_cents: int
    credit_applied_cents: int
    residual_amount_cents: int
    #: Bank-transfer discount (frozen) and the residual net of it.
    bank_transfer_discount_cents: int = 0
    amount_due_cents: int = 0
    bank_transfer_discount_percentage: int = 0
    #: VAT included in the charged amount, frozen on the order (prices are
    #: VAT-inclusive; nothing is added on top).
    vat_percentage: int = 0
    vat_amount_cents: int = 0
    status: str
    payment_method: str
    stripe_checkout_session_id: str | None = None
    payment_proof_uploaded_at: datetime | None = None
    note: str | None
    paid_at: datetime | None
    cancelled_at: datetime | None
    cancellation_reason: str | None
    created_at: datetime


class ImportedOrderQuoteRead(BaseModel):
    imported_product_id: uuid.UUID
    product_name: str
    amount_cents: int
    credit_discount_percentage: int
    max_creditable_cents: int
    customer_wallet_balance_cents: int
    bank_transfer_available: bool
    card_available: bool
    bank_transfer_discount_percentage: int = 0
    #: amount_cents paid entirely by bank transfer, after the discount.
    bank_transfer_amount_cents: int = 0


class ImportedOrderCreateRequest(BaseModel):
    customer_user_id: uuid.UUID
    imported_product_id: uuid.UUID
    credit_applied_cents: int = Field(default=0, ge=0)
    payment_method: str = "BANK_TRANSFER"
    note: str | None = Field(default=None, max_length=1000)


class ImportedOrderSelfCreateRequest(BaseModel):
    imported_product_id: uuid.UUID
    credit_applied_cents: int = Field(default=0, ge=0)
    payment_method: str = "BANK_TRANSFER"
    otp_code: str | None = None
    note: str | None = Field(default=None, max_length=1000)


class ImportedOrderCreditOtpRequest(BaseModel):
    imported_product_id: uuid.UUID
    credit_applied_cents: int = Field(gt=0)


class ImportedOrderCancelRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class ImportedOrderPaymentMethodUpdate(BaseModel):
    payment_method: str


class PaymentProofUrlRead(BaseModel):
    url: str


class CheckoutSessionRead(BaseModel):
    checkout_url: str
