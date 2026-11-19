"""Shop Sosnet Partner (CJ Dropshipping) API.

Admin screens need imported_products.manage, as for AliExpress; order
handling needs wallet.manage, as for every shop. Customer routes under
/cj/orders/mine mirror /imported-products/orders/mine so the unified
"I miei ordini" screen treats both shops alike.
"""

import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.foundation.db import get_db
from app.foundation.deps import CurrentUser, get_current_user, require_permission
from app.foundation.rate_limit import rate_limit
from app.modules.carts import service as carts_service
from app.modules.cj_dropshipping import client as cj
from app.modules.cj_dropshipping import service
from app.modules.cj_dropshipping.schemas import (
    CheckoutSessionRead,
    CjCartCreditOtpRequest,
    CjCartOrderRequest,
    CjImportRequest,
    CjOrderCancelRequest,
    CjOrderCreditOtpRequest,
    CjOrderPaymentMethodUpdate,
    CjOrderSelfCreateRequest,
    CjProductUpdate,
    CjSettingsRead,
    CjSettingsUpdate,
    CjVariantUpdate,
    PaymentProofUrlRead,
)
from app.modules.payments import service as payments_service
from app.modules.shop_categories import service as shop_categories_service
from app.modules.wallets import service as wallets_service

router = APIRouter(prefix="/cj", tags=["cj-dropshipping"])

CATALOG = "imported_products.manage"
ORDERS = "wallet.manage"


def _http(exc: Exception) -> HTTPException:
    if isinstance(exc, service.CjNotFoundError):
        return HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    return HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


ERRORS = (service.CjError, cj.CjApiError, wallets_service.InsufficientBalanceError)


# --- Admin: settings ---------------------------------------------------------------------------


@router.get("/settings", response_model=CjSettingsRead)
async def get_cj_settings(
    current_user: CurrentUser = Depends(require_permission(CATALOG)), db: AsyncSession = Depends(get_db)
) -> CjSettingsRead:
    row = await service.get_settings_row(db, organization_id=current_user.organization_id)
    return CjSettingsRead(**service.settings_read_dict(row))


@router.patch("/settings", response_model=CjSettingsRead)
async def update_cj_settings(
    payload: CjSettingsUpdate,
    current_user: CurrentUser = Depends(require_permission(CATALOG)),
    db: AsyncSession = Depends(get_db),
) -> CjSettingsRead:
    row = await service.get_settings_row(db, organization_id=current_user.organization_id)
    updates = payload.model_dump(exclude_unset=True)
    for key in [k for k, v in updates.items() if v is None and k != "api_key"]:
        updates.pop(key)
    if "usd_eur_rate" in updates:
        updates["usd_eur_rate"] = Decimal(str(updates["usd_eur_rate"]))
    try:
        row = await service.update_settings(db, row=row, updates=updates, actor_user_id=current_user.user_id)
    except ERRORS as exc:
        raise _http(exc) from exc
    return CjSettingsRead(**service.settings_read_dict(row))


@router.post("/settings/test", response_model=CjSettingsRead)
async def test_cj_connection(
    current_user: CurrentUser = Depends(require_permission(CATALOG)), db: AsyncSession = Depends(get_db)
) -> CjSettingsRead:
    """Log in with the saved key and read the CJ balance."""
    row = await service.get_settings_row(db, organization_id=current_user.organization_id)
    try:
        return CjSettingsRead(**await service.test_connection(db, row=row))
    except ERRORS as exc:
        raise _http(exc) from exc


# --- Admin: CJ catalog ------------------------------------------------------------------------------


@router.get("/catalog/categories")
async def list_cj_categories(
    current_user: CurrentUser = Depends(require_permission(CATALOG)), db: AsyncSession = Depends(get_db)
) -> list[dict]:
    row = await service.get_settings_row(db, organization_id=current_user.organization_id)
    try:
        return await service.categories(db, row=row)
    except ERRORS as exc:
        raise _http(exc) from exc


