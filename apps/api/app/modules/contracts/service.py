import calendar
import logging
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.foundation.db import utcnow
from app.modules.audit import service as audit_service
from app.modules.catalog import pricing
from app.modules.catalog.models import Product, ProductVersion
from app.modules.contracts.models import (
    Contract,
    ContractAttribution,
    ContractRequest,
    ContractStatusHistory,
)
from app.modules.contracts.state_machine import assert_transition_allowed, event_name_for
from app.modules.customers.models import SupplyPoint
from app.modules.network import service as network_service
from app.modules.network.models import AgentProfile
from app.modules.notifications import service as notifications_service
from app.modules.outbox import service as outbox_service
from app.modules.users.models import User

if TYPE_CHECKING:
    # Annotation only; the runtime import is function-local.
    from app.modules.customers.schemas import SupplyPointCreate

# Entering one of these (re)starts the term: activated_at/expires_at are reset.
TERM_START_STATUSES = {"ACTIVE", "RENEWED"}

logger = logging.getLogger(__name__)

#: wallet_transactions.source for the automatic contract credit, distinct
#: from ORDER_CASHBACK_BASE and INVOICE_REDEMPTION_BASE for accounting.
CONTRACT_CASHBACK_SOURCE = "CONTRACT_CASHBACK"

#: Statuses from which a contract can be paid. Payment does not wait for
#: document approval; activation does. A prepaid contract keeps its status
#: until approval moves it to PAID -> ACTIVE (transition_contract), the only
#: point where commissions are generated.
PREPAYABLE_STATUSES = frozenset(
    {"SUBMITTED", "DOCUMENTS_PENDING", "UNDER_REVIEW", "APPROVED", "PAYMENT_PENDING"}
)


def is_payable(contract: Contract) -> bool:
    return (
        contract.status in PREPAYABLE_STATUSES
        and bool(contract.gross_amount_cents)
        and contract.paid_at is None
    )


def _add_months(dt: datetime, months: int) -> datetime:
    """Add months, clamping the day to the target month (Jan 31 -> Feb 28/29)."""
    total_months = dt.month - 1 + months
    year = dt.year + total_months // 12
    month = total_months % 12 + 1
    day = min(dt.day, calendar.monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)


async def to_read_dicts(db: AsyncSession, contracts: list[Contract]) -> list[dict]:
    """Serialize contracts with display names (product, supply point, agents)
    resolved in bulk, so no caller shows bare UUIDs or does N+1 lookups."""
    if not contracts:
        return []

    product_version_ids = {c.product_version_id for c in contracts if c.product_version_id is not None}
    supply_point_ids = {c.supply_point_id for c in contracts}
    agent_ids = {c.activated_by_promoter_id for c in contracts if c.activated_by_promoter_id} | {
        c.first_referrer_agent_id for c in contracts if c.first_referrer_agent_id
    }
    # Comprehensions instead of dict(rows): SQLAlchemy Row does not type-check
    # as a tuple.
    agent_names: dict[uuid.UUID, str] = (
        {
            row.id: row.display_name
            for row in (
                await db.execute(
                    select(AgentProfile.id, AgentProfile.display_name).where(AgentProfile.id.in_(agent_ids))
                )
            ).all()
        }
        if agent_ids
        else {}
    )

    product_names: dict[uuid.UUID, str] = {
        row.id: row.name
        for row in (
            await db.execute(
                select(ProductVersion.id, ProductVersion.name).where(ProductVersion.id.in_(product_version_ids))
            )
        ).all()
    }
    supply_points: dict[uuid.UUID, SupplyPoint] = {
        sp.id: sp
        for sp in (await db.execute(select(SupplyPoint).where(SupplyPoint.id.in_(supply_point_ids)))).scalars()
    }

    def _agent_name(agent_id: uuid.UUID | None) -> str | None:
        return agent_names.get(agent_id) if agent_id is not None else None

    result = []
    for c in contracts:
        sp = supply_points.get(c.supply_point_id)
        row = {
            "id": c.id,
            "customer_id": c.customer_id,
            "supply_point_id": c.supply_point_id,
            "product_version_id": c.product_version_id,
            "status": c.status,
            "notes": c.notes,
            "iban": c.iban,
            "email": c.email,
            "holder_first_name": c.holder_first_name,
            "holder_last_name": c.holder_last_name,
            "pec": c.pec,
            "created_at": c.created_at,
            "activated_at": c.activated_at,
            "expires_at": c.expires_at,
            "product_name": product_names.get(c.product_version_id) if c.product_version_id else None,
            "supply_point_label": sp.label if sp else None,
            "pod_code": sp.pod_code if sp else None,
            "pdr_code": sp.pdr_code if sp else None,
            "energy_type": sp.energy_type if sp else None,
            "contract_request_id": c.contract_request_id,
            "created_by_role": c.created_by_role,
            "activated_by_promoter_id": c.activated_by_promoter_id,
            "activated_by_promoter_name": _agent_name(c.activated_by_promoter_id),
            "first_referrer_agent_id": c.first_referrer_agent_id,
            "first_referrer_name": _agent_name(c.first_referrer_agent_id),
            "customer_kind": c.customer_kind,
            "net_amount_cents": c.net_amount_cents,
            # Display-only; amounts are integer cents.
            "vat_rate": float(c.vat_rate) if c.vat_rate is not None else None,
            "vat_amount_cents": c.vat_amount_cents,
            "gross_amount_cents": c.gross_amount_cents,
            "payment_plan": c.payment_plan,
            "payment_discount_cents": int(c.payment_discount_cents or 0),
            "payment_method": c.payment_method,
            "paid_at": c.paid_at,
            "billing_stopped_at": c.billing_stopped_at,
            "terms_accepted_at": c.terms_accepted_at,
            "terms_version": c.terms_version,
        }
        result.append(row)
    return result


async def get_status_history(db: AsyncSession, *, contract_id: uuid.UUID) -> list[dict]:
    """Status change history for one contract, oldest first. Actor name is the
    agent display name, falling back to the login email."""
    stmt = (
        select(ContractStatusHistory)
        .where(ContractStatusHistory.contract_id == contract_id)
        .order_by(ContractStatusHistory.created_at.asc())
    )
    rows = (await db.execute(stmt)).scalars().all()
    if not rows:
        return []

    user_ids = {r.actor_user_id for r in rows}
    users = {u.id: u for u in (await db.execute(select(User).where(User.id.in_(user_ids)))).scalars()}
    agents_by_user = {
        a.user_id: a
        for a in (
            await db.execute(select(AgentProfile).where(AgentProfile.user_id.in_(user_ids)))
        ).scalars()
    }

    result = []
    for r in rows:
        agent = agents_by_user.get(r.actor_user_id)
        user = users.get(r.actor_user_id)
        actor_name = agent.display_name if agent else (user.email if user else "—")
        result.append({
            "id": r.id,
            "from_status": r.from_status,
            "to_status": r.to_status,
            "actor_user_id": r.actor_user_id,
            "actor_name": actor_name,
            "reason": r.reason,
            "notes": r.notes,
            "created_at": r.created_at,
        })
    return result


