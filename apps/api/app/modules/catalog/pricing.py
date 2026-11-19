"""Single source of VAT and contract pricing.

Inputs are database rows only (a `ProductVersion` and a customer kind), never
browser-supplied numbers. The resulting breakdown is snapshotted onto the
contract at creation, so later changes to a product's VAT rate never restate
signed contracts.
"""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from app.modules.catalog.models import ProductVersion

# --- Who a product may be sold to -------------------------------------------
#
# Private customers, businesses, or both. Legacy values still parse and map
# onto BUSINESS so old rows and clients keep working.
PRIVATE_PRODUCT_CUSTOMER_TYPE = "PRIVATE"
BUSINESS_PRODUCT_CUSTOMER_TYPE = "BUSINESS"
BOTH_PRODUCT_CUSTOMER_TYPES = "BOTH"

PRODUCT_CUSTOMER_TYPES = frozenset(
    {PRIVATE_PRODUCT_CUSTOMER_TYPE, BUSINESS_PRODUCT_CUSTOMER_TYPE, BOTH_PRODUCT_CUSTOMER_TYPES}
)

_LEGACY_PRODUCT_CUSTOMER_TYPES = {
    "SOLE_PROPRIETOR": BUSINESS_PRODUCT_CUSTOMER_TYPE,
    "PMI": BUSINESS_PRODUCT_CUSTOMER_TYPE,
    "CONDOMINIUM": BUSINESS_PRODUCT_CUSTOMER_TYPE,
    "ENERGY_INTENSIVE": BUSINESS_PRODUCT_CUSTOMER_TYPE,
}

# --- Who pays VAT -----------------------------------------------------------
#
# Private customers pay no VAT; VAT-registered customers pay net + VAT. The
# only input is `customers.kind`.
#
# Intentionally distinct from customers/service.py::PRIVATE_LIKE_KINDS, which
# is about naming: a sole proprietor has a personal name but is VAT-liable.
VAT_LIABLE_CUSTOMER_KINDS = frozenset({"SOLE_PROPRIETOR", "COMPANY", "CONDOMINIUM"})


def normalize_product_customer_type(value: str | None) -> str:
    """Map any stored value onto PRIVATE / BUSINESS / BOTH. Unknown values
    become BOTH: better to show a product than to hide it silently."""
    if not value:
        return BOTH_PRODUCT_CUSTOMER_TYPES
    upper = value.strip().upper()
    if upper in PRODUCT_CUSTOMER_TYPES:
        return upper
    return _LEGACY_PRODUCT_CUSTOMER_TYPES.get(upper, BOTH_PRODUCT_CUSTOMER_TYPES)


def is_business_customer(customer_kind: str | None) -> bool:
    return (customer_kind or "").strip().upper() in VAT_LIABLE_CUSTOMER_KINDS


def product_allows_customer_kind(product_customer_type: str | None, customer_kind: str | None) -> bool:
    """Whether a product may be sold to this customer kind. Used for catalog
    filtering and enforced server-side on contract creation."""
    normalized = normalize_product_customer_type(product_customer_type)
    if normalized == BOTH_PRODUCT_CUSTOMER_TYPES:
        return True
    if normalized == BUSINESS_PRODUCT_CUSTOMER_TYPE:
        return is_business_customer(customer_kind)
    return not is_business_customer(customer_kind)


def vat_rate_for(*, product_vat_percentage: float | None, customer_kind: str | None) -> Decimal:
    """Applied VAT rate in percentage points. The customer decides whether VAT
    applies; the product decides the rate."""
    if not is_business_customer(customer_kind):
        return Decimal(0)
    if product_vat_percentage is None:
        return Decimal(0)
    rate = Decimal(str(product_vat_percentage))
    return rate if rate > 0 else Decimal(0)


@dataclass(frozen=True)
class PriceBreakdown:
    """What gets snapshotted onto a contract and shown to the customer."""

    net_amount_cents: int
    #: Percentage points (Decimal("22")), not a fraction.
    vat_rate: Decimal
    vat_amount_cents: int
    gross_amount_cents: int

    @property
    def has_vat(self) -> bool:
        return self.vat_amount_cents > 0


