"""SOS Affiliate fed by Mamify, end to end against a fake Mamify server.

The fake answers the read-only service paths with the shapes the real API
returned on 4/11/2026 (50 rows a page, newest first, order lines without a
product id); everything else is the real code on the real test database.
Any other path makes the fake fail the test: SOS must never write to Mamify.
"""

import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import func, select, update

from app.modules.affiliate import service as affiliate_service
from app.modules.affiliate.models import AffiliateCommission, AffiliateOperation
from app.modules.mamify import client as client_module
from app.modules.mamify import service
from app.modules.mamify.client import READ_ONLY_PATHS, MamifyApiError, MamifyClient
from app.modules.mamify.models import MamifyMember, MamifyOrder
from app.modules.network.models import AgentProfile, NetworkNode
from app.modules.rbac.models import Role
from app.modules.users.models import User

NOV = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)
ROOT = 317

CATALOG = {
    "sos-affiliate": [
        {"id": 17292, "name": "Digital Ambassador", "price": 49, "promo_price": None},
        {"id": 17280, "name": "Pacchetto Start", "price": 1000, "promo_price": None},
        {"id": 17285, "name": "Pacchetto Start", "price": 97, "promo_price": None},
        {"id": 17999, "name": "Ricarica MamiCash", "price": 100, "promo_price": None},
    ],
    "digitalambassador": [
        {"id": 17297, "name": "12 Licenze", "price": 6000, "promo_price": 1600},
        {"id": 17293, "name": "Licenze", "price": 500, "promo_price": None},
    ],
}


class FakeMamify:
    """People, orders and products of a pretend Mamify (httpx.MockTransport)."""

    def __init__(self):
        self.people: dict[int, dict] = {}
        self.orders: dict[int, list[dict]] = {}
        self.calls: list[tuple[str, dict]] = []
        self.passwords: dict[str, str] = {}
        self.rate_limited_once = False

    def person(self, pid, name, sponsor, email=None):
        self.people[pid] = {"id": pid, "first_name": name, "last_name": "Test", "email": email or f"{name.lower()}@test.it",
                            "phone": "+39000", "registration_date": "2026-10-01 10:00", "level": 1,
                            "sponsor_id": sponsor, "direct": 0, "total": 0}

    def order(self, buyer, oid, products, *, paid=True, status="3", label="Completato"):
        rows = self.orders.setdefault(buyer, [])
        rows[:] = [o for o in rows if o["id"] != oid]
        rows.insert(0, {"id": oid, "date": "2026-11-10 10:00", "status": status, "status_label": label, "paid": paid,
                        "total": sum(p["price"] * p.get("quantity", 1) for p in products), "products": products,
                        "status_history": []})

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.split("/m/api/", 1)[1]
        data = json.loads(request.content or b"{}")
        self.calls.append((path, data))
        assert path in READ_ONLY_PATHS, f"SOS called a non read-only Mamify path: {path}"
        assert request.headers.get("X-Fw360-Customertoken") == ""
        if self.rate_limited_once:
            self.rate_limited_once = False
            return httpx.Response(429, headers={"Retry-After": "1"}, json={"status": 0, "error": "rate_limited"})
        ok = lambda payload: httpx.Response(200, json={"status": 1, "data": payload},
                                            headers={"X-RateLimit-Remaining": "50", "X-RateLimit-Reset": "0"})
        root = {"id": ROOT, "first_name": "Condividiamo Ltd", "last_name": "", "email": "ltd@test.it"}
        if path == "plugins/mamify/rag/apps/list":
            return ok({"total": 1, "list": [{"code": "sos-affiliate"}]})
        asked = int(data["customer_id"]) if str(data.get("customer_id", "")).isdigit() else ROOT
        if path == "plugins/mamify/rag/customer/find":
            if asked == ROOT:
                return ok({"customer": root, "sponsor": None, "network": {"direct": 0, "total": len(self.people)}})
            if asked not in self.people:
                return httpx.Response(200, json={"status": 0, "error": "customer_not_found", "message": "no"})
            person = self.people[asked]
            sponsor = {"id": person["sponsor_id"]} if person["sponsor_id"] != ROOT else root
            return ok({"customer": {k: v for k, v in person.items() if k != "sponsor_id"}, "sponsor": sponsor,
                       "network": {"direct": 0, "total": 0}})
        if path == "plugins/mamify/rag/customer/network":
            assert data["scope"] == "all"
            rows = sorted((p for p in self.people.values() if asked == ROOT or self.below(p["id"], asked)),
                          key=lambda p: -p["id"])
            page = data["page"]
            return ok({"customer": root, "scope": "all", "total": len(rows), "page": page,
                       "list": rows[(page - 1) * 50: page * 50]})
        if path == "plugins/mamify/rag/customer/orders":
            rows = self.orders.get(int(data["customer_id"]), [])
            if data.get("order_id"):
                rows = [o for o in rows if o["id"] == int(data["order_id"])]
            return ok({"customer": {"id": data["customer_id"]}, "total": len(rows), "page": 1, "list": rows[:50]})
        if path == "plugins/mamify/rag/products/search":
            rows = [{**p, "app": {"code": data["app"], "name": data["app"]}, "categories": []}
                    for p in CATALOG.get(data["app"], [])]
            return ok({"total": len(rows), "page": 1, "list": rows})
        if path == "plugins/mamify/auth/login":
            if self.passwords.get(data["email"]) == data["password"]:
                person = next((p for p in self.people.values() if p["email"] == data["email"]), {})
                return ok({"customer": person, "access_token": f"tok-{person.get('id')}"})
            return httpx.Response(200, json={"status": 0, "error": "wrong_credentials", "message": "no"})
        raise AssertionError(f"unexpected path {path}")

    def below(self, pid, ancestor):
        seen = set()
        while pid in self.people and pid not in seen:
            seen.add(pid)
            pid = self.people[pid]["sponsor_id"]
            if pid == ancestor:
                return True
        return False

    def count(self, path_end):
        return len([c for c in self.calls if c[0].endswith(path_end)])


