"""API for the Sosnet grocery shop («Fai la Spesa con Sosnet»).

Uses the same permissions as the other imported-product shops:
`imported_products.manage` for the catalog, `wallet.manage` for orders.
Customer routes under `/sosnet-market/orders/mine` mirror the AliExpress
ones, so "I miei Ordini" treats all four shops uniformly.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.foundation.config import get_settings
from app.foundation.db import get_db
from app.foundation.deps import CurrentUser, get_current_user, require_permission
from app.foundation.rate_limit import rate_limit
from app.modules.carts import service as carts_service
from app.modules.sosnet_market import service
from app.modules.sosnet_market.schemas import (
    CheckoutSessionRead,
    SosnetMarketCartCreditOtpRequest,
    SosnetMarketCartOrderRequest,
    SosnetMarketOrderCancelRequest,
    SosnetMarketOrderCreditOtpRequest,
    SosnetMarketOrderPaymentMethodUpdate,
    SosnetMarketOrderSelfCreateRequest,
    SosnetMarketSettingsRead,
    SosnetMarketSettingsUpdate,
    SosnetMarketShipRequest,
    ProducerUpdate,
    ProducerWrite,
    ProductUpdate,
    ProductWrite,
    VariantUpdate,
    VariantWrite,
)
from app.modules.payments import service as payments_service

router = APIRouter(prefix="/sosnet-market", tags=["sosnet-market"])

CATALOG = "imported_products.manage"
ORDERS = "wallet.manage"
ERRORS = service.ERRORS


def _http(exc: Exception) -> HTTPException:
    if isinstance(exc, service.SosnetMarketNotFoundError):
        return HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    return HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


# --- Admin: settings --------------------------------------------------------------------------


@router.get("/settings", response_model=SosnetMarketSettingsRead)
async def get_sosnet_market_settings(
    current_user: CurrentUser = Depends(require_permission(CATALOG)), db: AsyncSession = Depends(get_db)
) -> SosnetMarketSettingsRead:
    row = await service.get_settings_row(db, organization_id=current_user.organization_id)
    return SosnetMarketSettingsRead(**service.settings_read_dict(row))


@router.patch("/settings", response_model=SosnetMarketSettingsRead)
async def update_sosnet_market_settings(
    payload: SosnetMarketSettingsUpdate,
    current_user: CurrentUser = Depends(require_permission(CATALOG)),
    db: AsyncSession = Depends(get_db),
) -> SosnetMarketSettingsRead:
    row = await service.get_settings_row(db, organization_id=current_user.organization_id)
    try:
        row = await service.update_settings(
            db, row=row, actor_user_id=current_user.user_id,
            updates=payload.model_dump(exclude_unset=True),
        )
    except ERRORS as exc:
        raise _http(exc) from exc
    return SosnetMarketSettingsRead(**service.settings_read_dict(row))


# --- Admin: producing companies -------------------------------------------------------------------


@router.get("/producers")
async def list_sosnet_market_producers(
    current_user: CurrentUser = Depends(require_permission(CATALOG)), db: AsyncSession = Depends(get_db)
) -> list[dict]:
    rows = await service.list_producers(db, organization_id=current_user.organization_id)
    return [service.producer_read_dict(p) for p in rows]


@router.post("/producers", status_code=status.HTTP_201_CREATED)
async def create_sosnet_market_producer(
    payload: ProducerWrite,
    current_user: CurrentUser = Depends(require_permission(CATALOG)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        producer = await service.create_producer(
            db, organization_id=current_user.organization_id,
            actor_user_id=current_user.user_id, payload=payload.model_dump(),
        )
    except ERRORS as exc:
        raise _http(exc) from exc
    return service.producer_read_dict(producer)


@router.patch("/producers/{producer_id}")
async def update_sosnet_market_producer(
    producer_id: uuid.UUID,
    payload: ProducerUpdate,
    current_user: CurrentUser = Depends(require_permission(CATALOG)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        producer = await service.update_producer(
            db, organization_id=current_user.organization_id, producer_id=producer_id,
            payload=payload.model_dump(exclude_unset=True),
        )
    except ERRORS as exc:
        raise _http(exc) from exc
    return service.producer_read_dict(producer)


# --- Admin: catalog ------------------------------------------------------------------------------


@router.get("/products")
async def list_sosnet_market_products(
    current_user: CurrentUser = Depends(require_permission(CATALOG)), db: AsyncSession = Depends(get_db)
) -> list[dict]:
    rows = await service.list_products(db, organization_id=current_user.organization_id)
    return [await service.product_read_dict(db, p, admin=True) for p in rows]


@router.post("/products", status_code=status.HTTP_201_CREATED)
async def create_sosnet_market_product(
    payload: ProductWrite,
    current_user: CurrentUser = Depends(require_permission(CATALOG)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        product = await service.create_product(
            db, organization_id=current_user.organization_id,
            actor_user_id=current_user.user_id, payload=payload.model_dump(),
        )
    except ERRORS as exc:
        raise _http(exc) from exc
    except Exception as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return await service.product_read_dict(db, product, admin=True)


@router.patch("/products/{product_id}")
async def update_sosnet_market_product(
    product_id: uuid.UUID,
    payload: ProductUpdate,
    current_user: CurrentUser = Depends(require_permission(CATALOG)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        product = await service.update_product(
            db, organization_id=current_user.organization_id, product_id=product_id,
            payload=payload.model_dump(exclude_unset=True),
        )
    except ERRORS as exc:
        raise _http(exc) from exc
    except Exception as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return await service.product_read_dict(db, product, admin=True)


@router.post("/products/{product_id}/variants", status_code=status.HTTP_201_CREATED)
async def add_sosnet_market_variant(
    product_id: uuid.UUID,
    payload: VariantWrite,
    current_user: CurrentUser = Depends(require_permission(CATALOG)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        product = await service.add_variant(
            db, organization_id=current_user.organization_id, product_id=product_id,
            payload=payload.model_dump(),
        )
    except ERRORS as exc:
        raise _http(exc) from exc
    return await service.product_read_dict(db, product, admin=True)


@router.patch("/variants/{variant_id}")
async def update_sosnet_market_variant(
    variant_id: uuid.UUID,
    payload: VariantUpdate,
    current_user: CurrentUser = Depends(require_permission(CATALOG)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        variant = await service.update_variant(
            db, organization_id=current_user.organization_id, variant_id=variant_id,
            payload=payload.model_dump(exclude_unset=True),
        )
    except ERRORS as exc:
        raise _http(exc) from exc
    return {"id": variant.id, "label": variant.label, "price_cents": variant.price_cents,
            "inventory": variant.inventory, "active": variant.active}


# --- Customer: storefront -----------------------------------------------------------------------------


@router.get("/products/mine")
async def list_my_sosnet_market_products(
    current_user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[dict]:
    """Customer product grid; empty while the shop is disabled, so the tab
    disappears from the Shop automatically."""
    return await service.customer_products(db, organization_id=current_user.organization_id)


# --- Customer: checkout ----------------------------------------------------------------------------


@router.get("/orders/quote/mine")
async def get_my_sosnet_market_quote(
    variant_id: uuid.UUID,
    quantity: int = 1,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        return await service.get_quote(
            db, organization_id=current_user.organization_id, customer_user_id=current_user.user_id,
            variant_id=variant_id, quantity=quantity,
        )
    except ERRORS as exc:
        raise _http(exc) from exc


async def _my_cart_lines(db: AsyncSession, current_user: CurrentUser) -> list[tuple[uuid.UUID, int]]:
    try:
        _, lines = await carts_service.checkout_lines(
            db, customer_user_id=current_user.user_id, shop=service.SHOP
        )
    except (carts_service.CartValidationError, carts_service.CartNotFoundError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return lines


@router.get("/orders/quote/mine/cart")
async def get_my_sosnet_market_cart_quote(
    current_user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> dict:
    lines = await _my_cart_lines(db, current_user)
    try:
        return await service.get_quote(
            db, organization_id=current_user.organization_id, customer_user_id=current_user.user_id, lines=lines,
        )
    except ERRORS as exc:
        raise _http(exc) from exc


async def _request_otp(db: AsyncSession, current_user: CurrentUser, *, quote: dict, credit_cents: int) -> dict:
    from app.modules.auth import service as auth_service
    from app.modules.users.models import User

    user = await db.get(User, current_user.user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Utente non trovato.")
    articoli = len(quote["items"])
    cosa = quote["product_name"] if articoli == 1 else f"{articoli} articoli"
    await auth_service.request_otp(
        db, user=user, purpose=auth_service.WALLET_CREDIT_SPEND_OTP_PURPOSE,
        context_line=(
            f"Stai per acquistare <strong>{cosa}</strong> "
            f"(ordine da {quote['amount_cents'] / 100:.2f} &euro;) e utilizzare "
            f"<strong>{credit_cents / 100:.2f} SosnetCash</strong> dal tuo wallet "
            "per pagarne una parte. Usa questo codice per confermare l'operazione."
        ),
    )
    return {"ok": True}


@router.post(
    "/orders/mine/request-credit-otp",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(rate_limit("sosnet-market-credit-otp", max_requests=5, window_seconds=300))],
)
async def request_my_sosnet_market_credit_otp(
    payload: SosnetMarketOrderCreditOtpRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        quote = await service.get_quote(
            db, organization_id=current_user.organization_id, customer_user_id=current_user.user_id,
            variant_id=payload.variant_id, quantity=payload.quantity,
        )
    except ERRORS as exc:
        raise _http(exc) from exc
    return await _request_otp(db, current_user, quote=quote, credit_cents=payload.credit_applied_cents)


@router.post(
    "/orders/mine/cart/request-credit-otp",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(rate_limit("sosnet-market-cart-credit-otp", max_requests=5, window_seconds=300))],
)
async def request_my_sosnet_market_cart_credit_otp(
    payload: SosnetMarketCartCreditOtpRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    lines = await _my_cart_lines(db, current_user)
    try:
        quote = await service.get_quote(
            db, organization_id=current_user.organization_id, customer_user_id=current_user.user_id, lines=lines,
        )
    except ERRORS as exc:
        raise _http(exc) from exc
    return await _request_otp(db, current_user, quote=quote, credit_cents=payload.credit_applied_cents)


@router.post("/orders/mine", status_code=status.HTTP_201_CREATED)
async def create_my_sosnet_market_order(
    payload: SosnetMarketOrderSelfCreateRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        order = await service.create_order(
            db, organization_id=current_user.organization_id, customer_user_id=current_user.user_id,
            variant_id=payload.variant_id, quantity=payload.quantity, address=payload.address.model_dump(),
            credit_applied_cents=payload.credit_applied_cents, payment_method=payload.payment_method,
            actor_user_id=current_user.user_id, otp_code=payload.otp_code, note=payload.note,
        )
    except ERRORS as exc:
        raise _http(exc) from exc
    return await service.order_read_dict(db, order, admin=False)


@router.post("/orders/mine/cart", status_code=status.HTTP_201_CREATED)
async def create_my_sosnet_market_order_from_cart(
    payload: SosnetMarketCartOrderRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Turn the cart into an order; the cart is emptied only then."""
    lines = await _my_cart_lines(db, current_user)
    try:
        order = await service.create_order(
            db, organization_id=current_user.organization_id, customer_user_id=current_user.user_id,
            lines=lines, address=payload.address.model_dump(),
            credit_applied_cents=payload.credit_applied_cents, payment_method=payload.payment_method,
            actor_user_id=current_user.user_id, otp_code=payload.otp_code, note=payload.note,
        )
    except ERRORS as exc:
        raise _http(exc) from exc
    await carts_service.clear(db, customer_user_id=current_user.user_id, shop=service.SHOP)
    return await service.order_read_dict(db, order, admin=False)