class InvalidProducerAgentError(Exception):
    """The producer is not an active agent of this organization. Rejected at
    creation because a missing or inactive producer would freeze an empty
    network snapshot and silently yield no commissions at activation."""


async def product_requires_supply_point(db: AsyncSession, *, product_version_id: uuid.UUID) -> bool:
    """Decided by the product's commercial category (e.g. electricity and gas
    yes, telecoms no). Uncategorized products default to True."""
    from app.modules.catalog.models import ProductCategory

    version = await db.get(ProductVersion, product_version_id)
    product = await db.get(Product, version.product_id) if version is not None else None
    if product is None or product.commercial_category_id is None:
        return True
    category = await db.get(ProductCategory, product.commercial_category_id)
    return bool(category.requires_supply_point) if category is not None else True


class ClosingAgentNotFoundError(InvalidProducerAgentError):
    """The producer's role cannot close sales and no active upline agent can."""


async def _closing_agent_or_none(
    db: AsyncSession, *, organization_id: uuid.UUID, agent_id: uuid.UUID, at
) -> uuid.UUID | None:
    """None if `agent_id` may close sales (or has no role yet); otherwise the
    nearest ACTIVE upline agent who can."""
    from app.modules.commercial import service as commercial_service

    role = await commercial_service.role_at(db, agent_id=agent_id, at=at)
    if role is None or role.can_close_sales:
        return None
    ancestors = await network_service.ancestors_at(db, organization_id=organization_id, agent_id=agent_id, at=at)
    upline = [a for a, depth in ancestors if depth > 0]
    roles = await commercial_service.roles_at(db, agent_ids=upline, at=at)
    statuses = dict(
        (await db.execute(select(AgentProfile.id, AgentProfile.status).where(AgentProfile.id.in_(upline)))).all()
    ) if upline else {}
    for candidate in upline:
        candidate_role = roles.get(candidate)
        if statuses.get(candidate) == "ACTIVE" and (candidate_role is None or candidate_role.can_close_sales):
            return candidate
    raise ClosingAgentNotFoundError(
        "Il cliente è stato segnalato da un promoter, ma sopra di lui non c'è nessun collaboratore attivo "
        "che possa chiudere la vendita: contatta l'assistenza."
    )


async def create_contract(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    customer_id: uuid.UUID,
    supply_point_id: uuid.UUID | None,
    product_version_id: uuid.UUID | None,
    producer_agent_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    correlation_id: str,
    contract_request_id: uuid.UUID | None = None,
    notify_staff: bool = True,
    notes: str | None = None,
    iban: str | None = None,
    email: str | None = None,
    holder_first_name: str | None = None,
    holder_last_name: str | None = None,
    pec: str | None = None,
    created_by_role: str | None = None,
    activated_by_promoter_id: uuid.UUID | None = None,
    lead_id: uuid.UUID | None = None,
) -> Contract:
    """Create a DRAFT contract. Never generates commissions (see
    business-rules.md).

    `created_by_role` (CUSTOMER / PROMOTER / ADMIN) is frozen because roles
    change. `activated_by_promoter_id` is set only when a promoter filled the
    contract in for the customer, independently of who earns the commission.

    The price is computed server-side from the product version and customer
    kind (catalog/pricing.py) and frozen on the contract.

    Every contract belongs to a request: callers building one pass
    `contract_request_id` (with `notify_staff=False`, since the request
    notifies once on submission); otherwise a single-contract request is
    created here. `product_version_id` may be None only in DRAFT (enforced by
    a DB constraint)."""
    producer = await db.get(AgentProfile, producer_agent_id)
    if producer is None or producer.organization_id != organization_id:
        raise InvalidProducerAgentError(
            f"producer_agent_id {producer_agent_id} is not a known agent in this organization"
        )
    if producer.status != "ACTIVE":
        raise InvalidProducerAgentError(
            f"producer_agent_id {producer_agent_id} is {producer.status}, not ACTIVE -- "
            "cannot attribute a new contract to a non-active agent"
        )

    # A producer whose role cannot close sales becomes the referral Promoter
    # (earning the Split Plan referral fee) and the sale goes to the nearest
    # upline agent who can close it.
    sold_at = utcnow()
    referral_promoter_id: uuid.UUID | None = None
    closer = await _closing_agent_or_none(db, organization_id=organization_id, agent_id=producer_agent_id, at=sold_at)
    if closer is not None:
        referral_promoter_id = producer_agent_id
        producer_agent_id = closer

    from app.modules.customers.models import Customer

    attribution = ContractAttribution(
        organization_id=organization_id,
        producer_agent_id=producer_agent_id,
        attributed_promoter_id=producer_agent_id,
    )
    db.add(attribution)
    await db.flush()

    # Customer kind decides VAT, so it is frozen with the amounts.
    customer = await db.get(Customer, customer_id)
    customer_kind = customer.kind if customer is not None else None
    version = await db.get(ProductVersion, product_version_id) if product_version_id is not None else None
    price = await _price_for(db, version=version, customer_kind=customer_kind)

    if contract_request_id is None:
        request = ContractRequest(
            organization_id=organization_id,
            customer_id=customer_id,
            status="DRAFT",
            holder_first_name=holder_first_name,
            holder_last_name=holder_last_name,
            email=email,
            pec=pec,
            iban=iban,
            created_by_user_id=actor_user_id,
            created_by_role=created_by_role,
            activated_by_promoter_id=activated_by_promoter_id,
        )
        db.add(request)
        await db.flush()
        contract_request_id = request.id

    # Original referrer, frozen now so later customer reassignment does not
    # affect contracts already opened.
    first_referrer_agent_id = await _resolve_referring_agent_id_for_customer(
        db, organization_id=organization_id, customer_id=customer_id
    )

    from app.modules.leads import service as leads_service

    lead = await leads_service.lead_for_new_contract(
        db, organization_id=organization_id, customer_id=customer_id,
        product_id=version.product_id if version is not None else None,
        lead_id=lead_id, referral_promoter_id=referral_promoter_id, closing_agent_id=producer_agent_id,
        actor_user_id=actor_user_id,
    )

    contract = Contract(
        organization_id=organization_id,
        customer_id=customer_id,
        sold_at=sold_at,
        lead_id=lead.id if lead is not None else None,
        contract_request_id=contract_request_id,
        supply_point_id=supply_point_id,
        product_version_id=product_version_id,
        contract_attribution_id=attribution.id,
        status="DRAFT",
        notes=notes,
        iban=iban,
        email=email,
        holder_first_name=holder_first_name,
        holder_last_name=holder_last_name,
        pec=pec,
        created_by_user_id=actor_user_id,
        created_by_role=created_by_role,
        activated_by_promoter_id=activated_by_promoter_id,
        first_referrer_agent_id=first_referrer_agent_id,
        customer_kind=customer_kind,
        net_amount_cents=price.net_amount_cents if price else None,
        vat_rate=price.vat_rate if price else None,
        vat_amount_cents=price.vat_amount_cents if price else None,
        gross_amount_cents=price.gross_amount_cents if price else None,
    )
    db.add(contract)
    await db.flush()

    db.add(
        ContractStatusHistory(
            contract_id=contract.id,
            from_status=None,
            to_status="DRAFT",
            actor_user_id=actor_user_id,
            correlation_id=correlation_id,
        )
    )
    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="contract.created", entity_type="contract", entity_id=str(contract.id),
        new_value={"status": "DRAFT"},
    )
    if notify_staff:
        await notifications_service.notify_roles(
            db, organization_id=organization_id, roles=notifications_service.STAFF_NOTIFY_ROLES,
            type_="CONTRACT_CREATED", entity_type="contract", entity_id=contract.id,
            title="Nuovo contratto creato", body=f"Contratto {contract.id} in stato Bozza.",
            exclude_user_id=actor_user_id,
        )
    await db.commit()
    await db.refresh(contract)
    return contract