async def _no_sleep(_seconds):
    return None


@pytest.fixture
def mamify(monkeypatch):
    fake = FakeMamify()
    transport = httpx.MockTransport(fake.handler)
    monkeypatch.setattr(service, "client_for", lambda cfg: MamifyClient(cfg.base_url, cfg.api_key or "k",
                                                                         transport=transport, sleep=_no_sleep))
    monkeypatch.setattr(service, "_queue_new_members", lambda org: True)
    monkeypatch.setattr(client_module._Window, "remaining", None)
    return fake


@pytest.fixture
def clock(monkeypatch):
    monkeypatch.setattr(affiliate_service, "utcnow", lambda: NOV)


async def _admin(db, org):
    user = User(organization_id=org, email=f"admin-{uuid.uuid4().hex[:6]}@sos.it", password_hash="x", status="ACTIVE")
    db.add(user)
    await db.commit()
    return user


async def _configure(db, org, **extra):
    admin = await _admin(db, org)
    await service.update_config(db, organization_id=org, actor_user_id=admin.id, changes={
        "enabled": True, "api_key": "chiave-prova", "root_customer": str(ROOT),
        "cancelled_statuses": ["Annullato", "Rimborsato"], **extra,
    })
    return admin


async def _map(db, org, pid, code):
    admin = await _admin(db, org)
    await service.set_product_map(db, organization_id=org, mamify_product_id=str(pid), plan_code=code, title=None,
                                  actor_user_id=admin.id)


async def _agent(db, org, customer_id):
    member = (await db.execute(select(MamifyMember).where(
        MamifyMember.organization_id == org, MamifyMember.mamify_customer_id == str(customer_id)))).scalar_one()
    return await db.get(AgentProfile, member.agent_id)


async def _parent(db, org, agent_id):
    return await db.scalar(select(NetworkNode.direct_parent_agent_id).where(
        NetworkNode.organization_id == org, NetworkNode.agent_id == agent_id, NetworkNode.effective_to.is_(None)))


def _line(name, price, app="sos-affiliate", qty=1):
    return {"name": name, "quantity": qty, "price": price, "type": "product", "app": app}


async def _webhook(db, org, body, kind="orders/new"):
    cfg = await service.get_config(db, org)
    return await service.handle_webhook(db, cfg, kind, body)


async def _poll(db, org, calls=100):
    return await service.poll_orders(db, org, calls=calls)


# --- Read only -----------------------------------------------------------------