@router.get("/catalog/search")
async def search_cj_catalog(
    keyword: str | None = None,
    page: int = 1,
    category_id: str | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    free_shipping: bool = False,
    current_user: CurrentUser = Depends(require_permission(CATALOG)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    row = await service.get_settings_row(db, organization_id=current_user.organization_id)
    try:
        return await service.search_catalog(
            db, row=row, keyword=(keyword or "").strip() or None, page=max(1, min(page, 1000)),
            category_id=category_id or None, min_price=min_price, max_price=max_price, free_shipping=free_shipping,
        )
    except ERRORS as exc:
        raise _http(exc) from exc


@router.get("/catalog/products/{pid}")
async def preview_cj_product(
    pid: str, current_user: CurrentUser = Depends(require_permission(CATALOG)), db: AsyncSession = Depends(get_db)
) -> dict:
    row = await service.get_settings_row(db, organization_id=current_user.organization_id)
    try:
        return await service.preview_product(db, row=row, pid=pid)
    except ERRORS as exc:
        raise _http(exc) from exc


# --- Admin: imported products ---------------------------------------------------------------------


@router.get("/products")
async def list_cj_products(
    current_user: CurrentUser = Depends(require_permission(CATALOG)), db: AsyncSession = Depends(get_db)
) -> list[dict]:
    products = await service.list_products(db, organization_id=current_user.organization_id, active_only=False)
    # Load categories for the whole page in one query; N+1 here would slow
    # every Shop page load.
    categories = await shop_categories_service.category_ids_by_product(
        db, organization_id=current_user.organization_id, shop=service.SHOP,
        product_ids=[p.id for p in products],
    )
    return [
        await service.product_admin_dict(db, p, category_ids=categories.get(p.id, []))
        for p in products
    ]


@router.post("/products", status_code=status.HTTP_201_CREATED)
async def import_cj_product(
    payload: CjImportRequest,
    current_user: CurrentUser = Depends(require_permission(CATALOG)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    row = await service.get_settings_row(db, organization_id=current_user.organization_id)
    try:
        product = await service.import_product(
            db, row=row, actor_user_id=current_user.user_id, pid=payload.pid, name=payload.name,
            description=payload.description, credit_discount_percentage=payload.credit_discount_percentage,
            markup_percentage=payload.markup_percentage, vids=payload.vids, activate=payload.activate,
        )
    except ERRORS as exc:
        raise _http(exc) from exc
    return await service.product_admin_dict(db, product)


@router.patch("/products/{product_id}")
async def update_cj_product(
    product_id: uuid.UUID,
    payload: CjProductUpdate,
    current_user: CurrentUser = Depends(require_permission(CATALOG)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    row = await service.get_settings_row(db, organization_id=current_user.organization_id)
    updates = payload.model_dump(exclude_unset=True)
    for key in [k for k, v in updates.items() if v is None and k not in ("markup_percentage", "image_url")]:
        updates.pop(key)
    try:
        product = await service.get_product(db, organization_id=current_user.organization_id, product_id=product_id)
        product = await service.update_product(
            db, row=row, product=product, updates=updates, actor_user_id=current_user.user_id
        )
    except ERRORS as exc:
        raise _http(exc) from exc
    return await service.product_admin_dict(db, product)


@router.post("/products/{product_id}/sync")
async def sync_cj_product(
    product_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission(CATALOG)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    row = await service.get_settings_row(db, organization_id=current_user.organization_id)
    try:
        product = await service.get_product(db, organization_id=current_user.organization_id, product_id=product_id)
        product = await service.sync_product(db, row=row, product=product)
    except ERRORS as exc:
        raise _http(exc) from exc
    return await service.product_admin_dict(db, product)


@router.patch("/variants/{variant_id}")
async def update_cj_variant(
    variant_id: uuid.UUID,
    payload: CjVariantUpdate,
    current_user: CurrentUser = Depends(require_permission(CATALOG)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    updates = payload.model_dump(exclude_unset=True)
    for key in [k for k, v in updates.items() if v is None and k != "price_override_cents"]:
        updates.pop(key)
    try:
        variant = await service.update_variant(
            db, organization_id=current_user.organization_id, variant_id=variant_id, updates=updates
        )
        product = await service.get_product(
            db, organization_id=current_user.organization_id, product_id=variant.product_id
        )
    except ERRORS as exc:
        raise _http(exc) from exc
    return await service.product_admin_dict(db, product)


# --- Customer: storefront and checkout ----------------------------------------------------------------------


@router.get("/products/active")
async def list_cj_products_active(
    current_user: CurrentUser = Depends(require_permission("products.read")), db: AsyncSession = Depends(get_db)
) -> list[dict]:
    """The "Shop Sosnet Partner" tab; empty while the shop is disabled."""
    row = await service.get_settings_row(db, organization_id=current_user.organization_id)
    if not row.enabled:
        return []
    products = await service.list_products(db, organization_id=current_user.organization_id, active_only=True)
    categories = await shop_categories_service.category_ids_by_product(
        db, organization_id=current_user.organization_id, shop=service.SHOP,
        product_ids=[p.id for p in products],
    )
    out = []
    for product in products:
        card = await service.product_customer_dict(
            db, product, settings=row, category_ids=categories.get(product.id, [])
        )
        if card is not None:
            out.append(card)
    return out


@router.get("/orders/quote/mine")
async def get_my_cj_quote(
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


@router.post(
    "/orders/mine/request-credit-otp",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(rate_limit("cj-order-credit-otp", max_requests=5, window_seconds=300))],
)
async def request_my_cj_credit_otp(
    payload: CjOrderCreditOtpRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    from app.modules.auth import service as auth_service
    from app.modules.users.models import User

    user = await db.get(User, current_user.user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Utente non trovato.")
    try:
        quote = await service.get_quote(
            db, organization_id=current_user.organization_id, customer_user_id=current_user.user_id,
            variant_id=payload.variant_id, quantity=payload.quantity,
        )
    except ERRORS as exc:
        raise _http(exc) from exc
    context_line = (
        f"Stai per acquistare <strong>{quote['product_name']}</strong> "
        f"(ordine da {quote['amount_cents'] / 100:.2f} &euro;) e utilizzare "
        f"<strong>{payload.credit_applied_cents / 100:.2f} SosnetCash</strong> dal tuo wallet "
        "per pagarne una parte. Usa questo codice per confermare l'operazione."
    )
    await auth_service.request_otp(
        db, user=user, purpose=auth_service.WALLET_CREDIT_SPEND_OTP_PURPOSE, context_line=context_line
    )
    return {"ok": True}


@router.post("/orders/mine", status_code=status.HTTP_201_CREATED)
async def create_my_cj_order(
    payload: CjOrderSelfCreateRequest,
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


# --- Customer: cart checkout ---------------------------------------------------


async def _my_cart_lines(db: AsyncSession, current_user: CurrentUser) -> list[tuple[uuid.UUID, int]]:
    try:
        _, lines = await carts_service.checkout_lines(
            db, customer_user_id=current_user.user_id, shop="cj"
        )
    except (carts_service.CartValidationError, carts_service.CartNotFoundError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return lines


@router.get("/orders/quote/mine/cart")
async def get_my_cj_cart_quote(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    lines = await _my_cart_lines(db, current_user)
    try:
        return await service.get_quote(
            db, organization_id=current_user.organization_id, customer_user_id=current_user.user_id, lines=lines,
        )
    except ERRORS as exc:
        raise _http(exc) from exc


@router.post(
    "/orders/mine/cart/request-credit-otp",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(rate_limit("cj-cart-credit-otp", max_requests=5, window_seconds=300))],
)
async def request_my_cj_cart_credit_otp(
    payload: CjCartCreditOtpRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    from app.modules.auth import service as auth_service
    from app.modules.users.models import User

    user = await db.get(User, current_user.user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Utente non trovato.")
    lines = await _my_cart_lines(db, current_user)
    try:
        quote = await service.get_quote(
            db, organization_id=current_user.organization_id, customer_user_id=current_user.user_id, lines=lines,
        )
    except ERRORS as exc:
        raise _http(exc) from exc
    articles = len(quote["items"])
    what = quote["product_name"] if articles == 1 else f"{articles} articoli"
    await auth_service.request_otp(
        db, user=user, purpose=auth_service.WALLET_CREDIT_SPEND_OTP_PURPOSE,
        context_line=(
            f"Stai per acquistare <strong>{what}</strong> "
            f"(ordine da {quote['amount_cents'] / 100:.2f} &euro;) e utilizzare "
            f"<strong>{payload.credit_applied_cents / 100:.2f} SosnetCash</strong> dal tuo wallet "
            "per pagarne una parte. Usa questo codice per confermare l'operazione."
        ),
    )
    return {"ok": True}


@router.post("/orders/mine/cart", status_code=status.HTTP_201_CREATED)
async def create_my_cj_order_from_cart(
    payload: CjCartOrderRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Turn the cart into an order; the cart is emptied only on success, so a
    failed creation leaves it intact."""
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
    await carts_service.clear(db, customer_user_id=current_user.user_id, shop="cj")
    return await service.order_read_dict(db, order, admin=False)


@router.get("/orders/mine")
async def list_my_cj_orders(
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


@router.post("/orders/mine/{order_id}/checkout-session", response_model=CheckoutSessionRead)
async def create_my_cj_checkout_session(
    order_id: uuid.UUID,
    success_url: str,
    cancel_url: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CheckoutSessionRead:
    order = await _owned(db, current_user, order_id)
    if order.status != "AWAITING_PAYMENT":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Questo ordine non è da pagare.")
    try:
        checkout_url = await payments_service.create_checkout_session_for_cj_order(
            db, organization_id=current_user.organization_id, order=order, success_url=success_url,
            cancel_url=cancel_url,
        )
    except payments_service.StripeNotConfiguredError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return CheckoutSessionRead(checkout_url=checkout_url)


@router.patch("/orders/mine/{order_id}/payment-method")
async def change_my_cj_payment_method(
    order_id: uuid.UUID,
    payload: CjOrderPaymentMethodUpdate,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    order = await _owned(db, current_user, order_id)
    try:
        order = await service.change_payment_method(
            db, organization_id=current_user.organization_id, order=order, new_payment_method=payload.payment_method
        )
    except ERRORS as exc:
        raise _http(exc) from exc
    return await service.order_read_dict(db, order, admin=False)


@router.post(
    "/orders/mine/{order_id}/payment-proof",
    dependencies=[Depends(rate_limit("cj-payment-proof-upload", max_requests=20, window_seconds=300))],
)
async def upload_my_cj_payment_proof(
    order_id: uuid.UUID,
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    order = await _owned(db, current_user, order_id)
    try:
        order = await service.upload_payment_proof(
            db, organization_id=current_user.organization_id, order=order, file_bytes=await file.read(),
            content_type=file.content_type or "", original_filename=file.filename or "prova-pagamento",
            actor_user_id=current_user.user_id,
        )
    except ERRORS as exc:
        raise _http(exc) from exc
    return await service.order_read_dict(db, order, admin=False)


@router.get("/orders/mine/{order_id}/payment-proof-url", response_model=PaymentProofUrlRead)
async def get_my_cj_payment_proof_url(
    order_id: uuid.UUID, current_user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> PaymentProofUrlRead:
    order = await _owned(db, current_user, order_id)
    if order.payment_proof_storage_key is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ricevuta non trovata.")
    return PaymentProofUrlRead(url=service.presigned_payment_proof_url(order))


# --- Admin: orders ----------------------------------------------------------------------------------


@router.get("/orders")
async def list_cj_orders(
    status_filter: str | None = None,
    current_user: CurrentUser = Depends(require_permission(ORDERS)),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    orders = await service.list_orders(db, organization_id=current_user.organization_id, status_filter=status_filter)
    return [await service.order_read_dict(db, o, admin=True) for o in orders]


@router.get("/orders/summary")
async def cj_cash_summary(
    refresh: bool = False,
    current_user: CurrentUser = Depends(require_permission(ORDERS)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Customer-paid orders not yet paid on CJ, their total CJ cost, the CJ
    balance and the shortfall."""
    return await service.cash_requirement(db, organization_id=current_user.organization_id, refresh_balance=refresh)


@router.post("/orders/{order_id}/confirm-payment")
async def confirm_cj_order_payment(
    order_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission(ORDERS)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        order = await service.confirm_payment(
            db, organization_id=current_user.organization_id, order_id=order_id, actor_user_id=current_user.user_id
        )
    except ERRORS as exc:
        raise _http(exc) from exc
    return await service.order_read_dict(db, order, admin=True)


@router.post("/orders/{order_id}/cancel")
async def cancel_cj_order(
    order_id: uuid.UUID,
    payload: CjOrderCancelRequest,
    current_user: CurrentUser = Depends(require_permission(ORDERS)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        order = await service.cancel_order(
            db, organization_id=current_user.organization_id, order_id=order_id, reason=payload.reason,
            actor_user_id=current_user.user_id,
        )
    except ERRORS as exc:
        raise _http(exc) from exc
    return await service.order_read_dict(db, order, admin=True)


@router.get("/orders/{order_id}/payment-proof-url", response_model=PaymentProofUrlRead)
async def get_cj_order_payment_proof_url(
    order_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission(ORDERS)),
    db: AsyncSession = Depends(get_db),
) -> PaymentProofUrlRead:
    order = await service.get_org_scoped(db, organization_id=current_user.organization_id, order_id=order_id)
    if order is None or order.payment_proof_storage_key is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ricevuta non trovata.")
    return PaymentProofUrlRead(url=service.presigned_payment_proof_url(order))


@router.post("/orders/{order_id}/forward")
async def forward_cj_order(
    order_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission(ORDERS)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """"Invia a CJ" / "Paga con saldo CJ": create the CJ order if missing, then
    pay it from the balance when sufficient (otherwise it stays
    PAYMENT_REQUIRED). Outcomes are recorded on the order, never raised."""
    try:
        order = await service.forward_order(
            db, organization_id=current_user.organization_id, order_id=order_id, actor_user_id=current_user.user_id
        )
    except ERRORS as exc:
        raise _http(exc) from exc
    return await service.order_read_dict(db, order, admin=True)


@router.post("/orders/{order_id}/sync")
async def sync_cj_order(
    order_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission(ORDERS)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    order = await service.get_org_scoped(db, organization_id=current_user.organization_id, order_id=order_id)
    if order is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ordine non trovato.")
    if not order.cj_order_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Questo ordine non è ancora su CJ.")
    try:
        await service.sync_orders(db, organization_id=current_user.organization_id, orders=[order])
    except ERRORS as exc:
        raise _http(exc) from exc
    await db.refresh(order)
    return await service.order_read_dict(db, order, admin=True)
