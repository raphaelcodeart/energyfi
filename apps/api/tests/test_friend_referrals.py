"""Friend referrals: one level, no commissions, a cashback bonus every 10 active referrals.

Every customer, promoter or not, has a flat list of people who signed up
through their link. The list is separate from the commercial network and pays
nobody. Commercial placement follows the usual rules:

  - referrer is a promoter      -> the referrer's own tree
  - referrer is not a promoter  -> under the referrer's own promoter

A referral counts towards the gift only once one of their contracts is ACTIVE.
"""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.foundation.security import hash_password
from app.modules.auth import service as auth_service
from app.modules.auth.schemas import RegisterRequest
from app.modules.catalog.models import Product, ProductVersion
from app.modules.contracts import service as contract_service
from app.modules.customers.models import Address, Customer, SupplyPoint
from app.modules.friend_referrals import service as friend_referrals_service
from app.modules.friend_referrals.models import FriendReferral
from app.modules.network import service as network_service
from app.modules.rbac.models import Role
from app.modules.referral import service as referral_service
from app.modules.referral.models import CustomerAttribution, PromoterCode
from app.modules.users.models import User

NOW = datetime(2026, 1, 1, tzinfo=UTC)


async def _make_customer_role(db, organization_id) -> Role:
    role = Role(organization_id=organization_id, code="CUSTOMER", name="Customer")
    db.add(role)
    await db.commit()
    return role


async def _make_promoter(db, organization_id, *, name: str, parent_agent_id=None, with_login=True):
    user = None
    if with_login:
        user = User(
            organization_id=organization_id, email=f"{name.lower()}-{uuid.uuid4().hex[:6]}@example.com",
            password_hash=hash_password("irrelevant"),
        )
        db.add(user)
        await db.flush()
    agent = await network_service.create_agent(
        db, organization_id=organization_id, first_name=name, last_name="Promoter",
        promoter_code=f"{name[:3].upper()}-{uuid.uuid4().hex[:8]}",
        parent_agent_id=parent_agent_id, user_id=user.id if user else None,
    )
    code = await referral_service.get_or_create_promoter_code(
        db, organization_id=organization_id, agent_id=agent.id
    )
    await db.commit()
    return agent, user, code


async def _register_through(db, organization_id, code: str, *, email: str) -> User:
    return await auth_service.register_with_referral(
        db, organization_id=organization_id,
        payload=RegisterRequest(
            organization_id=str(organization_id),
            email=email, password="correct-horse-battery-staple", kind="PRIVATE",
            first_name="Nuovo", last_name="Cliente", referral_code=code, accept_privacy=True,
        ),
    )


async def _customer_of(db, organization_id, user_id) -> Customer:
    return (
        await db.execute(
            select(Customer).where(Customer.organization_id == organization_id, Customer.user_id == user_id)
        )
    ).scalar_one()


async def _agent_behind_attribution(db, organization_id, customer_id) -> uuid.UUID:
    attribution = await referral_service.get_current_attribution(
        db, organization_id=organization_id, customer_id=customer_id
    )
    code = await db.get(PromoterCode, attribution.promoter_code_id)
    return code.agent_id


async def _activate_a_contract_for(db, organization_id, customer: Customer, producer_agent_id):
    product = Product(
        organization_id=organization_id, code=f"P-{uuid.uuid4().hex[:6]}",
        energy_type="ELECTRICITY", customer_type="BOTH", category="INTERNAL",
    )
    db.add(product)
    await db.flush()
    version = ProductVersion(
        product_id=product.id, version_label="1.0", name="Luce", base_price_cents=15_00, valid_from=NOW
    )
    db.add(version)
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
    await db.commit()

    contract = await contract_service.create_contract(
        db, organization_id=organization_id, customer_id=customer.id, supply_point_id=supply_point.id,
        product_version_id=version.id, producer_agent_id=producer_agent_id,
        actor_user_id=customer.user_id, correlation_id=str(uuid.uuid4()),
    )
    for step in ["SUBMITTED", "UNDER_REVIEW", "APPROVED", "PAID"]:
        contract = await contract_service.transition_contract(
            db, organization_id=organization_id, contract=contract, to_status=step,
            actor_user_id=customer.user_id, reason="test", notes=None, correlation_id=str(uuid.uuid4()),
        )
    return contract


