"""CJ Dropshipping marketplace (Shop Sosnet Partner): pricing, settings,
import, the shared checkout, forwarding orders to CJ and tracking them. CJ is
faked at client.call, through which every CJ request passes."""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.foundation.db import utcnow
from app.foundation.security import hash_otp_code, hash_password
from app.modules.accounting import details as accounting_details
from app.modules.accounting import service as accounting_service
from app.modules.auth import service as auth_service
from app.modules.auth.models import OtpCode
from app.modules.cj_dropshipping import client as cj_client
from app.modules.cj_dropshipping import pricing
from app.modules.cj_dropshipping import service as cj_service
from app.modules.cj_dropshipping.models import CjOrder, CjSettings, CjVariant
from app.modules.notifications.models import Notification
from app.modules.organizations import service as organizations_service
from app.modules.organizations.schemas import OrganizationSettingsUpdate
from app.modules.rbac.models import Role, UserRole
from app.modules.users.models import User
from app.modules.carts import service as carts_service
from app.modules.wallets import service as wallet_service

def _con_iva(merce_cents: int, aliquota: int = 22) -> int:
    """Customer total for the goods: VAT is added on top of the listed price."""
    from app.modules.marketplaces import rules

    return merce_cents + rules.vat_added_cents(net_cents=merce_cents, percentage=aliquota)


OTP = "111222"
ADDRESS = {
    "recipient_name": "Mario Rossi", "recipient_phone": "3331234567", "address_line1": "Via Roma 1",
    "address_line2": None, "city": "Milano", "province": "MI", "postal_code": "20100",
}


class FakeCj:
    def __init__(self):
        self.calls: list[tuple[str, dict | None]] = []
        self.fail_create: str | None = None
        self.fail_pay: str | None = None
        self.lookup_error: str | None = None
        self.timeout_after_create = False
        self.autopay_on_create = False  # mirrors CJ's handling of sandbox orders
        self.balance = 0.0
        self.orders_created = 0
        self.freight_options = [
            {"logisticName": "CJPacket Ordinary", "logisticPrice": 6.10, "totalPostageFee": 7.81, "logisticAging": "4-8"},
            {"logisticName": "Slow Post", "logisticPrice": 9.50, "totalPostageFee": 9.50, "logisticAging": "20-30"},
            # Cheapest base price but most expensive in reality: must not be chosen.
            {"logisticName": "Trap Express", "logisticPrice": 5.00, "totalPostageFee": 12.00, "logisticAging": "3-5"},
        ]
        self.remote_orders: dict[str, dict] = {}

    async def __call__(self, db, settings, method, path, *, params=None, body=None):
        self.calls.append((path, body))
        if path == "/product/query":
            return {
                "pid": "P1", "productSku": "SKU1", "productNameEn": "Wireless Earbuds",
                "description": "<p>Great <b>sound</b></p><script>alert(1)</script><ul><li>Bluetooth 5.3</li></ul>",
                "categoryName": "Electronics", "bigImage": "https://img/1.jpg", "productImageSet": ["https://img/2.jpg"],
                "variants": [
                    {"vid": "V1", "variantSku": "SKU1-B", "variantKey": "Black", "variantSellPrice": "10.00",
                     "variantWeight": "120", "inventories": None},
                    {"vid": "V2", "variantSku": "SKU1-W", "variantKey": "White", "variantSellPrice": "11.00",
                     "variantWeight": "130", "inventories": None},
                ],
            }
        if path == "/product/stock/getInventoryByPid":
            return {
                "inventories": [{"countryCode": "CN", "totalInventoryNum": 500}],
                "variantInventories": [
                    {"vid": "V1", "inventory": [{"countryCode": "CN", "totalInventory": 500}]},
                    {"vid": "V2", "inventory": [{"countryCode": "CN", "totalInventory": 0}]},
                ],
            }
        if path == "/logistic/freightCalculate":
            return self.freight_options
        if path == "/shopping/order/getOrderDetail":
            if self.lookup_error:
                raise cj_client.CjApiError(self.lookup_error)  # e.g. timeout: code None
            item = self._find(params["orderId"])
            if item is None:
                raise cj_client.CjApiError("CJ: order not found", code=1600300)
            return dict(item)
        if path == "/shopping/order/createOrderV2":
            if self.fail_create:
                raise cj_client.CjApiError(self.fail_create, code=1600100)
            self.orders_created += 1
            n = self.orders_created
            status = "UNSHIPPED" if self.autopay_on_create else "UNPAID"
            item = {
                "orderId": f"26091711{n:04d}", "cjOrderCode": f"SD{n:04d}", "orderNum": body["orderNumber"],
                "orderStatus": status, "orderAmount": 17.81, "productAmount": 10.00, "postageAmount": 7.81,
            }
            self.remote_orders[body["orderNumber"]] = item
            if self.timeout_after_create:
                self.timeout_after_create = False
                raise cj_client.CjApiError("CJ non risponde (ReadTimeout). Riprova tra poco.")
            return {
                "orderId": item["cjOrderCode"], "orderNumber": body["orderNumber"], "shipmentOrderId": f"CJ{n}",
                "orderStatus": "", "orderAmount": 17.81, "productAmount": 10.00, "postageAmount": 7.81,
                "cjPayUrl": None if self.autopay_on_create else f"https://pay.cj.example/{n}",
            }
        if path == "/shopping/pay/payBalance":
            if self.fail_pay:
                message, self.fail_pay = self.fail_pay, None
                raise cj_client.CjApiError(message)
            item = self._find(body["orderId"])
            if item is None or item["orderStatus"] != "UNPAID":
                raise cj_client.CjApiError("CJ: pay order fail, order status is not unpaid.", code=1603001)
            if self.balance < item["orderAmount"]:
                raise cj_client.CjApiError("CJ: Insufficient balance", code=1603001)
            self.balance = round(self.balance - item["orderAmount"], 2)
            item["orderStatus"] = "UNSHIPPED"
            return None
        if path == "/shopping/order/getOrderDetailBatch":
            return [dict(i) for i in (self._find(x) for x in body["orderIds"]) if i is not None]
        if path == "/shopping/pay/getBalance":
            return {"amount": self.balance}
        raise AssertionError(f"unexpected CJ call {path}")

    def _find(self, ref):
        for item in self.remote_orders.values():
            if ref in (item["orderId"], item["cjOrderCode"], item["orderNum"]):
                return item
        return None

    def count(self, path):
        return sum(1 for p, _ in self.calls if p == path)

    def calls_to_orders(self):
        return sum(1 for p, _ in self.calls if p.startswith("/shopping/"))