async def _price_for(
    db: AsyncSession, *, version: ProductVersion | None, customer_kind: str | None
) -> pricing.PriceBreakdown | None:
    if version is None:
        return None
    product = await db.get(Product, version.product_id)
    return pricing.compute_contract_price(
        version=version, customer_kind=customer_kind,
        product_type=product.product_type if product else None,
    )


async def freeze_price(db: AsyncSession, *, contract: Contract, version: ProductVersion) -> None:
    """Set the package and freeze its price as create_contract does. Callers
    restrict this to contracts not yet paid (requests.py). Does not commit."""
    from app.modules.customers.models import Customer

    customer = await db.get(Customer, contract.customer_id)
    customer_kind = customer.kind if customer is not None else None
    price = await _price_for(db, version=version, customer_kind=customer_kind)
    contract.product_version_id = version.id
    contract.customer_kind = customer_kind
    contract.net_amount_cents = price.net_amount_cents if price else None
    contract.vat_rate = price.vat_rate if price else None
    contract.vat_amount_cents = price.vat_amount_cents if price else None
    contract.gross_amount_cents = price.gross_amount_cents if price else None
    contract.updated_at = utcnow()


class SelfServiceContractError(Exception):
    pass


async def _resolve_referring_agent_id_for_customer(
    db: AsyncSession, *, organization_id: uuid.UUID, customer_id: uuid.UUID
) -> uuid.UUID | None:
    """Most recent referring agent for a customer, keyed by customer_id (the
    network module's equivalent is keyed by user_id). Kept local to avoid a
    cross-domain import."""
    from app.modules.referral.models import CustomerAttribution, PromoterCode

    stmt = (
        select(PromoterCode.agent_id)
        .select_from(CustomerAttribution)
        .join(PromoterCode, PromoterCode.id == CustomerAttribution.promoter_code_id)
        .where(CustomerAttribution.organization_id == organization_id, CustomerAttribution.customer_id == customer_id)
        .order_by(CustomerAttribution.attributed_at.desc())
        .limit(1)
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def resolve_self_service_producer(
    db: AsyncSession, *, organization_id: uuid.UUID, customer_id: uuid.UUID
) -> tuple[uuid.UUID, uuid.UUID | None]:
    """Producer for a self-service contract: the customer's referrer or, if
    inactive, the nearest active upline sponsor. Returns the producer and the
    replaced referrer when a substitution happened.

    Walking up instead of blocking keeps the relationship in the same branch
    without admin intervention, while create_contract() still only accepts
    ACTIVE producers. The original referrer stays on the contract
    (first_referrer_agent_id)."""
    referrer_agent_id = await _resolve_referring_agent_id_for_customer(
        db, organization_id=organization_id, customer_id=customer_id
    )
    if referrer_agent_id is None:
        raise SelfServiceContractError(
            "Nessun promoter di riferimento trovato per il tuo account -- contatta l'assistenza."
        )
    producer = await network_service.resolve_nearest_active_agent(
        db, organization_id=organization_id, agent_id=referrer_agent_id
    )
    if producer is None:
        raise SelfServiceContractError(
            "Il promoter che ti ha invitato non è più attivo e non risulta nessun referente attivo "
            "sopra di lui. Contatta l'assistenza: ti verrà assegnato un nuovo referente e potrai "
            "completare l'attivazione."
        )
    return producer.id, (referrer_agent_id if producer.id != referrer_agent_id else None)


async def record_producer_substitution(
    db: AsyncSession, *, organization_id: uuid.UUID, contract: Contract, actor_user_id: uuid.UUID,
    substituted_for_agent_id: uuid.UUID,
) -> None:
    """Audit that someone other than the customer's referrer is credited, so
    the attribution is explainable later. Does not commit."""
    attribution = await db.get(ContractAttribution, contract.contract_attribution_id)
    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="contract.producer_substituted", entity_type="contract", entity_id=str(contract.id),
        previous_value={"producer_agent_id": str(substituted_for_agent_id)},
        new_value={"producer_agent_id": str(attribution.producer_agent_id) if attribution else None},
        reason="Il promoter di riferimento non è attivo: attribuito allo sponsor attivo più vicino",
    )


