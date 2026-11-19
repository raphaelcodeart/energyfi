"""Marketplace 3 (AliExpress dropshipping): settings, catalog, checkout, fulfillment.

The checkout matches the other Marketplaces (SosnetCash cap, OTP before
spending SosnetCash, bank transfer or card for the rest, bank-transfer
discount, Stripe webhook as the only proof of card payment). The supplier
side differs: paid orders are placed via the DS API and shipping status is
read back from tracking.

**Parsing responses.** Every read goes through `client.first()` over the
documented shapes. An unparseable product raises with the gateway's message
rather than silently yielding an empty catalog, which an administrator could
not diagnose. Fields marked "unverified" accept every plausible spelling.
"""

import hashlib
import hmac
import html
import logging
import re
import time
import uuid
from datetime import timedelta
from decimal import Decimal

import stripe
from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.foundation.config import get_settings
from app.foundation.db import utcnow
from app.foundation.email import send_html_email_best_effort
from app.foundation.email_templates import render_email
from app.modules.aliexpress_dropshipping import client as aliexpress
from app.modules.aliexpress_dropshipping import pricing
from app.modules.aliexpress_dropshipping.models import (
    ALIEXPRESS_ORDER_PAYMENT_METHODS,
    PRICE_BASES,
    PRICE_ROUNDINGS,
    SHIPPING_MODES,
    AliexpressOrder,
    AliexpressOrderItem,
    AliexpressProduct,
    AliexpressSettings,
    AliexpressVariant,
)
from app.modules.audit import service as audit_service
from app.modules.marketplaces import rules
from app.modules.notifications import service as notifications_service
from app.modules.organizations import service as organizations_service
from app.modules.shop_categories import service as shop_categories_service
from app.modules.users.models import User
from app.modules.wallets import service as wallets_service

logger = logging.getLogger(__name__)

#: Key of this shop in the categories layer (shop_categories/models.py::SHOPS).
SHOP = "aliexpress"

MAX_QUANTITY = 10
#: Max distinct lines per order; larger orders are hard to fulfil and would
#: split into many supplier orders.
MAX_ORDER_LINES = 20
MAX_ATTEMPTS = 6
#: Fulfillment states still worth polling for tracking.
FOLLOWED_FULFILLMENT = ("SENT", "SHIPPED")
#: Validity of a signed OAuth state.
STATE_MAX_AGE_SECONDS = 1800


class AliexpressError(Exception):
    pass


class AliexpressValidationError(AliexpressError):
    pass


class AliexpressNotFoundError(AliexpressError):
    pass


class InvalidOtpError(AliexpressError):
    pass


def order_number(order: AliexpressOrder) -> str:
    """Human-readable order reference."""
    return f"SOSNET-{order_code(order)}"


def order_code(order: AliexpressOrder) -> str:
    """Bare order number for emails and screens; falls back to a UUID prefix
    before the database-assigned number has been read back."""
    return str(order.number) if getattr(order, "number", None) else str(order.id)[:8].upper()


def out_order_id(order: AliexpressOrder) -> str:
    """Deterministic reference on AliExpress, so a retried placement is
    recognised as the same order, never a second one."""
    return f"sosnet-{order.id.hex}"


def html_to_text(value: str | None, limit: int = 8000) -> str:
    """Convert supplier HTML to plain text; third-party markup is never
    rendered on our pages."""
    if not value:
        return ""
    text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", "", value)
    text = re.sub(r"(?i)<br\s*/?>|</p>|</li>|</div>|</h\d>", "\n", text)
    text = re.sub(r"(?i)<li[^>]*>", "• ", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text).strip()
    return text[:limit]


def _decimal(value) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except Exception:  # noqa: BLE001
        return None


def _pick(node, *names: str):
    """First non-empty value among alternative spellings of a field."""
    if not isinstance(node, dict):
        return None
    for name in names:
        value = node.get(name)
        if value not in (None, ""):
            return value
    return None


# --- Settings ------------------------------------------------------------------------------------


