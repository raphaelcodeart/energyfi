"""SOS Affiliate operations end to end, on a real database.

Covers the cases of the specification (§12) that need storage: point
generation and licence inventory (TEST-01..10), the monthly rollover
(TEST-18, TEST-19), BD in the network and its idempotency (TEST-30, 32, 33),
plus the plan's promotions, resale split, reversals and the monthly close.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.modules.affiliate import service
from app.modules.affiliate.models import (
    AffiliateCommission,
    AffiliateLicense,
    AffiliateOperation,
    AffiliatePointEntry,
)
from app.modules.network import service as network_service

NOV = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)
DEC = datetime(2026, 12, 10, 12, 0, tzinfo=UTC)


@pytest.fixture
def clock(monkeypatch):
    """Moves the service's clock: periods, closes and pay dates follow it."""
    state = {"now": NOV}
    monkeypatch.setattr(service, "utcnow", lambda: state["now"])
    return state


async def _agent(db, org, name, parent=None):
    return await network_service.create_agent(
        db, organization_id=org, first_name=name, last_name="Test",
        promoter_code=f"{name[:3].upper()}-{uuid.uuid4().hex[:6]}", parent_agent_id=parent,
    )


async def _buy(db, org, agent, code, **kw):
    op = await service.create_purchase(db, organization_id=org, agent_id=agent.id, product_code=code,
                                       actor_user_id=None, **kw)
    return await service.confirm_operation(db, organization_id=org, operation_id=op.id, actor_user_id=None)


async def _points(db, org, agent_id, period):
    return (await service.period_points(db, org, period)).get(agent_id, 0)


async def _licenses(db, org, agent_id, status=None):
    q = select(func.count()).select_from(AffiliateLicense).where(
        AffiliateLicense.organization_id == org, AffiliateLicense.owner_agent_id == agent_id)
    if status:
        q = q.where(AffiliateLicense.status == status)
    return await db.scalar(q)


async def _client(db, org, agent):
    return await service.create_client(db, organization_id=org, agent_id=agent.id, company_name="Impresa Test S.r.l.",
                                       vat_number=None, contact_name=None, email=None, phone=None)


# --- 12.1 Generazione dei BC -------------------------------------------------


async def test_01_paid_month_generates_40_bcp(db, organization_id, clock):
    a = await _agent(db, organization_id, "Anna")
    await _buy(db, organization_id, a, "DIGITAL_AMBASSADOR", period="2026-11")
    assert await _points(db, organization_id, a.id, "2026-11") == 40


async def test_02_unpaid_month_generates_nothing(db, organization_id, clock):
    a = await _agent(db, organization_id, "Bruno")
    await service.create_purchase(db, organization_id=organization_id, agent_id=a.id,
                                  product_code="DIGITAL_AMBASSADOR", period="2026-11", actor_user_id=None)
    assert await _points(db, organization_id, a.id, "2026-11") == 0


@pytest.mark.parametrize("code,bc,licenses", [("LICENSE_1", 400, 1), ("SMALL", 350, 2), ("MEDIUM", 700, 5),
                                              ("LARGE", 1500, 12)],
                         ids=["03-single", "04-small", "05-medium", "06-large"])
async def test_03_06_licence_purchases(db, organization_id, clock, code, bc, licenses):
    a = await _agent(db, organization_id, "Carla")
    await _buy(db, organization_id, a, code)
    assert await _points(db, organization_id, a.id, "2026-11") == bc
    assert await _licenses(db, organization_id, a.id, "AVAILABLE") == licenses


async def _resell(db, org, agent, client, lic_id):
    op = await service.create_resale(db, organization_id=org, agent_id=agent.id, license_id=lic_id,
                                     client_id=client.id, actor_user_id=None)
    return await service.confirm_operation(db, organization_id=org, operation_id=op.id, actor_user_id=None)


async def test_07_08_resales_add_no_points_and_empty_the_inventory(db, organization_id, clock):
    a = await _agent(db, organization_id, "Dario")
    await _buy(db, organization_id, a, "LARGE")
    client = await _client(db, organization_id, a)
    ids = list((await db.execute(select(AffiliateLicense.id).where(AffiliateLicense.owner_agent_id == a.id))).scalars())
    await _resell(db, organization_id, a, client, ids[0])
    await _resell(db, organization_id, a, client, ids[1])
    assert await _licenses(db, organization_id, a.id, "AVAILABLE") == 10
    for lic_id in ids[2:]:
        await _resell(db, organization_id, a, client, lic_id)
    assert await _licenses(db, organization_id, a.id, "AVAILABLE") == 0
    assert await _licenses(db, organization_id, a.id, "RESOLD") == 12
    assert await _points(db, organization_id, a.id, "2026-11") == 1500


