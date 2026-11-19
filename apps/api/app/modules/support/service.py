import logging
import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.foundation.config import get_settings
from app.foundation.email import send_html_email_best_effort
from app.foundation.email_templates import render_email
from app.modules.audit import service as audit_service
from app.modules.customers.models import Company, Customer, CustomerProfile
from app.modules.customers.service import display_name_for
from app.modules.network.models import AgentProfile
from app.modules.notifications import service as notifications_service
from app.modules.organizations import service as organizations_service
from app.modules.support.models import Ticket, TicketMessage
from app.modules.support.schemas import TicketCreate, TicketMessageCreate, TicketStatusUpdate
from app.modules.users.models import User

logger = logging.getLogger(__name__)

ADMIN_REPLY_ROLE = "ADMIN"


class TicketDeletionError(Exception):
    """Raised when deleting a ticket that is not RESOLVED, the only deletable
    status (CLOSED is a separate, later terminal state)."""


def actor_role_for(roles: list[str]) -> str:
    """The role a user acts as on a ticket. Customers and promoters always act
    as themselves; any admin-tier role replies as ADMIN (see rbac/models.py
    SYSTEM_ROLES)."""
    if "CUSTOMER" in roles:
        return "CUSTOMER"
    if "PROMOTER" in roles:
        return "PROMOTER"
    return ADMIN_REPLY_ROLE


async def _display_names_for_users(db: AsyncSession, *, organization_id: uuid.UUID, user_ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    """Display name for a ticket participant: Customer, then AgentProfile, else
    the email (staff have neither)."""
    if not user_ids:
        return {}

    names: dict[uuid.UUID, str] = {}

    customers = (
        await db.execute(
            select(Customer).where(Customer.organization_id == organization_id, Customer.user_id.in_(user_ids))
        )
    ).scalars().all()
    if customers:
        customer_ids = [c.id for c in customers]
        profiles = {
            p.customer_id: p
            for p in (await db.execute(select(CustomerProfile).where(CustomerProfile.customer_id.in_(customer_ids)))).scalars()
        }
        companies = {
            c.customer_id: c
            for c in (await db.execute(select(Company).where(Company.customer_id.in_(customer_ids)))).scalars()
        }
        for c in customers:
            if c.user_id is not None:
                names[c.user_id] = display_name_for(c.kind, profiles.get(c.id), companies.get(c.id))

    remaining = user_ids - names.keys()
    if remaining:
        agents = (
            await db.execute(
                select(AgentProfile).where(
                    AgentProfile.organization_id == organization_id, AgentProfile.user_id.in_(remaining)
                )
            )
        ).scalars().all()
        for a in agents:
            if a.user_id is not None:
                names[a.user_id] = a.display_name

    remaining = user_ids - names.keys()
    if remaining:
        users = (await db.execute(select(User).where(User.id.in_(remaining)))).scalars().all()
        for u in users:
            names[u.id] = u.email

    return names


async def _enrich_tickets(db: AsyncSession, *, organization_id: uuid.UUID, tickets: list[Ticket]) -> list[dict]:
    if not tickets:
        return []
    ticket_ids = [t.id for t in tickets]
    names = await _display_names_for_users(
        db, organization_id=organization_id, user_ids={t.opened_by_user_id for t in tickets}
    )
    stats_stmt = (
        select(TicketMessage.ticket_id, func.count(), func.max(TicketMessage.created_at))
        .where(TicketMessage.ticket_id.in_(ticket_ids))
        .group_by(TicketMessage.ticket_id)
    )
    stats = {row[0]: (row[1], row[2]) for row in (await db.execute(stats_stmt)).all()}

    result = []
    for t in tickets:
        count, last_at = stats.get(t.id, (0, None))
        result.append(
            {
                "id": t.id,
                "organization_id": t.organization_id,
                "opened_by_user_id": t.opened_by_user_id,
                "opened_by_role": t.opened_by_role,
                "opened_by_name": names.get(t.opened_by_user_id),
                "subject": t.subject,
                "category": t.category,
                "status": t.status,
                "contract_id": t.contract_id,
                "created_at": t.created_at,
                "message_count": count,
                "last_message_at": last_at,
            }
        )
    # Most recent activity first (last reply, or creation when none).
    result.sort(key=lambda r: r["last_message_at"] or r["created_at"], reverse=True)
    return result


async def create_ticket(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    actor_role: str,
    payload: TicketCreate,
) -> Ticket:
    ticket = Ticket(
        organization_id=organization_id,
        opened_by_user_id=actor_user_id,
        opened_by_role=actor_role,
        subject=payload.subject,
        category=payload.category,
        status="OPEN",
        contract_id=payload.contract_id,
    )
    db.add(ticket)
    await db.flush()

    db.add(
        TicketMessage(
            ticket_id=ticket.id, author_user_id=actor_user_id, author_role=actor_role, body=payload.message
        )
    )

    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="ticket.created", entity_type="ticket", entity_id=str(ticket.id),
        new_value={"subject": payload.subject, "category": payload.category},
    )
    await notifications_service.notify_roles(
        db, organization_id=organization_id, roles=notifications_service.STAFF_NOTIFY_ROLES,
        type_="TICKET_CREATED", entity_type="ticket", entity_id=ticket.id,
        title=f"Nuovo ticket: {payload.subject}", body=payload.message[:200],
        exclude_user_id=actor_user_id,
    )
    await db.commit()
    await db.refresh(ticket)
    await _send_ticket_created_admin_email(db, organization_id=organization_id, ticket=ticket, message=payload.message)
    return ticket


