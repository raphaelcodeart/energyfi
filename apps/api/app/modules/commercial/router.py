import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.foundation.db import get_db
from app.foundation.deps import CurrentUser, get_current_user, require_permission
from app.modules.catalog.schemas import ProductCategoryIn, ProductCategoryUpdate
from app.modules.commercial import service
from app.modules.network.models import AgentProfile

router = APIRouter(prefix="/commercial", tags=["commercial"])


class CommercialRoleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str
    description: str
    commission_mode: str
    network_depth: int | None
    allows_delegation: bool
    allows_downline: bool
    can_close_sales: bool
    is_default: bool
    is_active: bool
    sort_order: int


class CommercialRoleIn(BaseModel):
    code: str = Field(min_length=2, max_length=32, pattern=r"^[A-Za-z0-9_]+$")
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=1000)
    commission_mode: str = "PERCENTAGE"
    network_depth: int | None = Field(default=None, ge=0, le=50)
    allows_delegation: bool = False
    allows_downline: bool = True
    can_close_sales: bool = True
    is_default: bool = False
    is_active: bool = True
    sort_order: int = 0


class CommercialRoleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    commission_mode: str | None = None
    network_depth: int | None = Field(default=None, ge=0, le=50)
    allows_delegation: bool | None = None
    allows_downline: bool | None = None
    can_close_sales: bool | None = None
    is_default: bool | None = None
    is_active: bool | None = None
    sort_order: int | None = None


class RoleAssignment(BaseModel):
    role_id: uuid.UUID
    effective_from: datetime | None = None
    reason: str | None = Field(default=None, max_length=500)


class DelegationIn(BaseModel):
    influencer_agent_id: uuid.UUID
    delegate_agent_id: uuid.UUID
    reason: str | None = Field(default=None, max_length=500)


def _error(exc: service.CommercialRoleError) -> HTTPException:
    return HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.get("/roles", response_model=list[CommercialRoleRead])
