"""Commission engine against the real database: the time- and state-dependent
cases the pure engine tests cannot cover (plan versions, role and sponsor
changes after a sale, referrals, cancellations, idempotency, plan validation).
"""

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.foundation.db import utcnow
from app.modules.catalog.models import Product, ProductVersion
from app.modules.commercial import service as commercial_service
from app.modules.commissions.models import CommissionMovement, CommissionReversal
from app.modules.commissions.services import lifecycle
from app.modules.commissions.services import plans as plans_service
from app.modules.commissions.services.run_calculation import run_calculation_for_contract
from app.modules.commissions.simulations.simulate import simulate_sale
from app.modules.commissions.tasks.dispatch import process_pending_outbox_events
from app.modules.contracts import service as contract_service
from app.modules.contracts.models import Contract
from app.modules.customers.models import Address, Customer, SupplyPoint
from app.modules.leads import service as leads_service
from app.modules.leads.models import Lead
from app.modules.network import service as network_service
from tests.split_helpers import PLAN_START, ensure_roles_for_all_agents
from tests.test_commission_engine_integration import _make_actor

NETWORK_RULES = [
    {"beneficiary_type": "SELLER", "calculation_type": "PERCENTAGE", "percentage": 50},
    {"beneficiary_type": "UPLINE_LEVEL", "network_level": 1, "calculation_type": "PERCENTAGE", "percentage": 20},
    {"beneficiary_type": "UPLINE_LEVEL", "network_level": 2, "calculation_type": "PERCENTAGE", "percentage": 15},
    {"beneficiary_type": "COMPANY", "calculation_type": "REMAINDER"},
]


async def _agent(db, organization_id, name, parent=None):
    return await network_service.create_agent(
        db, organization_id=organization_id, first_name=name, last_name="Test",
        promoter_code=f"{name[:3].upper()}-{uuid.uuid4().hex[:6]}", parent_agent_id=parent,
        joined_at=utcnow() - timedelta(days=400),
    )


async def _world(db, organization_id, *, margin_cents=15000):
    """Chain Mario -> Anna -> Luca (Luca sells) and a fixed-margin product."""
    actor = await _make_actor(db, organization_id)
    roles = await commercial_service.ensure_default_roles(db, organization_id=organization_id)
    await db.commit()
    mario = await _agent(db, organization_id, "Mario")
    anna = await _agent(db, organization_id, "Anna", mario.id)
    luca = await _agent(db, organization_id, "Luca", anna.id)
    await ensure_roles_for_all_agents(db, organization_id)

    product = Product(organization_id=organization_id, code=f"TLC-FIBRA-{uuid.uuid4().hex[:4]}",
                      product_type="SUBSCRIPTION", customer_type="PRIVATE")
    db.add(product)
    await db.flush()
    version = ProductVersion(
        product_id=product.id, version_label="1.0", name="Fibra 100", base_price_cents=3000,
        margin_type="FIXED", margin_amount_cents=margin_cents, valid_from=PLAN_START,
    )
    db.add(version)
    await db.commit()
    return {"actor": actor, "roles": roles, "mario": mario, "anna": anna, "luca": luca,
            "product": product, "version": version}


async def _plan(db, organization_id, w, *, rules=NETWORK_RULES, valid_from=PLAN_START, role="NETWORKER", fallback="COMPANY"):
    plan = await plans_service.create_plan(
        db, organization_id=organization_id, actor_user_id=w["actor"],
        values={"name": "Fibra Networker", "product_id": w["product"].id, "seller_role_id": w["roles"][role].id,
                "valid_from": valid_from, "fallback_strategy": fallback},
        rules=rules,
    )
    return await plans_service.activate(db, organization_id=organization_id, plan_id=plan.id, actor_user_id=w["actor"])


