"""SOS Affiliate HTTP routes: the Digital Ambassador area and the admin
console, through the real FastAPI app.

The services are covered in test_sos_affiliate_flows.py; this checks what
only the routes do: the affiliate is the session's, never one named in the
request; permissions gate the admin side; amounts leave as decimal strings.
"""

import uuid

import httpx
import pytest

from app.foundation import deps
from app.foundation.security import hash_password
from app.modules.network import service as network_service
from app.modules.users.models import User


async def _user(db, org, prefix):
    user = User(organization_id=org, email=f"{prefix}-{uuid.uuid4().hex[:8]}@example.demo",
                password_hash=hash_password("irrelevant"))
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest.fixture
async def api(db, organization_id, monkeypatch):
    from app.foundation.db import get_db
    from app.foundation.deps import CurrentUser, get_current_user
    from app.main import app

    state = {"user": None, "granted": set()}

    async def _codes(*args, **kwargs):
        return state["granted"]

    async def _db():
        yield db

    monkeypatch.setattr(deps, "get_permission_codes_for_user", _codes)
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        user_id=state["user"].id, organization_id=organization_id, roles=[]
    )
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test/api") as client:
            yield client, state
    finally:
        app.dependency_overrides.clear()


async def test_ambassador_purchase_confirmed_by_admin_then_pack_sale(db, organization_id, api):
    client, state = api
    sponsor_user = await _user(db, organization_id, "sponsor")
    da_user = await _user(db, organization_id, "da")
    admin = await _user(db, organization_id, "admin")
    sponsor = await network_service.create_agent(db, organization_id=organization_id, first_name="Sara", last_name="Sponsor",
                                                 promoter_code=f"SPO-{uuid.uuid4().hex[:6]}", parent_agent_id=None,
                                                 user_id=sponsor_user.id)
    await network_service.create_agent(db, organization_id=organization_id, first_name="Dino", last_name="Ambassador",
                                       promoter_code=f"DIN-{uuid.uuid4().hex[:6]}", parent_agent_id=sponsor.id,
                                       user_id=da_user.id)

    # --- the Digital Ambassador orders a LARGE package ---
    state["user"] = da_user
    assert (await client.get("/affiliate/catalog")).status_code == 200
    me = (await client.get("/affiliate/me")).json()
    assert (me["career"]["bcp"], me["sponsor"]["name"]) == (0, "Sara Sponsor")
    # A price in the body is ignored: the plan decides.
    order = await client.post("/affiliate/me/purchases", json={"product_code": "LARGE", "paid_amount": "1.00"})
    assert order.status_code == 201, order.text
    assert (order.json()["status"], order.json()["paid_amount"], order.json()["bc_points"]) == ("PENDING", "1600.00", 1500)

    # --- confirming needs payments.manage ---
    state["user"] = admin
    refused = await client.post(f"/affiliate/admin/operations/{order.json()['id']}/confirm", json={})
    assert refused.status_code == 403
    state["granted"] = {"payments.manage", "commissions.read_branch", "commissions.approve", "commissions.pay"}
    confirmed = await client.post(f"/affiliate/admin/operations/{order.json()['id']}/confirm", json={})
    assert confirmed.json()["status"] == "CONFIRMED"
    again = await client.post(f"/affiliate/admin/operations/{order.json()['id']}/confirm", json={})
    assert again.status_code == 200

    state["user"] = da_user
    me = (await client.get("/affiliate/me")).json()
    assert (me["career"]["bcp"], me["licenses"]["available"]) == (1500, 12)
    state["user"] = sponsor_user
    sponsor_me = (await client.get("/affiliate/me")).json()
    assert (sponsor_me["career"]["bcp"], sponsor_me["career"]["bct"]) == (0, 1500)
    assert sponsor_me["legs"][0]["points"] == 1500

    # --- a BUSINESS pack sold to a client company ---
    state["user"] = da_user
    company = await client.post("/affiliate/me/clients", json={"company_name": "Officina Rossi S.n.c."})
    assert company.status_code == 201
    sale = await client.post("/affiliate/me/pack-sales", json={"client_id": company.json()["id"], "pack_code": "BUSINESS"})
    assert sale.status_code == 201, sale.text
    state["user"] = admin
    await client.post(f"/affiliate/admin/operations/{sale.json()['id']}/confirm", json={})
    state["user"] = da_user
    bd = (await client.get("/affiliate/me/commissions?kind=BD")).json()
    assert [(r["position"], r["amount"]) for r in bd] == [(1, "360.00")]
    state["user"] = sponsor_user
    bd = (await client.get("/affiliate/me/commissions?kind=BD")).json()
    assert [(r["position"], r["amount"]) for r in bd] == [(2, "140.00")]

    # --- admin views and export ---
    state["user"] = admin
    overview = (await client.get("/affiliate/admin/overview")).json()
    assert overview["total_points"] == 1500
    affiliates = (await client.get("/affiliate/admin/affiliates")).json()
    assert {a["agent"]["name"] for a in affiliates} >= {"Sara Sponsor", "Dino Ambassador"}
    export = await client.get("/affiliate/admin/export/operations")
    assert export.status_code == 200 and export.headers["content-type"].startswith("text/csv")
    assert "LICENSE_PURCHASE" in export.text and "1600,00" in export.text
    plan = (await client.get("/affiliate/admin/plan")).json()
    assert plan[0]["is_current"] and len(plan[0]["config"]["career_levels"]) == 11
    assert (await client.get("/affiliate/admin/periods")).status_code == 200


async def test_account_without_profile_gets_a_clear_404(db, organization_id, api):
    client, state = api
    state["user"] = await _user(db, organization_id, "nobody")
    res = await client.get("/affiliate/me")
    assert res.status_code == 404
    assert "Digital Ambassador" in res.json()["detail"]
