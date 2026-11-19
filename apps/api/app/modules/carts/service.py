"""Cart contents, pricing and hand-off to checkout.

This module knows no prices. It tracks a customer's lines per shop and asks
the shop for a quote (`aliexpress_dropshipping.get_quote` and its
counterparts), which is the only place pricing lives.

The `SHOPS` registry is the single place to wire a new shop into the cart:
the line column and the quote function.

**Carts store no prices.** Every read reprices from current list prices, so
a stale price can never be claimed and no amount can be tampered with from
the browser.
"""

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.aliexpress_dropshipping import service as aliexpress_service
from app.modules.carts.models import CART_SHOPS, MAX_ITEM_QUANTITY, Cart, CartItem
from app.modules.cj_dropshipping import service as cj_service
from app.modules.sosnet_market import service as sosnet_market_service
from app.modules.shopify_dropshipping import service as shopify_service


class CartValidationError(ValueError):
    """Carries a customer-facing message, already in Italian."""


class CartNotFoundError(LookupError):
    pass


@dataclass(frozen=True)
class ShopBinding:
    """How a shop plugs into the cart."""

    #: `CartItem` column referencing this shop's variant.
    column: str
    #: The shop's quote function, called with `lines=[(variant_id, qty), ...]`.
    quote: Callable[..., Awaitable[dict]]
    #: Exceptions the shop raises when a line cannot be sold.
    errors: tuple[type[Exception], ...]


SHOPS: dict[str, ShopBinding] = {
    "aliexpress": ShopBinding(
        column="aliexpress_variant_id",
        quote=aliexpress_service.get_quote,
        errors=(aliexpress_service.AliexpressValidationError, aliexpress_service.AliexpressNotFoundError),
    ),
    "cj": ShopBinding(
        column="cj_variant_id",
        quote=cj_service.get_quote,
        errors=(cj_service.CjValidationError, cj_service.CjNotFoundError),
    ),
    "sosnet_market": ShopBinding(
        column="sosnet_market_variant_id",
        quote=sosnet_market_service.get_quote,
        errors=(sosnet_market_service.SosnetMarketValidationError, sosnet_market_service.SosnetMarketNotFoundError),
    ),
    "shopify": ShopBinding(
        column="shopify_variant_id",
        quote=shopify_service.get_quote,
        errors=(shopify_service.ShopifyValidationError, shopify_service.ShopifyNotFoundError),
    ),
}


def _binding(shop: str) -> ShopBinding:
    if shop not in CART_SHOPS:
        raise CartValidationError("Negozio sconosciuto.")
    binding = SHOPS.get(shop)
    if binding is None:
        raise CartValidationError("Il carrello non è ancora attivo su questo negozio.")
    return binding


# --- Contents -------------------------------------------------------------------------------------


async def get_or_create_cart(
    db: AsyncSession, *, organization_id: uuid.UUID, customer_user_id: uuid.UUID, shop: str
) -> Cart:
    """Return the customer's cart for the shop, creating it if missing.

    Safe under concurrency thanks to UNIQUE(customer_user_id, shop): a
    losing insert rolls back and re-reads the winner's cart."""
    _binding(shop)
    found = await db.execute(
        select(Cart).where(Cart.customer_user_id == customer_user_id, Cart.shop == shop)
    )
    cart = found.scalar_one_or_none()
    if cart is not None:
        return cart
    cart = Cart(organization_id=organization_id, customer_user_id=customer_user_id, shop=shop)
    db.add(cart)
    try:
        await db.flush()
    except Exception:
        await db.rollback()
        found = await db.execute(
            select(Cart).where(Cart.customer_user_id == customer_user_id, Cart.shop == shop)
        )
        cart = found.scalar_one_or_none()
        if cart is None:
            raise
    return cart


async def _items(db: AsyncSession, cart: Cart) -> list[CartItem]:
    rows = await db.execute(
        select(CartItem).where(CartItem.cart_id == cart.id).order_by(CartItem.created_at, CartItem.id)
    )
    return list(rows.scalars().all())


def _variant_id(item: CartItem, binding: ShopBinding) -> uuid.UUID:
    return getattr(item, binding.column)