@pytest.fixture
def fake_cj(monkeypatch):
    fake = FakeCj()
    cache: dict = {}

    async def cache_get(key):
        return cache.get(key)

    async def cache_set(key, value, seconds):
        cache[key] = value

    monkeypatch.setattr(cj_client, "call", fake)
    monkeypatch.setattr(cj_service, "_cache_get", cache_get)
    monkeypatch.setattr(cj_service, "_cache_set", cache_set)
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


async def _shop(db, organization_id, admin, bank_transfer_discount_percentage=None, credit_percentage=50, **settings_updates):
    from app.modules.marketplaces import rules

    await organizations_service.update_settings(
        db, organization_id=organization_id, payload=OrganizationSettingsUpdate(bank_iban="IT66W0883330410000000015702")
    )
    if bank_transfer_discount_percentage is not None:
        await rules.update_config(
            db, organization_id=organization_id, labels=None,
            bank_transfer_discount_percentage=bank_transfer_discount_percentage,
        )
    row = await cj_service.get_settings_row(db, organization_id=organization_id)
    await cj_service.update_settings(
        db, row=row, actor_user_id=admin.id,
        updates={
            "api_key": "CJ123@api@secret-abcd", "enabled": True, "markup_percentage": 40, "auto_forward": False,
            **settings_updates,
        },
    )
    product = await cj_service.import_product(
        db, row=row, actor_user_id=admin.id, pid="P1", name="Auricolari wireless", description=None,
        credit_discount_percentage=credit_percentage, markup_percentage=None, vids=None, activate=True,
    )
    variants = (await db.execute(select(CjVariant).where(CjVariant.product_id == product.id))).scalars().all()
    return row, product, {v.cj_vid: v for v in variants}


async def _otp(db, user_id):
    db.add(OtpCode(
        user_id=user_id, purpose=auth_service.WALLET_CREDIT_SPEND_OTP_PURPOSE, code_hash=hash_otp_code(OTP),
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
    ))
    await db.commit()


def _settings(**kw):
    base = {"usd_eur_rate": Decimal("0.92"), "markup_percentage": 40, "markup_fixed_cents": 0,
            "price_rounding": "90", "shipping_mode": "CUSTOMER_PAYS"}
    base.update(kw)
    return CjSettings(**base)


def test_price_is_cost_converted_marked_up_and_rounded_up():
    assert pricing.sale_price_cents(cost_usd="10", settings=_settings()) == 1290
    assert pricing.sale_price_cents(cost_usd="10", settings=_settings(price_rounding="99")) == 1299
    assert pricing.sale_price_cents(cost_usd="10", settings=_settings(price_rounding="NONE")) == 1288
    # Rounding is always upward: 12.91 -> 13.90.
    assert pricing._round_up(1291, "90") == 1390
    # Shipping included: estimated shipping is added to the price and checkout shipping is 0.
    included = _settings(shipping_mode="INCLUDED")
    assert pricing.sale_price_cents(cost_usd="10", settings=included, shipping_estimate_usd="7.81") == 2090
    assert pricing.shipping_price_cents(shipping_usd="7.81", settings=included) == 0
    assert pricing.shipping_price_cents(shipping_usd="7.81", settings=_settings()) == 719


def test_cj_description_becomes_plain_text():
    text = cj_service.html_to_text("<p>Great <b>sound</b></p><ul><li>Bluetooth</li></ul>&amp; more")
    assert "<" not in text
    assert "Great sound" in text and "• Bluetooth" in text and "& more" in text


@pytest.mark.asyncio
async def test_new_shop_starts_with_a_100_percent_markup(db, organization_id):
    row = await cj_service.get_settings_row(db, organization_id=organization_id)
    assert row.markup_percentage == 100  # pay 10, sell at 20 before rounding
    assert pricing.sale_price_cents(cost_usd="10", settings=row) == 1890  # 9.20 x 2 = 18.40 -> 18.90


@pytest.mark.asyncio
async def test_api_key_is_never_returned_and_changing_it_drops_the_tokens(db, organization_id):
    admin = await _user(db, organization_id, "ADMIN")
    row = await cj_service.get_settings_row(db, organization_id=organization_id)
    with pytest.raises(cj_service.CjValidationError):
        await cj_service.update_settings(db, row=row, updates={"enabled": True}, actor_user_id=admin.id)
    await cj_service.update_settings(db, row=row, updates={"api_key": "CJ1@api@secret-wxyz"}, actor_user_id=admin.id)
    row.access_token = "tok"
    await db.commit()
    read = cj_service.settings_read_dict(row)
    assert read["api_key_configured"] is True
    assert read["api_key_hint"] == "…wxyz"
    assert "secret" not in str(read)
    await cj_service.update_settings(db, row=row, updates={"api_key": "CJ1@api@other-1111"}, actor_user_id=admin.id)
    assert row.access_token is None


@pytest.mark.asyncio
async def test_import_saves_variants_with_our_price_and_blocks_duplicates(db, organization_id, fake_cj):
    admin = await _user(db, organization_id, "ADMIN")
    row, product, variants = await _shop(db, organization_id, admin)
    assert product.origin_country == "CN"
    assert product.shipping_days == "4-8"  # cheapest option
    assert "<" not in product.description
    assert "alert" not in product.description  # script contents dropped, not turned into text
    assert variants["V1"].price_cents == 1290
    assert variants["V1"].inventory == 500
    assert variants["V2"].inventory == 0

    card = await cj_service.product_customer_dict(db, product, settings=row)
    assert card["min_price_cents"] == 1290
    assert [v["in_stock"] for v in card["variants"]] == [True, False]

    with pytest.raises(cj_service.CjValidationError):
        await cj_service.import_product(
            db, row=row, actor_user_id=admin.id, pid="P1", name="x", description=None,
            credit_discount_percentage=None, markup_percentage=None, vids=None, activate=True,
        )

    # A new markup re-prices every variant from the stored cost.
    await cj_service.update_settings(db, row=row, updates={"markup_percentage": 100}, actor_user_id=admin.id)
    await db.refresh(variants["V1"])
    assert variants["V1"].price_cents == 1890


