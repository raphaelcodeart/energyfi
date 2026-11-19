"""A customer is never blocked because their referring promoter was deactivated.

A contract cannot be attributed to a non-ACTIVE agent, so contract creation
walks up the sponsor chain to the nearest ACTIVE agent. The branch that built
the relationship keeps it, nobody waits on an admin, and the substitution is
audited. If no active agent remains, the customer gets a clear, actionable
error instead of a server error.
"""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.foundation.security import hash_password
from app.modules.audit.models import AuditLog
from app.modules.catalog.models import Product, ProductVersion
from app.modules.contracts import service as contract_service
from app.modules.contracts.models import Contract, ContractAttribution
from app.modules.customers.models import Address, Customer, SupplyPoint
from app.modules.customers.schemas import SupplyPointCreate
from app.modules.network import service as network_service
from app.modules.referral import service as referral_service
from app.modules.users.models import User

NOW = datetime(2026, 1, 1, tzinfo=UTC)


async def _make_user(db, organization_id, prefix="u") -> User:
    user = User(
        organization_id=organization_id, email=f"{prefix}-{uuid.uuid4().hex[:8]}@example.com",
        password_hash=hash_password("irrelevant"),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _make_agent(db, organization_id, *, name, parent_agent_id=None, user_id=None, status="ACTIVE"):
    return await network_service.create_agent(
        db, organization_id=organization_id, first_name=name, last_name="Tester",
        promoter_code=f"{name[:3].upper()}-{uuid.uuid4().hex[:8]}",
        parent_agent_id=parent_agent_id, user_id=user_id, status=status,
    )


async def _make_internal_product(db, organization_id) -> ProductVersion:
    product = Product(
        organization_id=organization_id, code=f"LU-{uuid.uuid4().hex[:6]}",
        energy_type="ELECTRICITY", customer_type="BOTH", category="INTERNAL",
    )
    db.add(product)
    await db.flush()
    version = ProductVersion(
        product_id=product.id, version_label="1.0", name="Luce Energia Plus",
        base_price_cents=15_00, valid_from=NOW,
    )
    db.add(version)
    await db.commit()
    await db.refresh(version)
    return version


async def _make_customer_referred_by(db, organization_id, agent_id, *, with_login=True):
    user = await _make_user(db, organization_id, prefix="cust") if with_login else None
    customer = Customer(
        organization_id=organization_id, kind="PRIVATE", user_id=user.id if user else None,
        email=f"c-{uuid.uuid4().hex[:8]}@example.com",
    )
    db.add(customer)
    await db.flush()
    address = Address(
        organization_id=organization_id, customer_id=customer.id, kind="SUPPLY",
        street="Via Test 1", city="Roma", province="RM", postal_code="00100",
    )
    db.add(address)
    await db.flush()
    db.add(SupplyPoint(
        organization_id=organization_id, customer_id=customer.id, energy_type="ELECTRICITY",
        supply_address_id=address.id,
    ))
    code = await referral_service.get_or_create_promoter_code(
        db, organization_id=organization_id, agent_id=agent_id
    )
    await referral_service.attribute_customer(
        db, organization_id=organization_id, customer_id=customer.id,
        promoter_code_id=code.id, referral_session_id=None,
    )
    await db.commit()
    await db.refresh(customer)
    return customer, user


def _supply_point_payload() -> SupplyPointCreate:
    return SupplyPointCreate(
        energy_type="ELECTRICITY", pod_code="IT001E12345678",
        street="Via Test 1", city="Roma", province="RM", postal_code="00100",
    )


async def _terminate(db, agent):
    agent.status = "TERMINATED"
    await db.commit()
    await db.refresh(agent)


@pytest.mark.asyncio
async def test_customer_can_still_activate_when_their_promoter_was_deactivated(db, organization_id):
    """With the customer's promoter deactivated after sign-up, the contract is
    created and credited to the promoter's sponsor."""
    sponsor = await _make_agent(db, organization_id, name="Davide")
    promoter = await _make_agent(db, organization_id, name="Matteo", parent_agent_id=sponsor.id)
    _customer, customer_user = await _make_customer_referred_by(db, organization_id, promoter.id)
    version = await _make_internal_product(db, organization_id)

    await _terminate(db, promoter)

    contract = await contract_service.create_contract_self_service(
        db, organization_id=organization_id, customer_user_id=customer_user.id,
        product_version_id=version.id, supply_point_payload=_supply_point_payload(),
        email="cliente@example.com",
    )

    attribution = await db.get(ContractAttribution, contract.contract_attribution_id)
    assert attribution.producer_agent_id == sponsor.id, "la provvigione deve andare allo sponsor attivo"
    # The original referrer stays recorded, keeping the substitution visible.
    assert contract.first_referrer_agent_id == promoter.id
    assert contract.status == "DOCUMENTS_PENDING"


@pytest.mark.asyncio
async def test_the_substitution_is_audited_not_silent(db, organization_id):
    sponsor = await _make_agent(db, organization_id, name="Davide")
    promoter = await _make_agent(db, organization_id, name="Matteo", parent_agent_id=sponsor.id)
    _customer, customer_user = await _make_customer_referred_by(db, organization_id, promoter.id)
    version = await _make_internal_product(db, organization_id)
    await _terminate(db, promoter)

    contract = await contract_service.create_contract_self_service(
        db, organization_id=organization_id, customer_user_id=customer_user.id,
        product_version_id=version.id, supply_point_payload=_supply_point_payload(),
        email="cliente@example.com",
    )

    rows = list((await db.execute(
        select(AuditLog).where(
            AuditLog.action == "contract.producer_substituted",
            AuditLog.entity_id == str(contract.id),
        )
    )).scalars())
    assert len(rows) == 1
    assert rows[0].previous_value["producer_agent_id"] == str(promoter.id)
    assert rows[0].new_value["producer_agent_id"] == str(sponsor.id)


@pytest.mark.asyncio
async def test_no_substitution_audit_row_when_the_promoter_is_fine(db, organization_id):
    """With an active promoter, no substitution audit row is written."""
    promoter = await _make_agent(db, organization_id, name="Attiva")
    _customer, customer_user = await _make_customer_referred_by(db, organization_id, promoter.id)
    version = await _make_internal_product(db, organization_id)

    contract = await contract_service.create_contract_self_service(
        db, organization_id=organization_id, customer_user_id=customer_user.id,
        product_version_id=version.id, supply_point_payload=_supply_point_payload(),
        email="cliente@example.com",
    )

    attribution = await db.get(ContractAttribution, contract.contract_attribution_id)
    assert attribution.producer_agent_id == promoter.id
    rows = list((await db.execute(
        select(AuditLog).where(AuditLog.action == "contract.producer_substituted")
    )).scalars())
    assert rows == []


@pytest.mark.asyncio
async def test_it_walks_past_several_deactivated_levels(db, organization_id):
    """The walk-up continues past consecutive deactivated levels."""
    top = await _make_agent(db, organization_id, name="Top")
    middle = await _make_agent(db, organization_id, name="Middle", parent_agent_id=top.id)
    bottom = await _make_agent(db, organization_id, name="Bottom", parent_agent_id=middle.id)
    _customer, customer_user = await _make_customer_referred_by(db, organization_id, bottom.id)
    version = await _make_internal_product(db, organization_id)

    await _terminate(db, bottom)
    await _terminate(db, middle)

    contract = await contract_service.create_contract_self_service(
        db, organization_id=organization_id, customer_user_id=customer_user.id,
        product_version_id=version.id, supply_point_payload=_supply_point_payload(),
        email="cliente@example.com",
    )
    attribution = await db.get(ContractAttribution, contract.contract_attribution_id)
    assert attribution.producer_agent_id == top.id


@pytest.mark.asyncio
async def test_a_clear_italian_error_when_the_whole_upline_is_inactive(db, organization_id):
    """With no active upline, activation is refused with a readable Italian
    message rather than a server error."""
    root = await _make_agent(db, organization_id, name="Root")
    promoter = await _make_agent(db, organization_id, name="Solo", parent_agent_id=root.id)
    _customer, customer_user = await _make_customer_referred_by(db, organization_id, promoter.id)
    version = await _make_internal_product(db, organization_id)

    await _terminate(db, promoter)
    await _terminate(db, root)

    with pytest.raises(contract_service.SelfServiceContractError) as exc:
        await contract_service.create_contract_self_service(
            db, organization_id=organization_id, customer_user_id=customer_user.id,
            product_version_id=version.id, supply_point_payload=_supply_point_payload(),
            email="cliente@example.com",
        )
    message = str(exc.value)
    assert "assistenza" in message
    assert "producer_agent_id" not in message
    assert "TERMINATED" not in message


@pytest.mark.asyncio
async def test_the_inheriting_sponsor_can_activate_for_that_customer_from_the_crm(db, organization_id):
    """The sponsor who inherits the customer can activate contracts for them
    from the CRM."""
    sponsor_user = await _make_user(db, organization_id, prefix="sponsor")
    sponsor = await _make_agent(db, organization_id, name="Davide", user_id=sponsor_user.id)
    promoter = await _make_agent(db, organization_id, name="Matteo", parent_agent_id=sponsor.id)
    customer, _ = await _make_customer_referred_by(db, organization_id, promoter.id, with_login=False)
    version = await _make_internal_product(db, organization_id)

    await _terminate(db, promoter)

    contract = await contract_service.create_contract_for_recruited_customer(
        db, organization_id=organization_id, promoter_user_id=sponsor_user.id,
        customer_id=customer.id, product_version_id=version.id,
        supply_point_payload=_supply_point_payload(), email="cliente@example.com",
    )
    assert contract.activated_by_promoter_id == sponsor.id
    assert contract.created_by_role == "PROMOTER"


@pytest.mark.asyncio
async def test_an_unrelated_promoter_still_cannot_activate_for_someone_elses_customer(db, organization_id):
    """The walk-up grants access to the upline only, never to another branch."""
    sponsor = await _make_agent(db, organization_id, name="Davide")
    promoter = await _make_agent(db, organization_id, name="Matteo", parent_agent_id=sponsor.id)
    stranger_user = await _make_user(db, organization_id, prefix="stranger")
    await _make_agent(db, organization_id, name="Estraneo", user_id=stranger_user.id)
    customer, _ = await _make_customer_referred_by(db, organization_id, promoter.id, with_login=False)
    version = await _make_internal_product(db, organization_id)

    await _terminate(db, promoter)

    with pytest.raises(contract_service.SelfServiceContractError, match="non è nella tua rete"):
        await contract_service.create_contract_for_recruited_customer(
            db, organization_id=organization_id, promoter_user_id=stranger_user.id,
            customer_id=customer.id, product_version_id=version.id,
            supply_point_payload=_supply_point_payload(), email="cliente@example.com",
        )


@pytest.mark.asyncio
async def test_no_contract_row_is_left_behind_when_activation_is_refused(db, organization_id):
    """A refused activation leaves no partial contract behind."""
    root = await _make_agent(db, organization_id, name="Root")
    promoter = await _make_agent(db, organization_id, name="Solo", parent_agent_id=root.id)
    customer, customer_user = await _make_customer_referred_by(db, organization_id, promoter.id)
    version = await _make_internal_product(db, organization_id)
    await _terminate(db, promoter)
    await _terminate(db, root)

    with pytest.raises(contract_service.SelfServiceContractError):
        await contract_service.create_contract_self_service(
            db, organization_id=organization_id, customer_user_id=customer_user.id,
            product_version_id=version.id, supply_point_payload=_supply_point_payload(),
            email="cliente@example.com",
        )

    contracts = list((await db.execute(
        select(Contract).where(Contract.customer_id == customer.id)
    )).scalars())
    assert contracts == []
