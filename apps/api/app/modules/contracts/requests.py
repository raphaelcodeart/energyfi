"""Contract requests: several supply points, one contract per point, one
payment.

A customer with ten supply points has ten contracts, each with its own
package, approval, instalments and commissions, but enters holder data once,
uploads shared documents once, and pays once.

Flow:

1. Holder data, supply address and the number of points are collected up
   front. The request is created DRAFT with that many DRAFT contracts, each
   with its own supply point, so a partial request survives a closed
   browser. No POD/PDR code is asked.
2. Shared documents (identity, tax code...) are uploaded once on the request.
3. A package is chosen per point; it sets the energy type and its price is
   frozen on the contract.
4. Submit moves every point out of DRAFT together into normal review; from
   then on each contract is independent.
5. Payment (customer only): one Checkout Session for every payable contract,
   one line each or one subscription item each
   (payments/service.py::create_checkout_session_for_request).

Commissions and activation are not handled here; they stay per contract in
contracts/service.py::transition_contract.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.foundation.db import utcnow
from app.modules.audit import service as audit_service
from app.modules.catalog import pricing
from app.modules.catalog.models import Product, ProductVersion
from app.modules.contracts import payment_plans
from app.modules.contracts import service as contract_service
from app.modules.contracts.models import (
    Contract,
    ContractInstalment,
    ContractRequest,
    ContractRequestCheckout,
)
from app.modules.customers.models import Address, Company, Customer, CustomerProfile, SupplyPoint
from app.modules.network.models import AgentProfile
from app.modules.notifications import service as notifications_service

#: Larger portfolios are handled by the back office.
MAX_POINTS_PER_REQUEST = 50

#: Stripe's item limit per subscription. Instalment plans use one item per
#: contract, so larger requests can only be paid in full.
MAX_SUBSCRIPTION_LINES = 20


class ContractRequestError(Exception):
    pass


@dataclass(frozen=True)
class AddressData:
    street: str
    city: str
    province: str
    postal_code: str


@dataclass(frozen=True)
class HolderData:
    first_name: str
    last_name: str
    email: str
    pec: str | None
    iban: str | None
    address: AddressData


def _code(request: ContractRequest | Contract) -> str:
    return str(request.id)[:8].upper()


def _request_address(request: ContractRequest) -> AddressData | None:
    if not (request.street and request.city and request.province and request.postal_code):
        return None
    return AddressData(
        street=request.street, city=request.city, province=request.province, postal_code=request.postal_code
    )


def _point_label(energy_type: str | None, address: Address) -> str:
    from app.modules.customers.service import ENERGY_TYPE_LABELS

    kind = ENERGY_TYPE_LABELS.get(energy_type or "", "Punto di fornitura")
    return f"{kind} - {address.street}, {address.city}"


async def _customer_name(db: AsyncSession, customer: Customer | None) -> str:
    if customer is None:
        return "Cliente"
    from app.modules.customers.service import display_name_for

    profile = await db.get(CustomerProfile, customer.id)
    company = await db.get(Company, customer.id)
    return display_name_for(customer.kind, profile, company)


def _assert_draft(request: ContractRequest) -> None:
    if request.status != "DRAFT":
        raise ContractRequestError(
            "La pratica è già stata inviata: i contratti e le offerte scelte non si possono più modificare. "
            "Per aggiungere un altro contratto apri una nuova pratica."
        )


async def list_points(db: AsyncSession, *, request: ContractRequest, include_cancelled: bool = False) -> list[Contract]:
    stmt = select(Contract).where(Contract.contract_request_id == request.id).order_by(Contract.created_at)
    if not include_cancelled:
        # Hide points withdrawn while in draft; contracts cancelled after
        # activation remain part of the request.
        stmt = stmt.where(~((Contract.status == "CANCELLED") & (Contract.activated_at.is_(None))))
    return list((await db.execute(stmt)).scalars())


# --- Creation and holder data ------------------------------------------------


async def create_request(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    customer_id: uuid.UUID,
    holder: HolderData,
    actor_user_id: uuid.UUID,
    actor_role: str,
    promoter_agent_id: uuid.UUID | None,
    points_count: int = 1,
    product_version_id: uuid.UUID | None = None,
) -> ContractRequest:
    """Open a DRAFT request with holder, address and `points_count` DRAFT
    contracts; `product_version_id`, if given, is preselected on each.

    In self-service the referrer is resolved first, so a customer with no
    active sponsor is told before filling anything in. Commits."""
    if promoter_agent_id is None:
        try:
            await contract_service.resolve_self_service_producer(
                db, organization_id=organization_id, customer_id=customer_id
            )
        except contract_service.SelfServiceContractError as exc:
            raise ContractRequestError(str(exc)) from exc

    request = ContractRequest(
        organization_id=organization_id,
        customer_id=customer_id,
        status="DRAFT",
        holder_first_name=holder.first_name,
        holder_last_name=holder.last_name,
        email=holder.email,
        pec=holder.pec,
        iban=holder.iban,
        street=holder.address.street,
        city=holder.address.city,
        province=holder.address.province,
        postal_code=holder.address.postal_code,
        created_by_user_id=actor_user_id,
        created_by_role=actor_role,
        activated_by_promoter_id=promoter_agent_id,
        updated_at=utcnow(),
    )
    db.add(request)
    await db.flush()
    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="contract_request.created", entity_type="contract_request", entity_id=str(request.id),
        new_value={"customer_id": str(customer_id), "created_by_role": actor_role, "points": points_count},
    )
    await db.commit()
    await db.refresh(request)
    await set_points_count(db, request=request, count=points_count, actor_user_id=actor_user_id)
    if product_version_id is not None:
        await set_product_for_all(
            db, request=request, product_version_id=product_version_id, actor_user_id=actor_user_id
        )
    await db.refresh(request)
    return request


async def update_holder(
    db: AsyncSession, *, request: ContractRequest, holder: HolderData, actor_user_id: uuid.UUID
) -> ContractRequest:
    """Update holder data and address while in DRAFT and propagate them to
    every point, except points moved to their own address. Commits."""
    _assert_draft(request)
    previous_address = _request_address(request)
    request.holder_first_name = holder.first_name
    request.holder_last_name = holder.last_name
    request.email = holder.email
    request.pec = holder.pec
    request.iban = holder.iban
    request.street = holder.address.street
    request.city = holder.address.city
    request.province = holder.address.province
    request.postal_code = holder.address.postal_code
    request.updated_at = utcnow()
    for contract in await list_points(db, request=request):
        contract.holder_first_name = holder.first_name
        contract.holder_last_name = holder.last_name
        contract.email = holder.email
        contract.pec = holder.pec
        contract.iban = holder.iban
        contract.updated_at = utcnow()
        supply_point = await db.get(SupplyPoint, contract.supply_point_id)
        address = await db.get(Address, supply_point.supply_address_id) if supply_point else None
        if address is not None and (
            previous_address is None
            or (address.street, address.city, address.province, address.postal_code)
            == (previous_address.street, previous_address.city, previous_address.province, previous_address.postal_code)
        ):
            _apply_address(address, holder.address)
            supply_point.label = _point_label(supply_point.energy_type, address)
    await audit_service.record(
        db, organization_id=request.organization_id, actor_user_id=actor_user_id,
        action="contract_request.holder_updated", entity_type="contract_request", entity_id=str(request.id),
    )
    await db.commit()
    await db.refresh(request)
    return request


def _apply_address(address: Address, data: AddressData) -> None:
    address.street = data.street.strip()
    address.city = data.city.strip()
    address.province = data.province.strip().upper()
    address.postal_code = data.postal_code.strip()


# --- Supply points -----------------------------------------------------------


async def _producer_for_new_point(
    db: AsyncSession, *, request: ContractRequest
) -> tuple[uuid.UUID, uuid.UUID | None]:
    """Producer for a new point, resolved as for a single contract: the
    assisting promoter or the customer's referrer, falling back to the
    nearest active sponsor (returned as the substituted agent for auditing)."""
    from app.modules.network import service as network_service

    if request.activated_by_promoter_id is not None:
        promoter = await db.get(AgentProfile, request.activated_by_promoter_id)
        if promoter is not None and promoter.status == "ACTIVE":
            return promoter.id, None
        nearest = await network_service.resolve_nearest_active_agent(
            db, organization_id=request.organization_id, agent_id=request.activated_by_promoter_id
        )
        if nearest is None:
            raise ContractRequestError(
                "Il promoter che ha aperto questa pratica non è più attivo e non c'è un referente attivo sopra di lui. "
                "Contatta l'assistenza."
            )
        return nearest.id, request.activated_by_promoter_id
    try:
        return await contract_service.resolve_self_service_producer(
            db, organization_id=request.organization_id, customer_id=request.customer_id
        )
    except contract_service.SelfServiceContractError as exc:
        raise ContractRequestError(str(exc)) from exc


async def _load_package(db: AsyncSession, *, request: ContractRequest, product_version_id: uuid.UUID) -> tuple[ProductVersion, Product]:
    version = await db.get(ProductVersion, product_version_id)
    product = await db.get(Product, version.product_id) if version is not None else None
    if version is None or product is None or product.organization_id != request.organization_id:
        raise ContractRequestError("Contratto non trovato nel catalogo.")
    if product.category != "INTERNAL":
        raise ContractRequestError(
            "Solo i contratti SOSNET si attivano da qui -- gli altri prodotti si acquistano nello Shop."
        )
    if product.status != "ACTIVE" or version.status != "ACTIVE":
        raise ContractRequestError(f"Il contratto “{version.name}” non è più disponibile.")
    customer = await db.get(Customer, request.customer_id)
    if not pricing.product_allows_customer_kind(product.customer_type, customer.kind if customer else None):
        raise ContractRequestError(
            f"Il contratto “{version.name}” non è disponibile per la tipologia di questo cliente."
        )
    return version, product


async def add_point(db: AsyncSession, *, request: ContractRequest, actor_user_id: uuid.UUID) -> Contract:
    """Add a supply point at the request address with a DRAFT contract and
    no package yet. Commits."""
    from app.modules.customers.models import SupplyPoint as SupplyPointModel

    _assert_draft(request)
    address_data = _request_address(request)
    if address_data is None:
        raise ContractRequestError("Inserisci l'indirizzo prima di aggiungere i contratti.")
    if len(await list_points(db, request=request)) >= MAX_POINTS_PER_REQUEST:
        raise ContractRequestError(
            f"Una pratica può contenere al massimo {MAX_POINTS_PER_REQUEST} contratti: per gli altri apri una seconda pratica."
        )
    producer_agent_id, substituted_for = await _producer_for_new_point(db, request=request)

    address = Address(organization_id=request.organization_id, customer_id=request.customer_id, kind="SUPPLY",
                      street="", city="", province="", postal_code="")
    _apply_address(address, address_data)
    db.add(address)
    await db.flush()
    supply_point = SupplyPointModel(
        organization_id=request.organization_id,
        customer_id=request.customer_id,
        energy_type=None,
        supply_address_id=address.id,
        label=_point_label(None, address),
    )
    db.add(supply_point)
    await db.flush()

    try:
        contract = await contract_service.create_contract(
            db, organization_id=request.organization_id, customer_id=request.customer_id,
            supply_point_id=supply_point.id, product_version_id=None,
            producer_agent_id=producer_agent_id, actor_user_id=actor_user_id,
            correlation_id=str(uuid.uuid4()), contract_request_id=request.id, notify_staff=False,
            email=request.email, holder_first_name=request.holder_first_name,
            holder_last_name=request.holder_last_name, pec=request.pec, iban=request.iban,
            created_by_role=request.created_by_role, activated_by_promoter_id=request.activated_by_promoter_id,
        )
    except contract_service.InvalidProducerAgentError as exc:
        raise ContractRequestError(str(exc)) from exc
    if substituted_for is not None:
        await contract_service.record_producer_substitution(
            db, organization_id=request.organization_id, contract=contract, actor_user_id=actor_user_id,
            substituted_for_agent_id=substituted_for,
        )
    request.updated_at = utcnow()
    await db.commit()
    await db.refresh(contract)
    return contract


async def set_points_count(
    db: AsyncSession, *, request: ContractRequest, count: int, actor_user_id: uuid.UUID
) -> list[Contract]:
    """Add or remove points until there are exactly `count`. Removal prefers
    points without a package, newest first. Commits."""
    _assert_draft(request)
    if count < 1:
        raise ContractRequestError("Una pratica deve avere almeno un contratto.")
    if count > MAX_POINTS_PER_REQUEST:
        raise ContractRequestError(
            f"Una pratica può contenere al massimo {MAX_POINTS_PER_REQUEST} contratti: per gli altri apri una seconda pratica."
        )
    points = await list_points(db, request=request)
    while len(points) < count:
        points.append(await add_point(db, request=request, actor_user_id=actor_user_id))
    if len(points) > count:
        drafts = [p for p in points if p.status == "DRAFT"]
        # Empty ones first, newest first within each group.
        removable = sorted(drafts, key=lambda p: (p.product_version_id is not None, -p.created_at.timestamp()))
        for contract in removable[: len(points) - count]:
            await remove_point(db, request=request, contract=contract, actor_user_id=actor_user_id)
        points = await list_points(db, request=request)
    return points


async def get_point(db: AsyncSession, *, request: ContractRequest, contract_id: uuid.UUID) -> Contract:
    contract = await db.get(Contract, contract_id)
    if contract is None or contract.contract_request_id != request.id:
        raise ContractRequestError("Contratto non trovato in questa pratica.")
    return contract


async def update_point_address(
    db: AsyncSession, *, request: ContractRequest, contract: Contract, address_data: AddressData,
    actor_user_id: uuid.UUID,
) -> Contract:
    """Give one point an address different from the request's. Commits."""
    _assert_draft(request)
    if contract.status != "DRAFT":
        raise ContractRequestError("Questo contratto non si può più modificare.")
    supply_point = await db.get(SupplyPoint, contract.supply_point_id)
    address = await db.get(Address, supply_point.supply_address_id) if supply_point else None
    if supply_point is None or address is None:
        raise ContractRequestError("Punto di fornitura non trovato.")
    previous = {"street": address.street, "city": address.city}
    _apply_address(address, address_data)
    supply_point.label = _point_label(supply_point.energy_type, address)
    contract.updated_at = request.updated_at = utcnow()
    await audit_service.record(
        db, organization_id=request.organization_id, actor_user_id=actor_user_id,
        action="contract_request.point_address_updated", entity_type="contract", entity_id=str(contract.id),
        previous_value=previous, new_value={"street": address.street, "city": address.city},
    )
    await db.commit()
    await db.refresh(contract)
    return contract


