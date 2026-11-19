import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.foundation.db import utcnow
from app.modules.audit import service as audit_service
from app.modules.network import collaboration_documents

if TYPE_CHECKING:
    # Type annotations only; runtime imports stay function-local to avoid
    # module-level coupling with referral/users.
    from app.modules.customers.models import Customer
    from app.modules.customers.schemas import CustomerCreate
    from app.modules.referral.models import PromoterCode
    from app.modules.users.models import User
from app.modules.network.models import (
    AgentProfile,
    NetworkAssignmentHistory,
    NetworkClosure,
    NetworkEdge,
    NetworkNode,
    NetworkSnapshot,
    NetworkSnapshotNode,
)


class NetworkError(Exception):
    pass


class CycleError(NetworkError):
    pass


class DuplicateApplicationError(NetworkError):
    pass


class RootPromoterConflictError(NetworkError):
    pass


class ContractNotAcceptedError(NetworkError):
    pass


class RecruitedCustomerError(NetworkError):
    pass


class InvalidOtpError(NetworkError):
    pass


# Single source of truth for the collaboration-agreement version, read by both
# the acceptance check and the text served to the frontend.
COLLABORATION_CONTRACT_VERSION = "v1-2026"


async def _get_active_ancestors(
    db: AsyncSession, *, organization_id: uuid.UUID, agent_id: uuid.UUID
) -> list[tuple[uuid.UUID, int]]:
    """Ancestors of agent_id (including itself, depth 0), currently active."""
    stmt = select(NetworkClosure.ancestor_agent_id, NetworkClosure.depth).where(
        NetworkClosure.organization_id == organization_id,
        NetworkClosure.descendant_agent_id == agent_id,
        NetworkClosure.effective_to.is_(None),
    )
    return [(row[0], row[1]) for row in (await db.execute(stmt)).all()]


async def _get_active_descendants(
    db: AsyncSession, *, organization_id: uuid.UUID, agent_id: uuid.UUID
) -> list[tuple[uuid.UUID, int]]:
    """Descendants of agent_id (including itself, depth 0), currently active."""
    stmt = select(NetworkClosure.descendant_agent_id, NetworkClosure.depth).where(
        NetworkClosure.organization_id == organization_id,
        NetworkClosure.ancestor_agent_id == agent_id,
        NetworkClosure.effective_to.is_(None),
    )
    return [(row[0], row[1]) for row in (await db.execute(stmt)).all()]


async def create_agent(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    first_name: str,
    last_name: str,
    promoter_code: str,
    parent_agent_id: uuid.UUID | None,
    joined_at: datetime | None = None,
    actor_user_id: uuid.UUID | None = None,
    current_rank_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    status: str = "ACTIVE",
    commercial_role_id: uuid.UUID | None = None,
) -> AgentProfile:
    """Register a new agent (with no existing subtree) under an optional parent.

    Use move_agent() to relocate an agent that already has descendants. status
    defaults to ACTIVE; the user-facing creation routes pass PENDING_APPROVAL.
    first_name/last_name are separate columns for sorting and filtering;
    display_name is the denormalized "first last" used by most read paths."""
    joined_at = joined_at or utcnow()
    display_name = f"{first_name} {last_name}".strip()

    agent = AgentProfile(
        organization_id=organization_id,
        display_name=display_name,
        first_name=first_name,
        last_name=last_name,
        promoter_code=promoter_code,
        status=status,
        joined_at=joined_at,
        current_rank_id=current_rank_id,
        user_id=user_id,
    )
    db.add(agent)
    await db.flush()

    if parent_agent_id is not None:
        parent_node = (
            await db.execute(
                select(NetworkNode).where(
                    NetworkNode.organization_id == organization_id,
                    NetworkNode.agent_id == parent_agent_id,
                    NetworkNode.effective_to.is_(None),
                )
            )
        ).scalar_one_or_none()
        if parent_node is None:
            raise NetworkError("Parent agent has no active network node")

    node = NetworkNode(
        organization_id=organization_id,
        agent_id=agent.id,
        direct_parent_agent_id=parent_agent_id,
        status="ACTIVE",
        effective_from=joined_at,
    )
    db.add(node)

    # Reflexive closure row: every agent is its own ancestor at depth 0.
    db.add(
        NetworkClosure(
            organization_id=organization_id,
            ancestor_agent_id=agent.id,
            descendant_agent_id=agent.id,
            depth=0,
            effective_from=joined_at,
        )
    )

    if parent_agent_id is not None:
        db.add(
            NetworkEdge(
                organization_id=organization_id,
                parent_agent_id=parent_agent_id,
                child_agent_id=agent.id,
                effective_from=joined_at,
            )
        )
        ancestors = await _get_active_ancestors(db, organization_id=organization_id, agent_id=parent_agent_id)
        for ancestor_id, depth in ancestors:
            db.add(
                NetworkClosure(
                    organization_id=organization_id,
                    ancestor_agent_id=ancestor_id,
                    descendant_agent_id=agent.id,
                    depth=depth + 1,
                    effective_from=joined_at,
                )
            )

    await audit_service.record(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action="network.agent_created",
        entity_type="agent_profile",
        entity_id=str(agent.id),
        new_value={"parent_agent_id": str(parent_agent_id) if parent_agent_id else None},
    )
    # The commercial role is assigned with the person, in the same transaction:
    # the requested role, or the organization's default.
    from app.modules.commercial import service as commercial_service

    await commercial_service.ensure_role_for_agent(
        db, organization_id=organization_id, agent=agent, role_id=commercial_role_id
    )
    await db.commit()
    await db.refresh(agent)
    return agent


async def get_own_agent_profile(
    db: AsyncSession, *, organization_id: uuid.UUID, user_id: uuid.UUID
) -> AgentProfile | None:
    """The caller's own AgentProfile, independent of RBAC permissions: a plain
    CUSTOMER uses it to follow their 'Lavora con noi' application. GET
    /network/mine is the permission-gated branch view."""
    stmt = select(AgentProfile).where(
        AgentProfile.organization_id == organization_id, AgentProfile.user_id == user_id
    )
    return (await db.execute(stmt)).scalar_one_or_none()


def _generate_promoter_code(display_name: str) -> str:
    """Human-readable code (initials + random suffix) for self-service
    applications, where nobody types a code in. Uniqueness is enforced by the
    uq_sn_invite_codes_agent constraint, not checked here."""
    import re
    import secrets

    slug = re.sub(r"[^A-Z0-9]", "", display_name.upper())[:6] or "PROMO"
    return f"{slug}-{secrets.token_hex(3).upper()}"


AUTO_ACTIVATION_RANK_CODE = "SP1"


