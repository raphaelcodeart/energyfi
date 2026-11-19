import uuid

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.foundation.db import utcnow
from app.modules.audit import service as audit_service
from app.modules.catalog.models import Company, Product, ProductVersion
from app.modules.catalog.schemas import (
    ProductCreate,
    ProductUpdate,
    ProductVersionCreate,
    ProductVersionUpdate,
)
from app.modules.contracts.models import Contract


class ProductDeletionError(Exception):
    """Raised when a product cannot be deleted (see delete_product)."""


def _clamp_credit_discount(category: str, requested: int) -> int:
    """INTERNAL products are never discountable with wallet credits. Single
    enforcement point for every create/update path."""
    return requested if category != "INTERNAL" else 0


def _clamp_cashback_enabled(category: str, requested: bool) -> bool:
    """INTERNAL products never offer instant order cashback."""
    return requested if category != "INTERNAL" else False


def _clamp_contract_cashback(category: str, requested: int) -> int:
    """Automatic contract cashback exists only on INTERNAL products; other
    categories use opt-in order cashback, and the two never coexist."""
    if category != "INTERNAL":
        return 0
    return max(0, min(100, requested))


def _clamp_first_referrer_bonus(category: str, enabled: bool, amount_cents: int) -> tuple[bool, int]:
    """The legacy first-referrer bonus comes from contracts, so it exists only
    on INTERNAL products. A zero amount forces it disabled."""
    if category != "INTERNAL":
        return False, 0
    amount = max(0, amount_cents)
    # Keep the amount even when disabled so enabling later does not lose it.
    return (enabled and amount > 0), amount


def _margin_values(payload) -> dict:
    """All three margin columns from a payload, so switching type clears the
    stale value."""
    margin_type = getattr(payload, "margin_type", None)
    if margin_type is None:
        return {}
    return {
        "margin_type": margin_type,
        "margin_amount_cents": payload.margin_amount_cents if margin_type == "FIXED" else None,
        "margin_percentage": payload.margin_percentage if margin_type == "PERCENTAGE" else None,
    }


def _margin_snapshot(version) -> dict:
    return {
        "margin_type": version.margin_type,
        "margin_amount_cents": version.margin_amount_cents,
        "margin_percentage": str(version.margin_percentage) if version.margin_percentage is not None else None,
    }


async def list_products(db: AsyncSession, *, organization_id: uuid.UUID) -> list[Product]:
    stmt = (
        select(Product)
        .where(Product.organization_id == organization_id)
        .order_by(Product.created_at.desc())
    )
    return list((await db.execute(stmt)).scalars().all())


async def list_products_with_current_version(
    db: AsyncSession, *, organization_id: uuid.UUID
) -> list[tuple[Product, ProductVersion | None]]:
    """Each product with its most recent version by valid_from."""
    products = await list_products(db, organization_id=organization_id)
    if not products:
        return []

    product_ids = [p.id for p in products]
    versions_stmt = (
        select(ProductVersion)
        .where(ProductVersion.product_id.in_(product_ids))
        .order_by(ProductVersion.product_id, ProductVersion.valid_from.desc())
    )
    versions = (await db.execute(versions_stmt)).scalars().all()

    latest_by_product: dict[uuid.UUID, ProductVersion] = {}
    for version in versions:
        if version.product_id not in latest_by_product:
            latest_by_product[version.product_id] = version

    return [(product, latest_by_product.get(product.id)) for product in products]


async def get_product_with_versions(
    db: AsyncSession, *, organization_id: uuid.UUID, product_id: uuid.UUID
) -> tuple[Product, list[ProductVersion]] | None:
    product = await db.get(Product, product_id)
    if product is None or product.organization_id != organization_id:
        return None
    stmt = (
        select(ProductVersion)
        .where(ProductVersion.product_id == product_id)
        .order_by(ProductVersion.valid_from.desc())
    )
    versions = (await db.execute(stmt)).scalars().all()
    return product, list(versions)


