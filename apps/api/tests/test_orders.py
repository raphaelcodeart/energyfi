"""Partner and dropshipping product orders, optionally discounted with wallet
credit. Orders are not contracts. Covers the credit cap, direct PAID status
when credit covers the full price, exact refunds on cancellation, and
rejection of INTERNAL products."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.foundation.security import hash_otp_code, hash_password
from app.modules.auth import service as auth_service
from app.modules.auth.models import OtpCode
from app.modules.catalog import service as catalog_service
from app.modules.catalog.schemas import ProductCreate
from app.modules.orders import service as orders_service
from app.modules.organizations import service as organizations_service
from app.modules.organizations.schemas import OrganizationSettingsUpdate, PaymentSettingsUpdate
from app.modules.rbac.models import Role, UserRole
from app.modules.users.models import User
from app.modules.wallets import service as wallet_service

VALID_OTP_CODE = "654321"


async def _seed_credit_spend_otp(db, user_id):
    """Seed a valid credit-spend OTP directly, bypassing the email step."""
    db.add(
        OtpCode(
            user_id=user_id,
            purpose=auth_service.WALLET_CREDIT_SPEND_OTP_PURPOSE,
            code_hash=hash_otp_code(VALID_OTP_CODE),
            expires_at=datetime.now(UTC) + timedelta(minutes=10),
        )
    )
    await db.commit()


async def _configure_bank_transfer(db, organization_id):
    """Configure an IBAN so BANK_TRANSFER (the default method) is available."""
    await organizations_service.update_settings(
        db, organization_id=organization_id, payload=OrganizationSettingsUpdate(bank_iban="IT66W0883330410000000015702")
    )


async def _configure_stripe(db, organization_id):
    """Configure both Stripe keys so CARD is available."""
    await organizations_service.update_payment_settings(
        db, organization_id=organization_id,
        payload=PaymentSettingsUpdate(stripe_publishable_key="pk_test_abc", stripe_secret_key="sk_test_xyz"),
    )


async def _get_or_create_role(db, organization_id, *, role_code: str) -> Role:
    from sqlalchemy import select

    existing = (
        await db.execute(select(Role).where(Role.organization_id == organization_id, Role.code == role_code))
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    role = Role(organization_id=organization_id, code=role_code, name=role_code.title())
    db.add(role)
    await db.flush()
    return role


async def _make_user_with_role(db, organization_id, *, role_code: str = "CUSTOMER"):
    user = User(
        organization_id=organization_id, email=f"{role_code.lower()}-{uuid.uuid4().hex[:6]}@example.demo",
        password_hash=hash_password("irrelevant"),
    )
    db.add(user)
    await db.flush()
    role = await _get_or_create_role(db, organization_id, role_code=role_code)
    db.add(UserRole(user_id=user.id, organization_id=organization_id, role_id=role.id))
    await db.commit()
    await db.refresh(user)
    return user


async def _make_product_version(
    db, organization_id, actor_user_id, *, category="DROPSHIPPING", price_cents=5000, discount_pct=20,
    cashback_enabled=False,
):
    product = await catalog_service.create_product(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        payload=ProductCreate(
            code=f"ORD-{uuid.uuid4().hex[:6]}", customer_type="PRIVATE", category=category,
            name="Gadget", base_price_cents=price_cents, credit_discount_percentage=discount_pct,
            cashback_enabled=cashback_enabled,
        ),
    )
    _, versions = await catalog_service.get_product_with_versions(db, organization_id=organization_id, product_id=product.id)
    return versions[0]


@pytest.mark.asyncio
async def test_partial_credit_debits_wallet_and_leaves_residual_awaiting_payment(db, organization_id):
    await _configure_bank_transfer(db, organization_id)
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    version = await _make_product_version(db, organization_id, admin.id, price_cents=5000, discount_pct=20)

    wallet = await wallet_service.get_or_create_wallet(db, organization_id=organization_id, user_id=customer.id)
    await wallet_service.credit_wallet(
        db, organization_id=organization_id, wallet_id=wallet.id, amount_cents=2000, type_="ADMIN_CREDIT",
        actor_user_id=admin.id, idempotency_key=str(uuid.uuid4()),
    )

    quote = await orders_service.get_quote(
        db, organization_id=organization_id, customer_user_id=customer.id, product_version_id=version.id
    )
    assert quote["max_creditable_cents"] == 1000  # 20% of 5000
    assert quote["customer_wallet_balance_cents"] == 2000

    order = await orders_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, product_version_id=version.id,
        credit_applied_cents=1000, actor_user_id=admin.id,
        require_otp_for_credit_spend=False,
    )
    assert order.status == "AWAITING_PAYMENT"
    assert order.amount_cents == 5000
    assert order.credit_applied_cents == 1000
    assert order.credit_debit_transaction_id is not None

    wallet_after = await wallet_service.get_wallet_by_user_id(db, organization_id=organization_id, user_id=customer.id)
    assert wallet_after.balance_cents == 1000

    confirmed = await orders_service.confirm_payment(
        db, organization_id=organization_id, order_id=order.id, actor_user_id=admin.id
    )
    assert confirmed.status == "PAID"


@pytest.mark.asyncio
async def test_credit_covering_full_amount_skips_straight_to_paid(db, organization_id):
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    version = await _make_product_version(db, organization_id, admin.id, price_cents=3000, discount_pct=100)

    wallet = await wallet_service.get_or_create_wallet(db, organization_id=organization_id, user_id=customer.id)
    await wallet_service.credit_wallet(
        db, organization_id=organization_id, wallet_id=wallet.id, amount_cents=3000, type_="ADMIN_CREDIT",
        actor_user_id=admin.id, idempotency_key=str(uuid.uuid4()),
    )

    order = await orders_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, product_version_id=version.id,
        credit_applied_cents=3000, actor_user_id=admin.id,
        require_otp_for_credit_spend=False,
    )
    assert order.status == "PAID"  # no bank transfer needed
    assert order.paid_at is not None

    wallet_after = await wallet_service.get_wallet_by_user_id(db, organization_id=organization_id, user_id=customer.id)
    assert wallet_after.balance_cents == 0


@pytest.mark.asyncio
async def test_credit_over_cap_is_rejected(db, organization_id):
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    version = await _make_product_version(db, organization_id, admin.id, price_cents=5000, discount_pct=20)

    with pytest.raises(orders_service.InvalidCreditAmountError):
        await orders_service.create_order(
            db, organization_id=organization_id, customer_user_id=customer.id, product_version_id=version.id,
            credit_applied_cents=1001, actor_user_id=admin.id,  # cap is 1000
            require_otp_for_credit_spend=False,
        )


@pytest.mark.asyncio
async def test_credit_exceeding_balance_raises_and_creates_no_order(db, organization_id):
    await _configure_bank_transfer(db, organization_id)
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    version = await _make_product_version(db, organization_id, admin.id, price_cents=5000, discount_pct=50)
    # No wallet balance: the 2500 cap exceeds what the customer holds.

    with pytest.raises(wallet_service.InsufficientBalanceError):
        await orders_service.create_order(
            db, organization_id=organization_id, customer_user_id=customer.id, product_version_id=version.id,
            credit_applied_cents=2500, actor_user_id=admin.id,
            require_otp_for_credit_spend=False,
        )

    orders = await orders_service.list_orders(db, organization_id=organization_id)
    assert all(o.customer_user_id != customer.id for o in orders)


@pytest.mark.asyncio
async def test_cancel_refunds_the_exact_credit_debit(db, organization_id):
    await _configure_bank_transfer(db, organization_id)
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    version = await _make_product_version(db, organization_id, admin.id, price_cents=10000, discount_pct=10)

    wallet = await wallet_service.get_or_create_wallet(db, organization_id=organization_id, user_id=customer.id)
    await wallet_service.credit_wallet(
        db, organization_id=organization_id, wallet_id=wallet.id, amount_cents=1000, type_="ADMIN_CREDIT",
        actor_user_id=admin.id, idempotency_key=str(uuid.uuid4()),
    )

    order = await orders_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, product_version_id=version.id,
        credit_applied_cents=1000, actor_user_id=admin.id,
        require_otp_for_credit_spend=False,
    )
    mid_wallet = await wallet_service.get_wallet_by_user_id(db, organization_id=organization_id, user_id=customer.id)
    assert mid_wallet.balance_cents == 0

    cancelled = await orders_service.cancel_order(
        db, organization_id=organization_id, order_id=order.id, reason="Prodotto esaurito", actor_user_id=admin.id
    )
    assert cancelled.status == "CANCELLED"

    refunded_wallet = await wallet_service.get_wallet_by_user_id(db, organization_id=organization_id, user_id=customer.id)
    assert refunded_wallet.balance_cents == 1000

    with pytest.raises(orders_service.InvalidOrderStateError):
        await orders_service.cancel_order(
            db, organization_id=organization_id, order_id=order.id, reason="again", actor_user_id=admin.id
        )
    with pytest.raises(orders_service.InvalidOrderStateError):
        await orders_service.confirm_payment(db, organization_id=organization_id, order_id=order.id, actor_user_id=admin.id)


@pytest.mark.asyncio
async def test_internal_category_product_is_not_orderable(db, organization_id):
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    version = await _make_product_version(db, organization_id, admin.id, category="INTERNAL", price_cents=3000, discount_pct=0)

    with pytest.raises(orders_service.ProductNotEligibleError):
        await orders_service.create_order(
            db, organization_id=organization_id, customer_user_id=customer.id, product_version_id=version.id,
            credit_applied_cents=0, actor_user_id=admin.id,
            require_otp_for_credit_spend=False,
        )


@pytest.mark.asyncio
async def test_unconfigured_payment_method_is_rejected_and_creates_no_order(db, organization_id):
    """Payment methods stay unavailable until an admin configures them, and
    the server rejects them regardless of what the UI shows."""
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    version = await _make_product_version(db, organization_id, admin.id, price_cents=5000, discount_pct=0)

    with pytest.raises(orders_service.PaymentMethodNotAvailableError):
        await orders_service.create_order(
            db, organization_id=organization_id, customer_user_id=customer.id, product_version_id=version.id,
            credit_applied_cents=0, actor_user_id=admin.id, payment_method="BANK_TRANSFER",
        )
    with pytest.raises(orders_service.PaymentMethodNotAvailableError):
        await orders_service.create_order(
            db, organization_id=organization_id, customer_user_id=customer.id, product_version_id=version.id,
            credit_applied_cents=0, actor_user_id=admin.id, payment_method="CARD",
        )

    orders = await orders_service.list_orders(db, organization_id=organization_id)
    assert all(o.customer_user_id != customer.id for o in orders)


@pytest.mark.asyncio
async def test_card_requires_both_stripe_keys_configured(db, organization_id):
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    version = await _make_product_version(db, organization_id, admin.id, price_cents=5000, discount_pct=0)

    # A publishable key alone is not enough.
    await organizations_service.update_payment_settings(
        db, organization_id=organization_id, payload=PaymentSettingsUpdate(stripe_publishable_key="pk_test_abc")
    )
    with pytest.raises(orders_service.PaymentMethodNotAvailableError):
        await orders_service.create_order(
            db, organization_id=organization_id, customer_user_id=customer.id, product_version_id=version.id,
            credit_applied_cents=0, actor_user_id=admin.id, payment_method="CARD",
        )

    await organizations_service.update_payment_settings(
        db, organization_id=organization_id, payload=PaymentSettingsUpdate(stripe_secret_key="sk_test_xyz")
    )
    order = await orders_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, product_version_id=version.id,
        credit_applied_cents=0, actor_user_id=admin.id, payment_method="CARD",
    )
    assert order.status == "AWAITING_PAYMENT"
    assert order.payment_method == "CARD"


@pytest.mark.asyncio
async def test_confirm_payment_refuses_a_card_order(db, organization_id):
    """The manual bank-transfer confirmation can never mark a CARD order paid;
    only the Stripe webhook can. Enforced server-side, not just in the UI."""
    await _configure_stripe(db, organization_id)
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    version = await _make_product_version(db, organization_id, admin.id, price_cents=5000, discount_pct=0)

    order = await orders_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, product_version_id=version.id,
        credit_applied_cents=0, actor_user_id=admin.id, payment_method="CARD",
    )

    with pytest.raises(orders_service.InvalidOrderStateError):
        await orders_service.confirm_payment(
            db, organization_id=organization_id, order_id=order.id, actor_user_id=admin.id
        )

    refreshed = await orders_service.get_org_scoped(db, organization_id=organization_id, order_id=order.id)
    assert refreshed.status == "AWAITING_PAYMENT"


@pytest.mark.asyncio
async def test_full_credit_ignores_unconfigured_payment_method(db, organization_id):
    """With a zero residual nothing is charged, so an unavailable payment
    method is stored but never blocks the order."""
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    version = await _make_product_version(db, organization_id, admin.id, price_cents=3000, discount_pct=100)

    wallet = await wallet_service.get_or_create_wallet(db, organization_id=organization_id, user_id=customer.id)
    await wallet_service.credit_wallet(
        db, organization_id=organization_id, wallet_id=wallet.id, amount_cents=3000, type_="ADMIN_CREDIT",
        actor_user_id=admin.id, idempotency_key=str(uuid.uuid4()),
    )

    order = await orders_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, product_version_id=version.id,
        credit_applied_cents=3000, actor_user_id=admin.id, payment_method="CARD",
        require_otp_for_credit_spend=False,
    )
    assert order.status == "PAID"


@pytest.mark.asyncio
async def test_create_order_notifies_staff_but_not_the_actor(db, organization_id):
    """Staff with a notify role are told about new orders, except the user
    who created it on the customer's behalf."""
    from app.modules.notifications import service as notifications_service

    await _configure_bank_transfer(db, organization_id)
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    other_admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    version = await _make_product_version(db, organization_id, admin.id, price_cents=5000, discount_pct=0)

    await orders_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, product_version_id=version.id,
        credit_applied_cents=0, actor_user_id=admin.id,
        require_otp_for_credit_spend=False,
    )

    actor_notifications = await notifications_service.list_my_notifications(
        db, organization_id=organization_id, user_id=admin.id
    )
    assert not any(n.type == "ORDER_CREATED" for n in actor_notifications)

    other_notifications = await notifications_service.list_my_notifications(
        db, organization_id=organization_id, user_id=other_admin.id
    )
    assert any(n.type == "ORDER_CREATED" for n in other_notifications)


