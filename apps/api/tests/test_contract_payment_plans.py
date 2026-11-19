"""Contract payment plans: single payment, 3 instalments, 12 instalments.

Covers contracts only; the shop checkout is separate. Two areas matter: the
instalment arithmetic must stay within a few cents of the total, and the
webhook must tell a redelivered event apart from the next monthly
`invoice.paid` of the same subscription.
"""

import hashlib
import hmac
import json
import time
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.foundation.security import hash_password
from app.modules.catalog.models import Product, ProductVersion
from app.modules.contracts import payment_plans
from app.modules.contracts import service as contract_service
from app.modules.contracts.models import Contract
from app.modules.customers.models import Address, Customer, SupplyPoint
from app.modules.network import service as network_service
from app.modules.payments import service as payments_service
from app.modules.payments.models import StripeWebhookEvent
from app.modules.users.models import User
from tests.split_helpers import install_plan

NOW = datetime(2026, 1, 1, tzinfo=UTC)
WEBHOOK_SECRET = "whsec_test_secret"


# --- Instalment arithmetic -----------------------------------------------------


def test_a_price_that_divides_evenly_has_no_rounding_at_all():
    """249.00, the reference contract price, divides exactly by 3 and 12."""
    for key, expected_instalment in (
        (payment_plans.PLAN_FULL, 249_00),
        (payment_plans.PLAN_INSTALMENTS_3, 83_00),
        (payment_plans.PLAN_MONTHLY_12, 20_75),
    ):
        plan = payment_plans.plan_by_key(key)
        b = payment_plans.breakdown_for(plan, 249_00)
        assert b.instalment_cents == expected_instalment
        assert b.total_cents == 249_00
        assert b.rounding_difference_cents == 0


def test_a_price_that_does_not_divide_reports_the_difference_instead_of_hiding_it():
    plan = payment_plans.plan_by_key(payment_plans.PLAN_MONTHLY_12)
    b = payment_plans.breakdown_for(plan, 100_00)
    assert b.instalment_cents == 8_33
    assert b.total_cents == 99_96
    assert b.contract_total_cents == 100_00
    # The rounding difference is shown to the customer, never absorbed.
    assert b.rounding_difference_cents == -4


def test_the_rounding_difference_can_never_be_large():
    """For any price, splitting moves the total by at most a few cents."""
    for total in range(100, 100_000, 137):
        for plan in payment_plans.PAYMENT_PLANS:
            b = payment_plans.breakdown_for(plan, total)
            assert abs(b.rounding_difference_cents) <= plan.instalments // 2


def test_the_single_payment_discount_is_rounded_and_frozen():
    full = payment_plans.plan_by_key(payment_plans.PLAN_FULL)
    b = payment_plans.breakdown_for(full, 180_00, discount_percentage=32)
    assert (b.discount_cents, b.total_cents, b.instalment_cents, b.discount_percentage) == (57_60, 122_40, 122_40, 32)
    assert payment_plans.discount_cents_for(99_99, 32) == 32_00  # 31.9968 rounded half-up
    # Read back from the contract regardless of the current setting.
    contract = Contract(gross_amount_cents=180_00, payment_discount_cents=57_60)
    assert payment_plans.contract_breakdown(full, contract).total_cents == 122_40
    # Instalment plans are never discounted.
    twelve = payment_plans.plan_by_key(payment_plans.PLAN_MONTHLY_12)
    assert payment_plans.breakdown_for(twelve, 180_00, discount_percentage=32).total_cents == 180_00
    assert payment_plans.contract_breakdown(twelve, Contract(gross_amount_cents=180_00, payment_discount_cents=57_60)).total_cents == 180_00


def test_an_amount_too_small_to_split_drops_that_option():
    """Stripe rejects zero-amount recurring prices, so tiny totals cannot be
    split."""
    keys = {b.plan.key for b in payment_plans.available_breakdowns(5)}
    assert payment_plans.PLAN_FULL in keys
    assert payment_plans.PLAN_MONTHLY_12 not in keys


# --- Webhook -------------------------------------------------------------------