async def create_product(
    db: AsyncSession, *, organization_id: uuid.UUID, payload: ProductCreate, actor_user_id: uuid.UUID
) -> Product:
    """Create a product and its first version in one transaction; a product
    without versions cannot be sold."""
    product = Product(
        organization_id=organization_id,
        code=payload.code,
        product_type=payload.product_type,
        energy_type=payload.energy_type,
        customer_type=payload.customer_type,
        category=payload.category,
        commercial_category_id=payload.commercial_category_id,
        company_id=await _checked_company_id(db, organization_id=organization_id, company_id=payload.company_id),
        status="ACTIVE",
    )
    db.add(product)
    await db.flush()

    _first_referrer_enabled, _first_referrer_cents = _clamp_first_referrer_bonus(
        payload.category, payload.first_referrer_bonus_enabled, payload.first_referrer_bonus_cents
    )
    version = ProductVersion(
        product_id=product.id,
        version_label=payload.version_label,
        name=payload.name,
        description=payload.description,
        image_url=payload.image_url,
        base_price_cents=payload.base_price_cents,
        initial_fee_cents=payload.initial_fee_cents,
        recurring_fee_cents=payload.recurring_fee_cents,
        billing_period=payload.billing_period,
        tax_configuration={"vat_percentage": payload.vat_percentage} if payload.vat_percentage is not None else {},
        contract_duration_months=payload.contract_duration_months,
        commission_tokens=payload.commission_tokens,
        credit_discount_percentage=_clamp_credit_discount(payload.category, payload.credit_discount_percentage),
        cashback_enabled=_clamp_cashback_enabled(payload.category, payload.cashback_enabled),
        contract_cashback_percentage=_clamp_contract_cashback(payload.category, payload.contract_cashback_percentage),
        first_referrer_bonus_enabled=_first_referrer_enabled,
        first_referrer_bonus_cents=_first_referrer_cents,
        **_margin_values(payload),
        valid_from=utcnow(),
        status="ACTIVE",
    )
    db.add(version)

    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="product.created", entity_type="product", entity_id=str(product.id),
        new_value={"code": payload.code, "name": payload.name},
    )
    await db.commit()
    await db.refresh(product)
    return product


async def add_product_version(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    product_id: uuid.UUID,
    payload: ProductVersionCreate,
    actor_user_id: uuid.UUID,
) -> ProductVersion | None:
    """Add a version without touching previous ones, which existing contracts
    still reference."""
    product = await db.get(Product, product_id)
    if product is None or product.organization_id != organization_id:
        return None

    _version_first_referrer_enabled, _version_first_referrer_cents = _clamp_first_referrer_bonus(
        product.category, payload.first_referrer_bonus_enabled, payload.first_referrer_bonus_cents
    )
    version = ProductVersion(
        product_id=product_id,
        version_label=payload.version_label,
        name=payload.name,
        description=payload.description,
        image_url=payload.image_url,
        base_price_cents=payload.base_price_cents,
        initial_fee_cents=payload.initial_fee_cents,
        recurring_fee_cents=payload.recurring_fee_cents,
        billing_period=payload.billing_period,
        tax_configuration={"vat_percentage": payload.vat_percentage} if payload.vat_percentage is not None else {},
        contract_duration_months=payload.contract_duration_months,
        commission_tokens=payload.commission_tokens,
        credit_discount_percentage=_clamp_credit_discount(product.category, payload.credit_discount_percentage),
        cashback_enabled=_clamp_cashback_enabled(product.category, payload.cashback_enabled),
        contract_cashback_percentage=_clamp_contract_cashback(product.category, payload.contract_cashback_percentage),
        first_referrer_bonus_enabled=_version_first_referrer_enabled,
        first_referrer_bonus_cents=_version_first_referrer_cents,
        **_margin_values(payload),
        valid_from=utcnow(),
        status="ACTIVE",
    )
    db.add(version)

    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="product.version_added", entity_type="product", entity_id=str(product_id),
        new_value={"version_label": payload.version_label},
    )
    await db.commit()
    await db.refresh(version)
    return version