async def _get_current_rank_id(db: AsyncSession, *, organization_id: uuid.UUID, code: str) -> uuid.UUID | None:
    """Current version (valid_to IS NULL) of a legacy rank code."""
    from app.modules.commissions.models import Rank

    stmt = select(Rank.id).where(
        Rank.organization_id == organization_id, Rank.code == code, Rank.valid_to.is_(None)
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def _resolve_referring_agent_id(db: AsyncSession, *, organization_id: uuid.UUID, user_id: uuid.UUID) -> uuid.UUID | None:
    """Agent whose referral link the user signed up through, if any.

    Registration is invite-only, so an attribution normally exists; None covers
    customers created outside that flow. Lets a self-service application land
    under the actual sponsor instead of becoming a root."""
    from app.modules.customers.models import Customer
    from app.modules.referral.models import CustomerAttribution, PromoterCode

    stmt = (
        select(PromoterCode.agent_id)
        .select_from(CustomerAttribution)
        .join(Customer, Customer.id == CustomerAttribution.customer_id)
        .join(PromoterCode, PromoterCode.id == CustomerAttribution.promoter_code_id)
        .where(CustomerAttribution.organization_id == organization_id, Customer.user_id == user_id)
        .order_by(CustomerAttribution.attributed_at.desc())
        .limit(1)
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def apply_as_promoter(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    first_name: str,
    last_name: str,
    accept_contract: bool,
    otp_code: str,
    accepted_documents: dict[str, str] | None = None,
) -> AgentProfile:
    """Self-service 'Lavora con noi': an existing CUSTOMER becomes a PROMOTER.

    Requires the collaboration-agreement acceptance and a valid OTP (sent by
    POST /network/agents/apply/request-otp) as proof that the account holder
    agreed; both are checked before any branching.

    The applicant is activated immediately, with the legacy SP1 rank, under the
    promoter who referred them, and receives the PROMOTER role. Blacklisted or
    SUSPENDED agents go back to PENDING_APPROVAL instead: suspension is an
    admin decision the agent must not undo alone. TERMINATED agents are
    reactivated automatically.

    At most one AgentProfile exists per user, so a reapplication resets the
    existing row instead of creating a second profile and a disconnected
    network node."""
    from app.modules.auth import service as auth_service
    from app.modules.rbac import service as rbac_service
    from app.modules.users.models import User

    if not accept_contract:
        raise ContractNotAcceptedError("Devi accettare il contratto di collaborazione")

    # Every required document must be accepted at the exact version shown to
    # the applicant, so the record says which text was agreed to. A stale
    # version (text updated while the page was open) is refused.
    required = collaboration_documents.required_versions()
    submitted = accepted_documents or {}
    missing = [
        doc.title
        for doc in collaboration_documents.COLLABORATION_DOCUMENTS
        if submitted.get(doc.key) != doc.version
    ]
    if missing:
        raise ContractNotAcceptedError(
            "Devi leggere e accettare: " + "; ".join(missing)
        )

    user = await db.get(User, user_id)
    if user is None:
        raise NetworkError("User not found")
    otp_ok = await auth_service.verify_otp(
        db, user_id=user_id, purpose=auth_service.PROMOTER_APPLICATION_OTP_PURPOSE, code=otp_code
    )
    if not otp_ok:
        raise InvalidOtpError("Invalid or expired confirmation code")

    collaboration_accepted_at = utcnow()
    accepted_documents_record = {
        key: {"version": version, "accepted_at": collaboration_accepted_at.isoformat()}
        for key, version in required.items()
    }

    existing = await get_own_agent_profile(db, organization_id=organization_id, user_id=user_id)
    referring_agent_id = await _resolve_referring_agent_id(db, organization_id=organization_id, user_id=user_id)
    rank_id = await _get_current_rank_id(db, organization_id=organization_id, code=AUTO_ACTIVATION_RANK_CODE)

    if existing is not None:
        if existing.status in ("PENDING_APPROVAL", "ACTIVE"):
            raise DuplicateApplicationError(f"Existing application/profile is {existing.status}")

        # Blacklisted and SUSPENDED agents need manual approval: update_agent()
        # treats SUSPENDED as a real deactivation, and self-service must not
        # override it. TERMINATED is intentionally self-reactivable.
        previous_status = existing.status
        if existing.is_blacklisted or existing.status == "SUSPENDED":
            existing.status = "PENDING_APPROVAL"
            existing.first_name = first_name
            existing.last_name = last_name
            existing.display_name = f"{first_name} {last_name}".strip()
            existing.approved_by_user_id = None
            existing.approved_at = None
            existing.rejection_reason = None
            existing.collaboration_contract_version = COLLABORATION_CONTRACT_VERSION
            existing.collaboration_accepted_at = collaboration_accepted_at
            existing.collaboration_otp_verified_at = collaboration_accepted_at
            existing.collaboration_accepted_documents = accepted_documents_record
            await audit_service.record(
                db, organization_id=organization_id, actor_user_id=user_id,
                action="network.agent_reapplied", entity_type="agent_profile", entity_id=str(existing.id),
                previous_value={"status": previous_status}, new_value={"status": "PENDING_APPROVAL"},
            )
            await db.commit()
            await db.refresh(existing)
            return existing

        existing.status = "ACTIVE"
        existing.first_name = first_name
        existing.last_name = last_name
        existing.display_name = f"{first_name} {last_name}".strip()
        existing.current_rank_id = rank_id
        existing.approved_by_user_id = None
        existing.approved_at = utcnow()
        existing.rejection_reason = None
        existing.collaboration_contract_version = COLLABORATION_CONTRACT_VERSION
        existing.collaboration_accepted_at = collaboration_accepted_at
        existing.collaboration_otp_verified_at = collaboration_accepted_at
        existing.collaboration_accepted_documents = accepted_documents_record

        current_parent_id = (
            await db.execute(
                select(NetworkNode.direct_parent_agent_id).where(
                    NetworkNode.organization_id == organization_id,
                    NetworkNode.agent_id == existing.id,
                    NetworkNode.effective_to.is_(None),
                )
            )
        ).scalar_one_or_none()
        if referring_agent_id is not None and referring_agent_id != current_parent_id:
            await move_agent(
                db, organization_id=organization_id, agent_id=existing.id,
                new_parent_agent_id=referring_agent_id, requested_by=user_id, approved_by=user_id,
                reason="Riattivazione automatica 'lavora con noi': sponsor dal link di invito originale",
            )

        await rbac_service.assign_role(db, user_id=user_id, organization_id=organization_id, role_code="PROMOTER")
        await audit_service.record(
            db, organization_id=organization_id, actor_user_id=user_id,
            action="network.agent_auto_activated", entity_type="agent_profile", entity_id=str(existing.id),
            previous_value={"status": "TERMINATED"}, new_value={"status": "ACTIVE"},
        )
        await db.commit()
        await db.refresh(existing)
        return existing

    agent = await create_agent(
        db,
        organization_id=organization_id,
        first_name=first_name,
        last_name=last_name,
        promoter_code=_generate_promoter_code(f"{first_name} {last_name}"),
        parent_agent_id=referring_agent_id,
        actor_user_id=user_id,
        user_id=user_id,
        current_rank_id=rank_id,
        status="ACTIVE",
    )
    agent.collaboration_contract_version = COLLABORATION_CONTRACT_VERSION
    agent.collaboration_accepted_at = collaboration_accepted_at
    agent.collaboration_otp_verified_at = collaboration_accepted_at
    agent.collaboration_accepted_documents = accepted_documents_record
    await rbac_service.assign_role(db, user_id=user_id, organization_id=organization_id, role_code="PROMOTER")
    await db.commit()
    await db.refresh(agent)
    return agent


async def ensure_customer_side(db: AsyncSession, *, organization_id: uuid.UUID, agent: AgentProfile) -> bool:
    """A promoter is also a customer: give the agent's login the CUSTOMER role
    and a private customer record named after the agent, when missing, so
    they can switch between the two areas. Idempotent; does not commit.
    Returns whether anything was added."""
    from app.modules.customers.models import Customer, CustomerProfile
    from app.modules.rbac import service as rbac_service
    from app.modules.users.models import User

    if agent.user_id is None:
        return False
    user = await db.get(User, agent.user_id)
    if user is None:
        return False
    changed = False
    roles = await rbac_service.get_roles_for_user(db, user_id=user.id, organization_id=organization_id)
    if "CUSTOMER" not in roles:
        await rbac_service.assign_role(db, user_id=user.id, organization_id=organization_id, role_code="CUSTOMER")
        changed = True
    customer = (
        await db.execute(select(Customer).where(Customer.organization_id == organization_id, Customer.user_id == user.id))
    ).scalars().first()
    if customer is None:
        customer = Customer(organization_id=organization_id, kind="PRIVATE", email=user.email, user_id=user.id)
        db.add(customer)
        await db.flush()
        db.add(CustomerProfile(
            customer_id=customer.id,
            first_name=agent.first_name or agent.display_name,
            last_name=agent.last_name or "",
        ))
        changed = True
    if await _attribute_to_sponsor(db, organization_id=organization_id, agent=agent, customer_id=customer.id):
        changed = True
    return changed


async def _attribute_to_sponsor(
    db: AsyncSession, *, organization_id: uuid.UUID, agent: AgentProfile, customer_id: uuid.UUID
) -> bool:
    """A promoter's own contracts need a referrer, as for any customer: their
    sponsor, as if they had joined as that sponsor's customer, or themselves
    at the root of the network. No-op if the customer already has one."""
    from app.modules.referral import service as referral_service
    from app.modules.referral.models import CustomerAttribution

    attributed = (await db.execute(select(CustomerAttribution.id).where(
        CustomerAttribution.organization_id == organization_id, CustomerAttribution.customer_id == customer_id,
    ))).first()
    if attributed is not None:
        return False
    sponsor_id = (await db.execute(select(NetworkNode.direct_parent_agent_id).where(
        NetworkNode.agent_id == agent.id, NetworkNode.effective_to.is_(None),
    ))).scalar_one_or_none()
    code = await referral_service.get_or_create_promoter_code(
        db, organization_id=organization_id, agent_id=sponsor_id or agent.id
    )
    db.add(CustomerAttribution(
        organization_id=organization_id, customer_id=customer_id, promoter_code_id=code.id,
        referral_session_id=None, attributed_at=utcnow(),
    ))
    await db.flush()
    return True


async def create_root_promoter_with_login(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    first_name: str,
    last_name: str,
    email: str,
    promoter_code: str | None,
    actor_user_id: uuid.UUID,
) -> tuple[AgentProfile, "User", "PromoterCode", str]:
    """Admin-only creation of a new parentless network root, with login,
    ACTIVE agent profile and referral link in one step.

    Registration is otherwise invite-only (a referral code always implies a
    parent), so this is the only way to start a new root."""
    from app.foundation.config import get_settings
    from app.foundation.security import hash_password
    from app.modules.rbac import service as rbac_service
    from app.modules.referral.models import PromoterCode
    from app.modules.users.models import User

    existing_user = (
        await db.execute(
            select(User).where(
                User.organization_id == organization_id, func.lower(User.email) == email.lower()
            )
        )
    ).scalar_one_or_none()
    if existing_user is not None:
        raise RootPromoterConflictError(f"An account with email '{email}' already exists")

    code = promoter_code or _generate_promoter_code(f"{first_name} {last_name}")
    existing_code = (
        await db.execute(
            select(AgentProfile).where(
                AgentProfile.organization_id == organization_id, AgentProfile.promoter_code == code
            )
        )
    ).scalar_one_or_none()
    if existing_code is not None:
        raise RootPromoterConflictError(f"Promoter code '{code}' is already in use")

    temporary_password = _generate_temp_password()
    user = User(
        organization_id=organization_id,
        email=email,
        password_hash=hash_password(temporary_password),
        status="ACTIVE",
    )
    db.add(user)
    await db.flush()
    await rbac_service.assign_role(db, user_id=user.id, organization_id=organization_id, role_code="PROMOTER")

    agent = await create_agent(
        db,
        organization_id=organization_id,
        first_name=first_name,
        last_name=last_name,
        promoter_code=code,
        parent_agent_id=None,
        actor_user_id=actor_user_id,
        user_id=user.id,
        status="ACTIVE",
    )

    settings = get_settings()
    promoter_code_row = PromoterCode(
        organization_id=organization_id,
        agent_id=agent.id,
        code=code,
        personal_link=f"{settings.public_app_base_url}/r/{code}?org={organization_id}",
        status="ACTIVE",
        valid_from=utcnow(),
    )
    db.add(promoter_code_row)
    await audit_service.record(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action="network.root_promoter_created",
        entity_type="agent_profile",
        entity_id=str(agent.id),
        new_value={"display_name": agent.display_name, "promoter_code": code, "email": email},
    )
    await ensure_customer_side(db, organization_id=organization_id, agent=agent)
    await db.commit()
    await db.refresh(agent)
    await db.refresh(promoter_code_row)
    return agent, user, promoter_code_row, temporary_password


async def create_recruited_customer(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    promoter_user_id: uuid.UUID,
    payload: "CustomerCreate",
    actor_user_id: uuid.UUID,
) -> "Customer":
    """A promoter registers a new customer directly (CRM-style).

    The customer is attributed to the promoter exactly as with a referral-link
    registration. promoter_user_id is always the caller (set by the router),
    so a promoter can only attribute customers to themselves.

    The customer gets a login immediately (random, never-revealed password) so
    contracts and documents can be handled right away; first access happens
    through the set-your-password invite email."""
    promoter_agent = await get_own_agent_profile(db, organization_id=organization_id, user_id=promoter_user_id)
    if promoter_agent is None or promoter_agent.status != "ACTIVE":
        raise RecruitedCustomerError("Solo un promoter attivo può registrare nuovi clienti.")
    return await _register_customer_with_account(
        db, organization_id=organization_id, promoter_agent=promoter_agent, payload=payload,
        actor_user_id=actor_user_id, audit_action="customer.recruited_by_promoter",
        invited_by_display_name=promoter_agent.display_name,
    )


async def create_customer_with_account_by_staff(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    promoter_agent_id: uuid.UUID | None,
    payload: "CustomerCreate",
    actor_user_id: uuid.UUID,
) -> "Customer":
    """Admin "Nuovo cliente": personal data, a login and the set-your-password
    invite, so the customer can pay the pratica opened for them. The customer
    is attributed to the chosen promoter, or is a direct company customer when
    none is given."""
    promoter_agent = None
    if promoter_agent_id is not None:
        promoter_agent = await db.get(AgentProfile, promoter_agent_id)
        if (
            promoter_agent is None
            or promoter_agent.organization_id != organization_id
            or promoter_agent.status != "ACTIVE"
        ):
            raise RecruitedCustomerError("Promoter non valido o non attivo.")
    return await _register_customer_with_account(
        db, organization_id=organization_id, promoter_agent=promoter_agent, payload=payload,
        actor_user_id=actor_user_id, audit_action="customer.created_with_account_by_staff",
        invited_by_display_name="SOSNET",
    )


async def _register_customer_with_account(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    promoter_agent: "AgentProfile | None",
    payload: "CustomerCreate",
    actor_user_id: uuid.UUID,
    audit_action: str,
    invited_by_display_name: str,
) -> "Customer":
    from app.modules.customers import service as customers_service

    await _ensure_email_free(db, organization_id=organization_id, email=payload.email)
    try:
        customer = await customers_service.create_customer(
            db, organization_id=organization_id, payload=payload, actor_user_id=actor_user_id, commit=False
        )
    except customers_service.CustomerValidationError as exc:
        raise RecruitedCustomerError(str(exc)) from exc
    return await _attach_login_and_invite(
        db, organization_id=organization_id, customer=customer, promoter_agent=promoter_agent,
        actor_user_id=actor_user_id, audit_action=audit_action, invited_by_display_name=invited_by_display_name,
    )


async def create_login_for_existing_customer(
    db: AsyncSession, *, organization_id: uuid.UUID, customer_id: uuid.UUID, actor_user_id: uuid.UUID
) -> "Customer":
    """Give a login to a customer registered as personal data only, using the
    email on file, and send the set-your-password invite. Promoter attribution
    is left unchanged."""
    from app.modules.customers.models import Customer

    customer = await db.get(Customer, customer_id)
    if customer is None or customer.organization_id != organization_id:
        raise RecruitedCustomerError("Cliente non trovato.")
    if customer.user_id is not None:
        raise RecruitedCustomerError("Questo cliente ha già un accesso.")
    await _ensure_email_free(db, organization_id=organization_id, email=customer.email)
    return await _attach_login_and_invite(
        db, organization_id=organization_id, customer=customer, promoter_agent=None,
        actor_user_id=actor_user_id, audit_action="customer.login_created_by_staff",
        invited_by_display_name="SOSNET",
    )


async def _ensure_email_free(db: AsyncSession, *, organization_id: uuid.UUID, email: str) -> None:
    from app.modules.users.models import User

    existing_user = (
        await db.execute(
            select(User).where(User.organization_id == organization_id, func.lower(User.email) == email.lower())
        )
    ).scalar_one_or_none()
    if existing_user is not None:
        raise RecruitedCustomerError(f"Esiste già un account con l'email '{email}'.")


async def _attach_login_and_invite(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    customer: "Customer",
    promoter_agent: "AgentProfile | None",
    actor_user_id: uuid.UUID,
    audit_action: str,
    invited_by_display_name: str,
) -> "Customer":
    """Create the login (random, never-revealed password), CUSTOMER role and
    optional promoter attribution, then send the invite after commit."""
    from app.foundation.security import hash_password
    from app.modules.auth import service as auth_service
    from app.modules.rbac import service as rbac_service
    from app.modules.referral import service as referral_service
    from app.modules.referral.models import CustomerAttribution
    from app.modules.users.models import User

    user = User(
        organization_id=organization_id, email=customer.email,
        password_hash=hash_password(_generate_temp_password()), status="ACTIVE",
    )
    db.add(user)
    await db.flush()
    await rbac_service.assign_role(db, user_id=user.id, organization_id=organization_id, role_code="CUSTOMER")
    customer.user_id = user.id

    if promoter_agent is not None:
        promoter_code = await referral_service.get_or_create_promoter_code(
            db, organization_id=organization_id, agent_id=promoter_agent.id
        )
        db.add(
            CustomerAttribution(
                organization_id=organization_id, customer_id=customer.id,
                promoter_code_id=promoter_code.id, referral_session_id=None, attributed_at=utcnow(),
            )
        )
    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action=audit_action, entity_type="customer", entity_id=str(customer.id),
        new_value={
            "promoter_agent_id": str(promoter_agent.id) if promoter_agent else None,
            "email": customer.email,
        },
    )
    await db.commit()
    await db.refresh(customer)
    await db.refresh(user)

    await auth_service.send_account_invite_email(db, user=user, invited_by_display_name=invited_by_display_name)
    return customer


async def list_recruited_customers(
    db: AsyncSession, *, organization_id: uuid.UUID, promoter_user_id: uuid.UUID
) -> list[dict]:
    """Customers currently attributed to the promoter ("Miei Clienti").

    Uses the current attribution, so customers reassigned by an admin drop out.
    Flat, single-level list, unlike the multi-level branch view."""
    from app.modules.customers import service as customers_service
    from app.modules.referral import service as referral_service
    from app.modules.referral.models import CustomerAttribution, PromoterCode

    promoter_agent = await get_own_agent_profile(db, organization_id=organization_id, user_id=promoter_user_id)
    if promoter_agent is None:
        return []

    stmt = (
        select(CustomerAttribution.customer_id)
        .join(PromoterCode, PromoterCode.id == CustomerAttribution.promoter_code_id)
        .where(CustomerAttribution.organization_id == organization_id, PromoterCode.agent_id == promoter_agent.id)
        .distinct()
    )
    candidate_ids = {row[0] for row in (await db.execute(stmt)).all()}
    if not candidate_ids:
        return []

    current_ids = set()
    for customer_id in candidate_ids:
        attribution = await referral_service.get_current_attribution(
            db, organization_id=organization_id, customer_id=customer_id
        )
        if attribution is not None:
            promoter_code = await db.get(PromoterCode, attribution.promoter_code_id)
            if promoter_code is not None and promoter_code.agent_id == promoter_agent.id:
                current_ids.add(customer_id)

    if not current_ids:
        return []
    return await customers_service.list_customers(db, organization_id=organization_id, customer_ids=current_ids)


def _generate_temp_password() -> str:
    import secrets
    import string

    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(16)) + "!Aa1"