def test_only_read_paths_are_allowed():
    # Every allowed path is a service read or the login check.
    assert all("/rag/" in p or p == "plugins/mamify/auth/login" for p in READ_ONLY_PATHS)
    for forbidden in ("webhooks/create", "plugins/mamify/vouchers/distribute", "orders/updateStatus",
                      "customers/update", "multicall", "plugins/mamify/auth/delete"):
        assert forbidden not in READ_ONLY_PATHS


async def test_client_blocks_writes_before_any_request():
    sent = []
    client = MamifyClient("https://x/m/api", "k", transport=httpx.MockTransport(lambda r: sent.append(r)))
    for path in ("webhooks/create", "plugins/mamify/vouchers/distribute", "/orders/updateStatus/"):
        with pytest.raises(MamifyApiError) as err:
            await client.call(path, {"x": 1})
        assert err.value.code == "write_blocked"
    assert sent == []


async def test_client_waits_out_a_rate_limit(mamify):
    mamify.rate_limited_once = True
    client = service.client_for(type("C", (), {"base_url": "https://x/m/api", "api_key": "k"})())
    assert (await client.call("plugins/mamify/rag/apps/list", {}))["total"] == 1
    assert client.calls == 2


# --- Network -----------------------------------------------------------------


async def test_full_copy_reads_every_page_and_follows_changes(db, organization_id, mamify):
    await _configure(db, organization_id)
    mamify.person(10, "Anna", ROOT)
    mamify.person(11, "Bruno", 10)
    mamify.person(12, "Carla", 11)
    for pid in range(100, 220):  # 120 more people under Anna: three pages of 50
        mamify.person(pid, f"P{pid}", 10)
    result = await service.sync_network(db, organization_id)
    assert (result["members"], result["created"], result["errors"]) == (123, 123, [])
    assert mamify.count("rag/customer/network") == 3
    anna, bruno, carla = [(await _agent(db, organization_id, i)).id for i in (10, 11, 12)]
    assert await _parent(db, organization_id, anna) is None  # the root is the company, not a node
    assert await _parent(db, organization_id, bruno) == anna
    assert await _parent(db, organization_id, carla) == bruno
    anna_row = (await db.execute(select(MamifyMember).where(MamifyMember.agent_id == anna))).scalar_one()
    assert anna_row.direct_count == 121

    # Carla changes sponsor on Mamify; Bruno leaves the network.
    del mamify.people[11]
    mamify.people[12]["sponsor_id"] = 10
    result = await service.sync_network(db, organization_id)
    assert (result["created"], result["moved"], result["missing"]) == (0, 1, 1)
    assert await _parent(db, organization_id, carla) == anna
    bruno_row = (await db.execute(select(MamifyMember).where(MamifyMember.agent_id == bruno))).scalar_one()
    assert bruno_row.present is False


async def test_new_members_check_adds_only_the_newest(db, organization_id, mamify):
    await _configure(db, organization_id)
    assert "skipped" in await service.sync_new_members(db, organization_id)  # before the first copy
    mamify.person(10, "Anna", ROOT)
    mamify.person(11, "Bruno", 10)
    await service.sync_network(db, organization_id)
    calls_before = mamify.count("rag/customer/network")

    mamify.person(50, "Nuovo", 11)
    mamify.person(51, "Nuovissimo", 50)
    mamify.people[11]["sponsor_id"] = ROOT  # a move: left to the night's full copy
    result = await service.sync_new_members(db, organization_id)
    assert (result["created"], result["moved"], result["missing"], result["truncated"]) == (2, 0, 0, False)
    assert mamify.count("rag/customer/network") - calls_before == 1
    nuovo, nuovissimo = await _agent(db, organization_id, 50), await _agent(db, organization_id, 51)
    assert await _parent(db, organization_id, nuovo.id) == (await _agent(db, organization_id, 11)).id
    assert await _parent(db, organization_id, nuovissimo.id) == nuovo.id
    # Nothing new: one call, nothing written.
    assert (await service.sync_new_members(db, organization_id))["created"] == 0