async def remove_point(
    db: AsyncSession, *, request: ContractRequest, contract: Contract, actor_user_id: uuid.UUID
) -> None:
    """Withdraw a point from a draft request. The contract is CANCELLED, not
    deleted, to keep the audit trail consistent. The last point cannot be
    removed."""
    _assert_draft(request)
    if contract.status != "DRAFT":
        raise ContractRequestError("Questo contratto non si può più togliere dalla pratica.")
    if len(await list_points(db, request=request)) <= 1:
        raise ContractRequestError("Una pratica deve avere almeno un contratto.")
    await contract_service.transition_contract(
        db, organization_id=request.organization_id, contract=contract, to_status="CANCELLED",
        actor_user_id=actor_user_id, reason="Contratto tolto dalla pratica prima dell'invio", notes=None,
        correlation_id=str(uuid.uuid4()),
    )
    request.updated_at = utcnow()
    await db.commit()


async def _assign_package(db: AsyncSession, *, contract: Contract, version: ProductVersion, product: Product) -> None:
    """Set the package: it determines the point's energy type and freezes
    the price. Does not commit."""
    supply_point = await db.get(SupplyPoint, contract.supply_point_id)
    if supply_point is not None:
        supply_point.energy_type = product.energy_type
        address = await db.get(Address, supply_point.supply_address_id)
        if address is not None:
            supply_point.label = _point_label(product.energy_type, address)
    await contract_service.freeze_price(db, contract=contract, version=version)