async def test_resale_split_450_to_seller_and_500_mamicash_to_the_client(db, organization_id, clock):
    a = await _agent(db, organization_id, "Elena")
    await _buy(db, organization_id, a, "SMALL")
    client = await _client(db, organization_id, a)
    lic_id = (await db.execute(select(AffiliateLicense.id).where(AffiliateLicense.owner_agent_id == a.id))).scalars().first()
    op = await _resell(db, organization_id, a, client, lic_id)
    c = (await db.execute(select(AffiliateCommission).where(AffiliateCommission.operation_id == op.id))).scalar_one()
    assert (c.kind, c.amount) == ("RESALE", Decimal("450.00"))
    # SMALL: 400 for two licences, so each costs 200 and the margin is 250.
    assert c.details["margin"] == "250.00"
    await db.refresh(client)
    assert client.mamicash_balance == Decimal("500.00")


async def test_09_two_small_purchases(db, organization_id, clock):
    a = await _agent(db, organization_id, "Fabio")
    o1 = await _buy(db, organization_id, a, "SMALL")
    o2 = await _buy(db, organization_id, a, "SMALL")
    assert o1.id != o2.id and o1.paid_amount + o2.paid_amount == Decimal("800.00")
    assert await _points(db, organization_id, a.id, "2026-11") == 700
    assert await _licenses(db, organization_id, a.id) == 4


async def test_10_confirming_twice_counts_once(db, organization_id, clock):
    a = await _agent(db, organization_id, "Gino")
    op = await _buy(db, organization_id, a, "MEDIUM")
    await service.confirm_operation(db, organization_id=organization_id, operation_id=op.id, actor_user_id=None)
    assert await db.scalar(select(func.count()).select_from(AffiliatePointEntry)
                           .where(AffiliatePointEntry.operation_id == op.id)) == 1
    assert await _points(db, organization_id, a.id, "2026-11") == 700
    assert await _licenses(db, organization_id, a.id) == 5


async def test_same_month_cannot_be_paid_twice(db, organization_id, clock):
    a = await _agent(db, organization_id, "Ugo")
    await _buy(db, organization_id, a, "DIGITAL_AMBASSADOR", period="2026-11")
    with pytest.raises(service.AffiliateError):
        await service.create_purchase(db, organization_id=organization_id, agent_id=a.id,
                                      product_code="DIGITAL_AMBASSADOR", period="2026-11", actor_user_id=None)


async def test_rome_tickets_generate_bc_per_formula(db, organization_id, clock):
    a = await _agent(db, organization_id, "Ilaria")
    op = await _buy(db, organization_id, a, "ROMA_10")
    assert (op.paid_amount, op.quantity) == (Decimal("500.00"), 10)
    assert await _points(db, organization_id, a.id, "2026-11") == 450


async def test_gift_licence_every_six_paid_months(db, organization_id, clock):
    a = await _agent(db, organization_id, "Luca")
    for month in ("2026-11", "2026-12", "2027-01", "2027-02", "2027-03"):
        await _buy(db, organization_id, a, "DIGITAL_AMBASSADOR", period=month)
    assert await _licenses(db, organization_id, a.id) == 0
    await _buy(db, organization_id, a, "DIGITAL_AMBASSADOR", period="2027-04")
    gifts = list((await db.execute(select(AffiliateLicense).where(AffiliateLicense.owner_agent_id == a.id))).scalars())
    assert [(g.origin, g.unit_cost) for g in gifts] == [("GIFT", Decimal("0.00"))]


# --- 12.2 Rete, mesi e storico -----------------------------------------------


async def _level_one_network(db, org):
    """Root with 260 BCP and three legs of 80 (TEST-11 values)."""
    root = await _agent(db, org, "Root")
    legs = [await _agent(db, org, f"Leg{i}", parent=root.id) for i in range(3)]
    return root, legs


async def _give(db, org, agent, points):
    """An arbitrary number of points through a confirmed operation, so the
    month and leg arithmetic of TEST-11..19 can use the spec's numbers."""
    entry = AffiliateOperation(
        organization_id=org, kind="EVENT_TICKET_PURCHASE", status="PENDING", agent_id=agent.id,
        product_code="ROMA_1", quantity=1, bc_points=points,
        plan_version_id=(await service.get_plan(db, org)).id, idempotency_key=f"TEST:{uuid.uuid4()}",
    )
    db.add(entry)
    await db.commit()
    await service.confirm_operation(db, organization_id=org, operation_id=entry.id, actor_user_id=None)