async def test_branch_update_reads_only_that_branch(db, organization_id, mamify):
    await _configure(db, organization_id)
    mamify.person(10, "Anna", ROOT)
    mamify.person(11, "Bruno", 10)
    mamify.person(12, "Carla", 11)
    mamify.person(13, "Dario", ROOT)
    mamify.person(14, "Elena", 11)
    await service.sync_network(db, organization_id)
    anna = (await _agent(db, organization_id, 10)).id

    mamify.person(60, "Nuova", 11)        # new, inside Anna's branch
    mamify.people[12]["sponsor_id"] = 13  # Carla leaves the branch for Dario
    del mamify.people[14]                 # Elena leaves Mamify
    mamify.calls.clear()
    result = await service.sync_branch(db, organization_id, anna)
    assert (result["created"], result["moved"], result["missing"], result["errors"]) == (1, 1, 1, [])
    assert mamify.count("rag/customer/network") == 1  # one page: only the branch is read
    # root + Anna + the two who left the branch, looked up one by one
    assert mamify.count("rag/customer/find") == 4
    assert all(path in READ_ONLY_PATHS for path, _ in mamify.calls)
    assert await _parent(db, organization_id, (await _agent(db, organization_id, 60)).id) == \
        (await _agent(db, organization_id, 11)).id
    assert await _parent(db, organization_id, (await _agent(db, organization_id, 12)).id) == \
        (await _agent(db, organization_id, 13)).id
    elena = (await db.execute(select(MamifyMember).where(MamifyMember.mamify_customer_id == "14"))).scalar_one()
    assert elena.present is False
    anna_row = (await db.execute(select(MamifyMember).where(MamifyMember.agent_id == anna))).scalar_one()
    assert anna_row.branch_synced_at is not None and anna_row.branch_sync_result["created"] == 1


async def test_branch_update_request_is_queued_once_and_cooled_down(db, organization_id, mamify, monkeypatch):
    from app import celery_app

    await _configure(db, organization_id)
    mamify.person(10, "Anna", ROOT)
    await service.sync_network(db, organization_id)
    anna = (await _agent(db, organization_id, 10)).id
    queued = []
    monkeypatch.setattr(celery_app.mamify_branch_task, "delay", lambda *a: queued.append(a))
    first = await service.request_branch_sync(db, organization_id, anna)
    assert first["queued"] and first["running"]
    again = await service.request_branch_sync(db, organization_id, anna)
    assert again["queued"] is False and len(queued) == 1
    await service.sync_branch(db, organization_id, anna)
    with pytest.raises(service.MamifyError):  # just done: wait a little
        await service.request_branch_sync(db, organization_id, anna, by_self=True)
    with pytest.raises(service.MamifyError):  # not from Mamify
        from app.modules.network import service as network_service
        other = await network_service.create_agent(db, organization_id=organization_id, first_name="Locale",
                                                   last_name="", promoter_code="LOC1", parent_agent_id=None)
        await db.commit()
        await service.request_branch_sync(db, organization_id, other.id)


async def test_new_customer_webhook_queues_the_check(db, organization_id, mamify, monkeypatch):
    await _configure(db, organization_id)
    queued = []
    monkeypatch.setattr(service, "_queue_new_members", lambda org: queued.append(org) or True)
    assert await _webhook(db, organization_id, {"customer": {"id": 99}}, "customers/new") == "customer"
    assert queued == [organization_id]


# --- Orders ------------------------------------------------------------------


async def test_poller_applies_paid_sos_orders_once_and_skips_the_rest(db, organization_id, mamify, clock):
    await _configure(db, organization_id)
    mamify.person(10, "Anna", ROOT)
    await service.sync_network(db, organization_id)
    await _map(db, organization_id, 17297, "LARGE")
    anna = (await _agent(db, organization_id, 10)).id
    mamify.order(10, 501, [_line("12 Licenze", 1600, app="digitalambassador")])
    mamify.order(10, 502, [_line("Gift Card Glovo IT", 40, app="mamicash")])  # not SOS: never stored

    assert (await _poll(db, organization_id))["orders"] == 1
    await _poll(db, organization_id)  # read again: no new points
    states = dict((await db.execute(select(MamifyOrder.mamify_order_id, MamifyOrder.state).where(
        MamifyOrder.organization_id == organization_id))).all())
    assert states == {"501": "APPLIED"}
    assert (await affiliate_service.period_points(db, organization_id, "2026-11")).get(anna) == 1500
    ops = await db.scalar(select(func.count()).select_from(AffiliateOperation).where(
        AffiliateOperation.organization_id == organization_id, AffiliateOperation.agent_id == anna))
    assert ops == 1

    # Refunded on Mamify: points reversed.
    mamify.order(10, 501, [_line("12 Licenze", 1600, app="digitalambassador")], paid=False, status="5", label="Rimborsato")
    await _poll(db, organization_id)
    assert await db.scalar(select(MamifyOrder.state).where(MamifyOrder.mamify_order_id == "501")) == "CANCELLED"
    assert (await affiliate_service.period_points(db, organization_id, "2026-11")).get(anna, 0) == 0