async def update_product_version(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    version_id: uuid.UUID,
    payload: ProductVersionUpdate,
    actor_user_id: uuid.UUID,
) -> ProductVersion | None:
    """Edit a version in place, meant for corrections before it is sold. For
    versions in use, add a new version so contract pricing never changes."""
    version = await db.get(ProductVersion, version_id)
    if version is None:
        return None
    product = await db.get(Product, version.product_id)
    if product is None or product.organization_id != organization_id:
        return None

    previous = {"status": version.status, "base_price_cents": version.base_price_cents, **_margin_snapshot(version)}
    if payload.margin_type is not None:
        for field, value in _margin_values(payload).items():
            setattr(version, field, value)
    if payload.name is not None:
        version.name = payload.name
    if payload.description is not None:
        version.description = payload.description
    if payload.image_url is not None:
        version.image_url = payload.image_url
    if payload.base_price_cents is not None:
        version.base_price_cents = payload.base_price_cents
    if payload.initial_fee_cents is not None:
        version.initial_fee_cents = payload.initial_fee_cents
    if payload.recurring_fee_cents is not None:
        version.recurring_fee_cents = payload.recurring_fee_cents
    if payload.vat_percentage is not None:
        version.tax_configuration = {**(version.tax_configuration or {}), "vat_percentage": payload.vat_percentage}
    if payload.contract_duration_months is not None:
        version.contract_duration_months = payload.contract_duration_months
    if payload.commission_tokens is not None:
        version.commission_tokens = payload.commission_tokens
    if payload.credit_discount_percentage is not None:
        version.credit_discount_percentage = _clamp_credit_discount(product.category, payload.credit_discount_percentage)
    if payload.cashback_enabled is not None:
        version.cashback_enabled = _clamp_cashback_enabled(product.category, payload.cashback_enabled)
    if payload.contract_cashback_percentage is not None:
        version.contract_cashback_percentage = _clamp_contract_cashback(
            product.category, payload.contract_cashback_percentage
        )
    if payload.first_referrer_bonus_enabled is not None or payload.first_referrer_bonus_cents is not None:
        enabled, cents = _clamp_first_referrer_bonus(
            product.category,
            version.first_referrer_bonus_enabled
            if payload.first_referrer_bonus_enabled is None
            else payload.first_referrer_bonus_enabled,
            version.first_referrer_bonus_cents
            if payload.first_referrer_bonus_cents is None
            else payload.first_referrer_bonus_cents,
        )
        version.first_referrer_bonus_enabled = enabled
        version.first_referrer_bonus_cents = cents
    if payload.status is not None:
        version.status = payload.status

    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="product.version_updated", entity_type="product_version", entity_id=str(version_id),
        previous_value=previous,
        new_value={"status": version.status, "base_price_cents": version.base_price_cents, **_margin_snapshot(version)},
    )
    await db.commit()
    await db.refresh(version)
    return version


async def delete_product(
    db: AsyncSession, *, organization_id: uuid.UUID, product_id: uuid.UUID, actor_user_id: uuid.UUID
) -> bool | None:
    """Hard-delete a product and its versions. Returns None if not found;
    raises ProductDeletionError if any version was ever sold, since contracts
    must keep referencing it (retire it instead)."""
    product = await db.get(Product, product_id)
    if product is None or product.organization_id != organization_id:
        return None

    version_ids_stmt = select(ProductVersion.id).where(ProductVersion.product_id == product_id)
    version_ids = list((await db.execute(version_ids_stmt)).scalars().all())

    if version_ids:
        contract_count = (
            await db.execute(select(func.count()).select_from(Contract).where(Contract.product_version_id.in_(version_ids)))
        ).scalar_one()
        if contract_count > 0:
            raise ProductDeletionError(
                "Impossibile eliminare: questo prodotto ha contratti associati. Puoi solo disattivarlo."
            )

    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="product.deleted", entity_type="product", entity_id=str(product_id),
        previous_value={"code": product.code, "status": product.status},
    )
    await db.execute(delete(ProductVersion).where(ProductVersion.product_id == product_id))
    await db.delete(product)
    await db.commit()
    return True