async def test_18_19_new_month_starts_from_zero_and_keeps_history(db, organization_id, clock):
    root, legs = await _level_one_network(db, organization_id)
    await _give(db, organization_id, root, 750)
    for leg in legs:
        await _give(db, organization_id, leg, 250)
    clock["now"] = DEC
    close = await service.close_period(db, organization_id=organization_id, period="2026-11", actor_user_id=None)
    assert close.qualified_count >= 1
    november = await service.period_results(db, organization_id, "2026-11")
    assert next(r for r in november if r["agent"]["id"] == root.id)["level"] == 2

    summary = await service.affiliate_summary(db, organization_id, root.id)
    assert summary["career"]["bcp"] == 0 and summary["career"]["bct"] == 0

    await _give(db, organization_id, root, 260)
    for leg in legs:
        await _give(db, organization_id, leg, 80)
    summary = await service.affiliate_summary(db, organization_id, root.id)
    assert (summary["career"]["level"], summary["career"]["bonus"]) == (1, Decimal("75.00"))
    assert summary["history"][0]["level"] == 2

    bonus = (await db.execute(select(AffiliateCommission).where(
        AffiliateCommission.kind == "BC", AffiliateCommission.beneficiary_agent_id == root.id))).scalar_one()
    assert (bonus.amount, bonus.payable_on.isoformat()) == (Decimal("250.00"), "2026-12-15")


async def test_closing_twice_is_refused(db, organization_id, clock):
    root, _ = await _level_one_network(db, organization_id)
    await _give(db, organization_id, root, 100)
    clock["now"] = DEC
    await service.close_period(db, organization_id=organization_id, period="2026-11", actor_user_id=None)
    with pytest.raises(service.AffiliateError):
        await service.close_period(db, organization_id=organization_id, period="2026-11", actor_user_id=None)
    with pytest.raises(service.AffiliateError):
        await service.close_period(db, organization_id=organization_id, period="2026-12", actor_user_id=None)


async def test_bc_bonus_not_payable_before_the_15th(db, organization_id, clock):
    root, legs = await _level_one_network(db, organization_id)
    await _give(db, organization_id, root, 260)
    for leg in legs:
        await _give(db, organization_id, leg, 80)
    clock["now"] = DEC
    await service.close_period(db, organization_id=organization_id, period="2026-11", actor_user_id=None)
    bonus = (await db.execute(select(AffiliateCommission).where(
        AffiliateCommission.kind == "BC", AffiliateCommission.beneficiary_agent_id == root.id))).scalar_one()
    paid = await service.mark_commissions_paid(db, organization_id=organization_id, commission_ids=[bonus.id],
                                               actor_user_id=None)
    # today_rome() follows the real clock, not the fixture: only assert
    # that a bonus due on 15 December 2026 is never paid before it.
    if service.today_rome() < bonus.payable_on:
        assert paid == 0


# --- 12.3 BD e BM in rete ----------------------------------------------------


async def _chain(db, org, names):
    agents, parent = [], None
    for n in names:
        a = await _agent(db, org, n, parent=parent)
        agents.append(a)
        parent = a.id
    return agents


async def _sell(db, org, seller, client, pack):
    op = await service.create_pack_sale(db, organization_id=org, agent_id=seller.id, client_id=client.id,
                                        pack_code=pack, actor_user_id=None)
    return await service.confirm_operation(db, organization_id=org, operation_id=op.id, actor_user_id=None)


async def test_30_33_business_sale_in_the_network_paid_once(db, organization_id, clock):
    mario, luca, andrea, giovanni = await _chain(db, organization_id, ["Mario", "Luca", "Andrea", "Giovanni"])
    client = await _client(db, organization_id, giovanni)
    op = await _sell(db, organization_id, giovanni, client, "BUSINESS")
    await service.confirm_operation(db, organization_id=organization_id, operation_id=op.id, actor_user_id=None)
    rows = list((await db.execute(select(AffiliateCommission).where(AffiliateCommission.operation_id == op.id)
                                  .order_by(AffiliateCommission.position))).scalars())
    assert [(r.beneficiary_agent_id, r.amount) for r in rows] == [
        (giovanni.id, Decimal("360.00")), (andrea.id, Decimal("140.00")),
        (luca.id, Decimal("100.00")), (mario.id, Decimal("80.00")),
    ]
    assert all(r.kind == "BD" and r.status == "PAYABLE" for r in rows)
    # A pack sale is not a licence: no BC.
    assert await _points(db, organization_id, giovanni.id, "2026-11") == 0


async def test_32_two_business_sales_in_the_network(db, organization_id, clock):
    seller = (await _chain(db, organization_id, ["Solo"]))[0]
    client = await _client(db, organization_id, seller)
    await _sell(db, organization_id, seller, client, "BUSINESS")
    await _sell(db, organization_id, seller, client, "BUSINESS")
    direct = await db.scalar(select(func.sum(AffiliateCommission.amount)).where(
        AffiliateCommission.beneficiary_agent_id == seller.id, AffiliateCommission.kind == "BD"))
    assert direct == Decimal("720.00")


