"""Lead creation, handling and conversion.

`lead_for_new_contract` links a lead to a new contract; `mark_converted`
closes it on activation. The fee is set by the sale's Split Plan.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.foundation.db import utcnow
from app.modules.audit import service as audit_service
from app.modules.leads.models import LEAD_STATUSES, OPEN_LEAD_STATUSES, Lead
from app.modules.network.models import AgentProfile

#: Manual transitions. CONVERTED is set only by contract activation.
MANUAL_TRANSITIONS = {
    "NEW": {"QUALIFIED", "LOST", "EXPIRED"},
    "QUALIFIED": {"NEW", "LOST", "EXPIRED"},
    "LOST": {"NEW"},
    "EXPIRED": {"NEW"},
    "CONVERTED": set(),
}


class LeadError(Exception):
    pass


def _dict(lead: Lead) -> dict:
    return {
        "status": lead.status, "customer_id": str(lead.customer_id) if lead.customer_id else None,
        "product_id": str(lead.product_id) if lead.product_id else None,
        "assigned_agent_id": str(lead.assigned_agent_id) if lead.assigned_agent_id else None,
        "contact_name": lead.contact_name,
    }


async def create_lead(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    promoter_agent_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    contact_name: str,
    contact_email: str | None = None,
    contact_phone: str | None = None,
    customer_id: uuid.UUID | None = None,
    product_id: uuid.UUID | None = None,
    notes: str = "",
) -> Lead:
    promoter = await db.get(AgentProfile, promoter_agent_id)
    if promoter is None or promoter.organization_id != organization_id:
        raise LeadError("Promoter non trovato.")
    if promoter.status != "ACTIVE":
        raise LeadError("Solo un collaboratore attivo può registrare segnalazioni.")
    if not contact_name.strip():
        raise LeadError("Indica il nome della persona segnalata.")
    lead = Lead(
        organization_id=organization_id, promoter_agent_id=promoter_agent_id, customer_id=customer_id,
        product_id=product_id, contact_name=contact_name.strip(), contact_email=contact_email,
        contact_phone=contact_phone, notes=notes or "", status="NEW", created_by_user_id=actor_user_id,
    )
    db.add(lead)
    await db.flush()
    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="lead.created", entity_type="lead", entity_id=str(lead.id), new_value=_dict(lead),
    )
    await db.commit()
    await db.refresh(lead)
    return lead


async def update_lead(
    db: AsyncSession, *, organization_id: uuid.UUID, lead_id: uuid.UUID, actor_user_id: uuid.UUID | None,
    values: dict,
) -> Lead:
    lead = await db.get(Lead, lead_id)
    if lead is None or lead.organization_id != organization_id:
        raise LeadError("Segnalazione non trovata.")
    before = _dict(lead)
    new_status = values.get("status")
    if new_status is not None and new_status != lead.status:
        if new_status not in LEAD_STATUSES or new_status not in MANUAL_TRANSITIONS.get(lead.status, set()):
            raise LeadError(f"Una segnalazione {lead.status} non può passare a {new_status}.")
        lead.status = new_status
    for field in ("customer_id", "product_id", "assigned_agent_id", "notes", "closed_reason",
                  "contact_name", "contact_email", "contact_phone"):
        if field in values and values[field] is not None:
            setattr(lead, field, values[field])
    lead.updated_at = utcnow()
    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="lead.updated", entity_type="lead", entity_id=str(lead.id),
        previous_value=before, new_value=_dict(lead),
    )
    await db.commit()
    await db.refresh(lead)
    return lead


async def list_leads(
    db: AsyncSession, *, organization_id: uuid.UUID, promoter_agent_id: uuid.UUID | None = None,
    status: str | None = None,
) -> list[dict]:
    stmt = select(Lead).where(Lead.organization_id == organization_id)
    if promoter_agent_id is not None:
        stmt = stmt.where(Lead.promoter_agent_id == promoter_agent_id)
    if status:
        stmt = stmt.where(Lead.status == status)
    leads = list((await db.execute(stmt.order_by(Lead.created_at.desc()))).scalars())
    ids = {lead.promoter_agent_id for lead in leads} | {lead.assigned_agent_id for lead in leads if lead.assigned_agent_id}
    names = dict(
        (await db.execute(select(AgentProfile.id, AgentProfile.display_name).where(AgentProfile.id.in_(ids)))).all()
    ) if ids else {}
    return [
        {
            "id": lead.id, "promoter_agent_id": lead.promoter_agent_id,
            "promoter_name": names.get(lead.promoter_agent_id, "—"),
            "customer_id": lead.customer_id, "product_id": lead.product_id,
            "contact_name": lead.contact_name, "contact_email": lead.contact_email,
            "contact_phone": lead.contact_phone, "notes": lead.notes, "status": lead.status,
            "assigned_agent_id": lead.assigned_agent_id,
            "assigned_agent_name": names.get(lead.assigned_agent_id) if lead.assigned_agent_id else None,
            "converted_contract_id": lead.converted_contract_id, "converted_at": lead.converted_at,
            "closed_reason": lead.closed_reason, "created_at": lead.created_at,
        }
        for lead in leads
    ]


async def lead_for_new_contract(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    customer_id: uuid.UUID,
    product_id: uuid.UUID | None,
    lead_id: uuid.UUID | None,
    referral_promoter_id: uuid.UUID | None,
    closing_agent_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
) -> Lead | None:
    """Resolve the lead a contract originates from, in order:

    1. the explicit `lead_id`;
    2. if the customer was referred, a lead created now for the referrer, so
       a Promoter's link keeps its fee without a form being filled;
    3. an open lead for the same customer.

    Does not commit; runs in the contract's transaction."""
    if lead_id is not None:
        lead = await db.get(Lead, lead_id)
        if lead is None or lead.organization_id != organization_id:
            raise LeadError("Segnalazione non trovata.")
        if lead.status not in OPEN_LEAD_STATUSES and lead.status != "CONVERTED":
            raise LeadError("La segnalazione è chiusa e non può generare un contratto.")
        if lead.customer_id is None:
            lead.customer_id = customer_id
        return lead
    if referral_promoter_id is not None:
        lead = Lead(
            organization_id=organization_id, promoter_agent_id=referral_promoter_id, customer_id=customer_id,
            product_id=product_id, contact_name="Cliente dal link del promoter", status="QUALIFIED",
            assigned_agent_id=closing_agent_id, created_by_user_id=actor_user_id,
            notes="Creata automaticamente: il cliente si è registrato dal link di un promoter segnalatore.",
        )
        db.add(lead)
        await db.flush()
        await audit_service.record(
            db, organization_id=organization_id, actor_user_id=actor_user_id,
            action="lead.created", entity_type="lead", entity_id=str(lead.id),
            new_value={**_dict(lead), "automatic": True},
        )
        return lead
    return (
        await db.execute(
            select(Lead)
            .where(
                Lead.organization_id == organization_id,
                Lead.customer_id == customer_id,
                Lead.status.in_(OPEN_LEAD_STATUSES),
            )
            .order_by(Lead.created_at.desc())
        )
    ).scalars().first()


async def mark_converted(db: AsyncSession, *, contract) -> None:
    """Mark the contract's lead converted. Does not commit."""
    if contract.lead_id is None:
        return
    lead = await db.get(Lead, contract.lead_id)
    if lead is None or lead.status == "CONVERTED":
        return
    previous = lead.status
    lead.status = "CONVERTED"
    lead.converted_contract_id = contract.id
    lead.converted_at = utcnow()
    lead.updated_at = utcnow()
    await audit_service.record(
        db, organization_id=contract.organization_id, actor_user_id=None,
        action="lead.converted", entity_type="lead", entity_id=str(lead.id),
        previous_value={"status": previous}, new_value={"status": "CONVERTED", "contract_id": str(contract.id)},
    )