@pytest.mark.asyncio
async def test_confirm_payment_notifies_staff_and_sends_paid_email(db, organization_id):
    """Confirming a bank transfer notifies staff and emails the customer that
    payment is complete."""
    from unittest.mock import AsyncMock, patch

    from app.modules.notifications import service as notifications_service

    await _configure_bank_transfer(db, organization_id)
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    other_admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    version = await _make_product_version(db, organization_id, admin.id, price_cents=5000, discount_pct=0)

    order = await orders_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, product_version_id=version.id,
        credit_applied_cents=0, actor_user_id=customer.id,
        require_otp_for_credit_spend=False,
    )

    with patch.object(orders_service, "_send_order_paid_email", new_callable=AsyncMock) as mock_email:
        confirmed = await orders_service.confirm_payment(
            db, organization_id=organization_id, order_id=order.id, actor_user_id=admin.id
        )

    assert confirmed.status == "PAID"
    mock_email.assert_awaited_once()
    assert mock_email.call_args.kwargs["order"].id == order.id

    other_notifications = await notifications_service.list_my_notifications(
        db, organization_id=organization_id, user_id=other_admin.id
    )
    assert any(n.type == "ORDER_PAID" for n in other_notifications)


@pytest.mark.asyncio
async def test_mark_paid_via_stripe_notifies_staff_and_sends_paid_email(db, organization_id):
    """Stripe webhook confirmation yields the same staff notification and
    customer email as a bank-transfer confirmation, with no admin involved."""
    from unittest.mock import AsyncMock, patch

    from app.modules.notifications import service as notifications_service

    await _configure_stripe(db, organization_id)
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    version = await _make_product_version(db, organization_id, admin.id, price_cents=6900, discount_pct=0)

    order = await orders_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, product_version_id=version.id,
        credit_applied_cents=0, actor_user_id=customer.id, payment_method="CARD",
    )
    order = await orders_service.attach_stripe_checkout_session(db, order=order, session_id=f"cs_test_{uuid.uuid4().hex}")

    with patch.object(orders_service, "_send_order_paid_email", new_callable=AsyncMock) as mock_email:
        paid = await orders_service.mark_paid_via_stripe(
            db, organization_id=organization_id, stripe_checkout_session_id=order.stripe_checkout_session_id
        )

    assert paid.status == "PAID"
    assert paid.paid_by_user_id is None  # confirmed by Stripe, not a person
    mock_email.assert_awaited_once()

    admin_notifications = await notifications_service.list_my_notifications(
        db, organization_id=organization_id, user_id=admin.id
    )
    assert any(n.type == "ORDER_PAID" for n in admin_notifications)

    # A retried webhook for an already-paid session is a silent no-op.
    with patch.object(orders_service, "_send_order_paid_email", new_callable=AsyncMock) as mock_email_retry:
        await orders_service.mark_paid_via_stripe(
            db, organization_id=organization_id, stripe_checkout_session_id=order.stripe_checkout_session_id
        )
    mock_email_retry.assert_not_awaited()