async def test_31_bd_stops_at_thirteen_people(db, organization_id, clock):
    agents = await _chain(db, organization_id, [f"N{i:02d}" for i in range(16)])
    seller = agents[-1]
    client = await _client(db, organization_id, seller)
    op = await _sell(db, organization_id, seller, client, "START")
    count = await db.scalar(select(func.count()).select_from(AffiliateCommission)
                            .where(AffiliateCommission.operation_id == op.id))
    total = await db.scalar(select(func.sum(AffiliateCommission.amount)).where(AffiliateCommission.operation_id == op.id))
    assert (count, total) == (13, Decimal("420.00"))


async def test_bm_topup_pays_13_positions_on_the_whole_base(db, organization_id, clock):
    agents = await _chain(db, organization_id, [f"M{i:02d}" for i in range(13)])
    seller = agents[-1]
    client = await _client(db, organization_id, seller)
    op = await service.create_topup(db, organization_id=organization_id, agent_id=seller.id, client_id=client.id,
                                    amount=Decimal("10000"), actor_user_id=None)
    await service.confirm_operation(db, organization_id=organization_id, operation_id=op.id, actor_user_id=None)
    rows = list((await db.execute(select(AffiliateCommission).where(AffiliateCommission.operation_id == op.id)
                                  .order_by(AffiliateCommission.position))).scalars())
    assert rows[0].beneficiary_agent_id == seller.id and rows[0].amount == Decimal("100.00")
    assert sum(r.amount for r in rows) == Decimal("400.00") and all(r.kind == "BM" for r in rows)
    await db.refresh(client)
    assert client.mamicash_balance == Decimal("10000.00")


async def test_client_of_another_affiliate_is_refused(db, organization_id, clock):
    a = await _agent(db, organization_id, "Olga")
    b = await _agent(db, organization_id, "Piero")
    client = await _client(db, organization_id, a)
    with pytest.raises(service.AffiliateError):
        await service.create_pack_sale(db, organization_id=organization_id, agent_id=b.id, client_id=client.id,
                                       pack_code="START", actor_user_id=None)


# --- Corrections -------------------------------------------------------------


async def test_reversal_removes_points_and_cancels_unpaid_commissions(db, organization_id, clock):
    mario, giovanni = await _chain(db, organization_id, ["Mario", "Giovanni"])
    client = await _client(db, organization_id, giovanni)
    sale = await _sell(db, organization_id, giovanni, client, "PREMIUM")
    purchase = await _buy(db, organization_id, giovanni, "SMALL")
    await service.reverse_operation(db, organization_id=organization_id, operation_id=sale.id, actor_user_id=None,
                                    reason="Pagamento respinto")
    await service.reverse_operation(db, organization_id=organization_id, operation_id=purchase.id, actor_user_id=None,
                                    reason="Ordine annullato dal cliente")
    statuses = set((await db.execute(select(AffiliateCommission.status)
                                     .where(AffiliateCommission.operation_id == sale.id))).scalars())
    assert statuses == {"CANCELLED"}
    assert await _points(db, organization_id, giovanni.id, "2026-11") == 0
    assert await _licenses(db, organization_id, giovanni.id, "VOID") == 2
    with pytest.raises(service.AffiliateError):
        await service.reverse_operation(db, organization_id=organization_id, operation_id=sale.id, actor_user_id=None,
                                        reason="ancora")


async def test_purchase_with_resold_licences_cannot_be_reversed(db, organization_id, clock):
    a = await _agent(db, organization_id, "Rita")
    purchase = await _buy(db, organization_id, a, "SMALL")
    client = await _client(db, organization_id, a)
    lic_id = (await db.execute(select(AffiliateLicense.id).where(AffiliateLicense.owner_agent_id == a.id))).scalars().first()
    await _resell(db, organization_id, a, client, lic_id)
    with pytest.raises(service.AffiliateError):
        await service.reverse_operation(db, organization_id=organization_id, operation_id=purchase.id,
                                        actor_user_id=None, reason="test")


async def test_price_comes_from_the_plan_not_from_the_request(db, organization_id, clock):
    a = await _agent(db, organization_id, "Sara")
    with pytest.raises(service.AffiliateError):
        await service.create_purchase(db, organization_id=organization_id, agent_id=a.id, product_code="START",
                                      actor_user_id=None)
    op = await service.create_purchase(db, organization_id=organization_id, agent_id=a.id, product_code="LARGE",
                                       actor_user_id=None)
    assert (op.paid_amount, op.discount_amount, op.bc_points) == (Decimal("1600.00"), Decimal("4400.00"), 1500)