async def set_point_product(
    db: AsyncSession, *, request: ContractRequest, contract: Contract, product_version_id: uuid.UUID,
    actor_user_id: uuid.UUID,
) -> Contract:
    """Choose or change the package for one point. Commits."""
    _assert_draft(request)
    if contract.status != "DRAFT":
        raise ContractRequestError("L'offerta di questo contratto non si può più cambiare.")
    version, product = await _load_package(db, request=request, product_version_id=product_version_id)
    previous = str(contract.product_version_id) if contract.product_version_id else None
    await _assign_package(db, contract=contract, version=version, product=product)
    request.updated_at = utcnow()
    await audit_service.record(
        db, organization_id=request.organization_id, actor_user_id=actor_user_id,
        action="contract.package_selected", entity_type="contract", entity_id=str(contract.id),
        previous_value={"product_version_id": previous},
        new_value={"product_version_id": str(version.id), "gross_amount_cents": contract.gross_amount_cents},
    )
    await db.commit()
    await db.refresh(contract)
    return contract


#: Statuses in which staff may still change the package: nothing is paid or
#: activated yet.
STAFF_REPACKAGE_STATUSES = frozenset(
    {"DRAFT", "SUBMITTED", "DOCUMENTS_PENDING", "UNDER_REVIEW", "APPROVED", "PAYMENT_PENDING"}
)


async def staff_set_point_product(
    db: AsyncSession, *, request: ContractRequest, contract: Contract, product_version_id: uuid.UUID,
    actor_user_id: uuid.UUID,
) -> Contract:
    """Admin package change, allowed after submission but never once paid,
    billed or active, since price and commissions are fixed by then. Commits."""
    if contract.paid_at is not None:
        raise ContractRequestError(
            "Questo contratto è già pagato: il pacchetto non si cambia più. Respingilo e apri una nuova pratica."
        )
    if contract.stripe_subscription_id is not None and contract.billing_stopped_at is None:
        raise ContractRequestError(
            "Gli addebiti a rate di questo contratto sono attivi: interrompili prima di cambiare il pacchetto."
        )
    if contract.status not in STAFF_REPACKAGE_STATUSES:
        raise ContractRequestError(
            f"Un contratto {contract.status} non può cambiare pacchetto."
        )
    version, product = await _load_package(db, request=request, product_version_id=product_version_id)
    previous = str(contract.product_version_id) if contract.product_version_id else None
    previous_gross = contract.gross_amount_cents
    await _assign_package(db, contract=contract, version=version, product=product)
    request.updated_at = utcnow()
    await audit_service.record(
        db, organization_id=request.organization_id, actor_user_id=actor_user_id,
        action="contract.package_changed_by_staff", entity_type="contract", entity_id=str(contract.id),
        previous_value={"product_version_id": previous, "gross_amount_cents": previous_gross},
        new_value={"product_version_id": str(version.id), "gross_amount_cents": contract.gross_amount_cents},
    )
    await db.commit()
    await db.refresh(contract)
    return contract


async def set_product_for_all(
    db: AsyncSession, *, request: ContractRequest, product_version_id: uuid.UUID, actor_user_id: uuid.UUID
) -> int:
    """Apply one package to every draft point; returns how many were set.
    Commits."""
    _assert_draft(request)
    version, product = await _load_package(db, request=request, product_version_id=product_version_id)
    applied = 0
    for contract in await list_points(db, request=request):
        if contract.status != "DRAFT":
            continue
        await _assign_package(db, contract=contract, version=version, product=product)
        applied += 1
    request.updated_at = utcnow()
    await audit_service.record(
        db, organization_id=request.organization_id, actor_user_id=actor_user_id,
        action="contract_request.package_applied_to_all", entity_type="contract_request",
        entity_id=str(request.id), new_value={"product_version_id": str(version.id), "points": applied},
    )
    await db.commit()
    return applied