async def _contract(db, organization_id, w, seller, *, sold_at=None):
    customer = Customer(organization_id=organization_id, kind="PRIVATE", email=f"c-{uuid.uuid4().hex[:6]}@example.com")
    db.add(customer)
    await db.flush()
    address = Address(organization_id=organization_id, customer_id=customer.id, kind="SUPPLY",
                      street="Via Test 1", city="Roma", province="RM", postal_code="00100")
    db.add(address)
    await db.flush()
    sp = SupplyPoint(organization_id=organization_id, customer_id=customer.id, energy_type="ELECTRICITY",
                     supply_address_id=address.id)
    db.add(sp)
    await db.commit()
    contract = await contract_service.create_contract(
        db, organization_id=organization_id, customer_id=customer.id, supply_point_id=sp.id,
        product_version_id=w["version"].id, producer_agent_id=seller.id, actor_user_id=w["actor"],
        correlation_id=str(uuid.uuid4()),
    )
    if sold_at is not None:
        contract.sold_at = sold_at
        await db.commit()
    return contract


async def _activate(db, organization_id, w, contract):
    for step in ["SUBMITTED", "UNDER_REVIEW", "APPROVED", "PAID"]:
        contract = await contract_service.transition_contract(
            db, organization_id=organization_id, contract=contract, to_status=step,
            actor_user_id=w["actor"], reason="test", notes=None, correlation_id=str(uuid.uuid4()),
        )
    await process_pending_outbox_events(db)
    return contract


async def _paid_to(db, contract) -> dict[str, int]:
    rows = (await db.execute(
        select(CommissionMovement).where(CommissionMovement.contract_id == contract.id)
    )).scalars().all()
    out: dict[str, int] = {}
    for m in rows:
        key = str(m.agent_id) if m.agent_id else "COMPANY"
        out[key] = out.get(key, 0) + m.amount_cents
    return out


@pytest.mark.asyncio
async def test_full_sale_distributes_exactly_the_margin(db, organization_id):
    w = await _world(db, organization_id)
    await _plan(db, organization_id, w)
    contract = await _activate(db, organization_id, w, await _contract(db, organization_id, w, w["luca"]))

    paid = await _paid_to(db, contract)
    assert paid == {str(w["luca"].id): 7500, str(w["anna"].id): 3000, str(w["mario"].id): 2250, "COMPANY": 2250}
    assert sum(paid.values()) == 15000
    row = await db.get(Contract, contract.id)
    assert (row.reference_margin_cents, row.seller_role_code) == (15000, "NETWORKER")


@pytest.mark.asyncio
async def test_versioned_plan_each_sale_uses_the_version_valid_at_its_date(db, organization_id):
    """A sale uses the plan version valid on its own date, and activating a
    new version never recalculates past sales."""
    w = await _world(db, organization_id)
    v1 = await _plan(db, organization_id, w)
    old_sale = await _activate(db, organization_id, w, await _contract(db, organization_id, w, w["luca"]))
    before = await _paid_to(db, old_sale)

    v2_draft = await plans_service.new_version(
        db, organization_id=organization_id, plan_id=v1.id, actor_user_id=w["actor"],
        valid_from=utcnow() - timedelta(days=30),
    )
    await plans_service.update_draft(
        db, organization_id=organization_id, plan_id=v2_draft.id, actor_user_id=w["actor"], values={},
        rules=[
            {"beneficiary_type": "SELLER", "calculation_type": "PERCENTAGE", "percentage": 70},
            {"beneficiary_type": "COMPANY", "calculation_type": "REMAINDER"},
        ],
    )
    v2 = await plans_service.activate(db, organization_id=organization_id, plan_id=v2_draft.id, actor_user_id=w["actor"])
    v1 = await plans_service.get_plan(db, organization_id=organization_id, plan_id=v1.id)
    assert v1.valid_to == v2.valid_from, "la V1 si chiude esattamente dove comincia la V2"

    assert await _paid_to(db, old_sale) == before, "nessun ricalcolo del passato"

    backdated = await _contract(db, organization_id, w, w["luca"], sold_at=utcnow() - timedelta(days=60))
    backdated = await _activate(db, organization_id, w, backdated)
    today = await _activate(db, organization_id, w, await _contract(db, organization_id, w, w["luca"]))
    assert (await db.get(Contract, backdated.id)).split_plan_id == v1.id
    assert (await db.get(Contract, today.id)).split_plan_id == v2.id
    assert (await _paid_to(db, today))[str(w["luca"].id)] == 10500