@pytest.mark.asyncio
async def test_product_cj_cannot_ship_is_not_importable(db, organization_id, fake_cj):
    admin = await _user(db, organization_id, "ADMIN")
    fake_cj.freight_options = []
    row = await cj_service.get_settings_row(db, organization_id=organization_id)
    await cj_service.update_settings(db, row=row, updates={"api_key": "k"}, actor_user_id=admin.id)
    with pytest.raises(cj_service.CjValidationError):
        await cj_service.import_product(
            db, row=row, actor_user_id=admin.id, pid="P1", name="x", description=None,
            credit_discount_percentage=None, markup_percentage=None, vids=None, activate=True,
        )


@pytest.mark.asyncio
async def test_checkout_with_sosnetcash_and_shipping_like_every_shop(db, organization_id, fake_cj):
    admin = await _user(db, organization_id, "ADMIN")
    customer = await _user(db, organization_id)
    _row, _product, variants = await _shop(db, organization_id, admin)
    wallet = await wallet_service.get_or_create_wallet(db, organization_id=organization_id, user_id=customer.id)
    await wallet_service.credit_wallet(
        db, organization_id=organization_id, wallet_id=wallet.id, amount_cents=1000, type_="ADMIN_CREDIT",
        actor_user_id=admin.id, idempotency_key=str(uuid.uuid4()),
    )

    quote = await cj_service.get_quote(
        db, organization_id=organization_id, customer_user_id=customer.id, variant_id=variants["V1"].id, quantity=2
    )
    assert quote["items_cents"] == 2580
    assert quote["shipping_cents"] == 719
    assert quote["amount_cents"] == _con_iva(2580) + 719
    # The cap is 50% of the goods value, excluding shipping: SosnetCash
    # discounts the product, not the courier.
    assert quote["max_creditable_cents"] == round(quote["items_cents"] * 50 / 100)

    with pytest.raises(cj_service.CjValidationError):
        await cj_service.get_quote(
            db, organization_id=organization_id, customer_user_id=customer.id, variant_id=variants["V2"].id, quantity=1
        )
    with pytest.raises(cj_service.InvalidOtpError):
        await cj_service.create_order(
            db, organization_id=organization_id, customer_user_id=customer.id, variant_id=variants["V1"].id,
            quantity=2, address=ADDRESS, credit_applied_cents=1000, payment_method="BANK_TRANSFER",
            actor_user_id=customer.id, otp_code="000000", note=None,
        )

    await _otp(db, customer.id)
    order = await cj_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, variant_id=variants["V1"].id,
        quantity=2, address=ADDRESS, credit_applied_cents=1000, payment_method="BANK_TRANSFER",
        actor_user_id=customer.id, otp_code=OTP, note=None,
    )
    assert order.status == "AWAITING_PAYMENT"
    assert order.amount_cents == quote["amount_cents"]
    assert order.logistic_name == "CJPacket Ordinary"
    assert order.city == "Milano" and order.country_code == "IT"
    assert order.fulfillment_status == "NOT_SENT"
    txn = await db.get(wallet_service.WalletTransaction, order.credit_debit_transaction_id)
    assert txn.reference_cj_order_id == order.id
    assert (await wallet_service.get_wallet_by_user_id(
        db, organization_id=organization_id, user_id=customer.id
    )).balance_cents == 0

    # Unpaid orders cannot be forwarded to CJ.
    with pytest.raises(cj_service.CjValidationError):
        await cj_service.forward_order(db, organization_id=organization_id, order_id=order.id, actor_user_id=admin.id)

    await cj_service.confirm_payment(db, organization_id=organization_id, order_id=order.id, actor_user_id=admin.id)
    assert order.status == "PAID"

    movements = await accounting_service.list_my_movements(db, organization_id=organization_id, user_id=customer.id)
    euro_rows = [m for m in movements if m["kind"] == "ORDER_PAYMENT" and m["order_id"] == order.id]
    # Bank transfer: 5% off the residual after SosnetCash.
    assert euro_rows and euro_rows[0]["amount_cents"] == cj_service.amount_due_cents(order)
    wallet_rows = [m for m in movements if m["kind"] == "WALLET" and m["order_id"] == order.id]
    assert wallet_rows and wallet_rows[0]["product_name"] == "Auricolari wireless"

    detail = await accounting_details._order_detail(
        db, organization_id=organization_id, entity_id=order.id, owner_user_id=customer.id
    )
    assert detail["subtitle"].endswith("Marketplace 1")
    assert "CJ" not in detail["subtitle"] and "Partner" not in detail["subtitle"]
    assert not any(f and f["label"] == "Ordine CJ" for f in detail["facts"])


@pytest.mark.asyncio
async def test_cancel_gives_the_sosnetcash_back(db, organization_id, fake_cj):
    admin = await _user(db, organization_id, "ADMIN")
    customer = await _user(db, organization_id)
    _row, _product, variants = await _shop(db, organization_id, admin)
    wallet = await wallet_service.get_or_create_wallet(db, organization_id=organization_id, user_id=customer.id)
    await wallet_service.credit_wallet(
        db, organization_id=organization_id, wallet_id=wallet.id, amount_cents=500, type_="ADMIN_CREDIT",
        actor_user_id=admin.id, idempotency_key=str(uuid.uuid4()),
    )
    await _otp(db, customer.id)
    order = await cj_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, variant_id=variants["V1"].id,
        quantity=1, address=ADDRESS, credit_applied_cents=500, payment_method="BANK_TRANSFER",
        actor_user_id=customer.id, otp_code=OTP, note=None,
    )
    await cj_service.cancel_order(
        db, organization_id=organization_id, order_id=order.id, reason="ripensamento", actor_user_id=admin.id
    )
    assert order.status == "CANCELLED"
    assert (await wallet_service.get_wallet_by_user_id(
        db, organization_id=organization_id, user_id=customer.id
    )).balance_cents == 500


async def _paid_order(db, organization_id, fake_cj, admin=None, customer=None):
    admin = admin or await _user(db, organization_id, "ADMIN")
    customer = customer or await _user(db, organization_id)
    _row, _product, variants = await _shop(db, organization_id, admin)
    order = await cj_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, variant_id=variants["V1"].id,
        quantity=1, address=ADDRESS, credit_applied_cents=0, payment_method="BANK_TRANSFER",
        actor_user_id=customer.id, otp_code=None, note=None,
    )
    await cj_service.confirm_payment(db, organization_id=organization_id, order_id=order.id, actor_user_id=admin.id)
    return admin, customer, order


async def _staff_notes(db, type_):
    return (await db.execute(select(Notification).where(Notification.type == type_))).scalars().all()