@pytest.mark.asyncio
async def test_product_order_payment_never_touches_the_wallet(db, organization_id):
    """Only invoice-redemption cashback credits the wallet. A plain purchase
    with no credit applied leaves the wallet untouched, whether paid by bank
    transfer or by card."""
    await _configure_stripe(db, organization_id)
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    version = await _make_product_version(db, organization_id, admin.id, price_cents=10000, discount_pct=0)

    wallet_before = await wallet_service.get_or_create_wallet(db, organization_id=organization_id, user_id=customer.id)
    assert wallet_before.balance_cents == 0

    order = await orders_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, product_version_id=version.id,
        credit_applied_cents=0, actor_user_id=customer.id, payment_method="CARD",
    )
    order = await orders_service.attach_stripe_checkout_session(db, order=order, session_id=f"cs_test_{uuid.uuid4().hex}")
    paid = await orders_service.mark_paid_via_stripe(
        db, organization_id=organization_id, stripe_checkout_session_id=order.stripe_checkout_session_id
    )
    assert paid.status == "PAID"

    wallet_after = await wallet_service.get_wallet_by_user_id(db, organization_id=organization_id, user_id=customer.id)
    assert wallet_after.balance_cents == 0


@pytest.mark.asyncio
async def test_change_payment_method_switches_and_clears_stale_stripe_session(db, organization_id):
    """Switching from CARD to BANK_TRANSFER clears the Stripe session id, so a
    late webhook for the abandoned session cannot mark the order paid."""
    await _configure_stripe(db, organization_id)
    await _configure_bank_transfer(db, organization_id)
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    version = await _make_product_version(db, organization_id, admin.id, price_cents=5000, discount_pct=0)

    order = await orders_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, product_version_id=version.id,
        credit_applied_cents=0, actor_user_id=customer.id, payment_method="CARD",
    )
    order = await orders_service.attach_stripe_checkout_session(db, order=order, session_id=f"cs_test_{uuid.uuid4().hex}")
    assert order.stripe_checkout_session_id is not None

    switched = await orders_service.change_payment_method(
        db, organization_id=organization_id, order=order, new_payment_method="BANK_TRANSFER"
    )
    assert switched.payment_method == "BANK_TRANSFER"
    assert switched.stripe_checkout_session_id is None

    # Switching back to CARD has nothing to clear; a new session is attached later.
    back_to_card = await orders_service.change_payment_method(
        db, organization_id=organization_id, order=switched, new_payment_method="CARD"
    )
    assert back_to_card.payment_method == "CARD"


