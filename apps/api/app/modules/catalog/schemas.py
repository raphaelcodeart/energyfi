import uuid
from datetime import datetime

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.modules.catalog import pricing

PRODUCT_TYPES = {"ENERGY_CONTRACT", "DIGITAL", "PHYSICAL", "SUBSCRIPTION"}
# INTERNAL (default) is never discountable with wallet credits; the service
# layer enforces this. DROPSHIPPING/PARTNER may accept a credit discount.
PRODUCT_CATEGORIES = {"INTERNAL", "DROPSHIPPING", "PARTNER"}
MARGIN_TYPES = {"FIXED", "PERCENTAGE"}


class MarginFields(BaseModel):
    """Reference margin: a fixed amount or a percentage of the net sale
    amount, never both."""

    margin_type: str | None = None
    margin_amount_cents: int | None = Field(default=None, ge=0)
    margin_percentage: Decimal | None = Field(default=None, ge=0, le=100, decimal_places=4)

    @model_validator(mode="after")
    def _consistent_margin(self):
        if self.margin_type is None:
            return self
        if self.margin_type not in MARGIN_TYPES:
            raise ValueError("Tipo di margine non valido: FIXED o PERCENTAGE.")
        if self.margin_type == "FIXED" and self.margin_amount_cents is None:
            raise ValueError("Un margine fisso ha bisogno dell'importo.")
        if self.margin_type == "PERCENTAGE" and self.margin_percentage is None:
            raise ValueError("Un margine percentuale ha bisogno della percentuale.")
        return self


class ProductCategoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str
    requires_supply_point: bool
    is_active: bool


class ProductCategoryIn(BaseModel):
    code: str = Field(min_length=2, max_length=32, pattern=r"^[A-Za-z0-9_-]+$")
    name: str = Field(min_length=1, max_length=120)
    requires_supply_point: bool = False
    is_active: bool = True


class ProductCategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    requires_supply_point: bool | None = None
    is_active: bool | None = None


class ProductVersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    version_label: str
    name: str
    description: str
    image_url: str | None
    base_price_cents: int
    initial_fee_cents: int
    recurring_fee_cents: int
    billing_period: str
    vat_percentage: float | None
    contract_duration_months: int | None
    commission_tokens: dict[str, int]
    credit_discount_percentage: int
    cashback_enabled: bool
    contract_cashback_percentage: int
    first_referrer_bonus_enabled: bool
    first_referrer_bonus_cents: int
    margin_type: str | None = None
    margin_amount_cents: int | None = None
    margin_percentage: Decimal | None = None
    #: Derived, never stored, so it cannot disagree with the fields that drive
    #: behaviour (see pricing.cashback_mode_for).
    cashback_mode: str = pricing.CASHBACK_MODE_NONE
    #: Billing periods per contract and whole-contract net amount, computed
    #: server-side for the activation wizard.
    contract_billing_periods: int = 1
    contract_net_amount_cents: int = 0
    valid_from: datetime
    valid_to: datetime | None
    status: str

    @classmethod
    def from_version(
        cls, version, *, category: str | None = None, product_type: str | None = None
    ) -> "ProductVersionRead":
        """Build from a version. VAT lives in the tax_configuration JSONB, which
        from_attributes cannot read, so use this instead of model_validate()."""
        tax_configuration = version.tax_configuration or {}
        return cls(
            id=version.id,
            version_label=version.version_label,
            name=version.name,
            description=version.description,
            image_url=version.image_url,
            base_price_cents=version.base_price_cents,
            initial_fee_cents=version.initial_fee_cents,
            recurring_fee_cents=version.recurring_fee_cents,
            billing_period=version.billing_period,
            vat_percentage=tax_configuration.get("vat_percentage"),
            contract_duration_months=version.contract_duration_months,
            commission_tokens=version.commission_tokens or {},
            credit_discount_percentage=version.credit_discount_percentage,
            cashback_enabled=version.cashback_enabled,
            contract_cashback_percentage=version.contract_cashback_percentage,
            first_referrer_bonus_enabled=version.first_referrer_bonus_enabled,
            first_referrer_bonus_cents=version.first_referrer_bonus_cents,
            margin_type=version.margin_type,
            margin_amount_cents=version.margin_amount_cents,
            margin_percentage=version.margin_percentage,
            cashback_mode=pricing.cashback_mode_for(category=category, version=version),
            contract_billing_periods=pricing.contract_billing_periods(version, product_type=product_type),
            contract_net_amount_cents=pricing.contract_net_amount_cents(version, product_type=product_type),
            valid_from=version.valid_from,
            valid_to=version.valid_to,
            status=version.status,
        )


class ProductRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    code: str
    product_type: str
    energy_type: str | None
    customer_type: str
    status: str
    category: str
    commercial_category_id: uuid.UUID | None = None
    company_id: uuid.UUID | None = None


class ProductWithVersionsRead(ProductRead):
    versions: list[ProductVersionRead] = []
    #: See ProductCatalogRead.category_ids.
    category_ids: list[uuid.UUID] = []