# --- Placement ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_plain_customers_link_puts_the_new_customer_under_their_own_promoter(db, organization_id):
    """A non-promoter inviter has no downline: the invitee joins the tree
    under the inviter's promoter and still appears in the inviter's list."""
    await _make_customer_role(db, organization_id)
    agent, _agent_user, promoter_code = await _make_promoter(db, organization_id, name="Anna")

    inviter_user = await _register_through(
        db, organization_id, promoter_code.code, email=f"seg-{uuid.uuid4().hex[:6]}@example.com"
    )
    friend_code = await friend_referrals_service.get_or_create_code(
        db, organization_id=organization_id, user_id=inviter_user.id
    )

    invited_user = await _register_through(
        db, organization_id, friend_code.code, email=f"inv-{uuid.uuid4().hex[:6]}@example.com"
    )
    invited_customer = await _customer_of(db, organization_id, invited_user.id)

    # Commercial attribution: the inviter's promoter, NOT the inviter.
    assert await _agent_behind_attribution(db, organization_id, invited_customer.id) == agent.id

    # And the inviter sees them in their own list.
    referrals = await friend_referrals_service.list_my_referrals(
        db, organization_id=organization_id, referrer_user_id=inviter_user.id
    )
    assert [r["state"] for r in referrals] == ["INVITED"]
    assert referrals[0]["source"] == "FRIEND_LINK"


@pytest.mark.asyncio
async def test_a_promoters_own_link_still_behaves_exactly_as_before_and_also_fills_their_list(
    db, organization_id
):
    """A promoter's invitee joins that promoter's tree; the referral list is
    purely additive."""
    await _make_customer_role(db, organization_id)
    agent, agent_user, promoter_code = await _make_promoter(db, organization_id, name="Bruno")

    invited_user = await _register_through(
        db, organization_id, promoter_code.code, email=f"inv-{uuid.uuid4().hex[:6]}@example.com"
    )
    invited_customer = await _customer_of(db, organization_id, invited_user.id)

    assert await _agent_behind_attribution(db, organization_id, invited_customer.id) == agent.id
    referrals = await friend_referrals_service.list_my_referrals(
        db, organization_id=organization_id, referrer_user_id=agent_user.id
    )
    assert len(referrals) == 1
    assert referrals[0]["source"] == "PROMOTER_LINK"


@pytest.mark.asyncio
async def test_a_promoter_using_their_friend_link_keeps_customers_in_their_own_tree(db, organization_id):
    """A promoter's customers land in their tree whichever of their links was
    used."""
    await _make_customer_role(db, organization_id)
    agent, agent_user, _code = await _make_promoter(db, organization_id, name="Carla")

    friend_code = await friend_referrals_service.get_or_create_code(
        db, organization_id=organization_id, user_id=agent_user.id
    )
    invited_user = await _register_through(
        db, organization_id, friend_code.code, email=f"inv-{uuid.uuid4().hex[:6]}@example.com"
    )
    invited_customer = await _customer_of(db, organization_id, invited_user.id)

    assert await _agent_behind_attribution(db, organization_id, invited_customer.id) == agent.id


@pytest.mark.asyncio
async def test_an_unknown_code_is_still_refused(db, organization_id):
    """Registration remains invite-only; an unknown code is rejected."""
    await _make_customer_role(db, organization_id)
    with pytest.raises(auth_service.RegistrationError, match="invite-only"):
        await _register_through(db, organization_id, "SEG-DEADBEEF", email="nope@example.com")


# --- Counting and gifts -------------------------------------------------------