@pytest.mark.asyncio
async def test_change_payment_method_rejects_once_paid(db, organization_id):
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    version = await _make_product_version(db, organization_id, admin.id, price_cents=3000, discount_pct=100)

    wallet = await wallet_service.get_or_create_wallet(db, organization_id=organization_id, user_id=customer.id)
    await wallet_service.credit_wallet(
        db, organization_id=organization_id, wallet_id=wallet.id, amount_cents=3000, type_="ADMIN_CREDIT",
        actor_user_id=admin.id, idempotency_key=str(uuid.uuid4()),
    )
    order = await orders_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, product_version_id=version.id,
        credit_applied_cents=3000, actor_user_id=customer.id,
        require_otp_for_credit_spend=False,
    )
    assert order.status == "PAID"

    with pytest.raises(orders_service.InvalidOrderStateError):
        await orders_service.change_payment_method(
            db, organization_id=organization_id, order=order, new_payment_method="CARD"
        )


@pytest.mark.asyncio
async def test_change_payment_method_rejects_unavailable_method(db, organization_id):
    await _configure_bank_transfer(db, organization_id)
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    version = await _make_product_version(db, organization_id, admin.id, price_cents=5000, discount_pct=0)

    order = await orders_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, product_version_id=version.id,
        credit_applied_cents=0, actor_user_id=customer.id, payment_method="BANK_TRANSFER",
    )
    # Stripe is not configured, so switching to CARD fails.
    with pytest.raises(orders_service.PaymentMethodNotAvailableError):
        await orders_service.change_payment_method(
            db, organization_id=organization_id, order=order, new_payment_method="CARD"
        )