async def get_active_node(
    db: AsyncSession, *, organization_id: uuid.UUID, agent_id: uuid.UUID
) -> NetworkNode | None:
    """The agent's open network_nodes row (effective_to IS NULL), or None if the
    agent was never placed in the tree. Public so callers can check the current
    parent before deciding whether a move_agent() is needed."""
    return (
        await db.execute(
            select(NetworkNode).where(
                NetworkNode.organization_id == organization_id,
                NetworkNode.agent_id == agent_id,
                NetworkNode.effective_to.is_(None),
            )
        )
    ).scalar_one_or_none()


async def resolve_nearest_active_agent(
    db: AsyncSession, *, organization_id: uuid.UUID, agent_id: uuid.UUID
) -> AgentProfile | None:
    """The agent if ACTIVE, otherwise the closest ACTIVE ancestor; None if
    nobody in the upline is active or the agent is not in the tree.

    A customer must not be blocked because their promoter was deactivated:
    create_contract() rejects non-ACTIVE agents (a contract that pays nobody is
    not allowed), so the contract goes to the nearest active upline member,
    keeping it inside the branch that built the relationship.

    Closure rows with effective_to IS NULL mean the edge is current, not that
    the person is active, so agent status is filtered separately."""
    ancestors = await _get_active_ancestors(db, organization_id=organization_id, agent_id=agent_id)
    if not ancestors:
        # Not in the tree: the agent can still be usable on their own.
        agent = await db.get(AgentProfile, agent_id)
        if agent is not None and agent.organization_id == organization_id and agent.status == "ACTIVE":
            return agent
        return None

    by_depth = sorted(ancestors, key=lambda row: row[1])
    profiles = {
        profile.id: profile
        for profile in (
            await db.execute(
                select(AgentProfile).where(
                    AgentProfile.organization_id == organization_id,
                    AgentProfile.id.in_([ancestor_id for ancestor_id, _ in by_depth]),
                )
            )
        ).scalars()
    }
    for ancestor_id, _depth in by_depth:
        profile = profiles.get(ancestor_id)
        if profile is not None and profile.status == "ACTIVE":
            return profile
    return None