async def _make_payable_contract(db, organization_id, *, gross_cents: int = 249_00) -> Contract:
    user = User(
        organization_id=organization_id, email=f"c-{uuid.uuid4().hex[:8]}@example.com",
        password_hash=hash_password("irrelevant"),
    )
    db.add(user)
    await db.flush()
    customer = Customer(
        organization_id=organization_id, kind="PRIVATE", user_id=user.id,
        email=f"c-{uuid.uuid4().hex[:8]}@example.com",
    )
    db.add(customer)
    await db.flush()
    address = Address(
        organization_id=organization_id, customer_id=customer.id, kind="SUPPLY",
        street="Via Test 1", city="Roma", province="RM", postal_code="00100",
    )
    db.add(address)
    await db.flush()
    supply_point = SupplyPoint(
        organization_id=organization_id, customer_id=customer.id, energy_type="ELECTRICITY",
        supply_address_id=address.id,
    )
    db.add(supply_point)
    product = Product(
        organization_id=organization_id, code=f"P-{uuid.uuid4().hex[:6]}",
        energy_type="ELECTRICITY", customer_type="BOTH", category="INTERNAL",
    )
    db.add(product)
    await db.flush()
    version = ProductVersion(
        product_id=product.id, version_label="1.0", name="Energia Plus",
        base_price_cents=gross_cents, valid_from=NOW,
    )
    db.add(version)
    agent = await network_service.create_agent(
        db, organization_id=organization_id, first_name="Prod", last_name="Uttore",
        promoter_code=f"PR-{uuid.uuid4().hex[:8]}", parent_agent_id=None,
    )
    await db.commit()
    await install_plan(db, organization_id, product_version=version, rules=[
        {"beneficiary_type": "SELLER", "calculation_type": "PERCENTAGE", "percentage": 60},
        {"beneficiary_type": "COMPANY", "calculation_type": "REMAINDER"},
    ])

    contract = await contract_service.create_contract(
        db, organization_id=organization_id, customer_id=customer.id,
        supply_point_id=supply_point.id, product_version_id=version.id,
        producer_agent_id=agent.id, actor_user_id=user.id, correlation_id=str(uuid.uuid4()),
    )
    for step in ["SUBMITTED", "UNDER_REVIEW", "APPROVED"]:
        contract = await contract_service.transition_contract(
            db, organization_id=organization_id, contract=contract, to_status=step,
            actor_user_id=user.id, reason="test", notes=None, correlation_id=str(uuid.uuid4()),
        )
    # APPROVED auto-cascades to PAYMENT_PENDING, when the customer can pay.
    assert contract.status == "PAYMENT_PENDING"
    # Activation on payment requires an admin to accept the commission preview.
    from app.modules.commissions.services.preview import build_commission_preview

    preview = await build_commission_preview(db, organization_id=organization_id, contract=contract)
    await contract_service.accept_commission_plan(
        db, organization_id=organization_id, contract=contract, checksum=preview["checksum"],
        actor_user_id=user.id,
    )
    return contract


def _signed(payload: dict) -> tuple[bytes, str]:
    """Build a genuinely signed webhook body so tests exercise
    construct_event() and the real StripeObject shape."""
    body = json.dumps(payload).encode()
    timestamp = int(time.time())
    signature = hmac.new(
        WEBHOOK_SECRET.encode(), f"{timestamp}.".encode() + body, hashlib.sha256
    ).hexdigest()
    return body, f"t={timestamp},v1={signature}"


async def _configure_stripe(db, organization_id) -> None:
    """Store Stripe keys directly on the organization settings."""
    from app.modules.organizations.models import Organization

    org = await db.get(Organization, organization_id)
    org.settings = {
        **(org.settings or {}),
        "stripe_secret_key": "sk_test_fake",
        "stripe_publishable_key": "pk_test_fake",
        "stripe_webhook_secret": WEBHOOK_SECRET,
    }
    await db.commit()


@pytest.mark.asyncio
async def test_a_paid_checkout_activates_the_contract(db, organization_id):
    await _configure_stripe(db, organization_id)
    contract = await _make_payable_contract(db, organization_id)
    await contract_service.attach_stripe_checkout_session(
        db, contract=contract, session_id="cs_test_1", plan_key=payment_plans.PLAN_FULL
    )

    body, sig = _signed({
        "id": "evt_test_1",
        "type": "checkout.session.completed",
        "data": {"object": {
            "id": "cs_test_1",
            "metadata": {"kind": "contract", "contract_id": str(contract.id)},
        }},
    })
    await payments_service.handle_webhook_event(
        db, organization_id=organization_id, payload=body, sig_header=sig
    )

    await db.refresh(contract)
    # PAID cascades through ACTIVATION_PENDING into ACTIVE, which triggers commissions.
    assert contract.status == "ACTIVE"
    assert contract.paid_at is not None


@pytest.mark.asyncio
async def test_the_same_event_delivered_twice_changes_nothing(db, organization_id):
    """Stripe delivers at least once, so duplicate events are ignored."""
    await _configure_stripe(db, organization_id)
    contract = await _make_payable_contract(db, organization_id)
    await contract_service.attach_stripe_checkout_session(
        db, contract=contract, session_id="cs_test_2", plan_key=payment_plans.PLAN_FULL
    )
    payload = {
        "id": "evt_test_2",
        "type": "checkout.session.completed",
        "data": {"object": {"id": "cs_test_2", "metadata": {"kind": "contract"}}},
    }
    for _ in range(3):
        body, sig = _signed(payload)
        await payments_service.handle_webhook_event(
            db, organization_id=organization_id, payload=body, sig_header=sig
        )

    rows = list((await db.execute(
        select(StripeWebhookEvent).where(StripeWebhookEvent.stripe_event_id == "evt_test_2")
    )).scalars())
    assert len(rows) == 1, "l'evento deve essere registrato una sola volta"
    await db.refresh(contract)
    assert contract.status == "ACTIVE"


