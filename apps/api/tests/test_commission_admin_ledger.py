"""Admin commission ledger: each movement traces its contract, customer,
promoter, network level and calculation, and is paid via
PENDING -> APPROVED -> PAID exactly once."""

import pytest
from sqlalchemy import select

from app.modules.commissions.models import CommissionMovement
from app.modules.commissions.services import admin_ledger, lifecycle
from app.modules.contracts.models import Contract
from app.modules.commissions.tasks.dispatch import process_pending_outbox_events
from tests.test_commission_engine_integration import (
    _advance_to_active,
    _make_actor,
    _setup_contract_ready_to_activate,
)


@pytest.mark.asyncio
async def test_get_commission_movements_includes_full_traceability(db, organization_id):
    actor_user_id = await _make_actor(db, organization_id)
    contract, _sponsor = await _setup_contract_ready_to_activate(db, organization_id, actor_user_id)
    await _advance_to_active(db, organization_id, contract, actor_user_id)
    await process_pending_outbox_events(db)

    rows = await admin_ledger.get_commission_movements(db, organization_id=organization_id)
    assert len(rows) == 2  # the seller's direct share + the sponsor's indirect share

    producer_row = next(r for r in rows if r["depth_from_producer"] == 0)
    assert producer_row["contract_id"] == contract.id
    assert producer_row["movement_type"] == "DIRECT"
    assert producer_row["beneficiary_type"] == "SELLER"
    assert producer_row["calculation_type"] == "FIXED_AMOUNT"
    assert producer_row["amount_cents"] == 4000
    assert producer_row["reference_margin_cents"] == 4500
    assert producer_row["plan_name"] == "Piano di test" and producer_row["plan_version"] == 1
    assert producer_row["explanation"]
    assert producer_row["status"] == "PENDING"
    assert producer_row["paid_date"] is None

    sponsor_row = next(r for r in rows if r["depth_from_producer"] == 1)
    assert sponsor_row["movement_type"] == "INDIRECT"
    assert sponsor_row["calculation_type"] == "REMAINDER"
    assert sponsor_row["amount_cents"] == 500  # 45.00 margin minus 40.00 to the seller
    assert sponsor_row["role_at_calculation"] == "NETWORKER"


@pytest.mark.asyncio
async def test_get_commission_movements_filters_by_agent_and_status(db, organization_id):
    actor_user_id = await _make_actor(db, organization_id)
    contract, _sponsor = await _setup_contract_ready_to_activate(db, organization_id, actor_user_id)
    await _advance_to_active(db, organization_id, contract, actor_user_id)
    await process_pending_outbox_events(db)

    all_rows = await admin_ledger.get_commission_movements(db, organization_id=organization_id)
    one_agent = all_rows[0]["agent_id"]

    filtered = await admin_ledger.get_commission_movements(db, organization_id=organization_id, agent_id=one_agent)
    assert len(filtered) == 1
    assert filtered[0]["agent_id"] == one_agent

    pending_only = await admin_ledger.get_commission_movements(db, organization_id=organization_id, status="PENDING")
    assert len(pending_only) == 2
    paid_only = await admin_ledger.get_commission_movements(db, organization_id=organization_id, status="PAID")
    assert len(paid_only) == 0


@pytest.mark.asyncio
async def test_mark_movement_paid_transitions_status_and_is_idempotent_against_double_payment(db, organization_id):
    actor_user_id = await _make_actor(db, organization_id)
    contract, _sponsor = await _setup_contract_ready_to_activate(db, organization_id, actor_user_id)
    await _advance_to_active(db, organization_id, contract, actor_user_id)
    await process_pending_outbox_events(db)

    movement = (await db.execute(select(CommissionMovement).where(CommissionMovement.contract_id == contract.id))).scalars().first()
    assert movement.status == "PENDING"
    assert movement.paid_date is None

    # Unapproved movements cannot be paid.
    with pytest.raises(admin_ledger.CommissionPaymentError):
        await admin_ledger.mark_movement_paid(
            db, organization_id=organization_id, movement_id=movement.id, actor_user_id=actor_user_id
        )
    await lifecycle.transition(
        db, organization_id=organization_id, movement_ids=[movement.id], to_status="APPROVED",
        actor_user_id=actor_user_id,
    )

    paid = await admin_ledger.mark_movement_paid(
        db, organization_id=organization_id, movement_id=movement.id, actor_user_id=actor_user_id, note="Bonifico test"
    )
    assert paid.status == "PAID"
    assert paid.paid_date is not None

    with pytest.raises(admin_ledger.CommissionPaymentError):
        await admin_ledger.mark_movement_paid(
            db, organization_id=organization_id, movement_id=movement.id, actor_user_id=actor_user_id
        )


@pytest.mark.asyncio
async def test_commission_totals_by_level_aggregates_correctly(db, organization_id):
    actor_user_id = await _make_actor(db, organization_id)
    contract, _sponsor = await _setup_contract_ready_to_activate(db, organization_id, actor_user_id)
    await _advance_to_active(db, organization_id, contract, actor_user_id)
    await process_pending_outbox_events(db)

    levels = await admin_ledger.get_commission_totals_by_level(db, organization_id=organization_id)
    by_depth = {row["depth"]: row for row in levels}

    assert by_depth[0]["contracts"] == 1
    assert by_depth[0]["commission_cents"] == 4000
    contract_row = await db.get(Contract, contract.id)
    assert by_depth[0]["value_cents"] == contract_row.sale_amount_cents

    assert by_depth[1]["contracts"] == 1
    assert by_depth[1]["commission_cents"] == 500