async def move_agent(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    agent_id: uuid.UUID,
    new_parent_agent_id: uuid.UUID | None,
    requested_by: uuid.UUID,
    approved_by: uuid.UUID | None,
    reason: str,
    effective_at: datetime | None = None,
) -> None:
    """Move agent_id and its whole subtree under new_parent_agent_id.

    Single transaction: closes the old node/edge/closure rows, opens new ones
    for the subtree, writes assignment history and audit. Network snapshots of
    activated contracts are never touched; they keep the chain frozen at
    activation (see database-model.md).
    """
    effective_at = effective_at or utcnow()

    if new_parent_agent_id == agent_id:
        raise CycleError("An agent cannot be its own parent")

    node = (
        await db.execute(
            select(NetworkNode).where(
                NetworkNode.organization_id == organization_id,
                NetworkNode.agent_id == agent_id,
                NetworkNode.effective_to.is_(None),
            )
        )
    ).scalar_one_or_none()
    if node is None:
        raise NetworkError("Agent has no active network node")

    old_parent_agent_id = node.direct_parent_agent_id

    if new_parent_agent_id is not None:
        new_parent_ancestors = await _get_active_ancestors(
            db, organization_id=organization_id, agent_id=new_parent_agent_id
        )
        if any(ancestor_id == agent_id for ancestor_id, _ in new_parent_ancestors):
            raise CycleError("Move would create a cycle: new parent is a descendant of the agent")

    subtree = await _get_active_descendants(db, organization_id=organization_id, agent_id=agent_id)
    subtree_ids = {a for a, _ in subtree}

    # Paths internal to the subtree stay valid across the move.
    internal_rows = [
        row
        for row in (
            await db.execute(
                select(
                    NetworkClosure.ancestor_agent_id,
                    NetworkClosure.descendant_agent_id,
                    NetworkClosure.depth,
                ).where(
                    NetworkClosure.organization_id == organization_id,
                    NetworkClosure.ancestor_agent_id.in_(subtree_ids),
                    NetworkClosure.descendant_agent_id.in_(subtree_ids),
                    NetworkClosure.effective_to.is_(None),
                )
            )
        ).all()
    ]

    # Close every closure row linking an outside ancestor to the subtree.
    old_external_rows = (
        await db.execute(
            select(NetworkClosure).where(
                NetworkClosure.organization_id == organization_id,
                NetworkClosure.descendant_agent_id.in_(subtree_ids),
                NetworkClosure.ancestor_agent_id.not_in(subtree_ids),
                NetworkClosure.effective_to.is_(None),
            )
        )
    ).scalars().all()
    for row in old_external_rows:
        row.effective_to = effective_at

    if old_parent_agent_id is not None:
        old_edge = (
            await db.execute(
                select(NetworkEdge).where(
                    NetworkEdge.organization_id == organization_id,
                    NetworkEdge.parent_agent_id == old_parent_agent_id,
                    NetworkEdge.child_agent_id == agent_id,
                    NetworkEdge.effective_to.is_(None),
                )
            )
        ).scalar_one_or_none()
        if old_edge is not None:
            old_edge.effective_to = effective_at

    node.effective_to = effective_at
    new_node = NetworkNode(
        organization_id=organization_id,
        agent_id=agent_id,
        direct_parent_agent_id=new_parent_agent_id,
        status=node.status,
        effective_from=effective_at,
    )
    db.add(new_node)

    if new_parent_agent_id is not None:
        db.add(
            NetworkEdge(
                organization_id=organization_id,
                parent_agent_id=new_parent_agent_id,
                child_agent_id=agent_id,
                effective_from=effective_at,
            )
        )
        new_ancestors = await _get_active_ancestors(
            db, organization_id=organization_id, agent_id=new_parent_agent_id
        )
        # New paths: each new ancestor to each subtree member, depths composed.
        for ancestor_id, ancestor_depth in new_ancestors:
            for sub_ancestor, sub_descendant, sub_depth in internal_rows:
                if sub_ancestor != agent_id:
                    continue  # only need paths rooted at the moving agent itself
                db.add(
                    NetworkClosure(
                        organization_id=organization_id,
                        ancestor_agent_id=ancestor_id,
                        descendant_agent_id=sub_descendant,
                        depth=ancestor_depth + 1 + sub_depth,
                        effective_from=effective_at,
                    )
                )

    db.add(
        NetworkAssignmentHistory(
            organization_id=organization_id,
            agent_id=agent_id,
            old_parent_agent_id=old_parent_agent_id,
            new_parent_agent_id=new_parent_agent_id,
            requested_by=requested_by,
            approved_by=approved_by,
            reason=reason,
            effective_at=effective_at,
        )
    )

    await audit_service.record(
        db,
        organization_id=organization_id,
        actor_user_id=requested_by,
        action="network.agent_moved",
        entity_type="agent_profile",
        entity_id=str(agent_id),
        previous_value={"parent_agent_id": str(old_parent_agent_id) if old_parent_agent_id else None},
        new_value={"parent_agent_id": str(new_parent_agent_id) if new_parent_agent_id else None},
        reason=reason,
    )
    await db.commit()


_AGENT_FIELDS = (
    "id", "display_name", "promoter_code", "status", "current_rank_id", "joined_at", "rank_code",
    "direct_parent_agent_id", "photo_url", "rejection_reason", "email", "is_blacklisted", "first_name",
    "last_name", "user_id", "collaboration_accepted_at", "collaboration_accepted_documents", "email_verified",
    "privacy_accepted", "user_status", "commercial_role_id", "role_code", "role_name",
)