@pytest.mark.asyncio
async def test_a_referral_counts_only_once_their_contract_is_really_active(db, organization_id):
    await _make_customer_role(db, organization_id)
    agent, _agent_user, promoter_code = await _make_promoter(db, organization_id, name="Dario")
    inviter_user = await _register_through(
        db, organization_id, promoter_code.code, email=f"seg-{uuid.uuid4().hex[:6]}@example.com"
    )
    friend_code = await friend_referrals_service.get_or_create_code(
        db, organization_id=organization_id, user_id=inviter_user.id
    )
    invited_user = await _register_through(
        db, organization_id, friend_code.code, email=f"inv-{uuid.uuid4().hex[:6]}@example.com"
    )
    invited_customer = await _customer_of(db, organization_id, invited_user.id)

    summary = await friend_referrals_service.get_my_summary(
        db, organization_id=organization_id, user_id=inviter_user.id
    )
    assert summary["invited_total"] == 1
    assert summary["active_total"] == 0

    await _activate_a_contract_for(db, organization_id, invited_customer, agent.id)

    summary = await friend_referrals_service.get_my_summary(
        db, organization_id=organization_id, user_id=inviter_user.id
    )
    assert summary["active_total"] == 1
    assert summary["referrals"][0]["state"] == "ACTIVE"
    assert summary["missing_for_next_reward"] == 9
    assert summary["claimable_milestone"] is None


def test_the_milestone_maths():
    claimable = friend_referrals_service._claimable_milestone
    assert claimable(0, set()) is None
    assert claimable(9, set()) is None
    assert claimable(10, set()) == 10
    assert claimable(19, set()) == 10
    assert claimable(20, set()) == 10, "chi non ha riscattato a 10 non viene saltato"
    assert claimable(20, {10}) == 20
    assert claimable(20, {10, 20}) is None
    # Repeatable forever, every 10.
    assert claimable(34, {10, 20}) == 30


@pytest.mark.asyncio
async def test_the_bonus_can_be_requested_at_ten_and_only_once(db, organization_id):
    await _make_customer_role(db, organization_id)
    agent, _agent_user, promoter_code = await _make_promoter(db, organization_id, name="Elena")
    inviter_user = await _register_through(
        db, organization_id, promoter_code.code, email=f"seg-{uuid.uuid4().hex[:6]}@example.com"
    )
    friend_code = await friend_referrals_service.get_or_create_code(
        db, organization_id=organization_id, user_id=inviter_user.id
    )

    for i in range(10):
        invited_user = await _register_through(
            db, organization_id, friend_code.code, email=f"inv{i}-{uuid.uuid4().hex[:6]}@example.com"
        )
        invited_customer = await _customer_of(db, organization_id, invited_user.id)
        await _activate_a_contract_for(db, organization_id, invited_customer, agent.id)

    summary = await friend_referrals_service.get_my_summary(
        db, organization_id=organization_id, user_id=inviter_user.id
    )
    assert summary["active_total"] == 10
    assert summary["claimable_milestone"] == 10

    first = await friend_referrals_service.request_reward(
        db, organization_id=organization_id, user_id=inviter_user.id
    )
    assert first.milestone == 10
    assert first.status == "REQUESTED"

    # Requesting only opens a claim; the credit comes when staff confirm it.
    summary = await friend_referrals_service.get_my_summary(
        db, organization_id=organization_id, user_id=inviter_user.id
    )
    assert summary["claimable_milestone"] is None

    with pytest.raises(friend_referrals_service.FriendReferralError):
        await friend_referrals_service.request_reward(
            db, organization_id=organization_id, user_id=inviter_user.id
        )

    # Confirming it credits 10 EUR of SosnetCash, once, even if confirmed again.
    from app.modules.wallets import service as wallets_service

    for _ in range(2):
        await friend_referrals_service.handle_claim(
            db, organization_id=organization_id, claim_id=first.id, status="FULFILLED",
            note="Bonus accreditato", actor_user_id=inviter_user.id,
        )
    wallet = await wallets_service.get_wallet_by_user_id(
        db, organization_id=organization_id, user_id=inviter_user.id
    )
    assert wallet.balance_cents == friend_referrals_service.REWARD_CENTS == 1000


