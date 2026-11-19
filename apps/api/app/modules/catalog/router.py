import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.foundation.db import get_db
from app.foundation.deps import CurrentUser, require_permission
from app.foundation.storage import UploadValidationError, upload_media
from app.modules.catalog import service as catalog_service
from app.modules.catalog.schemas import (
    CompanyRead,
    CompanyWrite,
    ProductCatalogRead,
    ProductCreate,
    ProductRead,
    ProductUpdate,
    ProductVersionCreate,
    ProductVersionRead,
    ProductVersionUpdate,
    ProductWithVersionsRead,
)
from app.modules.shop_categories import service as shop_categories_service
from app.modules.shop_categories.models import CATALOG_SHOPS, shop_for_catalog_category

router = APIRouter(prefix="/products", tags=["catalog"])


@router.get("", response_model=list[ProductCatalogRead])
async def list_products(
    current_user: CurrentUser = Depends(require_permission("products.read")),
    db: AsyncSession = Depends(get_db),
) -> list[ProductCatalogRead]:
    """Every product with its current version's display fields. Serves both
    the admin grid and the marketplace; the customer app filters to ACTIVE."""
    pairs = await catalog_service.list_products_with_current_version(
        db, organization_id=current_user.organization_id
    )
    # One query for the page, keyed by (shop, product id) since the list spans
    # all sections.
    categories = await shop_categories_service.category_ids_by_shop_product(
        db,
        organization_id=current_user.organization_id,
        shops=CATALOG_SHOPS,
        product_ids=[product.id for product, _version in pairs],
    )
    return [
        ProductCatalogRead(
            **ProductRead.model_validate(product).model_dump(),
            current_version=(
                ProductVersionRead.from_version(version, category=product.category, product_type=product.product_type)
                if version
                else None
            ),
            category_ids=categories.get((shop_for_catalog_category(product.category), product.id), []),
        )
        for product, version in pairs
    ]


@router.get("/companies", response_model=list[CompanyRead])
async def list_companies(
    current_user: CurrentUser = Depends(require_permission("products.read")),
    db: AsyncSession = Depends(get_db),
) -> list[CompanyRead]:
    """The companies behind the products, with how many products each has."""
    rows = await catalog_service.list_companies(db, organization_id=current_user.organization_id)
    return [CompanyRead(**row) for row in rows]


@router.post("/companies", response_model=CompanyRead, status_code=status.HTTP_201_CREATED)
async def create_company(
    payload: CompanyWrite,
    current_user: CurrentUser = Depends(require_permission("products.manage")),
    db: AsyncSession = Depends(get_db),
) -> CompanyRead:
    try:
        company = await catalog_service.save_company(
            db, organization_id=current_user.organization_id, actor_user_id=current_user.user_id,
            values=payload.model_dump(),
        )
    except catalog_service.CompanyError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return CompanyRead.model_validate(company)


@router.put("/companies/{company_id}", response_model=CompanyRead)
async def update_company(
    company_id: uuid.UUID,
    payload: CompanyWrite,
    current_user: CurrentUser = Depends(require_permission("products.manage")),
    db: AsyncSession = Depends(get_db),
) -> CompanyRead:
    try:
        company = await catalog_service.save_company(
            db, organization_id=current_user.organization_id, actor_user_id=current_user.user_id,
            values=payload.model_dump(), company_id=company_id,
        )
    except catalog_service.CompanyError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return CompanyRead.model_validate(company)


@router.get("/{product_id}", response_model=ProductWithVersionsRead)
async def get_product(
    product_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("products.read")),
    db: AsyncSession = Depends(get_db),
) -> ProductWithVersionsRead:
    result = await catalog_service.get_product_with_versions(
        db, organization_id=current_user.organization_id, product_id=product_id
    )
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")
    product, versions = result
    return ProductWithVersionsRead(
        **ProductRead.model_validate(product).model_dump(),
        versions=[
            ProductVersionRead.from_version(v, category=product.category, product_type=product.product_type)
            for v in versions
        ],
        category_ids=await shop_categories_service.category_ids_for_product(
            db,
            organization_id=current_user.organization_id,
            shop=shop_for_catalog_category(product.category),
            product_id=product.id,
        ),
    )


@router.patch("/{product_id}", response_model=ProductRead)
async def update_product(
    product_id: uuid.UUID,
    payload: ProductUpdate,
    current_user: CurrentUser = Depends(require_permission("products.manage")),
    db: AsyncSession = Depends(get_db),
) -> ProductRead:
    try:
        product = await catalog_service.update_product(
            db,
            organization_id=current_user.organization_id,
            product_id=product_id,
            payload=payload,
            actor_user_id=current_user.user_id,
        )
    except catalog_service.CompanyError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")
    return ProductRead.model_validate(product)


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(
    product_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("products.manage")),
    db: AsyncSession = Depends(get_db),
) -> None:
    try:
        result = await catalog_service.delete_product(
            db, organization_id=current_user.organization_id, product_id=product_id,
            actor_user_id=current_user.user_id,
        )
    except catalog_service.ProductDeletionError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")


@router.post("", response_model=ProductRead, status_code=status.HTTP_201_CREATED)
async def create_product(
    payload: ProductCreate,
    current_user: CurrentUser = Depends(require_permission("products.manage")),
    db: AsyncSession = Depends(get_db),
) -> ProductRead:
    try:
        product = await catalog_service.create_product(
            db, organization_id=current_user.organization_id, payload=payload, actor_user_id=current_user.user_id
        )
    except catalog_service.CompanyError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return ProductRead.model_validate(product)


@router.post(
    "/{product_id}/versions", response_model=ProductVersionRead, status_code=status.HTTP_201_CREATED
)
async def add_product_version(
    product_id: uuid.UUID,
    payload: ProductVersionCreate,
    current_user: CurrentUser = Depends(require_permission("products.manage")),
    db: AsyncSession = Depends(get_db),
) -> ProductVersionRead:
    version = await catalog_service.add_product_version(
        db,
        organization_id=current_user.organization_id,
        product_id=product_id,
        payload=payload,
        actor_user_id=current_user.user_id,
    )
    if version is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")
    return ProductVersionRead.from_version(version)


@router.patch("/versions/{version_id}", response_model=ProductVersionRead)
async def update_product_version(
    version_id: uuid.UUID,
    payload: ProductVersionUpdate,
    current_user: CurrentUser = Depends(require_permission("products.manage")),
    db: AsyncSession = Depends(get_db),
) -> ProductVersionRead:
    version = await catalog_service.update_product_version(
        db,
        organization_id=current_user.organization_id,
        version_id=version_id,
        payload=payload,
        actor_user_id=current_user.user_id,
    )
    if version is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product version not found")
    return ProductVersionRead.from_version(version)


@router.post("/versions/{version_id}/photo", response_model=ProductVersionRead)
async def upload_product_version_photo(
    version_id: uuid.UUID,
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(require_permission("products.manage")),
    db: AsyncSession = Depends(get_db),
) -> ProductVersionRead:
    file_bytes = await file.read()
    try:
        photo_url = upload_media(
            file_bytes=file_bytes, content_type=file.content_type or "", key_prefix="photos/products"
        )
    except UploadValidationError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    version = await catalog_service.update_product_version(
        db, organization_id=current_user.organization_id, version_id=version_id,
        payload=ProductVersionUpdate(image_url=photo_url), actor_user_id=current_user.user_id,
    )
    if version is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product version not found")
    return ProductVersionRead.from_version(version)