@pytest.mark.asyncio
async def test_successive_versions_always_activate(db, organization_id):
    """Each new version closes the previous one before turning ACTIVE, so the
    no-overlap constraint never fires, whatever order rows are flushed in."""
    w = await _world(db, organization_id)
    current = await _plan(db, organization_id, w)
    for days_ago in (40, 30, 20, 10):
        draft = await plans_service.new_version(
            db, organization_id=organization_id, plan_id=current.id, actor_user_id=w["actor"],
            valid_from=utcnow() - timedelta(days=days_ago),
        )
        activated = await plans_service.activate(
            db, organization_id=organization_id, plan_id=draft.id, actor_user_id=w["actor"]
        )
        previous = await plans_service.get_plan(db, organization_id=organization_id, plan_id=current.id)
        assert previous.valid_to == activated.valid_from
        current = activated


@pytest.mark.asyncio
async def test_an_active_plan_cannot_be_edited_and_an_invalid_one_cannot_be_activated(db, organization_id):
    """Active plans are read-only, and a plan totalling 99% cannot be activated."""
    w = await _world(db, organization_id)
    plan = await plans_service.create_plan(
        db, organization_id=organization_id, actor_user_id=w["actor"],
        values={"name": "Sbagliato", "product_id": w["product"].id,
                "seller_role_id": w["roles"]["NETWORKER"].id, "valid_from": PLAN_START},
        rules=[
            {"beneficiary_type": "SELLER", "calculation_type": "PERCENTAGE", "percentage": 60},
            {"beneficiary_type": "UPLINE_LEVEL", "network_level": 1, "calculation_type": "PERCENTAGE", "percentage": 39},
        ],
    )
    with pytest.raises(plans_service.SplitPlanError) as exc:
        await plans_service.activate(db, organization_id=organization_id, plan_id=plan.id, actor_user_id=w["actor"])
    assert any("100%" in e for e in exc.value.errors)

    good = await _plan(db, organization_id, w)
    with pytest.raises(plans_service.SplitPlanError):
        await plans_service.update_draft(
            db, organization_id=organization_id, plan_id=good.id, actor_user_id=w["actor"], values={"name": "x"},
            rules=None,
        )


@pytest.mark.asyncio
async def test_overlapping_active_plans_are_refused(db, organization_id):
    w = await _world(db, organization_id)
    await _plan(db, organization_id, w)
    with pytest.raises(plans_service.SplitPlanError, match="sovrappone"):
        await _plan(db, organization_id, w, valid_from=utcnow())


@pytest.mark.asyncio
async def test_role_change_after_the_sale_does_not_change_its_commissions(db, organization_id):
    """A sale keeps the seller role held on the sale date."""
    w = await _world(db, organization_id)
    await _plan(db, organization_id, w)
    contract = await _contract(db, organization_id, w, w["luca"], sold_at=utcnow() - timedelta(days=2))
    await commercial_service.assign_role(
        db, organization_id=organization_id, agent_id=w["luca"].id,
        role_id=w["roles"]["DIRETTORE_COMMERCIALE"].id, actor_user_id=w["actor"],
        effective_from=utcnow() - timedelta(days=1),
    )
    contract = await _activate(db, organization_id, w, contract)
    row = await db.get(Contract, contract.id)
    assert row.seller_role_code == "NETWORKER"
    assert (await _paid_to(db, contract))[str(w["luca"].id)] == 7500


