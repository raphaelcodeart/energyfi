"""Reading and curating Shop categories.

Admin operations (create, rename, reorder, disable, delete, assign) sit
alongside the batch readers used by every product list
(category_ids_by_product() and siblings), which fetch a whole page's
categories in a single query to avoid per-product round trips.
"""

import uuid
from collections.abc import Sequence

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.foundation.db import utcnow
from app.modules.audit import service as audit_service
from app.modules.shop_categories.models import SHOPS, ShopCategory, ShopCategoryProduct


class ShopCategoryError(Exception):
    """Caller error; the Italian message is shown to the user as is."""


class ShopCategoryNotFoundError(ShopCategoryError):
    """-> 404."""


class ShopCategoryValidationError(ShopCategoryError):
    """-> 400."""


def normalize_shop(shop: str | None) -> str:
    """Single validation point for every incoming `shop` value."""
    key = (shop or "").strip().lower()
    if key not in SHOPS:
        raise ShopCategoryValidationError("Shop non valido.")
    return key


# --- Reads -----------------------------------------------------------------------------------------


async def list_categories(
    db: AsyncSession, *, organization_id: uuid.UUID, shop: str
) -> list[tuple[ShopCategory, int]]:
    """A shop's categories with product counts, in display order. Two
    queries regardless of the number of categories."""
    stmt = (
        select(ShopCategory)
        .where(ShopCategory.organization_id == organization_id, ShopCategory.shop == shop)
        .order_by(ShopCategory.position, ShopCategory.name)
    )
    categories = list((await db.execute(stmt)).scalars().all())
    if not categories:
        return []

    counts_stmt = (
        select(ShopCategoryProduct.category_id, func.count())
        .where(ShopCategoryProduct.category_id.in_([c.id for c in categories]))
        .group_by(ShopCategoryProduct.category_id)
    )
    counts: dict[uuid.UUID, int] = {
        category_id: count for category_id, count in (await db.execute(counts_stmt)).all()
    }
    return [(category, counts.get(category.id, 0)) for category in categories]


async def get_category(
    db: AsyncSession, *, organization_id: uuid.UUID, category_id: uuid.UUID
) -> ShopCategory:
    category = await db.get(ShopCategory, category_id)
    if category is None or category.organization_id != organization_id:
        raise ShopCategoryNotFoundError("Categoria non trovata.")
    return category


async def product_count(db: AsyncSession, *, category_id: uuid.UUID) -> int:
    """Product count for a single category (lists use the bulk count)."""
    stmt = (
        select(func.count())
        .select_from(ShopCategoryProduct)
        .where(ShopCategoryProduct.category_id == category_id)
    )
    return (await db.execute(stmt)).scalar_one()


async def category_ids_by_shop_product(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    shops: Sequence[str],
    product_ids: Sequence[uuid.UUID],
) -> dict[tuple[str, uuid.UUID], list[uuid.UUID]]:
    """{(shop, product_id): [category_id, ...]} in one query.

    Keyed by the pair because the catalog list spans three shops: a stale
    assignment from a product moved to another section must not follow it.
    """
    if not product_ids:
        return {}
    stmt = select(
        ShopCategoryProduct.shop, ShopCategoryProduct.product_id, ShopCategoryProduct.category_id
    ).where(
        ShopCategoryProduct.organization_id == organization_id,
        ShopCategoryProduct.shop.in_(list(shops)),
        ShopCategoryProduct.product_id.in_(list(product_ids)),
    )
    out: dict[tuple[str, uuid.UUID], list[uuid.UUID]] = {}
    for shop, product_id, category_id in (await db.execute(stmt)).all():
        out.setdefault((shop, product_id), []).append(category_id)
    return out


async def category_ids_by_product(
    db: AsyncSession, *, organization_id: uuid.UUID, shop: str, product_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, list[uuid.UUID]]:
    """Single-shop variant used by the marketplaces: {product_id: [...]}."""
    pairs = await category_ids_by_shop_product(
        db, organization_id=organization_id, shops=(shop,), product_ids=product_ids
    )
    return {product_id: ids for (_shop, product_id), ids in pairs.items()}


async def category_ids_for_product(
    db: AsyncSession, *, organization_id: uuid.UUID, shop: str, product_id: uuid.UUID
) -> list[uuid.UUID]:
    """One product's categories, for single-product responses; not for loops."""
    by_product = await category_ids_by_product(
        db, organization_id=organization_id, shop=shop, product_ids=(product_id,)
    )
    return by_product.get(product_id, [])


async def assignments_for_shop(
    db: AsyncSession, *, organization_id: uuid.UUID, shop: str
) -> dict[str, list[str]]:
    """{product_id: [category_id, ...]} as strings (JSON keys) for every
    categorised product of the shop."""
    stmt = select(ShopCategoryProduct.product_id, ShopCategoryProduct.category_id).where(
        ShopCategoryProduct.organization_id == organization_id, ShopCategoryProduct.shop == shop
    )
    out: dict[str, list[str]] = {}
    for product_id, category_id in (await db.execute(stmt)).all():
        out.setdefault(str(product_id), []).append(str(category_id))
    return out


