"""Licence register: assigning a licence to a company, the register pages and
the commercial margin of the resales (piano compensi, «Il margine
commerciale sulle licenze»)."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.modules.affiliate import licenses, service
from app.modules.affiliate.models import AffiliateLicense, AffiliateOperation
from app.modules.network import service as network_service

NOV = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)


@pytest.fixture
def clock(monkeypatch):
    monkeypatch.setattr(service, "utcnow", lambda: NOV)


async def _agent(db, org, name):
    return await network_service.create_agent(
        db, organization_id=org, first_name=name, last_name="Test",
        promoter_code=f"{name[:3].upper()}-{uuid.uuid4().hex[:6]}", parent_agent_id=None,
    )


async def _buy(db, org, agent, code):
    op = await service.create_purchase(db, organization_id=org, agent_id=agent.id, product_code=code, actor_user_id=None)
    return await service.confirm_operation(db, organization_id=org, operation_id=op.id, actor_user_id=None)


async def _free(db, org, agent):
    return list((await db.execute(select(AffiliateLicense).where(
        AffiliateLicense.organization_id == org, AffiliateLicense.owner_agent_id == agent.id,
        AffiliateLicense.status == "AVAILABLE").order_by(AffiliateLicense.created_at, AffiliateLicense.code))).scalars())


async def test_assign_to_a_new_company_reserves_the_licence_and_is_remembered(db, organization_id, clock):
    a = await _agent(db, organization_id, "Anna")
    await _buy(db, organization_id, a, "SMALL")
    lic = (await _free(db, organization_id, a))[0]
    op = await licenses.assign_license(
        db, organization_id=organization_id, agent_id=a.id, license_id=lic.id, client_id=None,
        new_client={"company_name": "Bar Centrale S.r.l.", "vat_number": "IT01234567890", "email": "Bar@Centrale.it"},
        actor_user_id=None, note="Consegnata a mano",
    )
    assert (op.kind, op.status) == ("LICENSE_RESALE", "PENDING")

    page = await licenses.licenses_page(db, organization_id, agent_id=a.id)
    assert page["counts"]["RESERVED"] == 1 and page["counts"]["AVAILABLE"] == 1
    row = next(r for r in page["items"] if r["id"] == lic.id)
    assert row["client"] == "Bar Centrale S.r.l."
    assert row["client_detail"]["email"] == "bar@centrale.it"
    assert row["assignment"]["status"] == "PENDING" and row["assignment"]["note"] == "Consegnata a mano"
    assert row["margin"] is None

    # Search on the server: by company, by VAT number, by licence code.
    for text in ("centrale", "01234567890", lic.code):
        found = await licenses.licenses_page(db, organization_id, agent_id=a.id, search=text)
        assert [r["id"] for r in found["items"]] == [lic.id]

    # Withdrawn before payment: the licence is free again.
    await service.cancel_operation(db, organization_id=organization_id, operation_id=op.id, actor_user_id=None,
                                   reason="ripensamento", agent_id=a.id)
    page = await licenses.licenses_page(db, organization_id, agent_id=a.id, status="AVAILABLE")
    assert page["total"] == 2


async def test_assign_needs_a_company(db, organization_id, clock):
    a = await _agent(db, organization_id, "Bruno")
    await _buy(db, organization_id, a, "SMALL")
    lic = (await _free(db, organization_id, a))[0]
    with pytest.raises(service.AffiliateError):
        await licenses.assign_license(db, organization_id=organization_id, agent_id=a.id, license_id=lic.id,
                                      client_id=None, new_client={"company_name": " "}, actor_user_id=None)


async def test_margin_of_a_small_package(db, organization_id, clock):
    """SMALL: 400 € for 2 licences. One resold: 450 collected, margin 250;
    if both are resold the margin is 900 - 400 = 500 (piano compensi)."""
    a = await _agent(db, organization_id, "Carla")
    await _buy(db, organization_id, a, "SMALL")
    lic = (await _free(db, organization_id, a))[0]
    op = await licenses.assign_license(db, organization_id=organization_id, agent_id=a.id, license_id=lic.id,
                                       client_id=None, new_client={"company_name": "Impresa Uno"}, actor_user_id=None)
    await service.confirm_operation(db, organization_id=organization_id, operation_id=op.id, actor_user_id=None)

    m = await licenses.agent_margins(db, organization_id, a.id)
    g = m["groups"][0]
    assert (g["product_code"], g["licenses"], g["available"], g["resold"]) == ("SMALL", 2, 1, 1)
    assert (g["cost"], g["collected"], g["margin"], g["potential_margin"]) == (
        Decimal("400.00"), Decimal("450.00"), Decimal("250.00"), Decimal("500.00"))
    assert m["totals"]["margin"] == Decimal("250.00")

    row = next(r for r in (await licenses.licenses_page(db, organization_id, agent_id=a.id))["items"] if r["id"] == lic.id)
    assert (row["status"], row["seller_amount"], row["margin"]) == ("RESOLD", Decimal("450.00"), Decimal("250.00"))

    office = await licenses.margins_page(db, organization_id, search="Carla")
    assert office["total"] == 1
    assert (office["items"][0]["resold"], office["items"][0]["margin"]) == (1, Decimal("250.00"))


async def test_large_package_potential_margin(db, organization_id, clock):
    a = await _agent(db, organization_id, "Dario")
    await _buy(db, organization_id, a, "LARGE")
    g = (await licenses.agent_margins(db, organization_id, a.id))["groups"][0]
    # 12 x 450 = 5.400 - 1.600 = 3.800 (piano compensi).
    assert (g["licenses"], g["potential_margin"], g["margin"]) == (12, Decimal("3800.00"), Decimal("0"))


async def test_resale_paid_on_mamify_uses_the_licence_already_assigned(db, organization_id, clock):
    a = await _agent(db, organization_id, "Elena")
    await _buy(db, organization_id, a, "MEDIUM")
    free = await _free(db, organization_id, a)
    client = await service.create_client(db, organization_id=organization_id, agent_id=a.id, company_name="Ottica Sole",
                                         vat_number=None, contact_name=None, email=None, phone=None)
    chosen = free[3]
    manual = await service.create_resale(db, organization_id=organization_id, agent_id=a.id, license_id=chosen.id,
                                         client_id=client.id, actor_user_id=None)

    op, created = await licenses.record_external_resale(db, organization_id=organization_id, seller_agent_id=a.id,
                                                        client_id=client.id, idempotency_key="MAMIFY:1:0:1")
    assert created and op.status == "CONFIRMED" and op.license_id == chosen.id
    await db.refresh(manual)
    assert manual.status == "CANCELLED"
    # Read again: same resale, nothing new.
    again, created = await licenses.record_external_resale(db, organization_id=organization_id, seller_agent_id=a.id,
                                                           client_id=client.id, idempotency_key="MAMIFY:1:0:1")
    assert not created and again.id == op.id

    # No assignment waiting: the oldest free licence.
    op2, _ = await licenses.record_external_resale(db, organization_id=organization_id, seller_agent_id=a.id,
                                                   client_id=client.id, idempotency_key="MAMIFY:2:0:1")
    assert op2.license_id == free[0].id


async def test_resale_paid_on_mamify_without_free_licences_is_refused(db, organization_id, clock):
    a = await _agent(db, organization_id, "Franco")
    client = await service.create_client(db, organization_id=organization_id, agent_id=a.id, company_name="Forno",
                                         vat_number=None, contact_name=None, email=None, phone=None)
    with pytest.raises(service.AffiliateError, match="licenze libere"):
        await licenses.record_external_resale(db, organization_id=organization_id, seller_agent_id=a.id,
                                              client_id=client.id, idempotency_key="MAMIFY:3:0:1")
    assert await db.scalar(select(AffiliateOperation.id).where(
        AffiliateOperation.idempotency_key == "MAMIFY:3:0:1")) is None
