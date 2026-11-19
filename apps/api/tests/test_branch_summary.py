"""Promoter branch view: per-agent and per-level contract and commission
totals, plus the per-contract detail list."""

import uuid
from datetime import UTC, datetime

import pytest

from app.foundation.security import hash_password
from app.modules.catalog.models import Product, ProductVersion
from app.modules.commissions.models import Rank
from app.modules.commissions.tasks.dispatch import process_pending_outbox_events
from tests.split_helpers import install_plan
from app.modules.contracts import service as contract_service
from app.modules.customers.models import Address, Customer, SupplyPoint
from app.modules.network import service as network_service
from app.modules.users.models import User

NOW = datetime(2026, 1, 1, tzinfo=UTC)


async def _make_actor(db, organization_id):
    user = User(
        organization_id=organization_id, email=f"actor-{uuid.uuid4().hex[:8]}@example.com",
        password_hash=hash_password("irrelevant"),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user.id


async def _make_contract_ready_to_activate(db, organization_id, actor_user_id, producer_agent_id):
    product = Product(organization_id=organization_id, code=f"P-{uuid.uuid4().hex[:6]}", energy_type="ELECTRICITY", customer_type="PRIVATE")
    db.add(product)
    await db.flush()
    product_version = ProductVersion(
        product_id=product.id, version_label="1.0", name="Test product", base_price_cents=1000,
        contract_duration_months=12, valid_from=NOW,
    )
    db.add(product_version)
    await db.flush()
    # Fixed 40.00 to the seller, remainder to the company: branch totals equal
    # the seller's share.
    await install_plan(db, organization_id, product_version=product_version, actor_user_id=actor_user_id, rules=[
        {"beneficiary_type": "SELLER", "calculation_type": "FIXED_AMOUNT", "amount_cents": 4000},
        {"beneficiary_type": "COMPANY", "calculation_type": "REMAINDER"},
    ])

    customer = Customer(organization_id=organization_id, kind="PRIVATE", email=f"cust-{uuid.uuid4().hex[:6]}@example.com")
    db.add(customer)
    await db.flush()
    address = Address(
        organization_id=organization_id, customer_id=customer.id, kind="SUPPLY",
        street="Via Test 1", city="Roma", province="RM", postal_code="00100",
    )
    db.add(address)
    await db.flush()
    supply_point = SupplyPoint(
        organization_id=organization_id, customer_id=customer.id, energy_type="ELECTRICITY", supply_address_id=address.id,
    )
    db.add(supply_point)
    await db.commit()

    contract = await contract_service.create_contract(
        db, organization_id=organization_id, customer_id=customer.id, supply_point_id=supply_point.id,
        product_version_id=product_version.id, producer_agent_id=producer_agent_id,
        actor_user_id=actor_user_id, correlation_id=str(uuid.uuid4()),
    )
    return contract


async def _advance_to_active(db, organization_id, contract, actor_user_id):
    for step in ["SUBMITTED", "UNDER_REVIEW", "APPROVED", "PAID"]:  # auto-cascades to ACTIVE
        contract = await contract_service.transition_contract(
            db, organization_id=organization_id, contract=contract, to_status=step,
            actor_user_id=actor_user_id, reason="test", notes=None, correlation_id=str(uuid.uuid4()),
        )
    return contract


async def _advance_to_documents_pending(db, organization_id, contract, actor_user_id):
    for step in ["SUBMITTED", "DOCUMENTS_PENDING"]:
        contract = await contract_service.transition_contract(
            db, organization_id=organization_id, contract=contract, to_status=step,
            actor_user_id=actor_user_id, reason="test", notes=None, correlation_id=str(uuid.uuid4()),
        )
    return contract


@pytest.mark.asyncio
async def test_branch_summary_counts_contracts_and_commissions_per_agent(db, organization_id):
    s1 = Rank(organization_id=organization_id, code="SP1", name="SosPromoter 1", level=1, personal_token_cents=4000, valid_from=NOW, rule_version="test")
    db.add(s1)
    await db.flush()

    sponsor = await network_service.create_agent(
        db, organization_id=organization_id, first_name="Sponsor", last_name="Tester", promoter_code=f"SP-{uuid.uuid4().hex[:8]}",
        parent_agent_id=None, current_rank_id=s1.id,
    )
    producer = await network_service.create_agent(
        db, organization_id=organization_id, first_name="Producer", last_name="Tester", promoter_code=f"PR-{uuid.uuid4().hex[:8]}",
        parent_agent_id=sponsor.id, current_rank_id=s1.id,
    )

    actor_user_id = await _make_actor(db, organization_id)

    active_contract = await _make_contract_ready_to_activate(db, organization_id, actor_user_id, producer.id)
    active_contract = await _advance_to_active(db, organization_id, active_contract, actor_user_id)
    await process_pending_outbox_events(db)

    problem_contract = await _make_contract_ready_to_activate(db, organization_id, actor_user_id, producer.id)
    await _advance_to_documents_pending(db, organization_id, problem_contract, actor_user_id)

    summary = await network_service.get_branch_summary(db, organization_id=organization_id, root_agent_id=sponsor.id)

    by_id = {a["agent_id"]: a for a in summary["agents"]}
    producer_row = by_id[producer.id]
    assert producer_row["contracts_total"] == 2
    assert producer_row["contracts_processed"] == 1  # ACTIVE
    assert producer_row["contracts_problem"] == 1  # DOCUMENTS_PENDING
    assert producer_row["commission_cents"] == 4000  # seller share of the active contract

    totals = summary["totals"]
    assert totals["contracts_closed"] == 1  # ACTIVE
    assert totals["contracts_rejected"] == 0
    assert totals["contracts_pending"] == 1  # DOCUMENTS_PENDING, not REJECTED
    assert totals["contracts_in_progress"] == 0
    assert totals["levels_below"] == 1  # producer is one level below sponsor
    assert totals["people_total"] == 1  # producer only, sponsor (self) excluded

    assert summary["totals"]["contracts"] == 2
    assert summary["totals"]["commission_cents"] == 4000


@pytest.mark.asyncio
async def test_branch_summary_totals_distinguish_rejected_from_other_pending(db, organization_id):
    """A rejected contract counts as rejected only, never also as pending."""
    s1 = Rank(organization_id=organization_id, code="SP1", name="SosPromoter 1", level=1, personal_token_cents=4000, valid_from=NOW, rule_version="test")
    db.add(s1)
    await db.flush()

    producer = await network_service.create_agent(
        db, organization_id=organization_id, first_name="Rejector", last_name="Tester", promoter_code=f"REJ-{uuid.uuid4().hex[:8]}",
        parent_agent_id=None, current_rank_id=s1.id,
    )
    actor_user_id = await _make_actor(db, organization_id)

    rejected_contract = await _make_contract_ready_to_activate(db, organization_id, actor_user_id, producer.id)
    rejected_contract = await contract_service.transition_contract(
        db, organization_id=organization_id, contract=rejected_contract, to_status="SUBMITTED",
        actor_user_id=actor_user_id, reason=None, notes=None, correlation_id=str(uuid.uuid4()),
    )
    rejected_contract = await contract_service.transition_contract(
        db, organization_id=organization_id, contract=rejected_contract, to_status="REJECTED",
        actor_user_id=actor_user_id, reason="Non idoneo", notes=None, correlation_id=str(uuid.uuid4()),
    )

    draft_contract = await _make_contract_ready_to_activate(db, organization_id, actor_user_id, producer.id)

    summary = await network_service.get_branch_summary(db, organization_id=organization_id, root_agent_id=producer.id)
    totals = summary["totals"]
    assert totals["contracts_rejected"] == 1
    assert totals["contracts_pending"] == 0
    assert totals["contracts_in_progress"] == 1  # the still-DRAFT contract
    assert totals["contracts_closed"] == 0
    assert totals["levels_below"] == 0  # producer is root, no downline
    assert totals["people_total"] == 0


@pytest.mark.asyncio
async def test_branch_contracts_links_customer_product_status_and_commission(db, organization_id):
    s1 = Rank(organization_id=organization_id, code="SP1", name="SosPromoter 1", level=1, personal_token_cents=4000, valid_from=NOW, rule_version="test")
    db.add(s1)
    await db.flush()

    producer = await network_service.create_agent(
        db, organization_id=organization_id, first_name="Solo", last_name="Producer", promoter_code=f"SOLO-{uuid.uuid4().hex[:8]}",
        parent_agent_id=None, current_rank_id=s1.id,
    )
    actor_user_id = await _make_actor(db, organization_id)

    contract = await _make_contract_ready_to_activate(db, organization_id, actor_user_id, producer.id)
    contract = await _advance_to_active(db, organization_id, contract, actor_user_id)
    await process_pending_outbox_events(db)

    rows = await network_service.get_branch_contracts(db, organization_id=organization_id, root_agent_id=producer.id)
    assert len(rows) == 1
    row = rows[0]
    assert row["contract_id"] == contract.id
    assert row["status"] == "ACTIVE"
    assert row["commission_cents"] == 4000
    assert row["is_problem"] is False
    assert row["producer_agent_id"] == producer.id
    assert "@example.com" in row["customer_email"]
    assert row["expires_at"] is not None  # activation sets the term
    assert row["admin_note"] is None  # no status transition carried a note


@pytest.mark.asyncio
async def test_branch_contracts_surfaces_latest_admin_note_for_problem_contracts(db, organization_id):
    """The branch list shows the latest admin note, so promoters see what a
    problem contract is missing."""
    s1 = Rank(organization_id=organization_id, code="SP1", name="SosPromoter 1", level=1, personal_token_cents=4000, valid_from=NOW, rule_version="test")
    db.add(s1)
    await db.flush()

    producer = await network_service.create_agent(
        db, organization_id=organization_id, first_name="Note", last_name="Producer", promoter_code=f"NOTE-{uuid.uuid4().hex[:8]}",
        parent_agent_id=None, current_rank_id=s1.id,
    )
    actor_user_id = await _make_actor(db, organization_id)

    contract = await _make_contract_ready_to_activate(db, organization_id, actor_user_id, producer.id)
    contract = await contract_service.transition_contract(
        db, organization_id=organization_id, contract=contract, to_status="SUBMITTED",
        actor_user_id=actor_user_id, reason=None, notes=None, correlation_id=str(uuid.uuid4()),
    )
    contract = await contract_service.transition_contract(
        db, organization_id=organization_id, contract=contract, to_status="DOCUMENTS_PENDING",
        actor_user_id=actor_user_id, reason="Missing ID", notes="Manca il documento di identita'",
        correlation_id=str(uuid.uuid4()),
    )

    rows = await network_service.get_branch_contracts(db, organization_id=organization_id, root_agent_id=producer.id)
    assert len(rows) == 1
    assert rows[0]["is_problem"] is True
    assert rows[0]["admin_note"] == "Manca il documento di identita'"


@pytest.mark.asyncio
async def test_organization_network_levels_counts_people_per_depth_from_their_own_root(db, organization_id):
    """Levels are measured from each agent's own tree root, since an
    organization can hold several independent trees."""
    root_a = await network_service.create_agent(
        db, organization_id=organization_id, first_name="Root", last_name="A", promoter_code=f"RA-{uuid.uuid4().hex[:8]}",
        parent_agent_id=None,
    )
    child_a = await network_service.create_agent(
        db, organization_id=organization_id, first_name="Child", last_name="A", promoter_code=f"CA-{uuid.uuid4().hex[:8]}",
        parent_agent_id=root_a.id,
    )
    root_b = await network_service.create_agent(
        db, organization_id=organization_id, first_name="Root", last_name="B", promoter_code=f"RB-{uuid.uuid4().hex[:8]}",
        parent_agent_id=None,
    )

    result = await network_service.get_organization_network_levels(db, organization_id=organization_id)
    assert result["people_total"] == 3
    assert result["levels_total"] == 2  # depth 0 (both roots) and depth 1 (child_a)
    assert result["people_by_level"] == {0: 2, 1: 1}


@pytest.mark.asyncio
async def test_organization_network_levels_empty_org_returns_zeroes(db, organization_id):
    result = await network_service.get_organization_network_levels(db, organization_id=organization_id)
    assert result == {"people_total": 0, "levels_total": 0, "people_by_level": {}}
