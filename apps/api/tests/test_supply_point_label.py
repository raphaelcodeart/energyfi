"""Every supply point has a human-readable label, computed at creation when
none is given, so lists are not just POD/PDR codes."""

import uuid

import pytest

from app.modules.customers import service as customer_service
from app.modules.customers.models import Customer
from app.modules.customers.schemas import SupplyPointCreate, SupplyPointUpdate
from tests.test_commission_engine_integration import _make_actor


async def _make_customer(db, organization_id):
    customer = Customer(organization_id=organization_id, kind="PRIVATE", email="label@example.com")
    db.add(customer)
    await db.commit()
    await db.refresh(customer)
    return customer


@pytest.mark.asyncio
async def test_supply_point_label_auto_computed_when_omitted(db, organization_id):
    actor_user_id = await _make_actor(db, organization_id)
    customer = await _make_customer(db, organization_id)

    supply_point = await customer_service.add_supply_point(
        db, organization_id=organization_id, customer_id=customer.id, actor_user_id=actor_user_id,
        payload=SupplyPointCreate(
            energy_type="ELECTRICITY", street="Via Roma 12", city="Milano", province="MI", postal_code="20100",
        ),
    )
    assert supply_point.label == "Energia elettrica - Via Roma 12, Milano"


@pytest.mark.asyncio
async def test_supply_point_label_explicit_value_is_preserved(db, organization_id):
    actor_user_id = await _make_actor(db, organization_id)
    customer = await _make_customer(db, organization_id)

    supply_point = await customer_service.add_supply_point(
        db, organization_id=organization_id, customer_id=customer.id, actor_user_id=actor_user_id,
        payload=SupplyPointCreate(
            label="Abitazione principale", energy_type="GAS", street="Via Torino 4", city="Torino",
            province="TO", postal_code="10100",
        ),
    )
    assert supply_point.label == "Abitazione principale"


@pytest.mark.asyncio
async def test_supply_point_label_can_be_updated(db, organization_id):
    actor_user_id = await _make_actor(db, organization_id)
    customer = await _make_customer(db, organization_id)

    supply_point = await customer_service.add_supply_point(
        db, organization_id=organization_id, customer_id=customer.id, actor_user_id=actor_user_id,
        payload=SupplyPointCreate(
            energy_type="GAS", street="Via Napoli 8", city="Napoli", province="NA", postal_code="80100",
        ),
    )

    updated = await customer_service.update_supply_point(
        db, organization_id=organization_id, supply_point_id=supply_point.id, actor_user_id=actor_user_id,
        payload=SupplyPointUpdate(label="Seconda casa - mare"),
    )
    assert updated.label == "Seconda casa - mare"


@pytest.mark.asyncio
async def test_update_supply_point_returns_none_for_unknown_org(db, organization_id):
    actor_user_id = await _make_actor(db, organization_id)
    result = await customer_service.update_supply_point(
        db, organization_id=organization_id, supply_point_id=uuid.uuid4(), actor_user_id=actor_user_id,
        payload=SupplyPointUpdate(label="x"),
    )
    assert result is None