# --- Submission and cancellation --------------------------------------------


async def submit_request(db: AsyncSession, *, request: ContractRequest, actor_user_id: uuid.UUID) -> ContractRequest:
    """Submit the request: all points leave DRAFT together and follow the
    single-contract flow (DOCUMENTS_PENDING, then UNDER_REVIEW once its own
    or the shared required documents are in).

    Staff receive one notification per request, not per point."""
    from app.modules.customers.models import Customer
    from app.modules.documents import service as documents_service

    _assert_draft(request)
    points = await list_points(db, request=request)
    if not points:
        raise ContractRequestError("Aggiungi almeno un punto di fornitura prima di inviare la pratica.")
    missing = [p for p in points if p.product_version_id is None]
    if missing:
        raise ContractRequestError(
            f"Scegli l'offerta da attivare per {'il contratto' if len(missing) == 1 else f'i {len(missing)} contratti'} "
            "ancora senza, poi invia la pratica."
        )
    if not (request.holder_first_name and request.holder_last_name and request.email and _request_address(request)):
        raise ContractRequestError("Completa i dati dell'intestatario e l'indirizzo prima di inviare la pratica.")

    for contract in points:
        if contract.status != "DRAFT":
            continue
        contract = await contract_service.transition_contract(
            db, organization_id=request.organization_id, contract=contract, to_status="SUBMITTED",
            actor_user_id=actor_user_id, reason=f"Pratica {_code(request)} inviata", notes=None,
            correlation_id=str(uuid.uuid4()),
        )
        contract = await contract_service.transition_contract(
            db, organization_id=request.organization_id, contract=contract, to_status="DOCUMENTS_PENDING",
            actor_user_id=actor_user_id, reason=None, notes=None, correlation_id=str(uuid.uuid4()),
        )
        await documents_service.maybe_advance_to_under_review(
            db, organization_id=request.organization_id, contract_id=contract.id, actor_user_id=actor_user_id
        )

    await db.refresh(request)
    if request.status == "DRAFT":
        # transition_contract normally promotes the request when its last
        # draft leaves; this covers a request with no drafts left to move.
        request.status = "SUBMITTED"
        request.submitted_at = utcnow()
    customer = await db.get(Customer, request.customer_id)
    name = await _customer_name(db, customer)
    await notifications_service.notify_roles(
        db, organization_id=request.organization_id, roles=notifications_service.STAFF_NOTIFY_ROLES,
        type_="CONTRACT_CREATED", entity_type="contract_request", entity_id=request.id,
        title=f"Nuova pratica {_code(request)}: {len(points)} {'contratto' if len(points) == 1 else 'contratti'}",
        body=f"{name} ha inviato una pratica di attivazione con {len(points)} contratt{'o' if len(points) == 1 else 'i'}.",
        exclude_user_id=actor_user_id,
    )
    await audit_service.record(
        db, organization_id=request.organization_id, actor_user_id=actor_user_id,
        action="contract_request.submitted", entity_type="contract_request", entity_id=str(request.id),
        new_value={"points": len(points)},
    )
    # When filled in on the customer's behalf, the customer still pays, so
    # they are told the request is waiting for them.
    filled_in_for_customer = request.created_by_role in ("PROMOTER", "ADMIN") and customer is not None
    promoter_name = None
    if filled_in_for_customer:
        if request.activated_by_promoter_id is not None:
            promoter = await db.get(AgentProfile, request.activated_by_promoter_id)
            promoter_name = promoter.display_name if promoter else None
        who = promoter_name or ("Il tuo promoter" if request.created_by_role == "PROMOTER" else "SOSNET")
        if customer.user_id is not None:
            await notifications_service.notify_user(
                db, organization_id=request.organization_id, user_id=customer.user_id,
                type_="CONTRACT_CREATED", entity_type="contract_request", entity_id=request.id,
                title="I tuoi contratti sono pronti da pagare",
                body=(
                    f"{who} ha compilato per te la pratica {_code(request)} con "
                    f"{len(points)} {'contratto' if len(points) == 1 else 'contratti'}. Controllala in “I miei Contratti” e procedi con il pagamento."
                ),
            )
    await db.commit()
    await db.refresh(request)
    if filled_in_for_customer:
        _email_customer_about_promoter_pratica(
            request=request, customer=customer,
            promoter_name=promoter_name or (None if request.created_by_role == "PROMOTER" else "SOSNET"),
            points=points,
        )
    return request


def _email_customer_about_promoter_pratica(
    *, request: ContractRequest, customer: Customer, promoter_name: str | None, points: list[Contract]
) -> None:
    """Email the customer that a request prepared on their behalf awaits
    payment. Best-effort, sent after commit."""
    import html

    from app.foundation.config import get_settings
    from app.foundation.email import send_html_email_best_effort
    from app.foundation.email_templates import render_email

    to = request.email or customer.email
    if not to:
        return
    who = html.escape(promoter_name or "Il tuo promoter")
    heading_who = "Il tuo promoter ha preparato i tuoi contratti" if promoter_name != "SOSNET" else "Abbiamo preparato i tuoi contratti"
    total = sum(int(p.gross_amount_cents or 0) for p in points)
    body_html = (
        f"<p>{who} ha preparato per te la pratica <strong>{_code(request)}</strong> con "
        f"<strong>{len(points)} {'contratto' if len(points) == 1 else 'contratti'}</strong>, per un totale di <strong>{total / 100:.2f} €</strong>.</p>"
        "<p>Ogni contratto è a sé. Accedi alla tua area, controlla i contratti in "
        "<em>I miei Contratti</em> e completa il pagamento: puoi pagare in un'unica soluzione o a rate. "
        "Se non hai ancora impostato la password, usa il link di invito che ti è arrivato.</p>"
    )
    send_html_email_best_effort(
        context=f"Promoter pratica email (request={request.id})",
        to=to,
        subject="I tuoi contratti SOSNET sono pronti - SOSNET",
        html_body=render_email(
            preheader=heading_who,
            heading="I tuoi contratti sono pronti",
            body_html=body_html,
            cta_label="Vai ai miei contratti",
            cta_url=f"{get_settings().public_app_base_url}/customer?tab=contracts",
        ),
        text_body=(
            f"{promoter_name or 'Il tuo promoter'} ha preparato per te la pratica {_code(request)} con "
            f"{len(points)} {'contratto' if len(points) == 1 else 'contratti'}. Accedi a I miei Contratti per controllarla e pagare."
        ),
    )