@pytest.mark.asyncio
async def test_the_success_url_is_not_what_marks_a_contract_paid(db, organization_id):
    """Visiting the success URL does nothing; only a signed webhook marks a
    contract PAID."""
    await _configure_stripe(db, organization_id)
    contract = await _make_payable_contract(db, organization_id)
    await contract_service.attach_stripe_checkout_session(
        db, contract=contract, session_id="cs_test_3", plan_key=payment_plans.PLAN_MONTHLY_12
    )
    await db.refresh(contract)
    assert contract.status == "PAYMENT_PENDING"
    assert contract.paid_at is None


@pytest.mark.asyncio
async def test_an_unsigned_or_tampered_payload_is_refused(db, organization_id):
    await _configure_stripe(db, organization_id)
    with pytest.raises(payments_service.WebhookVerificationError):
        await payments_service.handle_webhook_event(
            db, organization_id=organization_id,
            payload=b'{"id":"evt_x","type":"checkout.session.completed"}',
            sig_header="t=1,v1=deadbeef",
        )


@pytest.mark.asyncio
async def test_a_failed_instalment_warns_everybody_without_suspending_the_contract(db, organization_id):
    """A declined monthly charge does not cut off the contract automatically,
    but staff are notified."""
    await _configure_stripe(db, organization_id)
    contract = await _make_payable_contract(db, organization_id)
    await contract_service.attach_stripe_checkout_session(
        db, contract=contract, session_id="cs_test_4", plan_key=payment_plans.PLAN_MONTHLY_12
    )
    body, sig = _signed({
        "id": "evt_test_4",
        "type": "checkout.session.completed",
        "data": {"object": {"id": "cs_test_4", "metadata": {"kind": "contract"}, "subscription": "sub_test_4"}},
    })
    await payments_service.handle_webhook_event(
        db, organization_id=organization_id, payload=body, sig_header=sig
    )
    await db.refresh(contract)
    assert contract.status == "ACTIVE"

    outcome = await contract_service.record_subscription_invoice(
        db, organization_id=organization_id, subscription_id="sub_test_4",
        paid=False, amount_cents=20_75,
    )
    assert "NON riscossa" in outcome
    await db.refresh(contract)
    assert contract.status == "ACTIVE", "un addebito fallito non sospende il contratto da solo"


@pytest.mark.asyncio
async def test_a_successful_instalment_is_recorded(db, organization_id):
    await _configure_stripe(db, organization_id)
    contract = await _make_payable_contract(db, organization_id)
    contract.stripe_subscription_id = "sub_test_5"
    await db.commit()

    outcome = await contract_service.record_subscription_invoice(
        db, organization_id=organization_id, subscription_id="sub_test_5",
        paid=True, amount_cents=20_75,
    )
    assert "incassata" in outcome


@pytest.mark.asyncio
async def test_an_event_for_an_unknown_subscription_is_harmless(db, organization_id):
    outcome = await contract_service.record_subscription_invoice(
        db, organization_id=organization_id, subscription_id="sub_nonexistent",
        paid=True, amount_cents=100,
    )
    assert "nessun contratto" in outcome


@pytest.mark.asyncio
async def test_an_approved_contract_paid_in_instalments_keeps_its_plan(db, organization_id):
    """Paying an approved contract by card keeps its instalment plan: it is
    not mistaken for a staff-confirmed bank transfer and rewritten to a
    single FULL payment."""
    from app.modules.contracts.models import ContractInstalment

    await _configure_stripe(db, organization_id)
    contract = await _make_payable_contract(db, organization_id, gross_cents=180_00)
    await contract_service.attach_stripe_checkout_session(
        db, contract=contract, session_id="cs_twelve_approved", plan_key=payment_plans.PLAN_MONTHLY_12
    )
    contract = await contract_service.record_card_payment(db, organization_id=organization_id, contract=contract)
    assert contract.payment_plan == payment_plans.PLAN_MONTHLY_12
    assert contract.payment_method == "CARD"
    rows = list((await db.execute(select(ContractInstalment).where(ContractInstalment.contract_id == contract.id))).scalars())
    assert len(rows) == 12 and rows[0].amount_cents == 15_00 and rows[0].status == "PAID"