async def test_same_name_products_are_told_apart_by_price(db, organization_id, mamify, clock):
    await _configure(db, organization_id)
    mamify.person(10, "Anna", ROOT)
    mamify.person(30, "Impresa", 10)
    await service.sync_network(db, organization_id)
    await _map(db, organization_id, 17280, "START")  # yearly Start only; the monthly one is not in the plan
    mamify.order(30, 700, [_line("Pacchetto Start", 1000)])
    mamify.order(30, 701, [_line("Pacchetto Start", 97)])
    await _poll(db, organization_id)
    states = dict((await db.execute(select(MamifyOrder.mamify_order_id, MamifyOrder.state).where(
        MamifyOrder.organization_id == organization_id))).all())
    assert states == {"700": "APPLIED", "701": "IGNORED"}
    status = await service.status(db, organization_id)
    assert {"id": "17285", "orders": 1} in status["unmapped_products"]


async def test_unpaid_and_unknown_buyer_wait(db, organization_id, mamify, clock):
    await _configure(db, organization_id)
    mamify.person(10, "Anna", ROOT)
    await service.sync_network(db, organization_id)
    await _map(db, organization_id, 17292, "DIGITAL_AMBASSADOR")
    mamify.order(10, 600, [_line("Digital Ambassador", 49)], paid=False, status="0", label="In attesa di pagamento")
    await _poll(db, organization_id)
    assert await db.scalar(select(MamifyOrder.state).where(MamifyOrder.mamify_order_id == "600")) == "RECEIVED"

    # A webhook about someone not yet copied waits; the new-members check applies it.
    body = {"order": {"id": 602, "customer_id": 20, "paid": True, "products": [_line("Digital Ambassador", 49)]},
            "status": {"id": 3, "title": "Completato"}}
    assert await _webhook(db, organization_id, body) == "order"
    assert await db.scalar(select(MamifyOrder.state).where(MamifyOrder.mamify_order_id == "602")) == "UNMATCHED"
    mamify.person(20, "Dario", 10)
    await service.sync_new_members(db, organization_id)
    row = (await db.execute(select(MamifyOrder).where(MamifyOrder.mamify_order_id == "602"))).scalar_one()
    await db.refresh(row)
    assert row.state == "APPLIED"


async def test_poller_reads_people_with_a_downline_first(db, organization_id, mamify):
    await _configure(db, organization_id)
    mamify.person(10, "Anna", ROOT)
    for pid in range(11, 20):
        mamify.person(pid, f"P{pid}", ROOT)
    mamify.person(40, "Figlio", 15)
    await service.sync_network(db, organization_id)
    await _poll(db, organization_id, calls=2)
    first = [int(c[1]["customer_id"]) for c in mamify.calls if c[0].endswith("rag/customer/orders")]
    assert 15 in first and len(first) == 2


async def test_pack_bought_by_company_pays_bd_to_its_sponsor_chain(db, organization_id, mamify, clock):
    await _configure(db, organization_id)
    mamify.person(10, "Anna", ROOT)
    mamify.person(11, "Bruno", 10)
    mamify.person(30, "Impresa", 11)  # the company, under the ambassador who brought it
    await service.sync_network(db, organization_id)
    await _map(db, organization_id, 17280, "START")
    mamify.order(30, 700, [_line("Pacchetto Start", 1000)])
    await _poll(db, organization_id)
    anna, bruno = await _agent(db, organization_id, 10), await _agent(db, organization_id, 11)
    rows = {c.beneficiary_agent_id: c.amount for c in (await db.execute(select(AffiliateCommission).where(
        AffiliateCommission.organization_id == organization_id, AffiliateCommission.kind == "BD"))).scalars()}
    assert rows == {bruno.id: Decimal("180.00"), anna.id: Decimal("70.00")}