async def add_item(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    customer_user_id: uuid.UUID,
    shop: str,
    variant_id: uuid.UUID,
    quantity: int = 1,
) -> Cart:
    """Add a line or increase its quantity.

    The line is quoted by the shop first, so a disabled, out-of-stock or
    other-organization product is rejected now with its own message rather
    than failing later at checkout.
    """
    binding = _binding(shop)
    if quantity < 1:
        raise CartValidationError("La quantità deve essere almeno 1.")
    cart = await get_or_create_cart(
        db, organization_id=organization_id, customer_user_id=customer_user_id, shop=shop
    )
    existing = await db.execute(
        select(CartItem).where(
            CartItem.cart_id == cart.id, getattr(CartItem, binding.column) == variant_id
        )
    )
    item = existing.scalar_one_or_none()
    wanted = (item.quantity if item else 0) + quantity
    if wanted > MAX_ITEM_QUANTITY:
        raise CartValidationError(f"Al massimo {MAX_ITEM_QUANTITY} pezzi dello stesso articolo.")
    try:
        await binding.quote(
            db, organization_id=organization_id, customer_user_id=customer_user_id,
            lines=[(variant_id, wanted)],
        )
    except binding.errors as exc:
        raise CartValidationError(str(exc)) from exc
    if item is None:
        item = CartItem(cart_id=cart.id, quantity=wanted, **{binding.column: variant_id})
        db.add(item)
    else:
        item.quantity = wanted
    await db.commit()
    return cart


async def set_quantity(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    customer_user_id: uuid.UUID,
    shop: str,
    item_id: uuid.UUID,
    quantity: int,
) -> None:
    """Set a line's quantity; zero removes the line."""
    binding = _binding(shop)
    item, _cart = await _owned_item(db, customer_user_id=customer_user_id, shop=shop, item_id=item_id)
    if quantity <= 0:
        await db.delete(item)
        await db.commit()
        return
    if quantity > MAX_ITEM_QUANTITY:
        raise CartValidationError(f"Al massimo {MAX_ITEM_QUANTITY} pezzi dello stesso articolo.")
    try:
        await binding.quote(
            db, organization_id=organization_id, customer_user_id=customer_user_id,
            lines=[(_variant_id(item, binding), quantity)],
        )
    except binding.errors as exc:
        raise CartValidationError(str(exc)) from exc
    item.quantity = quantity
    await db.commit()


async def remove_item(
    db: AsyncSession, *, customer_user_id: uuid.UUID, shop: str, item_id: uuid.UUID
) -> None:
    item, _ = await _owned_item(db, customer_user_id=customer_user_id, shop=shop, item_id=item_id)
    await db.delete(item)
    await db.commit()


async def clear(db: AsyncSession, *, customer_user_id: uuid.UUID, shop: str) -> None:
    found = await db.execute(select(Cart).where(Cart.customer_user_id == customer_user_id, Cart.shop == shop))
    cart = found.scalar_one_or_none()
    if cart is None:
        return
    for item in await _items(db, cart):
        await db.delete(item)
    await db.commit()


async def _owned_item(
    db: AsyncSession, *, customer_user_id: uuid.UUID, shop: str, item_id: uuid.UUID
) -> tuple[CartItem, Cart]:
    """Fetch a line only if it belongs to the caller's cart for `shop`."""
    item = await db.get(CartItem, item_id)
    cart = await db.get(Cart, item.cart_id) if item is not None else None
    if item is None or cart is None or cart.customer_user_id != customer_user_id or cart.shop != shop:
        raise CartNotFoundError("Articolo non presente nel carrello.")
    return item, cart


# --- Pricing --------------------------------------------------------------------------------------