def test_shipping_is_chosen_and_charged_on_what_cj_really_bills():
    options = FakeCj().freight_options
    assert cj_service._cheapest(options)["logisticName"] == "CJPacket Ordinary"  # the real cost wins over the base price
    assert cj_service.postage_usd({"logisticPrice": 9.39, "totalPostageFee": 12.89}) == Decimal("12.89")
    assert cj_service.postage_usd({"logisticPrice": 9.39}) == Decimal("9.39")


@pytest.mark.asyncio
async def test_scenario1_balance_covers_it_created_and_paid_automatically(db, organization_id, fake_cj):
    fake_cj.balance = 100.0
    _admin, _customer, order = await _paid_order(db, organization_id, fake_cj)
    assert order.cj_payment_status == "NOT_REQUIRED"
    order = await cj_service.forward_order(db, organization_id=organization_id, order_id=order.id, actor_user_id=None)
    assert order.fulfillment_status == "PROCESSING"
    assert order.cj_payment_status == "PAID" and order.cj_paid_at is not None
    assert order.cj_order_code == "SD0001"
    assert order.cj_amount_usd == Decimal("17.81")
    body = next(b for p, b in fake_cj.calls if p == "/shopping/order/createOrderV2")
    assert body["payType"] == 1 and body["orderNumber"] == f"SOSNET-{order.id}"
    assert body["isSandbox"] == 1 and body["logisticName"] == "CJPacket Ordinary" and body["iossType"] == 3
    assert fake_cj.count("/shopping/pay/payBalance") == 1
    assert fake_cj.balance == 82.19
    read = await cj_service.order_read_dict(db, order, admin=False)
    assert read["delivery_status"] == "PREPARING"
    assert "cj_payment_status" not in read and "fulfillment_status" not in read and "cj_pay_url" not in read
    summary = await cj_service.cash_requirement(db, organization_id=organization_id, refresh_balance=False)
    assert summary["orders_to_pay"] == 0 and summary["required_usd"] == 0


@pytest.mark.asyncio
async def test_scenario1b_sandbox_order_paid_by_cj_at_creation_is_not_paid_again(db, organization_id, fake_cj):
    fake_cj.autopay_on_create = True
    _admin, _customer, order = await _paid_order(db, organization_id, fake_cj)
    order = await cj_service.forward_order(db, organization_id=organization_id, order_id=order.id, actor_user_id=None)
    assert order.cj_payment_status == "PAID" and order.fulfillment_status == "PROCESSING"
    assert fake_cj.count("/shopping/pay/payBalance") == 0 and fake_cj.count("/shopping/pay/getBalance") == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("balance", [0.0, 10.0])
async def test_scenario2_3_balance_zero_or_short_order_waits_for_payment(db, organization_id, fake_cj, balance):
    fake_cj.balance = balance
    _admin, customer, order = await _paid_order(db, organization_id, fake_cj)
    order = await cj_service.forward_order(db, organization_id=organization_id, order_id=order.id, actor_user_id=None)
    assert order.cj_order_id and order.fulfillment_status == "SENT"
    assert order.cj_payment_status == "PAYMENT_REQUIRED"
    assert order.last_error_kind == "INSUFFICIENT_BALANCE" and order.next_retry_at is not None
    assert order.cj_pay_url == "https://pay.cj.example/1"
    assert fake_cj.count("/shopping/pay/payBalance") == 0  # never attempted with an insufficient balance
    read = await cj_service.order_read_dict(db, order, admin=False)
    assert read["delivery_status"] == "RECEIVED"
    admin_read = await cj_service.order_read_dict(db, order, admin=True)
    assert admin_read["cj_payment_status"] == "PAYMENT_REQUIRED" and admin_read["cj_pay_url"]
    alerts = await _staff_notes(db, "CJ_PAYMENT_REQUIRED")
    assert len(alerts) >= 1 and "17.81" in alerts[0].title
    assert f"{balance:.2f}" in alerts[0].body
    # The customer is not notified.
    customer_notes = (await db.execute(select(Notification).where(Notification.recipient_user_id == customer.id))).scalars().all()
    assert all("CJ" not in n.title and "saldo" not in (n.body or "").lower() for n in customer_notes)
    # Asking again: same CJ order, no second alert.
    before = len(await _staff_notes(db, "CJ_PAYMENT_REQUIRED"))
    order = await cj_service.forward_order(db, organization_id=organization_id, order_id=order.id, actor_user_id=None)
    assert fake_cj.count("/shopping/order/createOrderV2") == 1
    assert len(await _staff_notes(db, "CJ_PAYMENT_REQUIRED")) == before
    summary = await cj_service.cash_requirement(db, organization_id=organization_id, refresh_balance=True)
    assert summary["orders_to_pay"] == 1 and summary["required_usd"] == 17.81
    assert summary["balance_usd"] == balance and summary["shortfall_usd"] == round(17.81 - balance, 2)


@pytest.mark.asyncio
async def test_scenario4_create_times_out_but_cj_created_it_no_duplicate(db, organization_id, fake_cj):
    fake_cj.balance = 100.0
    fake_cj.timeout_after_create = True
    _admin, _customer, order = await _paid_order(db, organization_id, fake_cj)
    order = await cj_service.forward_order(db, organization_id=organization_id, order_id=order.id, actor_user_id=None)
    assert order.fulfillment_status == "ERROR" and order.last_error_kind == "TEMPORARY"
    assert order.next_retry_at is not None and order.cj_order_id is None
    # A failing lookup must not lead to blind creation.
    fake_cj.lookup_error = "CJ non risponde (ReadTimeout). Riprova tra poco."
    order = await cj_service.forward_order(db, organization_id=organization_id, order_id=order.id, actor_user_id=None)
    assert fake_cj.count("/shopping/order/createOrderV2") == 1 and order.fulfillment_status == "ERROR"
    fake_cj.lookup_error = None
    order = await cj_service.forward_order(db, organization_id=organization_id, order_id=order.id, actor_user_id=None)
    assert fake_cj.count("/shopping/order/createOrderV2") == 1  # found by our order number
    assert order.cj_order_code == "SD0001" and order.cj_payment_status == "PAID"
    assert order.attempt_count == 3