async def test_topup_value_is_bm_base(db, organization_id, mamify, clock):
    await _configure(db, organization_id)
    mamify.person(10, "Anna", ROOT)
    mamify.person(30, "Impresa", 10)
    await service.sync_network(db, organization_id)
    await _map(db, organization_id, 17999, "MAMICASH_TOPUP")
    mamify.order(30, 800, [_line("Ricarica MamiCash", 100, qty=20)])
    await _poll(db, organization_id)
    anna = await _agent(db, organization_id, 10)
    bm = (await db.execute(select(AffiliateCommission).where(
        AffiliateCommission.organization_id == organization_id, AffiliateCommission.kind == "BM"))).scalar_one()
    assert (bm.beneficiary_agent_id, bm.amount) == (anna.id, Decimal("20.00"))


async def test_webhook_without_products_reads_the_order_from_mamify(db, organization_id, mamify, clock):
    await _configure(db, organization_id)
    mamify.person(10, "Anna", ROOT)
    await service.sync_network(db, organization_id)
    await _map(db, organization_id, 17297, "LARGE")
    mamify.order(10, 900, [_line("12 Licenze", 1600, app="digitalambassador")])
    await _webhook(db, organization_id, {"order": {"id": 900, "customer_id": 10, "paid": True},
                                         "status": {"id": 3, "title": "Completato"}})
    row = (await db.execute(select(MamifyOrder).where(MamifyOrder.mamify_order_id == "900"))).scalar_one()
    assert row.state == "APPLIED"


async def test_commissions_due_list_carries_the_mamify_customer(db, organization_id, mamify, clock, monkeypatch):
    monkeypatch.setattr(affiliate_service, "today_rome", lambda: NOV.date())
    await _configure(db, organization_id)
    mamify.person(10, "Anna", ROOT)
    mamify.person(30, "Impresa", 10)
    await service.sync_network(db, organization_id)
    await _map(db, organization_id, 17999, "MAMICASH_TOPUP")
    mamify.order(30, 810, [_line("Ricarica MamiCash", 100, qty=100)])
    await _poll(db, organization_id)
    calls = len(mamify.calls)
    due = await service.payable_for_mamify(db, organization_id)
    assert [(d["kind"], d["mamify_customer_id"], d["problem"]) for d in due] == [("BM", "10", None)]
    assert len(mamify.calls) == calls  # listing never calls Mamify


# --- Login -------------------------------------------------------------------


async def test_login_with_mamify_credentials_creates_local_login(db, organization_id, mamify):
    for code in ("CUSTOMER", "PROMOTER"):
        db.add(Role(organization_id=organization_id, code=code, name=code.title()))
    await db.commit()
    await _configure(db, organization_id)
    mamify.person(10, "Anna", ROOT, email="anna@test.it")
    mamify.passwords["anna@test.it"] = "pw-mamify"
    await service.sync_network(db, organization_id)

    assert not await service.login_via_mamify(db, organization_id=organization_id, email="anna@test.it", password="no")
    assert await service.login_via_mamify(db, organization_id=organization_id, email="anna@test.it", password="pw-mamify")
    anna = await _agent(db, organization_id, 10)
    assert anna.user_id is not None
    # Someone in Mamify but not in the SOS network gets nothing.
    mamify.passwords["altro@test.it"] = "x"
    assert not await service.login_via_mamify(db, organization_id=organization_id, email="altro@test.it", password="x")


async def test_login_never_takes_over_an_unrelated_local_account(db, organization_id, mamify):
    await _configure(db, organization_id)
    mamify.person(10, "Anna", ROOT, email="boss@sos.it")
    mamify.passwords["boss@sos.it"] = "pw"
    await service.sync_network(db, organization_id)
    db.add(User(organization_id=organization_id, email="boss@sos.it", password_hash="local", status="ACTIVE"))
    await db.commit()
    assert not await service.login_via_mamify(db, organization_id=organization_id, email="boss@sos.it", password="pw")


# --- Orders and customers screens ------------------------------------------------