async def send_payment_receipt(
    db: AsyncSession, *, request: ContractRequest, contracts: list[Contract], method: str
) -> None:
    """Email the customer a receipt for a request payment: what was paid now
    for each contract, how, and what is left if they pay in instalments.
    Best-effort, sent after the payment is committed."""
    import html

    from app.foundation.config import get_settings
    from app.foundation.email import send_html_email_best_effort
    from app.foundation.email_templates import render_email
    from app.modules.contracts import instalments as instalments_service
    from app.modules.customers.models import SupplyPoint

    customer = await db.get(Customer, request.customer_id)
    to = request.email or (customer.email if customer else None)
    if not to:
        return

    def euro(cents: int) -> str:
        return f"{cents / 100:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")

    rows_html = []
    paid_now = 0
    later_lines = []
    plan_label = None
    for contract in contracts:
        version = await db.get(ProductVersion, contract.product_version_id) if contract.product_version_id else None
        point = await db.get(SupplyPoint, contract.supply_point_id) if contract.supply_point_id else None
        rows = await instalments_service.list_instalments(db, contract_id=contract.id)
        first = next((r for r in rows if r.status == "PAID"), None)
        amount = int(first.amount_cents) if first else int(contract.gross_amount_cents or 0)
        paid_now += amount
        plan = payment_plans.plan_by_key(contract.payment_plan)
        plan_label = plan.label if plan else plan_label
        remaining = [r for r in rows if r.status != "PAID"]
        if remaining:
            later_lines.append(f"{len(remaining)} rate mensili da {euro(int(remaining[0].amount_cents))} per "
                               f"{html.escape(version.name if version else 'il contratto')}")
        name = html.escape(version.name if version else "Contratto")
        detail = html.escape(point.label) if point and point.label else f"Contratto {str(contract.id)[:8].upper()}"
        rows_html.append(
            f"<tr><td style='padding:10px 0; border-bottom:1px solid #e4ebf3;'><strong>{name}</strong><br>"
            f"<span style='font-size:13px; color:#556b7a;'>{detail}</span></td>"
            f"<td align='right' style='padding:10px 0; border-bottom:1px solid #e4ebf3; font-weight:700;'>{euro(amount)}</td></tr>"
        )

    method_label = "Carta di pagamento" if method == "CARD" else "Bonifico bancario"
    later_html = (
        "<p style='margin:16px 0 0 0; font-size:14px;'><strong>Prossimi addebiti:</strong><br>"
        + "<br>".join(later_lines) + "<br><span style='color:#556b7a;'>Ti addebiteremo in automatico ogni mese.</span></p>"
        if later_lines else ""
    )
    body_html = (
        f"<p>Grazie! Abbiamo ricevuto il pagamento della pratica <strong>{_code(request)}</strong>.</p>"
        "<table role='presentation' width='100%' cellpadding='0' cellspacing='0' style='margin:8px 0 4px 0; font-size:15px;'>"
        + "".join(rows_html)
        + f"<tr><td style='padding:14px 0 0 0; font-weight:800;'>Totale pagato</td>"
          f"<td align='right' style='padding:14px 0 0 0; font-size:18px; font-weight:800; color:#0a54e0;'>{euro(paid_now)}</td></tr>"
        "</table>"
        f"<p style='margin:14px 0 0 0; font-size:14px; color:#556b7a;'>Metodo: {method_label}"
        + (f" &middot; Modalità: {html.escape(plan_label)}" if plan_label else "")
        + f" &middot; Data: {utcnow().strftime('%d/%m/%Y')}</p>"
        + later_html
        + "<p style='margin:16px 0 0 0;'>Ogni contratto si attiva appena i suoi documenti sono approvati: "
          "ti avvisiamo noi. Trovi la ricevuta anche nella tua area, in <em>Movimenti contabili</em>.</p>"
    )
    send_html_email_best_effort(
        context=f"Contract request receipt (request={request.id})",
        to=to,
        subject=f"Ricevuta di pagamento pratica {_code(request)} - SOSNET",
        html_body=render_email(
            preheader=f"Pagamento ricevuto: {euro(paid_now)} per la pratica {_code(request)}",
            heading="Pagamento ricevuto, grazie",
            body_html=body_html,
            cta_label="Vai ai miei contratti",
            cta_url=f"{get_settings().public_app_base_url}/customer?tab=contracts",
        ),
        text_body=(
            f"Abbiamo ricevuto il pagamento della pratica {_code(request)}: {euro(paid_now)} "
            f"({method_label}). Ogni contratto si attiva appena i suoi documenti sono approvati."
        ),
    )


async def cancel_request(db: AsyncSession, *, request: ContractRequest, actor_user_id: uuid.UUID) -> ContractRequest:
    """Abandon a draft request and its draft points. Submitted requests are
    never cancelled as a whole; each contract is handled individually."""
    _assert_draft(request)
    for contract in await list_points(db, request=request):
        if contract.status == "DRAFT":
            await contract_service.transition_contract(
                db, organization_id=request.organization_id, contract=contract, to_status="CANCELLED",
                actor_user_id=actor_user_id, reason="Pratica annullata prima dell'invio", notes=None,
                correlation_id=str(uuid.uuid4()),
            )
    request.status = "CANCELLED"
    request.cancelled_at = request.updated_at = utcnow()
    await audit_service.record(
        db, organization_id=request.organization_id, actor_user_id=actor_user_id,
        action="contract_request.cancelled", entity_type="contract_request", entity_id=str(request.id),
    )
    await db.commit()
    await db.refresh(request)
    return request


# --- Payment -----------------------------------------------------------------


def payable_points(points: list[Contract]) -> list[Contract]:
    return [c for c in points if contract_service.is_payable(c)]


@dataclass(frozen=True)
class RequestPlanOption:
    plan: payment_plans.PaymentPlan
    instalment_cents: int
    total_cents: int
    rounding_difference_cents: int
    available: bool
    unavailable_reason: str | None
    #: Undiscounted price and single-payment discount.
    list_total_cents: int = 0
    discount_percentage: int = 0
    discount_cents: int = 0