@pytest.mark.asyncio
async def test_upload_payment_proof_stores_it_and_notifies_staff(db, organization_id):
    from app.modules.notifications import service as notifications_service

    await _configure_bank_transfer(db, organization_id)
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    other_admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    version = await _make_product_version(db, organization_id, admin.id, price_cents=5000, discount_pct=0)

    order = await orders_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, product_version_id=version.id,
        credit_applied_cents=0, actor_user_id=customer.id, payment_method="BANK_TRANSFER",
    )
    assert order.payment_proof_uploaded_at is None

    updated = await orders_service.upload_payment_proof(
        db, organization_id=organization_id, order=order, file_bytes=b"%PDF-1.4\nfake receipt",
        content_type="application/pdf", original_filename="bonifico.pdf", actor_user_id=customer.id,
    )
    assert updated.payment_proof_uploaded_at is not None
    assert updated.payment_proof_original_filename == "bonifico.pdf"

    url = orders_service.presigned_payment_proof_url(updated)
    assert url

    other_notifications = await notifications_service.list_my_notifications(
        db, organization_id=organization_id, user_id=other_admin.id
    )
    assert any(n.type == "ORDER_PAYMENT_PROOF_UPLOADED" for n in other_notifications)


@pytest.mark.asyncio
async def test_upload_payment_proof_rejects_a_card_order(db, organization_id):
    await _configure_stripe(db, organization_id)
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    version = await _make_product_version(db, organization_id, admin.id, price_cents=5000, discount_pct=0)

    order = await orders_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, product_version_id=version.id,
        credit_applied_cents=0, actor_user_id=customer.id, payment_method="CARD",
    )
    with pytest.raises(orders_service.PaymentProofError):
        await orders_service.upload_payment_proof(
            db, organization_id=organization_id, order=order, file_bytes=b"%PDF-1.4\nfake",
            content_type="application/pdf", original_filename="x.pdf", actor_user_id=customer.id,
        )