class ProductCatalogRead(ProductRead):
    """Product with its current version, denormalized for list views to avoid
    per-product detail fetches."""

    current_version: ProductVersionRead | None = None
    #: Shop categories within the product's section, so the grid can filter
    #: locally. Unrelated to `category`, which selects the section.
    category_ids: list[uuid.UUID] = []


class ProductCreate(MarginFields):
    code: str
    product_type: str = "ENERGY_CONTRACT"  # ENERGY_CONTRACT / DIGITAL / PHYSICAL / SUBSCRIPTION
    energy_type: str | None = None  # ELECTRICITY / GAS / DUAL_FUEL, ENERGY_CONTRACT only
    # PRIVATE / BUSINESS / BOTH; legacy values collapse onto BUSINESS.
    customer_type: str = pricing.BOTH_PRODUCT_CUSTOMER_TYPES
    category: str = "INTERNAL"  # see PRODUCT_CATEGORIES
    commercial_category_id: uuid.UUID | None = None
    company_id: uuid.UUID | None = None
    # Initial version fields: a product is always created with its first version.
    version_label: str = "1.0"
    name: str
    description: str = ""
    image_url: str | None = None
    base_price_cents: int
    initial_fee_cents: int = 0
    recurring_fee_cents: int = 0
    billing_period: str = "MONTHLY"
    vat_percentage: float | None = None
    contract_duration_months: int | None = 12
    commission_tokens: dict[str, int] = {}
    # Forced to 0 / False for INTERNAL products by the service layer.
    credit_discount_percentage: int = Field(default=0, ge=0, le=100)
    cashback_enabled: bool = False
    # INTERNAL-only; forced to 0 / False for other categories.
    contract_cashback_percentage: int = Field(default=0, ge=0, le=100)
    first_referrer_bonus_enabled: bool = False
    first_referrer_bonus_cents: int = Field(default=0, ge=0)

    @field_validator("customer_type")
    @classmethod
    def validate_customer_type(cls, v: str) -> str:
        return pricing.normalize_product_customer_type(v)

    @field_validator("product_type")
    @classmethod
    def validate_product_type(cls, v: str) -> str:
        if v not in PRODUCT_TYPES:
            raise ValueError(f"product_type must be one of {sorted(PRODUCT_TYPES)}")
        return v

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str) -> str:
        if v not in PRODUCT_CATEGORIES:
            raise ValueError(f"category must be one of {sorted(PRODUCT_CATEGORIES)}")
        return v


class ProductVersionCreate(MarginFields):
    version_label: str
    name: str
    description: str = ""
    image_url: str | None = None
    base_price_cents: int
    initial_fee_cents: int = 0
    recurring_fee_cents: int = 0
    billing_period: str = "MONTHLY"
    vat_percentage: float | None = None
    contract_duration_months: int | None = 12
    commission_tokens: dict[str, int] = {}
    credit_discount_percentage: int = Field(default=0, ge=0, le=100)
    cashback_enabled: bool = False
    contract_cashback_percentage: int = Field(default=0, ge=0, le=100)
    first_referrer_bonus_enabled: bool = False
    first_referrer_bonus_cents: int = Field(default=0, ge=0)


class ProductVersionUpdate(MarginFields):
    name: str | None = None
    description: str | None = None
    image_url: str | None = None
    base_price_cents: int | None = None
    initial_fee_cents: int | None = None
    recurring_fee_cents: int | None = None
    vat_percentage: float | None = None
    contract_duration_months: int | None = None
    commission_tokens: dict[str, int] | None = None
    credit_discount_percentage: int | None = Field(default=None, ge=0, le=100)
    cashback_enabled: bool | None = None
    contract_cashback_percentage: int | None = Field(default=None, ge=0, le=100)
    first_referrer_bonus_enabled: bool | None = None
    first_referrer_bonus_cents: int | None = Field(default=None, ge=0)
    status: str | None = None


class ProductUpdate(BaseModel):
    status: str | None = None
    product_type: str | None = None
    energy_type: str | None = None
    category: str | None = None
    commercial_category_id: uuid.UUID | None = None
    company_id: uuid.UUID | None = None
    #: True detaches the product from its company (company_id None means "unchanged").
    clear_company: bool = False
    customer_type: str | None = None

    @field_validator("customer_type")
    @classmethod
    def validate_customer_type(cls, v: str | None) -> str | None:
        return None if v is None else pricing.normalize_product_customer_type(v)

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str | None) -> str | None:
        if v is not None and v not in PRODUCT_CATEGORIES:
            raise ValueError(f"category must be one of {sorted(PRODUCT_CATEGORIES)}")
        return v


class CompanyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str
    logo_url: str | None
    website_url: str | None
    max_network_depth: int | None
    is_active: bool
    products: int = 0


class CompanyWrite(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=2000)
    logo_url: str | None = Field(default=None, max_length=1000)
    website_url: str | None = Field(default=None, max_length=1000)
    #: Levels of a collaborator's network its products reach; None = no cap.
    max_network_depth: int | None = Field(default=None, ge=1, le=12)
    is_active: bool = True