def plan_options(points: list[Contract], *, discount_percentage: int = 0) -> list[RequestPlanOption]:
    """Every plan priced for these contracts: each contract is split on its
    own (matching its future schedule) and the results are summed."""
    options = []
    for plan in payment_plans.PAYMENT_PLANS:
        breakdowns = [
            payment_plans.breakdown_for(plan, int(c.gross_amount_cents or 0), discount_percentage=discount_percentage)
            for c in points
        ]
        reason = None
        if any(b.instalment_cents <= 0 for b in breakdowns):
            reason = "Importo troppo basso per questa modalità."
        elif plan.instalments > 1 and len(points) > MAX_SUBSCRIPTION_LINES:
            reason = (
                f"A rate si possono pagare al massimo {MAX_SUBSCRIPTION_LINES} contratti insieme: "
                "scegli la soluzione unica oppure dividi i punti in due pratiche."
            )
        options.append(
            RequestPlanOption(
                plan=plan,
                instalment_cents=sum(b.instalment_cents for b in breakdowns),
                total_cents=sum(b.total_cents for b in breakdowns),
                rounding_difference_cents=sum(b.rounding_difference_cents for b in breakdowns),
                available=bool(points) and reason is None,
                unavailable_reason=reason,
                list_total_cents=sum(int(c.gross_amount_cents or 0) for c in points),
                discount_percentage=discount_percentage if any(b.discount_cents for b in breakdowns) else 0,
                discount_cents=sum(b.discount_cents for b in breakdowns),
            )
        )
    return options


async def cashback_total_cents(db: AsyncSession, *, points: list[Contract], discount_percentage: int = 0) -> int:
    """SosnetCash earned by these contracts, computed on the amount paid
    (after `discount_percentage`, if any)."""
    total = 0
    for contract in points:
        if contract.product_version_id is None or not contract.gross_amount_cents:
            continue
        version = await db.get(ProductVersion, contract.product_version_id)
        if version is not None:
            gross = int(contract.gross_amount_cents)
            paid = gross - payment_plans.discount_cents_for(gross, discount_percentage)
            total += pricing.contract_cashback_cents(version=version, gross_amount_cents=paid)
    return total


async def apply_checkout(
    db: AsyncSession,
    *,
    checkout: ContractRequestCheckout,
    stripe_invoice_id: str | None,
    stripe_subscription_id: str | None,
    stripe_customer_id: str | None,
    subscription_items: dict[str, str],
) -> str:
    """Record a completed request Checkout Session: each covered contract is
    paid as if on its own (first instalment, SosnetCash, activation if
    approved).

    `subscription_items` maps contract id to Stripe subscription item id so
    later invoice lines find their contract
    (service.py::record_subscription_invoice).

    Contracts already paid by another session are skipped and staff are told
    to refund them. Returns a text outcome. Idempotent. Commits."""
    from app.modules.contracts import service as contracts_service

    if checkout.completed_at is not None:
        return f"pratica {str(checkout.contract_request_id)[:8].upper()}: pagamento già registrato"

    plan = payment_plans.plan_by_key(checkout.payment_plan)
    request = await db.get(ContractRequest, checkout.contract_request_id)
    paid: list[Contract] = []
    duplicates: list[Contract] = []
    for line in checkout.lines:
        contract = await db.get(Contract, uuid.UUID(line["contract_id"]))
        if contract is None or contract.contract_request_id != checkout.contract_request_id:
            continue
        if contract.paid_at is not None:
            duplicates.append(contract)
            continue
        contract.payment_plan = checkout.payment_plan
        contract.payment_method = "CARD"
        contract.payment_discount_cents = (
            int(line.get("discount_cents") or 0) if plan is not None and plan.instalments <= 1 else 0
        )
        if stripe_subscription_id:
            contract.stripe_subscription_id = stripe_subscription_id
            contract.stripe_subscription_item_id = subscription_items.get(str(contract.id))
            contract.stripe_customer_id = stripe_customer_id
        contract.updated_at = utcnow()
        await db.commit()
        contract = await contracts_service.record_card_payment(
            db, organization_id=checkout.organization_id, contract=contract,
            stripe_invoice_id=stripe_invoice_id, notify_staff=False,
        )
        if plan is not None and plan.instalments > 1:
            await contracts_service.credit_contract_instalment_cashback(
                db, organization_id=checkout.organization_id, contract=contract, instalment_number=1
            )
        paid.append(contract)

    code = str(checkout.contract_request_id)[:8].upper()
    checkout.completed_at = utcnow()
    checkout.stripe_subscription_id = stripe_subscription_id
    checkout.stripe_customer_id = stripe_customer_id
    outcome = f"pratica {code}: {len(paid)} contratti pagati"
    if duplicates:
        outcome += f", {len(duplicates)} già pagati in precedenza"
    checkout.outcome = outcome[:255]

    if paid:
        await notifications_service.notify_roles(
            db, organization_id=checkout.organization_id, roles=notifications_service.STAFF_NOTIFY_ROLES,
            type_="CONTRACT_PAID_BEFORE_APPROVAL", entity_type="contract_request", entity_id=checkout.contract_request_id,
            title=f"Pratica {code} pagata: {len(paid)} {'contratto' if len(paid) == 1 else 'contratti'}",
            body=(
                f"Pagamento con carta ({plan.label.lower() if plan else checkout.payment_plan}). "
                "Ogni contratto si attiva appena approvi i suoi documenti e accetti la sua anteprima provvigioni."
            ),
        )
        customer = await db.get(Customer, request.customer_id) if request else None
        if customer is not None and customer.user_id is not None:
            await notifications_service.notify_user(
                db, organization_id=checkout.organization_id, user_id=customer.user_id,
                type_="CONTRACT_PAID_BEFORE_APPROVAL", entity_type="contract_request",
                entity_id=checkout.contract_request_id,
                title="Pagamento ricevuto",
                body=(
                    f"Abbiamo ricevuto il pagamento della pratica {code}. "
                    "Ogni contratto si attiva appena i suoi documenti sono approvati."
                ),
            )
    if duplicates:
        await notifications_service.notify_roles(
            db, organization_id=checkout.organization_id, roles=notifications_service.STAFF_NOTIFY_ROLES,
            type_="CONTRACT_PAID_REJECTED", entity_type="contract_request", entity_id=checkout.contract_request_id,
            title=f"Pagamento doppio sulla pratica {code}",
            body=(
                f"{len(duplicates)} contratti erano già stati pagati: "
                + ", ".join(_code(c) for c in duplicates)
                + ". Rimborsa quelle righe su Stripe" + (" e interrompi i loro addebiti." if stripe_subscription_id else ".")
            ),
        )
    await db.commit()
    if paid and request is not None:
        await send_payment_receipt(db, request=request, contracts=paid, method="CARD")
    return outcome


# --- Bank transfer -----------------------------------------------------------


class BankTransferError(Exception):
    pass


def bank_transfer_pending(request: ContractRequest, points: list[Contract]) -> bool:
    """Transfer announced, unconfirmed, and still payable (a later card
    payment also settles it)."""
    return (
        request.bank_transfer_requested_at is not None
        and request.bank_transfer_confirmed_at is None
        and any(c.payment_method == "BANK_TRANSFER" and contract_service.is_payable(c) for c in points)
    )