async def resolve_promoter_for_customer(
    db: AsyncSession, *, organization_id: uuid.UUID, promoter_user_id: uuid.UUID, customer_id: uuid.UUID
) -> AgentProfile:
    """The calling promoter's agent, if they may act for this customer
    (directly attributed, or inherited from a deactivated referrer).
    Raises otherwise."""
    promoter_agent = await network_service.get_own_agent_profile(
        db, organization_id=organization_id, user_id=promoter_user_id
    )
    if promoter_agent is None or promoter_agent.status != "ACTIVE":
        raise SelfServiceContractError("Solo un promoter attivo può attivare contratti per i propri clienti.")

    resolved_agent_id = await _resolve_referring_agent_id_for_customer(
        db, organization_id=organization_id, customer_id=customer_id
    )
    if resolved_agent_id != promoter_agent.id:
        # Same walk-up as self-service: the nearest ACTIVE sponsor of a
        # deactivated referrer inherits the customer.
        inheritor = (
            await network_service.resolve_nearest_active_agent(
                db, organization_id=organization_id, agent_id=resolved_agent_id
            )
            if resolved_agent_id is not None
            else None
        )
        if inheritor is None or inheritor.id != promoter_agent.id:
            raise SelfServiceContractError("Questo cliente non è nella tua rete.")
    return promoter_agent


async def create_contract_self_service(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    customer_user_id: uuid.UUID,
    product_version_id: uuid.UUID,
    supply_point_payload: "SupplyPointCreate",
    email: str,
    holder_first_name: str | None = None,
    holder_last_name: str | None = None,
    pec: str | None = None,
    iban: str | None = None,
) -> Contract:
    """A customer activates an SOSNET (INTERNAL) product themselves.

    The producer comes from the customer's referral attribution, which always
    exists because registration is invite-only
    (auth/service.py::register_with_referral). The contract is submitted
    straight to DOCUMENTS_PENDING, since the next step is uploading documents
    (business-rules.md#contract-self-service)."""
    from app.modules.customers import service as customers_service
    from app.modules.customers.models import Customer

    customer = (
        await db.execute(
            select(Customer).where(Customer.organization_id == organization_id, Customer.user_id == customer_user_id)
        )
    ).scalar_one_or_none()
    if customer is None:
        raise SelfServiceContractError("No customer record linked to this account")

    version = await db.get(ProductVersion, product_version_id)
    if version is None:
        raise SelfServiceContractError("Product version not found")
    product = await db.get(Product, version.product_id)
    if product is None or product.organization_id != organization_id:
        raise SelfServiceContractError("Product version not found")
    if product.category != "INTERNAL":
        raise SelfServiceContractError(
            "Solo i prodotti SOSNET si attivano come contratto -- gli altri prodotti si acquistano come ordine."
        )
    # The catalog UI filters by the same rule; this is the actual enforcement.
    if not pricing.product_allows_customer_kind(product.customer_type, customer.kind):
        raise SelfServiceContractError(
            "Questo contratto non è disponibile per la tua tipologia di cliente."
        )

    producer_agent_id, substituted_for_agent_id = await resolve_self_service_producer(
        db, organization_id=organization_id, customer_id=customer.id
    )

    supply_point = await customers_service.add_supply_point(
        db, organization_id=organization_id, customer_id=customer.id,
        payload=supply_point_payload, actor_user_id=customer_user_id,
    )
    if supply_point is None:
        raise SelfServiceContractError("Unable to create supply point")

    contract = await create_contract(
        db, organization_id=organization_id, customer_id=customer.id,
        supply_point_id=supply_point.id, product_version_id=product_version_id,
        producer_agent_id=producer_agent_id, actor_user_id=customer_user_id,
        correlation_id=str(uuid.uuid4()), email=email,
        holder_first_name=holder_first_name, holder_last_name=holder_last_name, pec=pec, iban=iban,
        created_by_role="CUSTOMER",
        # Self-service: no promoter acted on the customer's behalf.
        activated_by_promoter_id=None,
    )
    if substituted_for_agent_id is not None:
        await record_producer_substitution(
            db, organization_id=organization_id, contract=contract, actor_user_id=customer_user_id,
            substituted_for_agent_id=substituted_for_agent_id,
        )
        await db.commit()
    contract = await transition_contract(
        db, organization_id=organization_id, contract=contract, to_status="SUBMITTED",
        actor_user_id=customer_user_id, reason="Attivazione self-service", notes=None,
        correlation_id=str(uuid.uuid4()),
    )
    contract = await transition_contract(
        db, organization_id=organization_id, contract=contract, to_status="DOCUMENTS_PENDING",
        actor_user_id=customer_user_id, reason=None, notes=None,
        correlation_id=str(uuid.uuid4()),
    )
    return contract


async def create_contract_for_recruited_customer(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    promoter_user_id: uuid.UUID,
    customer_id: uuid.UUID,
    product_version_id: uuid.UUID,
    supply_point_payload: "SupplyPointCreate",
    email: str,
    holder_first_name: str | None = None,
    holder_last_name: str | None = None,
    pec: str | None = None,
    iban: str | None = None,
) -> Contract:
    """A promoter activates a contract for one of their own customers, who
    need not have logged in. The producer is always the caller's own agent
    (never client-supplied), and resolve_promoter_for_customer ensures the
    customer belongs to them, so a promoter cannot act for another's
    customer."""
    from app.modules.customers import service as customers_service
    from app.modules.customers.models import Customer

    customer = await db.get(Customer, customer_id)
    if customer is None or customer.organization_id != organization_id:
        raise SelfServiceContractError("Customer not found")

    promoter_agent = await resolve_promoter_for_customer(
        db, organization_id=organization_id, promoter_user_id=promoter_user_id, customer_id=customer_id
    )

    version = await db.get(ProductVersion, product_version_id)
    if version is None:
        raise SelfServiceContractError("Product version not found")
    product = await db.get(Product, version.product_id)
    if product is None or product.organization_id != organization_id:
        raise SelfServiceContractError("Product version not found")
    if product.category != "INTERNAL":
        raise SelfServiceContractError(
            "Solo i prodotti SOSNET si attivano come contratto -- gli altri prodotti si acquistano come ordine."
        )
    if not pricing.product_allows_customer_kind(product.customer_type, customer.kind):
        raise SelfServiceContractError(
            "Questo contratto non è disponibile per la tipologia di questo cliente."
        )

    supply_point = await customers_service.add_supply_point(
        db, organization_id=organization_id, customer_id=customer.id,
        payload=supply_point_payload, actor_user_id=promoter_user_id,
    )
    if supply_point is None:
        raise SelfServiceContractError("Unable to create supply point")

    contract = await create_contract(
        db, organization_id=organization_id, customer_id=customer.id,
        supply_point_id=supply_point.id, product_version_id=product_version_id,
        producer_agent_id=promoter_agent.id, actor_user_id=promoter_user_id,
        correlation_id=str(uuid.uuid4()), email=email,
        holder_first_name=holder_first_name, holder_last_name=holder_last_name, pec=pec, iban=iban,
        created_by_role="PROMOTER",
        # The promoter completed this on the customer's behalf.
        activated_by_promoter_id=promoter_agent.id,
    )
    contract = await transition_contract(
        db, organization_id=organization_id, contract=contract, to_status="SUBMITTED",
        actor_user_id=promoter_user_id, reason="Attivazione da promoter per proprio cliente", notes=None,
        correlation_id=str(uuid.uuid4()),
    )
    contract = await transition_contract(
        db, organization_id=organization_id, contract=contract, to_status="DOCUMENTS_PENDING",
        actor_user_id=promoter_user_id, reason=None, notes=None,
        correlation_id=str(uuid.uuid4()),
    )
    return contract


