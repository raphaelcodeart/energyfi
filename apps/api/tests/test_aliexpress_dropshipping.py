"""AliExpress dropshipping marketplace: pricing, import, the shared checkout
(SosnetCash never 100%, bank transfer -5%), placing paid orders with the
supplier without duplicates, and tracking them to delivery.

Business requests are faked at client.call; request signing and the token
exchange are tested against client._post, the only other path to the
gateway. Fake responses follow the documented shapes, including nestings
that differ between methods, so the readers never silently return an empty
result."""

import hashlib
import hmac
import json
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
import stripe
from sqlalchemy import select

from app.foundation.security import hash_otp_code, hash_password
from app.modules.accounting import details as accounting_details
from app.modules.accounting import service as accounting_service
from app.modules.aliexpress_dropshipping import client as aliexpress_client
from app.modules.aliexpress_dropshipping import pricing
from app.modules.aliexpress_dropshipping import service as aliexpress_service
from app.modules.aliexpress_dropshipping.models import AliexpressProduct, AliexpressSettings, AliexpressVariant
from app.modules.auth import service as auth_service
from app.modules.auth.models import OtpCode
from app.modules.marketplaces import rules
from app.modules.organizations import service as organizations_service
from app.modules.organizations.models import Organization
from app.modules.organizations.schemas import OrganizationSettingsUpdate
from app.modules.rbac.models import Role, UserRole
from app.modules.users.models import User
from app.modules.carts import service as carts_service
from app.modules.wallets import service as wallet_service

def _con_iva(merce_cents: int, aliquota: int = 22) -> int:
    """Customer total for the goods: VAT is added on top of the listed price."""
    from app.modules.marketplaces import rules

    return merce_cents + rules.vat_added_cents(net_cents=merce_cents, percentage=aliquota)


OTP = "333444"
ADDRESS = {
    "recipient_name": "Mario Rossi", "recipient_phone": "333 1234567", "address_line1": "Via Roma 1",
    "address_line2": None, "city": "Milano", "province": "MI", "postal_code": "20100",
}
PRODUCT_ID = "1005006123456789"
APP_KEY = "547960"
APP_SECRET = "s3cret_wxyz"


def _sku(sku_id, *, code, colour, sale, price, stock):
    """A SKU as described by ds.product.get."""
    sku = {
        "sku_id": sku_id,
        "sku_attr": f"14:{sku_id}",
        "sku_code": code,
        "sku_price": price,
        "sku_available_stock": stock,
        "ae_sku_property_dtos": {
            "ae_sku_property_d_t_o": [
                {"sku_property_name": "Colore", "property_value_definition_name": colour}
            ]
        },
    }
    if sale is not None:
        sku["offer_sale_price"] = sale
    return sku


class FakeAliexpress:
    """The DS gateway as seen by `call()`."""

    def __init__(self):
        self.calls: list[str] = []
        self.params: list[dict] = []
        self.orders: dict[str, dict] = {}
        self.orders_created = 0
        #: "lost" = the order is created but the response never arrives.
        self.fail_create_once: str | None = None
        self.fail_create: str | None = None
        #: Respond to the create call without an order number.
        self.create_without_number = False
        self.tracking: dict = {}
        self.search_shape = "documented"
        #: Shipping cost in cents and ways to break the quote;
        #: `freight_by_quantity` makes the answer depend on quantity, as the real API does.
        self.freight_cents = 499
        self.freight_by_quantity: dict[int, int] = {}
        self.freight_by_sku: dict[str, int] = {}
        self.fail_freight: str | None = None
        self.freight_without_price = False

    async def __call__(self, settings, method, params=None):
        self.calls.append(method)
        self.params.append(dict(params or {}))
        if method == "aliexpress.ds.category.get":
            return {"aliexpress_ds_category_get_response": {"resp_result": {"result": {
                "categories": {"category": [
                    {"category_id": 3, "category_name": "Elettronica"},
                    {"category_id": 7, "category_name": "Casa"},
                ]}
            }}}}
        if method == "aliexpress.ds.text.search":
            item = {
                "product_id": PRODUCT_ID, "product_title": "Wireless Earbuds",
                "product_main_image_url": "https://img/1.jpg", "target_sale_price": "10.00",
                "target_original_price": "24.00", "store_name": "ACME Store",
                "product_detail_url": f"https://www.aliexpress.com/item/{PRODUCT_ID}.html",
            }
            if self.search_shape == "documented":
                return {"aliexpress_ds_text_search_response": {"data": {
                    "products": {"selection_search_product": [item]}, "totalPage": 1,
                }}}
            # The alternative nesting documented for the same method.
            return {"aliexpress_ds_text_search_response": {"resp_result": {"result": {
                "products": [item], "total_page": 1,
            }}}}
        if method == "aliexpress.ds.product.get":
            return {"aliexpress_ds_product_get_response": {"result": {
                "ae_item_base_info_dto": {
                    "product_id": PRODUCT_ID, "subject": "Wireless Earbuds",
                    "detail": "<p>Great <b>sound</b></p><script>x()</script>",
                    "product_status_type": "onSelling",
                    "detail_url": f"https://www.aliexpress.com/item/{PRODUCT_ID}.html",
                },
                "ae_multimedia_info_dto": {"image_urls": "https://img/1.jpg;https://img/2.jpg"},
                "ae_store_info": {"store_name": "ACME Store"},
                "ae_item_sku_info_dtos": {"ae_item_sku_info_d_t_o": [
                    _sku("11", code="EB-B", colour="Nero", sale="10.00", price="24.00", stock=50),
                    _sku("12", code="EB-W", colour="Bianco", sale=None, price="25.00", stock=0),
                ]},
            }}}
        if method == "aliexpress.ds.freight.query":
            if self.fail_freight:
                raise aliexpress_client.AliexpressApiError(self.fail_freight, "TEMPORARY")
            asked = json.loads(params["queryDeliveryReq"])
            quantity = int(asked["quantity"])
            sku = str(asked.get("selectedSkuId") or "")
            cents = self.freight_by_sku.get(sku, self.freight_by_quantity.get(quantity, self.freight_cents))
            option = {
                "service_name": "AliExpress Standard Shipping", "company": "Cainiao",
                "shipping_fee_currency": "EUR",
                "min_delivery_days": 10, "max_delivery_days": 20, "tracking": True,
            }
            # An option without a price is not free: its cost is unknown.
            if not self.freight_without_price:
                # The real API returns an amount ("1.99"), not cents, despite the field name.
                option["shipping_fee_cent"] = f"{cents / 100:.2f}"
            return {"aliexpress_ds_freight_query_response": {"result": {"delivery_options": {
                "delivery_option_dto": [option]
            }}}}
        if method == "aliexpress.ds.order.create":
            if self.fail_create:
                raise aliexpress_client.AliexpressApiError(
                    f"AliExpress: {self.fail_create} (codice 15).", "VALIDATION"
                )
            self.orders_created += 1
            order_id = str(3000 + self.orders_created)
            self.orders[order_id] = {"request": params, "tracking": None}
            if self.fail_create_once:
                self.fail_create_once = None
                raise aliexpress_client.AliexpressApiError(
                    "AliExpress non risponde (ReadTimeout). Riprova tra poco.", "TEMPORARY"
                )
            if self.create_without_number:
                return {"aliexpress_ds_order_create_response": {"result": {"is_success": True}}}
            return {"aliexpress_ds_order_create_response": {"result": {
                "is_success": True, "order_list": {"number": [int(order_id)]},
            }}}
        if method == "aliexpress.ds.order.tracking.get":
            return {"aliexpress_ds_order_tracking_get_response": {"result": {
                "data": self.tracking.get(params["ae_order_id"], [])
            }}}
        raise AssertionError(f"unexpected method {method}")

    def count(self, method):
        return sum(1 for c in self.calls if c == method)


@pytest.fixture
def fake_aliexpress(monkeypatch):
    fake = FakeAliexpress()
    monkeypatch.setattr(aliexpress_client, "call", fake)
    # In-memory freight cache instead of Redis: same semantics (same key ->
    # same answer without calling AliExpress), isolated per test.
    store: dict = {}
    fake.cache = store

    async def _get(key):
        return store.get(key)

    async def _set(key, value, seconds):
        store[key] = value

    monkeypatch.setattr(aliexpress_client, "cache_get", _get)
    monkeypatch.setattr(aliexpress_client, "cache_set", _set)
    return fake


async def _user(db, organization_id, role_code="CUSTOMER"):
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


async def _connect(db, row, admin):
    """Credentials plus the token an OAuth round trip would leave; a PATCH can
    never set a token."""
    await aliexpress_service.update_settings(
        db, row=row, actor_user_id=admin.id, updates={"app_key": APP_KEY, "app_secret": APP_SECRET}
    )
    row.access_token = "tok-test"
    row.refresh_token = "rt-test"
    row.account_label = "sosnet-shop"
    await db.commit()
    return row


async def _shop(db, organization_id, admin, credit_percentage=None, **settings_updates):
    await organizations_service.update_settings(
        db, organization_id=organization_id, payload=OrganizationSettingsUpdate(bank_iban="IT66W0883330410000000015702")
    )
    row = await aliexpress_service.get_settings_row(db, organization_id=organization_id)
    await _connect(db, row, admin)
    await aliexpress_service.update_settings(
        db, row=row, actor_user_id=admin.id,
        updates={"enabled": True, "auto_forward": False, **settings_updates},
    )
    product = await aliexpress_service.import_product(
        db, row=row, actor_user_id=admin.id, product_id=PRODUCT_ID, name="Auricolari wireless", description=None,
        credit_discount_percentage=credit_percentage, markup_percentage=None, variant_ids=None, activate=True,
    )
    variants = (
        await db.execute(select(AliexpressVariant).where(AliexpressVariant.product_id == product.id))
    ).scalars().all()
    return row, product, {v.sku: v for v in variants}