async def shop_section(
    db: AsyncSession, *, organization_id: uuid.UUID, customer_user_id: uuid.UUID, shop: str
) -> dict | None:
    """One shop's cart at current prices, or `None` if empty.

    If any line has become unsellable the combined quote fails; we then
    quote line by line so the customer is told which line to fix instead of
    facing a cart that will not open.
    """
    binding = _binding(shop)
    found = await db.execute(select(Cart).where(Cart.customer_user_id == customer_user_id, Cart.shop == shop))
    cart = found.scalar_one_or_none()
    if cart is None:
        return None
    items = await _items(db, cart)
    if not items:
        return None

    lines = [(_variant_id(item, binding), item.quantity) for item in items]
    by_variant = {_variant_id(item, binding): item for item in items}
    try:
        quote = await binding.quote(
            db, organization_id=organization_id, customer_user_id=customer_user_id, lines=lines
        )
    except binding.errors:
        return await _section_with_problems(
            db, binding=binding, organization_id=organization_id, customer_user_id=customer_user_id,
            cart=cart, items=items,
        )
    for entry in quote["items"]:
        entry["cart_item_id"] = by_variant[entry["variant_id"]].id
        entry["available"] = True
        entry["unavailable_reason"] = None
    return {"cart_id": cart.id, "shop": shop, "purchasable": True, "problems": [], **quote}


async def _section_with_problems(
    db: AsyncSession,
    *,
    binding: ShopBinding,
    organization_id: uuid.UUID,
    customer_user_id: uuid.UUID,
    cart: Cart,
    items: list[CartItem],
) -> dict:
    """Quote each line separately, flagging the ones no longer purchasable."""
    entries: list[dict] = []
    problems: list[str] = []
    good: list[tuple[uuid.UUID, int]] = []
    for item in items:
        variant_id = _variant_id(item, binding)
        try:
            one = await binding.quote(
                db, organization_id=organization_id, customer_user_id=customer_user_id,
                lines=[(variant_id, item.quantity)],
            )
        except binding.errors as exc:
            entries.append(
                {
                    "cart_item_id": item.id,
                    "variant_id": variant_id,
                    "product_name": "Articolo non più disponibile",
                    "variant_label": None,
                    "image_url": None,
                    "quantity": item.quantity,
                    "unit_price_cents": 0,
                    "line_total_cents": 0,
                    "credit_discount_percentage": 0,
                    "available": False,
                    "unavailable_reason": str(exc),
                }
            )
            problems.append(str(exc))
            continue
        entry = one["items"][0]
        entry["cart_item_id"] = item.id
        entry["available"] = True
        entry["unavailable_reason"] = None
        entries.append(entry)
        good.append((variant_id, item.quantity))

    totals: dict[str, Any] = {}
    if good:
        totals = await binding.quote(
            db, organization_id=organization_id, customer_user_id=customer_user_id, lines=good
        )
        totals.pop("items", None)
    return {
        "cart_id": cart.id,
        "shop": cart.shop,
        # Blocked until the customer fixes the broken lines: silently
        # paying for the rest would deliver a different order than composed.
        "purchasable": False,
        "problems": problems,
        "items": entries,
        **totals,
    }


async def summary(db: AsyncSession, *, organization_id: uuid.UUID, customer_user_id: uuid.UUID) -> dict:
    """All sections plus the totals shown on the header cart icon."""
    sections = []
    for shop in CART_SHOPS:
        if shop not in SHOPS:
            continue
        section = await shop_section(
            db, organization_id=organization_id, customer_user_id=customer_user_id, shop=shop
        )
        if section is not None:
            sections.append(section)
    return {
        "sections": sections,
        "item_count": sum(sum(i["quantity"] for i in s["items"]) for s in sections),
        "total_cents": sum(s.get("amount_cents", 0) for s in sections),
    }


async def checkout_lines(
    db: AsyncSession, *, customer_user_id: uuid.UUID, shop: str
) -> tuple[Cart, list[tuple[uuid.UUID, int]]]:
    """Lines to hand to the shop's order creation. No pricing here: the
    shop reprices and freezes the result on the order."""
    binding = _binding(shop)
    found = await db.execute(select(Cart).where(Cart.customer_user_id == customer_user_id, Cart.shop == shop))
    cart = found.scalar_one_or_none()
    items = await _items(db, cart) if cart is not None else []
    if cart is None or not items:
        raise CartValidationError("Il carrello è vuoto.")
    return cart, [(_variant_id(item, binding), item.quantity) for item in items]