@pytest.mark.asyncio
async def test_sponsor_change_after_the_sale_does_not_change_who_is_paid(db, organization_id):
    """Moving the seller to a new sponsor does not redirect earlier indirect shares."""
    w = await _world(db, organization_id)
    await _plan(db, organization_id, w)
    contract = await _contract(db, organization_id, w, w["luca"], sold_at=utcnow() - timedelta(days=10))
    await network_service.move_agent(
        db, organization_id=organization_id, agent_id=w["luca"].id, new_parent_agent_id=w["mario"].id,
        requested_by=w["actor"], approved_by=w["actor"], reason="test",
    )
    contract = await _activate(db, organization_id, w, contract)
    paid = await _paid_to(db, contract)
    assert paid[str(w["anna"].id)] == 3000
    assert paid[str(w["mario"].id)] == 2250


@pytest.mark.asyncio
async def test_promoter_referral_routes_the_sale_and_pays_the_fee(db, organization_id):
    """A referred sale goes to the first upline agent able to close it; the
    referring promoter gets the fee and the closing chain the rest."""
    w = await _world(db, organization_id)
    sara = await _agent(db, organization_id, "Sara", w["luca"].id)
    await commercial_service.assign_role(
        db, organization_id=organization_id, agent_id=sara.id, role_id=w["roles"]["PROMOTER"].id,
        actor_user_id=w["actor"], effective_from=utcnow() - timedelta(days=300),
    )
    await _plan(db, organization_id, w, rules=[
        {"beneficiary_type": "PROMOTER", "calculation_type": "FIXED_AMOUNT", "amount_cents": 2000},
        {"beneficiary_type": "SELLER", "calculation_type": "PERCENTAGE", "percentage": 50},
        {"beneficiary_type": "UPLINE_LEVEL", "network_level": 1, "calculation_type": "REMAINDER"},
    ])
    contract = await _activate(db, organization_id, w, await _contract(db, organization_id, w, sara))

    paid = await _paid_to(db, contract)
    assert paid == {str(sara.id): 2000, str(w["luca"].id): 7500, str(w["anna"].id): 5500}
    lead = await db.get(Lead, (await db.get(Contract, contract.id)).lead_id)
    assert lead.status == "CONVERTED" and lead.promoter_agent_id == sara.id


@pytest.mark.asyncio
async def test_a_lead_that_never_converts_pays_nothing(db, organization_id):
    """An unconverted referral pays nothing."""
    w = await _world(db, organization_id)
    lead = await leads_service.create_lead(
        db, organization_id=organization_id, promoter_agent_id=w["mario"].id, actor_user_id=w["actor"],
        contact_name="Cliente potenziale",
    )
    await leads_service.update_lead(
        db, organization_id=organization_id, lead_id=lead.id, actor_user_id=w["actor"], values={"status": "LOST"},
    )
    rows = (await db.execute(select(CommissionMovement).where(CommissionMovement.agent_id == w["mario"].id))).all()
    assert rows == []


@pytest.mark.asyncio
async def test_same_event_twice_never_duplicates(db, organization_id):
    """Processing the same event twice creates no duplicate lines."""
    w = await _world(db, organization_id)
    await _plan(db, organization_id, w)
    contract = await _activate(db, organization_id, w, await _contract(db, organization_id, w, w["luca"]))
    calc_event = (await db.execute(
        select(CommissionMovement.origin_event_id).where(CommissionMovement.contract_id == contract.id)
    )).scalars().first()
    again = await run_calculation_for_contract(
        db, organization_id=organization_id, contract_id=contract.id, trigger_event_id=calc_event,
    )
    assert again is not None
    count = len((await db.execute(select(CommissionMovement).where(CommissionMovement.contract_id == contract.id))).all())
    assert count == 4


