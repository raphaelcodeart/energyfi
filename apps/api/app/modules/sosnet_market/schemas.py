"""Browser-facing schemas for the Sosnet grocery shop.

No totals or order prices are accepted: checkout recomputes everything from
the catalog. Prices appear only where the administrator edits the catalog.
"""

import uuid

from pydantic import BaseModel, Field


class SosnetMarketSettingsRead(BaseModel):
    enabled: bool
    #: Paid orders are forwarded to the companies automatically.
    auto_forward: bool
    shipping_mode: str
    shipping_flat_cents: int
    shipping_days: str | None
    ship_to_country: str


class SosnetMarketSettingsUpdate(BaseModel):
    enabled: bool | None = None
    auto_forward: bool | None = None
    shipping_mode: str | None = None
    shipping_flat_cents: int | None = Field(default=None, ge=0, le=100000)
    shipping_days: str | None = Field(default=None, max_length=32)
    ship_to_country: str | None = Field(default=None, min_length=2, max_length=2)


class ProducerWrite(BaseModel):
    """The producing company. Only `name` is required so catalog entry is
    never blocked by missing details."""

    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=4000)
    website_url: str | None = Field(default=None, max_length=1000)
    logo_url: str | None = Field(default=None, max_length=1000)
    vat_number: str | None = Field(default=None, max_length=32)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=32)
    address: str | None = Field(default=None, max_length=500)


class ProducerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=4000)
    website_url: str | None = Field(default=None, max_length=1000)
    logo_url: str | None = Field(default=None, max_length=1000)
    vat_number: str | None = Field(default=None, max_length=32)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=32)
    address: str | None = Field(default=None, max_length=500)
    active: bool | None = None


class VariantWrite(BaseModel):
    label: str = Field(default="Unica", max_length=255)
    sku: str | None = Field(default=None, max_length=128)
    image_url: str | None = Field(default=None, max_length=1000)
    price_cents: int = Field(gt=0, le=10_000_000)
    #: `None` = stock not tracked; zero = sold out.
    inventory: int | None = Field(default=None, ge=0)
    active: bool = True


class VariantUpdate(BaseModel):
    label: str | None = Field(default=None, max_length=255)
    sku: str | None = Field(default=None, max_length=128)
    image_url: str | None = Field(default=None, max_length=1000)
    price_cents: int | None = Field(default=None, gt=0, le=10_000_000)
    inventory: int | None = Field(default=None, ge=0)
    active: bool | None = None


class ProductWrite(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=8000)
    image_url: str | None = Field(default=None, max_length=1000)
    images: list[str] = Field(default_factory=list)
    status: str = "ACTIVE"
    #: Share of the price payable in SosnetCash; never 100 (common rule).
    credit_discount_percentage: int = Field(default=30, ge=0, le=99)
    unit_cost_cents: int | None = Field(default=None, ge=0)
    producer_id: uuid.UUID | None = None
    #: At least one; a product without variants cannot be bought.
    variants: list[VariantWrite] = Field(min_length=1)


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=8000)
    image_url: str | None = Field(default=None, max_length=1000)
    images: list[str] | None = None
    status: str | None = None
    credit_discount_percentage: int | None = Field(default=None, ge=0, le=99)
    unit_cost_cents: int | None = Field(default=None, ge=0)
    producer_id: uuid.UUID | None = None


class SosnetMarketAddress(BaseModel):
    recipient_name: str = Field(min_length=2, max_length=128)
    recipient_phone: str | None = Field(default=None, max_length=32)
    address_line1: str = Field(min_length=3, max_length=255)
    address_line2: str | None = Field(default=None, max_length=255)
    city: str = Field(min_length=1, max_length=128)
    province: str = Field(min_length=1, max_length=64)
    postal_code: str = Field(min_length=3, max_length=16)


class SosnetMarketOrderSelfCreateRequest(BaseModel):
    variant_id: uuid.UUID
    quantity: int = Field(ge=1, le=10)
    address: SosnetMarketAddress
    credit_applied_cents: int = Field(default=0, ge=0)
    payment_method: str = "BANK_TRANSFER"
    otp_code: str | None = None
    note: str | None = Field(default=None, max_length=1000)


class SosnetMarketCartOrderRequest(BaseModel):
    """Cart checkout: the server-side cart, not the browser, defines what is bought."""

    address: SosnetMarketAddress
    credit_applied_cents: int = Field(default=0, ge=0)
    payment_method: str = "BANK_TRANSFER"
    otp_code: str | None = None
    note: str | None = Field(default=None, max_length=1000)


class SosnetMarketCartCreditOtpRequest(BaseModel):
    credit_applied_cents: int = Field(ge=1)


class SosnetMarketOrderCreditOtpRequest(BaseModel):
    variant_id: uuid.UUID
    quantity: int = Field(ge=1, le=10)
    credit_applied_cents: int = Field(ge=1)


class SosnetMarketOrderCancelRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class SosnetMarketOrderPaymentMethodUpdate(BaseModel):
    payment_method: str


class SosnetMarketShipRequest(BaseModel):
    tracking_number: str | None = Field(default=None, max_length=128)
    tracking_url: str | None = Field(default=None, max_length=1000)
    tracking_company: str | None = Field(default=None, max_length=128)


class CheckoutSessionRead(BaseModel):
    checkout_url: str