async def _other_product(db, organization_id, admin, *, credit_percentage, price_cents=5000):
    """A second AliExpress product with its own SosnetCash percentage, since
    the fake catalog's variants all share one."""
    product = AliexpressProduct(
        organization_id=organization_id, aliexpress_product_id="1005009999999999",
        name="Lampada da scrivania", status="ACTIVE",
        credit_discount_percentage=credit_percentage, created_by_user_id=admin.id,
    )
    db.add(product)
    await db.flush()
    variant = AliexpressVariant(
        product_id=product.id, aliexpress_sku_id="99", sku_attr="14:99", sku="LMP-1",
        label="Bianco", source_price_amount=Decimal("20.00"), cost_amount=Decimal("8.00"),
        price_cents=price_cents, inventory=25, active=True, available_in_store=True,
    )
    db.add(variant)
    await db.commit()
    await db.refresh(variant)
    return product, variant


async def _otp(db, user_id):
    db.add(OtpCode(
        user_id=user_id, purpose=auth_service.WALLET_CREDIT_SPEND_OTP_PURPOSE, code_hash=hash_otp_code(OTP),
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
    ))
    await db.commit()


async def _card_ready(db, organization_id, monkeypatch):
    org = await db.get(Organization, organization_id)
    org.settings = {**(org.settings or {}), "stripe_secret_key": "sk_test_fake", "stripe_publishable_key": "pk_test_fake"}
    await db.commit()
    created = []

    class _Session:
        def __init__(self, n):
            self.id = f"cs_aliexpress_{n}_{uuid.uuid4().hex[:6]}"
            self.url = f"https://stripe.example/{self.id}"

    monkeypatch.setattr(
        stripe.checkout.Session, "create", staticmethod(lambda **p: created.append(p) or _Session(len(created)))
    )
    return created


async def _paid_order(db, organization_id, fake_aliexpress):
    admin = await _user(db, organization_id, "ADMIN")
    customer = await _user(db, organization_id)
    _row, _product, variants = await _shop(db, organization_id, admin)
    order = await aliexpress_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, variant_id=variants["EB-B"].id,
        quantity=1, address=ADDRESS, credit_applied_cents=0, payment_method="BANK_TRANSFER",
        actor_user_id=customer.id, otp_code=None, note=None,
    )
    await aliexpress_service.confirm_payment(
        db, organization_id=organization_id, order_id=order.id, actor_user_id=admin.id
    )
    return admin, customer, order


# --- Pricing and settings ----------------------------------------------------------------------


def test_price_starts_from_cost_or_price_is_marked_up_and_rounded_up():
    row = AliexpressSettings(
        currency_rate=Decimal(1), price_basis="COST", markup_percentage=100, markup_fixed_cents=0,
        price_rounding="90", shipping_mode="CUSTOMER_PAYS", shipping_minimum_cents=590,
    )
    assert pricing.sale_price_cents(cost=Decimal("10.00"), price=Decimal("24.00"), settings=row) == 2090
    # No dropshipping price: the list price is the base.
    assert pricing.sale_price_cents(cost=None, price=Decimal("25.00"), settings=row) == 5090
    row.price_basis = "PRICE"
    row.markup_percentage = 0
    row.price_rounding = "NONE"
    assert pricing.sale_price_cents(cost=Decimal("10.00"), price=Decimal("24.00"), settings=row) == 2400
    row.shipping_mode = "INCLUDED"
    assert pricing.sale_price_cents(cost=None, price=Decimal("24.00"), settings=row) == 2990
    # Shipping included: nothing is charged at checkout, whatever AliExpress asks.
    assert pricing.charged_shipping_cents(supplier_cents=1400, settings=row) == 0
    row.shipping_mode = "CUSTOMER_PAYS"
    # Customer pays the real cost, with the minimum as a floor.
    assert pricing.charged_shipping_cents(supplier_cents=0, settings=row) == 590
    assert pricing.charged_shipping_cents(supplier_cents=200, settings=row) == 590
    assert pricing.charged_shipping_cents(supplier_cents=590, settings=row) == 590
    assert pricing.charged_shipping_cents(supplier_cents=740, settings=row) == 740
    assert pricing.charged_shipping_cents(supplier_cents=1420, settings=row) == 1420
    row.currency_rate = Decimal("0.92")  # account answering in USD
    row.shipping_mode = "CUSTOMER_PAYS"
    assert pricing.sale_price_cents(cost=None, price=Decimal("10.00"), settings=row) == 920


def test_signature_is_the_gateway_s_own_recipe():
    """HMAC-SHA256 over name+value sorted by name, uppercase hex; the path is
    signed for system calls, not for business calls."""
    params = {"b": "2", "a": "1", "timestamp": "1700000000000"}
    expected = hmac.new(
        b"secret", b"a1b2timestamp1700000000000", hashlib.sha256
    ).hexdigest().upper()
    assert aliexpress_client.sign("secret", params) == expected
    with_path = hmac.new(
        b"secret", b"/auth/token/createa1b2timestamp1700000000000", hashlib.sha256
    ).hexdigest().upper()
    assert aliexpress_client.sign("secret", params, path="/auth/token/create") == with_path
    assert with_path != expected


@pytest.mark.asyncio
async def test_secrets_are_never_returned_and_new_shop_defaults(db, organization_id, fake_aliexpress):
    admin = await _user(db, organization_id, "ADMIN")
    row = await aliexpress_service.get_settings_row(db, organization_id=organization_id)
    assert row.markup_percentage == 100 and row.default_credit_percentage == rules.DEFAULT_CREDIT_PERCENTAGE
    assert row.ship_to_country == "IT" and row.target_currency == "EUR"
    # Nothing can be enabled before the account is linked.
    with pytest.raises(aliexpress_service.AliexpressValidationError):
        await aliexpress_service.update_settings(db, row=row, actor_user_id=admin.id, updates={"enabled": True})
    await aliexpress_service.update_settings(
        db, row=row, actor_user_id=admin.id, updates={"app_key": APP_KEY, "app_secret": APP_SECRET}
    )
    read = aliexpress_service.settings_read_dict(row)
    assert read["app_key"] == APP_KEY and read["app_secret_hint"] == "…wxyz" and read["connected"] is False
    assert APP_SECRET not in str(read)
    with pytest.raises(aliexpress_service.AliexpressValidationError):
        await aliexpress_service.update_settings(db, row=row, actor_user_id=admin.id, updates={"enabled": True})
    row.access_token = "tok-test"
    await db.commit()
    info = await aliexpress_service.test_connection(db, row=row)
    assert info["connected"] is True and info["sample_categories"] == ["Elettronica", "Casa"]
    assert info["last_connected_at"] is not None
    await aliexpress_service.update_settings(db, row=row, actor_user_id=admin.id, updates={"enabled": True})
    assert row.enabled
    # A new App Secret invalidates the existing authorisation.
    await aliexpress_service.update_settings(
        db, row=row, actor_user_id=admin.id, updates={"app_secret": "another_one"}
    )
    assert row.access_token is None and row.last_connected_at is None


@pytest.mark.asyncio
async def test_import_saves_variants_with_our_price_at_30_percent_sosnetcash(db, organization_id, fake_aliexpress):
    admin = await _user(db, organization_id, "ADMIN")
    row, product, variants = await _shop(db, organization_id, admin)
    assert product.credit_discount_percentage == 30
    assert product.description == "Great sound"  # plain text, no script
    assert product.vendor == "ACME Store"
    assert variants["EB-B"].price_cents == 2090  # 10 (ds price) +100% -> 20.90
    assert variants["EB-W"].price_cents == 5090  # no ds price: 25 +100%
    assert variants["EB-B"].label == "Colore: Nero"
    # Orders are placed with sku_attr, so it must survive the import.
    assert variants["EB-B"].sku_attr == "14:11"
    with pytest.raises(aliexpress_service.AliexpressValidationError):
        await aliexpress_service.import_product(
            db, row=row, actor_user_id=admin.id, product_id=PRODUCT_ID, name="x", description=None,
            credit_discount_percentage=None, markup_percentage=None, variant_ids=None, activate=True,
        )
    # SosnetCash may be raised, but never to 100%.
    with pytest.raises(aliexpress_service.AliexpressValidationError):
        await aliexpress_service.update_product(
            db, row=row, product=product, updates={"credit_discount_percentage": 100}, actor_user_id=admin.id
        )
    await aliexpress_service.update_product(
        db, row=row, product=product, updates={"credit_discount_percentage": 99}, actor_user_id=admin.id
    )
    # Changing settings re-prices products.
    await aliexpress_service.update_settings(db, row=row, actor_user_id=admin.id, updates={"markup_percentage": 50})
    await db.refresh(variants["EB-B"])
    assert variants["EB-B"].price_cents == 1590


@pytest.mark.asyncio
async def test_catalog_search_and_freight_survive_both_nestings(db, organization_id, fake_aliexpress):
    admin = await _user(db, organization_id, "ADMIN")
    row = await aliexpress_service.get_settings_row(db, organization_id=organization_id)
    await _connect(db, row, admin)

    page = await aliexpress_service.search_catalog(db, row=row, keyword="earbuds", cursor=None)
    assert len(page["items"]) == 1 and page["next_cursor"] is None
    assert page["items"][0]["product_id"] == PRODUCT_ID
    assert page["items"][0]["min_price_cents"] == 2090 and page["items"][0]["already_imported"] is False
    assert fake_aliexpress.params[-1]["countryCode"] == "IT" and fake_aliexpress.params[-1]["currency"] == "EUR"
    # The alternative documented nesting must not read as empty.
    fake_aliexpress.search_shape = "alternative"
    again = await aliexpress_service.search_catalog(db, row=row, keyword="earbuds", cursor="2")
    assert len(again["items"]) == 1
    assert fake_aliexpress.params[-1]["pageIndex"] == "2"

    freight = await aliexpress_service.freight_options(
        db, row=row, product_id=PRODUCT_ID, sku_id="11", quantity=2
    )
    option = freight["options"][0]
    assert option["shipping_fee_cents"] == 499 and option["max_days"] == 20
    assert option["company"] == "Cainiao"

    # Imported products are flagged in later searches.
    await aliexpress_service.import_product(
        db, row=row, actor_user_id=admin.id, product_id=PRODUCT_ID, name="Auricolari", description=None,
        credit_discount_percentage=None, markup_percentage=None, variant_ids=None, activate=True,
    )
    fake_aliexpress.search_shape = "documented"
    page = await aliexpress_service.search_catalog(db, row=row, keyword="earbuds", cursor=None)
    assert page["items"][0]["already_imported"] is True