def _vat_cents(net_cents: int, vat_rate: Decimal) -> int:
    """VAT rounded half-up to the cent, computed in Decimal to avoid float
    error."""
    if vat_rate <= 0 or net_cents <= 0:
        return 0
    raw = (Decimal(net_cents) * vat_rate) / Decimal(100)
    return int(raw.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def compute_price(*, net_amount_cents: int, product_vat_percentage: float | None, customer_kind: str | None) -> PriceBreakdown:
    rate = vat_rate_for(product_vat_percentage=product_vat_percentage, customer_kind=customer_kind)
    vat_cents = _vat_cents(net_amount_cents, rate)
    return PriceBreakdown(
        net_amount_cents=net_amount_cents,
        vat_rate=rate,
        vat_amount_cents=vat_cents,
        gross_amount_cents=net_amount_cents + vat_cents,
    )


# --- Where a SosnetCash credit comes from -------------------------------------
#
# Three mutually exclusive modes, derived from `cashback_enabled` (orders) and
# `contract_cashback_percentage` (contracts) rather than stored, and exposed
# on the product API so the applicable rule is explicit.
CASHBACK_MODE_NONE = "NO_CASHBACK"
#: Partner/dropshipping: opt-in, funded by a surcharge
#: (orders/service.py::ORDER_CASHBACK_PERCENTAGE).
CASHBACK_MODE_STANDARD = "STANDARD"
#: SOSNET's own services: credited automatically on payment, no surcharge.
CASHBACK_MODE_AUTOMATIC_INTERNAL = "AUTOMATIC_INTERNAL_SERVICE"


def cashback_mode_for(*, category: str | None, version: ProductVersion) -> str:
    if (category or "").upper() == "INTERNAL":
        return (
            CASHBACK_MODE_AUTOMATIC_INTERNAL
            if int(version.contract_cashback_percentage or 0) > 0
            else CASHBACK_MODE_NONE
        )
    return CASHBACK_MODE_STANDARD if version.cashback_enabled else CASHBACK_MODE_NONE


def contract_cashback_cents(*, version: ProductVersion, gross_amount_cents: int) -> int:
    """SosnetCash credited for a paid contract: a percentage of the gross
    (VAT-included) amount actually paid, never an inflated base."""
    percentage = int(version.contract_cashback_percentage or 0)
    if percentage <= 0 or gross_amount_cents <= 0:
        return 0
    raw = (Decimal(gross_amount_cents) * Decimal(percentage)) / Decimal(100)
    return int(raw.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def product_vat_percentage(version: ProductVersion) -> float | None:
    """VAT rate from the `tax_configuration` JSONB (there is no column)."""
    configuration = version.tax_configuration or {}
    raw = configuration.get("vat_percentage")
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


#: Months per billing period. A recurring product's catalog price is per
#: period, not per contract.
BILLING_PERIOD_MONTHS = {"MONTHLY": 1, "QUARTERLY": 3, "ANNUAL": 12}


#: Only these types are priced per period. Other types are one-off purchases
#: at the listed price, whatever billing period or duration they carry.
RECURRING_PRODUCT_TYPES = frozenset({"ENERGY_CONTRACT", "SUBSCRIPTION"})


def contract_billing_periods(version: ProductVersion, *, product_type: str | None) -> int:
    """Billing periods in one contract term (12 for 12 months billed monthly).
    Falls back to 1, i.e. the listed price, for one-off types, missing
    durations or unknown periods."""
    if (product_type or "").upper() not in RECURRING_PRODUCT_TYPES:
        return 1
    duration = int(version.contract_duration_months or 0)
    period_months = BILLING_PERIOD_MONTHS.get((version.billing_period or "").upper())
    if duration <= 0 or period_months is None:
        return 1
    return max(1, duration // period_months)


def contract_net_amount_cents(version: ProductVersion, *, product_type: str | None) -> int:
    """Taxable amount of a whole contract, VAT excluded: the per-period
    `base_price_cents` times the number of periods in the term. Every price,
    payment plan and VAT figure derives from this.

    `initial_fee_cents` and `recurring_fee_cents` are intentionally not
    charged."""
    return int(version.base_price_cents or 0) * contract_billing_periods(version, product_type=product_type)


def compute_contract_price(
    *, version: ProductVersion, customer_kind: str | None, product_type: str | None
) -> PriceBreakdown:
    """Full contract price; the only entry point for contracts and payments."""
    return compute_price(
        net_amount_cents=contract_net_amount_cents(version, product_type=product_type),
        product_vat_percentage=product_vat_percentage(version),
        customer_kind=customer_kind,
    )