async def request_bank_transfer(
    db: AsyncSession, *, request: ContractRequest, actor_user_id: uuid.UUID
) -> ContractRequest:
    """Customer chooses to pay the whole request by transfer; the
    single-payment discount is frozen on each contract. Nothing is paid until
    an administrator confirms receipt. Commits."""
    from app.modules.organizations import service as organizations_service

    if not await organizations_service.is_bank_transfer_configured(db, organization_id=request.organization_id):
        raise BankTransferError("Il pagamento con bonifico non è disponibile al momento.")
    points = payable_points(await list_points(db, request=request))
    if not points:
        raise BankTransferError("In questa pratica non c'è nessun contratto da pagare.")
    percentage = await organizations_service.get_contract_full_payment_discount_percentage(
        db, organization_id=request.organization_id
    )
    total = 0
    for contract in points:
        gross = int(contract.gross_amount_cents or 0)
        contract.payment_plan = payment_plans.PLAN_FULL
        contract.payment_method = "BANK_TRANSFER"
        contract.payment_discount_cents = payment_plans.discount_cents_for(gross, percentage)
        contract.updated_at = utcnow()
        total += gross - contract.payment_discount_cents
    request.bank_transfer_requested_at = utcnow()
    request.bank_transfer_total_cents = total
    request.bank_transfer_confirmed_at = None
    request.bank_transfer_confirmed_by_user_id = None
    request.updated_at = utcnow()
    code = _code(request)
    await audit_service.record(
        db, organization_id=request.organization_id, actor_user_id=actor_user_id,
        action="contract_request.bank_transfer_requested", entity_type="contract_request",
        entity_id=str(request.id), new_value={"total_cents": total, "contracts": len(points), "discount": percentage},
    )
    await notifications_service.notify_roles(
        db, organization_id=request.organization_id, roles=notifications_service.STAFF_NOTIFY_ROLES,
        type_="CONTRACT_REQUEST_BANK_TRANSFER", entity_type="contract_request", entity_id=request.id,
        title=f"Pratica {code}: il cliente paga con bonifico",
        body=f"{total / 100:.2f} EUR per {len(points)} {'contratto' if len(points) == 1 else 'contratti'}. "
             "Conferma quando lo ricevi, dalla pratica.",
        exclude_user_id=actor_user_id,
    )
    await db.commit()
    await db.refresh(request)
    return request


async def upload_bank_transfer_proof(
    db: AsyncSession, *, request: ContractRequest, file_bytes: bytes, content_type: str, original_filename: str,
    actor_user_id: uuid.UUID,
) -> ContractRequest:
    from app.foundation.storage import UploadValidationError
    from app.foundation.storage import upload_document as storage_upload_document

    if not bank_transfer_pending(request, await list_points(db, request=request)):
        raise BankTransferError("La ricevuta si carica per una pratica in attesa di bonifico.")
    try:
        key = storage_upload_document(
            file_bytes=file_bytes, content_type=content_type,
            key_prefix=f"contract-request-payment-proofs/{request.id}",
        )
    except UploadValidationError as exc:
        raise BankTransferError(str(exc)) from exc
    request.payment_proof_storage_key = key
    request.payment_proof_original_filename = original_filename[:255]
    request.payment_proof_uploaded_at = utcnow()
    await notifications_service.notify_roles(
        db, organization_id=request.organization_id, roles=notifications_service.STAFF_NOTIFY_ROLES,
        type_="CONTRACT_REQUEST_BANK_TRANSFER", entity_type="contract_request", entity_id=request.id,
        title=f"Pratica {_code(request)}: ricevuta del bonifico caricata", body=None, exclude_user_id=actor_user_id,
    )
    await db.commit()
    await db.refresh(request)
    return request


def payment_proof_url(request: ContractRequest) -> str | None:
    from app.foundation.storage import generate_presigned_document_url

    if not request.payment_proof_storage_key:
        return None
    return generate_presigned_document_url(storage_key=request.payment_proof_storage_key, expires_in_seconds=300)


async def confirm_bank_transfer(
    db: AsyncSession, *, request: ContractRequest, actor_user_id: uuid.UUID
) -> list[Contract]:
    """Admin confirms the transfer: each contract announced for transfer is
    recorded as a card payment would be (discounted instalment, SosnetCash,
    activation if approved). Returns the paid contracts. Commits."""
    from app.modules.contracts import service as contracts_service

    points = await list_points(db, request=request)
    if not bank_transfer_pending(request, points):
        raise BankTransferError("Questa pratica non ha un bonifico in attesa di conferma.")
    paid = []
    for contract in points:
        if contract.payment_method != "BANK_TRANSFER" or not contract_service.is_payable(contract):
            continue
        contract = await contracts_service.record_card_payment(
            db, organization_id=request.organization_id, contract=contract, notify_staff=False,
            bank_transfer_confirmed_by=actor_user_id,
        )
        paid.append(contract)
    request.bank_transfer_confirmed_at = utcnow()
    request.bank_transfer_confirmed_by_user_id = actor_user_id
    request.updated_at = utcnow()
    code = _code(request)
    await audit_service.record(
        db, organization_id=request.organization_id, actor_user_id=actor_user_id,
        action="contract_request.bank_transfer_confirmed", entity_type="contract_request",
        entity_id=str(request.id), new_value={"contracts": [str(c.id) for c in paid]},
    )
    customer = await db.get(Customer, request.customer_id)
    if customer is not None and customer.user_id is not None:
        await notifications_service.notify_user(
            db, organization_id=request.organization_id, user_id=customer.user_id,
            type_="CONTRACT_PAID_BEFORE_APPROVAL", entity_type="contract_request", entity_id=request.id,
            title="Bonifico ricevuto",
            body=f"Abbiamo ricevuto il bonifico della pratica {code}. "
                 "Ogni contratto si attiva appena i suoi documenti sono approvati.",
        )
    await db.commit()
    await db.refresh(request)
    if paid:
        await send_payment_receipt(db, request=request, contracts=paid, method="BANK_TRANSFER")
    return paid


# --- Reads -------------------------------------------------------------------


async def _instalment_summary(db: AsyncSession, contract_ids: list[uuid.UUID]) -> dict[uuid.UUID, dict]:
    if not contract_ids:
        return {}
    rows = list(
        (await db.execute(select(ContractInstalment).where(ContractInstalment.contract_id.in_(contract_ids)))).scalars()
    )
    out: dict[uuid.UUID, dict] = {}
    for row in rows:
        entry = out.setdefault(row.contract_id, {"total": row.instalments_total, "paid": 0, "failed": 0})
        if row.status == "PAID":
            entry["paid"] += 1
        elif row.status == "FAILED":
            entry["failed"] += 1
    return out


