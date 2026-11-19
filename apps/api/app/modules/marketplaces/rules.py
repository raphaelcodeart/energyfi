"""Rules shared by the imported-product shops.

- Marketplace 1 -- CJ Dropshipping (`cj_dropshipping`), admin menu "Shop CJ";
- Marketplace 2 -- Shopify (`shopify_dropshipping`), admin menu "Shop Shopify";
- Marketplace 3 -- AliExpress (`imported_products`, curated by hand), "Shop AliExpress".

Each shop keeps its own tables and supplier logic; the promises made to the
customer are identical everywhere and are defined here:

- **Bank transfer is cheaper.** Displayed prices are the same for every
  payment method; paying the euro part by bank transfer subtracts
  `bank_transfer_discount_percentage` (default 5%), computed server-side on
  the residual after SosnetCash and frozen on the order. A card surcharge is
  never applied: Italian law forbids it (art. 3, c. 4, D.Lgs. 11/2010; art. 62
  Codice del Consumo), while a discount for another method is allowed.
  See docs/business-rules.md#marketplace.
- **SosnetCash covers only part of the price.** These products never earn
  cashback, they can only spend it: a new product starts at
  DEFAULT_CREDIT_PERCENTAGE and an administrator may raise it up to
  MAX_CREDIT_PERCENTAGE.
- **The displayed price is net of VAT; VAT is added on top.** The shop shows
  "17,90 EUR + IVA" and the checkout quote lists VAT as its own line
  (17,90 + 3,94 = 21,84). The "+ IVA" label next to the price is therefore
  mandatory, so the customer is not surprised at payment time.
  **Shipping is outside the VAT base.**
  **Neither SosnetCash nor the bank-transfer discount reduces the taxable
  base**: VAT is computed on the goods at full price and frozen when the
  order is created; both reductions apply to the payment, not the price.
  Orders with `vat_mode == "INCLUDED"` carry VAT inside the total; the
  VAT columns must always be read according to the order's `vat_mode`.
- **Shop tab names** are settings, "Marketplace 1/2/3" by default.

Organization-level settings live in `organizations.settings` (JSONB):
`marketplace_bank_transfer_discount_percentage`, `marketplace_vat_percentage`,
`marketplace_labels`.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.organizations.models import Organization

DEFAULT_BANK_TRANSFER_DISCOUNT_PERCENTAGE = 5
MAX_BANK_TRANSFER_DISCOUNT_PERCENTAGE = 30
#: The standard Italian rate.
DEFAULT_VAT_PERCENTAGE = 22
#: Ceiling so a typo in the admin form cannot distort every new order.
MAX_VAT_PERCENTAGE = 30
#: SosnetCash usable on a newly imported product, as a percent of its price.
DEFAULT_CREDIT_PERCENTAGE = 30
#: Never 100: an imported product is never bought entirely with SosnetCash.
MAX_CREDIT_PERCENTAGE = 99

ALIEXPRESS = "aliexpress"
CJ = "cj"
SHOPIFY = "shopify"
#: The fourth shop, with a hand-written catalog.
SOSNET_MARKET = "sosnet_market"
MARKETPLACES = (ALIEXPRESS, CJ, SHOPIFY, SOSNET_MARKET)
DEFAULT_LABELS = {
    CJ: "Marketplace 1", SHOPIFY: "Marketplace 2", ALIEXPRESS: "Marketplace 3",
    SOSNET_MARKET: "Fai la Spesa con Sosnet",
}

#: The Shop's own sections, backed by `catalog.products`. Each can be
#: disabled or renamed from the admin, since an organization may not sell all
#: of them. Keys are lower-case `Product.category` values; INTERNAL holds the
#: SOSNET contracts.
INTERNAL = "internal"
PARTNER = "partner"
DROPSHIPPING = "dropshipping"
SECTIONS = (INTERNAL, PARTNER, DROPSHIPPING)
DEFAULT_SECTION_LABELS = {
    INTERNAL: "SOSNET",
    PARTNER: "Prodotti Partner",
    DROPSHIPPING: "Offerte Sosnet",
}


class CreditPercentageError(ValueError):
    pass


def check_credit_percentage(value: int) -> int:
    """Reject an SosnetCash share outside the allowed range."""
    if value < 0 or value > MAX_CREDIT_PERCENTAGE:
        raise CreditPercentageError(
            f"Sui prodotti dei Marketplace il SosnetCash può coprire al massimo il {MAX_CREDIT_PERCENTAGE}% del prezzo."
        )
    return value


def bank_transfer_discount_cents(*, residual_cents: int, percentage: int) -> int:
    """Bank-transfer discount on `residual_cents`, rounded half up to the
    cent (2,50 EUR at 5% -> 0,13 EUR)."""
    if residual_cents <= 0 or percentage <= 0:
        return 0
    return (residual_cents * percentage + 50) // 100


def vat_included_cents(*, gross_cents: int, percentage: int) -> int:
    """VAT contained in a VAT-inclusive amount: gross x pct / (100 + pct),
    rounded half up to the cent (18,20 EUR at 22% -> 3,28 EUR).

    Used to read orders with `vat_mode == "INCLUDED"`. Integer arithmetic
    only: floor((2n + d) / 2d) is half-up on n/d, so no float touches a
    fiscal figure."""
    if gross_cents <= 0 or percentage <= 0:
        return 0
    denominator = 100 + percentage
    return (2 * gross_cents * percentage + denominator) // (2 * denominator)


#: How VAT relates to the price on an order. Stored per order so existing
#: orders keep the rule they were created under; new orders use ADDED.
VAT_MODES = ("INCLUDED", "ADDED")
DEFAULT_VAT_MODE = "ADDED"


def vat_added_cents(*, net_cents: int, percentage: int) -> int:
    """VAT to add on top of a net amount: net x pct / 100, rounded half up
    to the cent (17,90 at 22% -> 3,94).

    Counterpart of `vat_included_cents`; the two give different results on
    the same amount (3,94 vs 3,23 on 17,90), which is why every order records
    its `vat_mode`. Integer arithmetic only."""
    if net_cents <= 0 or percentage <= 0:
        return 0
    return (2 * net_cents * percentage + 100) // 200


async def _settings(db: AsyncSession, organization_id: uuid.UUID) -> dict:
    org = await db.get(Organization, organization_id)
    return dict(org.settings or {}) if org is not None else {}


async def get_bank_transfer_discount_percentage(db: AsyncSession, *, organization_id: uuid.UUID) -> int:
    value = (await _settings(db, organization_id)).get("marketplace_bank_transfer_discount_percentage")
    if value is None:
        return DEFAULT_BANK_TRANSFER_DISCOUNT_PERCENTAGE
    try:
        return max(0, min(MAX_BANK_TRANSFER_DISCOUNT_PERCENTAGE, int(value)))
    except (TypeError, ValueError):
        return DEFAULT_BANK_TRANSFER_DISCOUNT_PERCENTAGE


async def get_vat_percentage(db: AsyncSession, *, organization_id: uuid.UUID) -> int:
    """Marketplace VAT rate (default 22). An invalid stored value falls back
    to the default instead of breaking checkout."""
    value = (await _settings(db, organization_id)).get("marketplace_vat_percentage")
    if value is None:
        return DEFAULT_VAT_PERCENTAGE
    try:
        return max(0, min(MAX_VAT_PERCENTAGE, int(value)))
    except (TypeError, ValueError):
        return DEFAULT_VAT_PERCENTAGE


async def get_labels(db: AsyncSession, *, organization_id: uuid.UUID) -> dict[str, str]:
    stored = (await _settings(db, organization_id)).get("marketplace_labels") or {}
    return {
        key: (str(stored.get(key)).strip() if stored.get(key) and str(stored.get(key)).strip() else DEFAULT_LABELS[key])
        for key in MARKETPLACES
    }


async def get_sections(db: AsyncSession, *, organization_id: uuid.UUID) -> dict[str, dict]:
    """Label and enabled flag of each Shop section. Sections default to
    enabled so a new organization sees its catalog without configuration."""
    stored = (await _settings(db, organization_id)).get("shop_sections") or {}
    sections = {}
    for key in SECTIONS:
        saved = stored.get(key) if isinstance(stored.get(key), dict) else {}
        label = str(saved.get("label") or "").strip()
        sections[key] = {
            "label": label or DEFAULT_SECTION_LABELS[key],
            "enabled": bool(saved.get("enabled", True)),
        }
    return sections


async def get_config(db: AsyncSession, *, organization_id: uuid.UUID) -> dict:
    return {
        "labels": await get_labels(db, organization_id=organization_id),
        "sections": await get_sections(db, organization_id=organization_id),
        "bank_transfer_discount_percentage": await get_bank_transfer_discount_percentage(
            db, organization_id=organization_id
        ),
        "vat_percentage": await get_vat_percentage(db, organization_id=organization_id),
        "default_credit_percentage": DEFAULT_CREDIT_PERCENTAGE,
        "max_credit_percentage": MAX_CREDIT_PERCENTAGE,
    }


async def update_config(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    labels: dict[str, str] | None,
    bank_transfer_discount_percentage: int | None,
    sections: dict[str, dict] | None = None,
    vat_percentage: int | None = None,
) -> dict:
    org = await db.get(Organization, organization_id)
    if org is None:
        raise ValueError("Organization not found")
    settings = dict(org.settings or {})
    if labels is not None:
        current = dict(settings.get("marketplace_labels") or {})
        for key, value in labels.items():
            if key in MARKETPLACES:
                current[key] = (value or "").strip()[:40] or DEFAULT_LABELS[key]
        settings["marketplace_labels"] = current
    if sections is not None:
        current_sections = dict(settings.get("shop_sections") or {})
        for key, value in sections.items():
            if key not in SECTIONS or not isinstance(value, dict):
                continue
            saved = dict(current_sections.get(key) or {})
            if "label" in value:
                saved["label"] = (str(value["label"] or "")).strip()[:40] or DEFAULT_SECTION_LABELS[key]
            if "enabled" in value:
                saved["enabled"] = bool(value["enabled"])
            current_sections[key] = saved
        settings["shop_sections"] = current_sections
    if bank_transfer_discount_percentage is not None:
        settings["marketplace_bank_transfer_discount_percentage"] = max(
            0, min(MAX_BANK_TRANSFER_DISCOUNT_PERCENTAGE, int(bank_transfer_discount_percentage))
        )
    if vat_percentage is not None:
        # Clamped here as well as in the router: new orders freeze this rate.
        settings["marketplace_vat_percentage"] = max(0, min(MAX_VAT_PERCENTAGE, int(vat_percentage)))
    # A new dict: in-place mutation of a JSONB column is not tracked.
    org.settings = settings
    await db.commit()
    return await get_config(db, organization_id=organization_id)