@router.get("/orders/mine")
async def list_my_sosnet_market_orders(
    current_user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[dict]:
    orders = await service.list_orders(
        db, organization_id=current_user.organization_id, customer_user_id=current_user.user_id
    )
    return [await service.order_read_dict(db, o, admin=False) for o in orders]


async def _owned(db: AsyncSession, current_user: CurrentUser, order_id: uuid.UUID):
    order = await service.get_owned(
        db, organization_id=current_user.organization_id, customer_user_id=current_user.user_id, order_id=order_id
    )
    if order is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ordine non trovato.")
    return order


@router.patch("/orders/mine/{order_id}/payment-method")
async def change_my_sosnet_market_payment_method(
    order_id: uuid.UUID,
    payload: SosnetMarketOrderPaymentMethodUpdate,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    order = await _owned(db, current_user, order_id)
    try:
        order = await service.change_payment_method(
            db, organization_id=current_user.organization_id, order=order,
            new_payment_method=payload.payment_method,
        )
    except ERRORS as exc:
        raise _http(exc) from exc
    return await service.order_read_dict(db, order, admin=False)


@router.post("/orders/mine/{order_id}/checkout-session", response_model=CheckoutSessionRead)
async def create_my_sosnet_market_checkout_session(
    order_id: uuid.UUID,
    success_url: str | None = None,
    cancel_url: str | None = None,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CheckoutSessionRead:
    order = await _owned(db, current_user, order_id)
    base = get_settings().public_app_base_url
    try:
        url = await payments_service.create_checkout_session_for_sosnet_market_order(
            db, organization_id=current_user.organization_id, order=order,
            success_url=success_url or f"{base}/customer?tab=orders",
            cancel_url=cancel_url or f"{base}/customer?tab=orders",
        )
    except payments_service.StripeNotConfiguredError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return CheckoutSessionRead(checkout_url=url)


# --- Admin: orders --------------------------------------------------------------------------------


@router.get("/orders")
async def list_sosnet_market_orders(
    current_user: CurrentUser = Depends(require_permission(ORDERS)), db: AsyncSession = Depends(get_db)
) -> list[dict]:
    orders = await service.list_orders(db, organization_id=current_user.organization_id)
    return [await service.order_read_dict(db, o, admin=True) for o in orders]


@router.post("/orders/{order_id}/confirm-payment")
async def confirm_sosnet_market_payment(
    order_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission(ORDERS)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        order = await service.confirm_payment(
            db, organization_id=current_user.organization_id, order_id=order_id,
            actor_user_id=current_user.user_id,
        )
    except ERRORS as exc:
        raise _http(exc) from exc
    return await service.order_read_dict(db, order, admin=True)


@router.post("/orders/{order_id}/forward")
async def forward_sosnet_market_order(
    order_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission(ORDERS)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Email each producing company its order lines and the delivery address.

    Repeatable: unlike AliExpress, resending creates no second purchase, only
    another email, useful when the first one is lost."""
    try:
        order = await service.forward_order(
            db, organization_id=current_user.organization_id, order_id=order_id,
            actor_user_id=current_user.user_id,
        )
    except ERRORS as exc:
        raise _http(exc) from exc
    return await service.order_read_dict(db, order, admin=True)


@router.post("/orders/{order_id}/ship")
async def ship_sosnet_market_order(
    order_id: uuid.UUID,
    payload: SosnetMarketShipRequest,
    current_user: CurrentUser = Depends(require_permission(ORDERS)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """No supplier notifies shipment here: the administrator marks it, which
    triggers the tracking email to the customer."""
    try:
        order = await service.mark_shipped(
            db, organization_id=current_user.organization_id, order_id=order_id,
            actor_user_id=current_user.user_id, tracking_number=payload.tracking_number,
            tracking_url=payload.tracking_url, tracking_company=payload.tracking_company,
        )
    except ERRORS as exc:
        raise _http(exc) from exc
    return await service.order_read_dict(db, order, admin=True)


@router.post("/orders/{order_id}/delivered")
async def deliver_sosnet_market_order(
    order_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission(ORDERS)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        order = await service.mark_delivered(
            db, organization_id=current_user.organization_id, order_id=order_id,
            actor_user_id=current_user.user_id,
        )
    except ERRORS as exc:
        raise _http(exc) from exc
    return await service.order_read_dict(db, order, admin=True)


@router.post("/orders/{order_id}/cancel")
async def cancel_sosnet_market_order(
    order_id: uuid.UUID,
    payload: SosnetMarketOrderCancelRequest,
    current_user: CurrentUser = Depends(require_permission(ORDERS)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        order = await service.cancel_order(
            db, organization_id=current_user.organization_id, order_id=order_id,
            reason=payload.reason, actor_user_id=current_user.user_id,
        )
    except ERRORS as exc:
        raise _http(exc) from exc
    return await service.order_read_dict(db, order, admin=True)