def _agent_list_select(organization_id: uuid.UUID):
    from app.modules.commercial.models import CommercialRole
    from app.modules.commissions.models import Rank
    from app.modules.users.models import User

    return (
        select(
            AgentProfile.id,
            AgentProfile.display_name,
            AgentProfile.promoter_code,
            AgentProfile.status,
            AgentProfile.current_rank_id,
            AgentProfile.joined_at,
            Rank.code,
            NetworkNode.direct_parent_agent_id,
            AgentProfile.photo_url,
            AgentProfile.rejection_reason,
            User.email,
            AgentProfile.is_blacklisted,
            AgentProfile.first_name,
            AgentProfile.last_name,
            AgentProfile.user_id,
            AgentProfile.collaboration_accepted_at,
            AgentProfile.collaboration_accepted_documents,
            User.email_verified_at,
            User.privacy_accepted_at,
            User.status,
            CommercialRole.id,
            CommercialRole.code,
            CommercialRole.name,
        )
        .join(Rank, Rank.id == AgentProfile.current_rank_id, isouter=True)
        .join(CommercialRole, CommercialRole.id == AgentProfile.current_commercial_role_id, isouter=True)
        .join(
            NetworkNode,
            (NetworkNode.agent_id == AgentProfile.id) & (NetworkNode.effective_to.is_(None)),
            isouter=True,
        )
        # Outer join: an admin-suggested agent may have no login (email=None).
        .join(User, User.id == AgentProfile.user_id, isouter=True)
        .where(AgentProfile.organization_id == organization_id)
    )


def _agent_row(r) -> dict:
    out = dict(zip(_AGENT_FIELDS, r[:len(_AGENT_FIELDS)], strict=True))
    out["collaboration_accepted_documents"] = out["collaboration_accepted_documents"] or {}
    out["email_verified"] = out["email_verified"] is not None
    out["privacy_accepted"] = out["privacy_accepted"] is not None
    return out


async def list_agents(db: AsyncSession, *, organization_id: uuid.UUID) -> list[dict]:
    """Every agent at once. Kept for small organizations and scripts: the
    admin screens use list_agents_page / lookup_agents, which stay fast with
    tens of thousands of people."""
    stmt = _agent_list_select(organization_id).order_by(AgentProfile.joined_at.desc())
    return [_agent_row(r) for r in (await db.execute(stmt)).all()]


AGENT_SORTS = ("recent", "oldest", "name", "code")
MAX_AGENT_PAGE_SIZE = 200


def _agent_filters(stmt, *, organization_id: uuid.UUID, search: str | None, status: str | None,
                   parent_id: uuid.UUID | None, blacklisted: bool | None):
    from app.modules.mamify.models import MamifyMember
    from app.modules.users.models import User

    if status and status != "ALL":
        stmt = stmt.where(AgentProfile.status == status)
    if blacklisted is not None:
        stmt = stmt.where(AgentProfile.is_blacklisted.is_(blacklisted))
    if parent_id is not None:
        stmt = stmt.where(NetworkNode.direct_parent_agent_id == parent_id)
    q = (search or "").strip()
    if q:
        like = f"%{q.replace('%', '').replace('_', ' ')}%"
        # Uncorrelated on purpose: one scan of the Mamify emails, not one per row.
        mamify_email = select(MamifyMember.agent_id).where(
            MamifyMember.organization_id == organization_id, MamifyMember.email.ilike(like))
        stmt = stmt.where(or_(
            AgentProfile.display_name.ilike(like),
            AgentProfile.promoter_code.ilike(like),
            func.concat(AgentProfile.first_name, " ", AgentProfile.last_name).ilike(like),
            User.email.ilike(like),
            AgentProfile.id.in_(mamify_email),
        ))
    return stmt


async def list_agents_page(
    db: AsyncSession, *, organization_id: uuid.UUID, page: int = 1, page_size: int = 25,
    search: str | None = None, status: str | None = None, sort: str = "recent",
    parent_id: uuid.UUID | None = None, blacklisted: bool | None = None,
) -> dict:
    """One page of the collaborator registry, filtered on the server, with
    for each row its sponsor, how many people it brought in and how big its
    network is. `counts` are for the whole organization (the KPI tiles)."""
    from app.modules.mamify.models import MamifyMember

    page_size = max(1, min(page_size, MAX_AGENT_PAGE_SIZE))
    page = max(1, page)
    base = _agent_filters(_agent_list_select(organization_id), organization_id=organization_id, search=search,
                          status=status,
                          parent_id=parent_id, blacklisted=blacklisted)
    total = await db.scalar(select(func.count()).select_from(base.order_by(None).subquery())) or 0
    order = {
        "recent": (AgentProfile.joined_at.desc(), AgentProfile.id),
        "oldest": (AgentProfile.joined_at.asc(), AgentProfile.id),
        "name": (func.lower(AgentProfile.display_name), AgentProfile.id),
        "code": (AgentProfile.promoter_code, AgentProfile.id),
    }.get(sort, (AgentProfile.joined_at.desc(), AgentProfile.id))
    rows = [_agent_row(r) for r in (await db.execute(
        base.order_by(*order).offset((page - 1) * page_size).limit(page_size))).all()]

    ids = [r["id"] for r in rows]
    parent_ids = {r["direct_parent_agent_id"] for r in rows if r["direct_parent_agent_id"]}
    directs: dict = {}
    sizes: dict = {}
    parents: dict = {}
    mamify: dict = {}
    if ids:
        directs = dict((await db.execute(
            select(NetworkNode.direct_parent_agent_id, func.count()).where(
                NetworkNode.organization_id == organization_id, NetworkNode.effective_to.is_(None),
                NetworkNode.direct_parent_agent_id.in_(ids)).group_by(NetworkNode.direct_parent_agent_id))).all())
        sizes = dict((await db.execute(
            select(NetworkClosure.ancestor_agent_id, func.count()).where(
                NetworkClosure.organization_id == organization_id, NetworkClosure.effective_to.is_(None),
                NetworkClosure.depth > 0, NetworkClosure.ancestor_agent_id.in_(ids))
            .group_by(NetworkClosure.ancestor_agent_id))).all())
        mamify = {a: (c, e) for a, c, e in (await db.execute(
            select(MamifyMember.agent_id, MamifyMember.mamify_customer_id, MamifyMember.email).where(
                MamifyMember.organization_id == organization_id, MamifyMember.agent_id.in_(ids)))).all()}
    if parent_ids:
        parents = {i: (n, c) for i, n, c in (await db.execute(
            select(AgentProfile.id, AgentProfile.display_name, AgentProfile.promoter_code)
            .where(AgentProfile.id.in_(parent_ids)))).all()}
    for r in rows:
        p = parents.get(r["direct_parent_agent_id"])
        r["parent_name"], r["parent_code"] = (p if p else (None, None))
        r["direct_count"] = directs.get(r["id"], 0)
        r["network_size"] = sizes.get(r["id"], 0)
        m = mamify.get(r["id"])
        r["mamify_customer_id"], r["contact_email"] = (m[0], r["email"] or m[1]) if m else (None, r["email"])

    by_status = dict((await db.execute(
        select(AgentProfile.status, func.count()).where(AgentProfile.organization_id == organization_id)
        .group_by(AgentProfile.status))).all())
    blacklisted_count = await db.scalar(select(func.count()).where(
        AgentProfile.organization_id == organization_id, AgentProfile.is_blacklisted.is_(True))) or 0
    return {
        "items": rows, "total": total, "page": page, "page_size": page_size,
        "pages": max(1, -(-total // page_size)),
        "counts": {"ALL": sum(by_status.values()), **by_status, "BLACKLISTED": blacklisted_count},
    }


async def lookup_agents(
    db: AsyncSession, *, organization_id: uuid.UUID, q: str | None = None, ids: list[uuid.UUID] | None = None,
    status: str | None = None, limit: int = 20,
) -> list[dict]:
    """Small answers for the "choose a collaborator" fields: by search text,
    or by id to show the name of the one already chosen."""
    stmt = select(AgentProfile.id, AgentProfile.display_name, AgentProfile.promoter_code, AgentProfile.status,
                  AgentProfile.user_id).where(AgentProfile.organization_id == organization_id)
    if ids:
        stmt = stmt.where(AgentProfile.id.in_(ids[:200]))
    else:
        if not (q or "").strip():
            return []
        like = f"%{q.strip().replace('%', '').replace('_', ' ')}%"
        stmt = stmt.where(or_(AgentProfile.display_name.ilike(like), AgentProfile.promoter_code.ilike(like),
                              func.concat(AgentProfile.first_name, " ", AgentProfile.last_name).ilike(like)))
        # Exact code first, then names that start with the text.
        stmt = stmt.order_by((func.lower(AgentProfile.promoter_code) != q.strip().lower()),
                             ~func.lower(AgentProfile.display_name).startswith(q.strip().lower()),
                             func.lower(AgentProfile.display_name))
        stmt = stmt.limit(max(1, min(limit, 50)))
    if status:
        stmt = stmt.where(AgentProfile.status == status)
    return [{"id": i, "display_name": n, "promoter_code": c, "status": s, "user_id": u}
            for i, n, c, s, u in (await db.execute(stmt)).all()]


async def iter_agents_csv(db: AsyncSession, *, organization_id: uuid.UUID, search: str | None,
                          status: str | None):
    """Rows of the CSV export of the filtered registry, read in batches."""
    from sqlalchemy.orm import aliased

    parent = aliased(AgentProfile)
    stmt = _agent_filters(_agent_list_select(organization_id), organization_id=organization_id, search=search,
                          status=status, parent_id=None, blacklisted=None).add_columns(parent.display_name.label("parent_name")).join(
        parent, parent.id == NetworkNode.direct_parent_agent_id, isouter=True,
    ).order_by(AgentProfile.joined_at.desc(), AgentProfile.id)
    result = await db.stream(stmt.execution_options(yield_per=2000))
    async for r in result:
        a = _agent_row(r)
        yield [str(a["id"]), a["display_name"], a["promoter_code"], a["role_name"] or "",
               r[-1] or "Radice", a["status"], a["joined_at"].isoformat() if a["joined_at"] else ""]


async def update_agent(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    agent_id: uuid.UUID,
    first_name: str | None,
    last_name: str | None,
    status_value: str | None,
    current_rank_id: uuid.UUID | None,
    actor_user_id: uuid.UUID,
    is_blacklisted: bool | None = None,
) -> AgentProfile | None:
    from app.modules.commissions.models import AgentRankHistory
    from app.modules.rbac import service as rbac_service

    agent = await db.get(AgentProfile, agent_id)
    if agent is None or agent.organization_id != organization_id:
        return None

    # PENDING_APPROVAL -> ACTIVE is an approval and must go through
    # approve_agent() (network.approve); otherwise an ADMIN with network.manage
    # could confirm their own suggested agent. Reactivating a SUSPENDED or
    # TERMINATED agent is allowed here.
    if status_value == "ACTIVE" and agent.status == "PENDING_APPROVAL":
        raise AgentApprovalError("Use the dedicated approve endpoint (network.approve) to activate a suggested agent")

    previous = {
        "status": agent.status,
        "current_rank_id": str(agent.current_rank_id) if agent.current_rank_id else None,
        "is_blacklisted": agent.is_blacklisted,
    }
    if first_name is not None or last_name is not None:
        agent.first_name = first_name if first_name is not None else agent.first_name
        agent.last_name = last_name if last_name is not None else agent.last_name
        agent.display_name = f"{agent.first_name or ''} {agent.last_name or ''}".strip()
    if status_value is not None:
        agent.status = status_value
        # SUSPENDED/TERMINATED revokes the PROMOTER role and ACTIVE restores it.
        # Agents without a login have no role to sync.
        if agent.user_id is not None:
            if status_value == "ACTIVE":
                await rbac_service.assign_role(
                    db, user_id=agent.user_id, organization_id=organization_id, role_code="PROMOTER"
                )
            elif status_value in ("SUSPENDED", "TERMINATED"):
                await rbac_service.revoke_role(
                    db, user_id=agent.user_id, organization_id=organization_id, role_code="PROMOTER"
                )
    if is_blacklisted is not None:
        agent.is_blacklisted = is_blacklisted
    if current_rank_id is not None:
        agent.current_rank_id = current_rank_id
        db.add(
            AgentRankHistory(
                organization_id=organization_id,
                agent_id=agent_id,
                rank_id=current_rank_id,
                effective_from=utcnow(),
                calculation_source="MANUAL",
                rule_version_id="manual-admin-update",
                approved_by=actor_user_id,
                reason="Aggiornamento qualifica da pannello amministrativo",
            )
        )

    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="network.agent_updated", entity_type="agent_profile", entity_id=str(agent_id),
        previous_value=previous,
        new_value={
            "status": agent.status,
            "current_rank_id": str(agent.current_rank_id) if agent.current_rank_id else None,
            "is_blacklisted": agent.is_blacklisted,
        },
    )
    await db.commit()
    await db.refresh(agent)
    return agent


class AgentApprovalError(Exception):
    pass


async def approve_agent(
    db: AsyncSession, *, organization_id: uuid.UUID, agent_id: uuid.UUID, actor_user_id: uuid.UUID
) -> AgentProfile | None:
    """Approve a suggested collaborator (PENDING_APPROVAL) and make them ACTIVE.
    Requires network.approve, which plain ADMINs do not hold."""
    agent = await db.get(AgentProfile, agent_id)
    if agent is None or agent.organization_id != organization_id:
        return None
    if agent.status != "PENDING_APPROVAL":
        raise AgentApprovalError(f"Agent is {agent.status}, not PENDING_APPROVAL")

    agent.status = "ACTIVE"
    agent.approved_by_user_id = actor_user_id
    agent.approved_at = utcnow()

    # An approved agent with a login also gets PROMOTER, alongside existing
    # roles; assign_role() is idempotent.
    if agent.user_id is not None:
        from app.modules.rbac import service as rbac_service

        await rbac_service.assign_role(
            db, user_id=agent.user_id, organization_id=organization_id, role_code="PROMOTER"
        )
        await ensure_customer_side(db, organization_id=organization_id, agent=agent)

    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="network.agent_approved", entity_type="agent_profile", entity_id=str(agent_id),
        previous_value={"status": "PENDING_APPROVAL"}, new_value={"status": "ACTIVE"},
    )
    await db.commit()
    await db.refresh(agent)
    return agent


