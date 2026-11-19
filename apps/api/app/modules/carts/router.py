"""Customer cart endpoints.

Only "mine" routes: a cart belongs to its owner and has no admin surface.
Ownership of each line is checked in the service, the single path every
call goes through.

Checkout is not here: turning a cart into an order belongs to each shop,
which knows its address, shipping, VAT and payment rules
(e.g. `POST /aliexpress/orders/mine/cart`).
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.foundation.db import get_db
from app.foundation.deps import CurrentUser, get_current_user
from app.modules.carts import service
from app.modules.carts.schemas import CartItemAddRequest, CartItemQuantityUpdate

router = APIRouter(prefix="/carts", tags=["carts"])


def _http(exc: Exception) -> HTTPException:
    if isinstance(exc, service.CartNotFoundError):
        return HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    return HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.get("/mine")
async def get_my_cart(
    current_user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> dict:
    """The whole cart, one section per shop, priced at current list prices."""
    return await service.summary(
        db, organization_id=current_user.organization_id, customer_user_id=current_user.user_id
    )


@router.post("/mine/{shop}/items", status_code=status.HTTP_201_CREATED)
async def add_to_my_cart(
    shop: str,
    payload: CartItemAddRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        await service.add_item(
            db, organization_id=current_user.organization_id, customer_user_id=current_user.user_id,
            shop=shop, variant_id=payload.variant_id, quantity=payload.quantity,
        )
    except (service.CartValidationError, service.CartNotFoundError) as exc:
        raise _http(exc) from exc
    return await service.summary(
        db, organization_id=current_user.organization_id, customer_user_id=current_user.user_id
    )


@router.patch("/mine/{shop}/items/{item_id}")
async def update_my_cart_item(
    shop: str,
    item_id: uuid.UUID,
    payload: CartItemQuantityUpdate,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        await service.set_quantity(
            db, organization_id=current_user.organization_id, customer_user_id=current_user.user_id,
            shop=shop, item_id=item_id, quantity=payload.quantity,
        )
    except (service.CartValidationError, service.CartNotFoundError) as exc:
        raise _http(exc) from exc
    return await service.summary(
        db, organization_id=current_user.organization_id, customer_user_id=current_user.user_id
    )


@router.delete("/mine/{shop}/items/{item_id}")
async def remove_from_my_cart(
    shop: str,
    item_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        await service.remove_item(db, customer_user_id=current_user.user_id, shop=shop, item_id=item_id)
    except (service.CartValidationError, service.CartNotFoundError) as exc:
        raise _http(exc) from exc
    return await service.summary(
        db, organization_id=current_user.organization_id, customer_user_id=current_user.user_id
    )


@router.delete("/mine/{shop}")
async def clear_my_cart(
    shop: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        await service.clear(db, customer_user_id=current_user.user_id, shop=shop)
    except (service.CartValidationError, service.CartNotFoundError) as exc:
        raise _http(exc) from exc
    return await service.summary(
        db, organization_id=current_user.organization_id, customer_user_id=current_user.user_id
    )