async def test_orders_and_customers_pages(db, organization_id, mamify, clock):
    await _configure(db, organization_id)
    mamify.person(10, "Anna", ROOT)
    mamify.person(11, "Bruno", 10)
    mamify.person(12, "Carla", 10)
    await service.sync_network(db, organization_id)
    await _map(db, organization_id, 17297, "LARGE")
    mamify.order(10, 501, [_line("12 Licenze", 1600, app="digitalambassador")])
    mamify.order(11, 601, [_line("Pacchetto Strano", 729)])  # SOS app, not mapped
    await _poll(db, organization_id)

    orders = await service.orders_page(db, organization_id, page_size=1)
    assert (orders["total"], orders["pages"], len(orders["items"])) == (2, 2, 1)
    assert orders["counts"]["ALL"] == 2 and orders["counts"]["APPLIED"] == 1
    assert orders["applied_total"] == Decimal(1600)
    anna_orders = await service.orders_page(db, organization_id, search="anna")
    item = anna_orders["items"][0]
    assert anna_orders["total"] == 1 and item["buyer"]["name"] == "Anna Test"
    assert item["lines"][0]["name"] == "12 Licenze"
    assert (await service.orders_page(db, organization_id, state="APPLIED"))["total"] == 1

    everyone = await service.customers_page(db, organization_id)
    assert everyone["total"] == 3 and everyone["buyers"] == 2
    buyers = await service.customers_page(db, organization_id, buyers_only=True)
    assert {c["name"] for c in buyers["items"]} == {"Anna Test", "Bruno Test"}
    bruno = (await service.customers_page(db, organization_id, search="bruno"))["items"][0]
    assert bruno["sponsor"]["name"] == "Anna Test" and bruno["orders"] == 1

    # One customer's orders read on demand: one read-only call.
    mamify.order(12, 701, [_line("12 Licenze", 1600, app="digitalambassador")])
    await db.execute(update(MamifyMember).where(MamifyMember.mamify_customer_id == "12").values(orders_checked_at=None))
    await db.commit()
    mamify.calls.clear()
    out = await service.recheck_member_orders(db, organization_id, "12")
    assert out["found"] == 1 and mamify.count("rag/customer/orders") == 1
    with pytest.raises(service.MamifyError):  # just read
        await service.recheck_member_orders(db, organization_id, "12")


async def test_opening_the_dashboard_reads_ones_own_orders(db, organization_id, mamify, clock, monkeypatch):
    """The poller reaches a person about once an hour; opening one's own
    dashboard queues a read of one's own orders, at most every 2 minutes."""
    from app import celery_app

    await _configure(db, organization_id)
    mamify.person(10, "Anna", ROOT)
    await service.sync_network(db, organization_id)
    await _map(db, organization_id, 17297, "LARGE")
    anna = (await _agent(db, organization_id, 10)).id
    queued = []
    monkeypatch.setattr(celery_app.mamify_own_orders_task, "delay", lambda *a: queued.append(a))

    assert await service.request_own_orders(db, organization_id, anna) is True
    assert await service.request_own_orders(db, organization_id, anna) is False  # just asked
    assert queued == [(str(organization_id), "10")]

    mamify.order(10, 800, [_line("12 Licenze", 1600, app="digitalambassador")])
    assert (await service.read_own_orders(db, organization_id, "10"))["orders"] == 1
    assert await db.scalar(select(MamifyOrder.state).where(MamifyOrder.mamify_order_id == "800")) == "APPLIED"

    mine = await service.list_own_orders(db, organization_id, anna)
    assert [o["mamify_order_id"] for o in mine] == ["800"]
    assert mine[0]["state"] == "APPLIED" and mine[0]["products"][0]["name"] == "12 Licenze"
    assert mine[0]["bc_points"] > 0 and mine[0]["operations"][0]["kind"] == "LICENSE_PURCHASE"


async def test_a_product_moved_to_another_app_is_still_recognised(db, organization_id, mamify, clock):
    await _configure(db, organization_id)
    mamify.person(10, "Anna", ROOT)
    await service.sync_network(db, organization_id)
    await _map(db, organization_id, 17292, "DIGITAL_AMBASSADOR")
    cfg = await service.get_config(db, organization_id)
    cfg.product_catalog = {"items": [{"id": "17292", "app": "sos-affiliate", "name": "Digital Ambassador",
                                      "price": 49, "promo_price": None}]}
    await db.commit()
    mamify.order(10, 900, [_line("Digital Ambassador", 49, app="digitalambassador")])
    await _poll(db, organization_id)
    assert await db.scalar(select(MamifyOrder.state).where(MamifyOrder.mamify_order_id == "900")) == "APPLIED"