# --- Writes ----------------------------------------------------------------------------------------


async def _name_taken(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    shop: str,
    name: str,
    exclude_id: uuid.UUID | None = None,
) -> bool:
    """Pre-check mirroring the unique index, so the admin gets a readable
    message instead of an integrity error."""
    stmt = select(ShopCategory.id).where(
        ShopCategory.organization_id == organization_id,
        ShopCategory.shop == shop,
        func.lower(ShopCategory.name) == name.lower(),
    )
    if exclude_id is not None:
        stmt = stmt.where(ShopCategory.id != exclude_id)
    return (await db.execute(stmt)).first() is not None


async def create_category(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    shop: str,
    name: str,
    position: int = 0,
    actor_user_id: uuid.UUID,
) -> ShopCategory:
    shop = normalize_shop(shop)
    name = name.strip()
    if not name:
        raise ShopCategoryValidationError("Il nome della categoria è obbligatorio.")
    if await _name_taken(db, organization_id=organization_id, shop=shop, name=name):
        raise ShopCategoryValidationError("Esiste già una categoria con questo nome in questo shop.")

    category = ShopCategory(
        organization_id=organization_id, shop=shop, name=name, position=position, active=True
    )
    db.add(category)
    await db.flush()
    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="shop_category.created", entity_type="shop_category", entity_id=str(category.id),
        new_value={"shop": shop, "name": name},
    )
    await db.commit()
    await db.refresh(category)
    return category


async def update_category(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    category_id: uuid.UUID,
    name: str | None = None,
    position: int | None = None,
    active: bool | None = None,
    actor_user_id: uuid.UUID,
) -> ShopCategory:
    category = await get_category(db, organization_id=organization_id, category_id=category_id)
    previous = {"name": category.name, "position": category.position, "active": category.active}

    if name is not None:
        new_name = name.strip()
        if not new_name:
            raise ShopCategoryValidationError("Il nome della categoria è obbligatorio.")
        if await _name_taken(
            db, organization_id=organization_id, shop=category.shop, name=new_name, exclude_id=category.id
        ):
            raise ShopCategoryValidationError("Esiste già una categoria con questo nome in questo shop.")
        category.name = new_name
    if position is not None:
        category.position = position
    if active is not None:
        category.active = active
    category.updated_at = utcnow()

    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="shop_category.updated", entity_type="shop_category", entity_id=str(category.id),
        previous_value=previous,
        new_value={"name": category.name, "position": category.position, "active": category.active},
    )
    await db.commit()
    await db.refresh(category)
    return category


async def delete_category(
    db: AsyncSession, *, organization_id: uuid.UUID, category_id: uuid.UUID, actor_user_id: uuid.UUID
) -> None:
    """Delete a category and its assignments (also removed explicitly so the
    session sees it, besides ON DELETE CASCADE). Products are untouched."""
    category = await get_category(db, organization_id=organization_id, category_id=category_id)
    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="shop_category.deleted", entity_type="shop_category", entity_id=str(category.id),
        previous_value={"shop": category.shop, "name": category.name},
    )
    await db.execute(delete(ShopCategoryProduct).where(ShopCategoryProduct.category_id == category.id))
    await db.delete(category)
    await db.commit()


async def replace_assignments(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    shop: str,
    product_id: uuid.UUID,
    category_ids: Sequence[uuid.UUID],
    actor_user_id: uuid.UUID,
) -> list[uuid.UUID]:
    """Replace, in full, a product's categories within `shop`.

    Ids are validated against this organization and shop before writing; a
    foreign category is rejected rather than silently dropped.
    """
    shop = normalize_shop(shop)
    wanted = list(dict.fromkeys(category_ids))

    if wanted:
        found_stmt = select(ShopCategory.id).where(
            ShopCategory.organization_id == organization_id,
            ShopCategory.shop == shop,
            ShopCategory.id.in_(wanted),
        )
        found = set((await db.execute(found_stmt)).scalars().all())
        if len(found) != len(wanted):
            raise ShopCategoryValidationError(
                "Una o più categorie non esistono o non appartengono a questo shop."
            )

    await db.execute(
        delete(ShopCategoryProduct).where(
            ShopCategoryProduct.organization_id == organization_id,
            ShopCategoryProduct.shop == shop,
            ShopCategoryProduct.product_id == product_id,
        )
    )
    for category_id in wanted:
        db.add(
            ShopCategoryProduct(
                organization_id=organization_id,
                category_id=category_id,
                shop=shop,
                product_id=product_id,
            )
        )

    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="shop_category.products_assigned", entity_type="shop_category_product",
        entity_id=str(product_id),
        new_value={"shop": shop, "category_ids": [str(cid) for cid in wanted]},
    )
    await db.commit()
    return wanted