@pytest.mark.asyncio
async def test_scenario5_payment_fails_temporarily_and_is_recovered(db, organization_id, fake_cj):
    fake_cj.balance = 100.0
    fake_cj.fail_pay = "CJ non risponde (ConnectTimeout). Riprova tra poco."
    _admin, _customer, order = await _paid_order(db, organization_id, fake_cj)
    order = await cj_service.forward_order(db, organization_id=organization_id, order_id=order.id, actor_user_id=None)
    assert order.fulfillment_status == "SENT" and order.cj_payment_status == "FAILED"
    assert order.last_error_kind == "TEMPORARY" and order.next_retry_at is not None
    assert (await cj_service.order_read_dict(db, order, admin=False))["delivery_status"] == "RECEIVED"
    # The retry job picks it up when due.
    order.next_retry_at = utcnow() - timedelta(minutes=1)
    await db.commit()
    await cj_service.update_settings(
        db, row=await cj_service.get_settings_row(db, organization_id=organization_id),
        updates={"auto_forward": True}, actor_user_id=None,
    )
    assert await cj_service.retry_due_orders(db, organization_id=organization_id) == 1
    await db.refresh(order)
    assert order.cj_payment_status == "PAID" and order.fulfillment_status == "PROCESSING"
    assert fake_cj.count("/shopping/order/createOrderV2") == 1 and fake_cj.count("/shopping/pay/payBalance") == 2


@pytest.mark.asyncio
async def test_scenario6_admin_pays_on_cj_page_and_sync_detects_it(db, organization_id, fake_cj):
    _admin, _customer, order = await _paid_order(db, organization_id, fake_cj)
    order = await cj_service.forward_order(db, organization_id=organization_id, order_id=order.id, actor_user_id=None)
    assert order.cj_payment_status == "PAYMENT_REQUIRED"
    fake_cj.remote_orders[f"SOSNET-{order.id}"]["orderStatus"] = "UNSHIPPED"  # paid by card on CJ's page
    assert await cj_service.sync_orders(db, organization_id=organization_id) == 1
    await db.refresh(order)
    assert order.cj_payment_status == "PAID" and order.fulfillment_status == "PROCESSING"
    assert (await cj_service.order_read_dict(db, order, admin=False))["delivery_status"] == "PREPARING"
    with pytest.raises(cj_service.CjValidationError):
        await cj_service.forward_order(db, organization_id=organization_id, order_id=order.id, actor_user_id=None)
    fake_cj.balance = 100.0
    assert await cj_service.retry_due_orders(db, organization_id=organization_id) == 0
    assert fake_cj.count("/shopping/pay/payBalance") == 0 and fake_cj.balance == 100.0


@pytest.mark.asyncio
async def test_scenario6b_balance_topped_up_is_spent_once_oldest_first(db, organization_id, fake_cj):
    admin = await _user(db, organization_id, "ADMIN")
    customer = await _user(db, organization_id)
    _row, _product, variants = await _shop(db, organization_id, admin, auto_forward=True)
    orders = []
    for _ in range(2):
        order = await cj_service.create_order(
            db, organization_id=organization_id, customer_user_id=customer.id, variant_id=variants["V1"].id,
            quantity=1, address=ADDRESS, credit_applied_cents=0, payment_method="BANK_TRANSFER",
            actor_user_id=customer.id, otp_code=None, note=None,
        )
        order.status, order.paid_at = "PAID", utcnow()
        await db.commit()
        orders.append(await cj_service.forward_order(db, organization_id=organization_id, order_id=order.id, actor_user_id=None))
    assert [o.cj_payment_status for o in orders] == ["PAYMENT_REQUIRED", "PAYMENT_REQUIRED"]
    summary = await cj_service.cash_requirement(db, organization_id=organization_id, refresh_balance=True)
    assert summary["required_usd"] == 35.62 and summary["shortfall_usd"] == 35.62
    fake_cj.balance = 20.0  # enough for one
    for o in orders:
        o.next_retry_at = utcnow() - timedelta(minutes=1)
    await db.commit()
    assert await cj_service.retry_due_orders(db, organization_id=organization_id) == 1
    for o in orders:
        await db.refresh(o)
    assert [o.cj_payment_status for o in orders] == ["PAID", "PAYMENT_REQUIRED"]
    assert fake_cj.count("/shopping/pay/payBalance") == 1 and fake_cj.balance == 2.19


@pytest.mark.asyncio
async def test_scenario7_tracking_reaches_the_customer(db, organization_id, fake_cj):
    fake_cj.balance = 100.0
    _admin, customer, order = await _paid_order(db, organization_id, fake_cj)
    await cj_service.forward_order(db, organization_id=organization_id, order_id=order.id, actor_user_id=None)
    remote = fake_cj.remote_orders[f"SOSNET-{order.id}"]
    remote.update({"orderStatus": "SHIPPED", "trackNumber": "LP123IT", "trackingProvider": "PostNL"})
    assert await cj_service.sync_orders(db, organization_id=organization_id) == 1
    await db.refresh(order)
    assert order.fulfillment_status == "SHIPPED" and order.tracking_number == "LP123IT" and order.shipped_at
    notes = (
        await db.execute(
            select(Notification).where(Notification.recipient_user_id == customer.id, Notification.type == "ORDER_SHIPPED")
        )
    ).scalars().all()
    assert len(notes) == 1
    read = await cj_service.order_read_dict(db, order, admin=False)
    assert read["delivery_status"] == "SHIPPED" and read["tracking_url"].endswith("LP123IT")
    assert await cj_service.sync_orders(db, organization_id=organization_id) == 0  # nobody notified twice


@pytest.mark.asyncio
async def test_scenario8_two_processes_one_order_handled_once(db, organization_id, fake_cj):
    fake_cj.balance = 100.0
    _admin, _customer, order = await _paid_order(db, organization_id, fake_cj)
    # Another process holds the order.
    order.fulfillment_status = "SENDING"
    order.last_attempt_at = utcnow()
    await db.commit()
    with pytest.raises(cj_service.CjValidationError):
        await cj_service.forward_order(db, organization_id=organization_id, order_id=order.id, actor_user_id=None)
    assert fake_cj.calls_to_orders() == 0
    # If that process died after CJ created the order, it is taken over after 10 minutes without duplicates.
    fake_cj.remote_orders[f"SOSNET-{order.id}"] = {
        "orderId": "999", "cjOrderCode": "SD0999", "orderNum": f"SOSNET-{order.id}", "orderStatus": "UNPAID",
        "orderAmount": 17.81,
    }
    order.last_attempt_at = utcnow() - timedelta(minutes=15)
    await db.commit()
    order = await cj_service.forward_order(db, organization_id=organization_id, order_id=order.id, actor_user_id=None)
    assert fake_cj.count("/shopping/order/createOrderV2") == 0
    assert order.cj_order_code == "SD0999" and order.cj_payment_status == "PAID"