# --- Checkout ---------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_checkout_with_sosnetcash_never_the_whole_price(db, organization_id, fake_aliexpress):
    admin = await _user(db, organization_id, "ADMIN")
    customer = await _user(db, organization_id)
    _row, _product, variants = await _shop(db, organization_id, admin, credit_percentage=99)
    wallet = await wallet_service.get_or_create_wallet(db, organization_id=organization_id, user_id=customer.id)
    await wallet_service.credit_wallet(
        db, organization_id=organization_id, wallet_id=wallet.id, amount_cents=10000, type_="ADMIN_CREDIT",
        actor_user_id=admin.id, idempotency_key=str(uuid.uuid4()),
    )
    quote = await aliexpress_service.get_quote(
        db, organization_id=organization_id, customer_user_id=customer.id, variant_id=variants["EB-B"].id, quantity=1
    )
    assert quote["amount_cents"] == _con_iva(2090) + 590
    assert quote["max_creditable_cents"] < quote["amount_cents"]
    with pytest.raises(aliexpress_service.AliexpressValidationError):
        await aliexpress_service.get_quote(
            db, organization_id=organization_id, customer_user_id=customer.id, variant_id=variants["EB-W"].id,
            quantity=1,
        )
    # Even a product stored at 100% is never fully payable in SosnetCash.
    assert aliexpress_service.max_creditable_cents(amount_cents=1000, credit_discount_percentage=100) == 990
    with pytest.raises(aliexpress_service.InvalidOtpError):
        await aliexpress_service.create_order(
            db, organization_id=organization_id, customer_user_id=customer.id, variant_id=variants["EB-B"].id,
            quantity=1, address=ADDRESS, credit_applied_cents=1000, payment_method="BANK_TRANSFER",
            actor_user_id=customer.id, otp_code="000000", note=None,
        )
    await _otp(db, customer.id)
    order = await aliexpress_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, variant_id=variants["EB-B"].id,
        quantity=1, address=ADDRESS, credit_applied_cents=1000, payment_method="BANK_TRANSFER",
        actor_user_id=customer.id, otp_code=OTP, note=None,
    )
    # 5% of what remains after SosnetCash.
    residuo = order.amount_cents - order.credit_applied_cents
    assert order.status == "AWAITING_PAYMENT"
    assert order.bank_transfer_discount_cents == (residuo * 5 + 50) // 100
    txn = await db.get(wallet_service.WalletTransaction, order.credit_debit_transaction_id)
    assert txn.reference_aliexpress_order_id == order.id

    await aliexpress_service.confirm_payment(
        db, organization_id=organization_id, order_id=order.id, actor_user_id=admin.id
    )
    movements = await accounting_service.list_my_movements(db, organization_id=organization_id, user_id=customer.id)
    euro_rows = [m for m in movements if m["kind"] == "ORDER_PAYMENT" and m["order_id"] == order.id]
    assert euro_rows and euro_rows[0]["amount_cents"] == aliexpress_service.amount_due_cents(order)
    wallet_rows = [m for m in movements if m["kind"] == "WALLET" and m["order_id"] == order.id]
    assert wallet_rows and wallet_rows[0]["product_name"] == "Auricolari wireless"
    detail = await accounting_details._order_detail(
        db, organization_id=organization_id, entity_id=order.id, owner_user_id=customer.id
    )
    assert detail["subtitle"].endswith("Marketplace 3")
    assert "AliExpress" not in str(detail)


@pytest.mark.asyncio
async def test_bank_transfer_discount_frozen_and_recomputed_on_switch(
    db, organization_id, fake_aliexpress, monkeypatch
):
    from app.modules.payments import service as payments_service

    created = await _card_ready(db, organization_id, monkeypatch)
    admin = await _user(db, organization_id, "ADMIN")
    customer = await _user(db, organization_id)
    _row, _product, variants = await _shop(db, organization_id, admin)
    quote = await aliexpress_service.get_quote(
        db, organization_id=organization_id, customer_user_id=customer.id, variant_id=variants["EB-B"].id, quantity=1
    )
    totale = quote["amount_cents"]
    sconto = (totale * 5 + 50) // 100
    assert quote["bank_transfer_discount_percentage"] == 5
    assert quote["bank_transfer_amount_cents"] == totale - sconto

    order = await aliexpress_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, variant_id=variants["EB-B"].id,
        quantity=1, address=ADDRESS, credit_applied_cents=0, payment_method="CARD",
        actor_user_id=customer.id, otp_code=None, note=None,
    )
    assert order.bank_transfer_discount_cents == 0 and aliexpress_service.amount_due_cents(order) == totale
    assert created[-1]["line_items"][0]["price_data"]["unit_amount"] == totale
    assert created[-1]["metadata"]["kind"] == "aliexpress_order"

    await aliexpress_service.change_payment_method(
        db, organization_id=organization_id, order=order, new_payment_method="BANK_TRANSFER"
    )
    assert order.bank_transfer_discount_cents == sconto
    assert aliexpress_service.amount_due_cents(order) == totale - sconto
    # A percentage change applies to the customer's next choice.
    await rules.update_config(db, organization_id=organization_id, labels=None, bank_transfer_discount_percentage=10)
    await aliexpress_service.change_payment_method(
        db, organization_id=organization_id, order=order, new_payment_method="CARD"
    )
    await aliexpress_service.change_payment_method(
        db, organization_id=organization_id, order=order, new_payment_method="BANK_TRANSFER"
    )
    assert order.bank_transfer_discount_cents == (totale * 10 + 50) // 100
    # Switching to card: full price, no discount.
    await payments_service.create_checkout_session_for_aliexpress_order(
        db, organization_id=organization_id, order=order, success_url="https://x/ok", cancel_url="https://x/ko",
    )
    await db.refresh(order)
    assert order.payment_method == "CARD" and order.bank_transfer_discount_cents == 0
    assert created[-1]["line_items"][0]["price_data"]["unit_amount"] == totale

    paid = await aliexpress_service.mark_paid_via_stripe(
        db, organization_id=organization_id, stripe_checkout_session_id=order.stripe_checkout_session_id
    )
    assert paid.status == "PAID"
    movements = await accounting_service.list_my_movements(db, organization_id=organization_id, user_id=customer.id)
    euro_rows = [m for m in movements if m["kind"] == "ORDER_PAYMENT" and m["order_id"] == order.id]
    assert euro_rows and euro_rows[0]["amount_cents"] == aliexpress_service.amount_due_cents(order)


@pytest.mark.asyncio
async def test_webhook_marks_the_aliexpress_order_paid(db, organization_id, fake_aliexpress, monkeypatch):
    from app.modules.payments import service as payments_service

    await _card_ready(db, organization_id, monkeypatch)
    admin = await _user(db, organization_id, "ADMIN")
    customer = await _user(db, organization_id)
    _row, _product, variants = await _shop(db, organization_id, admin)
    order = await aliexpress_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, variant_id=variants["EB-B"].id,
        quantity=1, address=ADDRESS, credit_applied_cents=0, payment_method="CARD",
        actor_user_id=customer.id, otp_code=None, note=None,
    )
    import json
    import time

    secret = "whsec_aliexpress_test"
    org = await db.get(Organization, organization_id)
    org.settings = {**org.settings, "stripe_webhook_secret": secret}
    await db.commit()
    body = json.dumps({
        "id": f"evt_{uuid.uuid4().hex[:10]}", "object": "event", "type": "checkout.session.completed",
        "data": {"object": {
            # Older link (from the confirmation email): only the metadata identifies the order.
            "id": "cs_old_email_link", "object": "checkout.session",
            "metadata": {"kind": "aliexpress_order", "aliexpress_order_id": str(order.id)},
        }},
    }).encode()
    timestamp = int(time.time())
    signature = hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()
    await payments_service.handle_webhook_event(
        db, organization_id=organization_id, payload=body, sig_header=f"t={timestamp},v1={signature}"
    )
    await db.refresh(order)
    assert order.status == "PAID"


# --- Placing orders with the supplier ---------------------------------------------------------


@pytest.mark.asyncio
async def test_paid_order_is_placed_at_the_supplier_once(db, organization_id, fake_aliexpress):
    admin, _customer, order = await _paid_order(db, organization_id, fake_aliexpress)
    order = await aliexpress_service.forward_order(
        db, organization_id=organization_id, order_id=order.id, actor_user_id=admin.id
    )
    assert order.fulfillment_status == "SENT" and order.aliexpress_order_id == "3001"
    import json

    request = json.loads(fake_aliexpress.params[-1]["param_place_order_request4_open_api_d_t_o"])
    assert request["product_items"] == [{
        "product_count": 1, "product_id": PRODUCT_ID, "sku_attr": "14:11",
        "order_memo": aliexpress_service.order_number(order),
    }]
    assert request["logistics_address"]["city"] == "Milano"
    assert request["logistics_address"]["country"] == "IT"
    # Only digits reach the supplier; the prefix is sent separately.
    assert request["logistics_address"]["mobile_no"] == "3331234567"
    assert request["logistics_address"]["phone_country"] == "+39"
    # Deterministic reference, so a resubmission is the same order.
    assert request["out_order_id"] == aliexpress_service.out_order_id(order) == order.out_order_id
    with pytest.raises(aliexpress_service.AliexpressValidationError):
        await aliexpress_service.forward_order(
            db, organization_id=organization_id, order_id=order.id, actor_user_id=admin.id
        )
    assert fake_aliexpress.orders_created == 1