async def reject_agent(
    db: AsyncSession, *, organization_id: uuid.UUID, agent_id: uuid.UUID, actor_user_id: uuid.UUID, reason: str | None
) -> AgentProfile | None:
    """Reject a suggested collaborator: soft (TERMINATED with a stored reason),
    never a hard delete, to keep history append-only."""
    agent = await db.get(AgentProfile, agent_id)
    if agent is None or agent.organization_id != organization_id:
        return None
    if agent.status != "PENDING_APPROVAL":
        raise AgentApprovalError(f"Agent is {agent.status}, not PENDING_APPROVAL")

    agent.status = "TERMINATED"
    agent.approved_by_user_id = actor_user_id
    agent.approved_at = utcnow()
    agent.rejection_reason = reason

    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="network.agent_rejected", entity_type="agent_profile", entity_id=str(agent_id),
        previous_value={"status": "PENDING_APPROVAL"}, new_value={"status": "TERMINATED", "reason": reason},
    )
    await db.commit()
    await db.refresh(agent)
    return agent


async def set_agent_photo(
    db: AsyncSession, *, organization_id: uuid.UUID, agent_id: uuid.UUID, photo_url: str, actor_user_id: uuid.UUID
) -> AgentProfile | None:
    agent = await db.get(AgentProfile, agent_id)
    if agent is None or agent.organization_id != organization_id:
        return None

    agent.photo_url = photo_url
    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="network.agent_photo_updated", entity_type="agent_profile", entity_id=str(agent_id),
    )
    await db.commit()
    await db.refresh(agent)
    return agent


async def is_ancestor(
    db: AsyncSession, *, organization_id: uuid.UUID, ancestor_agent_id: uuid.UUID, agent_id: uuid.UUID
) -> bool:
    """ABAC check: is ancestor_agent_id an active ancestor of agent_id (or the
    same agent)? Authorizes branch-scoped access."""
    stmt = select(NetworkClosure.depth).where(
        NetworkClosure.organization_id == organization_id,
        NetworkClosure.ancestor_agent_id == ancestor_agent_id,
        NetworkClosure.descendant_agent_id == agent_id,
        NetworkClosure.effective_to.is_(None),
    )
    return (await db.execute(stmt)).scalar_one_or_none() is not None


async def get_branch(
    db: AsyncSession, *, organization_id: uuid.UUID, root_agent_id: uuid.UUID, include_frozen: bool = True
) -> list[dict]:
    """Descendants of root_agent_id (depth 0 = itself) with the display fields
    the network tree UI needs, in one query.

    `is_frozen` is the owner's account status (users.status == FROZEN), which
    is independent of the AgentProfile lifecycle in `status`.

    include_frozen=False removes frozen members together with their whole
    subtree: a frozen member is fully detached from the upline's view, and
    leaving orphans would break the tree and misstate depths. Only roles in
    network/router.py's _FROZEN_VISIBLE_ROLES pass True."""
    from app.modules.commercial.models import CommercialRole
    from app.modules.commissions.models import Rank
    from app.modules.users.models import User

    descendants = await _get_active_descendants(
        db, organization_id=organization_id, agent_id=root_agent_id
    )
    if not descendants:
        return []
    depth_by_agent = {agent_id: depth for agent_id, depth in descendants}

    stmt = (
        select(
            AgentProfile.id,
            AgentProfile.display_name,
            AgentProfile.promoter_code,
            AgentProfile.status,
            Rank.code,
            NetworkNode.direct_parent_agent_id,
            User.status,
            CommercialRole.code,
            CommercialRole.name,
        )
        .join(Rank, Rank.id == AgentProfile.current_rank_id, isouter=True)
        .join(CommercialRole, CommercialRole.id == AgentProfile.current_commercial_role_id, isouter=True)
        .join(
            NetworkNode,
            (NetworkNode.agent_id == AgentProfile.id) & (NetworkNode.effective_to.is_(None)),
            isouter=True,
        )
        # Outer join: agents without a login cannot be frozen.
        .join(User, User.id == AgentProfile.user_id, isouter=True)
        .where(AgentProfile.id.in_(depth_by_agent.keys()))
    )
    rows = (await db.execute(stmt)).all()
    branch = [
        {
            "agent_id": row[0],
            "depth": depth_by_agent[row[0]],
            "display_name": row[1],
            "promoter_code": row[2],
            "status": row[3],
            "rank_code": row[4],
            # The root's parent is outside this branch, so it is reported as
            # null to keep the UI from attaching the root to an unknown node.
            "parent_agent_id": row[5] if row[0] != root_agent_id else None,
            "is_frozen": row[6] == "FROZEN",
            "role_code": row[7],
            "role_name": row[8],
        }
        for row in rows
    ]
    if include_frozen:
        return branch
    return _without_frozen_subtrees(branch, root_agent_id=root_agent_id)