async def set_contract_iban(
    db: AsyncSession, *, organization_id: uuid.UUID, contract: Contract, iban: str, actor_user_id: uuid.UUID
) -> Contract:
    """Set or correct a contract's IBAN after creation. Audited. Commits."""
    previous = contract.iban
    contract.iban = iban
    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="contract.iban_updated", entity_type="contract", entity_id=str(contract.id),
        previous_value={"iban": previous}, new_value={"iban": iban},
    )
    await db.commit()
    await db.refresh(contract)
    return contract


# Statuses that involve no separate decision: entering the key immediately
# continues to the value. Only approval (UNDER_REVIEW -> APPROVED) and payment
# confirmation (PAYMENT_PENDING -> PAID) need a human
# (business-rules.md#contract-self-service). Each hop is still a full,
# audited transition_contract() call.
AUTO_CASCADE_AFTER: dict[str, str] = {
    "APPROVED": "PAYMENT_PENDING",
    "PAID": "ACTIVATION_PENDING",
    "ACTIVATION_PENDING": "ACTIVE",
}


async def transition_contract(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    contract: Contract,
    to_status: str,
    actor_user_id: uuid.UUID,
    reason: str | None,
    notes: str | None,
    correlation_id: str,
) -> Contract:
    """Single entry point for contract status changes. Validates against the
    state machine, records history and audit, and enqueues the transition's
    domain event. Commission inputs are frozen only on first activation.
    Then follows AUTO_CASCADE_AFTER, so e.g. UNDER_REVIEW -> APPROVED returns
    a contract already in PAYMENT_PENDING."""
    from_status = contract.status
    assert_transition_allowed(from_status, to_status)

    if to_status == "ACTIVE" and contract.network_snapshot_id is None:
        # Freeze every commission input (network chain and seller role as of
        # the sale date, Split Plan, amount, margin) so later changes cannot
        # alter this contract's payouts. Reactivation does not refreeze.
        from app.modules.commissions.services import sale as sale_service
        from app.modules.leads import service as leads_service

        await sale_service.freeze_contract(db, contract=contract)
        await leads_service.mark_converted(db, contract=contract)

    if to_status == "PAID" and contract.paid_at is None:
        # No Stripe payment: staff are confirming a single bank transfer. A
        # transfer the customer announced keeps its frozen discount; any other
        # manual confirmation is at list price.
        contract.paid_at = utcnow()
        chosen_transfer = contract.payment_method == "BANK_TRANSFER" and contract.payment_plan == "FULL"
        contract.payment_plan = "FULL"
        contract.payment_method = "BANK_TRANSFER"
        if not chosen_transfer:
            contract.payment_discount_cents = 0
    if to_status == "PAID":
        from app.modules.contracts import instalments as instalments_service

        rows = await instalments_service.ensure_schedule(db, contract=contract)
        if not any(r.status == "PAID" for r in rows):
            await instalments_service.record_payment(
                db, contract=contract, source=instalments_service.SOURCE_ADMIN, number=1,
                actor_user_id=actor_user_id,
            )

    if to_status in TERM_START_STATUSES:
        now = utcnow()
        contract.activated_at = now
        product_version = await db.get(ProductVersion, contract.product_version_id)
        duration = product_version.contract_duration_months if product_version else None
        contract.expires_at = _add_months(now, duration) if duration else None

    contract.status = to_status
    db.add(
        ContractStatusHistory(
            contract_id=contract.id,
            from_status=from_status,
            to_status=to_status,
            actor_user_id=actor_user_id,
            reason=reason,
            notes=notes,
            correlation_id=correlation_id,
        )
    )

    event_name = event_name_for(from_status, to_status)
    if event_name is not None:
        db.add(
            outbox_service.enqueue(
                organization_id=organization_id,
                event_type=event_name,
                payload={"contract_id": str(contract.id), "correlation_id": correlation_id},
            )
        )

    if from_status == "DRAFT" and to_status == "SUBMITTED":
        # Mark the request SUBMITTED once no draft points remain. Covers
        # contracts submitted individually rather than via
        # requests.py::submit_request.
        request = await db.get(ContractRequest, contract.contract_request_id)
        if request is not None and request.status == "DRAFT":
            other_drafts = (
                await db.execute(
                    select(Contract.id).where(
                        Contract.contract_request_id == request.id,
                        Contract.id != contract.id,
                        Contract.status == "DRAFT",
                    )
                )
            ).first()
            if other_drafts is None:
                request.status = "SUBMITTED"
                request.submitted_at = utcnow()
                request.updated_at = utcnow()

    if from_status == "ACTIVATION_PENDING" and to_status == "ACTIVE":
        # Release commissions for instalments already paid, in this transaction.
        from app.modules.contracts import instalments as instalments_service

        await instalments_service.release_paid_instalments(db, contract=contract)

    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="contract.transitioned", entity_type="contract", entity_id=str(contract.id),
        previous_value={"status": from_status}, new_value={"status": to_status},
        reason=reason, correlation_id=correlation_id,
    )
    contract.updated_at = utcnow()
    await db.commit()
    await db.refresh(contract)

    # After commit: the SosnetCash credit is a separate idempotent ledger
    # entry and must never roll back the status change.
    if to_status == "PAID":
        await credit_contract_cashback(
            db, organization_id=organization_id, contract=contract, actor_user_id=actor_user_id
        )

    if to_status == "ACTIVE":
        # Notify the friend referrer (separate from the sponsorship network;
        # see friend_referrals/models.py). Best-effort, after commit.
        from app.modules.friend_referrals import service as friend_referrals_service

        await friend_referrals_service.notify_referrer_of_activation(
            db, organization_id=organization_id, customer_id=contract.customer_id
        )

    if to_status == "REJECTED" and contract.paid_at is not None:
        # A prepaid contract was rejected (possibly still being billed).
        # Refunds and cancellations stay manual, so staff are alerted.
        await notifications_service.notify_roles(
            db, organization_id=organization_id, roles=notifications_service.STAFF_NOTIFY_ROLES,
            type_="CONTRACT_PAID_REJECTED", entity_type="contract", entity_id=contract.id,
            title=f"Respinto un contratto già pagato: {str(contract.id)[:8].upper()}",
            body=(
                "Il cliente aveva già pagato. Valuta il rimborso su Stripe, il cashback SosnetCash "
                "accreditato e, se a rate, annulla l'abbonamento."
            ),
        )
        await db.commit()

    next_status = AUTO_CASCADE_AFTER.get(contract.status)
    if contract.status == "PAYMENT_PENDING" and contract.paid_at is not None:
        # Prepaid: approval was the last step, so continue to PAID and via
        # the cascade to ACTIVE, where commissions are generated.
        next_status = "PAID"
    if next_status is not None:
        contract = await transition_contract(
            db, organization_id=organization_id, contract=contract, to_status=next_status,
            actor_user_id=actor_user_id, reason="Automatico -- nessuna decisione separata richiesta",
            notes=None, correlation_id=correlation_id,
        )
    return contract