@pytest.mark.asyncio
async def test_lost_answer_is_never_retried_by_a_machine(db, organization_id, fake_aliexpress):
    """AliExpress cannot be asked whether it already has an order, so a lost
    response halts the automatic flow: the order (and payment) may exist, and
    only a person may decide to resend."""
    from app.modules.notifications.models import Notification

    admin, _customer, order = await _paid_order(db, organization_id, fake_aliexpress)
    fake_aliexpress.fail_create_once = "lost"
    order = await aliexpress_service.forward_order(
        db, organization_id=organization_id, order_id=order.id, actor_user_id=admin.id
    )
    assert order.fulfillment_status == "ERROR" and order.last_error_kind == "TEMPORARY"
    assert order.next_retry_at is None
    assert order.out_order_id  # saved before the call so the admin can search for it
    alerts = list((await db.execute(
        select(Notification).where(Notification.type == "ALIEXPRESS_ORDER_FAILED")
    )).scalars())
    assert alerts and order.out_order_id in (alerts[0].body or "")
    # The retry job skips it; the admin can still force it.
    assert await aliexpress_service.retry_due_orders(db, organization_id=organization_id) == 0
    assert fake_aliexpress.orders_created == 1


@pytest.mark.asyncio
async def test_an_answer_without_an_order_number_is_treated_as_lost(db, organization_id, fake_aliexpress):
    admin, _customer, order = await _paid_order(db, organization_id, fake_aliexpress)
    fake_aliexpress.create_without_number = True
    order = await aliexpress_service.forward_order(
        db, organization_id=organization_id, order_id=order.id, actor_user_id=admin.id
    )
    assert order.fulfillment_status == "ERROR" and order.aliexpress_order_id is None
    assert order.next_retry_at is None and "numero d'ordine" in order.forward_error


@pytest.mark.asyncio
async def test_supplier_refusal_alerts_staff_and_is_not_retried(db, organization_id, fake_aliexpress):
    admin, _customer, order = await _paid_order(db, organization_id, fake_aliexpress)
    fake_aliexpress.fail_create = "product is out of stock"
    order = await aliexpress_service.forward_order(
        db, organization_id=organization_id, order_id=order.id, actor_user_id=admin.id
    )
    assert order.fulfillment_status == "ERROR" and order.last_error_kind == "VALIDATION"
    assert order.next_retry_at is None and "out of stock" in order.forward_error


@pytest.mark.asyncio
async def test_a_variant_without_sku_attr_is_refused_before_any_call(db, organization_id, fake_aliexpress):
    admin, _customer, order = await _paid_order(db, organization_id, fake_aliexpress)
    variant = await db.get(AliexpressVariant, order.aliexpress_variant_id)
    variant.sku_attr = None
    await db.commit()
    order = await aliexpress_service.forward_order(
        db, organization_id=organization_id, order_id=order.id, actor_user_id=admin.id
    )
    assert order.fulfillment_status == "ERROR" and fake_aliexpress.orders_created == 0
    assert "risincronizza" in order.forward_error
    # Our own refusal, not the supplier's: nothing to retry until the admin
    # syncs the product again.
    assert order.last_error_kind == "VALIDATION" and order.next_retry_at is None


@pytest.mark.asyncio
async def test_tracking_and_delivery_reach_the_customer(db, organization_id, fake_aliexpress):
    from app.modules.notifications.models import Notification

    admin, customer, order = await _paid_order(db, organization_id, fake_aliexpress)
    order = await aliexpress_service.forward_order(
        db, organization_id=organization_id, order_id=order.id, actor_user_id=admin.id
    )
    fake_aliexpress.tracking[order.aliexpress_order_id] = [{
        "mail_no": "LX123IT", "official_website": "https://track/LX123IT",
        "logistics_service_name": "Poste", "logistics_status": "IN_TRANSIT",
        "tracking_detail_line_list": [{"event_desc": "Shipped from warehouse"}],
    }]
    assert await aliexpress_service.sync_orders(db, organization_id=organization_id) == 1
    await db.refresh(order)
    assert order.fulfillment_status == "SHIPPED" and order.tracking_number == "LX123IT"
    assert order.tracking_company == "Poste" and order.aliexpress_order_status == "IN_TRANSIT"
    read = await aliexpress_service.order_read_dict(db, order, admin=False)
    assert read["delivery_status"] == "SHIPPED" and read["tracking_url"] == "https://track/LX123IT"
    fake_aliexpress.tracking[order.aliexpress_order_id][0]["tracking_detail_line_list"].append(
        {"event_desc": "Delivered / consegnato al destinatario"}
    )
    await aliexpress_service.sync_orders(db, organization_id=organization_id)
    await db.refresh(order)
    assert order.fulfillment_status == "DELIVERED" and order.delivered_at is not None
    notes = list((await db.execute(
        select(Notification).where(Notification.recipient_user_id == customer.id, Notification.type == "ORDER_SHIPPED")
    )).scalars())
    assert len(notes) == 2


@pytest.mark.asyncio
async def test_retry_job_sends_paid_orders_that_were_never_sent(db, organization_id, fake_aliexpress):
    admin, _customer, order = await _paid_order(db, organization_id, fake_aliexpress)
    row = await aliexpress_service.get_settings_row(db, organization_id=organization_id)
    await aliexpress_service.update_settings(db, row=row, actor_user_id=admin.id, updates={"auto_forward": True})
    order.paid_at = order.paid_at - timedelta(minutes=5)
    await db.commit()
    assert await aliexpress_service.retry_due_orders(db, organization_id=organization_id) == 1
    await db.refresh(order)
    assert order.fulfillment_status == "SENT"
    assert await aliexpress_service.retry_due_orders(db, organization_id=organization_id) == 0
    assert fake_aliexpress.orders_created == 1


@pytest.mark.asyncio
async def test_switched_off_shop_sells_nothing(db, organization_id, fake_aliexpress):
    admin = await _user(db, organization_id, "ADMIN")
    customer = await _user(db, organization_id)
    row, _product, variants = await _shop(db, organization_id, admin)
    await aliexpress_service.update_settings(db, row=row, actor_user_id=admin.id, updates={"enabled": False})
    with pytest.raises(aliexpress_service.AliexpressValidationError):
        await aliexpress_service.get_quote(
            db, organization_id=organization_id, customer_user_id=customer.id, variant_id=variants["EB-B"].id,
            quantity=1,
        )


@pytest.mark.asyncio
async def test_a_product_taken_off_sale_stops_being_sold(db, organization_id, fake_aliexpress, monkeypatch):
    admin = await _user(db, organization_id, "ADMIN")
    row, product, variants = await _shop(db, organization_id, admin)
    original = fake_aliexpress.__call__

    async def offline(settings, method, params=None):
        body = await original(settings, method, params)
        if method == "aliexpress.ds.product.get":
            body["aliexpress_ds_product_get_response"]["result"]["ae_item_base_info_dto"][
                "product_status_type"
            ] = "offline"
        return body

    monkeypatch.setattr(aliexpress_client, "call", offline)
    product = await aliexpress_service.sync_product(db, row=row, product=product)
    assert product.sync_error and "non è più in vendita" in product.sync_error
    await db.refresh(variants["EB-B"])
    assert variants["EB-B"].available_in_store is False
    assert await aliexpress_service.product_customer_dict(
        db, product, settings=row, bank_transfer_discount_percentage=5
    ) is None


# --- Signing, tokens and account authorisation -------------------------------------------------


@pytest.mark.asyncio
async def test_token_is_created_refreshed_and_carried_on_every_call(db, organization_id, monkeypatch):
    """Code -> token exchange, renewal shortly before expiry, and a single
    retry when the gateway rejects a token that expired early."""
    admin = await _user(db, organization_id, "ADMIN")
    row = await aliexpress_service.get_settings_row(db, organization_id=organization_id)
    await aliexpress_service.update_settings(
        db, row=row, actor_user_id=admin.id, updates={"app_key": APP_KEY, "app_secret": APP_SECRET}
    )

    posts: list[tuple[str, dict]] = []
    refuse_next = {"value": False}

    async def fake_post(url, params):
        posts.append((url, dict(params)))
        if url.endswith("/auth/token/create"):
            return {
                "access_token": "at-1", "refresh_token": "rt-1", "expires_in": 86400,
                "user_nick": "sosnet-shop",
            }
        if url.endswith("/auth/token/refresh"):
            return {"access_token": f"at-{len([p for p in posts if 'refresh' in p[0]]) + 1}", "expires_in": 86400}
        if refuse_next["value"]:
            refuse_next["value"] = False
            return {"code": "27", "message": "Invalid session", "sub_message": "token is expired"}
        return {"aliexpress_ds_category_get_response": {"result": {"categories": []}}}

    monkeypatch.setattr(aliexpress_client, "_post", fake_post)

    await aliexpress_client.create_token(row, code="the-code")
    assert row.access_token == "at-1" and row.refresh_token == "rt-1"
    assert row.account_label == "sosnet-shop" and row.token_expires_at is not None
    # System calls sign the path.
    url, params = posts[-1]
    assert url == "https://api-sg.aliexpress.com/rest/auth/token/create"
    assert params["sign"] == aliexpress_client.sign(
        APP_SECRET, {k: v for k, v in params.items() if k != "sign"}, path="/auth/token/create"
    )

    await aliexpress_client.category_get(row, language="it")
    url, params = posts[-1]
    assert url == "https://api-sg.aliexpress.com/sync"
    assert params["method"] == "aliexpress.ds.category.get" and params["session"] == "at-1"
    # Business calls sign without the path.
    assert params["sign"] == aliexpress_client.sign(
        APP_SECRET, {k: v for k, v in params.items() if k != "sign"}
    )

    # Rejected token -> one transparent refresh and retry.
    refuse_next["value"] = True
    await aliexpress_client.category_get(row, language="it")
    assert row.access_token == "at-2"
    assert posts[-2][0].endswith("/auth/token/refresh")

    # Nearly expired -> renewed before the call.
    row.token_expires_at = datetime.now(UTC) + timedelta(minutes=1)
    await aliexpress_client.category_get(row, language="it")
    assert row.access_token == "at-3" and posts[-1][1]["session"] == "at-3"

    # No refresh token: the admin must link the account again.
    row.refresh_token = None
    row.token_expires_at = datetime.now(UTC) - timedelta(minutes=1)
    with pytest.raises(aliexpress_client.AliexpressApiError) as err:
        await aliexpress_client.category_get(row, language="it")
    assert err.value.kind == "AUTHENTICATION" and "ricollega" in str(err.value)