def _without_frozen_subtrees(branch: list[dict], *, root_agent_id: uuid.UUID) -> list[dict]:
    """Remove frozen members and everything below them, walking each node up to
    the branch root. Iterative and guarded against malformed parent chains."""
    by_id = {row["agent_id"]: row for row in branch}
    kept = []
    for row in branch:
        node: dict | None = row
        seen: set[uuid.UUID] = set()
        hidden = False
        while node is not None and node["agent_id"] not in seen:
            seen.add(node["agent_id"])
            if node["is_frozen"]:
                hidden = True
                break
            if node["agent_id"] == root_agent_id:
                break
            parent_id = node["parent_agent_id"]
            node = by_id.get(parent_id) if parent_id is not None else None
        if not hidden:
            kept.append(row)
    return kept


# Contracts needing human action (usually missing or rejected documents),
# shown to promoters as "problemi".
PROBLEM_CONTRACT_STATUSES = {"DOCUMENTS_PENDING", "REJECTED", "SUSPENDED"}
# Still in progress, nothing wrong yet.
IN_PROGRESS_CONTRACT_STATUSES = {"DRAFT", "SUBMITTED", "UNDER_REVIEW", "APPROVED", "PAYMENT_PENDING", "ACTIVATION_PENDING"}
# Deal done (paying or paid).
PROCESSED_CONTRACT_STATUSES = {"PAID", "ACTIVE", "RENEWED"}


async def get_branch_summary(
    db: AsyncSession, *, organization_id: uuid.UUID, root_agent_id: uuid.UUID, include_frozen: bool = True
) -> dict:
    """Per-agent and per-level rollup of contracts (by status bucket) and earned
    commission for a promoter's branch.

    include_frozen is passed to get_branch(), so totals cover only members the
    caller can see."""
    from app.modules.commissions.models import CommissionMovement
    from app.modules.contracts.models import Contract, ContractAttribution

    branch = await get_branch(
        db, organization_id=organization_id, root_agent_id=root_agent_id, include_frozen=include_frozen
    )
    if not branch:
        return {
            "agents": [],
            "totals": {
                "contracts": 0, "commission_cents": 0, "contracts_by_status": {},
                "contracts_closed": 0, "contracts_rejected": 0, "contracts_pending": 0,
                "contracts_in_progress": 0, "levels_below": 0, "people_total": 0,
            },
        }
    agent_ids = [row["agent_id"] for row in branch]

    contract_stmt = (
        select(ContractAttribution.producer_agent_id, Contract.status, func.count())
        .select_from(Contract)
        .join(ContractAttribution, ContractAttribution.id == Contract.contract_attribution_id)
        .where(ContractAttribution.producer_agent_id.in_(agent_ids))
        .group_by(ContractAttribution.producer_agent_id, Contract.status)
    )
    contract_rows = (await db.execute(contract_stmt)).all()
    contracts_by_agent: dict[uuid.UUID, dict[str, int]] = {}
    for producer_agent_id, status, count in contract_rows:
        contracts_by_agent.setdefault(producer_agent_id, {})[status] = count

    commission_stmt = (
        select(CommissionMovement.agent_id, func.coalesce(func.sum(CommissionMovement.amount_cents), 0))
        .where(
            CommissionMovement.agent_id.in_(agent_ids),
            CommissionMovement.status.notin_(["CANCELLED", "REVERSED"]),
        )
        .group_by(CommissionMovement.agent_id)
    )
    commission_rows = (await db.execute(commission_stmt)).all()
    commission_by_agent = {agent_id: int(total) for agent_id, total in commission_rows}

    agents = []
    total_contracts = 0
    total_commission_cents = 0
    total_by_status: dict[str, int] = {}
    max_depth = 0
    for row in branch:
        by_status = contracts_by_agent.get(row["agent_id"], {})
        agent_contract_total = sum(by_status.values())
        problem_count = sum(by_status.get(s, 0) for s in PROBLEM_CONTRACT_STATUSES)
        in_progress_count = sum(by_status.get(s, 0) for s in IN_PROGRESS_CONTRACT_STATUSES)
        processed_count = sum(by_status.get(s, 0) for s in PROCESSED_CONTRACT_STATUSES)
        agent_commission = commission_by_agent.get(row["agent_id"], 0)

        agents.append({
            **row,
            "contracts_total": agent_contract_total,
            "contracts_by_status": by_status,
            "contracts_problem": problem_count,
            "contracts_in_progress": in_progress_count,
            "contracts_processed": processed_count,
            "commission_cents": agent_commission,
        })
        total_contracts += agent_contract_total
        total_commission_cents += agent_commission
        max_depth = max(max_depth, row["depth"])
        for status, count in by_status.items():
            total_by_status[status] = total_by_status.get(status, 0) + count

    # Coarse status buckets; the full list is in
    # docs/business-rules.md#contract-state-machine.
    total_closed = sum(total_by_status.get(s, 0) for s in PROCESSED_CONTRACT_STATUSES)
    total_rejected = total_by_status.get("REJECTED", 0)
    total_pending = sum(total_by_status.get(s, 0) for s in PROBLEM_CONTRACT_STATUSES) - total_rejected
    total_in_progress = sum(total_by_status.get(s, 0) for s in IN_PROGRESS_CONTRACT_STATUSES)

    return {
        "agents": agents,
        "totals": {
            "contracts": total_contracts,
            "commission_cents": total_commission_cents,
            "contracts_by_status": total_by_status,
            "contracts_closed": total_closed,
            "contracts_rejected": total_rejected,
            "contracts_pending": total_pending,
            "contracts_in_progress": total_in_progress,
            "levels_below": max_depth,
            "people_total": len(branch) - 1,  # exclude self (depth 0)
        },
    }


async def get_organization_network_levels(db: AsyncSession, *, organization_id: uuid.UUID) -> dict:
    """Admin-only, organization-wide view: headcount per depth below each
    top-level sponsor and the maximum depth. Unlike get_branch_summary() it has
    no root, because several independent roots can coexist."""
    # An agent's depth is its largest depth as a descendant, i.e. measured
    # from its topmost ancestor.
    stmt = (
        select(NetworkClosure.descendant_agent_id, func.max(NetworkClosure.depth))
        .where(NetworkClosure.organization_id == organization_id)
        .group_by(NetworkClosure.descendant_agent_id)
    )
    rows = (await db.execute(stmt)).all()
    if not rows:
        return {"people_total": 0, "levels_total": 0, "people_by_level": {}}

    people_by_level: dict[int, int] = {}
    for _agent_id, depth in rows:
        people_by_level[depth] = people_by_level.get(depth, 0) + 1

    return {
        "people_total": len(rows),
        "levels_total": max(people_by_level.keys()) + 1,
        "people_by_level": people_by_level,
    }