# ---- Self-checkout OTP required to spend wallet credit ----

@pytest.mark.asyncio
async def test_self_checkout_credit_spend_without_otp_is_rejected(db, organization_id):
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    version = await _make_product_version(db, organization_id, admin.id, price_cents=5000, discount_pct=20)
    wallet = await wallet_service.get_or_create_wallet(db, organization_id=organization_id, user_id=customer.id)
    await wallet_service.credit_wallet(
        db, organization_id=organization_id, wallet_id=wallet.id, amount_cents=2000, type_="ADMIN_CREDIT",
        actor_user_id=admin.id, idempotency_key=str(uuid.uuid4()),
    )

    with pytest.raises(orders_service.InvalidOtpError):
        await orders_service.create_order(
            db, organization_id=organization_id, customer_user_id=customer.id, product_version_id=version.id,
            credit_applied_cents=1000, actor_user_id=customer.id,  # OTP required by default
        )


@pytest.mark.asyncio
async def test_self_checkout_credit_spend_with_wrong_otp_is_rejected(db, organization_id):
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    version = await _make_product_version(db, organization_id, admin.id, price_cents=5000, discount_pct=20)
    wallet = await wallet_service.get_or_create_wallet(db, organization_id=organization_id, user_id=customer.id)
    await wallet_service.credit_wallet(
        db, organization_id=organization_id, wallet_id=wallet.id, amount_cents=2000, type_="ADMIN_CREDIT",
        actor_user_id=admin.id, idempotency_key=str(uuid.uuid4()),
    )
    await _seed_credit_spend_otp(db, customer.id)

    with pytest.raises(orders_service.InvalidOtpError):
        await orders_service.create_order(
            db, organization_id=organization_id, customer_user_id=customer.id, product_version_id=version.id,
            credit_applied_cents=1000, actor_user_id=customer.id, otp_code="000000",
        )


@pytest.mark.asyncio
async def test_self_checkout_credit_spend_with_valid_otp_succeeds(db, organization_id):
    await _configure_bank_transfer(db, organization_id)
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    version = await _make_product_version(db, organization_id, admin.id, price_cents=5000, discount_pct=20)
    wallet = await wallet_service.get_or_create_wallet(db, organization_id=organization_id, user_id=customer.id)
    await wallet_service.credit_wallet(
        db, organization_id=organization_id, wallet_id=wallet.id, amount_cents=2000, type_="ADMIN_CREDIT",
        actor_user_id=admin.id, idempotency_key=str(uuid.uuid4()),
    )
    await _seed_credit_spend_otp(db, customer.id)

    order = await orders_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, product_version_id=version.id,
        credit_applied_cents=1000, actor_user_id=customer.id, otp_code=VALID_OTP_CODE,
    )
    assert order.credit_applied_cents == 1000

    # The OTP is single-use.
    with pytest.raises(orders_service.InvalidOtpError):
        await orders_service.create_order(
            db, organization_id=organization_id, customer_user_id=customer.id, product_version_id=version.id,
            credit_applied_cents=500, actor_user_id=customer.id, otp_code=VALID_OTP_CODE,
        )