def test_error_classification():
    assert cj_service.classify_error(cj_client.CjApiError("CJ non risponde (ReadTimeout).")) == "TEMPORARY"
    assert cj_service.classify_error(cj_client.CjApiError("CJ: Insufficient balance", code=1603001)) == "INSUFFICIENT_BALANCE"
    assert cj_service.classify_error(cj_client.CjApiError("CJ: token invalid", code=1600001)) == "AUTHENTICATION"
    assert cj_service.classify_error(cj_client.CjApiError("CJ: Param error", code=1600100)) == "VALIDATION"


@pytest.mark.asyncio
async def test_orders_of_a_switched_off_shop_cannot_be_placed(db, organization_id, fake_cj):
    admin = await _user(db, organization_id, "ADMIN")
    customer = await _user(db, organization_id)
    row, _product, variants = await _shop(db, organization_id, admin)
    await cj_service.update_settings(db, row=row, updates={"enabled": False}, actor_user_id=admin.id)
    with pytest.raises(cj_service.CjValidationError):
        await cj_service.get_quote(
            db, organization_id=organization_id, customer_user_id=customer.id, variant_id=variants["V1"].id, quantity=1
        )
    assert (await db.execute(select(CjOrder))).first() is None


@pytest.mark.asyncio
async def test_real_sized_cj_tokens_are_stored(db, organization_id, monkeypatch):
    """CJ JWT tokens exceed 500 characters and must be stored in full."""
    long_token = "API@CJ1@CJ:" + "x" * 900

    async def raw_call(method, path, **kwargs):
        if path == "/authentication/getAccessToken":
            return {"code": 200, "data": {
                "accessToken": long_token, "refreshToken": long_token, "openId": 51143,
                "accessTokenExpiryDate": "2027-03-16T02:28:23+08:00", "refreshTokenExpiryDate": "2027-03-16T02:28:23+08:00",
            }}
        return {"code": 200, "data": {"amount": 12.5}}

    monkeypatch.setattr(cj_client, "_raw_call", raw_call)
    row = await cj_service.get_settings_row(db, organization_id=organization_id)
    row.api_key = "CJ1@api@key"
    await db.commit()
    read = await cj_service.test_connection(db, row=row)
    assert read["connected"] is True
    assert read["last_balance_usd"] == 12.5
    await db.refresh(row)
    assert row.access_token == long_token and row.open_id == "51143"


def test_stock_comes_from_the_inventory_endpoint_and_picks_the_nearest_warehouse():
    """CJ's product detail has inventories=null; stock comes only from
    getInventoryByPid. Ships from the warehouse covering most variants, the
    nearest on a tie."""
    detail = {"variants": [{"vid": "A", "inventories": None}, {"vid": "B", "inventories": None}]}
    inventory = {"variantInventories": [
        {"vid": "A", "inventory": [{"countryCode": "CN", "totalInventory": 40000}, {"countryCode": "DE", "totalInventory": 12}]},
        {"vid": "B", "inventory": [{"countryCode": "CN", "totalInventory": 7}]},
    ]}
    stock = cj_service._stock_by_variant(detail, inventory)
    assert stock["A"] == {"CN": 40000, "DE": 12}
    # B is only in China: shipping from Germany would show B as sold out.
    assert cj_service._choose_origin(stock, inventory) == "CN"
    both_in_de = {"A": {"CN": 5, "DE": 3}, "B": {"CN": 5, "DE": 9}}
    assert cj_service._choose_origin(both_in_de, None) == "DE"
    assert cj_service._choose_origin(cj_service._stock_by_variant(detail, None), None) == "CN"



# --- Bank transfer costs 5% less (never a card surcharge) ---------------------------------


def test_bank_transfer_discount_is_the_percentage_of_the_residual_rounded_half_up():
    assert pricing.bank_transfer_discount_cents(residual_cents=2000, percentage=5) == 100
    assert pricing.bank_transfer_discount_cents(residual_cents=250, percentage=5) == 13  # 12.5 -> 13
    assert pricing.bank_transfer_discount_cents(residual_cents=249, percentage=5) == 12  # 12.45 -> 12
    assert pricing.bank_transfer_discount_cents(residual_cents=0, percentage=5) == 0
    assert pricing.bank_transfer_discount_cents(residual_cents=2000, percentage=0) == 0


async def _card_ready(db, organization_id, monkeypatch):
    import stripe

    from app.modules.organizations.models import Organization

    org = await db.get(Organization, organization_id)
    org.settings = {**(org.settings or {}), "stripe_secret_key": "sk_test_fake", "stripe_publishable_key": "pk_test_fake"}
    await db.commit()
    created = []

    class _Session:
        def __init__(self, n):
            self.id = f"cs_cj_{n}_{uuid.uuid4().hex[:6]}"
            self.url = f"https://stripe.example/{self.id}"

    monkeypatch.setattr(
        stripe.checkout.Session, "create", staticmethod(lambda **p: created.append(p) or _Session(len(created)))
    )
    return created