async def summaries(db: AsyncSession, requests: list[ContractRequest]) -> list[dict]:
    """List rows for every audience, derived from the contracts rather than
    stored: point counts by state, totals and payment status."""
    if not requests:
        return []
    request_ids = [r.id for r in requests]
    contracts = list(
        (
            await db.execute(
                select(Contract).where(Contract.contract_request_id.in_(request_ids)).order_by(Contract.created_at)
            )
        ).scalars()
    )
    by_request: dict[uuid.UUID, list[Contract]] = {}
    for c in contracts:
        if c.status == "CANCELLED" and c.activated_at is None:
            continue
        by_request.setdefault(c.contract_request_id, []).append(c)

    customer_ids = {r.customer_id for r in requests}
    customers = {
        c.id: c for c in (await db.execute(select(Customer).where(Customer.id.in_(customer_ids)))).scalars()
    }
    customer_names = {cid: await _customer_name(db, customers.get(cid)) for cid in customer_ids}
    agent_ids = {r.activated_by_promoter_id for r in requests if r.activated_by_promoter_id}
    agent_names = (
        {
            a.id: a.display_name
            for a in (await db.execute(select(AgentProfile).where(AgentProfile.id.in_(agent_ids)))).scalars()
        }
        if agent_ids
        else {}
    )
    instalments = await _instalment_summary(db, [c.id for c in contracts])

    out = []
    for r in requests:
        points = by_request.get(r.id, [])
        live = [c for c in points if c.status not in ("REJECTED", "CANCELLED")]
        statuses: dict[str, int] = {}
        for c in points:
            statuses[c.status] = statuses.get(c.status, 0) + 1
        out.append({
            "id": r.id,
            "code": _code(r),
            "customer_id": r.customer_id,
            "customer_name": customer_names.get(r.customer_id),
            "customer_kind": customers[r.customer_id].kind if r.customer_id in customers else None,
            "status": r.status,
            "created_at": r.created_at,
            "submitted_at": r.submitted_at,
            "updated_at": r.updated_at,
            "created_by_role": r.created_by_role,
            "activated_by_promoter_id": r.activated_by_promoter_id,
            "activated_by_promoter_name": agent_names.get(r.activated_by_promoter_id) if r.activated_by_promoter_id else None,
            "holder_name": " ".join(x for x in (r.holder_first_name, r.holder_last_name) if x) or None,
            "points_total": len(points),
            "points_by_status": statuses,
            "points_active": sum(1 for c in points if c.status in ("ACTIVE", "RENEWED")),
            "points_to_review": statuses.get("UNDER_REVIEW", 0),
            "points_documents_pending": statuses.get("DOCUMENTS_PENDING", 0),
            "points_without_package": sum(1 for c in points if c.product_version_id is None),
            "points_paid": sum(1 for c in live if c.paid_at is not None),
            "points_payable": sum(1 for c in live if contract_service.is_payable(c)),
            "total_gross_cents": sum(int(c.gross_amount_cents or 0) for c in live),
            "payment_plans": sorted({c.payment_plan for c in live if c.paid_at is not None and c.payment_plan}),
            "instalments_failed": sum(instalments.get(c.id, {}).get("failed", 0) for c in live),
            "bank_transfer_pending": bank_transfer_pending(r, points),
            "bank_transfer_total_cents": r.bank_transfer_total_cents,
            "bank_transfer_requested_at": r.bank_transfer_requested_at,
            "payment_proof_uploaded_at": r.payment_proof_uploaded_at,
            "total_paid_cents": sum(
                int(c.gross_amount_cents or 0) - int(c.payment_discount_cents or 0)
                for c in live if c.paid_at is not None
            ),
        })
    return out


async def detail(db: AsyncSession, *, request: ContractRequest, include_checkouts: bool) -> dict:
    """Full request view: summary, holder, and each point with address,
    package, price, document completeness and instalments."""
    from app.modules.documents import service as documents_service

    [summary] = await summaries(db, [request])
    points = await list_points(db, request=request)
    rows = await contract_service.to_read_dicts(db, points)
    customer = await db.get(Customer, request.customer_id)
    kind = customer.kind if customer else "PRIVATE"
    instalments = await _instalment_summary(db, [c.id for c in points])

    enriched = []
    for contract, row in zip(points, rows, strict=True):
        supply_point = await db.get(SupplyPoint, contract.supply_point_id)
        address = await db.get(Address, supply_point.supply_address_id) if supply_point else None
        slots = await documents_service.get_contract_documents_status(
            db, organization_id=request.organization_id, contract=contract, customer_kind=kind
        )
        product = None
        if contract.product_version_id is not None:
            version = await db.get(ProductVersion, contract.product_version_id)
            product = await db.get(Product, version.product_id) if version else None
        enriched.append({
            **row,
            "position": len(enriched) + 1,
            "meter_number": supply_point.meter_number if supply_point else None,
            "street": address.street if address else None,
            "city": address.city if address else None,
            "province": address.province if address else None,
            "postal_code": address.postal_code if address else None,
            "product_id": product.id if product else None,
            "documents_missing": sum(1 for s in slots if s["required"] and s["document"] is None),
            "documents_rejected": sum(1 for s in slots if s["document"] is not None and s["document"].status == "REJECTED"),
            "instalments_total": instalments.get(contract.id, {}).get("total"),
            "instalments_paid": instalments.get(contract.id, {}).get("paid", 0),
            "instalments_failed": instalments.get(contract.id, {}).get("failed", 0),
            # Stripe is still billing this contract (target of "stop billing").
            "billing_active": contract.stripe_subscription_id is not None and contract.billing_stopped_at is None,
        })

    out = {
        **summary,
        "street": request.street,
        "city": request.city,
        "province": request.province,
        "postal_code": request.postal_code,
        "holder_first_name": request.holder_first_name,
        "holder_last_name": request.holder_last_name,
        "email": request.email,
        "pec": request.pec,
        "iban": request.iban,
        "points": enriched,
        "checkouts": [],
    }
    if include_checkouts:
        checkouts = list(
            (
                await db.execute(
                    select(ContractRequestCheckout)
                    .where(ContractRequestCheckout.contract_request_id == request.id)
                    .order_by(ContractRequestCheckout.created_at.desc())
                )
            ).scalars()
        )
        out["checkouts"] = [
            {
                "id": c.id,
                "created_at": c.created_at,
                "payment_plan": c.payment_plan,
                "total_cents": c.total_cents,
                "instalment_cents": c.instalment_cents,
                "contracts": len(c.lines),
                "completed_at": c.completed_at,
                "stripe_checkout_session_id": c.stripe_checkout_session_id,
                "stripe_subscription_id": c.stripe_subscription_id,
                "outcome": c.outcome,
            }
            for c in checkouts
        ]
    return out
