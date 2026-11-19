"""Shop categories API.

Listing is open to every logged-in user, customers included, who need the
names to filter the grid. Every change requires `products.manage`, the same
permission that governs the catalog.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.foundation.db import get_db
from app.foundation.deps import CurrentUser, get_current_user, require_permission
from app.modules.shop_categories import service
from app.modules.shop_categories.schemas import (
    ShopCategoryAssignmentRead,
    ShopCategoryAssignmentUpdate,
    ShopCategoryCreate,
    ShopCategoryRead,
    ShopCategoryUpdate,
)

router = APIRouter(prefix="/shop-categories", tags=["shop-categories"])

MANAGE = "products.manage"


def _http(exc: service.ShopCategoryError) -> HTTPException:
    if isinstance(exc, service.ShopCategoryNotFoundError):
        return HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    return HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.get("", response_model=list[ShopCategoryRead])
async def list_shop_categories(
    shop: str = Query(...),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ShopCategoryRead]:
    """A shop's categories with product counts, inactive ones included (the
    admin needs them; the customer app hides them)."""
    try:
        key = service.normalize_shop(shop)
    except service.ShopCategoryError as exc:
        raise _http(exc) from exc
    rows = await service.list_categories(db, organization_id=current_user.organization_id, shop=key)
    return [
        ShopCategoryRead(
            id=category.id, shop=category.shop, name=category.name, position=category.position,
            active=category.active, product_count=count,
        )
        for category, count in rows
    ]


@router.get("/assignments")
async def list_shop_category_assignments(
    shop: str = Query(...),
    current_user: CurrentUser = Depends(require_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> dict[str, list[str]]:
    """{product_id: [category_id, ...]} for every categorised product of
    the shop, in one call for the whole admin screen."""
    try:
        key = service.normalize_shop(shop)
    except service.ShopCategoryError as exc:
        raise _http(exc) from exc
    return await service.assignments_for_shop(db, organization_id=current_user.organization_id, shop=key)


@router.put("/assignments", response_model=ShopCategoryAssignmentRead)
async def replace_shop_category_assignments(
    payload: ShopCategoryAssignmentUpdate,
    current_user: CurrentUser = Depends(require_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> ShopCategoryAssignmentRead:
    """Replace a product's categories in one shop; the product itself is
    never modified."""
    try:
        category_ids = await service.replace_assignments(
            db, organization_id=current_user.organization_id, shop=payload.shop,
            product_id=payload.product_id, category_ids=payload.category_ids,
            actor_user_id=current_user.user_id,
        )
    except service.ShopCategoryError as exc:
        raise _http(exc) from exc
    return ShopCategoryAssignmentRead(
        shop=service.normalize_shop(payload.shop), product_id=payload.product_id, category_ids=category_ids
    )


@router.post("", response_model=ShopCategoryRead, status_code=status.HTTP_201_CREATED)
async def create_shop_category(
    payload: ShopCategoryCreate,
    current_user: CurrentUser = Depends(require_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> ShopCategoryRead:
    try:
        category = await service.create_category(
            db, organization_id=current_user.organization_id, shop=payload.shop, name=payload.name,
            position=payload.position, actor_user_id=current_user.user_id,
        )
    except service.ShopCategoryError as exc:
        raise _http(exc) from exc
    return ShopCategoryRead(
        id=category.id, shop=category.shop, name=category.name, position=category.position,
        active=category.active, product_count=0,
    )


@router.patch("/{category_id}", response_model=ShopCategoryRead)
async def update_shop_category(
    category_id: uuid.UUID,
    payload: ShopCategoryUpdate,
    current_user: CurrentUser = Depends(require_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> ShopCategoryRead:
    try:
        category = await service.update_category(
            db, organization_id=current_user.organization_id, category_id=category_id,
            name=payload.name, position=payload.position, active=payload.active,
            actor_user_id=current_user.user_id,
        )
    except service.ShopCategoryError as exc:
        raise _http(exc) from exc
    return ShopCategoryRead(
        id=category.id, shop=category.shop, name=category.name, position=category.position,
        active=category.active,
        # The admin re-renders the chip from this response, count included.
        product_count=await service.product_count(db, category_id=category.id),
    )


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_shop_category(
    category_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete the category and its assignments; products are untouched."""
    try:
        await service.delete_category(
            db, organization_id=current_user.organization_id, category_id=category_id,
            actor_user_id=current_user.user_id,
        )
    except service.ShopCategoryError as exc:
        raise _http(exc) from exc