@pytest.mark.asyncio
async def test_bank_transfer_costs_five_percent_less_on_the_residual_only(db, organization_id, fake_cj, monkeypatch):
    from app.modules.payments import service as payments_service

    created = await _card_ready(db, organization_id, monkeypatch)
    admin = await _user(db, organization_id, "ADMIN")
    customer = await _user(db, organization_id)
    _row, _product, variants = await _shop(db, organization_id, admin)
    wallet = await wallet_service.get_or_create_wallet(db, organization_id=organization_id, user_id=customer.id)
    await wallet_service.credit_wallet(
        db, organization_id=organization_id, wallet_id=wallet.id, amount_cents=1299, type_="ADMIN_CREDIT",
        actor_user_id=admin.id, idempotency_key=str(uuid.uuid4()),
    )

    quote = await cj_service.get_quote(
        db, organization_id=organization_id, customer_user_id=customer.id, variant_id=variants["V1"].id, quantity=2
    )
    assert quote["amount_cents"] == _con_iva(2580) + 719
    assert quote["bank_transfer_discount_percentage"] == 5
    assert quote["bank_transfer_amount_cents"] == quote["amount_cents"] - (quote["amount_cents"] * 5 + 50) // 100

    await _otp(db, customer.id)
    order = await cj_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, variant_id=variants["V1"].id,
        quantity=2, address=ADDRESS, credit_applied_cents=quote["max_creditable_cents"], payment_method="CARD",
        actor_user_id=customer.id, otp_code=OTP, note=None,
    )
    # Cap: 50% of the goods, shipping excluded.
    assert order.credit_applied_cents == 1290
    residuo = quote["amount_cents"] - 1290
    # Card pays exactly the price shown, with no surcharge.
    assert order.bank_transfer_discount_cents == 0
    assert cj_service.amount_due_cents(order) == residuo
    assert created[-1]["line_items"][0]["price_data"]["unit_amount"] == residuo
    assert "description" not in created[-1]["line_items"][0]["price_data"]["product_data"]

    # Bank transfer takes 5% off the residual only: SosnetCash is never discounted.
    await cj_service.change_payment_method(
        db, organization_id=organization_id, order=order, new_payment_method="BANK_TRANSFER"
    )
    sconto = (residuo * 5 + 50) // 100
    assert order.bank_transfer_discount_cents == sconto
    assert cj_service.amount_due_cents(order) == residuo - sconto
    read = await cj_service.order_read_dict(db, order, admin=False)
    assert read["bank_transfer_discount_cents"] == sconto and read["amount_due_cents"] == residuo - sconto

    # Back to card (Stripe checkout): the discount is removed.
    url = await payments_service.create_checkout_session_for_cj_order(
        db, organization_id=organization_id, order=order, success_url="https://x/ok", cancel_url="https://x/ko",
    )
    assert url.startswith("https://stripe.example/")
    await db.refresh(order)
    assert order.payment_method == "CARD" and order.bank_transfer_discount_cents == 0
    assert created[-1]["line_items"][0]["price_data"]["unit_amount"] == residuo

    await cj_service.mark_paid_via_stripe(
        db, organization_id=organization_id, stripe_checkout_session_id=order.stripe_checkout_session_id
    )
    movements = await accounting_service.list_my_movements(db, organization_id=organization_id, user_id=customer.id)
    euro_rows = [m for m in movements if m["kind"] == "ORDER_PAYMENT" and m["order_id"] == order.id]
    assert euro_rows and euro_rows[0]["amount_cents"] == residuo


@pytest.mark.asyncio
async def test_card_has_no_discount_and_zero_percent_switches_it_off(db, organization_id, fake_cj, monkeypatch):
    await _card_ready(db, organization_id, monkeypatch)
    admin = await _user(db, organization_id, "ADMIN")
    customer = await _user(db, organization_id)
    _row, _product, variants = await _shop(db, organization_id, admin, bank_transfer_discount_percentage=0)
    bank = await cj_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, variant_id=variants["V1"].id,
        quantity=1, address=ADDRESS, credit_applied_cents=0, payment_method="BANK_TRANSFER",
        actor_user_id=customer.id, otp_code=None, note=None,
    )
    assert bank.bank_transfer_discount_cents == 0
    assert cj_service.amount_due_cents(bank) == bank.amount_cents

    from app.modules.marketplaces import rules

    await rules.update_config(db, organization_id=organization_id, labels=None, bank_transfer_discount_percentage=5)
    card = await cj_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, variant_id=variants["V1"].id,
        quantity=1, address=ADDRESS, credit_applied_cents=0, payment_method="CARD",
        actor_user_id=customer.id, otp_code=None, note=None,
    )
    assert card.bank_transfer_discount_cents == 0
    assert cj_service.amount_due_cents(card) == card.amount_cents


@pytest.mark.asyncio
async def test_a_new_product_starts_at_30_percent_sosnetcash_and_never_100(db, organization_id, fake_cj):
    """Marketplace products can never be bought entirely with SosnetCash; the
    default is 30% and the admin may raise it to anything below 100."""
    admin = await _user(db, organization_id, "ADMIN")
    row = await cj_service.get_settings_row(db, organization_id=organization_id)
    await cj_service.update_settings(
        db, row=row, actor_user_id=admin.id, updates={"api_key": "CJ123@api@secret-abcd", "auto_forward": False}
    )
    product = await cj_service.import_product(
        db, row=row, actor_user_id=admin.id, pid="P1", name="Auricolari", description=None,
        credit_discount_percentage=None, markup_percentage=None, vids=None, activate=True,
    )
    assert product.credit_discount_percentage == 30
    with pytest.raises(cj_service.CjValidationError):
        await cj_service.update_product(
            db, row=row, product=product, updates={"credit_discount_percentage": 100}, actor_user_id=admin.id
        )
    product = await cj_service.update_product(
        db, row=row, product=product, updates={"credit_discount_percentage": 80}, actor_user_id=admin.id
    )
    assert product.credit_discount_percentage == 80


# --- VAT ----------------------------------------------------------------------------------


def test_vat_included_is_the_tax_contained_in_the_price_rounded_half_up():
    """vat_included_cents extracts the VAT contained in a gross amount,
    gross x pct / (100 + pct), rounding half up."""
    from app.modules.marketplaces import rules

    assert rules.vat_included_cents(gross_cents=1220, percentage=22) == 220
    assert rules.vat_included_cents(gross_cents=1815, percentage=22) == 327
    # Half a cent rounds up, as on an invoice.
    assert rules.vat_included_cents(gross_cents=3, percentage=20) == 1
    assert rules.vat_included_cents(gross_cents=9, percentage=20) == 2
    assert rules.vat_included_cents(gross_cents=0, percentage=22) == 0
    assert rules.vat_included_cents(gross_cents=1220, percentage=0) == 0