async def list_roles(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[CommercialRoleRead]:
    """Reference data readable by any organization member."""
    roles = await service.list_roles(db, organization_id=current_user.organization_id)
    return [CommercialRoleRead.model_validate(r) for r in roles]


@router.post("/roles", response_model=CommercialRoleRead, status_code=status.HTTP_201_CREATED)
async def create_role(
    payload: CommercialRoleIn,
    current_user: CurrentUser = Depends(require_permission("commercial_roles.manage")),
    db: AsyncSession = Depends(get_db),
) -> CommercialRoleRead:
    try:
        role = await service.create_role(
            db, organization_id=current_user.organization_id, actor_user_id=current_user.user_id,
            values=payload.model_dump(),
        )
    except service.CommercialRoleError as exc:
        raise _error(exc) from exc
    return CommercialRoleRead.model_validate(role)


@router.patch("/roles/{role_id}", response_model=CommercialRoleRead)
async def update_role(
    role_id: uuid.UUID,
    payload: CommercialRoleUpdate,
    current_user: CurrentUser = Depends(require_permission("commercial_roles.manage")),
    db: AsyncSession = Depends(get_db),
) -> CommercialRoleRead:
    try:
        role = await service.update_role(
            db, organization_id=current_user.organization_id, role_id=role_id,
            actor_user_id=current_user.user_id, values=payload.model_dump(exclude_unset=True),
        )
    except service.CommercialRoleError as exc:
        raise _error(exc) from exc
    return CommercialRoleRead.model_validate(role)


@router.get("/agents/{agent_id}/roles")
async def agent_role_history(
    agent_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("network.read_branch")),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    agent = await db.get(AgentProfile, agent_id)
    if agent is None or agent.organization_id != current_user.organization_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Collaboratore non trovato.")
    return await service.role_history(db, organization_id=current_user.organization_id, agent_id=agent_id)


@router.post("/agents/{agent_id}/role", status_code=status.HTTP_201_CREATED)
async def assign_role(
    agent_id: uuid.UUID,
    payload: RoleAssignment,
    current_user: CurrentUser = Depends(require_permission("commercial_roles.manage")),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    try:
        await service.assign_role(
            db, organization_id=current_user.organization_id, agent_id=agent_id, role_id=payload.role_id,
            actor_user_id=current_user.user_id, effective_from=payload.effective_from, reason=payload.reason,
        )
    except service.CommercialRoleError as exc:
        raise _error(exc) from exc
    return await service.role_history(db, organization_id=current_user.organization_id, agent_id=agent_id)


@router.get("/delegations")
async def list_delegations(
    influencer_agent_id: uuid.UUID | None = None,
    current_user: CurrentUser = Depends(require_permission("network.read_branch")),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    return await service.list_delegations(
        db, organization_id=current_user.organization_id, influencer_agent_id=influencer_agent_id
    )


@router.post("/delegations", status_code=status.HTTP_201_CREATED)
async def create_delegation(
    payload: DelegationIn,
    current_user: CurrentUser = Depends(require_permission("commercial_roles.manage")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        delegation = await service.create_delegation(
            db, organization_id=current_user.organization_id, influencer_agent_id=payload.influencer_agent_id,
            delegate_agent_id=payload.delegate_agent_id, actor_user_id=current_user.user_id, reason=payload.reason,
        )
    except service.CommercialRoleError as exc:
        raise _error(exc) from exc
    return {"id": str(delegation.id)}


@router.post("/delegations/{delegation_id}/end")
async def end_delegation(
    delegation_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("commercial_roles.manage")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        delegation = await service.end_delegation(
            db, organization_id=current_user.organization_id, delegation_id=delegation_id,
            actor_user_id=current_user.user_id,
        )
    except service.CommercialRoleError as exc:
        raise _error(exc) from exc
    return {"id": str(delegation.id), "valid_to": delegation.valid_to}


# --- Product commercial categories -------------------------------------------------------


@router.get("/categories")
async def list_categories(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    from sqlalchemy import select

    from app.modules.catalog.models import ProductCategory
    from app.modules.catalog.schemas import ProductCategoryRead

    rows = (
        await db.execute(
            select(ProductCategory).where(ProductCategory.organization_id == current_user.organization_id)
            .order_by(ProductCategory.name)
        )
    ).scalars()
    return [ProductCategoryRead.model_validate(r).model_dump(mode="json") for r in rows]


@router.post("/categories", status_code=status.HTTP_201_CREATED)
async def create_category(
    payload: ProductCategoryIn,
    current_user: CurrentUser = Depends(require_permission("products.manage")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    from sqlalchemy import select

    from app.modules.audit import service as audit_service
    from app.modules.catalog.models import ProductCategory
    from app.modules.catalog.schemas import ProductCategoryRead

    code = payload.code.upper()
    exists = (
        await db.execute(
            select(ProductCategory.id).where(
                ProductCategory.organization_id == current_user.organization_id, ProductCategory.code == code
            )
        )
    ).first()
    if exists is not None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Esiste già una categoria {code}.")
    category = ProductCategory(organization_id=current_user.organization_id, **{**payload.model_dump(), "code": code})
    db.add(category)
    await db.flush()
    await audit_service.record(
        db, organization_id=current_user.organization_id, actor_user_id=current_user.user_id,
        action="product_category.created", entity_type="product_category", entity_id=str(category.id),
        new_value=payload.model_dump(),
    )
    await db.commit()
    await db.refresh(category)
    return ProductCategoryRead.model_validate(category).model_dump(mode="json")


@router.patch("/categories/{category_id}")
async def update_category(
    category_id: uuid.UUID,
    payload: ProductCategoryUpdate,
    current_user: CurrentUser = Depends(require_permission("products.manage")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    from app.modules.audit import service as audit_service
    from app.modules.catalog.models import ProductCategory
    from app.modules.catalog.schemas import ProductCategoryRead

    category = await db.get(ProductCategory, category_id)
    if category is None or category.organization_id != current_user.organization_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Categoria non trovata.")
    before = ProductCategoryRead.model_validate(category).model_dump(mode="json")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(category, field, value)
    await audit_service.record(
        db, organization_id=current_user.organization_id, actor_user_id=current_user.user_id,
        action="product_category.updated", entity_type="product_category", entity_id=str(category.id),
        previous_value=before, new_value=payload.model_dump(exclude_unset=True),
    )
    await db.commit()
    await db.refresh(category)
    return ProductCategoryRead.model_validate(category).model_dump(mode="json")


@router.get("/me")
async def my_commercial_profile(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict | None:
    """Member overview: current role and history, sponsor, recruit count."""
    from sqlalchemy import func, select

    from app.modules.network.models import NetworkNode

    agent = (
        await db.execute(
            select(AgentProfile).where(
                AgentProfile.organization_id == current_user.organization_id,
                AgentProfile.user_id == current_user.user_id,
            )
        )
    ).scalar_one_or_none()
    if agent is None:
        return None
    node = (
        await db.execute(
            select(NetworkNode).where(NetworkNode.agent_id == agent.id, NetworkNode.effective_to.is_(None))
        )
    ).scalar_one_or_none()
    sponsor = await db.get(AgentProfile, node.direct_parent_agent_id) if node and node.direct_parent_agent_id else None
    direct_count = (
        await db.execute(
            select(func.count()).select_from(NetworkNode).where(
                NetworkNode.direct_parent_agent_id == agent.id, NetworkNode.effective_to.is_(None)
            )
        )
    ).scalar_one()
    role = (
        await service.get_role(db, organization_id=current_user.organization_id, role_id=agent.current_commercial_role_id)
        if agent.current_commercial_role_id
        else None
    )
    return {
        "agent_id": str(agent.id),
        "role": CommercialRoleRead.model_validate(role).model_dump(mode="json") if role else None,
        "role_history": [
            {**h, "id": str(h["id"]), "role_id": str(h["role_id"]),
             "valid_from": h["valid_from"].isoformat(), "valid_to": h["valid_to"].isoformat() if h["valid_to"] else None}
            for h in await service.role_history(db, organization_id=current_user.organization_id, agent_id=agent.id)
        ],
        "sponsor": {"name": sponsor.display_name, "promoter_code": sponsor.promoter_code} if sponsor else None,
        "direct_count": int(direct_count),
    }