@pytest.mark.asyncio
async def test_authorisation_round_trip_is_signed_and_expires(db, organization_id, monkeypatch):
    admin = await _user(db, organization_id, "ADMIN")
    row = await aliexpress_service.get_settings_row(db, organization_id=organization_id)
    with pytest.raises(aliexpress_client.AliexpressNotConfiguredError):
        aliexpress_service.authorize_url(row)
    await aliexpress_service.update_settings(
        db, row=row, actor_user_id=admin.id, updates={"app_key": APP_KEY, "app_secret": APP_SECRET}
    )
    url = aliexpress_service.authorize_url(row)
    import urllib.parse

    query = dict(urllib.parse.parse_qsl(url.split("?", 1)[1]))
    assert url.startswith("https://api-sg.aliexpress.com/oauth/authorize?")
    assert query["client_id"] == APP_KEY
    assert query["redirect_uri"].endswith("/api/aliexpress/oauth/callback")
    state = query["state"]
    assert aliexpress_service.oauth_state_settings_id(state) == row.id
    assert aliexpress_service.oauth_state_ok(row, state)
    assert not aliexpress_service.oauth_state_ok(row, state[:-1] + ("0" if state[-1] != "0" else "1"))
    assert not aliexpress_service.oauth_state_ok(row, "nonsense")
    # Older than half an hour: no longer ours.
    old = f"{row.id}.{int(datetime.now(UTC).timestamp()) - 3600}"
    old_mac = hmac.new(APP_SECRET.encode(), old.encode(), hashlib.sha256).hexdigest()
    assert not aliexpress_service.oauth_state_ok(row, f"{old}.{old_mac}")

    async def fake_post(url, params):
        return {"access_token": "at-callback", "refresh_token": "rt-callback", "expires_in": 86400}

    monkeypatch.setattr(aliexpress_client, "_post", fake_post)
    await aliexpress_service.complete_authorisation(db, row=row, code="the-code")
    assert row.access_token == "at-callback" and row.last_connected_at is not None
    assert aliexpress_service.settings_read_dict(row)["connected"] is True


@pytest.mark.asyncio
async def test_a_gateway_error_reaches_the_administrator_with_its_own_words(db, organization_id, monkeypatch):
    admin = await _user(db, organization_id, "ADMIN")
    row = await aliexpress_service.get_settings_row(db, organization_id=organization_id)
    await aliexpress_service.update_settings(
        db, row=row, actor_user_id=admin.id, updates={"app_key": APP_KEY, "app_secret": APP_SECRET}
    )
    row.access_token = "tok"
    await db.commit()

    async def fake_post(url, params):
        return {"code": "50000", "message": "remote service error", "sub_message": "ApiCallLimit"}

    monkeypatch.setattr(aliexpress_client, "_post", fake_post)
    with pytest.raises(aliexpress_client.AliexpressApiError) as err:
        await aliexpress_client.category_get(row)
    assert "remote service error" in str(err.value) and "ApiCallLimit" in str(err.value)
    assert err.value.kind == "TEMPORARY"


def test_unwrap_and_first_read_json_strings_and_alternative_nestings():
    body = {"resp": '{"result": {"items": [1, 2]}}'}
    assert aliexpress_client.unwrap(body, "resp", "result", "items") == [1, 2]
    assert aliexpress_client.unwrap(body, "resp", "nope") is None
    assert aliexpress_client.first(
        {"b": {"x": 1}}, ("a", "x"), ("b", "x")
    ) == 1
    # An empty answer is not an answer: `first` keeps looking.
    assert aliexpress_client.first({"a": {"x": []}, "b": {"x": 3}}, ("a", "x"), ("b", "x")) == 3
    assert aliexpress_client.items_of({"ae_item_sku_info_d_t_o": [1]}, "ae_item_sku_info_d_t_o") == [1]
    assert aliexpress_client.items_of({"only": [1, 2]}) == [1, 2]
    assert aliexpress_client.items_of([1, 2]) == [1, 2]
    assert aliexpress_client.items_of(None) == []


# --- VAT ----------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_vat_is_frozen_with_the_discount_and_the_margin_is_net_of_it(
    db, organization_id, fake_aliexpress, monkeypatch
):
    """VAT is added on the goods at full price and frozen on the order;
    neither the bank-transfer discount nor SosnetCash changes it, since they
    reduce the payment, not the price. Margin is measured net of VAT and
    supplier shipping."""
    from app.modules.payments import service as payments_service

    await _card_ready(db, organization_id, monkeypatch)
    admin = await _user(db, organization_id, "ADMIN")
    customer = await _user(db, organization_id)
    _row, _product, variants = await _shop(db, organization_id, admin)

    order = await aliexpress_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, variant_id=variants["EB-B"].id,
        quantity=1, address=ADDRESS, credit_applied_cents=0, payment_method="BANK_TRANSFER",
        actor_user_id=customer.id, otp_code=None, note=None,
    )
    merce = order.unit_price_cents * order.quantity
    assert order.vat_percentage == 22
    assert order.vat_mode == "ADDED"
    # 22% on top of the goods; the total contains both.
    assert order.vat_amount_cents == 460
    assert order.amount_cents == merce + 460 + order.shipping_cents
    assert order.bank_transfer_discount_cents == (order.amount_cents * 5 + 50) // 100
    iva_congelata = order.vat_amount_cents

    # Changing payment method changes the amount due, not the tax.
    await aliexpress_service.change_payment_method(
        db, organization_id=organization_id, order=order, new_payment_method="CARD"
    )
    assert order.bank_transfer_discount_cents == 0
    assert order.vat_amount_cents == iva_congelata
    assert aliexpress_service.amount_due_cents(order) == order.amount_cents

    read = await aliexpress_service.order_read_dict(db, order, admin=False)
    assert read["vat_percentage"] == 22 and read["vat_amount_cents"] == iva_congelata
    assert read["vat_mode"] == "ADDED"
    admin_read = await aliexpress_service.order_read_dict(db, order, admin=True)
    # Margin excludes VAT and the supplier shipping cost.
    assert admin_read["supplier_shipping_cents"] == 499
    assert admin_read["estimated_margin_cents"] == (
        aliexpress_service.taxable_base_cents(order)
        - admin_read["supplier_cost_cents"] - admin_read["supplier_shipping_cents"]
    )
    # Shipping margin alone: charged 590, paid 499.
    assert admin_read["shipping_margin_cents"] == 590 - 499

    # A rate change applies to new orders only, whatever the payment method switches.
    await rules.update_config(
        db, organization_id=organization_id, labels=None, bank_transfer_discount_percentage=None, vat_percentage=10
    )
    for metodo in ("BANK_TRANSFER", "CARD"):
        await aliexpress_service.change_payment_method(
            db, organization_id=organization_id, order=order, new_payment_method=metodo
        )
        assert order.vat_percentage == 22 and order.vat_amount_cents == iva_congelata

    await payments_service.create_checkout_session_for_aliexpress_order(
        db, organization_id=organization_id, order=order, success_url="https://x/ok", cancel_url="https://x/ko",
    )
    await db.refresh(order)
    assert order.bank_transfer_discount_cents == 0
    assert order.vat_amount_cents == iva_congelata

    # New orders take the new rate.
    nuovo = await aliexpress_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, variant_id=variants["EB-B"].id,
        quantity=1, address=ADDRESS, credit_applied_cents=0, payment_method="BANK_TRANSFER",
        actor_user_id=customer.id, otp_code=None, note=None,
    )
    assert nuovo.vat_percentage == 10


@pytest.mark.asyncio
async def test_sosnetcash_does_not_shrink_the_vat_and_a_zero_rate_switches_it_off(
    db, organization_id, fake_aliexpress
):
    """SosnetCash is a payment method, not a discount: it does not reduce the
    VAT. A zero rate switches VAT off."""
    admin = await _user(db, organization_id, "ADMIN")
    customer = await _user(db, organization_id)
    _row, _product, variants = await _shop(db, organization_id, admin, credit_percentage=99)
    wallet = await wallet_service.get_or_create_wallet(db, organization_id=organization_id, user_id=customer.id)
    await wallet_service.credit_wallet(
        db, organization_id=organization_id, wallet_id=wallet.id, amount_cents=1000, type_="ADMIN_CREDIT",
        actor_user_id=admin.id, idempotency_key=str(uuid.uuid4()),
    )
    await _otp(db, customer.id)
    order = await aliexpress_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, variant_id=variants["EB-B"].id,
        quantity=1, address=ADDRESS, credit_applied_cents=1000, payment_method="BANK_TRANSFER",
        actor_user_id=customer.id, otp_code=OTP, note=None,
    )
    # Bank-transfer discount is 5% of the residual after SosnetCash; the
    # taxable base stays the full goods value.
    assert order.bank_transfer_discount_cents == ((order.amount_cents - order.credit_applied_cents) * 5 + 50) // 100
    merce = order.unit_price_cents * order.quantity
    assert order.vat_amount_cents == 460  # 22% of 20.90
    assert order.amount_cents == merce + 460 + order.shipping_cents

    await rules.update_config(
        db, organization_id=organization_id, labels=None, bank_transfer_discount_percentage=None, vat_percentage=0
    )
    plain = await aliexpress_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, variant_id=variants["EB-B"].id,
        quantity=1, address=ADDRESS, credit_applied_cents=0, payment_method="BANK_TRANSFER",
        actor_user_id=customer.id, otp_code=None, note=None,
    )
    assert plain.vat_percentage == 0 and plain.vat_amount_cents == 0