async def credit_contract_cashback(
    db: AsyncSession, *, organization_id: uuid.UUID, contract: Contract, actor_user_id: uuid.UUID | None
) -> None:
    """Credit the automatic SosnetCash earned by a paid SOSNET contract.

    Distinct from partner-invoice cashback (invoice_redemptions) and opt-in
    order cashback: INTERNAL contracts carry no surcharge, and the credit is
    a per-product percentage of the gross paid (0 by default).

    Credits the whole contract at once, for single payments. Instalment plans
    are handled by credit_contract_instalment_cashback (per instalment by
    default, or all upfront at the first one, per organization setting).

    Exactly-once via `contracts.cashback_credited_at` plus a deterministic
    wallet idempotency key for races such as replayed webhooks.

    Never raises: the contract is already committed as PAID."""
    from app.modules.organizations import service as _organizations_service

    if not await _organizations_service.is_feature_enabled(db, organization_id=organization_id, name="wallet"):
        return  # SosnetCash is switched off: nothing to credit.
    from app.modules.contracts import payment_plans

    if contract.cashback_credited_at is not None:
        return
    plan = payment_plans.plan_by_key(contract.payment_plan)
    if plan is not None and plan.instalments > 1:
        return

    version = await db.get(ProductVersion, contract.product_version_id)
    if version is None:
        return
    gross = contract.gross_amount_cents
    if gross is None:
        # No frozen price: recomputing from today's product would restate
        # history, so skip with a warning.
        logger.warning("Contract %s has no gross_amount_cents snapshot; skipping cashback", contract.id)
        return
    # Based on the amount actually paid, after any single-payment discount.
    paid_cents = gross - int(contract.payment_discount_cents or 0)
    amount_cents = pricing.contract_cashback_cents(version=version, gross_amount_cents=paid_cents)
    credited = await _credit_contract_sosnetcash(
        db, organization_id=organization_id, contract=contract, amount_cents=amount_cents,
        actor_user_id=actor_user_id, idempotency_key=f"contract-cashback:{contract.id}",
        note=f"Cashback contratto {str(contract.id)[:8].upper()}",
    )
    if credited:
        contract.cashback_credited_at = utcnow()
        await db.commit()
        await db.refresh(contract)


async def credit_contract_instalment_cashback(
    db: AsyncSession, *, organization_id: uuid.UUID, contract: Contract, instalment_number: int
) -> None:
    """SosnetCash for one collected instalment, according to the organization
    setting (organizations/service.py::get_contract_instalment_cashback_mode):

    - PER_INSTALMENT: the percentage applied to this instalment, summing to
      the single-payment amount once all are paid;
    - UPFRONT: the whole contract's cashback at the first instalment (same
      amount and idempotency key as a single payment), nothing afterwards.

    The mode is effectively fixed at the first instalment: once an upfront
    credit exists in the ledger, no per-instalment credit follows.

    Idempotency is keyed by instalment number, not Stripe invoice, so a manual
    confirmation and a later Stripe retry count as one. The amount is the
    plan instalment, not the invoice amount. Never raises."""
    from app.modules.organizations import service as _organizations_service

    if not await _organizations_service.is_feature_enabled(db, organization_id=organization_id, name="wallet"):
        return  # SosnetCash is switched off: nothing to credit.
    from app.modules.contracts import payment_plans
    from app.modules.organizations import service as organizations_service
    from app.modules.wallets.models import WalletTransaction

    plan = payment_plans.plan_by_key(contract.payment_plan)
    if plan is None or plan.instalments <= 1 or not contract.gross_amount_cents:
        return
    if contract.status in ("REJECTED", "CANCELLED"):
        return
    version = await db.get(ProductVersion, contract.product_version_id)
    if version is None:
        return
    code = str(contract.id)[:8].upper()
    upfront_key = f"contract-cashback:{contract.id}"

    if instalment_number == 1 and (
        await organizations_service.get_contract_instalment_cashback_mode(db, organization_id=organization_id)
        == organizations_service.CASHBACK_UPFRONT
    ):
        amount_cents = pricing.contract_cashback_cents(version=version, gross_amount_cents=contract.gross_amount_cents)
        idempotency_key = upfront_key
        note = f"Cashback contratto {code} (intero, anticipato alla prima rata)"
    else:
        already_in_advance = (
            await db.execute(select(WalletTransaction.id).where(WalletTransaction.idempotency_key == upfront_key))
        ).first()
        if already_in_advance is not None:
            return
        instalment_cents = payment_plans.breakdown_for(plan, contract.gross_amount_cents).instalment_cents
        amount_cents = pricing.contract_cashback_cents(version=version, gross_amount_cents=instalment_cents)
        idempotency_key = f"contract-cashback:{contract.id}:rata-{instalment_number}"
        note = f"Cashback contratto {code} (rata {instalment_number} di {plan.instalments})"

    credited = await _credit_contract_sosnetcash(
        db, organization_id=organization_id, contract=contract, amount_cents=amount_cents,
        actor_user_id=None, idempotency_key=idempotency_key, note=note,
    )
    if credited and contract.cashback_credited_at is None:
        # On instalment plans this only means crediting has started; the
        # ledger holds the actual totals.
        contract.cashback_credited_at = utcnow()
        await db.commit()
        await db.refresh(contract)


