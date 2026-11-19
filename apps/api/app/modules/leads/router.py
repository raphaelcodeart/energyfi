import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.foundation.db import get_db
from app.foundation.deps import CurrentUser, require_permission
from app.modules.leads import service
from app.modules.network.models import AgentProfile

router = APIRouter(prefix="/leads", tags=["leads"])


class LeadIn(BaseModel):
    contact_name: str = Field(min_length=1, max_length=200)
    contact_email: str | None = Field(default=None, max_length=255)
    contact_phone: str | None = Field(default=None, max_length=40)
    customer_id: uuid.UUID | None = None
    product_id: uuid.UUID | None = None
    notes: str = Field(default="", max_length=2000)
    #: Staff only: register the lead on behalf of another member.
    promoter_agent_id: uuid.UUID | None = None


class LeadUpdate(BaseModel):
    status: str | None = None
    customer_id: uuid.UUID | None = None
    product_id: uuid.UUID | None = None
    assigned_agent_id: uuid.UUID | None = None
    notes: str | None = Field(default=None, max_length=2000)
    closed_reason: str | None = Field(default=None, max_length=500)


async def _own_agent(db: AsyncSession, current_user: CurrentUser) -> AgentProfile | None:
    return (
        await db.execute(
            select(AgentProfile).where(
                AgentProfile.organization_id == current_user.organization_id,
                AgentProfile.user_id == current_user.user_id,
            )
        )
    ).scalar_one_or_none()


@router.get("/mine")
async def my_leads(
    current_user: CurrentUser = Depends(require_permission("leads.create")),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    agent = await _own_agent(db, current_user)
    if agent is None:
        return []
    return await service.list_leads(db, organization_id=current_user.organization_id, promoter_agent_id=agent.id)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_lead(
    payload: LeadIn,
    current_user: CurrentUser = Depends(require_permission("leads.create")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    promoter_id = payload.promoter_agent_id
    if promoter_id is None:
        agent = await _own_agent(db, current_user)
        if agent is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Solo un collaboratore può registrare segnalazioni.")
        promoter_id = agent.id
    else:
        from app.modules.rbac.service import get_permission_codes_for_user

        granted = await get_permission_codes_for_user(
            db, user_id=current_user.user_id, organization_id=current_user.organization_id
        )
        if "leads.manage" not in granted:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Puoi registrare segnalazioni solo a tuo nome.")
    try:
        lead = await service.create_lead(
            db, organization_id=current_user.organization_id, promoter_agent_id=promoter_id,
            actor_user_id=current_user.user_id, contact_name=payload.contact_name,
            contact_email=payload.contact_email, contact_phone=payload.contact_phone,
            customer_id=payload.customer_id, product_id=payload.product_id, notes=payload.notes,
        )
    except service.LeadError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return {"id": str(lead.id), "status": lead.status}


@router.get("")
async def list_leads(
    status_filter: str | None = None,
    promoter_agent_id: uuid.UUID | None = None,
    current_user: CurrentUser = Depends(require_permission("leads.manage")),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    return await service.list_leads(
        db, organization_id=current_user.organization_id, promoter_agent_id=promoter_agent_id, status=status_filter
    )


@router.patch("/{lead_id}")
async def update_lead(
    lead_id: uuid.UUID,
    payload: LeadUpdate,
    current_user: CurrentUser = Depends(require_permission("leads.manage")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        lead = await service.update_lead(
            db, organization_id=current_user.organization_id, lead_id=lead_id,
            actor_user_id=current_user.user_id, values=payload.model_dump(exclude_unset=True),
        )
    except service.LeadError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return {"id": str(lead.id), "status": lead.status}
