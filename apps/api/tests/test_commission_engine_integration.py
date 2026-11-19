import asyncio
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.foundation.security import hash_password
from app.modules.audit.models import AuditLog
from app.modules.catalog.models import Product, ProductVersion
from app.modules.commissions.models import CommissionCalculation, CommissionMovement, Rank
from app.modules.commissions.services.run_calculation import run_calculation_for_contract
from app.modules.commissions.tasks.dispatch import process_pending_outbox_events
from app.modules.contracts import service as contract_service
from app.modules.contracts.models import Contract, ContractRequest
from app.modules.customers.models import Address, Customer, SupplyPoint
from app.modules.network import service as network_service
from app.modules.network.models import AgentProfile, NetworkSnapshot, NetworkSnapshotNode
from app.modules.organizations.models import Organization
from app.modules.outbox import service as outbox_service
from app.modules.outbox.models import DomainOutbox
from app.modules.users.models import User
from tests.conftest import TEST_DATABASE_URL
from tests.split_helpers import install_plan

NOW = datetime(2026, 1, 1, tzinfo=UTC)


async def _make_actor(db, organization_id):
    """Create a real user to act as actor (history and audit rows need a valid FK)."""
    user = User(
        organization_id=organization_id, email=f"actor-{uuid.uuid4().hex[:8]}@example.com",
        password_hash=hash_password("irrelevant"),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user.id


async def _setup_contract_ready_to_activate(db, organization_id, actor_user_id):
    """Build producer (SP1) -> sponsor (SP2), a product, a customer with a
    supply point and a DRAFT contract. Returns (contract, sponsor)."""
    s1 = Rank(
        organization_id=organization_id, code="SP1", name="SosPromoter 1", level=1,
        personal_token_cents=4000, valid_from=NOW, rule_version="test",
    )
    s2 = Rank(
        organization_id=organization_id, code="SP2", name="SosPromoter 2", level=2,
        personal_token_cents=4500, valid_from=NOW, rule_version="test",
    )
    db.add_all([s1, s2])
    await db.flush()

    sponsor = await network_service.create_agent(
        db, organization_id=organization_id, first_name="Sponsor", last_name="Tester", promoter_code=f"SP-{uuid.uuid4().hex[:8]}",
        parent_agent_id=None, current_rank_id=s2.id,
    )
    producer = await network_service.create_agent(
        db, organization_id=organization_id, first_name="Producer", last_name="Tester", promoter_code=f"PR-{uuid.uuid4().hex[:8]}",
        parent_agent_id=sponsor.id, current_rank_id=s1.id,
    )

    product = Product(organization_id=organization_id, code="TEST-PROD", energy_type="ELECTRICITY", customer_type="PRIVATE")
    db.add(product)
    await db.flush()
    product_version = ProductVersion(
        product_id=product.id, version_label="1.0", name="Test product", base_price_cents=1000,
        valid_from=NOW,
    )
    db.add(product_version)
    await db.flush()
    # Margin 45.00 EUR: 40.00 to the seller, the remaining 5.00 to the sponsor.
    await install_plan(db, organization_id, product_version=product_version, actor_user_id=actor_user_id)

    customer = Customer(organization_id=organization_id, kind="PRIVATE", email="test@example.com")
    db.add(customer)
    await db.flush()
    address = Address(
        organization_id=organization_id, customer_id=customer.id, kind="SUPPLY",
        street="Via Test 1", city="Roma", province="RM", postal_code="00100",
    )
    db.add(address)
    await db.flush()
    supply_point = SupplyPoint(
        organization_id=organization_id, customer_id=customer.id, energy_type="ELECTRICITY",
        supply_address_id=address.id,
    )
    db.add(supply_point)
    await db.commit()

    contract = await contract_service.create_contract(
        db, organization_id=organization_id, customer_id=customer.id, supply_point_id=supply_point.id,
        product_version_id=product_version.id, producer_agent_id=producer.id,
        actor_user_id=actor_user_id, correlation_id=str(uuid.uuid4()),
    )
    return contract, sponsor


async def _advance_to_active(db, organization_id, contract, actor_user_id):
    for step in ["SUBMITTED", "UNDER_REVIEW", "APPROVED", "PAID"]:  # APPROVED and PAID auto-cascade to PAYMENT_PENDING and ACTIVE
        contract = await contract_service.transition_contract(
            db, organization_id=organization_id, contract=contract, to_status=step,
            actor_user_id=actor_user_id, reason="test", notes=None, correlation_id=str(uuid.uuid4()),
        )
    return contract


@pytest.mark.asyncio
async def test_activation_generates_expected_commission_movements(db, organization_id):
    actor_user_id = await _make_actor(db, organization_id)
    contract, _sponsor = await _setup_contract_ready_to_activate(db, organization_id, actor_user_id)
    await _advance_to_active(db, organization_id, contract, actor_user_id)

    processed = await process_pending_outbox_events(db)
    assert processed >= 1

    stmt = select(CommissionMovement).where(CommissionMovement.contract_id == contract.id)
    movements = (await db.execute(stmt)).scalars().all()

    # Seller: fixed share 40.00; sponsor: remainder of the 45.00 margin = 5.00
    assert len(movements) == 2
    amounts = sorted(m.amount_cents for m in movements)
    assert amounts == [500, 4000]


@pytest.mark.asyncio
async def test_reprocessing_outbox_does_not_duplicate_movements(db, organization_id):
    actor_user_id = await _make_actor(db, organization_id)
    contract, _sponsor = await _setup_contract_ready_to_activate(db, organization_id, actor_user_id)
    await _advance_to_active(db, organization_id, contract, actor_user_id)

    first_count = await process_pending_outbox_events(db)
    second_count = await process_pending_outbox_events(db)
    assert first_count >= 1
    assert second_count == 0  # nothing left to process

    stmt = select(CommissionMovement).where(CommissionMovement.contract_id == contract.id)
    movements = (await db.execute(stmt)).scalars().all()
    assert len(movements) == 2  # no duplicates


@pytest.mark.asyncio
async def test_commission_calculation_is_scoped_to_its_organization(db):
    from app.modules.organizations.models import Organization

    org_a = Organization(name="Org A", status="ACTIVE")
    org_b = Organization(name="Org B", status="ACTIVE")
    db.add_all([org_a, org_b])
    await db.commit()
    await db.refresh(org_a)
    await db.refresh(org_b)

    actor_user_id = await _make_actor(db, org_a.id)
    contract_a, _sponsor = await _setup_contract_ready_to_activate(db, org_a.id, actor_user_id)
    await _advance_to_active(db, org_a.id, contract_a, actor_user_id)
    await process_pending_outbox_events(db)

    stmt = select(CommissionMovement).where(CommissionMovement.organization_id == org_b.id)
    org_b_movements = (await db.execute(stmt)).scalars().all()
    assert org_b_movements == []  # no cross-organization leakage


@pytest.mark.asyncio
async def test_empty_ancestor_chain_records_failed_calculation_not_silent_skip(db, organization_id):
    """A producer with an empty ancestor chain must fail loudly: the event is
    audited instead of the contract activating with nobody paid and no record
    of why."""
    customer = Customer(organization_id=organization_id, kind="PRIVATE", email="empty-chain@example.com")
    db.add(customer)
    await db.flush()
    address = Address(
        organization_id=organization_id, customer_id=customer.id, kind="SUPPLY",
        street="Via Test 2", city="Roma", province="RM", postal_code="00100",
    )
    db.add(address)
    await db.flush()
    supply_point = SupplyPoint(
        organization_id=organization_id, customer_id=customer.id, energy_type="ELECTRICITY",
        supply_address_id=address.id,
    )
    db.add(supply_point)

    product = Product(organization_id=organization_id, code="EMPTY-PROD", energy_type="ELECTRICITY", customer_type="PRIVATE")
    db.add(product)
    await db.flush()
    product_version = ProductVersion(
        product_id=product.id, version_label="1.0", name="Empty chain product", base_price_cents=1000,
        valid_from=NOW,
    )
    db.add(product_version)

    # An empty snapshot simulates an unresolvable ancestor chain.
    snapshot = NetworkSnapshot(organization_id=organization_id, reason="test_empty_chain")
    db.add(snapshot)
    await db.flush()

    # Every contract belongs to a contract request.
    request = ContractRequest(organization_id=organization_id, customer_id=customer.id, status="SUBMITTED")
    db.add(request)
    await db.flush()

    contract = Contract(
        organization_id=organization_id, customer_id=customer.id, supply_point_id=supply_point.id,
        contract_request_id=request.id,
        product_version_id=product_version.id, contract_attribution_id=None,
        network_snapshot_id=snapshot.id, status="ACTIVE",
    )
    db.add(contract)
    await db.commit()
    await db.refresh(contract)

    trigger_event_id = uuid.uuid4()
    calculation = await run_calculation_for_contract(
        db, organization_id=organization_id, contract_id=contract.id, trigger_event_id=trigger_event_id,
    )

    assert calculation is not None
    assert calculation.status == "FAILED"

    movements = (await db.execute(
        select(CommissionMovement).where(CommissionMovement.contract_id == contract.id)
    )).scalars().all()
    assert movements == []

    audit_rows = (await db.execute(
        select(AuditLog).where(
            AuditLog.organization_id == organization_id,
            AuditLog.action == "commission.calculation_failed",
            AuditLog.entity_id == str(contract.id),
        )
    )).scalars().all()
    assert len(audit_rows) == 1  # the failure is recorded


@pytest.mark.asyncio
async def test_dispatch_isolates_failing_event_from_others(db, organization_id):
    """A poisoned event (unknown contract_id) must not block other events in
    the same batch. It is enqueued first to prove the loop continues past it."""
    actor_user_id = await _make_actor(db, organization_id)

    poisoned_contract_id = uuid.uuid4()
    db.add(outbox_service.enqueue(
        organization_id=organization_id, event_type="ContractActivated",
        payload={"contract_id": str(poisoned_contract_id), "correlation_id": str(uuid.uuid4())},
    ))
    await db.commit()

    contract, _sponsor = await _setup_contract_ready_to_activate(db, organization_id, actor_user_id)
    contract = await _advance_to_active(db, organization_id, contract, actor_user_id)

    processed = await process_pending_outbox_events(db)
    assert processed >= 1

    movements = (await db.execute(
        select(CommissionMovement).where(CommissionMovement.contract_id == contract.id)
    )).scalars().all()
    assert len(movements) == 2  # the healthy contract is still paid

    events = (await db.execute(
        select(DomainOutbox).where(
            DomainOutbox.organization_id == organization_id,
            DomainOutbox.event_type == "ContractActivated",
        )
    )).scalars().all()
    poisoned_event = next(e for e in events if e.payload["contract_id"] == str(poisoned_contract_id))
    assert poisoned_event.processed_at is None  # kept for retry

    audit_rows = (await db.execute(
        select(AuditLog).where(
            AuditLog.organization_id == organization_id,
            AuditLog.action == "commission.calculation_error",
            AuditLog.entity_id == str(poisoned_contract_id),
        )
    )).scalars().all()
    assert len(audit_rows) == 1


@pytest.mark.asyncio
async def test_concurrent_calculation_race_is_handled_by_db_constraint():
    """Two truly concurrent connections (not the savepoint-based `db` fixture)
    race to process the same trigger event. The unique constraint on
    (contract, trigger) makes the loser back off cleanly, leaving exactly one
    calculation and one set of movements."""
    engine = create_async_engine(TEST_DATABASE_URL)
    setup_session = AsyncSession(bind=engine, expire_on_commit=False)
    try:
        org = Organization(name=f"Race Org {uuid.uuid4()}", status="ACTIVE")
        setup_session.add(org)
        await setup_session.commit()
        await setup_session.refresh(org)

        actor_user_id = await _make_actor(setup_session, org.id)
        contract, _sponsor = await _setup_contract_ready_to_activate(setup_session, org.id, actor_user_id)
        contract = await _advance_to_active(setup_session, org.id, contract, actor_user_id)

        event = (await setup_session.execute(
            select(DomainOutbox).where(
                DomainOutbox.organization_id == org.id, DomainOutbox.event_type == "ContractActivated"
            )
        )).scalar_one()
        org_id, contract_id, event_id = org.id, contract.id, event.id
    finally:
        await setup_session.close()

    session_a = AsyncSession(bind=engine, expire_on_commit=False)
    session_b = AsyncSession(bind=engine, expire_on_commit=False)
    try:
        results = await asyncio.gather(
            run_calculation_for_contract(session_a, organization_id=org_id, contract_id=contract_id, trigger_event_id=event_id),
            run_calculation_for_contract(session_b, organization_id=org_id, contract_id=contract_id, trigger_event_id=event_id),
            return_exceptions=True,
        )
    finally:
        await session_a.close()
        await session_b.close()

    for result in results:
        assert not isinstance(result, Exception), f"run_calculation_for_contract raised: {result!r}"

    verify_session = AsyncSession(bind=engine, expire_on_commit=False)
    try:
        calcs = (await verify_session.execute(
            select(CommissionCalculation).where(
                CommissionCalculation.contract_id == contract_id,
                CommissionCalculation.trigger_event_id == event_id,
            )
        )).scalars().all()
        assert len(calcs) == 1

        movements = (await verify_session.execute(
            select(CommissionMovement).where(CommissionMovement.contract_id == contract_id)
        )).scalars().all()
        assert len(movements) == 2  # producer + sponsor, no duplicates
    finally:
        await verify_session.close()

    await engine.dispose()


@pytest.mark.asyncio
async def test_terminated_ancestor_excluded_from_commission_chain(db, organization_id):
    """A TERMINATED ancestor is excluded from payment: the snapshot freezes
    them as inactive, so they never collect the sponsor difference."""
    actor_user_id = await _make_actor(db, organization_id)
    contract, sponsor = await _setup_contract_ready_to_activate(db, organization_id, actor_user_id)

    sponsor_row = await db.get(AgentProfile, sponsor.id)
    sponsor_row.status = "TERMINATED"
    await db.commit()

    await _advance_to_active(db, organization_id, contract, actor_user_id)
    await process_pending_outbox_events(db)

    movements = (await db.execute(
        select(CommissionMovement).where(CommissionMovement.contract_id == contract.id)
    )).scalars().all()
    agent_rows = [m for m in movements if m.beneficiary_kind == "AGENT"]
    company_rows = [m for m in movements if m.beneficiary_kind == "COMPANY"]
    # Only the seller is paid; the terminated sponsor's share follows the
    # plan's COMPANY fallback.
    assert [m.amount_cents for m in agent_rows] == [4000]
    assert agent_rows[0].agent_id != sponsor.id
    assert [(m.amount_cents, m.fallback_applied) for m in company_rows] == [(500, "COMPANY")]

    contract_row = await db.get(Contract, contract.id)
    snapshot_nodes = (await db.execute(
        select(NetworkSnapshotNode).where(NetworkSnapshotNode.snapshot_id == contract_row.network_snapshot_id)
    )).scalars().all()
    # The sponsor keeps their level in the frozen chain but is marked
    # inactive, which prevents payment.
    by_agent = {n.ancestor_agent_id: n for n in snapshot_nodes}
    assert by_agent[sponsor.id].agent_status == "TERMINATED"
    assert by_agent[sponsor.id].depth == 1


@pytest.mark.asyncio
async def test_pending_approval_ancestor_excluded_from_commission_chain(db, organization_id):
    """A PENDING_APPROVAL agent is not yet a confirmed promoter and is
    excluded in the same way."""
    actor_user_id = await _make_actor(db, organization_id)
    contract, sponsor = await _setup_contract_ready_to_activate(db, organization_id, actor_user_id)

    sponsor_row = await db.get(AgentProfile, sponsor.id)
    sponsor_row.status = "PENDING_APPROVAL"
    await db.commit()

    await _advance_to_active(db, organization_id, contract, actor_user_id)
    await process_pending_outbox_events(db)

    movements = (await db.execute(
        select(CommissionMovement).where(
            CommissionMovement.contract_id == contract.id, CommissionMovement.beneficiary_kind == "AGENT"
        )
    )).scalars().all()
    assert len(movements) == 1
    assert movements[0].amount_cents == 4000
    assert movements[0].agent_id != sponsor.id