# --- Cart ------------------------------------------------------------------------


async def _two_in_stock(db, variants):
    """The fake catalog has one SKU in stock; restock the second for the cart."""
    variants["EB-W"].inventory = 10
    await db.commit()
    return variants["EB-B"], variants["EB-W"]


@pytest.mark.asyncio
async def test_cart_prices_every_line_and_charges_shipping_once(db, organization_id, fake_aliexpress):
    admin = await _user(db, organization_id, "ADMIN")
    customer = await _user(db, organization_id)
    _row, _product, variants = await _shop(db, organization_id, admin)
    black, white = await _two_in_stock(db, variants)

    await carts_service.add_item(
        db, organization_id=organization_id, customer_user_id=customer.id, shop="aliexpress",
        variant_id=black.id, quantity=2,
    )
    await carts_service.add_item(
        db, organization_id=organization_id, customer_user_id=customer.id, shop="aliexpress",
        variant_id=white.id, quantity=1,
    )
    summary = await carts_service.summary(
        db, organization_id=organization_id, customer_user_id=customer.id
    )
    section = summary["sections"][0]
    assert summary["item_count"] == 3
    assert [i["quantity"] for i in section["items"]] == [2, 1]
    items_cents = 2 * black.price_cents + white.price_cents
    # One shipping per order, not per line.
    assert section["items_cents"] == items_cents
    assert section["amount_cents"] == _con_iva(items_cents) + section["shipping_cents"]
    assert section["purchasable"] is True and section["problems"] == []


@pytest.mark.asyncio
async def test_adding_the_same_article_twice_raises_the_quantity(db, organization_id, fake_aliexpress):
    admin = await _user(db, organization_id, "ADMIN")
    customer = await _user(db, organization_id)
    _row, _product, variants = await _shop(db, organization_id, admin)
    for _ in range(3):
        await carts_service.add_item(
            db, organization_id=organization_id, customer_user_id=customer.id, shop="aliexpress",
            variant_id=variants["EB-B"].id, quantity=1,
        )
    summary = await carts_service.summary(db, organization_id=organization_id, customer_user_id=customer.id)
    assert len(summary["sections"][0]["items"]) == 1
    assert summary["item_count"] == 3


@pytest.mark.asyncio
async def test_cart_refuses_an_article_that_is_out_of_stock(db, organization_id, fake_aliexpress):
    admin = await _user(db, organization_id, "ADMIN")
    customer = await _user(db, organization_id)
    _row, _product, variants = await _shop(db, organization_id, admin)
    with pytest.raises(carts_service.CartValidationError):
        await carts_service.add_item(
            db, organization_id=organization_id, customer_user_id=customer.id, shop="aliexpress",
            variant_id=variants["EB-W"].id, quantity=1,
        )


@pytest.mark.asyncio
async def test_cart_still_opens_when_a_line_became_unavailable(db, organization_id, fake_aliexpress):
    admin = await _user(db, organization_id, "ADMIN")
    customer = await _user(db, organization_id)
    _row, _product, variants = await _shop(db, organization_id, admin)
    black, white = await _two_in_stock(db, variants)
    for variant in (black, white):
        await carts_service.add_item(
            db, organization_id=organization_id, customer_user_id=customer.id, shop="aliexpress",
            variant_id=variant.id, quantity=1,
        )
    white.inventory = 0  # sold out after being added to the cart
    await db.commit()

    summary = await carts_service.summary(db, organization_id=organization_id, customer_user_id=customer.id)
    section = summary["sections"][0]
    # The cart still opens and flags the offending line, so the customer
    # knows what to remove.
    assert section["purchasable"] is False
    assert len(section["problems"]) == 1
    available = {i["variant_id"]: i["available"] for i in section["items"]}
    assert available[black.id] is True and available[white.id] is False


@pytest.mark.asyncio
async def test_cart_checkout_makes_one_order_with_every_line_and_empties_the_cart(
    db, organization_id, fake_aliexpress
):
    admin = await _user(db, organization_id, "ADMIN")
    customer = await _user(db, organization_id)
    _row, _product, variants = await _shop(db, organization_id, admin)
    black, white = await _two_in_stock(db, variants)
    for variant, qty in ((black, 2), (white, 1)):
        await carts_service.add_item(
            db, organization_id=organization_id, customer_user_id=customer.id, shop="aliexpress",
            variant_id=variant.id, quantity=qty,
        )
    _cart, lines = await carts_service.checkout_lines(
        db, customer_user_id=customer.id, shop="aliexpress"
    )

    order = await aliexpress_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, lines=lines, address=ADDRESS,
        credit_applied_cents=0, payment_method="BANK_TRANSFER", actor_user_id=customer.id,
        otp_code=None, note=None,
    )
    items = await aliexpress_service.order_items(db, order)
    assert len(items) == 2
    assert {i.aliexpress_variant_id for i in items} == {black.id, white.id}
    assert order.amount_cents == _con_iva(2 * black.price_cents + white.price_cents) + order.shipping_cents
    # Product name is frozen on the line: renames do not rewrite orders.
    assert all(i.product_name for i in items)

    # The AliExpress request body carries every line.
    request = await aliexpress_service._order_request(db, order)
    assert len(request["product_items"]) == 2
    assert {p["product_count"] for p in request["product_items"]} == {2, 1}

    await carts_service.clear(db, customer_user_id=customer.id, shop="aliexpress")
    empty = await carts_service.summary(db, organization_id=organization_id, customer_user_id=customer.id)
    assert empty["sections"] == [] and empty["item_count"] == 0


@pytest.mark.asyncio
async def test_sosnetcash_cap_on_one_line_is_the_percentage_of_that_product(db, organization_id, fake_aliexpress):
    """With a single line the cap is that product's percentage of its value:
    the cart rule applied to one item."""
    admin = await _user(db, organization_id, "ADMIN")
    customer = await _user(db, organization_id)
    _row, product, variants = await _shop(db, organization_id, admin, credit_percentage=30)
    quote = await aliexpress_service.get_quote(
        db, organization_id=organization_id, customer_user_id=customer.id,
        variant_id=variants["EB-B"].id, quantity=2,
    )
    assert quote["credit_discount_percentage"] == product.credit_discount_percentage
    assert quote["max_creditable_cents"] == round(
        quote["items_cents"] * product.credit_discount_percentage / 100
    )


@pytest.mark.asyncio
async def test_cart_when_the_administrator_switches_the_marketplace_off(db, organization_id, fake_aliexpress):
    """A disabled shop keeps the cart visible and intact, showing what is in
    it and why it cannot be paid."""
    admin = await _user(db, organization_id, "ADMIN")
    customer = await _user(db, organization_id)
    row, _product, variants = await _shop(db, organization_id, admin)
    black, white = await _two_in_stock(db, variants)
    for variant in (black, white):
        await carts_service.add_item(
            db, organization_id=organization_id, customer_user_id=customer.id, shop="aliexpress",
            variant_id=variant.id, quantity=1,
        )

    await aliexpress_service.update_settings(db, row=row, actor_user_id=admin.id, updates={"enabled": False})

    summary = await carts_service.summary(db, organization_id=organization_id, customer_user_id=customer.id)
    section = summary["sections"][0]
    assert section["purchasable"] is False
    assert all(not i["available"] for i in section["items"])
    assert all("non è disponibile" in (i["unavailable_reason"] or "") for i in section["items"])
    # Items are still counted and the total is real.
    assert summary["item_count"] == 2
    assert summary["total_cents"] == 0

    # The API refuses payment while the shop is off.
    _cart, lines = await carts_service.checkout_lines(db, customer_user_id=customer.id, shop="aliexpress")
    with pytest.raises(aliexpress_service.AliexpressValidationError):
        await aliexpress_service.create_order(
            db, organization_id=organization_id, customer_user_id=customer.id, lines=lines, address=ADDRESS,
            credit_applied_cents=0, payment_method="BANK_TRANSFER", actor_user_id=customer.id,
            otp_code=None, note=None,
        )

    # Re-enabled, the same cart is purchasable again.
    await aliexpress_service.update_settings(db, row=row, actor_user_id=admin.id, updates={"enabled": True})
    again = await carts_service.summary(db, organization_id=organization_id, customer_user_id=customer.id)
    assert again["sections"][0]["purchasable"] is True
    assert again["total_cents"] > 0


