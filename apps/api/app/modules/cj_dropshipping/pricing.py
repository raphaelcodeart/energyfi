"""CJ cost in USD to customer price in EUR.

    price = cost_usd x rate x (1 + markup%) + fixed markup [+ shipping if included]
            rounded UP to x,90 / x,99 (or to the cent)

Rounding only goes up so it can never push a sale below the configured
margin. Integer cents and Decimal throughout, never float, so pricing is
deterministic.
"""

from decimal import ROUND_CEILING, Decimal

from app.modules.cj_dropshipping.models import CjSettings
from app.modules.marketplaces import rules


def usd_to_eur_cents(amount_usd: Decimal | float | str, rate: Decimal) -> int:
    """USD to EUR cents, rounded up to the cent."""
    cents = Decimal(str(amount_usd)) * Decimal(rate) * 100
    return int(cents.to_integral_value(rounding=ROUND_CEILING))


def _round_up(cents: int, rounding: str) -> int:
    if rounding not in ("90", "99"):
        return cents
    target = int(rounding)
    euros, rest = divmod(cents, 100)
    return euros * 100 + target if rest <= target else (euros + 1) * 100 + target


def sale_price_cents(
    *,
    cost_usd: Decimal | float | str,
    settings: CjSettings,
    markup_percentage: int | None = None,
    shipping_estimate_usd: Decimal | float | str | None = None,
) -> int:
    """Unit price. `markup_percentage` is a per-product override; the shipping
    estimate is included only if the organization sells shipping-included."""
    markup = settings.markup_percentage if markup_percentage is None else markup_percentage
    rate = Decimal(settings.usd_eur_rate)
    cost_cents = Decimal(str(cost_usd)) * rate * 100
    cents = cost_cents * (Decimal(100 + markup) / 100) + Decimal(settings.markup_fixed_cents or 0)
    if settings.shipping_mode == "INCLUDED" and shipping_estimate_usd:
        cents += Decimal(str(shipping_estimate_usd)) * rate * 100
    return _round_up(int(cents.to_integral_value(rounding=ROUND_CEILING)), settings.price_rounding)


def shipping_price_cents(*, shipping_usd: Decimal | float | str, settings: CjSettings) -> int:
    """Shipping charged at checkout: the converted CJ cost, or zero when
    shipping is already included in the price."""
    if settings.shipping_mode == "INCLUDED":
        return 0
    return usd_to_eur_cents(shipping_usd, Decimal(settings.usd_eur_rate))


def margin_cents(*, price_cents: int, cost_usd: Decimal | float | str, rate: Decimal) -> int:
    return price_cents - usd_to_eur_cents(cost_usd, rate)


# All Marketplaces share one bank-transfer discount.
bank_transfer_discount_cents = rules.bank_transfer_discount_cents