async def test_licence_paid_by_the_company_on_mamify_is_the_one_its_ambassador_assigned(db, organization_id, mamify, clock):
    from app.modules.affiliate import licenses
    from app.modules.affiliate.models import AffiliateClient, AffiliateLicense

    await _configure(db, organization_id)
    mamify.person(10, "Anna", ROOT)
    mamify.person(30, "Impresa", 10, email="Impresa@Test.it")
    await service.sync_network(db, organization_id)
    anna = await _agent(db, organization_id, 10)
    op = await affiliate_service.create_purchase(db, organization_id=organization_id, agent_id=anna.id,
                                                 product_code="SMALL", actor_user_id=None)
    await affiliate_service.confirm_operation(db, organization_id=organization_id, operation_id=op.id, actor_user_id=None)
    lics = list((await db.execute(select(AffiliateLicense).where(AffiliateLicense.owner_agent_id == anna.id)
                                  .order_by(AffiliateLicense.code))).scalars())
    # Anna typed the company in herself and gave it her second licence.
    await licenses.assign_license(db, organization_id=organization_id, agent_id=anna.id, license_id=lics[1].id,
                                  client_id=None, new_client={"company_name": "Impresa S.r.l.", "email": "impresa@test.it"},
                                  actor_user_id=None)

    await _map(db, organization_id, 17293, "LICENSE_RESALE")
    mamify.order(30, 950, [_line("Licenze", 500, app="digitalambassador")])
    await _poll(db, organization_id)

    assert await db.scalar(select(MamifyOrder.state).where(MamifyOrder.mamify_order_id == "950")) == "APPLIED"
    await db.refresh(lics[1])
    assert lics[1].status == "RESOLD"
    clients = list((await db.execute(select(AffiliateClient).where(AffiliateClient.agent_id == anna.id))).scalars())
    assert [(c.company_name, c.mamify_customer_id) for c in clients] == [("Impresa S.r.l.", "30")]
    resale = (await db.execute(select(AffiliateCommission).where(
        AffiliateCommission.organization_id == organization_id, AffiliateCommission.kind == "RESALE"))).scalar_one()
    assert (resale.beneficiary_agent_id, resale.amount) == (anna.id, Decimal("450.00"))

    # Read and processed again: nothing more.
    await service.recheck_all_orders(db, organization_id)
    await _poll(db, organization_id)
    order_row = (await db.execute(select(MamifyOrder).where(MamifyOrder.mamify_order_id == "950"))).scalar_one()
    await service.process_order(db, await service.get_config(db, organization_id), order_row.id)
    assert await db.scalar(select(func.count()).select_from(AffiliateCommission).where(
        AffiliateCommission.organization_id == organization_id, AffiliateCommission.kind == "RESALE")) == 1


async def test_licence_paid_on_mamify_waits_while_the_ambassador_has_none(db, organization_id, mamify, clock):
    await _configure(db, organization_id)
    mamify.person(10, "Anna", ROOT)
    mamify.person(30, "Impresa", 10)
    await service.sync_network(db, organization_id)
    await _map(db, organization_id, 17293, "LICENSE_RESALE")
    mamify.order(30, 951, [_line("Licenze", 500, app="digitalambassador")])
    await _poll(db, organization_id)
    row = (await db.execute(select(MamifyOrder).where(MamifyOrder.mamify_order_id == "951"))).scalar_one()
    assert row.state == "ERROR" and "licenze libere" in row.message

    anna = await _agent(db, organization_id, 10)
    op = await affiliate_service.create_purchase(db, organization_id=organization_id, agent_id=anna.id,
                                                 product_code="LICENSE_1", actor_user_id=None)
    await affiliate_service.confirm_operation(db, organization_id=organization_id, operation_id=op.id, actor_user_id=None)
    await service.retry_waiting_orders(db, organization_id)
    await db.refresh(row)
    assert row.state == "APPLIED"