@pytest.mark.asyncio
async def test_a_cart_order_shows_every_line_and_sends_a_payment_receipt(
    db, organization_id, fake_aliexpress, monkeypatch
):
    """A cart order must read as multi-item everywhere: the API behind both
    order panels, the margin and the emails."""
    sent: list[dict] = []
    monkeypatch.setattr(
        aliexpress_service, "send_html_email_best_effort",
        lambda **kw: sent.append(kw) or True,
    )
    admin = await _user(db, organization_id, "ADMIN")
    customer = await _user(db, organization_id)
    _row, _product, variants = await _shop(db, organization_id, admin)
    black, white = await _two_in_stock(db, variants)
    for variant, qty in ((black, 2), (white, 1)):
        await carts_service.add_item(
            db, organization_id=organization_id, customer_user_id=customer.id, shop="aliexpress",
            variant_id=variant.id, quantity=qty,
        )
    _cart, lines = await carts_service.checkout_lines(db, customer_user_id=customer.id, shop="aliexpress")
    order = await aliexpress_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, lines=lines, address=ADDRESS,
        credit_applied_cents=0, payment_method="BANK_TRANSFER", actor_user_id=customer.id,
        otp_code=None, note=None,
    )

    # --- API behind "I miei Ordini" and the admin panel ---
    mine = await aliexpress_service.order_read_dict(db, order, admin=False)
    assert len(mine["items"]) == 2
    assert {i["quantity"] for i in mine["items"]} == {2, 1}
    assert sum(i["line_total_cents"] for i in mine["items"]) == 2 * black.price_cents + white.price_cents

    as_admin = await aliexpress_service.order_read_dict(db, order, admin=True)
    assert len(as_admin["item_supplier_orders"]) == 2
    # Margin counts the costs of every line, not just the first.
    items = await aliexpress_service.order_items(db, order)
    only_first = aliexpress_service.pricing.to_eur_cents(
        items[0].unit_cost_amount * items[0].quantity, order.currency_rate
    )
    assert as_admin["supplier_cost_cents"] > only_first

    # --- First email: order confirmation with all items ---
    confirmation = sent[-1]
    assert "Conferma ordine" in confirmation["subject"]
    for item in items:
        assert item.product_name in confirmation["html_body"]

    # --- Second email: receipt, only once payment is confirmed ---
    assert not any("Pagamento ricevuto" in m["subject"] for m in sent)
    await aliexpress_service.confirm_payment(
        db, organization_id=organization_id, order_id=order.id, actor_user_id=admin.id
    )
    receipts = [m for m in sent if "Pagamento ricevuto" in m["subject"]]
    assert len(receipts) == 1
    receipt = receipts[0]["html_body"]
    for item in items:
        assert item.product_name in receipt
    await db.refresh(order)
    assert f"{aliexpress_service.amount_due_cents(order) / 100:.2f}" in receipt
    # Customer emails never name the supplier.
    for message in sent:
        assert "AliExpress" not in message["subject"]
        assert "AliExpress" not in message["html_body"]


# --- Real shipping with a minimum -------------------------------------------------
#
# charged = max(real AliExpress cost, configured minimum)
# The minimum applies once per order, never per item.


async def _quote_with_freight(db, organization_id, customer, variant, *, quantity=1):
    return await aliexpress_service.get_quote(
        db, organization_id=organization_id, customer_user_id=customer.id,
        variant_id=variant.id, quantity=quantity,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("real_cents", "charged_cents"),
    [
        (0, 590),     # free -> minimum
        (200, 590),   # below minimum
        (590, 590),   # exactly the minimum
        (700, 700),   # above minimum: real cost
        (1420, 1420), # real cost
    ],
)
async def test_the_customer_pays_the_higher_of_real_and_minimum(
    db, organization_id, fake_aliexpress, real_cents, charged_cents
):
    admin = await _user(db, organization_id, "ADMIN")
    customer = await _user(db, organization_id)
    _row, _product, variants = await _shop(db, organization_id, admin)
    fake_aliexpress.freight_cents = real_cents
    quote = await _quote_with_freight(db, organization_id, customer, variants["EB-B"])
    assert quote["supplier_shipping_cents"] == real_cents
    assert quote["shipping_cents"] == charged_cents
    assert quote["minimum_shipping_cents"] == 590
    assert quote["shipping_is_minimum"] is (charged_cents > real_cents)


@pytest.mark.asyncio
async def test_the_minimum_applies_once_to_the_order_not_once_per_article(
    db, organization_id, fake_aliexpress
):
    """Three items with 4.00 of real shipping pay the 5.90 minimum once,
    not once per item."""
    admin = await _user(db, organization_id, "ADMIN")
    customer = await _user(db, organization_id)
    _row, _product, variants = await _shop(db, organization_id, admin)
    black, white = await _two_in_stock(db, variants)
    # 1.50 + 1.50 + 1.00 = 4.00 real, three pieces on two lines.
    fake_aliexpress.freight_by_quantity = {2: 300, 1: 100}
    quote = await aliexpress_service.get_quote(
        db, organization_id=organization_id, customer_user_id=customer.id,
        lines=[(black.id, 2), (white.id, 1)],
    )
    assert quote["supplier_shipping_cents"] == 400
    assert quote["shipping_cents"] == 590           # the minimum, once
    assert quote["shipping_cents"] != 590 * 3       # not once per line
    assert [i["supplier_shipping_cents"] for i in quote["items"]] == [300, 100]


@pytest.mark.asyncio
async def test_when_the_real_shipping_beats_the_minimum_the_order_pays_the_real_one(
    db, organization_id, fake_aliexpress
):
    """Real shipping above the minimum (12.00 vs 5.90) is charged in full."""
    admin = await _user(db, organization_id, "ADMIN")
    customer = await _user(db, organization_id)
    _row, _product, variants = await _shop(db, organization_id, admin)
    black, white = await _two_in_stock(db, variants)
    fake_aliexpress.freight_by_quantity = {2: 800, 1: 400}
    quote = await aliexpress_service.get_quote(
        db, organization_id=organization_id, customer_user_id=customer.id,
        lines=[(black.id, 2), (white.id, 1)],
    )
    assert quote["supplier_shipping_cents"] == 1200
    assert quote["shipping_cents"] == 1200
    assert quote["shipping_is_minimum"] is False


@pytest.mark.asyncio
async def test_changing_the_minimum_in_the_admin_changes_the_checkout_at_once(
    db, organization_id, fake_aliexpress
):
    """Changing the minimum (5.90 -> 6.90) takes effect at checkout without code changes."""
    admin = await _user(db, organization_id, "ADMIN")
    customer = await _user(db, organization_id)
    row, _product, variants = await _shop(db, organization_id, admin)
    fake_aliexpress.freight_cents = 200
    first = await _quote_with_freight(db, organization_id, customer, variants["EB-B"])
    assert first["shipping_cents"] == 590

    await aliexpress_service.update_settings(
        db, row=row, actor_user_id=admin.id, updates={"shipping_minimum_cents": 690}
    )
    again = await _quote_with_freight(db, organization_id, customer, variants["EB-B"])
    assert again["minimum_shipping_cents"] == 690
    assert again["shipping_cents"] == 690


@pytest.mark.asyncio
async def test_the_freight_is_asked_again_when_quantity_or_sku_changes(
    db, organization_id, fake_aliexpress
):
    """Quotes depend on quantity and SKU, so changing either must not return a
    stale cached figure."""
    admin = await _user(db, organization_id, "ADMIN")
    customer = await _user(db, organization_id)
    _row, _product, variants = await _shop(db, organization_id, admin)
    black, white = await _two_in_stock(db, variants)
    fake_aliexpress.freight_by_quantity = {1: 700, 3: 1500}

    one = await _quote_with_freight(db, organization_id, customer, black, quantity=1)
    three = await _quote_with_freight(db, organization_id, customer, black, quantity=3)
    assert one["shipping_cents"] == 700 and three["shipping_cents"] == 1500

    # Same quantity: same answer from the cache, no extra call.
    calls_before = fake_aliexpress.count("aliexpress.ds.freight.query")
    again = await _quote_with_freight(db, organization_id, customer, black, quantity=1)
    assert again["shipping_cents"] == 700
    assert fake_aliexpress.count("aliexpress.ds.freight.query") == calls_before

    # Different SKU, different key, different quote.
    fake_aliexpress.freight_by_sku = {white.aliexpress_sku_id: 250}
    other = await _quote_with_freight(db, organization_id, customer, white, quantity=1)
    assert other["supplier_shipping_cents"] == 250


@pytest.mark.asyncio
async def test_an_aliexpress_failure_never_becomes_free_shipping(db, organization_id, fake_aliexpress):
    """Unknown shipping cost means no sale.

    Neither zero nor the minimum is a real figure: charging 5.90 for a
    shipment that may cost 20 would sell at a loss."""
    admin = await _user(db, organization_id, "ADMIN")
    customer = await _user(db, organization_id)
    _row, _product, variants = await _shop(db, organization_id, admin)

    fake_aliexpress.fail_freight = "AliExpress non risponde (ReadTimeout)."
    with pytest.raises(aliexpress_service.AliexpressShippingUnavailableError):
        await _quote_with_freight(db, organization_id, customer, variants["EB-B"])
    with pytest.raises(aliexpress_service.AliexpressShippingUnavailableError):
        await aliexpress_service.create_order(
            db, organization_id=organization_id, customer_user_id=customer.id,
            variant_id=variants["EB-B"].id, quantity=1, address=ADDRESS, credit_applied_cents=0,
            payment_method="BANK_TRANSFER", actor_user_id=customer.id, otp_code=None, note=None,
        )

    # An option without a price means "unknown", not zero.
    fake_aliexpress.fail_freight = None
    fake_aliexpress.freight_without_price = True
    with pytest.raises(aliexpress_service.AliexpressShippingUnavailableError):
        await _quote_with_freight(db, organization_id, customer, variants["EB-B"])


@pytest.mark.asyncio
async def test_the_order_freezes_what_shipping_cost_and_what_was_charged(
    db, organization_id, fake_aliexpress
):
    """Supplier and charged shipping are frozen separately on the order and
    its lines, so the shipping margin stays reconstructable."""
    admin = await _user(db, organization_id, "ADMIN")
    customer = await _user(db, organization_id)
    _row, _product, variants = await _shop(db, organization_id, admin)
    black, white = await _two_in_stock(db, variants)
    fake_aliexpress.freight_by_quantity = {2: 300, 1: 100}
    order = await aliexpress_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id,
        lines=[(black.id, 2), (white.id, 1)], address=ADDRESS, credit_applied_cents=0,
        payment_method="BANK_TRANSFER", actor_user_id=customer.id, otp_code=None, note=None,
    )
    assert order.supplier_shipping_cents == 400
    assert order.minimum_shipping_cents == 590
    assert order.shipping_cents == 590
    items = await aliexpress_service.order_items(db, order)
    assert sorted(i.supplier_shipping_cents for i in items) == [100, 300]

    admin_read = await aliexpress_service.order_read_dict(db, order, admin=True)
    assert admin_read["shipping_margin_cents"] == 190  # 590 charged - 400 real