@pytest.mark.asyncio
async def test_asking_before_reaching_ten_is_refused(db, organization_id):
    await _make_customer_role(db, organization_id)
    _agent, _agent_user, promoter_code = await _make_promoter(db, organization_id, name="Fabio")
    inviter_user = await _register_through(
        db, organization_id, promoter_code.code, email=f"seg-{uuid.uuid4().hex[:6]}@example.com"
    )
    with pytest.raises(friend_referrals_service.FriendReferralError, match="10"):
        await friend_referrals_service.request_reward(
            db, organization_id=organization_id, user_id=inviter_user.id
        )


@pytest.mark.asyncio
async def test_the_list_never_exposes_a_referred_customers_contact_details(db, organization_id):
    """The referral list does not expose referrals' contact details."""
    await _make_customer_role(db, organization_id)
    _agent, _agent_user, promoter_code = await _make_promoter(db, organization_id, name="Gianna")
    inviter_user = await _register_through(
        db, organization_id, promoter_code.code, email=f"seg-{uuid.uuid4().hex[:6]}@example.com"
    )
    friend_code = await friend_referrals_service.get_or_create_code(
        db, organization_id=organization_id, user_id=inviter_user.id
    )
    await _register_through(
        db, organization_id, friend_code.code, email="segretissima@example.com"
    )

    referrals = await friend_referrals_service.list_my_referrals(
        db, organization_id=organization_id, referrer_user_id=inviter_user.id
    )
    assert set(referrals[0]) == {"id", "display_name", "state", "source", "invited_at"}


@pytest.mark.asyncio
async def test_one_customer_can_only_be_referred_once(db, organization_id):
    """Recording a referral is idempotent."""
    await _make_customer_role(db, organization_id)
    _agent, agent_user, promoter_code = await _make_promoter(db, organization_id, name="Hugo")
    invited_user = await _register_through(
        db, organization_id, promoter_code.code, email=f"inv-{uuid.uuid4().hex[:6]}@example.com"
    )
    invited_customer = await _customer_of(db, organization_id, invited_user.id)

    await friend_referrals_service.record_referral(
        db, organization_id=organization_id, referrer_user_id=agent_user.id,
        referred_customer_id=invited_customer.id, code_used=promoter_code.code, source="PROMOTER_LINK",
    )
    rows = list((await db.execute(
        select(FriendReferral).where(FriendReferral.referred_customer_id == invited_customer.id)
    )).scalars())
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_the_code_is_stable_across_calls(db, organization_id):
    user = User(
        organization_id=organization_id, email=f"u-{uuid.uuid4().hex[:6]}@example.com",
        password_hash=hash_password("irrelevant"),
    )
    db.add(user)
    await db.commit()

    first = await friend_referrals_service.get_or_create_code(
        db, organization_id=organization_id, user_id=user.id
    )
    second = await friend_referrals_service.get_or_create_code(
        db, organization_id=organization_id, user_id=user.id
    )
    assert first.id == second.id
    assert first.code == second.code


@pytest.mark.asyncio
async def test_the_invite_list_creates_no_commercial_attribution_of_its_own(db, organization_id):
    """Referrals never create extra attributions: each customer has exactly
    one CustomerAttribution, whichever link was used."""
    await _make_customer_role(db, organization_id)
    _agent, _agent_user, promoter_code = await _make_promoter(db, organization_id, name="Ivo")
    inviter_user = await _register_through(
        db, organization_id, promoter_code.code, email=f"seg-{uuid.uuid4().hex[:6]}@example.com"
    )
    friend_code = await friend_referrals_service.get_or_create_code(
        db, organization_id=organization_id, user_id=inviter_user.id
    )
    invited_user = await _register_through(
        db, organization_id, friend_code.code, email=f"inv-{uuid.uuid4().hex[:6]}@example.com"
    )
    invited_customer = await _customer_of(db, organization_id, invited_user.id)

    attributions = list((await db.execute(
        select(CustomerAttribution).where(CustomerAttribution.customer_id == invited_customer.id)
    )).scalars())
    assert len(attributions) == 1