async def update_product(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    product_id: uuid.UUID,
    payload: ProductUpdate,
    actor_user_id: uuid.UUID,
) -> Product | None:
    """Update product-level fields such as status. Pricing is per version."""
    product = await db.get(Product, product_id)
    if product is None or product.organization_id != organization_id:
        return None

    previous = {"status": product.status, "commercial_category_id": str(product.commercial_category_id or "")}
    if payload.status is not None:
        product.status = payload.status
    if payload.commercial_category_id is not None:
        product.commercial_category_id = payload.commercial_category_id
    if payload.clear_company:
        product.company_id = None
    elif payload.company_id is not None:
        product.company_id = await _checked_company_id(
            db, organization_id=organization_id, company_id=payload.company_id
        )
    if payload.product_type is not None:
        product.product_type = payload.product_type
    if payload.energy_type is not None:
        product.energy_type = payload.energy_type
    if payload.category is not None:
        product.category = payload.category
        if payload.category == "INTERNAL":
            # Clear credit discount and order cashback on every version.
            await db.execute(
                update(ProductVersion)
                .where(ProductVersion.product_id == product_id)
                .values(credit_discount_percentage=0, cashback_enabled=False)
            )

    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="product.updated", entity_type="product", entity_id=str(product_id),
        previous_value=previous, new_value={"status": product.status},
    )
    await db.commit()
    await db.refresh(product)
    return product


# --- Companies -------------------------------------------------------------------


class CompanyError(Exception):
    pass


async def _checked_company_id(db: AsyncSession, *, organization_id: uuid.UUID, company_id: uuid.UUID | None) -> uuid.UUID | None:
    if company_id is None:
        return None
    company = await db.get(Company, company_id)
    if company is None or company.organization_id != organization_id:
        raise CompanyError("Azienda non trovata.")
    return company.id


async def list_companies(db: AsyncSession, *, organization_id: uuid.UUID) -> list[dict]:
    counts = dict((await db.execute(
        select(Product.company_id, func.count()).where(
            Product.organization_id == organization_id, Product.company_id.is_not(None),
        ).group_by(Product.company_id)
    )).all())
    companies = (await db.execute(
        select(Company).where(Company.organization_id == organization_id).order_by(Company.name)
    )).scalars().all()
    return [
        {"id": c.id, "name": c.name, "description": c.description, "logo_url": c.logo_url,
         "website_url": c.website_url, "max_network_depth": c.max_network_depth, "is_active": c.is_active,
         "products": counts.get(c.id, 0)}
        for c in companies
    ]


async def save_company(
    db: AsyncSession, *, organization_id: uuid.UUID, actor_user_id: uuid.UUID, values: dict,
    company_id: uuid.UUID | None = None,
) -> Company:
    """Create a company, or update it when `company_id` is given. Commits."""
    name = values["name"].strip()
    clash = (await db.execute(select(Company.id).where(
        Company.organization_id == organization_id, func.lower(Company.name) == name.lower(),
        *([Company.id != company_id] if company_id else []),
    ))).first()
    if clash:
        raise CompanyError(f"Esiste già un'azienda chiamata «{name}».")
    if company_id is None:
        company = Company(organization_id=organization_id)
        db.add(company)
        previous = None
    else:
        company = await db.get(Company, company_id)
        if company is None or company.organization_id != organization_id:
            raise CompanyError("Azienda non trovata.")
        previous = {"name": company.name, "max_network_depth": company.max_network_depth, "is_active": company.is_active}
    company.name = name
    company.description = values.get("description") or ""
    company.logo_url = values.get("logo_url") or None
    company.website_url = values.get("website_url") or None
    company.max_network_depth = values.get("max_network_depth")
    company.is_active = values.get("is_active", True)
    await db.flush()
    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="company.created" if previous is None else "company.updated", entity_type="company",
        entity_id=str(company.id), previous_value=previous,
        new_value={"name": company.name, "max_network_depth": company.max_network_depth, "is_active": company.is_active},
    )
    await db.commit()
    await db.refresh(company)
    return company