@pytest.mark.asyncio
async def test_cancellation_cancels_unpaid_and_reverses_paid(db, organization_id):
    """On cancellation nothing is deleted: unpaid lines become CANCELLED and
    paid lines get a negative reversal."""
    w = await _world(db, organization_id)
    await _plan(db, organization_id, w)
    contract = await _activate(db, organization_id, w, await _contract(db, organization_id, w, w["luca"]))
    luca_row = (await db.execute(select(CommissionMovement).where(
        CommissionMovement.contract_id == contract.id, CommissionMovement.agent_id == w["luca"].id
    ))).scalar_one()
    for status in ("APPROVED", "PAID"):
        await lifecycle.transition(
            db, organization_id=organization_id, movement_ids=[luca_row.id], to_status=status, actor_user_id=w["actor"],
        )

    contract = await contract_service.transition_contract(
        db, organization_id=organization_id, contract=await db.get(Contract, contract.id), to_status="CANCELLED",
        actor_user_id=w["actor"], reason="recesso", notes=None, correlation_id=str(uuid.uuid4()),
    )
    await process_pending_outbox_events(db)

    rows = (await db.execute(select(CommissionMovement).where(CommissionMovement.contract_id == contract.id))).scalars().all()
    statuses = {(str(m.agent_id) if m.agent_id else "COMPANY", m.movement_type): m.status for m in rows}
    assert statuses[(str(w["luca"].id), "DIRECT")] == "PAID"
    assert statuses[(str(w["anna"].id), "INDIRECT")] == "CANCELLED"
    assert statuses[("COMPANY", "COMPANY_SHARE")] == "CANCELLED"
    reversal = next(m for m in rows if m.movement_type == "REVERSAL")
    assert (reversal.agent_id, reversal.amount_cents) == (w["luca"].id, -7500)
    link = (await db.execute(select(CommissionReversal))).scalars().all()
    assert [lk.original_movement_id for lk in link] == [luca_row.id]

    # Reprocessing does not reverse twice.
    await lifecycle.reverse_contract(db, organization_id=organization_id, contract_id=contract.id, actor_user_id=w["actor"], reason="x")
    assert len((await db.execute(select(CommissionMovement).where(
        CommissionMovement.contract_id == contract.id, CommissionMovement.movement_type == "REVERSAL"
    ))).all()) == 1


@pytest.mark.asyncio
async def test_simulator_uses_the_same_engine_and_writes_nothing(db, organization_id):
    w = await _world(db, organization_id)
    await _plan(db, organization_id, w)
    result = await simulate_sale(
        db, organization_id=organization_id, seller_agent_id=w["luca"].id, product_id=w["product"].id,
        sold_at=utcnow(),
    )
    assert result["errors"] == []
    assert [(r["name"], r["total_cents"]) for r in result["rows"]] == [
        ("Luca Test", 7500), ("Anna Test", 3000), ("Mario Test", 2250), ("Azienda", 2250),
    ]
    assert result["distributed_cents"] == result["reference_margin_cents"] == 15000
    written = (await db.execute(select(CommissionMovement).where(
        CommissionMovement.agent_id.in_([w["luca"].id, w["anna"].id, w["mario"].id])
    ))).first()
    assert written is None


@pytest.mark.asyncio
async def test_a_contract_without_a_plan_cannot_be_approved(db, organization_id):
    """Without a plan for the product and role, the preview reports it and the
    contract cannot be approved."""
    from app.modules.commissions.services.preview import build_commission_preview

    w = await _world(db, organization_id)
    contract = await _contract(db, organization_id, w, w["luca"])
    preview = await build_commission_preview(db, organization_id=organization_id, contract=contract)
    assert any("Split Plan" in e for e in preview["blocking_errors"])
    with pytest.raises(contract_service.CommissionPreviewChangedError):
        await contract_service.accept_commission_plan(
            db, organization_id=organization_id, contract=contract, checksum=preview["checksum"],
            actor_user_id=w["actor"],
        )


def test_money_never_uses_floats():
    """Money and percentage columns are integer or NUMERIC, never float."""
    from sqlalchemy import BigInteger, Integer, Numeric

    from app.modules.commissions.models import CommissionMovement as M
    from app.modules.commissions.models import SplitRule as R

    for column in (M.__table__.c.amount_cents, M.__table__.c.reference_margin_cents, R.__table__.c.amount_cents):
        assert isinstance(column.type, (BigInteger, Integer))
    for column in (R.__table__.c.percentage, M.__table__.c.calculation_value):
        assert isinstance(column.type, Numeric) and column.type.asdecimal