@pytest.mark.asyncio
async def test_vat_is_frozen_with_the_discount_and_the_margin_is_net_of_it(
    db, organization_id, fake_cj, monkeypatch
):
    """VAT (22% by default) is added on the goods and frozen on the order.
    Neither the bank-transfer discount nor SosnetCash changes it, and the
    margin against CJ cost is measured on the taxable base, never on the gross."""
    from app.modules.marketplaces import rules
    from app.modules.payments import service as payments_service

    await _card_ready(db, organization_id, monkeypatch)
    admin = await _user(db, organization_id, "ADMIN")
    customer = await _user(db, organization_id)
    _row, _product, variants = await _shop(db, organization_id, admin)
    wallet = await wallet_service.get_or_create_wallet(db, organization_id=organization_id, user_id=customer.id)
    await wallet_service.credit_wallet(
        db, organization_id=organization_id, wallet_id=wallet.id, amount_cents=1000, type_="ADMIN_CREDIT",
        actor_user_id=admin.id, idempotency_key=str(uuid.uuid4()),
    )
    await _otp(db, customer.id)

    order = await cj_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, variant_id=variants["V1"].id,
        quantity=2, address=ADDRESS, credit_applied_cents=1000, payment_method="BANK_TRANSFER",
        actor_user_id=customer.id, otp_code=OTP, note=None,
    )
    assert order.bank_transfer_discount_cents == ((order.amount_cents - order.credit_applied_cents) * 5 + 50) // 100
    assert order.vat_percentage == 22
    assert order.vat_amount_cents == 568  # 22% of the goods
    # SosnetCash is a payment method, not a discount: VAT is not derived from
    # the amount actually transferred.
    assert order.vat_amount_cents != rules.vat_included_cents(
        gross_cents=cj_service.amount_due_cents(order), percentage=22
    )

    # Card: no discount, same VAT, same price.
    await cj_service.change_payment_method(
        db, organization_id=organization_id, order=order, new_payment_method="CARD"
    )
    assert order.bank_transfer_discount_cents == 0
    assert order.vat_amount_cents == 568
    assert cj_service.amount_due_cents(order) == (
        order.amount_cents - order.credit_applied_cents - order.bank_transfer_discount_cents
    )

    read = await cj_service.order_read_dict(db, order, admin=False)
    assert read["vat_percentage"] == 22 and read["vat_amount_cents"] == 568
    admin_read = await cj_service.order_read_dict(db, order, admin=True)
    # VAT never belongs to us, so margin is computed on the taxable base.
    assert admin_read["estimated_margin_cents"] == (
        cj_service.taxable_base_cents(order) - admin_read["cj_cost_cents"]
    )

    # The Stripe checkout re-freezes VAT together with the discount.
    await cj_service.change_payment_method(
        db, organization_id=organization_id, order=order, new_payment_method="BANK_TRANSFER"
    )
    assert order.vat_amount_cents == 568
    await payments_service.create_checkout_session_for_cj_order(
        db, organization_id=organization_id, order=order, success_url="https://x/ok", cancel_url="https://x/ko",
    )
    await db.refresh(order)
    assert order.bank_transfer_discount_cents == 0 and order.vat_amount_cents == 568


@pytest.mark.asyncio
async def test_vat_rate_is_a_setting_and_zero_switches_it_off(db, organization_id, fake_cj):
    from app.modules.marketplaces import rules

    admin = await _user(db, organization_id, "ADMIN")
    customer = await _user(db, organization_id)
    _row, _product, variants = await _shop(db, organization_id, admin)

    config = await rules.get_config(db, organization_id=organization_id)
    assert config["vat_percentage"] == 22

    # Out-of-range rates are clamped, not rejected, like the bank-transfer discount.
    config = await rules.update_config(
        db, organization_id=organization_id, labels=None, bank_transfer_discount_percentage=None, vat_percentage=99
    )
    assert config["vat_percentage"] == rules.MAX_VAT_PERCENTAGE

    await rules.update_config(
        db, organization_id=organization_id, labels=None, bank_transfer_discount_percentage=None, vat_percentage=0
    )
    order = await cj_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, variant_id=variants["V1"].id,
        quantity=1, address=ADDRESS, credit_applied_cents=0, payment_method="BANK_TRANSFER",
        actor_user_id=customer.id, otp_code=None, note=None,
    )
    assert order.vat_percentage == 0 and order.vat_amount_cents == 0
    admin_read = await cj_service.order_read_dict(db, order, admin=True)
    # With no VAT the taxable base is the discounted price.
    assert admin_read["estimated_margin_cents"] == (
        order.amount_cents - order.bank_transfer_discount_cents - admin_read["cj_cost_cents"]
    )


async def _two_cj_in_stock(db, variants):
    """The fake catalog has one sold-out variant; the cart needs two in stock."""
    due = list(variants.values())[:2]
    for v in due:
        v.inventory = 25
        v.active = True
    await db.commit()
    return due


# --- CJ cart ------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cj_cart_charges_one_shipping_for_the_whole_order(db, organization_id, fake_cj):
    """CJ quotes the whole cart in one call, so the customer pays one
    shipping for the order, not the (higher) sum of separate quotes."""
    admin = await _user(db, organization_id, "ADMIN")
    customer = await _user(db, organization_id)
    _row, _product, variants = await _shop(db, organization_id, admin)
    due = await _two_cj_in_stock(db, variants)
    if len(due) < 2:
        pytest.skip("il catalogo finto ha una variante sola")

    for v in due:
        await carts_service.add_item(
            db, organization_id=organization_id, customer_user_id=customer.id, shop="cj",
            variant_id=v.id, quantity=1,
        )
    summary = await carts_service.summary(db, organization_id=organization_id, customer_user_id=customer.id)
    sezione = summary["sections"][0]
    assert sezione["shop"] == "cj"
    assert len(sezione["items"]) == 2
    # One shipping per order.
    assert sezione["amount_cents"] == _con_iva(sezione["items_cents"]) + sezione["shipping_cents"]
    # SosnetCash cap is the sum of the line caps, shipping excluded.
    assert sezione["max_creditable_cents"] == sum(
        i["max_creditable_cents"] for i in sezione["items"]
    )


@pytest.mark.asyncio
async def test_cj_cart_becomes_one_order_with_every_line(db, organization_id, fake_cj):
    admin = await _user(db, organization_id, "ADMIN")
    customer = await _user(db, organization_id)
    _row, _product, variants = await _shop(db, organization_id, admin)
    due = await _two_cj_in_stock(db, variants)
    if len(due) < 2:
        pytest.skip("il catalogo finto ha una variante sola")
    for v in due:
        await carts_service.add_item(
            db, organization_id=organization_id, customer_user_id=customer.id, shop="cj",
            variant_id=v.id, quantity=1,
        )
    _cart, lines = await carts_service.checkout_lines(db, customer_user_id=customer.id, shop="cj")
    order = await cj_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, lines=lines, address=ADDRESS,
        credit_applied_cents=0, payment_method="BANK_TRANSFER", actor_user_id=customer.id,
        otp_code=None, note=None,
    )
    items = await cj_service.order_items(db, order)
    assert len(items) == 2
    assert {i.variant_id for i in items} == {v.id for v in due}
    # The CJ request body carries every line.
    body = await cj_service._create_body(db, order)
    assert len(body["products"]) == 2
    # The order has a human-readable number.
    await db.refresh(order)
    assert order.number and cj_service.order_code(order) == str(order.number)