async def _credit_contract_sosnetcash(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    contract: Contract,
    amount_cents: int,
    actor_user_id: uuid.UUID | None,
    idempotency_key: str,
    note: str,
) -> bool:
    from app.modules.customers.models import Customer
    from app.modules.wallets import service as wallets_service

    if amount_cents <= 0:
        return False
    customer = await db.get(Customer, contract.customer_id)
    if customer is None or customer.user_id is None:
        # No login means no wallet; warn because credit is owed but cannot
        # be delivered yet.
        logger.warning("Contract %s customer has no user account; SosnetCash not credited", contract.id)
        return False

    wallet = await wallets_service.get_or_create_wallet(
        db, organization_id=organization_id, user_id=customer.user_id
    )
    try:
        await wallets_service.credit_wallet(
            db,
            organization_id=organization_id,
            wallet_id=wallet.id,
            amount_cents=amount_cents,
            type_="ADMIN_CREDIT",
            actor_user_id=actor_user_id,
            reference_contract_id=contract.id,
            source=CONTRACT_CASHBACK_SOURCE,
            note=note,
            idempotency_key=idempotency_key,
        )
    except Exception:
        logger.exception("Contract %s: SosnetCash credit failed", contract.id)
        return False
    return True


# --- Contract payment (Stripe) -----------------------------------------------


async def attach_stripe_checkout_session(
    db: AsyncSession, *, contract: Contract, session_id: str, plan_key: str, discount_cents: int = 0
) -> Contract:
    """Record the live Checkout Session and its plan, replacing any earlier
    one so the webhook honours only the latest attempt. Status is unchanged
    until Stripe confirms."""
    contract.stripe_checkout_session_id = session_id
    contract.payment_plan = plan_key
    contract.payment_discount_cents = discount_cents
    contract.payment_method = "CARD"
    contract.updated_at = utcnow()
    await db.commit()
    await db.refresh(contract)
    return contract


async def attach_stripe_subscription(
    db: AsyncSession, *, contract: Contract, subscription_id: str, customer_id: str | None
) -> Contract:
    contract.stripe_subscription_id = subscription_id
    if customer_id:
        contract.stripe_customer_id = customer_id
    contract.updated_at = utcnow()
    await db.commit()
    await db.refresh(contract)
    return contract


async def has_accepted_commission_plan(db: AsyncSession, *, contract_id: uuid.UUID) -> bool:
    from app.modules.contracts.models import ContractCommissionPlan

    return (
        await db.execute(select(ContractCommissionPlan.id).where(ContractCommissionPlan.contract_id == contract_id))
    ).first() is not None


class CommissionPreviewChangedError(Exception):
    pass


async def accept_commission_plan(
    db: AsyncSession, *, organization_id: uuid.UUID, contract: Contract, checksum: str, actor_user_id: uuid.UUID
):
    """Store the accepted commission preview. It is recomputed server-side and
    rejected if its checksum differs from what the administrator saw (e.g.
    network, role or payment changed). Commits."""
    from app.modules.commissions.services.preview import build_commission_preview
    from app.modules.contracts.models import ContractCommissionPlan

    preview = await build_commission_preview(db, organization_id=organization_id, contract=contract)
    if preview.get("blocking_errors"):
        raise CommissionPreviewChangedError(
            "Le provvigioni di questo contratto non si possono calcolare: "
            + " ".join(preview["blocking_errors"])
        )
    if preview["checksum"] != checksum:
        raise CommissionPreviewChangedError(
            "L'anteprima delle provvigioni è cambiata da quando l'hai aperta (rete, ruoli, piano o pagamento aggiornati). "
            "Ricaricala e controllala di nuovo."
        )
    plan = ContractCommissionPlan(
        organization_id=organization_id,
        contract_id=contract.id,
        accepted_by_user_id=actor_user_id,
        accepted_at=utcnow(),
        payment_plan=preview["payment"]["plan_key"],
        total_commission_cents=preview["total_commission_cents"],
        preview=preview,
        checksum=checksum,
    )
    db.add(plan)
    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="contract.commission_preview_accepted", entity_type="contract", entity_id=str(contract.id),
        new_value={"total_commission_cents": preview["total_commission_cents"], "checksum": checksum},
    )
    await db.commit()
    return plan


async def mark_paid_via_stripe(
    db: AsyncSession, *, organization_id: uuid.UUID, stripe_checkout_session_id: str,
    stripe_invoice_id: str | None = None,
) -> Contract | None:
    """Verified-webhook handler for a single-contract Checkout Session (not a
    request checkout). The success URL is never proof of payment.

    Returns None when no contract matches (other organization or superseded
    session) so Stripe does not retry indefinitely.
    """
    contract = (
        await db.execute(
            select(Contract).where(
                Contract.organization_id == organization_id,
                Contract.stripe_checkout_session_id == stripe_checkout_session_id,
            )
        )
    ).scalar_one_or_none()
    if contract is None:
        return None
    return await record_card_payment(
        db, organization_id=organization_id, contract=contract, stripe_invoice_id=stripe_invoice_id
    )