@pytest.mark.asyncio
async def test_admin_created_order_never_needs_an_otp(db, organization_id):
    """Staff-created orders skip the OTP: it would go to the customer's inbox,
    and the action is already permission-gated and audited."""
    await _configure_bank_transfer(db, organization_id)
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    version = await _make_product_version(db, organization_id, admin.id, price_cents=5000, discount_pct=20)
    wallet = await wallet_service.get_or_create_wallet(db, organization_id=organization_id, user_id=customer.id)
    await wallet_service.credit_wallet(
        db, organization_id=organization_id, wallet_id=wallet.id, amount_cents=2000, type_="ADMIN_CREDIT",
        actor_user_id=admin.id, idempotency_key=str(uuid.uuid4()),
    )

    order = await orders_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, product_version_id=version.id,
        credit_applied_cents=1000, actor_user_id=admin.id, require_otp_for_credit_spend=False,
    )
    assert order.credit_applied_cents == 1000


# ---- Instant cashback ----

@pytest.mark.asyncio
async def test_cashback_requires_the_product_to_allow_it(db, organization_id):
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    version = await _make_product_version(db, organization_id, admin.id, price_cents=5000, discount_pct=0, cashback_enabled=False)

    with pytest.raises(orders_service.CashbackNotAvailableError):
        await orders_service.create_order(
            db, organization_id=organization_id, customer_user_id=customer.id, product_version_id=version.id,
            credit_applied_cents=0, actor_user_id=customer.id, cashback_requested=True,
            require_otp_for_credit_spend=False,
        )


@pytest.mark.asyncio
async def test_cashback_requires_a_real_residual_to_apply_to(db, organization_id):
    """Cashback refunds money paid new, so it cannot apply to an order fully
    covered by credit."""
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    version = await _make_product_version(
        db, organization_id, admin.id, price_cents=3000, discount_pct=100, cashback_enabled=True
    )
    wallet = await wallet_service.get_or_create_wallet(db, organization_id=organization_id, user_id=customer.id)
    await wallet_service.credit_wallet(
        db, organization_id=organization_id, wallet_id=wallet.id, amount_cents=3000, type_="ADMIN_CREDIT",
        actor_user_id=admin.id, idempotency_key=str(uuid.uuid4()),
    )
    await _seed_credit_spend_otp(db, customer.id)

    with pytest.raises(orders_service.CashbackNotAvailableError):
        await orders_service.create_order(
            db, organization_id=organization_id, customer_user_id=customer.id, product_version_id=version.id,
            credit_applied_cents=3000, actor_user_id=customer.id, cashback_requested=True, otp_code=VALID_OTP_CODE,
        )


@pytest.mark.asyncio
async def test_cashback_surcharge_and_credit_on_bank_transfer_confirm(db, organization_id):
    """A 100.00 EUR order with cashback costs 105.00 EUR (5% surcharge) and,
    once paid, credits exactly 105.00 EUR back as a base row plus a bonus
    row: never more than was actually paid."""
    await _configure_bank_transfer(db, organization_id)
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    version = await _make_product_version(
        db, organization_id, admin.id, price_cents=10000, discount_pct=0, cashback_enabled=True
    )

    order = await orders_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, product_version_id=version.id,
        credit_applied_cents=0, actor_user_id=customer.id, cashback_requested=True,
        require_otp_for_credit_spend=False,
    )
    assert order.cashback_requested is True
    assert order.cashback_surcharge_cents == 500  # 5% of 10000
    row = await orders_service.to_read_dict(db, order)
    assert row["residual_amount_cents"] == 10500

    confirmed = await orders_service.confirm_payment(
        db, organization_id=organization_id, order_id=order.id, actor_user_id=admin.id
    )
    assert confirmed.cashback_credited_at is not None

    wallet_after = await wallet_service.get_wallet_by_user_id(db, organization_id=organization_id, user_id=customer.id)
    assert wallet_after.balance_cents == 10500  # exactly what was paid


