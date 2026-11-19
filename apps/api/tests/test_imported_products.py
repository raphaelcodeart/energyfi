"""Imported products ("Acquisti SOSNET").

A catalog and order system kept apart from catalog.products, for goods
sourced from an external provider. Customers may pay partly with SosnetCash,
but these orders never generate cashback. Covers provider/product CRUD, the
credit-cap + OTP checkout, cancellation refunds via REVERSAL, and the wallet
ledger's reference_imported_order_id."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.foundation.security import hash_otp_code, hash_password
from app.modules.auth import service as auth_service
from app.modules.auth.models import OtpCode
from app.modules.imported_products import service as imported_products_service
from app.modules.organizations import service as organizations_service
from app.modules.organizations.schemas import OrganizationSettingsUpdate, PaymentSettingsUpdate
from app.modules.rbac.models import Role, UserRole
from app.modules.users.models import User
from app.modules.wallets import service as wallet_service

def _con_iva(merce_cents: int, aliquota: int = 22) -> int:
    """Customer total for the goods: VAT is added on top of the listed price."""
    from app.modules.marketplaces import rules

    return merce_cents + rules.vat_added_cents(net_cents=merce_cents, percentage=aliquota)


VALID_OTP_CODE = "111222"


async def _seed_credit_spend_otp(db, user_id):
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
    await organizations_service.update_settings(
        db, organization_id=organization_id, payload=OrganizationSettingsUpdate(bank_iban="IT66W0883330410000000015702")
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


async def _make_imported_product(db, organization_id, actor_user_id, *, price_cents=5000, discount_pct=20):
    provider = await imported_products_service.create_provider(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        provider_type="ALIEXPRESS", name="AliExpress IT", base_url=None, api_key="secret-key-1234", enabled=True,
    )
    product = await imported_products_service.create_imported_product(
        db, organization_id=organization_id, actor_user_id=actor_user_id, provider_id=provider.id,
        external_id=None, external_url=None, name="Power Bank importato", description="",
        image_url=None, price_cents=price_cents, credit_discount_percentage=discount_pct, status="ACTIVE",
    )
    return provider, product


@pytest.mark.asyncio
async def test_provider_api_key_is_masked_in_the_read_dict(db, organization_id):
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    provider = await imported_products_service.create_provider(
        db, organization_id=organization_id, actor_user_id=admin.id,
        provider_type="ALIEXPRESS", name="AliExpress IT", base_url="https://api.example.com",
        api_key="super-secret-abcd1234", enabled=True,
    )
    read = imported_products_service.to_provider_read_dict(provider)
    assert read["api_key_configured"] is True
    assert read["api_key_last4"] == "1234"
    assert "api_key" not in read


@pytest.mark.asyncio
async def test_partial_credit_debits_wallet_and_leaves_residual_awaiting_payment(db, organization_id):
    await _configure_bank_transfer(db, organization_id)
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    _provider, product = await _make_imported_product(db, organization_id, admin.id, price_cents=5000, discount_pct=20)

    wallet = await wallet_service.get_or_create_wallet(db, organization_id=organization_id, user_id=customer.id)
    await wallet_service.credit_wallet(
        db, organization_id=organization_id, wallet_id=wallet.id, amount_cents=2000, type_="ADMIN_CREDIT",
        actor_user_id=admin.id, idempotency_key=str(uuid.uuid4()),
    )

    quote = await imported_products_service.get_quote(
        db, organization_id=organization_id, customer_user_id=customer.id, imported_product_id=product.id
    )
    assert quote["max_creditable_cents"] == 1000  # 20% of 5000
    assert quote["customer_wallet_balance_cents"] == 2000

    await _seed_credit_spend_otp(db, customer.id)
    order = await imported_products_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, imported_product_id=product.id,
        credit_applied_cents=1000, actor_user_id=customer.id, otp_code=VALID_OTP_CODE,
    )
    assert order.status == "AWAITING_PAYMENT"
    assert order.amount_cents == _con_iva(5000)
    assert order.credit_applied_cents == 1000
    assert order.credit_debit_transaction_id is not None

    wallet_after = await wallet_service.get_wallet_by_user_id(db, organization_id=organization_id, user_id=customer.id)
    assert wallet_after.balance_cents == 1000

    txn = await db.get(wallet_service.WalletTransaction, order.credit_debit_transaction_id)
    assert txn.reference_imported_order_id == order.id
    assert txn.reference_order_id is None

    confirmed = await imported_products_service.confirm_payment(
        db, organization_id=organization_id, order_id=order.id, actor_user_id=admin.id
    )
    assert confirmed.status == "PAID"


@pytest.mark.asyncio
async def test_sosnetcash_can_never_cover_the_whole_price(db, organization_id):
    """SosnetCash can never cover 100% of a marketplace product."""
    from app.modules.marketplaces import rules

    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    with pytest.raises(rules.CreditPercentageError):
        await _make_imported_product(db, organization_id, admin.id, price_cents=3000, discount_pct=100)
    _provider, product = await _make_imported_product(db, organization_id, admin.id, price_cents=3000, discount_pct=99)
    with pytest.raises(rules.CreditPercentageError):
        await imported_products_service.update_imported_product(
            db, product=product, updates={"credit_discount_percentage": 100}
        )
    customer = await _make_user_with_role(db, organization_id)
    quote = await imported_products_service.get_quote(
        db, organization_id=organization_id, customer_user_id=customer.id, imported_product_id=product.id
    )
    assert quote["max_creditable_cents"] == 2970


@pytest.mark.asyncio
async def test_card_costs_five_percent_more_and_bank_transfer_does_not(db, organization_id):
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    await organizations_service.update_settings(
        db, organization_id=organization_id, payload=OrganizationSettingsUpdate(bank_iban="IT66W0883330410000000015702")
    )
    await organizations_service.update_payment_settings(
        db, organization_id=organization_id,
        payload=PaymentSettingsUpdate(
            stripe_publishable_key="pk_test_x", stripe_secret_key="sk_test_x", stripe_webhook_secret="whsec_x",
        ),
    )
    _provider, product = await _make_imported_product(db, organization_id, admin.id, price_cents=3000, discount_pct=30)
    quote = await imported_products_service.get_quote(
        db, organization_id=organization_id, customer_user_id=customer.id, imported_product_id=product.id
    )
    assert quote["bank_transfer_discount_percentage"] == 5 and quote["bank_transfer_amount_cents"] == quote["amount_cents"] - (quote["amount_cents"] * 5 + 50) // 100

    order = await imported_products_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, imported_product_id=product.id,
        credit_applied_cents=0, payment_method="BANK_TRANSFER", actor_user_id=customer.id,
    )
    assert order.bank_transfer_discount_cents == ((order.amount_cents - order.credit_applied_cents) * 5 + 50) // 100 and imported_products_service.amount_due_cents(order) == order.amount_cents - order.bank_transfer_discount_cents
    order = await imported_products_service.change_payment_method(
        db, organization_id=organization_id, order=order, new_payment_method="CARD"
    )
    # Card pays the full price, without the bank-transfer discount.
    assert order.bank_transfer_discount_cents == 0 and imported_products_service.amount_due_cents(order) == order.amount_cents - order.credit_applied_cents
    read = await imported_products_service.to_read_dict(db, order)
    assert read["amount_due_cents"] == order.amount_cents - order.credit_applied_cents


@pytest.mark.asyncio
async def test_credit_over_cap_is_rejected(db, organization_id):
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    _provider, product = await _make_imported_product(db, organization_id, admin.id, price_cents=5000, discount_pct=20)

    await _seed_credit_spend_otp(db, customer.id)
    with pytest.raises(imported_products_service.InvalidCreditAmountError):
        await imported_products_service.create_order(
            db, organization_id=organization_id, customer_user_id=customer.id, imported_product_id=product.id,
            credit_applied_cents=1001, actor_user_id=customer.id, otp_code=VALID_OTP_CODE,
        )


@pytest.mark.asyncio
async def test_spending_credit_without_a_valid_otp_is_rejected(db, organization_id):
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    _provider, product = await _make_imported_product(db, organization_id, admin.id, price_cents=5000, discount_pct=20)

    wallet = await wallet_service.get_or_create_wallet(db, organization_id=organization_id, user_id=customer.id)
    await wallet_service.credit_wallet(
        db, organization_id=organization_id, wallet_id=wallet.id, amount_cents=2000, type_="ADMIN_CREDIT",
        actor_user_id=admin.id, idempotency_key=str(uuid.uuid4()),
    )

    with pytest.raises(imported_products_service.InvalidOtpError):
        await imported_products_service.create_order(
            db, organization_id=organization_id, customer_user_id=customer.id, imported_product_id=product.id,
            credit_applied_cents=500, actor_user_id=customer.id, otp_code="000000",
        )


@pytest.mark.asyncio
async def test_cancel_refunds_the_exact_credit_debit_via_reversal(db, organization_id):
    await _configure_bank_transfer(db, organization_id)
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    _provider, product = await _make_imported_product(db, organization_id, admin.id, price_cents=5000, discount_pct=20)

    wallet = await wallet_service.get_or_create_wallet(db, organization_id=organization_id, user_id=customer.id)
    await wallet_service.credit_wallet(
        db, organization_id=organization_id, wallet_id=wallet.id, amount_cents=2000, type_="ADMIN_CREDIT",
        actor_user_id=admin.id, idempotency_key=str(uuid.uuid4()),
    )

    await _seed_credit_spend_otp(db, customer.id)
    order = await imported_products_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, imported_product_id=product.id,
        credit_applied_cents=1000, actor_user_id=customer.id, otp_code=VALID_OTP_CODE,
    )
    wallet_mid = await wallet_service.get_wallet_by_user_id(db, organization_id=organization_id, user_id=customer.id)
    assert wallet_mid.balance_cents == 1000

    cancelled = await imported_products_service.cancel_order(
        db, organization_id=organization_id, order_id=order.id, reason="Cliente ha cambiato idea", actor_user_id=admin.id,
    )
    assert cancelled.status == "CANCELLED"

    wallet_after = await wallet_service.get_wallet_by_user_id(db, organization_id=organization_id, user_id=customer.id)
    assert wallet_after.balance_cents == 2000


@pytest.mark.asyncio
async def test_product_never_offers_cashback_fields(db, organization_id):
    """These orders carry no cashback fields; the read-dict shape is the
    enforced contract."""
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    await _configure_bank_transfer(db, organization_id)
    _provider, product = await _make_imported_product(db, organization_id, admin.id, price_cents=5000, discount_pct=0)

    order = await imported_products_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, imported_product_id=product.id,
        credit_applied_cents=0, actor_user_id=customer.id,
    )
    row = await imported_products_service.to_read_dict(db, order)
    assert "cashback_requested" not in row
    assert "cashback_surcharge_cents" not in row
    assert row["residual_amount_cents"] == order.amount_cents - order.credit_applied_cents


@pytest.mark.asyncio
async def test_shop_sections_can_be_renamed_and_switched_off(db, organization_id):
    """The Shop's own sections (contracts, partner, offers) can be enabled,
    disabled and renamed like the marketplaces; all start enabled."""
    from app.modules.marketplaces import rules

    sections = await rules.get_sections(db, organization_id=organization_id)
    assert sections["internal"] == {"label": "SOSNET", "enabled": True}
    assert sections["dropshipping"]["label"] == "Offerte Sosnet"

    config = await rules.update_config(
        db, organization_id=organization_id, labels=None, bank_transfer_discount_percentage=None,
        sections={"partner": {"enabled": False}, "dropshipping": {"label": "  Occasioni  "}},
    )
    assert config["sections"]["partner"] == {"label": "Prodotti Partner", "enabled": False}
    assert config["sections"]["dropshipping"] == {"label": "Occasioni", "enabled": True}
    # Other sections and marketplace labels are unaffected.
    assert config["sections"]["internal"]["enabled"] is True
    assert config["labels"]["cj"] == "Marketplace 1"

    # A blank label resets to the default; unknown keys are ignored.
    config = await rules.update_config(
        db, organization_id=organization_id, labels=None, bank_transfer_discount_percentage=None,
        sections={"dropshipping": {"label": "   "}, "inventata": {"enabled": False}},
    )
    assert config["sections"]["dropshipping"]["label"] == "Offerte Sosnet"
    assert "inventata" not in config["sections"]


@pytest.mark.asyncio
async def test_vat_is_included_in_the_price_and_frozen_on_the_order(db, organization_id):
    """VAT is added on the full price of the goods and frozen on the order.
    Neither the bank-transfer discount nor SosnetCash changes it."""
    from app.modules.marketplaces import rules

    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    await _configure_bank_transfer(db, organization_id)
    await organizations_service.update_payment_settings(
        db, organization_id=organization_id,
        payload=PaymentSettingsUpdate(
            stripe_publishable_key="pk_test_x", stripe_secret_key="sk_test_x", stripe_webhook_secret="whsec_x",
        ),
    )
    _provider, product = await _make_imported_product(db, organization_id, admin.id, price_cents=3000, discount_pct=30)

    order = await imported_products_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, imported_product_id=product.id,
        credit_applied_cents=0, payment_method="BANK_TRANSFER", actor_user_id=customer.id,
    )
    assert order.bank_transfer_discount_cents == ((order.amount_cents - order.credit_applied_cents) * 5 + 50) // 100
    assert order.vat_percentage == 22 and order.vat_amount_cents == 660  # 22% of 3000

    order = await imported_products_service.change_payment_method(
        db, organization_id=organization_id, order=order, new_payment_method="CARD"
    )
    # Card: no bank-transfer discount, never a surcharge.
    assert order.bank_transfer_discount_cents == 0
    assert order.vat_amount_cents == 660
    assert imported_products_service.amount_due_cents(order) == (
        order.amount_cents - order.credit_applied_cents - order.bank_transfer_discount_cents
    )
    read = await imported_products_service.to_read_dict(db, order)
    assert read["vat_percentage"] == 22 and read["vat_amount_cents"] == 660

    # SosnetCash is a payment method, not a discount.
    wallet = await wallet_service.get_or_create_wallet(db, organization_id=organization_id, user_id=customer.id)
    await wallet_service.credit_wallet(
        db, organization_id=organization_id, wallet_id=wallet.id, amount_cents=900, type_="ADMIN_CREDIT",
        actor_user_id=admin.id, idempotency_key=str(uuid.uuid4()),
    )
    await _seed_credit_spend_otp(db, customer.id)
    with_credit = await imported_products_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, imported_product_id=product.id,
        credit_applied_cents=900, payment_method="BANK_TRANSFER", actor_user_id=customer.id, otp_code=VALID_OTP_CODE,
    )
    # 5% of the amount left after SosnetCash.
    assert with_credit.bank_transfer_discount_cents == (
        (with_credit.amount_cents - with_credit.credit_applied_cents) * 5 + 50
    ) // 100
    assert with_credit.vat_amount_cents == 660

    # Zero rate: no VAT and the price is unchanged.
    await rules.update_config(
        db, organization_id=organization_id, labels=None, bank_transfer_discount_percentage=None, vat_percentage=0
    )
    zero = await imported_products_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, imported_product_id=product.id,
        credit_applied_cents=0, payment_method="BANK_TRANSFER", actor_user_id=customer.id,
    )
    assert zero.vat_percentage == 0 and zero.vat_amount_cents == 0
    assert zero.amount_cents == 3000
