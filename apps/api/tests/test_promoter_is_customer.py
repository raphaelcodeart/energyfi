"""A promoter is also a customer: their login carries the CUSTOMER role and a
customer record, so they can switch between the two areas."""

import uuid

import pytest
from sqlalchemy import select

from app.modules.customers.models import Customer
from app.modules.network import service as network_service
from app.modules.rbac import service as rbac_service
from app.modules.rbac.models import Role
from app.seed.bootstrap import _ensure_promoters_are_customers
from tests.test_commission_engine_integration import _make_actor


async def _roles(db, organization_id):
    for code in ("CUSTOMER", "PROMOTER"):
        db.add(Role(organization_id=organization_id, code=code, name=code.title()))
    await db.commit()


@pytest.mark.asyncio
async def test_a_new_root_promoter_is_also_a_customer(db, organization_id):
    await _roles(db, organization_id)
    actor = await _make_actor(db, organization_id)
    agent, user, _code, _password = await network_service.create_root_promoter_with_login(
        db, organization_id=organization_id, first_name="Rita", last_name="Radice",
        email=f"rita-{uuid.uuid4().hex[:6]}@example.com", promoter_code=None, actor_user_id=actor,
    )
    roles = await rbac_service.get_roles_for_user(db, user_id=user.id, organization_id=organization_id)
    assert {"PROMOTER", "CUSTOMER"} <= set(roles)
    customer = (await db.execute(select(Customer).where(Customer.user_id == user.id))).scalar_one()
    assert customer.email == user.email

    # They can open a contract for themselves: at the root, they are their own referrer.
    from app.modules.contracts import service as contract_service

    producer, substituted = await contract_service.resolve_self_service_producer(
        db, organization_id=organization_id, customer_id=customer.id
    )
    assert producer == agent.id and substituted is None


@pytest.mark.asyncio
async def test_a_promoter_below_a_sponsor_buys_through_the_sponsor(db, organization_id):
    from app.foundation.security import hash_password
    from app.modules.contracts import service as contract_service
    from app.modules.users.models import User

    await _roles(db, organization_id)
    actor = await _make_actor(db, organization_id)
    sponsor, *_ = await network_service.create_root_promoter_with_login(
        db, organization_id=organization_id, first_name="Sara", last_name="Sponsor",
        email=f"sara-{uuid.uuid4().hex[:6]}@example.com", promoter_code=None, actor_user_id=actor,
    )
    user = User(organization_id=organization_id, email=f"figlio-{uuid.uuid4().hex[:6]}@example.com",
                password_hash=hash_password("irrelevant"))
    db.add(user)
    await db.flush()
    await rbac_service.assign_role(db, user_id=user.id, organization_id=organization_id, role_code="PROMOTER")
    child = await network_service.create_agent(
        db, organization_id=organization_id, first_name="Figlio", last_name="Rete",
        promoter_code=f"FIG-{uuid.uuid4().hex[:8]}", parent_agent_id=sponsor.id, user_id=user.id,
    )
    await db.commit()
    await _ensure_promoters_are_customers(db, org_id=organization_id)
    await db.commit()

    customer = (await db.execute(select(Customer).where(Customer.user_id == child.user_id))).scalar_one()
    producer, _ = await contract_service.resolve_self_service_producer(
        db, organization_id=organization_id, customer_id=customer.id
    )
    assert producer == sponsor.id


@pytest.mark.asyncio
async def test_bootstrap_makes_existing_promoters_customers_once(db, organization_id):
    await _roles(db, organization_id)
    actor = await _make_actor(db, organization_id)
    _agent, user, _code, _password = await network_service.create_root_promoter_with_login(
        db, organization_id=organization_id, first_name="Ugo", last_name="Uno",
        email=f"ugo-{uuid.uuid4().hex[:6]}@example.com", promoter_code=None, actor_user_id=actor,
    )
    # Already a customer: the backfill adds nothing, twice.
    assert await _ensure_promoters_are_customers(db, org_id=organization_id) == 0
    await db.commit()
    assert await _ensure_promoters_are_customers(db, org_id=organization_id) == 0
    count = (await db.execute(select(Customer.id).where(Customer.user_id == user.id))).all()
    assert len(count) == 1


@pytest.mark.asyncio
async def test_bootstrap_backfills_a_promoter_who_was_never_a_customer(db, organization_id):
    from app.foundation.security import hash_password
    from app.modules.users.models import User

    await _roles(db, organization_id)
    user = User(organization_id=organization_id, email=f"solo-{uuid.uuid4().hex[:6]}@example.com",
                password_hash=hash_password("irrelevant"))
    db.add(user)
    await db.flush()
    await rbac_service.assign_role(db, user_id=user.id, organization_id=organization_id, role_code="PROMOTER")
    await network_service.create_agent(
        db, organization_id=organization_id, first_name="Solo", last_name="Promoter",
        promoter_code=f"SOL-{uuid.uuid4().hex[:8]}", parent_agent_id=None, user_id=user.id,
    )
    await db.commit()

    assert await _ensure_promoters_are_customers(db, org_id=organization_id) == 1
    await db.commit()
    assert await _ensure_promoters_are_customers(db, org_id=organization_id) == 0
    roles = await rbac_service.get_roles_for_user(db, user_id=user.id, organization_id=organization_id)
    assert "CUSTOMER" in roles
