"""The collaborator card opened from the network tree: earnings per Split
Plan list the people whose sales paid them, and the position and network
figures match the tree."""

import pytest

from app.modules.network.card import get_agent_card
from tests.test_split_plans_integration import _activate, _contract, _plan, _world


@pytest.mark.asyncio
async def test_the_card_shows_each_plan_with_the_people_behind_the_earnings(db, organization_id):
    w = await _world(db, organization_id)
    plan = await _plan(db, organization_id, w)
    await _activate(db, organization_id, w, await _contract(db, organization_id, w, w["luca"]))
    await _activate(db, organization_id, w, await _contract(db, organization_id, w, w["anna"]))

    card = await get_agent_card(db, organization_id=organization_id, agent_id=w["anna"].id, include_contact=False)

    assert [u["name"] for u in card["upline"]] == [w["mario"].display_name]
    assert card["network"]["direct"] == 1 and card["network"]["total"] == 1
    assert card["sales"]["own_sold"] == 1 and card["sales"]["network_sold"] == 1
    assert card["agent"]["email"] is None

    [entry] = card["plans"]
    assert entry["plan_id"] == plan.id
    people = {p["name"]: p for p in entry["people"]}
    assert set(people) == {"Vendita propria", w["luca"].display_name}
    # 50% of her own sale and 20% (level 1) of Luca's, on a 150 EUR margin.
    assert people["Vendita propria"]["earned_cents"] == 7500
    assert people[w["luca"].display_name]["earned_cents"] == 3000
    assert entry["earned_cents"] == card["earnings"]["total_cents"] == 10500


@pytest.mark.asyncio
async def test_a_card_from_another_organization_is_not_found(db, organization_id):
    import uuid

    assert await get_agent_card(db, organization_id=organization_id, agent_id=uuid.uuid4(), include_contact=True) is None


@pytest.mark.asyncio
async def test_the_product_network_shows_only_buyers_within_the_company_depth(db, organization_id):
    from app.modules.catalog.models import Company
    from app.modules.network.card import get_product_network

    w = await _world(db, organization_id)
    await _plan(db, organization_id, w)
    await _activate(db, organization_id, w, await _contract(db, organization_id, w, w["anna"]))
    await _activate(db, organization_id, w, await _contract(db, organization_id, w, w["luca"]))

    view = await get_product_network(db, organization_id=organization_id, agent_id=w["anna"].id, product_id=w["product"].id)
    assert [(lvl["depth"], lvl["buyers"]) for lvl in view["levels"]] == [(1, 1), (2, 1)]
    tree = view["tree"]
    assert tree["agent_id"] == str(w["anna"].id)
    luca = next(c for c in tree["children"] if c["agent_id"] == str(w["luca"].id))
    assert [c["role_label"] for c in luca["children"]] == ["Cliente · ha acquistato"]

    # A company that reaches one level only hides Luca's customer.
    company = Company(organization_id=organization_id, name="FibraNet", max_network_depth=1)
    db.add(company)
    await db.flush()
    w["product"].company_id = company.id
    await db.commit()
    view = await get_product_network(db, organization_id=organization_id, agent_id=w["anna"].id, product_id=w["product"].id)
    assert view["depth_limit"] == 1
    assert [(lvl["depth"], lvl["buyers"]) for lvl in view["levels"]] == [(1, 1)]
    assert all(c["agent_id"] != str(w["luca"].id) for c in view["tree"]["children"])


@pytest.mark.asyncio
async def test_joining_a_company_shows_up_for_the_promoter_and_for_staff(db, organization_id):
    from app.modules.catalog.models import Company
    from app.modules.network import card

    w = await _world(db, organization_id)
    await _plan(db, organization_id, w)
    company = Company(organization_id=organization_id, name="FibraNet", max_network_depth=2)
    db.add(company)
    await db.flush()
    w["product"].company_id = company.id
    await db.commit()
    await _activate(db, organization_id, w, await _contract(db, organization_id, w, w["luca"]))

    mine = await card.get_my_companies(db, organization_id=organization_id, agent_id=w["anna"].id)
    assert [(c["name"], c["joined_at"], c["network_buyers"]) for c in mine] == [("FibraNet", None, 1)]

    await card.set_membership(db, organization_id=organization_id, agent_id=w["anna"].id, company_id=company.id, join=True)
    await card.set_membership(db, organization_id=organization_id, agent_id=w["anna"].id, company_id=company.id, join=True)
    mine = await card.get_my_companies(db, organization_id=organization_id, agent_id=w["anna"].id)
    assert mine[0]["joined_at"] is not None

    staff = await card.get_company_participants(db, organization_id=organization_id, company_id=company.id)
    assert [m["name"] for m in staff["members"]] == [w["anna"].display_name]
    assert [s["name"] for s in staff["sellers_not_members"]] == [w["luca"].display_name]
    assert len(staff["customers"]) == 1

    await card.set_membership(db, organization_id=organization_id, agent_id=w["anna"].id, company_id=company.id, join=False)
    staff = await card.get_company_participants(db, organization_id=organization_id, company_id=company.id)
    assert staff["members"] == [] and len(staff["former_members"]) == 1