@pytest.mark.asyncio
async def test_cashback_credited_via_stripe_webhook_and_not_double_credited_on_retry(db, organization_id):
    await _configure_stripe(db, organization_id)
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    version = await _make_product_version(
        db, organization_id, admin.id, price_cents=6000, discount_pct=0, cashback_enabled=True
    )

    order = await orders_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, product_version_id=version.id,
        credit_applied_cents=0, actor_user_id=customer.id, payment_method="CARD", cashback_requested=True,
        require_otp_for_credit_spend=False,
    )
    order = await orders_service.attach_stripe_checkout_session(db, order=order, session_id=f"cs_test_{uuid.uuid4().hex}")

    paid = await orders_service.mark_paid_via_stripe(
        db, organization_id=organization_id, stripe_checkout_session_id=order.stripe_checkout_session_id
    )
    assert paid.cashback_credited_at is not None
    wallet_after = await wallet_service.get_wallet_by_user_id(db, organization_id=organization_id, user_id=customer.id)
    assert wallet_after.balance_cents == 6300  # 6000 + 5%

    # A retried webhook must not credit twice.
    await orders_service.mark_paid_via_stripe(
        db, organization_id=organization_id, stripe_checkout_session_id=order.stripe_checkout_session_id
    )
    wallet_again = await wallet_service.get_wallet_by_user_id(db, organization_id=organization_id, user_id=customer.id)
    assert wallet_again.balance_cents == 6300


@pytest.mark.asyncio
async def test_cashback_base_is_computed_after_credit_discount_not_before(db, organization_id):
    """With credit applied, the cashback surcharge and base are computed on
    the residual, not the list price, so spent credit cannot be recycled
    into new credit."""
    await _configure_bank_transfer(db, organization_id)
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    version = await _make_product_version(
        db, organization_id, admin.id, price_cents=10000, discount_pct=50, cashback_enabled=True
    )
    wallet = await wallet_service.get_or_create_wallet(db, organization_id=organization_id, user_id=customer.id)
    await wallet_service.credit_wallet(
        db, organization_id=organization_id, wallet_id=wallet.id, amount_cents=2000, type_="ADMIN_CREDIT",
        actor_user_id=admin.id, idempotency_key=str(uuid.uuid4()),
    )
    await _seed_credit_spend_otp(db, customer.id)

    order = await orders_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, product_version_id=version.id,
        credit_applied_cents=2000, actor_user_id=customer.id, cashback_requested=True, otp_code=VALID_OTP_CODE,
    )
    assert order.cashback_surcharge_cents == 400  # 5% of the 8000 residual
    row = await orders_service.to_read_dict(db, order)
    assert row["residual_amount_cents"] == 8400  # 8000 + 400

    await orders_service.confirm_payment(db, organization_id=organization_id, order_id=order.id, actor_user_id=admin.id)

    wallet_after = await wallet_service.get_wallet_by_user_id(db, organization_id=organization_id, user_id=customer.id)
    # 2000 spent entirely, then 8000 + 400 credited back.
    assert wallet_after.balance_cents == 8400


# ---- Product-level cashback_enabled flag ----

@pytest.mark.asyncio
async def test_cashback_enabled_is_forced_false_for_an_internal_product(db, organization_id):
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    product = await catalog_service.create_product(
        db, organization_id=organization_id, actor_user_id=admin.id,
        payload=ProductCreate(
            code=f"INT-{uuid.uuid4().hex[:6]}", customer_type="PRIVATE", category="INTERNAL",
            name="Luce Energia", base_price_cents=5000, cashback_enabled=True,
        ),
    )
    _, versions = await catalog_service.get_product_with_versions(db, organization_id=organization_id, product_id=product.id)
    assert versions[0].cashback_enabled is False


@pytest.mark.asyncio
async def test_switching_category_to_internal_clears_cashback_enabled(db, organization_id):
    from app.modules.catalog.schemas import ProductUpdate

    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    version = await _make_product_version(db, organization_id, admin.id, category="PARTNER", cashback_enabled=True)
    assert version.cashback_enabled is True

    await catalog_service.update_product(
        db, organization_id=organization_id, product_id=version.product_id,
        payload=ProductUpdate(category="INTERNAL"), actor_user_id=admin.id,
    )
    _, versions = await catalog_service.get_product_with_versions(
        db, organization_id=organization_id, product_id=version.product_id
    )
    assert versions[0].cashback_enabled is False