async def _send_ticket_created_admin_email(
    db: AsyncSession, *, organization_id: uuid.UUID, ticket: Ticket, message: str
) -> None:
    """Best-effort admin email, sent after commit so an SMTP failure never
    blocks ticket creation; the in-app notification is the reliable channel."""
    admin_email = await organizations_service.get_admin_notification_email(db, organization_id=organization_id)
    html = render_email(
        preheader=f"Nuovo ticket: {ticket.subject}",
        heading="Nuovo ticket di supporto",
        body_html=(
            f"<p><strong>Oggetto:</strong> {ticket.subject}</p>"
            f"<p><strong>Categoria:</strong> {ticket.category}</p>"
            f"<p style=\"white-space:pre-wrap;\">{message[:500]}</p>"
        ),
        cta_label="Apri il ticket",
        cta_url=f"{get_settings().public_app_base_url}/admin/support/{ticket.id}",
    )
    send_html_email_best_effort(
        context=f"Ticket-created admin email (ticket={ticket.id})",
        to=admin_email,
        subject=f"[SOSNET] Nuovo ticket: {ticket.subject}",
        html_body=html,
        text_body=f"Nuovo ticket: {ticket.subject}\n\n{message[:500]}",
    )


async def list_tickets(db: AsyncSession, *, organization_id: uuid.UUID) -> list[dict]:
    """Org-wide list; the router gates it on tickets.respond."""
    stmt = select(Ticket).where(Ticket.organization_id == organization_id)
    tickets = (await db.execute(stmt)).scalars().all()
    return await _enrich_tickets(db, organization_id=organization_id, tickets=list(tickets))


async def list_my_tickets(db: AsyncSession, *, organization_id: uuid.UUID, user_id: uuid.UUID) -> list[dict]:
    stmt = select(Ticket).where(
        Ticket.organization_id == organization_id, Ticket.opened_by_user_id == user_id
    )
    tickets = (await db.execute(stmt)).scalars().all()
    return await _enrich_tickets(db, organization_id=organization_id, tickets=list(tickets))


async def get_ticket_detail(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    ticket_id: uuid.UUID,
    requester_user_id: uuid.UUID | None,
    requester_is_staff: bool,
) -> dict | None:
    """Ownership scoping (ABAC), as for network branches: staff
    (tickets.respond) can open any ticket in the org, others only their own."""
    ticket = await db.get(Ticket, ticket_id)
    if ticket is None or ticket.organization_id != organization_id:
        return None
    if not requester_is_staff and ticket.opened_by_user_id != requester_user_id:
        return None

    rows = await _enrich_tickets(db, organization_id=organization_id, tickets=[ticket])
    detail = rows[0]

    messages = (
        await db.execute(
            select(TicketMessage).where(TicketMessage.ticket_id == ticket_id).order_by(TicketMessage.created_at)
        )
    ).scalars().all()
    names = await _display_names_for_users(
        db, organization_id=organization_id, user_ids={m.author_user_id for m in messages}
    )
    detail["messages"] = [
        {
            "id": m.id,
            "ticket_id": m.ticket_id,
            "author_user_id": m.author_user_id,
            "author_role": m.author_role,
            "author_name": names.get(m.author_user_id),
            "body": m.body,
            "created_at": m.created_at,
        }
        for m in messages
    ]
    return detail


async def add_message(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    ticket_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    actor_role: str,
    requester_is_staff: bool,
    payload: TicketMessageCreate,
) -> Ticket | None:
    ticket = await db.get(Ticket, ticket_id)
    if ticket is None or ticket.organization_id != organization_id:
        return None
    if not requester_is_staff and ticket.opened_by_user_id != actor_user_id:
        return None

    db.add(
        TicketMessage(ticket_id=ticket_id, author_user_id=actor_user_id, author_role=actor_role, body=payload.body)
    )
    # A staff reply on an OPEN ticket moves it to IN_PROGRESS so the requester
    # sees it is being handled.
    if requester_is_staff and ticket.status == "OPEN":
        ticket.status = "IN_PROGRESS"

    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="ticket.message_added", entity_type="ticket", entity_id=str(ticket_id),
        new_value={"author_role": actor_role},
    )
    await db.commit()
    await db.refresh(ticket)
    return ticket


async def delete_ticket(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    ticket_id: uuid.UUID,
    actor_user_id: uuid.UUID,
) -> bool | None:
    """Staff-only (tickets.delete, enforced by the router). Returns None when the
    ticket is not in this org (404); raises TicketDeletionError unless RESOLVED
    (400). ticket_messages.ticket_id has no ON DELETE rule, so messages are
    deleted explicitly in the same transaction first."""
    ticket = await db.get(Ticket, ticket_id)
    if ticket is None or ticket.organization_id != organization_id:
        return None
    if ticket.status != "RESOLVED":
        raise TicketDeletionError("Only a resolved ticket can be deleted.")

    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="ticket.deleted", entity_type="ticket", entity_id=str(ticket_id),
        previous_value={"subject": ticket.subject, "category": ticket.category, "status": ticket.status},
    )
    await db.execute(delete(TicketMessage).where(TicketMessage.ticket_id == ticket_id))
    await db.delete(ticket)
    await db.commit()
    return True


async def update_status(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    ticket_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    payload: TicketStatusUpdate,
) -> Ticket | None:
    """Staff-only (tickets.respond, enforced by the router): requesters can say
    a problem is solved, but only staff changes the status formally."""
    ticket = await db.get(Ticket, ticket_id)
    if ticket is None or ticket.organization_id != organization_id:
        return None

    previous_status = ticket.status
    ticket.status = payload.status

    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="ticket.status_changed", entity_type="ticket", entity_id=str(ticket_id),
        previous_value={"status": previous_status}, new_value={"status": payload.status},
    )
    await db.commit()
    await db.refresh(ticket)
    return ticket