async def get_settings_row(db: AsyncSession, *, organization_id: uuid.UUID) -> AliexpressSettings:
    row = (
        await db.execute(select(AliexpressSettings).where(AliexpressSettings.organization_id == organization_id))
    ).scalar_one_or_none()
    if row is None:
        row = AliexpressSettings(
            organization_id=organization_id, default_credit_percentage=rules.DEFAULT_CREDIT_PERCENTAGE
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
    return row


def settings_read_dict(row: AliexpressSettings) -> dict:
    return {
        "app_key": row.app_key,
        "app_secret_configured": bool(row.app_secret),
        "app_secret_hint": f"…{row.app_secret[-4:]}" if row.app_secret else None,
        "connected": bool(row.access_token),
        "account_label": row.account_label,
        "token_expires_at": row.token_expires_at,
        "last_connected_at": row.last_connected_at,
        "enabled": row.enabled,
        "ship_to_country": row.ship_to_country,
        "target_currency": row.target_currency,
        "target_language": row.target_language,
        "currency_rate": float(row.currency_rate),
        "price_basis": row.price_basis,
        "markup_percentage": row.markup_percentage,
        "markup_fixed_cents": row.markup_fixed_cents,
        "price_rounding": row.price_rounding,
        "shipping_mode": row.shipping_mode,
        "shipping_minimum_cents": row.shipping_minimum_cents,
        "shipping_days": row.shipping_days,
        "default_credit_percentage": row.default_credit_percentage,
        "max_credit_percentage": rules.MAX_CREDIT_PERCENTAGE,
        "auto_forward": row.auto_forward,
    }


PRICING_KEYS = (
    "currency_rate", "price_basis", "markup_percentage", "markup_fixed_cents", "price_rounding",
    "shipping_mode", "shipping_minimum_cents",
)


async def update_settings(
    db: AsyncSession, *, row: AliexpressSettings, updates: dict, actor_user_id: uuid.UUID
) -> AliexpressSettings:
    """Save settings; a changed pricing rule immediately reprices every
    variant from its stored AliExpress figures."""
    if "price_rounding" in updates and updates["price_rounding"] not in PRICE_ROUNDINGS:
        raise AliexpressValidationError("Arrotondamento non valido.")
    if "shipping_mode" in updates and updates["shipping_mode"] not in SHIPPING_MODES:
        raise AliexpressValidationError("Modalità di spedizione non valida.")
    if "price_basis" in updates and updates["price_basis"] not in PRICE_BASES:
        raise AliexpressValidationError("Base di prezzo non valida.")
    if "default_credit_percentage" in updates:
        try:
            rules.check_credit_percentage(updates["default_credit_percentage"])
        except rules.CreditPercentageError as exc:
            raise AliexpressValidationError(str(exc)) from exc
    if updates.get("ship_to_country"):
        updates["ship_to_country"] = str(updates["ship_to_country"]).upper()
    if updates.get("target_currency"):
        updates["target_currency"] = str(updates["target_currency"]).upper()
    # Credentials are popped from `updates` so they never reach the audit log.
    credentials_changed = False
    if "app_key" in updates:
        app_key = (updates.pop("app_key") or "").strip() or None
        if app_key != row.app_key:
            row.app_key = app_key
            credentials_changed = True
    if "app_secret" in updates:
        secret = (updates.pop("app_secret") or "").strip() or None
        if secret and secret != row.app_secret:
            row.app_secret = secret
            credentials_changed = True
    if credentials_changed:
        # A token issued to the old app is invalid; the account must be relinked.
        row.access_token = None
        row.refresh_token = None
        row.token_expires_at = None
        row.account_label = None
        row.last_connected_at = None
    enabling = updates.get("enabled")
    if enabling and not (row.app_key and row.app_secret and row.access_token):
        raise AliexpressValidationError(
            "Per attivare il Marketplace servono prima App Key, App Secret e l'autorizzazione "
            "dell'account AliExpress."
        )
    reprice = any(k in updates and updates[k] != getattr(row, k) for k in PRICING_KEYS)
    for key, value in updates.items():
        setattr(row, key, value)
    row.updated_at = utcnow()
    await audit_service.record(
        db, organization_id=row.organization_id, actor_user_id=actor_user_id,
        action="aliexpress.settings_updated", entity_type="aliexpress_settings", entity_id=str(row.id),
        new_value={k: (str(v) if isinstance(v, Decimal) else v) for k, v in updates.items()},
    )
    await db.commit()
    await db.refresh(row)
    if reprice:
        await reprice_all(db, settings=row)
    return row


def _category_names(body: dict) -> list[str]:
    """A few category names from the connection test, as proof of real data."""
    node = aliexpress.first(
        body,
        ("aliexpress_ds_category_get_response", "resp_result", "result", "categories"),
        ("aliexpress_ds_category_get_response", "result", "categories"),
        ("result", "categories"),
        ("categories",),
    )
    names = []
    for item in aliexpress.items_of(node, "category")[:5]:
        if isinstance(item, dict):
            names.append(str(_pick(item, "category_name", "name", "category_id") or ""))
    return [n for n in names if n]


async def test_connection(db: AsyncSession, *, row: AliexpressSettings) -> dict:
    """Cheapest call proving App Key, signature, token and DS permission."""
    body = await aliexpress.category_get(row, language=row.target_language)
    row.last_connected_at = utcnow()
    await db.commit()
    await db.refresh(row)
    return {**settings_read_dict(row), "sample_categories": _category_names(body)}


# --- Account authorisation (OAuth) --------------------------------------------------------------
#
# Stateless: the state carries the settings row id so the unauthenticated
# callback can find the row, and an HMAC proves the round trip is ours and
# recent.


def oauth_state(row: AliexpressSettings) -> str:
    ts = int(time.time())
    payload = f"{row.id}.{ts}"
    mac = hmac.new((row.app_secret or "").encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{mac}"


def oauth_state_settings_id(state: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(state.split(".", 1)[0])
    except (ValueError, AttributeError):
        return None


def oauth_state_ok(row: AliexpressSettings, state: str) -> bool:
    parts = (state or "").split(".")
    if len(parts) != 3:
        return False
    try:
        age = time.time() - int(parts[1])
    except ValueError:
        return False
    if age < -60 or age > STATE_MAX_AGE_SECONDS:
        return False
    expected = hmac.new(
        (row.app_secret or "").encode(), f"{parts[0]}.{parts[1]}".encode(), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, parts[2])


async def get_settings_row_any_org(db: AsyncSession, *, settings_id: uuid.UUID) -> AliexpressSettings | None:
    """For the public callback only, where the signed state replaces the
    user and organization context."""
    return await db.get(AliexpressSettings, settings_id)


def authorize_url(row: AliexpressSettings) -> str:
    if not aliexpress.has_credentials(row):
        raise aliexpress.AliexpressNotConfiguredError()
    return aliexpress.authorize_url(app_key=row.app_key, state=oauth_state(row))


async def complete_authorisation(
    db: AsyncSession, *, row: AliexpressSettings, code: str, actor_user_id: uuid.UUID | None = None
) -> AliexpressSettings:
    await aliexpress.create_token(row, code=code)
    await audit_service.record(
        db, organization_id=row.organization_id, actor_user_id=actor_user_id,
        action="aliexpress.account_authorised", entity_type="aliexpress_settings", entity_id=str(row.id),
        new_value={"account": row.account_label},
    )
    await db.commit()
    await db.refresh(row)
    return row


def _variant_price(variant: AliexpressVariant, *, settings: AliexpressSettings, product: AliexpressProduct) -> int:
    return pricing.sale_price_cents(
        cost=variant.cost_amount, price=variant.source_price_amount, settings=settings,
        markup_percentage=product.markup_percentage,
    )


async def reprice_all(db: AsyncSession, *, settings: AliexpressSettings) -> int:
    products = list(
        (
            await db.execute(
                select(AliexpressProduct).where(AliexpressProduct.organization_id == settings.organization_id)
            )
        ).scalars()
    )
    count = 0
    for product in products:
        for variant in await _variants(db, product.id):
            variant.price_cents = _variant_price(variant, settings=settings, product=product)
            count += 1
    await db.commit()
    return count


# --- AliExpress catalog (search and preview) -----------------------------------------------------


def _images_of(node) -> list[str]:
    """`image_urls` may be a semicolon-separated string or a list."""
    if isinstance(node, list):
        return [str(u) for u in node if u]
    if isinstance(node, str):
        return [u.strip() for u in node.replace(",", ";").split(";") if u.strip()]
    return []


def _sku_label(sku: dict) -> str:
    """Customer-facing variant label, e.g. "Colore: Nero · Taglia: M"."""
    properties = aliexpress.items_of(
        _pick(sku, "ae_sku_property_dtos", "ae_sku_property_d_t_o_s", "sku_property_list", "aeSkuPropertyDtos"),
        "ae_sku_property_d_t_o", "sku_property",
    )
    parts = []
    for prop in properties:
        if not isinstance(prop, dict):
            continue
        name = _pick(prop, "sku_property_name", "skuPropertyName", "property_name")
        value = _pick(
            prop, "property_value_definition_name", "sku_property_value", "propertyValueDefinitionName",
            "skuPropertyValue", "property_value",
        )
        if value:
            parts.append(f"{name}: {value}" if name else str(value))
    return " · ".join(str(p) for p in parts)[:255]


def _parse_sku(sku: dict, *, settings: AliexpressSettings) -> dict | None:
    sku_id = _pick(sku, "sku_id", "skuId", "id")
    if sku_id is None:
        return None
    # offer_sale_price is the dropshipper's cost, sku_price the list price.
    # Unverified: some responses use sale_price/original_price instead.
    cost = _decimal(_pick(sku, "offer_sale_price", "offerSalePrice", "sku_bulk_order_price", "sale_price"))
    price = _decimal(_pick(sku, "sku_price", "skuPrice", "original_price", "sku_sale_price")) or cost or Decimal(0)
    stock = _pick(sku, "sku_available_stock", "skuAvailableStock", "ipm_sku_stock", "available_stock")
    try:
        inventory = int(stock) if stock is not None else None
    except (TypeError, ValueError):
        inventory = None
    label = _sku_label(sku) or "Standard"
    image = None
    for prop in aliexpress.items_of(
        _pick(sku, "ae_sku_property_dtos", "ae_sku_property_d_t_o_s", "sku_property_list"), "ae_sku_property_d_t_o"
    ):
        if isinstance(prop, dict) and _pick(prop, "sku_image", "skuImage"):
            image = str(_pick(prop, "sku_image", "skuImage"))
            break
    return {
        "variant_id": str(sku_id),
        "sku_attr": str(_pick(sku, "sku_attr", "skuAttr") or "") or None,
        "sku": str(_pick(sku, "sku_code", "skuCode", "seller_sku") or "") or None,
        "label": label,
        "image_url": image,
        "cost_amount": float(cost) if cost is not None else None,
        "source_price_amount": float(price),
        "inventory": inventory,
        "price_cents": pricing.sale_price_cents(cost=cost, price=price, settings=settings),
    }


def _parse_product(body: dict, *, settings: AliexpressSettings) -> dict:
    """An AliExpress product as shown in admin, with our price per SKU.
    Raises when the response holds no product instead of returning an empty
    card."""
    result = aliexpress.first(
        body,
        ("aliexpress_ds_product_get_response", "result"),
        ("aliexpress_ds_product_get_response", "resp_result", "result"),
        ("result",),
        ("data",),
    )
    if not isinstance(result, dict):
        raise AliexpressNotFoundError("AliExpress non ha restituito il prodotto: riprova o controlla l'ID.")
    base = _pick(result, "ae_item_base_info_dto", "ae_item_base_info_d_t_o", "aeItemBaseInfoDto", "item_base_info") or {}
    multimedia = _pick(result, "ae_multimedia_info_dto", "ae_multimedia_info_d_t_o", "aeMultimediaInfoDto") or {}
    store = _pick(result, "ae_store_info", "ae_store_info_dto", "aeStoreInfo") or {}
    sku_node = _pick(result, "ae_item_sku_info_dtos", "ae_item_sku_info_d_t_o_s", "aeItemSkuInfoDtos", "sku_info") or {}

    product_id = str(_pick(base, "product_id", "productId") or _pick(result, "product_id", "productId") or "")
    images = _images_of(_pick(multimedia, "image_urls", "imageUrls", "images"))
    variants = []
    for sku in aliexpress.items_of(sku_node, "ae_item_sku_info_d_t_o", "sku", "ae_item_sku_info_dto"):
        if isinstance(sku, dict):
            parsed = _parse_sku(sku, settings=settings)
            if parsed is not None:
                variants.append(parsed)
    prices = [v["price_cents"] for v in variants]
    status_raw = str(_pick(base, "product_status_type", "productStatusType", "status") or "").lower()
    return {
        "product_id": product_id,
        "product_url": _pick(base, "detail_url", "product_detail_url", "productDetailUrl")
        or (f"https://www.aliexpress.com/item/{product_id}.html" if product_id else None),
        "title": str(_pick(base, "subject", "product_title", "title") or ""),
        "vendor": str(_pick(store, "store_name", "storeName") or "") or None,
        # Unknown statuses count as on sale, so nothing is hidden by mistake.
        "status": "INACTIVE" if status_raw in ("offline", "off_selling", "inactive") else "ACTIVE",
        "description_text": html_to_text(_pick(base, "detail", "description", "product_description")),
        "image_url": images[0] if images else None,
        "images": images[:20],
        "variants": variants,
        "min_price_cents": min(prices) if prices else None,
        "max_price_cents": max(prices) if prices else None,
        "currency": settings.target_currency,
    }


def _parse_search_item(item: dict, *, settings: AliexpressSettings) -> dict | None:
    """A search hit. Search results carry no SKUs, so the price is the
    advertised one with our markup; per-variant prices come with the preview
    (ds.product.get)."""
    product_id = _pick(item, "product_id", "productId", "itemId", "item_id")
    if product_id is None:
        return None
    sale = _decimal(
        _pick(item, "target_sale_price", "targetSalePrice", "sale_price", "app_sale_price", "min_price", "salePrice")
    )
    original = _decimal(
        _pick(item, "target_original_price", "targetOriginalPrice", "original_price", "originalPrice", "max_price")
    )
    base_price = sale or original or Decimal(0)
    price_cents = pricing.sale_price_cents(cost=sale, price=original or base_price, settings=settings)
    image = _pick(item, "product_main_image_url", "productMainImageUrl", "image_url", "itemMainPic", "main_image")
    return {
        "product_id": str(product_id),
        "product_url": _pick(item, "product_detail_url", "productDetailUrl", "item_url", "detail_url"),
        "title": str(_pick(item, "product_title", "productTitle", "title", "subject") or ""),
        "vendor": str(_pick(item, "store_name", "storeName", "shop_name") or "") or None,
        "status": "ACTIVE",
        "description_text": "",
        "image_url": str(image) if image else None,
        "images": [str(image)] if image else [],
        "variants": [],
        "min_price_cents": price_cents,
        "max_price_cents": price_cents,
        "currency": settings.target_currency,
        "source_sale_price": float(sale) if sale is not None else None,
        "evaluate_rate": _pick(item, "evaluate_rate", "evaluateRate", "rating"),
    }


async def search_catalog(
    db: AsyncSession, *, row: AliexpressSettings, keyword: str | None, cursor: str | None
) -> dict:
    """`cursor` is the page number as a string, matching the cursor API
    used by the other shops."""
    if not keyword:
        raise AliexpressValidationError("Scrivi che cosa cercare nel catalogo AliExpress.")
    try:
        page = max(1, int(cursor)) if cursor else 1
    except ValueError:
        page = 1
    body = await aliexpress.text_search(row, keyword=keyword, page=page)
    node = aliexpress.first(
        body,
        ("aliexpress_ds_text_search_response", "data", "products"),
        ("aliexpress_ds_text_search_response", "resp_result", "result", "products"),
        ("aliexpress_ds_text_search_response", "result", "products"),
        ("data", "products"),
        ("result", "products"),
        ("products",),
    )
    raw_items = aliexpress.items_of(node, "selection_search_product", "product", "traffic_product_info")
    imported = {
        pid for pid in (
            await db.execute(
                select(AliexpressProduct.aliexpress_product_id).where(
                    AliexpressProduct.organization_id == row.organization_id
                )
            )
        ).scalars()
    }
    items = []
    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        parsed = _parse_search_item(raw, settings=row)
        if parsed is None:
            continue
        parsed["already_imported"] = parsed["product_id"] in imported
        items.append(parsed)
    # When the page count is missing, a full page means "maybe more"; at
    # worst the customer sees one empty page.
    total_pages = _pick(
        aliexpress.first(
            body,
            ("aliexpress_ds_text_search_response", "data"),
            ("aliexpress_ds_text_search_response", "resp_result", "result"),
            ("data",),
            ("result",),
        ) or {},
        "totalPage", "total_page", "total_pages",
    )
    try:
        has_next = page < int(total_pages) if total_pages is not None else len(items) >= 20
    except (TypeError, ValueError):
        has_next = len(items) >= 20
    return {"items": items, "next_cursor": str(page + 1) if items and has_next else None}


async def preview_product(db: AsyncSession, *, row: AliexpressSettings, product_id: str) -> dict:
    body = await aliexpress.product_get(row, product_id=product_id)
    parsed = _parse_product(body, settings=row)
    if not parsed["variants"]:
        raise AliexpressNotFoundError(
            "AliExpress non ha restituito nessuna variante acquistabile per questo prodotto."
        )
    return parsed


def _parse_freight(body: dict, *, settings: AliexpressSettings) -> list[dict]:
    node = aliexpress.first(
        body,
        ("aliexpress_ds_freight_query_response", "result", "delivery_options"),
        ("aliexpress_ds_freight_query_response", "resp_result", "result", "delivery_options"),
        ("result", "delivery_options"),
        ("delivery_options",),
        ("result",),
    )
    options = []
    for item in aliexpress.items_of(node, "delivery_option_dto", "delivery_option_d_t_o", "freight"):
        if not isinstance(item, dict):
            continue
        # Despite its name, `shipping_fee_cent` holds an amount, not cents
        # (the gateway returns "1.99" for 1,99 EUR). Both fields are read as
        # amounts in the response currency; misreading would undercharge
        # shipping.
        amount = _pick(item, "shipping_fee_amount", "shippingFeeAmount", "freight_amount")
        if isinstance(amount, dict):
            amount = _pick(amount, "value", "amount")
        if amount is None:
            amount = _pick(item, "shipping_fee_cent", "shippingFeeCent")
        fee = _decimal(amount)
        options.append({
            "service_name": _pick(item, "service_name", "serviceName", "delivery_provider_name"),
            "company": _pick(item, "company", "carrier", "delivery_provider_name"),
            "shipping_fee_amount": float(fee) if fee is not None else None,
            "shipping_fee_cents": pricing.to_eur_cents(fee, Decimal(settings.currency_rate)) if fee is not None else None,
            "currency": _pick(item, "shipping_fee_currency", "currency") or settings.target_currency,
            "min_days": _pick(item, "min_delivery_days", "minDeliveryDays"),
            "max_days": _pick(item, "max_delivery_days", "maxDeliveryDays"),
            "free_shipping": bool(_pick(item, "free_shipping", "freeShipping") or False),
            "tracking": bool(_pick(item, "tracking", "tracking_available") or False),
        })
    return options


async def freight_options(
    db: AsyncSession, *, row: AliexpressSettings, product_id: str, sku_id: str | None, quantity: int
) -> dict:
    """AliExpress shipping options for a product, shown to administrators
    when setting the shipping minimum."""
    body = await aliexpress.freight_query(row, product_id=product_id, sku_id=sku_id, quantity=max(1, quantity))
    return {"options": _parse_freight(body, settings=row)}


# --- Imported products ---------------------------------------------------------------------------


async def _variants(db: AsyncSession, product_id: uuid.UUID) -> list[AliexpressVariant]:
    return list(
        (
            await db.execute(
                select(AliexpressVariant)
                .where(AliexpressVariant.product_id == product_id)
                .order_by(AliexpressVariant.created_at)
            )
        ).scalars()
    )


async def get_product(db: AsyncSession, *, organization_id: uuid.UUID, product_id: uuid.UUID) -> AliexpressProduct:
    product = await db.get(AliexpressProduct, product_id)
    if product is None or product.organization_id != organization_id:
        raise AliexpressNotFoundError("Prodotto non trovato.")
    return product


def _check_credit(value: int) -> int:
    try:
        return rules.check_credit_percentage(value)
    except rules.CreditPercentageError as exc:
        raise AliexpressValidationError(str(exc)) from exc


async def import_product(
    db: AsyncSession, *, row: AliexpressSettings, actor_user_id: uuid.UUID, product_id: str, name: str,
    description: str | None, credit_discount_percentage: int | None, markup_percentage: int | None,
    variant_ids: list[str] | None, activate: bool,
) -> AliexpressProduct:
    existing = (
        await db.execute(
            select(AliexpressProduct).where(
                AliexpressProduct.organization_id == row.organization_id,
                AliexpressProduct.aliexpress_product_id == product_id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise AliexpressValidationError("Questo prodotto è già stato importato: lo trovi in Prodotti importati.")
    credit = _check_credit(
        row.default_credit_percentage if credit_discount_percentage is None else credit_discount_percentage
    )
    preview = await preview_product(db, row=row, product_id=product_id)
    chosen = [v for v in preview["variants"] if not variant_ids or v["variant_id"] in variant_ids]
    if not chosen:
        raise AliexpressValidationError("Scegli almeno una variante da vendere.")

    product = AliexpressProduct(
        organization_id=row.organization_id,
        aliexpress_product_id=product_id,
        product_url=preview["product_url"],
        name=name.strip() or (preview["title"] or "Prodotto")[:255],
        source_title=(preview["title"] or "")[:500] or None,
        vendor=(preview["vendor"] or "")[:255] or None,
        description=(description if description is not None else preview["description_text"])[:8000],
        image_url=preview["image_url"],
        images=preview["images"],
        status="ACTIVE" if activate else "INACTIVE",
        credit_discount_percentage=credit,
        markup_percentage=markup_percentage,
        last_synced_at=utcnow(),
        created_by_user_id=actor_user_id,
        updated_at=utcnow(),
    )
    db.add(product)
    await db.flush()
    for v in chosen:
        variant = AliexpressVariant(
            product_id=product.id,
            aliexpress_sku_id=v["variant_id"],
            sku_attr=v["sku_attr"],
            sku=v["sku"],
            label=v["label"],
            image_url=v["image_url"],
            cost_amount=_decimal(v["cost_amount"]),
            source_price_amount=_decimal(v["source_price_amount"]) or Decimal(0),
            price_cents=0,
            inventory=v["inventory"],
            last_synced_at=utcnow(),
        )
        variant.price_cents = _variant_price(variant, settings=row, product=product)
        db.add(variant)
    await audit_service.record(
        db, organization_id=row.organization_id, actor_user_id=actor_user_id,
        action="aliexpress.product_imported", entity_type="aliexpress_product", entity_id=str(product.id),
        new_value={"aliexpress_product_id": product_id, "variants": len(chosen)},
    )
    await db.commit()
    await db.refresh(product)
    return product


async def update_product(
    db: AsyncSession, *, row: AliexpressSettings, product: AliexpressProduct, updates: dict,
    actor_user_id: uuid.UUID,
) -> AliexpressProduct:
    if "credit_discount_percentage" in updates:
        _check_credit(updates["credit_discount_percentage"])
    reprice = "markup_percentage" in updates and updates["markup_percentage"] != product.markup_percentage
    for key, value in updates.items():
        setattr(product, key, value)
    product.updated_at = utcnow()
    if reprice:
        for variant in await _variants(db, product.id):
            variant.price_cents = _variant_price(variant, settings=row, product=product)
    await audit_service.record(
        db, organization_id=row.organization_id, actor_user_id=actor_user_id,
        action="aliexpress.product_updated", entity_type="aliexpress_product", entity_id=str(product.id),
        new_value={k: v for k, v in updates.items() if k != "description"},
    )
    await db.commit()
    await db.refresh(product)
    return product


async def update_variant(
    db: AsyncSession, *, organization_id: uuid.UUID, variant_id: uuid.UUID, updates: dict
) -> AliexpressVariant:
    variant = await db.get(AliexpressVariant, variant_id)
    product = await db.get(AliexpressProduct, variant.product_id) if variant else None
    if variant is None or product is None or product.organization_id != organization_id:
        raise AliexpressNotFoundError("Variante non trovata.")
    for key, value in updates.items():
        setattr(variant, key, value)
    await db.commit()
    await db.refresh(variant)
    return variant


async def sync_product(
    db: AsyncSession, *, row: AliexpressSettings, product: AliexpressProduct
) -> AliexpressProduct:
    """Refresh cost, price and stock from AliExpress and reprice. SKUs no
    longer offered are kept (orders reference them) but stop being sold, as
    does a product withdrawn from AliExpress."""
    try:
        parsed = _parse_product(
            await aliexpress.product_get(row, product_id=product.aliexpress_product_id), settings=row
        )
    except (aliexpress.AliexpressApiError, AliexpressNotFoundError) as exc:
        product.sync_error = str(exc)[:500]
        product.last_synced_at = utcnow()
        await db.commit()
        await db.refresh(product)
        return product
    variants = await _variants(db, product.id)
    by_id = {v["variant_id"]: v for v in parsed["variants"]}
    product.source_title = (parsed["title"] or "")[:500] or product.source_title
    product.images = parsed["images"] or product.images
    on_sale = parsed["status"] == "ACTIVE"
    for variant in variants:
        fresh = by_id.get(variant.aliexpress_sku_id)
        variant.available_in_store = fresh is not None and on_sale
        if fresh is not None:
            variant.cost_amount = _decimal(fresh["cost_amount"])
            variant.source_price_amount = _decimal(fresh["source_price_amount"]) or variant.source_price_amount
            variant.inventory = fresh["inventory"]
            variant.sku_attr = fresh["sku_attr"] or variant.sku_attr
        variant.last_synced_at = utcnow()
        variant.price_cents = _variant_price(variant, settings=row, product=product)
    if not on_sale:
        product.sync_error = "Il prodotto non è più in vendita su AliExpress."
    elif not by_id:
        product.sync_error = "AliExpress non ha restituito nessuna variante per questo prodotto."
    else:
        product.sync_error = None
    product.last_synced_at = utcnow()
    product.updated_at = utcnow()
    await db.commit()
    await db.refresh(product)
    return product


async def sync_all_products(db: AsyncSession, *, organization_id: uuid.UUID) -> int:
    row = await get_settings_row(db, organization_id=organization_id)
    if not aliexpress.is_connected(row):
        return 0
    products = await list_products(db, organization_id=organization_id, active_only=False)
    for product in products:
        await sync_product(db, row=row, product=product)
    return len(products)


def variant_price(variant: AliexpressVariant) -> int:
    return variant.price_override_cents or variant.price_cents


def variant_sellable(variant: AliexpressVariant) -> bool:
    return variant.active and variant.available_in_store and (variant.inventory is None or variant.inventory > 0)


async def _category_ids(
    db: AsyncSession, product: AliexpressProduct, category_ids: list[uuid.UUID] | None
) -> list[uuid.UUID]:
    """Categories for a product card. List endpoints pass them in (fetched
    in bulk); single-product endpoints pass None and pay one query."""
    if category_ids is not None:
        return category_ids
    return await shop_categories_service.category_ids_for_product(
        db, organization_id=product.organization_id, shop=SHOP, product_id=product.id
    )


async def product_admin_dict(
    db: AsyncSession, product: AliexpressProduct, *, category_ids: list[uuid.UUID] | None = None
) -> dict:
    variants = await _variants(db, product.id)
    sold = await db.execute(
        select(AliexpressOrder.id).where(
            AliexpressOrder.aliexpress_product_id == product.id, AliexpressOrder.status == "PAID"
        )
    )
    return {
        "id": product.id,
        "category_ids": await _category_ids(db, product, category_ids),
        "aliexpress_product_id": product.aliexpress_product_id,
        "product_url": product.product_url,
        "name": product.name,
        "source_title": product.source_title,
        "vendor": product.vendor,
        "description": product.description,
        "image_url": product.image_url,
        "images": product.images or [],
        "status": product.status,
        "credit_discount_percentage": product.credit_discount_percentage,
        "markup_percentage": product.markup_percentage,
        "last_synced_at": product.last_synced_at,
        "sync_error": product.sync_error,
        "paid_orders": len(sold.all()),
        "created_at": product.created_at,
        "variants": [
            {
                "id": v.id,
                "aliexpress_sku_id": v.aliexpress_sku_id,
                "sku_attr": v.sku_attr,
                "sku": v.sku,
                "label": v.label,
                "image_url": v.image_url,
                "cost_amount": float(v.cost_amount) if v.cost_amount is not None else None,
                "source_price_amount": float(v.source_price_amount),
                "price_cents": v.price_cents,
                "price_override_cents": v.price_override_cents,
                "effective_price_cents": variant_price(v),
                "inventory": v.inventory,
                "active": v.active,
                "available_in_store": v.available_in_store,
            }
            for v in variants
        ],
    }


async def list_products(
    db: AsyncSession, *, organization_id: uuid.UUID, active_only: bool
) -> list[AliexpressProduct]:
    stmt = select(AliexpressProduct).where(AliexpressProduct.organization_id == organization_id)
    if active_only:
        stmt = stmt.where(AliexpressProduct.status == "ACTIVE")
    return list((await db.execute(stmt.order_by(AliexpressProduct.created_at.desc()))).scalars())


async def product_customer_dict(
    db: AsyncSession, product: AliexpressProduct, *, settings: AliexpressSettings,
    bank_transfer_discount_percentage: int, category_ids: list[uuid.UUID] | None = None,
) -> dict | None:
    """Customer product card, same shape for every marketplace."""
    variants = [v for v in await _variants(db, product.id) if v.active and v.available_in_store]
    if not variants:
        return None
    prices = [variant_price(v) for v in variants]
    return {
        "id": product.id,
        "category_ids": await _category_ids(db, product, category_ids),
        "name": product.name,
        "description": product.description,
        "image_url": product.image_url,
        "images": product.images or [],
        "min_price_cents": min(prices),
        "max_price_cents": max(prices),
        "credit_discount_percentage": product.credit_discount_percentage,
        "shipping_days": settings.shipping_days,
        "shipping_included": settings.shipping_mode == "INCLUDED",
        #: Displayed prices are full prices; bank transfer takes this percent off.
        "bank_transfer_discount_percentage": bank_transfer_discount_percentage,
        "in_stock": any(variant_sellable(v) for v in variants),
        "variants": [
            {
                "id": v.id,
                "label": v.label,
                "image_url": v.image_url,
                "price_cents": variant_price(v),
                "in_stock": variant_sellable(v),
            }
            for v in variants
        ],
    }


# --- Checkout -------------------------------------------------------------------------------------


async def _sellable(
    db: AsyncSession, *, organization_id: uuid.UUID, variant_id: uuid.UUID
) -> tuple[AliexpressProduct, AliexpressVariant]:
    variant = await db.get(AliexpressVariant, variant_id)
    product = await db.get(AliexpressProduct, variant.product_id) if variant else None
    if variant is None or product is None or product.organization_id != organization_id or product.status != "ACTIVE":
        raise AliexpressValidationError("Prodotto non disponibile.")
    if not variant_sellable(variant):
        raise AliexpressValidationError("Questa variante al momento non è disponibile.")
    return product, variant


def max_creditable_cents(*, amount_cents: int, credit_discount_percentage: int) -> int:
    """SosnetCash cap; never the whole price, whatever is stored."""
    percentage = min(credit_discount_percentage, rules.MAX_CREDIT_PERCENTAGE)
    return min(round(amount_cents * percentage / 100), max(amount_cents - 1, 0))


def bank_transfer_total_cents(*, residual_cents: int, percentage: int) -> int:
    return residual_cents - rules.bank_transfer_discount_cents(residual_cents=residual_cents, percentage=percentage)


def taxable_base_cents(order: AliexpressOrder) -> int:
    """Net-of-VAT sale value: amount collected (amount minus bank-transfer
    discount) minus VAT. `amount_cents` includes VAT under both vat modes.
    SosnetCash is not subtracted: it is a payment method, not a discount.
    Margins are measured on this figure."""
    return order.amount_cents - (order.bank_transfer_discount_cents or 0) - (order.vat_amount_cents or 0)


def amount_due_cents(order: AliexpressOrder) -> int:
    """What the customer pays in euro: residual after SosnetCash, minus the
    bank-transfer discount when paying by bank transfer."""
    return order.amount_cents - order.credit_applied_cents - (order.bank_transfer_discount_cents or 0)


async def freeze_bank_transfer_discount(db: AsyncSession, *, order: AliexpressOrder) -> None:
    """Freeze the bank-transfer discount for the current payment method from
    the current setting, never from the client. Does not commit.

    VAT is untouched: it is frozen at creation on the full taxable base, so
    switching payment method changes what is paid, not the tax."""
    if order.status != "AWAITING_PAYMENT":
        return
    if order.payment_method == "BANK_TRANSFER":
        percentage = await rules.get_bank_transfer_discount_percentage(db, organization_id=order.organization_id)
        order.bank_transfer_discount_cents = rules.bank_transfer_discount_cents(
            residual_cents=order.amount_cents - order.credit_applied_cents, percentage=percentage
        )
    else:
        order.bank_transfer_discount_cents = 0


#: Freight quote cache lifetime: avoids an API call on every quantity change
#: while staying fresh enough for checkout.
FREIGHT_CACHE_SECONDS = 1800


class AliexpressShippingUnavailableError(AliexpressValidationError):
    """The real shipping cost could not be determined.

    There is no acceptable fallback: charging the minimum or zero could sell
    at a loss, so the order is blocked."""


def _cheapest_freight(options: list[dict]) -> dict | None:
    """Cheapest option with a known price. Options without an amount are
    unpriced, not free, and are ignored."""
    priced = [o for o in options if o.get("shipping_fee_cents") is not None]
    return min(priced, key=lambda o: o["shipping_fee_cents"]) if priced else None


async def supplier_shipping_cents(
    *, row: AliexpressSettings, product: AliexpressProduct, variant: AliexpressVariant, quantity: int
) -> int:
    """AliExpress shipping cost for one line, in EUR cents.

    Cached by (product, SKU, quantity, destination), so any change yields a
    fresh quote without explicit invalidation. Raises
    AliexpressShippingUnavailableError when no priced option is available;
    never returns zero as a fallback.
    """
    key = (
        f"aliexpress:freight:{row.organization_id}:{product.aliexpress_product_id}:"
        f"{variant.aliexpress_sku_id}:{quantity}:{row.ship_to_country}"
    )
    cached = await aliexpress.cache_get(key)
    if cached is not None:
        return int(cached)
    try:
        body = await aliexpress.freight_query(
            row, product_id=product.aliexpress_product_id,
            sku_id=variant.aliexpress_sku_id, quantity=max(1, quantity),
        )
    except aliexpress.AliexpressApiError as exc:
        logger.warning(
            "AliExpress freight query failed (product=%s sku=%s qty=%s): %s",
            product.aliexpress_product_id, variant.aliexpress_sku_id, quantity, exc,
        )
        raise AliexpressShippingUnavailableError(
            f"«{product.name}»: non riusciamo a calcolare la spedizione in questo momento. Riprova tra poco."
        ) from exc
    option = _cheapest_freight(_parse_freight(body, settings=row))
    if option is None:
        logger.warning(
            "AliExpress freight query returned no priced option (product=%s sku=%s qty=%s)",
            product.aliexpress_product_id, variant.aliexpress_sku_id, quantity,
        )
        raise AliexpressShippingUnavailableError(
            f"«{product.name}»: AliExpress non offre una spedizione per l'Italia in questo momento."
        )
    cents = int(option["shipping_fee_cents"])
    await aliexpress.cache_set(key, cents, FREIGHT_CACHE_SECONDS)
    return cents


async def payment_methods(db: AsyncSession, *, organization_id: uuid.UUID) -> dict:
    return {
        "bank_transfer": await organizations_service.is_bank_transfer_configured(db, organization_id=organization_id),
        "card": await organizations_service.is_stripe_configured(db, organization_id=organization_id),
    }


async def order_items(db: AsyncSession, order: AliexpressOrder) -> list[AliexpressOrderItem]:
    """An order's lines in insertion order; every order has at least one."""
    rows = await db.execute(
        select(AliexpressOrderItem)
        .where(AliexpressOrderItem.order_id == order.id)
        .order_by(AliexpressOrderItem.created_at, AliexpressOrderItem.id)
    )
    return list(rows.scalars().all())


def _item_field(item, name: str):
    """Read a field from either a quote dict or an order-item row."""
    return item[name] if isinstance(item, dict) else getattr(item, name)


def _items_summary(items: list) -> str:
    """One-line order title (email subject, notification title): first
    product plus how many others."""
    first = _item_field(items[0], "product_name")
    others = len(items) - 1
    return first if others <= 0 else f"{first} + altri {others}"


def _items_detail(items: list) -> str:
    """All lines spelled out, for a notification body."""
    parts = []
    for item in items:
        label = _item_field(item, "variant_label")
        parts.append(
            f"{_item_field(item, 'quantity')} × {_item_field(item, 'product_name')}"
            + (f" ({label})" if label else "")
        )
    return " · ".join(parts)


#: A purchase line: (variant id, quantity). Used by both cart and
#: single-product checkout.
OrderLine = tuple[uuid.UUID, int]


def _lines_from(variant_id: uuid.UUID | None, quantity: int, lines: list[OrderLine] | None) -> list[OrderLine]:
    """Normalise input to a list of lines: `lines` from the cart, or
    `variant_id`/`quantity` from single-product checkout."""
    if lines is not None:
        if not lines:
            raise AliexpressValidationError("Il carrello è vuoto.")
        if len(lines) > MAX_ORDER_LINES:
            raise AliexpressValidationError(f"Al massimo {MAX_ORDER_LINES} articoli diversi per ordine.")
        return lines
    if variant_id is None:
        raise AliexpressValidationError("Nessun prodotto da ordinare.")
    return [(variant_id, quantity)]


def creditable_cents_per_line(items: list[dict]) -> list[int]:
    """SosnetCash cap per line: the line's own percentage on its own total.
    The order cap is their sum.

    No order-wide average percentage, which after rounding could draw
    SosnetCash from a product that accepts none. Shipping is excluded:
    SosnetCash applies to goods only."""
    return [
        round(item["line_total_cents"] * item["credit_discount_percentage"] / 100)
        for item in items
    ]


async def get_quote(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    customer_user_id: uuid.UUID,
    variant_id: uuid.UUID | None = None,
    quantity: int = 1,
    lines: list[OrderLine] | None = None,
) -> dict:
    """Price a purchase per line and in total. Shipping is charged once per
    order, never per line."""
    row = await get_settings_row(db, organization_id=organization_id)
    if not row.enabled:
        raise AliexpressValidationError("Questo shop non è disponibile al momento.")

    items: list[dict] = []
    seen: set[uuid.UUID] = set()
    for line_variant_id, line_quantity in _lines_from(variant_id, quantity, lines):
        if line_quantity < 1 or line_quantity > MAX_QUANTITY:
            raise AliexpressValidationError(f"Quantità da 1 a {MAX_QUANTITY}.")
        if line_variant_id in seen:
            raise AliexpressValidationError("Lo stesso articolo compare due volte nell'ordine.")
        seen.add(line_variant_id)
        product, variant = await _sellable(db, organization_id=organization_id, variant_id=line_variant_id)
        if variant.inventory is not None and variant.inventory < line_quantity:
            raise AliexpressValidationError(
                f"«{product.name}»: disponibili solo {variant.inventory} pezzi."
            )
        unit = variant_price(variant)
        # The DS API quotes freight per product only; the order total is the sum.
        line_shipping = (
            0 if row.shipping_mode == "INCLUDED"
            else await supplier_shipping_cents(row=row, product=product, variant=variant, quantity=line_quantity)
        )
        items.append(
            {
                "variant_id": variant.id,
                "supplier_shipping_cents": line_shipping,
                "product_id": product.id,
                "product_name": product.name,
                "variant_label": variant.label,
                "image_url": variant.image_url or product.image_url,
                "quantity": line_quantity,
                "unit_price_cents": unit,
                "line_total_cents": unit * line_quantity,
                "credit_discount_percentage": product.credit_discount_percentage,
            }
        )

    items_cents = sum(i["line_total_cents"] for i in items)
    # Apply the minimum to the order's real total, not to each line.
    supplier_cents = sum(i["supplier_shipping_cents"] for i in items)
    shipping_cents = pricing.charged_shipping_cents(supplier_cents=supplier_cents, settings=row)
    vat_percentage = await rules.get_vat_percentage(db, organization_id=organization_id)
    # Displayed prices are net; VAT is added on goods only, not shipping.
    vat_cents = rules.vat_added_cents(net_cents=items_cents, percentage=vat_percentage)
    amount = items_cents + vat_cents + shipping_cents
    per_line = creditable_cents_per_line(items)
    for item, creditable in zip(items, per_line):
        item["max_creditable_cents"] = creditable
    # SosnetCash can never cover the whole order (marketplaces/rules.py).
    creditable_cents = min(sum(per_line), max(amount - 1, 0))
    # Displayed percentage is relative to goods, the same base as the cap;
    # for a single line it equals the product's own percentage.
    credit_percentage = round(creditable_cents * 100 / items_cents) if items_cents > 0 else 0
    wallet = await wallets_service.get_wallet_by_user_id(db, organization_id=organization_id, user_id=customer_user_id)
    methods = await payment_methods(db, organization_id=organization_id)
    discount_percentage = await rules.get_bank_transfer_discount_percentage(db, organization_id=organization_id)
    user = await db.get(User, customer_user_id)
    first = items[0]
    return {
        "items": items,
        # First-line fields for the single-product checkout; never totals.
        "variant_id": first["variant_id"],
        "product_name": first["product_name"],
        "variant_label": first["variant_label"],
        "quantity": first["quantity"],
        "unit_price_cents": first["unit_price_cents"],
        "items_cents": items_cents,
        #: VAT added on goods, already included in amount_cents.
        "vat_cents": vat_cents,
        "vat_percentage": vat_percentage,
        "shipping_cents": shipping_cents,
        #: Breakdown behind the charged shipping, for admin and margin
        #: reporting; customers only see `shipping_cents`.
        "supplier_shipping_cents": supplier_cents,
        "minimum_shipping_cents": row.shipping_minimum_cents or 0,
        "shipping_is_minimum": row.shipping_mode != "INCLUDED" and shipping_cents > supplier_cents,
        "shipping_included": row.shipping_mode == "INCLUDED",
        "shipping_days": row.shipping_days,
        "amount_cents": amount,
        "credit_discount_percentage": credit_percentage,
        "max_creditable_cents": creditable_cents,
        "customer_wallet_balance_cents": wallet.balance_cents if wallet else 0,
        "bank_transfer_discount_percentage": discount_percentage,
        "bank_transfer_amount_cents": bank_transfer_total_cents(residual_cents=amount, percentage=discount_percentage),
        "bank_transfer_available": methods["bank_transfer"],
        "card_available": methods["card"],
        "default_address": {
            "street": user.residence_street if user else None,
            "city": user.residence_city if user else None,
            "province": user.residence_province if user else None,
            "postal_code": user.residence_postal_code if user else None,
        },
    }


async def create_order(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    customer_user_id: uuid.UUID,
    address: dict,
    credit_applied_cents: int,
    payment_method: str,
    actor_user_id: uuid.UUID,
    otp_code: str | None,
    note: str | None,
    variant_id: uuid.UUID | None = None,
    quantity: int = 1,
    lines: list[OrderLine] | None = None,
) -> AliexpressOrder:
    """Create an order with every amount computed server-side, never taken
    from the client. Lines go to AliexpressOrderItem; all money stays on the
    header."""
    order_lines = _lines_from(variant_id, quantity, lines)
    quote = await get_quote(
        db, organization_id=organization_id, customer_user_id=customer_user_id, lines=order_lines,
    )
    row = await get_settings_row(db, organization_id=organization_id)
    amount = quote["amount_cents"]
    if credit_applied_cents < 0 or credit_applied_cents > quote["max_creditable_cents"]:
        raise AliexpressValidationError(
            f"Puoi usare al massimo {quote['max_creditable_cents'] / 100:.2f} SosnetCash per questo ordine."
        )
    if credit_applied_cents > 0:
        from app.modules.auth import service as auth_service

        if not otp_code or not await auth_service.verify_otp(
            db, user_id=customer_user_id, purpose=auth_service.WALLET_CREDIT_SPEND_OTP_PURPOSE, code=otp_code
        ):
            raise InvalidOtpError("Codice di conferma mancante, non valido o scaduto.")
    if payment_method not in ALIEXPRESS_ORDER_PAYMENT_METHODS:
        raise AliexpressValidationError("Metodo di pagamento non valido.")
    methods = await payment_methods(db, organization_id=organization_id)
    if payment_method == "BANK_TRANSFER" and not methods["bank_transfer"]:
        raise AliexpressValidationError("Il pagamento con bonifico non è configurato.")
    if payment_method == "CARD" and not methods["card"]:
        raise AliexpressValidationError("Il pagamento con carta non è configurato.")

    wallet = None
    if credit_applied_cents > 0:
        wallet = await wallets_service.get_or_create_wallet(
            db, organization_id=organization_id, user_id=customer_user_id
        )
        if wallet.balance_cents < credit_applied_cents:
            raise wallets_service.InsufficientBalanceError("Saldo SosnetCash insufficiente.")

    first = quote["items"][0]
    first_variant = await db.get(AliexpressVariant, first["variant_id"])
    order = AliexpressOrder(
        organization_id=organization_id,
        customer_user_id=customer_user_id,
        # Header line columns mirror the first line; the real lines are
        # AliexpressOrderItem rows.
        aliexpress_product_id=first["product_id"],
        aliexpress_variant_id=first["variant_id"],
        created_by_user_id=actor_user_id,
        quantity=first["quantity"],
        unit_price_cents=first["unit_price_cents"],
        shipping_cents=quote["shipping_cents"],
        #: Frozen so the shipping margin can be reconstructed later.
        supplier_shipping_cents=quote["supplier_shipping_cents"],
        minimum_shipping_cents=quote["minimum_shipping_cents"],
        amount_cents=amount,
        vat_percentage=quote["vat_percentage"],
        vat_amount_cents=quote["vat_cents"],
        vat_mode="ADDED",
        credit_applied_cents=credit_applied_cents,
        status="AWAITING_PAYMENT",
        payment_method=payment_method,
        note=note,
        recipient_name=address["recipient_name"],
        recipient_phone=address.get("recipient_phone"),
        address_line1=address["address_line1"],
        address_line2=address.get("address_line2"),
        city=address["city"],
        province=address["province"],
        postal_code=address["postal_code"],
        country_code=row.ship_to_country or "IT",
        shipping_days=row.shipping_days,
        unit_cost_amount=pricing.base_amount(
            cost=first_variant.cost_amount, price=first_variant.source_price_amount, settings=row
        )
        if first_variant is not None
        else None,
        currency_rate=row.currency_rate,
    )
    db.add(order)
    await db.flush()
    for item in quote["items"]:
        variant = await db.get(AliexpressVariant, item["variant_id"])
        db.add(
            AliexpressOrderItem(
                order_id=order.id,
                aliexpress_product_id=item["product_id"],
                aliexpress_variant_id=item["variant_id"],
                quantity=item["quantity"],
                unit_price_cents=item["unit_price_cents"],
                unit_cost_amount=pricing.base_amount(
                    cost=variant.cost_amount, price=variant.source_price_amount, settings=row
                )
                if variant is not None
                else None,
                supplier_shipping_cents=item["supplier_shipping_cents"],
                product_name=item["product_name"][:255],
                variant_label=(item["variant_label"] or None) and item["variant_label"][:255],
                credit_discount_percentage=item["credit_discount_percentage"],
            )
        )
    order.out_order_id = out_order_id(order)
    await freeze_bank_transfer_discount(db, order=order)
    await notifications_service.notify_roles(
        db, organization_id=organization_id, roles=notifications_service.STAFF_NOTIFY_ROLES,
        type_="ALIEXPRESS_ORDER_CREATED", entity_type="aliexpress_order", entity_id=order.id,
        title=f"Nuovo ordine AliExpress: {_items_summary(quote['items'])}",
        body=f"{amount / 100:.2f} EUR -- {_items_detail(quote['items'])}",
        exclude_user_id=actor_user_id,
    )
    if credit_applied_cents > 0:
        assert wallet is not None
        debit = await wallets_service.debit_wallet_for_aliexpress_purchase(
            db, organization_id=organization_id, wallet_id=wallet.id, amount_cents=credit_applied_cents,
            reference_aliexpress_order_id=order.id, actor_user_id=actor_user_id,
            note=f"Acquisto {_items_summary(quote['items'])}",
            idempotency_key=f"aliexpress-order:{order.id}:credit",
        )
        order.credit_debit_transaction_id = debit.id
    await db.commit()
    await db.refresh(order)
    await _send_order_email(db, order=order)
    return order


async def after_paid(db: AsyncSession, *, order: AliexpressOrder) -> None:
    """Queue automatic forwarding when `auto_forward` is on; otherwise the
    order waits for an administrator to send it manually."""
    row = await get_settings_row(db, organization_id=order.organization_id)
    if not row.auto_forward:
        return
    try:
        from app.celery_app import celery_app

        celery_app.send_task("app.celery_app.aliexpress_forward_order_task", args=[str(order.id)])
    except Exception:
        logger.exception("Could not queue AliExpress forwarding of order %s", order.id)


# --- Orders: reads ------------------------------------------------------------------------------------


async def get_org_scoped(
    db: AsyncSession, *, organization_id: uuid.UUID, order_id: uuid.UUID
) -> AliexpressOrder | None:
    order = await db.get(AliexpressOrder, order_id)
    if order is None or order.organization_id != organization_id:
        return None
    return order


async def get_owned(
    db: AsyncSession, *, organization_id: uuid.UUID, customer_user_id: uuid.UUID, order_id: uuid.UUID
) -> AliexpressOrder | None:
    order = await get_org_scoped(db, organization_id=organization_id, order_id=order_id)
    if order is None or order.customer_user_id != customer_user_id:
        return None
    return order


async def list_orders(
    db: AsyncSession, *, organization_id: uuid.UUID, customer_user_id: uuid.UUID | None = None,
    status_filter: str | None = None,
) -> list[AliexpressOrder]:
    stmt = select(AliexpressOrder).where(AliexpressOrder.organization_id == organization_id)
    if customer_user_id is not None:
        stmt = stmt.where(AliexpressOrder.customer_user_id == customer_user_id)
    if status_filter:
        stmt = stmt.where(AliexpressOrder.status == status_filter)
    return list((await db.execute(stmt.order_by(AliexpressOrder.created_at.desc()))).scalars())


def tracking_link(order: AliexpressOrder) -> str | None:
    if order.tracking_url:
        return order.tracking_url
    return f"https://t.17track.net/it#nums={order.tracking_number}" if order.tracking_number else None


def delivery_status(order: AliexpressOrder) -> str | None:
    """Customer-facing shipping state, same values as the other shops."""
    if order.status != "PAID":
        return None
    if order.fulfillment_status == "CANCELLED":
        return "PROBLEM"
    if order.fulfillment_status == "DELIVERED":
        return "DELIVERED"
    if order.fulfillment_status == "SHIPPED":
        return "SHIPPED"
    if order.fulfillment_status == "SENT":
        return "PREPARING"
    return "RECEIVED"


async def order_read_dict(db: AsyncSession, order: AliexpressOrder, *, admin: bool) -> dict:
    from app.modules.imported_products.service import _resolve_display_name

    product = await db.get(AliexpressProduct, order.aliexpress_product_id)
    variant = await db.get(AliexpressVariant, order.aliexpress_variant_id)
    # Header line fields below describe the first line only; `items` is
    # the authoritative list of what was bought.
    items = await order_items(db, order)
    out = {
        "id": order.id,
        "number": order.number,
        "order_code": order_code(order),
        "customer_user_id": order.customer_user_id,
        "customer_display_name": await _resolve_display_name(
            db, organization_id=order.organization_id, user_id=order.customer_user_id
        ),
        "aliexpress_product_id": order.aliexpress_product_id,
        "aliexpress_variant_id": order.aliexpress_variant_id,
        "product_name": product.name if product else "—",
        "product_image_url": (variant.image_url if variant and variant.image_url else None)
        or (product.image_url if product else None),
        "variant_label": variant.label if variant else None,
        "created_by_user_id": order.created_by_user_id,
        "quantity": order.quantity,
        "unit_price_cents": order.unit_price_cents,
        "shipping_cents": order.shipping_cents,
        "amount_cents": order.amount_cents,
        "credit_applied_cents": order.credit_applied_cents,
        "residual_amount_cents": order.amount_cents - order.credit_applied_cents,
        "bank_transfer_discount_cents": order.bank_transfer_discount_cents or 0,
        #: Frozen at order creation; interpret according to `vat_mode`.
        "vat_percentage": order.vat_percentage or 0,
        "vat_amount_cents": order.vat_amount_cents or 0,
        "vat_mode": order.vat_mode,
        "bank_transfer_discount_percentage": await rules.get_bank_transfer_discount_percentage(
            db, organization_id=order.organization_id
        ),
        "amount_due_cents": amount_due_cents(order),
        "status": order.status,
        "payment_method": order.payment_method,
        "stripe_checkout_session_id": order.stripe_checkout_session_id,
        "payment_proof_uploaded_at": order.payment_proof_uploaded_at,
        "note": order.note,
        "paid_at": order.paid_at,
        "cancelled_at": order.cancelled_at,
        "cancellation_reason": order.cancellation_reason,
        "created_at": order.created_at,
        "recipient_name": order.recipient_name,
        "recipient_phone": order.recipient_phone,
        "address_line1": order.address_line1,
        "address_line2": order.address_line2,
        "city": order.city,
        "province": order.province,
        "postal_code": order.postal_code,
        "country_code": order.country_code,
        "shipping_days": order.shipping_days,
        "items": [
            {
                "id": item.id,
                "product_id": item.aliexpress_product_id,
                "variant_id": item.aliexpress_variant_id,
                "product_name": item.product_name,
                "variant_label": item.variant_label,
                "quantity": item.quantity,
                "unit_price_cents": item.unit_price_cents,
                "line_total_cents": item.unit_price_cents * item.quantity,
                "supplier_shipping_cents": item.supplier_shipping_cents,
                # Per-line tracking when the supplier split the order,
                # otherwise the order-level tracking.
                "tracking_number": item.tracking_number or order.tracking_number,
                "tracking_url": item.tracking_url or tracking_link(order),
            }
            for item in items
        ],
        "delivery_status": delivery_status(order),
        "tracking_number": order.tracking_number,
        "tracking_url": tracking_link(order),
        "shipped_at": order.shipped_at,
        "delivered_at": order.delivered_at,
    }
    if admin:
        # Supplier cost sums every line; unknown if any line lacks a cost.
        per_line = [
            pricing.to_eur_cents(Decimal(item.unit_cost_amount) * item.quantity, Decimal(order.currency_rate))
            for item in items
            if item.unit_cost_amount is not None
        ]
        cost_cents = sum(per_line) if len(per_line) == len(items) and items else None
        out.update({
            "fulfillment_status": order.fulfillment_status,
            "aliexpress_order_id": order.aliexpress_order_id,
            "aliexpress_order_status": order.aliexpress_order_status,
            "out_order_id": order.out_order_id,
            "tracking_company": order.tracking_company,
            #: Shipping has its own margin (charged max(real, minimum) minus
            #: real cost); None when the real cost was not recorded.
            "supplier_shipping_cents": order.supplier_shipping_cents,
            "minimum_shipping_cents": order.minimum_shipping_cents,
            "shipping_margin_cents": (
                order.shipping_cents - order.supplier_shipping_cents
                if order.supplier_shipping_cents is not None else None
            ),
            #: One Sosnet order may map to several AliExpress orders (one
            #: per seller); this maps supplier order ids to lines.
            "item_supplier_orders": [
                {"item_id": item.id, "product_name": item.product_name,
                 "aliexpress_order_id": item.aliexpress_order_id}
                for item in items
            ],
            "unit_cost_amount": float(order.unit_cost_amount) if order.unit_cost_amount is not None else None,
            "currency_rate": float(order.currency_rate),
            "supplier_cost_cents": cost_cents,
            #: Taxable base (see taxable_base_cents) minus supplier goods
            #: cost and real shipping cost. VAT is never margin.
            "estimated_margin_cents": (
                taxable_base_cents(order) - cost_cents - (order.supplier_shipping_cents or 0)
                if cost_cents is not None else None
            ),
            "attempt_count": order.attempt_count,
            "last_attempt_at": order.last_attempt_at,
            "next_retry_at": order.next_retry_at,
            "last_error_kind": order.last_error_kind,
            "forwarded_at": order.forwarded_at,
            "forward_error": order.forward_error,
            "last_sync_at": order.last_sync_at,
        })
    return out


# --- Orders: payment (same flow as the other shops) --------------------------------------------------


async def _send_payment_receipt_email(
    db: AsyncSession, *, order: AliexpressOrder, items: list[AliexpressOrderItem], by_card: bool
) -> None:
    """Payment receipt email.

    Self-contained: repeats the item list rather than referring to the
    confirmation email. Figures are read frozen from the order, never
    recomputed. Best-effort: a send failure must not fail the already
    recorded payment.
    """
    user = await db.get(User, order.customer_user_id)
    if user is None:
        return
    code = order_code(order)
    title = _items_summary(items) if items else "il tuo ordine"
    rows = "".join(
        f"<tr>"
        f"<td style=\"padding:4px 0\">{html.escape(item.product_name)}"
        + (f"<br><small>{html.escape(item.variant_label)}</small>" if item.variant_label else "")
        + f"</td>"
        f"<td style=\"padding:4px 8px;text-align:center\">{item.quantity}</td>"
        f"<td style=\"padding:4px 0;text-align:right\">"
        f"{item.unit_price_cents * item.quantity / 100:.2f} &euro;</td>"
        f"</tr>"
        for item in items
    )
    body = (
        f"<p>Numero ordine: <strong>#{code}</strong></p>"
        f"<table style=\"width:100%;border-collapse:collapse;font-size:14px\">{rows}</table>"
        f"<p style=\"margin-top:12px\">Spedizione: {order.shipping_cents / 100:.2f} &euro;<br>"
    )
    if order.credit_applied_cents:
        body += f"SosnetCash utilizzati: -{order.credit_applied_cents / 100:.2f}<br>"
    if order.bank_transfer_discount_cents:
        body += f"Sconto per pagamento con bonifico: -{order.bank_transfer_discount_cents / 100:.2f} &euro;<br>"
    body += (
        f"<strong>Totale pagato: {amount_due_cents(order) / 100:.2f} &euro;</strong> "
        f"({'carta' if by_card else 'bonifico'})</p>"
    )
    if order.vat_amount_cents:
        # Informational: the frozen VAT is already part of the total paid.
        body += f"<p><small>IVA {order.vat_percentage}% inclusa nel prezzo: {order.vat_amount_cents / 100:.2f} &euro;</small></p>"
    body += (
        f"<p>Consegna a: {html.escape(order.recipient_name)}, {html.escape(order.address_line1)}, "
        f"{html.escape(order.postal_code)} {html.escape(order.city)} ({html.escape(order.province)})"
        + (f"<br>Consegna stimata in {html.escape(order.shipping_days)} giorni lavorativi" if order.shipping_days else "")
        + "</p>"
        "<p>Prepariamo la spedizione: ti avvisiamo appena parte, con il numero per seguirla.</p>"
    )
    send_html_email_best_effort(
        context=f"AliExpress payment receipt email (order={order.id})",
        to=user.email,
        subject=f"Pagamento ricevuto - ordine #{code} - SOSNET",
        html_body=render_email(
            preheader=f"Ricevuta di pagamento -- {title}",
            heading="Pagamento ricevuto, grazie",
            body_html=body,
            cta_label=None,
            cta_url=None,
        ),
        text_body=f"Pagamento ricevuto per l'ordine #{code}: {amount_due_cents(order) / 100:.2f} EUR.",
    )


async def _mark_paid(
    db: AsyncSession, *, order: AliexpressOrder, by_card: bool, actor_user_id: uuid.UUID | None
) -> None:
    order.status = "PAID"
    order.paid_by_user_id = actor_user_id
    order.paid_at = utcnow()
    items = await order_items(db, order)
    name = _items_summary(items) if items else "un prodotto"
    await notifications_service.notify_user(
        db, organization_id=order.organization_id, user_id=order.customer_user_id, type_="ORDER_PAID",
        entity_type="aliexpress_order", entity_id=order.id, title=f"Il tuo ordine per {name} è confermato",
        body="Ti avvisiamo appena viene spedito.",
    )
    await notifications_service.notify_roles(
        db, organization_id=order.organization_id, roles=notifications_service.STAFF_NOTIFY_ROLES,
        type_="ALIEXPRESS_ORDER_PAID", entity_type="aliexpress_order", entity_id=order.id,
        title=f"{'Pagamento Stripe' if by_card else 'Bonifico'} confermato: {name}",
        body=f"{amount_due_cents(order) / 100:.2f} EUR -- da inviare ad AliExpress",
    )
    # The receipt is sent only here. Both callers reject orders not in
    # AWAITING_PAYMENT, so a replayed Stripe webhook sends no second receipt.
    await _send_payment_receipt_email(db, order=order, items=items, by_card=by_card)


async def confirm_payment(
    db: AsyncSession, *, organization_id: uuid.UUID, order_id: uuid.UUID, actor_user_id: uuid.UUID
) -> AliexpressOrder:
    order = await get_org_scoped(db, organization_id=organization_id, order_id=order_id)
    if order is None:
        raise AliexpressNotFoundError("Ordine non trovato.")
    if order.status != "AWAITING_PAYMENT":
        raise AliexpressValidationError("Questo ordine non è in attesa di pagamento.")
    if order.payment_method == "CARD":
        raise AliexpressValidationError("Un ordine pagato con carta viene confermato automaticamente da Stripe.")
    await _mark_paid(db, order=order, by_card=False, actor_user_id=actor_user_id)
    await db.commit()
    await db.refresh(order)
    await after_paid(db, order=order)
    return order


async def mark_paid_via_stripe(
    db: AsyncSession, *, organization_id: uuid.UUID, stripe_checkout_session_id: str, order_id: str | None = None
) -> AliexpressOrder | None:
    """Mark a card order paid from the Stripe webhook. Idempotent.

    `order_id` from the session metadata is the fallback lookup: a customer
    may pay through an older link (e.g. the confirmation email's) after a
    newer checkout replaced the session id stored on the order."""
    order = (
        await db.execute(
            select(AliexpressOrder).where(
                AliexpressOrder.organization_id == organization_id,
                AliexpressOrder.stripe_checkout_session_id == stripe_checkout_session_id,
            )
        )
    ).scalar_one_or_none()
    if order is None and order_id:
        try:
            order = await get_org_scoped(db, organization_id=organization_id, order_id=uuid.UUID(str(order_id)))
        except ValueError:
            order = None
    if order is None or order.status != "AWAITING_PAYMENT":
        return order
    await _mark_paid(db, order=order, by_card=True, actor_user_id=None)
    await db.commit()
    await db.refresh(order)
    await after_paid(db, order=order)
    return order


async def cancel_order(
    db: AsyncSession, *, organization_id: uuid.UUID, order_id: uuid.UUID, reason: str, actor_user_id: uuid.UUID
) -> AliexpressOrder:
    order = await get_org_scoped(db, organization_id=organization_id, order_id=order_id)
    if order is None:
        raise AliexpressNotFoundError("Ordine non trovato.")
    if order.status != "AWAITING_PAYMENT":
        raise AliexpressValidationError("Si può annullare solo un ordine non ancora pagato.")
    if order.credit_debit_transaction_id is not None:
        await wallets_service.reverse_transaction(
            db, organization_id=organization_id, transaction_id=order.credit_debit_transaction_id,
            actor_user_id=actor_user_id, reason=f"Ordine annullato: {reason}",
            idempotency_key=f"aliexpress-order:{order.id}:cancel-refund",
        )
    order.status = "CANCELLED"
    order.cancelled_by_user_id = actor_user_id
    order.cancelled_at = utcnow()
    order.cancellation_reason = reason
    await db.commit()
    await db.refresh(order)
    return order


async def change_payment_method(
    db: AsyncSession, *, organization_id: uuid.UUID, order: AliexpressOrder, new_payment_method: str
) -> AliexpressOrder:
    if order.status != "AWAITING_PAYMENT":
        raise AliexpressValidationError("Il metodo di pagamento si cambia solo prima di pagare.")
    if new_payment_method not in ALIEXPRESS_ORDER_PAYMENT_METHODS:
        raise AliexpressValidationError("Metodo di pagamento non valido.")
    if new_payment_method != order.payment_method:
        methods = await payment_methods(db, organization_id=organization_id)
        if new_payment_method == "BANK_TRANSFER" and not methods["bank_transfer"]:
            raise AliexpressValidationError("Il pagamento con bonifico non è configurato.")
        if new_payment_method == "CARD" and not methods["card"]:
            raise AliexpressValidationError("Il pagamento con carta non è configurato.")
        if order.payment_method == "CARD":
            order.stripe_checkout_session_id = None
        order.payment_method = new_payment_method
        await freeze_bank_transfer_discount(db, order=order)
        await db.commit()
        await db.refresh(order)
    return order


async def upload_payment_proof(
    db: AsyncSession, *, organization_id: uuid.UUID, order: AliexpressOrder, file_bytes: bytes, content_type: str,
    original_filename: str, actor_user_id: uuid.UUID,
) -> AliexpressOrder:
    from app.foundation.storage import UploadValidationError
    from app.foundation.storage import upload_document as storage_upload_document

    if order.status != "AWAITING_PAYMENT" or order.payment_method != "BANK_TRANSFER":
        raise AliexpressValidationError("La ricevuta si carica solo per un ordine da pagare con bonifico.")
    try:
        storage_key = storage_upload_document(
            file_bytes=file_bytes, content_type=content_type,
            key_prefix=f"aliexpress-order-payment-proofs/{order.customer_user_id}",
        )
    except UploadValidationError as exc:
        raise AliexpressValidationError(str(exc)) from exc
    order.payment_proof_storage_key = storage_key
    order.payment_proof_original_filename = original_filename
    order.payment_proof_uploaded_at = utcnow()
    await notifications_service.notify_roles(
        db, organization_id=organization_id, roles=notifications_service.STAFF_NOTIFY_ROLES,
        type_="ORDER_PAYMENT_PROOF_UPLOADED", entity_type="aliexpress_order", entity_id=order.id,
        title="Ricevuta di bonifico caricata: ordine AliExpress", body=None, exclude_user_id=actor_user_id,
    )
    await db.commit()
    await db.refresh(order)
    return order


def presigned_payment_proof_url(order: AliexpressOrder) -> str:
    from app.foundation.storage import generate_presigned_document_url

    assert order.payment_proof_storage_key is not None
    return generate_presigned_document_url(storage_key=order.payment_proof_storage_key, expires_in_seconds=300)


async def prepare_card_payment(db: AsyncSession, *, order: AliexpressOrder) -> int:
    """Switch the order to card (dropping the bank-transfer discount) and
    return the amount Stripe must charge. Does not commit."""
    order.payment_method = "CARD"
    await freeze_bank_transfer_discount(db, order=order)
    await db.flush()
    return amount_due_cents(order)


async def attach_stripe_checkout_session(
    db: AsyncSession, *, order: AliexpressOrder, session_id: str
) -> AliexpressOrder:
    order.payment_method = "CARD"
    order.stripe_checkout_session_id = session_id
    await db.commit()
    await db.refresh(order)
    return order


async def _send_order_email(db: AsyncSession, *, order: AliexpressOrder) -> None:
    user = await db.get(User, order.customer_user_id)
    if user is None:
        return
    settings = get_settings()
    code = order_code(order)
    items = await order_items(db, order)
    title = _items_summary(items)
    # One row per line, using the names frozen on the order.
    rows = "".join(
        f"<br><strong>{html.escape(item.product_name)}</strong>"
        + (f" — {html.escape(item.variant_label)}" if item.variant_label else "")
        + f" × {item.quantity} — {item.unit_price_cents * item.quantity / 100:.2f} &euro;"
        for item in items
    )
    lines = (
        f"<p>Numero ordine: <strong>#{code}</strong></p>"
        f"<p>{rows.removeprefix('<br>')}<br>"
        f"Spedizione: {order.shipping_cents / 100:.2f} &euro;"
        + (f" (consegna stimata {html.escape(order.shipping_days)} giorni)" if order.shipping_days else "")
        + f"<br>Totale: <strong>{order.amount_cents / 100:.2f} &euro;</strong>"
        + (f" (di cui {order.credit_applied_cents / 100:.2f} SosnetCash)" if order.credit_applied_cents else "")
        # Informational: the frozen VAT is already part of the total.
        + (
            f"<br><small>IVA {order.vat_percentage}% inclusa: {order.vat_amount_cents / 100:.2f} &euro;</small>"
            if order.vat_amount_cents
            else ""
        )
        + "</p>"
        f"<p>Consegna a: {html.escape(order.recipient_name)}, {html.escape(order.address_line1)}, "
        f"{html.escape(order.postal_code)} {html.escape(order.city)} ({html.escape(order.province)})</p>"
    )
    residual = order.amount_cents - order.credit_applied_cents
    cta_label = cta_url = None
    heading = "Completa il pagamento del tuo ordine"
    if order.payment_method == "CARD":
        from app.modules.payments import service as payments_service

        lines += f"<p>Da pagare con carta: <strong>{amount_due_cents(order) / 100:.2f} &euro;</strong></p>"
        try:
            cta_url = await payments_service.create_checkout_session_for_aliexpress_order(
                db, organization_id=order.organization_id, order=order,
                success_url=f"{settings.public_app_base_url}/customer?tab=orders",
                cancel_url=f"{settings.public_app_base_url}/customer?tab=orders",
            )
            cta_label = "Paga con carta"
        except (payments_service.StripeNotConfiguredError, stripe.error.StripeError):
            logger.exception("AliExpress order %s confirmation email sent without a Stripe link", order.id)
    else:
        bank = await organizations_service.get_settings(db, organization_id=order.organization_id)
        discount = order.bank_transfer_discount_cents or 0
        lines += f"<p>Da pagare con bonifico: <strong>{amount_due_cents(order) / 100:.2f} &euro;</strong>"
        if discount:
            lines += (
                f"<br><small>Include lo sconto per il pagamento con bonifico ({discount / 100:.2f} &euro;); "
                f"con carta sarebbero {residual / 100:.2f} &euro;.</small>"
            )
        lines += "</p>"
        if bank.get("bank_iban"):
            lines += (
                f"<p><strong>IBAN:</strong> {bank['bank_iban']}<br>"
                f"<strong>Intestatario:</strong> {bank.get('bank_account_holder') or 'SOSNET'}<br>"
                f"<strong>Causale:</strong> Ordine {code}</p>"
            )
    send_html_email_best_effort(
        context=f"AliExpress order confirmation email (order={order.id})",
        to=user.email,
        subject=f"Conferma ordine - {title} - SOSNET",
        html_body=render_email(
            preheader=f"Riepilogo del tuo ordine -- {title}", heading=heading, body_html=lines,
            cta_label=cta_label, cta_url=cta_url,
        ),
        text_body=f"{heading}: {title}, totale {order.amount_cents / 100:.2f} EUR.",
    )


# --- Fulfillment on AliExpress ------------------------------------------------------------------
#
# A paid order is placed on AliExpress with its SKUs, quantities, the
# customer's address and our `out_order_id`.
#
# Never two supplier orders, whatever fails:
# - one sender at a time: a conditional UPDATE claims the order (-> SENDING);
# - `out_order_id` is deterministic, so a duplicated request is the same order.
#
# The DS API offers no lookup by our reference, so when the ds.order.create
# response is lost we do NOT retry automatically: the order may already exist
# and be charged. It goes to ERROR, staff are alerted, and a human decides.


def _schedule_retry(order: AliexpressOrder, kind: str, *, may_exist: bool = False) -> None:
    order.last_error_kind = kind
    if may_exist:
        # The order may exist on AliExpress: never retry automatically.
        order.next_retry_at = None
    elif kind in ("TEMPORARY", "AUTHENTICATION") and order.attempt_count < MAX_ATTEMPTS:
        minutes = min(5 * 2 ** max(order.attempt_count - 1, 0), 360)
        order.next_retry_at = utcnow() + timedelta(minutes=minutes)
    else:
        order.next_retry_at = None


async def _staff_alert(db: AsyncSession, *, order: AliexpressOrder, type_: str, title: str, body: str) -> None:
    await notifications_service.notify_roles(
        db, organization_id=order.organization_id, roles=notifications_service.STAFF_NOTIFY_ROLES,
        type_=type_, entity_type="aliexpress_order", entity_id=order.id, title=title[:255], body=body[:1000],
    )


def _phone_digits(value: str | None) -> str:
    return re.sub(r"\D", "", value or "")[:20]


async def _order_request(db: AsyncSession, order: AliexpressOrder) -> dict:
    """Body of ds.order.create (PlaceOrderRequest4OpenApiDTO in the DS docs).

    One `product_items` entry per line, each identified by `sku_attr`; a
    variant without it cannot be ordered. Lines from different sellers
    produce several supplier orders (see _order_ids_from_answer())."""
    product_items = []
    for item in await order_items(db, order):
        variant = await db.get(AliexpressVariant, item.aliexpress_variant_id)
        product = await db.get(AliexpressProduct, item.aliexpress_product_id)
        if variant is None or product is None:
            raise AliexpressValidationError(
                f"«{item.product_name}»: prodotto o variante dell'ordine non più presenti."
            )
        if not variant.sku_attr:
            raise AliexpressValidationError(
                f"«{item.product_name}» non ha l'identificativo SKU di AliExpress: "
                "risincronizza il prodotto prima di inviare."
            )
        product_items.append(
            {
                "product_count": item.quantity,
                "product_id": product.aliexpress_product_id,
                "sku_attr": variant.sku_attr,
                "order_memo": order_number(order),
            }
        )
    address = {
        "address": order.address_line1[:255],
        "address2": (order.address_line2 or "")[:255],
        "city": order.city[:100],
        "contact_person": order.recipient_name[:100],
        "country": order.country_code,
        "full_name": order.recipient_name[:100],
        "mobile_no": _phone_digits(order.recipient_phone),
        # Unverified: the dialling prefix goes apart from the number; only
        # Italy is supported.
        "phone_country": "+39" if order.country_code == "IT" else "",
        "province": order.province[:64],
        "zip": order.postal_code,
    }
    return {
        "logistics_address": address,
        "product_items": product_items,
        "out_order_id": order.out_order_id or out_order_id(order),
    }


def _order_ids_from_answer(body: dict) -> list[str]:
    """All supplier order ids created (result.order_list.number).

    Lines from different sellers become separate AliExpress orders, and each
    must be tracked. The response order is not guaranteed to match our
    lines; forward_order assigns ids to lines only when counts match."""
    node = aliexpress.first(
        body,
        ("aliexpress_ds_order_create_response", "result", "order_list"),
        ("aliexpress_ds_order_create_response", "resp_result", "result", "order_list"),
        ("result", "order_list"),
        ("order_list",),
    )
    found: list[str] = []
    for value in aliexpress.items_of(node, "number", "order_id", "orderId"):
        if isinstance(value, dict):
            value = _pick(value, "order_id", "orderId", "number")
        if value not in (None, "") and str(value) not in found:
            found.append(str(value))
    if found:
        return found
    single = aliexpress.first(
        body,
        ("aliexpress_ds_order_create_response", "result", "order_id"),
        ("result", "order_id"),
        ("order_id",),
    )
    return [str(single)] if single not in (None, "", [], {}) else []


async def forward_order(
    db: AsyncSession, *, organization_id: uuid.UUID, order_id: uuid.UUID, actor_user_id: uuid.UUID | None
) -> AliexpressOrder:
    """Place the paid order on AliExpress exactly once. Safe to call
    repeatedly (automatic flow, retry job, administrator); failures are
    recorded on the order, not raised."""
    order = await get_org_scoped(db, organization_id=organization_id, order_id=order_id)
    if order is None:
        raise AliexpressNotFoundError("Ordine non trovato.")
    if order.status != "PAID":
        raise AliexpressValidationError("Si invia ad AliExpress solo un ordine già pagato dal cliente.")
    if order.aliexpress_order_id:
        raise AliexpressValidationError("Questo ordine è già su AliExpress.")
    now = utcnow()
    claimed = await db.execute(
        update(AliexpressOrder)
        .where(
            AliexpressOrder.id == order.id,
            AliexpressOrder.aliexpress_order_id.is_(None),
            or_(
                AliexpressOrder.fulfillment_status.in_(("NOT_SENT", "ERROR")),
                and_(
                    AliexpressOrder.fulfillment_status == "SENDING",
                    AliexpressOrder.last_attempt_at < now - timedelta(minutes=10),
                ),
            ),
        )
        .values(fulfillment_status="SENDING", last_attempt_at=now, attempt_count=AliexpressOrder.attempt_count + 1)
    )
    await db.commit()
    if claimed.rowcount != 1:
        await db.refresh(order)
        raise AliexpressValidationError("Questo ordine è già in lavorazione proprio ora.")
    await db.refresh(order)
    row = await get_settings_row(db, organization_id=organization_id)
    sent = False
    try:
        request = await _order_request(db, order)
        order.out_order_id = request["out_order_id"]
        await db.commit()  # persist the reference before sending, in case the response is lost
        sent = True
        body = await aliexpress.order_create(row, request=request)
        supplier_order_ids = _order_ids_from_answer(body)
        if not supplier_order_ids:
            # Success without an id: outcome unknown, must not auto-retry.
            raise aliexpress.AliexpressApiError(
                "AliExpress ha accettato la richiesta senza restituire il numero d'ordine: "
                "controlla su AliExpress prima di riprovare.",
                "TEMPORARY",
            )
        # Header gets the first id. Lines get one each only when counts
        # match (or all share a single id); otherwise matching would be a
        # guess, so staff reconcile manually.
        items = await order_items(db, order)
        if len(supplier_order_ids) == len(items):
            for item, supplier_id in zip(items, supplier_order_ids):
                item.aliexpress_order_id = supplier_id[:128]
        elif len(supplier_order_ids) == 1:
            for item in items:
                item.aliexpress_order_id = supplier_order_ids[0][:128]
        else:
            await _staff_alert(
                db, order=order, type_="ALIEXPRESS_ORDER_SPLIT",
                title=f"Ordine AliExpress diviso dal fornitore: #{order_code(order)}",
                body=(
                    f"AliExpress ha creato {len(supplier_order_ids)} ordini per {len(items)} articoli "
                    f"({', '.join(supplier_order_ids)}): abbina i tracking a mano."
                ),
            )
        order.aliexpress_order_id = supplier_order_ids[0][:128]
        order.fulfillment_status = "SENT"
        order.forwarded_at = order.forwarded_at or utcnow()
        order.forwarded_by_user_id = actor_user_id
        order.forward_error = None
        order.last_error_kind = None
        order.next_retry_at = None
        await audit_service.record(
            db, organization_id=organization_id, actor_user_id=actor_user_id,
            action="aliexpress.order_created", entity_type="aliexpress_order", entity_id=str(order.id),
            new_value={
                "aliexpress_order_id": order.aliexpress_order_id,
                "aliexpress_order_ids": supplier_order_ids,
                "out_order_id": order.out_order_id,
            },
        )
        await db.commit()
    except (aliexpress.AliexpressApiError, AliexpressValidationError) as exc:
        kind = getattr(exc, "kind", "VALIDATION")
        may_exist = sent and kind == "TEMPORARY"
        logger.warning("AliExpress forwarding failed for order %s (%s): %s", order.id, kind, exc)
        order.fulfillment_status = "ERROR"
        order.forward_error = str(exc)[:500]
        _schedule_retry(order, kind, may_exist=may_exist)
        if order.next_retry_at is None:
            await _staff_alert(
                db, order=order, type_="ALIEXPRESS_ORDER_FAILED",
                title=f"Ordine #{order_code(order)}: serve un controllo su AliExpress",
                body=(
                    f"{exc}. "
                    + (
                        f"L'ordine potrebbe essere già stato creato: cercalo su AliExpress con il riferimento "
                        f"{order.out_order_id}. "
                        if may_exist else ""
                    )
                    + "Il cliente ha pagato e vede \"Ordine ricevuto\". Marketplace AliExpress → Ordini."
                ),
            )
        await db.commit()
    await db.refresh(order)
    return order


# --- Tracking -------------------------------------------------------------------------------------
#
# Tracking responses vary widely, so they are walked recursively: the first
# plausible waybill number, carrier and status win, and delivery is detected
# from both status values and event text.

TRACKING_NUMBER_KEYS = ("mail_no", "mailNo", "logistics_no", "logisticsNo", "tracking_number", "trackingNumber", "waybill_no")
TRACKING_URL_KEYS = ("official_website", "officialWebsite", "tracking_url", "trackingUrl", "track_url")
TRACKING_COMPANY_KEYS = (
    "logistics_service_name", "logisticsServiceName", "carrier", "company", "logistics_company", "service_name",
    "serviceName", "provider_name",
)
TRACKING_STATUS_KEYS = (
    "status", "logistics_status", "logisticsStatus", "package_status", "tracking_status", "current_status", "state",
)
TRACKING_EVENT_KEYS = ("event_desc", "eventDesc", "status_desc", "description", "track_content")
#: API vocabulary plus Italian carrier wording.
DELIVERED_WORDS = ("delivered", "signed", "sign_in", "signfor", "consegnat", "consegna effettuata")
SHIPPED_WORDS = ("shipped", "transit", "in_transit", "departed", "picked", "accepted", "spedit", "in viaggio")


def _walk(node, found: dict) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            if isinstance(value, (dict, list)):
                _walk(value, found)
                continue
            if value in (None, ""):
                continue
            text = str(value)
            if key in TRACKING_NUMBER_KEYS:
                found.setdefault("number", text)
            elif key in TRACKING_URL_KEYS and text.startswith("http"):
                found.setdefault("url", text)
            elif key in TRACKING_COMPANY_KEYS:
                found.setdefault("company", text)
            elif key in TRACKING_STATUS_KEYS:
                found.setdefault("status", text)
                found.setdefault("words", "")
                found["words"] += " " + text
            elif key in TRACKING_EVENT_KEYS:
                found.setdefault("words", "")
                found["words"] += " " + text
    elif isinstance(node, list):
        for item in node:
            _walk(item, found)


def _tracking_from_remote(body: dict) -> tuple[str | None, dict, str | None]:
    """(our fulfillment status or None if unchanged, tracking info, raw
    supplier status)."""
    found: dict = {}
    _walk(body, found)
    words = (found.get("words", "") + " " + found.get("status", "")).lower()
    tracking = {k: found.get(k) for k in ("number", "url", "company") if found.get(k)}
    if any(word in words for word in DELIVERED_WORDS):
        return "DELIVERED", tracking, found.get("status")
    if "cancel" in words or "annullat" in words:
        return "CANCELLED", tracking, found.get("status")
    if tracking.get("number") or any(word in words for word in SHIPPED_WORDS):
        return "SHIPPED", tracking, found.get("status")
    return None, tracking, found.get("status")


async def sync_orders(
    db: AsyncSession, *, organization_id: uuid.UUID, orders: list[AliexpressOrder] | None = None
) -> int:
    """Poll tracking for in-flight orders, notifying the customer on
    shipment and delivery. Returns the number of orders changed."""
    row = await get_settings_row(db, organization_id=organization_id)
    if not aliexpress.is_connected(row):
        return 0
    if orders is None:
        orders = list(
            (
                await db.execute(
                    select(AliexpressOrder).where(
                        AliexpressOrder.organization_id == organization_id,
                        AliexpressOrder.aliexpress_order_id.is_not(None),
                        AliexpressOrder.fulfillment_status.in_(FOLLOWED_FULFILLMENT),
                    )
                )
            ).scalars()
        )
    changed = 0
    for order in orders:
        if not order.aliexpress_order_id:
            continue
        try:
            body = await aliexpress.order_tracking(row, order_id=order.aliexpress_order_id)
        except aliexpress.AliexpressApiError as exc:
            # Skip and retry on the next run; one failure must not block others.
            logger.info("AliExpress tracking unavailable for order %s: %s", order.id, exc)
            order.last_sync_at = utcnow()
            continue
        order.last_sync_at = utcnow()
        new_status, tracking, remote_status = _tracking_from_remote(body)
        previous = order.fulfillment_status
        previous_tracking = order.tracking_number
        if remote_status:
            order.aliexpress_order_status = remote_status[:64]
        if tracking:
            order.tracking_number = (tracking.get("number") or "")[:128] or order.tracking_number
            order.tracking_url = (tracking.get("url") or "")[:1000] or order.tracking_url
            order.tracking_company = (tracking.get("company") or "")[:128] or order.tracking_company
        if new_status and order.fulfillment_status != "SENDING":
            order.fulfillment_status = new_status
        if order.fulfillment_status == previous and order.tracking_number == previous_tracking:
            continue
        changed += 1
        if order.fulfillment_status == "SHIPPED" and previous != "SHIPPED":
            order.shipped_at = utcnow()
            await _notify_customer_shipping(db, order=order, delivered=False)
        elif order.fulfillment_status == "DELIVERED" and previous != "DELIVERED":
            order.delivered_at = utcnow()
            order.shipped_at = order.shipped_at or utcnow()
            await _notify_customer_shipping(db, order=order, delivered=True)
        elif order.fulfillment_status == "CANCELLED" and previous != "CANCELLED":
            await _staff_alert(
                db, order=order, type_="ALIEXPRESS_ORDER_FAILED",
                title=f"AliExpress ha annullato l'ordine {order_code(order)}",
                body="Il cliente ha già pagato: valuta rimborso o nuovo invio.",
            )
    await db.commit()
    return changed


async def retry_due_orders(db: AsyncSession, *, organization_id: uuid.UUID) -> int:
    """Safety net for automatic forwarding: unsent paid orders, stale
    SENDING claims and temporary failures due for retry (bounded attempts).
    Orders whose response was lost are excluded (see forward_order)."""
    row = await get_settings_row(db, organization_id=organization_id)
    if not aliexpress.is_connected(row) or not row.auto_forward:
        return 0
    now = utcnow()
    due = list(
        (
            await db.execute(
                select(AliexpressOrder)
                .where(
                    AliexpressOrder.organization_id == organization_id,
                    AliexpressOrder.status == "PAID",
                    AliexpressOrder.aliexpress_order_id.is_(None),
                    or_(
                        and_(
                            AliexpressOrder.fulfillment_status == "NOT_SENT",
                            AliexpressOrder.paid_at < now - timedelta(minutes=2),
                        ),
                        and_(
                            AliexpressOrder.fulfillment_status == "ERROR",
                            AliexpressOrder.next_retry_at.is_not(None),
                            AliexpressOrder.next_retry_at <= now,
                        ),
                        and_(
                            AliexpressOrder.fulfillment_status == "SENDING",
                            AliexpressOrder.last_attempt_at < now - timedelta(minutes=10),
                        ),
                    ),
                )
                .order_by(AliexpressOrder.paid_at)
            )
        ).scalars()
    )
    handled = 0
    for order in due:
        try:
            await forward_order(db, organization_id=organization_id, order_id=order.id, actor_user_id=None)
            handled += 1
        except AliexpressError:
            continue
    return handled


async def _notify_customer_shipping(db: AsyncSession, *, order: AliexpressOrder, delivered: bool) -> None:
    # Summarise all lines so a multi-item order does not look partial.
    items = await order_items(db, order)
    name = _items_summary(items) if items else "il tuo ordine"
    title = f"{name} è stato consegnato" if delivered else f"{name} è stato spedito"
    body = None if delivered else (f"Numero di tracking: {order.tracking_number}" if order.tracking_number else None)
    await notifications_service.notify_user(
        db, organization_id=order.organization_id, user_id=order.customer_user_id, type_="ORDER_SHIPPED",
        entity_type="aliexpress_order", entity_id=order.id, title=title, body=body,
    )
    user = await db.get(User, order.customer_user_id)
    if user is None:
        return
    link = tracking_link(order)
    body_html = (
        f"<p>Numero ordine: <strong>#{order_code(order)}</strong></p>"
        f"<p><strong>{html.escape(name)}</strong> {'è stato consegnato' if delivered else 'è in viaggio verso di te'}.</p>"
    )
    if not delivered and order.tracking_number:
        body_html += f"<p>Numero di tracking: <strong>{html.escape(order.tracking_number)}</strong></p>"
    send_html_email_best_effort(
        context=f"AliExpress order shipping email (order={order.id}, delivered={delivered})",
        to=user.email,
        subject=f"{'Consegnato' if delivered else 'Spedito'}: {name} - SOSNET",
        html_body=render_email(
            preheader=title, heading=title, body_html=body_html,
            cta_label=None if delivered or not link else "Segui la spedizione",
            cta_url=None if delivered else link,
        ),
        text_body=title + (f" Tracking: {order.tracking_number}" if order.tracking_number and not delivered else ""),
    )