async def get_branch_contracts(
    db: AsyncSession, *, organization_id: uuid.UUID, root_agent_id: uuid.UUID, viewer_agent_id: uuid.UUID | None = None
) -> list[dict]:
    """Contract-level detail for a promoter's whole downline (customer, product,
    status, commission), one row per contract, so problems can be traced to the
    customer to contact."""
    from app.modules.catalog.models import ProductVersion
    from app.modules.commissions.models import CommissionMovement
    from app.modules.contracts.models import Contract, ContractAttribution, ContractStatusHistory
    from app.modules.customers.models import Company, Customer, CustomerProfile, SupplyPoint
    from app.modules.customers.service import display_name_for

    branch = await get_branch(db, organization_id=organization_id, root_agent_id=root_agent_id)
    agent_ids = [row["agent_id"] for row in branch]
    if not agent_ids:
        return []
    agent_name_by_id = {row["agent_id"]: row["display_name"] for row in branch}

    stmt = (
        select(
            Contract.id,
            Contract.status,
            Contract.customer_id,
            Contract.supply_point_id,
            Contract.expires_at,
            ContractAttribution.producer_agent_id,
            ProductVersion.name,
            ProductVersion.base_price_cents,
        )
        .select_from(Contract)
        .join(ContractAttribution, ContractAttribution.id == Contract.contract_attribution_id)
        .join(ProductVersion, ProductVersion.id == Contract.product_version_id)
        .where(ContractAttribution.producer_agent_id.in_(agent_ids))
        .order_by(Contract.created_at.desc())
    )
    rows = (await db.execute(stmt)).all()
    if not rows:
        return []

    contract_ids = [r[0] for r in rows]
    customer_ids = list({r[2] for r in rows})
    supply_point_ids = list({r[3] for r in rows})

    customers = {c.id: c for c in (await db.execute(select(Customer).where(Customer.id.in_(customer_ids)))).scalars()}
    profiles = {
        p.customer_id: p
        for p in (await db.execute(select(CustomerProfile).where(CustomerProfile.customer_id.in_(customer_ids)))).scalars()
    }
    companies = {
        c.customer_id: c
        for c in (await db.execute(select(Company).where(Company.customer_id.in_(customer_ids)))).scalars()
    }
    supply_point_labels = dict(
        (
            await db.execute(select(SupplyPoint.id, SupplyPoint.label).where(SupplyPoint.id.in_(supply_point_ids)))
        ).all()
    )

    commission_stmt = (
        select(CommissionMovement.contract_id, func.coalesce(func.sum(CommissionMovement.amount_cents), 0))
        .where(
            CommissionMovement.contract_id.in_(contract_ids),
            CommissionMovement.beneficiary_kind == "AGENT",
            CommissionMovement.status.notin_(["CANCELLED", "REVERSED"]),
        )
        .group_by(CommissionMovement.contract_id)
    )
    commission_by_contract = {cid: int(total) for cid, total in (await db.execute(commission_stmt)).all()}

    # The viewer's own commission per contract, as opposed to the total across
    # beneficiaries above. None when the viewer has no agent profile: "not a
    # beneficiary" differs from "earned zero".
    my_commission_by_contract: dict[uuid.UUID, int] | None = None
    if viewer_agent_id is not None:
        my_commission_stmt = (
            select(CommissionMovement.contract_id, func.coalesce(func.sum(CommissionMovement.amount_cents), 0))
            .where(
                CommissionMovement.contract_id.in_(contract_ids),
                CommissionMovement.agent_id == viewer_agent_id,
                CommissionMovement.status.notin_(["CANCELLED", "REVERSED"]),
            )
            .group_by(CommissionMovement.contract_id)
        )
        my_commission_by_contract = {cid: int(total) for cid, total in (await db.execute(my_commission_stmt)).all()}

    # Latest admin note per contract: tells the promoter what to chase with the
    # customer (e.g. which document is missing).
    note_history_stmt = (
        select(ContractStatusHistory.contract_id, ContractStatusHistory.notes, ContractStatusHistory.created_at)
        .where(ContractStatusHistory.contract_id.in_(contract_ids), ContractStatusHistory.notes.isnot(None))
        .order_by(ContractStatusHistory.contract_id, ContractStatusHistory.created_at.desc())
    )
    latest_note_by_contract: dict[uuid.UUID, str] = {}
    for cid, notes, _created_at in (await db.execute(note_history_stmt)).all():
        if cid not in latest_note_by_contract:
            latest_note_by_contract[cid] = notes

    result = []
    for (
        contract_id, status, customer_id, supply_point_id, expires_at, producer_agent_id, product_name, base_price_cents,
    ) in rows:
        customer = customers.get(customer_id)
        result.append({
            "contract_id": contract_id,
            "status": status,
            "customer_id": customer_id,
            "customer_name": display_name_for(customer.kind, profiles.get(customer_id), companies.get(customer_id))
            if customer else "—",
            "customer_email": customer.email if customer else None,
            "customer_phone": customer.phone if customer else None,
            "product_name": product_name,
            "value_cents": base_price_cents,
            "supply_point_label": supply_point_labels.get(supply_point_id),
            "expires_at": expires_at,
            "producer_agent_id": producer_agent_id,
            "producer_name": agent_name_by_id.get(producer_agent_id, "—"),
            "commission_cents": commission_by_contract.get(contract_id, 0),
            "my_commission_cents": (
                my_commission_by_contract.get(contract_id, 0) if my_commission_by_contract is not None else None
            ),
            "is_problem": status in PROBLEM_CONTRACT_STATUSES,
            "admin_note": latest_note_by_contract.get(contract_id),
        })
    return result


async def ancestors_at(
    db: AsyncSession, *, organization_id: uuid.UUID, agent_id: uuid.UUID, at: datetime
) -> list[tuple[uuid.UUID, int]]:
    """Sponsorship chain of agent_id (itself at depth 0) as it was at `at`,
    nearest first.

    Closure rows are historized (move_agent() closes and reopens rows instead of
    rewriting them), so a past sponsor is a plain read. If `at` precedes the
    agent's entry into the network (a backdated contract), the entry chain is
    used as the closest approximation."""
    at_date = (
        NetworkClosure.effective_from <= at,
        or_(NetworkClosure.effective_to.is_(None), NetworkClosure.effective_to > at),
    )
    stmt = (
        select(NetworkClosure.ancestor_agent_id, NetworkClosure.depth)
        .where(
            NetworkClosure.organization_id == organization_id,
            NetworkClosure.descendant_agent_id == agent_id,
            *at_date,
        )
        .order_by(NetworkClosure.depth.asc())
    )
    rows = [(r[0], r[1]) for r in (await db.execute(stmt)).all()]
    if rows:
        return rows
    first = (
        await db.execute(
            select(func.min(NetworkClosure.effective_from)).where(
                NetworkClosure.organization_id == organization_id,
                NetworkClosure.descendant_agent_id == agent_id,
            )
        )
    ).scalar_one_or_none()
    if first is None or first <= at:
        return rows
    return await ancestors_at(db, organization_id=organization_id, agent_id=agent_id, at=first)


async def chain_at(
    db: AsyncSession, *, organization_id: uuid.UUID, seller_agent_id: uuid.UUID, at: datetime
) -> list[dict]:
    """The sale's chain as used by the commission engine: each person with
    level, commercial role at the date, and status. Shared by the activation
    snapshot, the preview and the simulator so they cannot diverge."""
    from app.modules.commercial import service as commercial_service
    from app.modules.network.models import AgentProfile as _AgentProfile

    ancestors = await ancestors_at(db, organization_id=organization_id, agent_id=seller_agent_id, at=at)
    agent_ids = [a for a, _ in ancestors]
    agents = {
        a.id: a
        for a in (await db.execute(select(_AgentProfile).where(_AgentProfile.id.in_(agent_ids)))).scalars()
    } if agent_ids else {}
    roles = await commercial_service.roles_at(db, agent_ids=agent_ids, at=at)
    chain = []
    for agent_id, depth in ancestors:
        agent = agents.get(agent_id)
        if agent is None:
            continue
        role = roles.get(agent_id)
        chain.append({
            "agent_id": agent_id,
            "name": agent.display_name,
            "depth": depth,
            "status": agent.status,
            "role_id": role.id if role else None,
            "role_code": role.code if role else None,
            "allows_delegation": bool(role.allows_delegation) if role else False,
            "network_depth": role.network_depth if role else None,
            "can_close_sales": bool(role.can_close_sales) if role else True,
        })
    return chain


async def create_snapshot_for_contract(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    producer_agent_id: uuid.UUID,
    reason: str = "contract_activation",
    as_of: datetime | None = None,
) -> NetworkSnapshot:
    """Freeze the seller's sponsorship chain at the sale date (`as_of`), with
    each member's commercial role at that date and current status. Called once,
    at activation.

    Every ancestor keeps its level even when not ACTIVE; inactive members get no
    share, and the empty slot is handled by the Split Plan's fallback strategy,
    a business choice that shortening the chain would hide."""
    at = as_of or utcnow()
    snapshot = NetworkSnapshot(organization_id=organization_id, reason=reason, as_of=at)
    db.add(snapshot)
    await db.flush()

    chain = await chain_at(db, organization_id=organization_id, seller_agent_id=producer_agent_id, at=at)
    from app.modules.network.models import AgentProfile as _AgentProfile

    ranks = dict(
        (await db.execute(
            select(_AgentProfile.id, _AgentProfile.current_rank_id).where(
                _AgentProfile.id.in_([c["agent_id"] for c in chain])
            )
        )).all()
    ) if chain else {}
    for member in chain:
        db.add(
            NetworkSnapshotNode(
                snapshot_id=snapshot.id,
                ancestor_agent_id=member["agent_id"],
                depth=member["depth"],
                rank_id_at_snapshot=ranks.get(member["agent_id"]),
                commercial_role_id=member["role_id"],
                role_code=member["role_code"],
                agent_status=member["status"],
            )
        )

    await db.flush()
    return snapshot
