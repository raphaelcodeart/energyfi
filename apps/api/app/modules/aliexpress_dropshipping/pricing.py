"""Converts an AliExpress price into the EUR price the customer pays.

    base  = the SKU's dropshipping price (our cost) or its list price, per
            AliexpressSettings.price_basis; falls back to the list price
            when no dropshipping price is available
    price = base x rate x (1 + markup%) + fixed markup,
            rounded UP to x,90 / x,99 (or to the cent)

Shipping is priced separately from the real AliExpress quote, with a
configurable minimum (see charged_shipping_cents()).

Rounding only goes up; integer cents and Decimal, never float.
"""

from decimal import ROUND_CEILING, Decimal

from app.modules.aliexpress_dropshipping.models import AliexpressSettings


def _round_up(cents: int, rounding: str) -> int:
    if rounding not in ("90", "99"):
        return cents
    target = int(rounding)
    euros, rest = divmod(cents, 100)
    return euros * 100 + target if rest <= target else (euros + 1) * 100 + target


def base_amount(*, cost: Decimal | None, price: Decimal, settings: AliexpressSettings) -> Decimal:
    if settings.price_basis == "COST" and cost is not None and Decimal(cost) > 0:
        return Decimal(cost)
    return Decimal(price)


def to_eur_cents(amount: Decimal | float | str, rate: Decimal) -> int:
    cents = Decimal(str(amount)) * Decimal(rate) * 100
    return int(cents.to_integral_value(rounding=ROUND_CEILING))


def sale_price_cents(
    *,
    cost: Decimal | None,
    price: Decimal,
    settings: AliexpressSettings,
    markup_percentage: int | None = None,
) -> int:
    """Unit price; `markup_percentage` overrides the organization default."""
    markup = settings.markup_percentage if markup_percentage is None else markup_percentage
    rate = Decimal(settings.currency_rate)
    base = base_amount(cost=cost, price=price, settings=settings)
    cents = base * rate * 100 * (Decimal(100 + markup) / 100) + Decimal(settings.markup_fixed_cents or 0)
    if settings.shipping_mode == "INCLUDED":
        # Quantity and destination are unknown here, so the minimum is the
        # only available estimate; checkout then charges no shipping.
        cents += Decimal(settings.shipping_minimum_cents or 0)
    return _round_up(int(cents.to_integral_value(rounding=ROUND_CEILING)), settings.price_rounding)


def charged_shipping_cents(*, supplier_cents: int, settings: AliexpressSettings) -> int:
    """Shipping charged on an order: max(real AliExpress cost, minimum).

    `supplier_cents` is the real cost of the **whole order**, summed by the
    caller, so the minimum applies once per order, never per item (three
    items at 1,20 cost 3,60 and are charged 5,90, not 17,70).

    With shipping INCLUDED nothing is charged; the minimum is already in the
    list price (see sale_price_cents).

    The minimum is not a fallback: a caller that cannot obtain the real cost
    must stop rather than pass zero, which would mean "free shipping".
    """
    if settings.shipping_mode == "INCLUDED":
        return 0
    return max(int(supplier_cents), settings.shipping_minimum_cents or 0)