@pytest.mark.asyncio
async def test_the_browser_cannot_decide_the_shipping_or_the_total(db, organization_id, fake_aliexpress):
    """The server computes the total.

    Neither the quote nor order creation accepts an amount from the caller;
    the order total can only be recomputed."""
    admin = await _user(db, organization_id, "ADMIN")
    customer = await _user(db, organization_id)
    _row, _product, variants = await _shop(db, organization_id, admin)
    fake_aliexpress.freight_cents = 900

    import inspect

    for fn in (aliexpress_service.get_quote, aliexpress_service.create_order):
        taken = set(inspect.signature(fn).parameters)
        assert not taken & {"amount_cents", "shipping_cents", "unit_price_cents", "total_cents"}

    order = await aliexpress_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id,
        variant_id=variants["EB-B"].id, quantity=1, address=ADDRESS, credit_applied_cents=0,
        payment_method="BANK_TRANSFER", actor_user_id=customer.id, otp_code=None, note=None,
    )
    assert order.shipping_cents == 900  # real cost, not the minimum
    assert order.amount_cents == _con_iva(order.unit_price_cents * order.quantity) + 900


@pytest.mark.asyncio
async def test_the_freight_field_carries_an_amount_not_cents(db, organization_id, fake_aliexpress):
    """shipping_fee_cent carries an amount, not cents: "1.99" means 1.99 EUR.
    Reading it as cents would sell expensive shipping at the minimum, at a
    loss."""
    admin = await _user(db, organization_id, "ADMIN")
    row, _product, _variants = await _shop(db, organization_id, admin)
    body = {"aliexpress_ds_freight_query_response": {"result": {"delivery_options": {
        "delivery_option_dto": [{"shipping_fee_cent": "1.99", "shipping_fee_currency": "EUR"}]
    }}}}
    assert aliexpress_service._parse_freight(body, settings=row)[0]["shipping_fee_cents"] == 199

    # Expensive shipping stays expensive instead of vanishing under the minimum.
    body["aliexpress_ds_freight_query_response"]["result"]["delivery_options"][
        "delivery_option_dto"][0]["shipping_fee_cent"] = "12.00"
    parsed = aliexpress_service._parse_freight(body, settings=row)[0]["shipping_fee_cents"]
    assert parsed == 1200
    assert aliexpress_service.pricing.charged_shipping_cents(supplier_cents=parsed, settings=row) == 1200


@pytest.mark.asyncio
async def test_each_product_brings_its_own_sosnetcash_entitlement(db, organization_id, fake_aliexpress):
    """Each product carries its own SosnetCash percentage, never an order-wide
    average: averaging would take credit from items that accept none or deny
    it to items that do."""
    admin = await _user(db, organization_id, "ADMIN")
    customer = await _user(db, organization_id)
    row, product, variants = await _shop(db, organization_id, admin, credit_percentage=50)
    black, white = await _two_in_stock(db, variants)
    # Truly free shipping: the minimum must be zeroed too, or it would apply.
    fake_aliexpress.freight_cents = 0
    await aliexpress_service.update_settings(
        db, row=row, actor_user_id=admin.id, updates={"shipping_minimum_cents": 0}
    )

    # Two lines at the same percentage: the cap is their sum.
    quote = await aliexpress_service.get_quote(
        db, organization_id=organization_id, customer_user_id=customer.id,
        lines=[(black.id, 1), (white.id, 1)],
    )
    per_line = [i["max_creditable_cents"] for i in quote["items"]]
    assert per_line == [round(i["line_total_cents"] * 50 / 100) for i in quote["items"]]
    assert quote["max_creditable_cents"] == sum(per_line)

    # The cap never reaches the whole order, whatever the percentage.
    assert quote["max_creditable_cents"] < quote["amount_cents"]


@pytest.mark.asyncio
async def test_buying_from_the_cart_gives_the_same_cap_as_buying_the_product_alone(
    db, organization_id, fake_aliexpress
):
    """A single item gives the same cap from its product page or the cart:
    its percentage of the goods value, shipping excluded."""
    admin = await _user(db, organization_id, "ADMIN")
    customer = await _user(db, organization_id)
    _row, product, variants = await _shop(db, organization_id, admin, credit_percentage=30)
    quote = await aliexpress_service.get_quote(
        db, organization_id=organization_id, customer_user_id=customer.id,
        variant_id=variants["EB-B"].id, quantity=2,
    )
    # SosnetCash discounts the goods, not the courier.
    assert quote["max_creditable_cents"] == round(
        quote["items_cents"] * product.credit_discount_percentage / 100
    )
    assert quote["credit_discount_percentage"] == product.credit_discount_percentage


@pytest.mark.asyncio
async def test_a_product_that_takes_no_sosnetcash_never_lends_any_to_the_others(
    db, organization_id, fake_aliexpress
):
    """A 0% product contributes no spendable SosnetCash and takes none away
    from the product next to it."""
    admin = await _user(db, organization_id, "ADMIN")
    customer = await _user(db, organization_id)
    row, _product, variants = await _shop(db, organization_id, admin, credit_percentage=99)
    fake_aliexpress.freight_cents = 0
    await aliexpress_service.update_settings(
        db, row=row, actor_user_id=admin.id, updates={"shipping_minimum_cents": 0}
    )
    black = variants["EB-B"]
    _other, cheap = await _other_product(db, organization_id, admin, credit_percentage=0)

    alone = await aliexpress_service.get_quote(
        db, organization_id=organization_id, customer_user_id=customer.id,
        variant_id=black.id, quantity=1,
    )
    together = await aliexpress_service.get_quote(
        db, organization_id=organization_id, customer_user_id=customer.id,
        lines=[(black.id, 1), (cheap.id, 1)],
    )
    # 0% contributes zero; 99% contributes exactly what it would alone.
    assert together["items"][1]["max_creditable_cents"] == 0
    assert together["items"][0]["max_creditable_cents"] == alone["max_creditable_cents"]
    assert together["max_creditable_cents"] == alone["max_creditable_cents"]


@pytest.mark.asyncio
async def test_a_zero_minimum_means_the_customer_pays_exactly_what_shipping_costs(
    db, organization_id, fake_aliexpress
):
    """A zero minimum disables the floor: the customer pays the real cost.

    The mechanism stays in place and is re-enabled by setting an amount."""
    admin = await _user(db, organization_id, "ADMIN")
    customer = await _user(db, organization_id)
    row, _product, variants = await _shop(db, organization_id, admin)
    await aliexpress_service.update_settings(
        db, row=row, actor_user_id=admin.id, updates={"shipping_minimum_cents": 0}
    )
    for reale in (0, 199, 2324, 4416):
        fake_aliexpress.cache.clear()
        fake_aliexpress.freight_cents = reale
        quote = await aliexpress_service.get_quote(
            db, organization_id=organization_id, customer_user_id=customer.id,
            variant_id=variants["EB-B"].id, quantity=1,
        )
        assert quote["supplier_shipping_cents"] == reale
        assert quote["shipping_cents"] == reale
        assert quote["shipping_is_minimum"] is False


@pytest.mark.asyncio
async def test_the_sosnetcash_cap_is_exactly_what_the_customer_can_add_up_by_hand(
    db, organization_id, fake_aliexpress
):
    """The cap is the sum of price x quantity x percentage per line, shipping
    excluded, so a customer can check it by hand."""
    admin = await _user(db, organization_id, "ADMIN")
    customer = await _user(db, organization_id)
    _row, product, variants = await _shop(db, organization_id, admin, credit_percentage=25)
    black, white = await _two_in_stock(db, variants)
    fake_aliexpress.freight_cents = 1200  # high shipping must not count

    quote = await aliexpress_service.get_quote(
        db, organization_id=organization_id, customer_user_id=customer.id,
        lines=[(black.id, 3), (white.id, 2)],
    )
    a_mano = round(black.price_cents * 3 * 25 / 100) + round(white.price_cents * 2 * 25 / 100)
    assert quote["max_creditable_cents"] == a_mano
    # Two lines, two quotes; shipping is high on purpose.
    assert quote["shipping_cents"] == 2400
    # Shipping did not move the cap.
    assert quote["max_creditable_cents"] < quote["items_cents"]


@pytest.mark.asyncio
async def test_every_order_gets_a_readable_number(db, organization_id, fake_aliexpress):
    """A sequential, database-assigned, unique order number, used in emails
    and read out by customers on the phone."""
    admin = await _user(db, organization_id, "ADMIN")
    customer = await _user(db, organization_id)
    _row, _product, variants = await _shop(db, organization_id, admin)

    numeri = []
    for _ in range(2):
        order = await aliexpress_service.create_order(
            db, organization_id=organization_id, customer_user_id=customer.id,
            variant_id=variants["EB-B"].id, quantity=1, address=ADDRESS, credit_applied_cents=0,
            payment_method="BANK_TRANSFER", actor_user_id=customer.id, otp_code=None, note=None,
        )
        await db.refresh(order)
        numeri.append(order.number)
        assert aliexpress_service.order_code(order) == str(order.number)
        assert aliexpress_service.order_number(order) == f"SOSNET-{order.number}"

    assert numeri[1] > numeri[0], "i numeri devono crescere"
    assert len(set(numeri)) == 2, "e non ripetersi"
    assert numeri[0] >= 1000, "si parte da 1000, non da 1"

    read = await aliexpress_service.order_read_dict(db, order, admin=False)
    assert read["number"] == order.number and read["order_code"] == str(order.number)