async def record_card_payment(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    contract: Contract,
    stripe_invoice_id: str | None = None,
    notify_staff: bool = True,
    bank_transfer_confirmed_by: uuid.UUID | None = None,
) -> Contract:
    """Record the first payment of a contract (card, or a confirmed bank
    transfer via `bank_transfer_confirmed_by`). Later instalments are billed
    automatically. `contract.payment_plan` must already be set: it drives the
    instalment schedule and SosnetCash crediting.

    `notify_staff=False` lets a request notify once for all its contracts."""
    from app.modules.contracts import instalments as instalments_service

    # Card and confirmed transfer share one path so instalment row, cashback
    # and activation cannot diverge.
    if bank_transfer_confirmed_by is not None:
        source = instalments_service.SOURCE_ADMIN
        reason = "Bonifico confermato dall'amministrazione"
    else:
        source = instalments_service.SOURCE_STRIPE_CHECKOUT
        reason = "Pagamento confermato da Stripe"

    if contract.status == "PAYMENT_PENDING" and await has_accepted_commission_plan(db, contract_id=contract.id):
        # Set paid_at first, otherwise the PAID transition treats this as a
        # manual transfer and overwrites the plan with FULL / BANK_TRANSFER.
        contract.paid_at = utcnow()
        await instalments_service.record_payment(
            db, contract=contract, source=source, number=1, invoice_id=stripe_invoice_id,
            actor_user_id=bank_transfer_confirmed_by,
        )
        return await transition_contract(
            db, organization_id=organization_id, contract=contract, to_status="PAID",
            actor_user_id=bank_transfer_confirmed_by or contract.created_by_user_id or contract.customer_id,
            reason=reason, notes=None, correlation_id=str(uuid.uuid4()),
        )
    if contract.paid_at is not None:
        # Already recorded (webhook redelivery or parallel admin confirmation).
        return contract

    # Paid before approval (PREPAYABLE_STATUSES), or PAYMENT_PENDING without
    # an accepted commission preview: record payment and credit SosnetCash
    # now, keep the status; approval later carries it through PAID to ACTIVE.
    #
    # A contract no longer activatable (e.g. rejected meanwhile) still has
    # its payment recorded, earns no credit, and staff are asked to refund.
    contract.paid_at = utcnow()
    contract.updated_at = utcnow()
    code = str(contract.id)[:8].upper()
    accepted = contract.status in PREPAYABLE_STATUSES
    if accepted:
        await instalments_service.record_payment(
            db, contract=contract, source=source, number=1, invoice_id=stripe_invoice_id,
            actor_user_id=bank_transfer_confirmed_by,
        )
    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=bank_transfer_confirmed_by,
        action="contract.paid_before_approval" if accepted else "contract.paid_while_not_activatable",
        entity_type="contract", entity_id=str(contract.id),
        new_value={"status": contract.status, "payment_plan": contract.payment_plan},
        reason=reason,
    )
    if notify_staff or not accepted:
        await notifications_service.notify_roles(
            db, organization_id=organization_id, roles=notifications_service.STAFF_NOTIFY_ROLES,
            type_="CONTRACT_PAID_BEFORE_APPROVAL" if accepted else "CONTRACT_PAID_REJECTED",
            entity_type="contract", entity_id=contract.id,
            title=f"Contratto {code} pagato" + ("" if accepted else " dopo essere stato chiuso"),
            body=(
                "Il cliente ha già pagato: il contratto si attiva appena approvi i documenti e accetti l'anteprima provvigioni."
                if accepted
                else "Il contratto non è più attivabile: valuta il rimborso su Stripe e interrompi gli addebiti di questo contratto."
            ),
        )
    await db.commit()
    await db.refresh(contract)
    if accepted:
        await credit_contract_cashback(
            db, organization_id=organization_id, contract=contract, actor_user_id=None
        )
    return contract


async def record_subscription_invoice(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    subscription_id: str,
    paid: bool,
    amount_cents: int,
    invoice_id: str | None = None,
    billing_reason: str | None = None,
    lines: list[tuple[str, int]] | None = None,
) -> str:
    """Handle a paid or failed monthly subscription invoice.

    A subscription belongs to one contract or to a request with one item per
    contract; each `(subscription_item_id, amount_cents)` in `lines` is then
    recorded as that contract's own instalment (cashback, commission slice).

    Contract statuses never change here: suspending after a failed charge is
    a human decision, so staff and customer are notified instead.
    """
    contracts = list(
        (
            await db.execute(
                select(Contract).where(
                    Contract.organization_id == organization_id,
                    Contract.stripe_subscription_id == subscription_id,
                )
            )
        ).scalars()
    )
    if not contracts:
        return "nessun contratto per questo abbonamento"

    if len(contracts) == 1 and contracts[0].stripe_subscription_item_id is None:
        targets = [(contracts[0], amount_cents)]
    else:
        by_item = {c.stripe_subscription_item_id: c for c in contracts if c.stripe_subscription_item_id}
        targets = [(by_item[item_id], cents) for item_id, cents in (lines or []) if item_id in by_item]
        if not targets:
            return "nessuna riga della fattura corrisponde a un contratto"

    from app.modules.contracts import instalments as instalments_service

    codes = ", ".join(str(c.id)[:8].upper() for c, _ in targets)
    # The first instalment is recorded by the checkout handler; its
    # "subscription_create" invoice may arrive before the contracts are
    # linked. Later months are recorded here, keyed by invoice.
    is_later_month = bool(invoice_id) and billing_reason != "subscription_create"

    if paid:
        for contract, cents in targets:
            if is_later_month and contract.status not in ("REJECTED", "CANCELLED"):
                # Commission slice: released now if active, else at activation.
                row = await instalments_service.record_payment(
                    db, contract=contract, source=instalments_service.SOURCE_STRIPE_INVOICE, invoice_id=invoice_id,
                )
                if row is not None:
                    await db.commit()
                    await credit_contract_instalment_cashback(
                        db, organization_id=organization_id, contract=contract, instalment_number=row.number
                    )
            await audit_service.record(
                db, organization_id=organization_id, actor_user_id=None,
                action="contract.instalment_paid", entity_type="contract", entity_id=str(contract.id),
                new_value={"amount_cents": cents, "subscription_id": subscription_id, "invoice_id": invoice_id},
            )
        await db.commit()
        return f"rata incassata per {'il contratto' if len(targets) == 1 else 'i contratti'} {codes}"

    for contract, cents in targets:
        if is_later_month:
            await instalments_service.record_failure(db, contract=contract, invoice_id=invoice_id)
        await audit_service.record(
            db, organization_id=organization_id, actor_user_id=None,
            action="contract.instalment_failed", entity_type="contract", entity_id=str(contract.id),
            new_value={"amount_cents": cents, "subscription_id": subscription_id, "invoice_id": invoice_id},
            reason="Addebito della rata non riuscito",
        )
    first = targets[0][0]
    await notifications_service.notify_roles(
        db, organization_id=organization_id, roles=notifications_service.STAFF_NOTIFY_ROLES,
        type_="CONTRACT_INSTALMENT_FAILED", entity_type="contract", entity_id=first.id,
        title=(
            f"Rata non riscossa: contratto {codes}"
            if len(targets) == 1
            else f"Rata non riscossa: {len(targets)} contratti della pratica {str(first.contract_request_id)[:8].upper()}"
        ),
        body=(
            "L'addebito mensile non è andato a buon fine: le provvigioni di questa rata restano ferme. "
            "Se il cliente paga in altro modo, confermala a mano dal registro provvigioni del contratto."
        ),
    )
    customer_user_id = await _customer_user_id_for(db, contract=first)
    if customer_user_id is not None:
        await notifications_service.notify_user(
            db, organization_id=organization_id, user_id=customer_user_id,
            type_="CONTRACT_INSTALMENT_FAILED", entity_type="contract", entity_id=first.id,
            title="Rata del contratto non addebitata",
            body="Non siamo riusciti ad addebitare la rata mensile. Controlla la tua carta: riproveremo a breve.",
        )
    await db.commit()
    return f"rata NON riscossa per {'il contratto' if len(targets) == 1 else 'i contratti'} {codes}"


async def _customer_user_id_for(db: AsyncSession, *, contract: Contract) -> uuid.UUID | None:
    from app.modules.customers.models import Customer

    customer = await db.get(Customer, contract.customer_id)
    return customer.user_id if customer is not None else None
