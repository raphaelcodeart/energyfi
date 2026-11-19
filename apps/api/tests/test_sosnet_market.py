"""Sosnet Market ("Fai la Spesa con Sosnet") storefront.

Rules shared by every marketplace are covered in their own test modules.
This module covers what is specific to this shop: a hand-written catalogue,
the producer name frozen on each order, flat-rate shipping, and cart,
SosnetCash and VAT behaving as in the other marketplaces."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.modules.auth import service as auth_service
from app.modules.auth.models import OtpCode
from app.modules.carts import service as carts_service
from app.modules.sosnet_market import service as market
from app.modules.marketplaces import rules
from app.modules.organizations import service as organizations_service
from app.modules.organizations.schemas import OrganizationSettingsUpdate
from app.modules.rbac.models import Role, UserRole
from app.modules.users.models import User
from app.modules.wallets import service as wallet_service
from app.foundation.security import hash_otp_code, hash_password

OTP = "424242"
ADDRESS = {
    "recipient_name": "Mario Rossi", "recipient_phone": "333 1234567", "address_line1": "Via Roma 1",
    "address_line2": None, "city": "Milano", "province": "MI", "postal_code": "20100",
}


async def _user(db, organization_id, role_code="CUSTOMER"):
    from sqlalchemy import select

    user = User(
        organization_id=organization_id, email=f"{role_code.lower()}-{uuid.uuid4().hex[:6]}@example.demo",
        password_hash=hash_password("x"),
    )
    db.add(user)
    await db.flush()
    role = (
        await db.execute(select(Role).where(Role.organization_id == organization_id, Role.code == role_code))
    ).scalar_one_or_none()
    if role is None:
        role = Role(organization_id=organization_id, code=role_code, name=role_code.title())
        db.add(role)
        await db.flush()
    db.add(UserRole(user_id=user.id, organization_id=organization_id, role_id=role.id))
    await db.commit()
    await db.refresh(user)
    return user


async def _otp(db, user_id):
    db.add(OtpCode(
        user_id=user_id, purpose=auth_service.WALLET_CREDIT_SPEND_OTP_PURPOSE, code_hash=hash_otp_code(OTP),
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
    ))
    await db.commit()


async def _shop(db, organization_id, admin, *, shipping_flat_cents=490, credit_percentage=25):
    await organizations_service.update_settings(
        db, organization_id=organization_id,
        payload=OrganizationSettingsUpdate(bank_iban="IT66W0883330410000000015702"),
    )
    row = await market.get_settings_row(db, organization_id=organization_id)
    await market.update_settings(
        db, row=row, actor_user_id=admin.id,
        updates={"enabled": True, "shipping_flat_cents": shipping_flat_cents, "shipping_days": "3-5"},
    )
    producer = await market.create_producer(
        db, organization_id=organization_id, actor_user_id=admin.id,
        payload={"name": "Caseificio Rossi", "description": "Formaggi di malga dal 1952",
                 "website_url": "https://caseificiorossi.it", "vat_number": "IT01234567890",
                 "email": None, "phone": None, "address": None, "logo_url": None},
    )
    pane = await market.create_product(
        db, organization_id=organization_id, actor_user_id=admin.id,
        payload={"name": "Pane di segale", "description": "Cotto a legna",
                 "credit_discount_percentage": credit_percentage, "unit_cost_cents": 200,
                 "producer_id": producer.id,
                 "variants": [{"label": "500 g", "price_cents": 450, "inventory": 20},
                              {"label": "1 kg", "price_cents": 800, "inventory": 10}]},
    )
    miele = await market.create_product(
        db, organization_id=organization_id, actor_user_id=admin.id,
        payload={"name": "Miele di acacia", "description": "Vasetto da 500 g",
                 "credit_discount_percentage": credit_percentage, "unit_cost_cents": 400,
                 "producer_id": producer.id,
                 "variants": [{"label": "Unica", "price_cents": 900, "inventory": 15}]},
    )
    return row, producer, pane, miele


async def _variants(db, product):
    return await market._variants(db, product.id)


@pytest.mark.asyncio
async def test_the_admin_builds_the_catalogue_by_hand(db, organization_id):
    """With no supplier, the admin writes products and variants by hand; a
    product without variants is rejected."""
    admin = await _user(db, organization_id, "ADMIN")
    _row, producer, pane, _miele = await _shop(db, organization_id, admin)

    letto = await market.product_read_dict(db, pane, admin=True)
    assert letto["name"] == "Pane di segale"
    assert [v["label"] for v in letto["variants"]] == ["500 g", "1 kg"]
    assert letto["producer"]["name"] == "Caseificio Rossi"
    # Customers see the producer, but not its VAT number.
    pubblico = await market.product_read_dict(db, pane, admin=False)
    assert pubblico["producer"]["name"] == "Caseificio Rossi"
    assert "vat_number" not in pubblico["producer"]

    with pytest.raises(market.SosnetMarketValidationError):
        await market.create_product(
            db, organization_id=organization_id, actor_user_id=admin.id,
            payload={"name": "Senza varianti", "variants": []},
        )
    # Producer names are unique.
    with pytest.raises(market.SosnetMarketValidationError):
        await market.create_producer(
            db, organization_id=organization_id, actor_user_id=admin.id, payload={"name": producer.name},
        )


@pytest.mark.asyncio
async def test_the_shop_is_empty_while_it_is_switched_off(db, organization_id):
    """A disabled shop shows and sells nothing, and its tile disappears from
    the Shop."""
    admin = await _user(db, organization_id, "ADMIN")
    customer = await _user(db, organization_id)
    row, _p, pane, _m = await _shop(db, organization_id, admin)
    assert len(await market.customer_products(db, organization_id=organization_id)) == 2

    await market.update_settings(db, row=row, actor_user_id=admin.id, updates={"enabled": False})
    assert await market.customer_products(db, organization_id=organization_id) == []
    variante = (await _variants(db, pane))[0]
    with pytest.raises(market.SosnetMarketValidationError):
        await market.get_quote(
            db, organization_id=organization_id, customer_user_id=customer.id,
            variant_id=variante.id, quantity=1,
        )


@pytest.mark.asyncio
async def test_the_quote_adds_vat_and_charges_one_shipping(db, organization_id):
    """VAT is added on goods, shipping is charged once per order, and the
    SosnetCash cap is the sum of the line caps."""
    admin = await _user(db, organization_id, "ADMIN")
    customer = await _user(db, organization_id)
    _row, _p, pane, miele = await _shop(db, organization_id, admin)
    mezzo_kg = (await _variants(db, pane))[0]
    vasetto = (await _variants(db, miele))[0]

    quote = await market.get_quote(
        db, organization_id=organization_id, customer_user_id=customer.id,
        lines=[(mezzo_kg.id, 2), (vasetto.id, 1)],
    )
    merce = 450 * 2 + 900
    assert quote["items_cents"] == merce
    assert quote["vat_cents"] == rules.vat_added_cents(net_cents=merce, percentage=22)
    assert quote["shipping_cents"] == 490
    assert quote["amount_cents"] == merce + quote["vat_cents"] + 490
    # Cap excludes shipping and VAT.
    assert quote["max_creditable_cents"] == round(900 * 25 / 100) + round(900 * 25 / 100)
    assert quote["max_creditable_cents"] == sum(i["max_creditable_cents"] for i in quote["items"])


@pytest.mark.asyncio
async def test_the_cart_becomes_one_order_that_remembers_the_producer(db, organization_id):
    """Orders freeze the producer name, so renaming the producer does not
    rewrite past orders."""
    admin = await _user(db, organization_id, "ADMIN")
    customer = await _user(db, organization_id)
    _row, producer, pane, miele = await _shop(db, organization_id, admin)
    mezzo_kg = (await _variants(db, pane))[0]
    vasetto = (await _variants(db, miele))[0]

    for variante, quantita in ((mezzo_kg, 2), (vasetto, 1)):
        await carts_service.add_item(
            db, organization_id=organization_id, customer_user_id=customer.id, shop="sosnet_market",
            variant_id=variante.id, quantity=quantita,
        )
    riepilogo = await carts_service.summary(
        db, organization_id=organization_id, customer_user_id=customer.id
    )
    sezione = riepilogo["sections"][0]
    assert sezione["shop"] == "sosnet_market" and len(sezione["items"]) == 2

    _cart, lines = await carts_service.checkout_lines(
        db, customer_user_id=customer.id, shop="sosnet_market"
    )
    order = await market.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, lines=lines, address=ADDRESS,
        credit_applied_cents=0, payment_method="BANK_TRANSFER", actor_user_id=customer.id,
        otp_code=None, note=None,
    )
    items = await market.order_items(db, order)
    assert len(items) == 2
    assert all(i.producer_name == "Caseificio Rossi" for i in items)
    assert order.number and market.order_code(order) == str(order.number)
    assert order.vat_mode == "ADDED"

    await market.update_producer(
        db, organization_id=organization_id, producer_id=producer.id, payload={"name": "Caseificio Bianchi"},
    )
    items = await market.order_items(db, order)
    assert all(i.producer_name == "Caseificio Rossi" for i in items)

    await carts_service.clear(db, customer_user_id=customer.id, shop="sosnet_market")
    vuoto = await carts_service.summary(db, organization_id=organization_id, customer_user_id=customer.id)
    assert vuoto["sections"] == []


@pytest.mark.asyncio
async def test_sosnetcash_is_spent_with_a_code_and_never_covers_it_all(db, organization_id):
    admin = await _user(db, organization_id, "ADMIN")
    customer = await _user(db, organization_id)
    _row, _p, pane, _m = await _shop(db, organization_id, admin, credit_percentage=99)
    variante = (await _variants(db, pane))[1]  # 1 kg, 8.00
    wallet = await wallet_service.get_or_create_wallet(
        db, organization_id=organization_id, user_id=customer.id
    )
    await wallet_service.credit_wallet(
        db, organization_id=organization_id, wallet_id=wallet.id, amount_cents=10000,
        type_="ADMIN_CREDIT", actor_user_id=admin.id, idempotency_key=str(uuid.uuid4()),
    )
    quote = await market.get_quote(
        db, organization_id=organization_id, customer_user_id=customer.id, variant_id=variante.id, quantity=1
    )
    # Never the whole order, whatever the percentage.
    assert quote["max_creditable_cents"] < quote["amount_cents"]

    with pytest.raises(market.InvalidOtpError):
        await market.create_order(
            db, organization_id=organization_id, customer_user_id=customer.id, variant_id=variante.id,
            quantity=1, address=ADDRESS, credit_applied_cents=quote["max_creditable_cents"],
            payment_method="BANK_TRANSFER", actor_user_id=customer.id, otp_code="000000", note=None,
        )
    await _otp(db, customer.id)
    order = await market.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, variant_id=variante.id,
        quantity=1, address=ADDRESS, credit_applied_cents=quote["max_creditable_cents"],
        payment_method="BANK_TRANSFER", actor_user_id=customer.id, otp_code=OTP, note=None,
    )
    assert order.credit_applied_cents == quote["max_creditable_cents"]
    # SosnetCash is a payment method and does not reduce VAT.
    assert order.vat_amount_cents == rules.vat_added_cents(net_cents=order.items_cents, percentage=22)
    # Bank-transfer discount is 5% of the amount left after SosnetCash.
    residuo = order.amount_cents - order.credit_applied_cents
    assert order.bank_transfer_discount_cents == (residuo * 5 + 50) // 100


@pytest.mark.asyncio
async def test_the_admin_ships_it_and_the_customer_is_told(db, organization_id):
    """There is no supplier to forward to: the customer pays, then the admin
    ships and records the tracking number."""
    admin = await _user(db, organization_id, "ADMIN")
    customer = await _user(db, organization_id)
    _row, _p, pane, _m = await _shop(db, organization_id, admin)
    variante = (await _variants(db, pane))[0]
    order = await market.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, variant_id=variante.id,
        quantity=1, address=ADDRESS, credit_applied_cents=0, payment_method="BANK_TRANSFER",
        actor_user_id=customer.id, otp_code=None, note=None,
    )
    # An unpaid order cannot be shipped.
    with pytest.raises(market.SosnetMarketValidationError):
        await market.mark_shipped(
            db, organization_id=organization_id, order_id=order.id, actor_user_id=admin.id,
            tracking_number="X1", tracking_url=None, tracking_company=None,
        )
    await market.confirm_payment(
        db, organization_id=organization_id, order_id=order.id, actor_user_id=admin.id
    )
    await db.refresh(order)
    assert order.status == "PAID" and market.delivery_status(order) == "RECEIVED"

    await market.mark_shipped(
        db, organization_id=organization_id, order_id=order.id, actor_user_id=admin.id,
        tracking_number="RR123456789IT", tracking_url=None, tracking_company="Poste",
    )
    await db.refresh(order)
    assert market.delivery_status(order) == "SHIPPED" and order.tracking_number == "RR123456789IT"

    await market.mark_delivered(
        db, organization_id=organization_id, order_id=order.id, actor_user_id=admin.id
    )
    await db.refresh(order)
    assert market.delivery_status(order) == "DELIVERED"


@pytest.mark.asyncio
async def test_a_sold_out_variant_cannot_be_bought_or_put_in_the_cart(db, organization_id):
    admin = await _user(db, organization_id, "ADMIN")
    customer = await _user(db, organization_id)
    _row, _p, pane, _m = await _shop(db, organization_id, admin)
    variante = (await _variants(db, pane))[0]
    await market.update_variant(
        db, organization_id=organization_id, variant_id=variante.id, payload={"inventory": 0}
    )
    with pytest.raises(market.SosnetMarketValidationError):
        await market.get_quote(
            db, organization_id=organization_id, customer_user_id=customer.id,
            variant_id=variante.id, quantity=1,
        )
    with pytest.raises(carts_service.CartValidationError):
        await carts_service.add_item(
            db, organization_id=organization_id, customer_user_id=customer.id, shop="sosnet_market",
            variant_id=variante.id, quantity=1,
        )


# --- Forwarding orders to producers -------------------------------------------------


async def _paid_order(db, organization_id, admin, customer, *, lines):
    order = await market.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, lines=lines, address=ADDRESS,
        credit_applied_cents=0, payment_method="BANK_TRANSFER", actor_user_id=customer.id,
        otp_code=None, note="Citofonare Rossi",
    )
    await market.confirm_payment(
        db, organization_id=organization_id, order_id=order.id, actor_user_id=admin.id
    )
    await db.refresh(order)
    return order


@pytest.mark.asyncio
async def test_the_order_is_emailed_to_each_producer_with_only_its_own_lines(
    db, organization_id, monkeypatch
):
    """A mixed order sends each producer only its own lines plus the
    delivery address."""
    inviate: list[dict] = []
    monkeypatch.setattr(market, "send_html_email_best_effort", lambda **kw: inviate.append(kw) or True)

    admin = await _user(db, organization_id, "ADMIN")
    customer = await _user(db, organization_id)
    _row, primo, pane, miele = await _shop(db, organization_id, admin)
    await market.update_producer(
        db, organization_id=organization_id, producer_id=primo.id, payload={"email": "ordini@caseificio.it"}
    )
    secondo = await market.create_producer(
        db, organization_id=organization_id, actor_user_id=admin.id,
        payload={"name": "Apicoltura Verdi", "description": "", "email": "ciao@apicolturaverdi.it",
                 "website_url": None, "logo_url": None, "vat_number": None, "phone": None, "address": None},
    )
    await market.update_product(
        db, organization_id=organization_id, product_id=miele.id, payload={"producer_id": secondo.id}
    )

    mezzo_kg = (await _variants(db, pane))[0]
    vasetto = (await _variants(db, miele))[0]
    order = await _paid_order(
        db, organization_id, admin, customer, lines=[(mezzo_kg.id, 2), (vasetto.id, 1)]
    )
    inviate.clear()  # drop customer emails; only producer emails matter here

    await market.forward_order(
        db, organization_id=organization_id, order_id=order.id, actor_user_id=admin.id
    )
    ai_fornitori = {m["to"]: m for m in inviate}
    assert set(ai_fornitori) == {"ordini@caseificio.it", "ciao@apicolturaverdi.it"}

    caseificio = ai_fornitori["ordini@caseificio.it"]["html_body"]
    apicoltura = ai_fornitori["ciao@apicolturaverdi.it"]["html_body"]
    assert "Pane di segale" in caseificio and "Miele" not in caseificio
    assert "Miele di acacia" in apicoltura and "Pane" not in apicoltura
    # Both get the delivery address and the customer note.
    for corpo in (caseificio, apicoltura):
        assert "Via Roma 1" in corpo and "20100" in corpo and "Mario Rossi" in corpo
        assert "Citofonare Rossi" in corpo
        # Never the customer price: it would reveal the markup.
        assert "4,50" not in corpo and "9,00" not in corpo

    await db.refresh(order)
    assert order.fulfillment_status == "SENT" and order.forwarded_at is not None
    assert order.forward_error is None


@pytest.mark.asyncio
async def test_an_order_is_never_forwarded_before_it_is_paid(db, organization_id):
    admin = await _user(db, organization_id, "ADMIN")
    customer = await _user(db, organization_id)
    _row, producer, pane, _m = await _shop(db, organization_id, admin)
    await market.update_producer(
        db, organization_id=organization_id, producer_id=producer.id, payload={"email": "ordini@caseificio.it"}
    )
    variante = (await _variants(db, pane))[0]
    order = await market.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, variant_id=variante.id,
        quantity=1, address=ADDRESS, credit_applied_cents=0, payment_method="BANK_TRANSFER",
        actor_user_id=customer.id, otp_code=None, note=None,
    )
    with pytest.raises(market.SosnetMarketValidationError):
        await market.forward_order(
            db, organization_id=organization_id, order_id=order.id, actor_user_id=admin.id
        )


@pytest.mark.asyncio
async def test_a_company_without_an_email_is_reported_and_not_silently_skipped(
    db, organization_id, monkeypatch
):
    """A producer without an email means goods nobody is preparing, so it
    must be reported rather than ignored."""
    inviate: list[dict] = []
    monkeypatch.setattr(market, "send_html_email_best_effort", lambda **kw: inviate.append(kw) or True)
    admin = await _user(db, organization_id, "ADMIN")
    customer = await _user(db, organization_id)
    _row, _producer, pane, _m = await _shop(db, organization_id, admin)  # no email on the producer
    variante = (await _variants(db, pane))[0]
    order = await _paid_order(db, organization_id, admin, customer, lines=[(variante.id, 1)])

    with pytest.raises(market.SosnetMarketValidationError):
        await market.forward_order(
            db, organization_id=organization_id, order_id=order.id, actor_user_id=admin.id
        )
    await db.refresh(order)
    assert order.fulfillment_status == "NOT_SENT"
    assert "non ha un'email" in (order.forward_error or "")


@pytest.mark.asyncio
async def test_auto_forward_sends_it_the_moment_the_payment_is_confirmed(
    db, organization_id, monkeypatch
):
    """Auto-forward off (the default) waits for the manual button; on, the
    order is sent at payment."""
    inviate: list[dict] = []
    monkeypatch.setattr(market, "send_html_email_best_effort", lambda **kw: inviate.append(kw) or True)
    admin = await _user(db, organization_id, "ADMIN")
    customer = await _user(db, organization_id)
    row, producer, pane, _m = await _shop(db, organization_id, admin)
    assert row.auto_forward is False, "l'automatismo deve nascere spento"
    await market.update_producer(
        db, organization_id=organization_id, producer_id=producer.id, payload={"email": "ordini@caseificio.it"}
    )
    variante = (await _variants(db, pane))[0]

    order = await _paid_order(db, organization_id, admin, customer, lines=[(variante.id, 1)])
    assert not [m for m in inviate if m["to"] == "ordini@caseificio.it"]
    await db.refresh(order)
    assert order.fulfillment_status == "NOT_SENT"

    await market.update_settings(db, row=row, actor_user_id=admin.id, updates={"auto_forward": True})
    inviate.clear()
    altro = await _paid_order(db, organization_id, admin, customer, lines=[(variante.id, 1)])
    assert [m for m in inviate if m["to"] == "ordini@caseificio.it"]
    await db.refresh(altro)
    assert altro.fulfillment_status == "SENT"
