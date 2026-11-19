import logging
import uuid

import stripe
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.foundation.config import get_settings
from app.foundation.db import utcnow
from app.foundation.email import send_html_email_best_effort
from app.foundation.email_templates import render_email
from app.modules.catalog.models import Product, ProductVersion
from app.modules.customers.models import Company, Customer, CustomerProfile
from app.modules.customers.service import display_name_for
from app.modules.network.models import AgentProfile
from app.modules.notifications import service as notifications_service
from app.modules.orders.models import ORDER_PAYMENT_METHODS, Order
from app.modules.organizations import service as organizations_service
from app.modules.users.models import User
from app.modules.wallets import service as wallets_service

logger = logging.getLogger(__name__)


class OrderError(Exception):
    pass


class ProductNotEligibleError(OrderError):
    pass


class InvalidCreditAmountError(OrderError):
    pass


class InvalidOrderStateError(OrderError):
    pass


class InvalidPaymentMethodError(OrderError):
    pass


class PaymentMethodNotAvailableError(OrderError):
    pass


class PaymentProofError(OrderError):
    """Unsupported or oversized file, or an order that is not an
    AWAITING_PAYMENT bank-transfer order."""


class CashbackNotAvailableError(OrderError):
    """Cashback requested but the product does not offer it, or wallet
    credit already covers the whole price."""


class InvalidOtpError(OrderError):
    """Self-checkout spends wallet credit without a valid, fresh OTP."""


# Flat surcharge the customer pays on the new-money residual to opt into
# instant cashback; not configurable per product. Intentionally independent
# of invoice_redemptions' CASHBACK_PERCENTAGE even though both are 5%.
ORDER_CASHBACK_PERCENTAGE = 5


async def _get_sellable_product_version(
    db: AsyncSession, *, organization_id: uuid.UUID, product_version_id: uuid.UUID
) -> tuple[ProductVersion, Product]:
    version = await db.get(ProductVersion, product_version_id)
    if version is None:
        raise ProductNotEligibleError("Product version not found")
    product = await db.get(Product, version.product_id)
    if product is None or product.organization_id != organization_id:
        raise ProductNotEligibleError("Product version not found")
    if product.category == "INTERNAL":
        raise ProductNotEligibleError(
            "I prodotti Interno SOSNET si acquistano come contratto, non come ordine -- vedi POST /contracts."
        )
    return version, product


def max_creditable_cents(*, amount_cents: int, credit_discount_percentage: int) -> int:
    return round(amount_cents * credit_discount_percentage / 100)


async def get_available_payment_methods(db: AsyncSession, *, organization_id: uuid.UUID) -> dict:
    """Residual payment methods enabled for the organization. Read by both
    create_order (enforcement) and the quote endpoints (UI)."""
    return {
        "bank_transfer": await organizations_service.is_bank_transfer_configured(db, organization_id=organization_id),
        "card": await organizations_service.is_stripe_configured(db, organization_id=organization_id),
    }


async def get_quote(
    db: AsyncSession, *, organization_id: uuid.UUID, customer_user_id: uuid.UUID, product_version_id: uuid.UUID
) -> dict:
    version, _product = await _get_sellable_product_version(
        db, organization_id=organization_id, product_version_id=product_version_id
    )
    wallet = await wallets_service.get_wallet_by_user_id(
        db, organization_id=organization_id, user_id=customer_user_id
    )
    methods = await get_available_payment_methods(db, organization_id=organization_id)
    return {
        "product_version_id": version.id,
        "product_name": version.name,
        "amount_cents": version.base_price_cents,
        "credit_discount_percentage": version.credit_discount_percentage,
        "max_creditable_cents": max_creditable_cents(
            amount_cents=version.base_price_cents, credit_discount_percentage=version.credit_discount_percentage
        ),
        "customer_wallet_balance_cents": wallet.balance_cents if wallet else 0,
        "bank_transfer_available": methods["bank_transfer"],
        "card_available": methods["card"],
        "cashback_available": version.cashback_enabled,
        "cashback_percentage": ORDER_CASHBACK_PERCENTAGE,
    }


async def _resolve_display_name(db: AsyncSession, *, organization_id: uuid.UUID, user_id: uuid.UUID) -> str:
    """Mirrors the helper in invoice_redemptions/service.py; kept local
    rather than importing a private cross-domain helper."""
    agent = (
        await db.execute(
            select(AgentProfile.display_name).where(
                AgentProfile.organization_id == organization_id, AgentProfile.user_id == user_id
            )
        )
    ).scalar_one_or_none()
    if agent:
        return agent

    customer = (
        await db.execute(
            select(Customer).where(Customer.organization_id == organization_id, Customer.user_id == user_id)
        )
    ).scalar_one_or_none()
    if customer is not None:
        profile = await db.get(CustomerProfile, customer.id)
        company = await db.get(Company, customer.id)
        name = display_name_for(customer.kind, profile, company)
        if name != "—":
            return name

    user = await db.get(User, user_id)
    return user.email if user else "—"


async def to_read_dict(db: AsyncSession, order: Order) -> dict:
    version = await db.get(ProductVersion, order.product_version_id)
    customer_name = await _resolve_display_name(
        db, organization_id=order.organization_id, user_id=order.customer_user_id
    )
    return {
        "id": order.id,
        "customer_user_id": order.customer_user_id,
        "customer_display_name": customer_name,
        "product_version_id": order.product_version_id,
        "product_name": version.name if version else "—",
        "product_image_url": version.image_url if version else None,
        "created_by_user_id": order.created_by_user_id,
        "amount_cents": order.amount_cents,
        "credit_applied_cents": order.credit_applied_cents,
        # New money actually owed (bank transfer or card), cashback surcharge
        # included.
        "residual_amount_cents": order.amount_cents - order.credit_applied_cents + order.cashback_surcharge_cents,
        "cashback_requested": order.cashback_requested,
        "cashback_surcharge_cents": order.cashback_surcharge_cents,
        "cashback_credited_at": order.cashback_credited_at,
        "status": order.status,
        "payment_method": order.payment_method,
        "stripe_checkout_session_id": order.stripe_checkout_session_id,
        "payment_proof_uploaded_at": order.payment_proof_uploaded_at,
        "note": order.note,
        "paid_at": order.paid_at,
        "cancelled_at": order.cancelled_at,
        "cancellation_reason": order.cancellation_reason,
        "created_at": order.created_at,
    }


async def hydrate(db: AsyncSession, orders: list[Order]) -> list[dict]:
    return [await to_read_dict(db, o) for o in orders]


async def create_order(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    customer_user_id: uuid.UUID,
    product_version_id: uuid.UUID,
    credit_applied_cents: int,
    actor_user_id: uuid.UUID,
    payment_method: str = "BANK_TRANSFER",
    note: str | None = None,
    cashback_requested: bool = False,
    otp_code: str | None = None,
    require_otp_for_credit_spend: bool = True,
) -> Order:
    """Create an order, optionally spending wallet credit.

    Self-checkout keeps require_otp_for_credit_spend=True so a stolen session
    alone cannot drain a wallet. The staff endpoint passes False: the action is
    already permissioned and audited, and the OTP would reach the customer's
    inbox, not the admin's."""
    version, _product = await _get_sellable_product_version(
        db, organization_id=organization_id, product_version_id=product_version_id
    )
    amount_cents = version.base_price_cents
    cap = max_creditable_cents(amount_cents=amount_cents, credit_discount_percentage=version.credit_discount_percentage)
    if credit_applied_cents < 0 or credit_applied_cents > cap:
        raise InvalidCreditAmountError(
            f"credit_applied_cents must be between 0 and {cap} for this product ({version.credit_discount_percentage}% of {amount_cents})"
        )

    if credit_applied_cents > 0 and require_otp_for_credit_spend:
        from app.modules.auth import service as auth_service

        if not otp_code or not await auth_service.verify_otp(
            db, user_id=customer_user_id, purpose=auth_service.WALLET_CREDIT_SPEND_OTP_PURPOSE, code=otp_code
        ):
            raise InvalidOtpError("Codice di conferma mancante, non valido o scaduto.")

    # The pre-surcharge residual is the base for any cashback credit. Using the
    # full amount_cents instead would let a customer mint credit from credit
    # already spent.
    residual_before_cashback = amount_cents - credit_applied_cents
    cashback_surcharge_cents = 0
    if cashback_requested:
        if not version.cashback_enabled:
            raise CashbackNotAvailableError("Questo prodotto non consente il cashback.")
        if residual_before_cashback <= 0:
            raise CashbackNotAvailableError(
                "Il cashback richiede un pagamento residuo maggiore di zero -- il credito wallet copre già l'intero importo."
            )
        cashback_surcharge_cents = round(residual_before_cashback * ORDER_CASHBACK_PERCENTAGE / 100)

    total_to_charge = residual_before_cashback + cashback_surcharge_cents

    # Payment method only matters when something will be charged; a
    # fully credit-paid order goes straight to PAID, so don't validate it then.
    if total_to_charge > 0:
        if payment_method not in ORDER_PAYMENT_METHODS:
            raise InvalidPaymentMethodError(f"payment_method must be one of {ORDER_PAYMENT_METHODS}")
        available = await get_available_payment_methods(db, organization_id=organization_id)
        if payment_method == "BANK_TRANSFER" and not available["bank_transfer"]:
            raise PaymentMethodNotAvailableError("Il pagamento con bonifico non è configurato.")
        if payment_method == "CARD" and not available["card"]:
            raise PaymentMethodNotAvailableError("Il pagamento con carta non è configurato.")

    wallet = None
    if credit_applied_cents > 0:
        # Pre-check before creating the order so a failed debit leaves no Order
        # row without an explicit rollback (which would clash with SAVEPOINT-based
        # test sessions). A concurrent debit racing this check is still rejected by
        # the compare-and-set in debit_wallet_for_purchase.
        wallet = await wallets_service.get_or_create_wallet(
            db, organization_id=organization_id, user_id=customer_user_id
        )
        if wallet.balance_cents < credit_applied_cents:
            raise wallets_service.InsufficientBalanceError("Insufficient balance")

    order = Order(
        organization_id=organization_id,
        customer_user_id=customer_user_id,
        product_version_id=product_version_id,
        created_by_user_id=actor_user_id,
        amount_cents=amount_cents,
        credit_applied_cents=credit_applied_cents,
        cashback_requested=cashback_requested,
        cashback_surcharge_cents=cashback_surcharge_cents,
        status="AWAITING_PAYMENT",
        payment_method=payment_method,
        note=note,
    )
    db.add(order)
    await db.flush()  # assigns order.id, no commit yet

    # Staff notification, added before commit so it shares the order's
    # transaction.
    await notifications_service.notify_roles(
        db, organization_id=organization_id, roles=notifications_service.STAFF_NOTIFY_ROLES,
        type_="ORDER_CREATED", entity_type="order", entity_id=order.id,
        title=f"Nuovo ordine: {version.name}", body=f"{amount_cents / 100:.2f} EUR -- {payment_method}",
        exclude_user_id=actor_user_id,
    )

    if credit_applied_cents > 0:
        assert wallet is not None
        if total_to_charge == 0:
            order.status = "PAID"
            order.paid_by_user_id = actor_user_id
            order.paid_at = utcnow()
        # debit_wallet_for_purchase commits: order row, PAID transition and
        # debit land atomically.
        debit_txn = await wallets_service.debit_wallet_for_purchase(
            db, organization_id=organization_id, wallet_id=wallet.id, amount_cents=credit_applied_cents,
            reference_order_id=order.id, actor_user_id=actor_user_id,
            note=f"Ordine {version.name}", idempotency_key=f"order:{order.id}:credit",
        )
        order.credit_debit_transaction_id = debit_txn.id
        await db.commit()
        await db.refresh(order)
    else:
        await db.commit()
        await db.refresh(order)

    await _send_order_confirmation_email(db, organization_id=organization_id, order=order, version=version)
    return order


async def _send_order_confirmation_email(
    db: AsyncSession, *, organization_id: uuid.UUID, order: Order, version: ProductVersion
) -> None:
    """Best-effort "order received" email, sent after commit so SMTP or
    Stripe failures never undo the order. Includes the IBAN for bank
    transfer, or a fresh Stripe Checkout link for card; a later session
    created from the dashboard supersedes it for webhook matching."""
    user = await db.get(User, order.customer_user_id)
    if user is None:
        return

    settings = get_settings()
    residual_cents = order.amount_cents - order.credit_applied_cents + order.cashback_surcharge_cents
    order_code = str(order.id)[:8].upper()
    order_code_line = f"<p>Numero ordine: <strong>#{order_code}</strong></p>"
    cashback_line = (
        f"<p>Include il {ORDER_CASHBACK_PERCENTAGE}% per il cashback che riceverai come SosnetCash "
        "non appena il pagamento sarà confermato.</p>"
        if order.cashback_requested else ""
    )
    cta_label: str | None = None
    cta_url: str | None = None

    if order.status == "PAID":
        heading = "Ordine confermato"
        body_html = (
            order_code_line
            + f"<p>Il tuo ordine per <strong>{version.name}</strong> è confermato.</p>"
            f"<p>Totale: {order.amount_cents / 100:.2f} &euro;"
            + (f" (di cui {order.credit_applied_cents / 100:.2f} SosnetCash)" if order.credit_applied_cents else "")
            + "</p><p>Non è richiesto alcun pagamento aggiuntivo.</p>"
        )
    elif order.payment_method == "CARD":
        from app.modules.payments import service as payments_service

        heading = "Completa il pagamento del tuo ordine"
        body_html = (
            order_code_line
            + f"<p>Il tuo ordine per <strong>{version.name}</strong> è stato registrato.</p>"
            f"<p>Da pagare: <strong>{residual_cents / 100:.2f} &euro;</strong>"
            + (f" (dopo {order.credit_applied_cents / 100:.2f} SosnetCash già applicati)" if order.credit_applied_cents else "")
            + "</p>"
            + cashback_line
            + "<p>Completa il pagamento con carta cliccando il pulsante qui sotto.</p>"
        )
        try:
            cta_url = await payments_service.create_checkout_session_for_order(
                db, organization_id=organization_id, order=order,
                success_url=f"{settings.public_app_base_url}/customer",
                cancel_url=f"{settings.public_app_base_url}/customer",
            )
            cta_label = "Paga con carta"
        except payments_service.StripeNotConfiguredError:
            logger.warning("Order %s confirmation email sent without a Stripe link (Stripe not configured)", order.id)
        except stripe.error.StripeError:
            # Stripe failures must not affect the committed order; the customer can
            # still pay later from their orders page, which creates a new session.
            logger.exception("Order %s confirmation email sent without a Stripe link (Stripe API error)", order.id)
    else:
        bank_settings = await organizations_service.get_settings(db, organization_id=organization_id)
        iban = bank_settings.get("bank_iban")
        heading = "Completa il pagamento del tuo ordine"
        body_html = (
            order_code_line
            + f"<p>Il tuo ordine per <strong>{version.name}</strong> è stato registrato.</p>"
            f"<p>Da pagare tramite bonifico: <strong>{residual_cents / 100:.2f} &euro;</strong>"
            + (f" (dopo {order.credit_applied_cents / 100:.2f} SosnetCash già applicati)" if order.credit_applied_cents else "")
            + "</p>"
            + cashback_line
        )
        if iban:
            body_html += (
                f"<p><strong>IBAN:</strong> {iban}<br>"
                f"<strong>Intestatario:</strong> {bank_settings.get('bank_account_holder') or 'SOSNET'}<br>"
                f"<strong>Causale:</strong> Ordine {order_code}</p>"
            )
            if bank_settings.get("bank_transfer_instructions"):
                body_html += f"<p>{bank_settings['bank_transfer_instructions']}</p>"
        else:
            body_html += "<p>Contatta l'amministrazione per le coordinate bancarie.</p>"

    html = render_email(
        preheader=f"Riepilogo del tuo ordine -- {version.name}",
        heading=heading,
        body_html=body_html,
        cta_label=cta_label,
        cta_url=cta_url,
    )
    send_html_email_best_effort(
        context=f"Order confirmation email (order={order.id})",
        to=user.email,
        subject=f"Conferma ordine - {version.name} - SOSNET",
        html_body=html,
        text_body=f"{heading}: {version.name}, totale {order.amount_cents / 100:.2f} EUR.",
    )


async def _send_order_paid_email(
    db: AsyncSession, *, order: Order, version: ProductVersion | None
) -> None:
    """Best-effort "payment received" email, sent after the order is
    committed PAID. Shared by bank-transfer confirmation and Stripe
    confirmation; only the method label differs."""
    user = await db.get(User, order.customer_user_id)
    if user is None:
        return

    method_label = "Carta (Stripe)" if order.payment_method == "CARD" else "Bonifico bancario"
    product_name = version.name if version else "un prodotto"
    paid_at_label = order.paid_at.strftime("%d/%m/%Y %H:%M") if order.paid_at else "-"
    # New money actually charged, which credit and cashback can make differ
    # from the product price.
    amount_paid_cents = order.amount_cents - order.credit_applied_cents + order.cashback_surcharge_cents
    cashback_credited_line = ""
    if order.cashback_requested and order.cashback_credited_at:
        total_cashback_cents = (order.amount_cents - order.credit_applied_cents) + order.cashback_surcharge_cents
        cashback_credited_line = (
            f"<p>Hai ricevuto <strong>{total_cashback_cents / 100:.2f} SosnetCash</strong> sul tuo wallet.</p>"
        )
    body_html = (
        "<p>Il pagamento del tuo ordine &egrave; stato confermato.</p>"
        f"<p><strong>Numero ordine:</strong> #{str(order.id)[:8].upper()}<br>"
        f"<strong>Prodotto:</strong> {product_name}<br>"
        f"<strong>Importo pagato:</strong> {amount_paid_cents / 100:.2f} &euro;<br>"
        f"<strong>Metodo di pagamento:</strong> {method_label}<br>"
        "<strong>Stato:</strong> Pagato<br>"
        f"<strong>Data:</strong> {paid_at_label}</p>"
        + cashback_credited_line
    )
    html = render_email(
        preheader="Pagamento completato con successo",
        heading="Pagamento completato con successo",
        body_html=body_html,
        cta_label="Vai ai miei ordini",
        cta_url=f"{get_settings().public_app_base_url}/customer?tab=orders",
    )
    send_html_email_best_effort(
        context=f"Order-paid email (order={order.id})",
        to=user.email,
        subject=f"Pagamento confermato - Ordine {str(order.id)[:8]} - SOSNET",
        html_body=html,
        text_body=(
            f"Pagamento completato con successo. Ordine {order.id}, {product_name}, "
            f"{order.amount_cents / 100:.2f} EUR, {method_label}."
        ),
    )


async def get_org_scoped(db: AsyncSession, *, organization_id: uuid.UUID, order_id: uuid.UUID) -> Order | None:
    order = await db.get(Order, order_id)
    if order is None or order.organization_id != organization_id:
        return None
    return order


async def get_owned(
    db: AsyncSession, *, organization_id: uuid.UUID, customer_user_id: uuid.UUID, order_id: uuid.UUID
) -> Order | None:
    """Look up an order owned by the given customer, so "my order" actions
    can never reach someone else's order by id."""
    order = await get_org_scoped(db, organization_id=organization_id, order_id=order_id)
    if order is None or order.customer_user_id != customer_user_id:
        return None
    return order


async def list_orders(
    db: AsyncSession, *, organization_id: uuid.UUID, status_filter: str | None = None
) -> list[Order]:
    stmt = select(Order).where(Order.organization_id == organization_id)
    if status_filter:
        stmt = stmt.where(Order.status == status_filter)
    stmt = stmt.order_by(Order.created_at.desc())
    return list((await db.execute(stmt)).scalars().all())


async def list_orders_for_customer(
    db: AsyncSession, *, organization_id: uuid.UUID, customer_user_id: uuid.UUID
) -> list[Order]:
    stmt = (
        select(Order)
        .where(Order.organization_id == organization_id, Order.customer_user_id == customer_user_id)
        .order_by(Order.created_at.desc())
    )
    return list((await db.execute(stmt)).scalars().all())


async def _credit_order_cashback(
    db: AsyncSession, *, organization_id: uuid.UUID, order: Order, version: ProductVersion | None,
    actor_user_id: uuid.UUID | None,
) -> None:
    """Credit instant cashback once an opted-in order is PAID.

    Two wallet rows: the pre-surcharge residual (base) and the surcharge
    (bonus), so the ledger shows the split. The total never exceeds the new
    money paid on this order, so credit cannot be minted from credit.

    Idempotent via the cashback_credited_at guard and, independently, the
    order-derived idempotency key in credit_wallet, so Stripe webhook
    retries are no-ops."""
    from app.modules.organizations import service as _organizations_service

    if not await _organizations_service.is_feature_enabled(db, organization_id=organization_id, name="wallet"):
        return  # SosnetCash is switched off: nothing to credit.
    if not order.cashback_requested or order.cashback_credited_at is not None:
        return
    base_cents = order.amount_cents - order.credit_applied_cents
    bonus_cents = order.cashback_surcharge_cents
    if base_cents <= 0 or bonus_cents <= 0:
        # Defensive: create_order already rejects cashback without a residual.
        return

    product_name = version.name if version else "un prodotto"
    wallet = await wallets_service.get_or_create_wallet(
        db, organization_id=organization_id, user_id=order.customer_user_id
    )
    await wallets_service.credit_wallet(
        db, organization_id=organization_id, wallet_id=wallet.id, amount_cents=base_cents,
        type_="ADMIN_CREDIT", actor_user_id=actor_user_id, source="ORDER_CASHBACK_BASE",
        reference_order_id=order.id, note=f"Cashback ordine {product_name}",
        idempotency_key=f"order:{order.id}:cashback-base",
    )
    await wallets_service.credit_wallet(
        db, organization_id=organization_id, wallet_id=wallet.id, amount_cents=bonus_cents,
        type_="ADMIN_CREDIT", actor_user_id=actor_user_id, source="ORDER_CASHBACK_BONUS",
        reference_order_id=order.id, note=f"Bonus {ORDER_CASHBACK_PERCENTAGE}% cashback ordine {product_name}",
        idempotency_key=f"order:{order.id}:cashback-bonus",
    )
    order.cashback_credited_at = utcnow()


async def confirm_payment(
    db: AsyncSession, *, organization_id: uuid.UUID, order_id: uuid.UUID, actor_user_id: uuid.UUID
) -> Order:
    order = await get_org_scoped(db, organization_id=organization_id, order_id=order_id)
    if order is None:
        raise OrderError("Order not found")
    if order.status != "AWAITING_PAYMENT":
        raise InvalidOrderStateError(f"Cannot confirm payment for an order in status {order.status}")
    if order.payment_method == "CARD":
        # Manual bank-transfer confirmation only. CARD orders reach PAID solely
        # through the Stripe webhook; enforcing it here (not just in the UI)
        # means an admin can never mark a card order paid without Stripe.
        raise InvalidOrderStateError(
            "Questo ordine si paga con carta: la conferma arriva automaticamente da Stripe, "
            "non è richiesta (né consentita) un'azione manuale."
        )

    order.status = "PAID"
    order.paid_by_user_id = actor_user_id
    order.paid_at = utcnow()

    version = await db.get(ProductVersion, order.product_version_id)
    await notifications_service.notify_user(
        db, organization_id=organization_id, user_id=order.customer_user_id, type_="ORDER_PAID",
        entity_type="order", entity_id=order.id,
        title=f"Il tuo ordine per {version.name if version else 'un prodotto'} è confermato",
        body=None,
    )
    await notifications_service.notify_roles(
        db, organization_id=organization_id, roles=notifications_service.STAFF_NOTIFY_ROLES,
        type_="ORDER_PAID", entity_type="order", entity_id=order.id,
        title=f"Bonifico confermato: {version.name if version else 'ordine'}",
        body=f"{order.amount_cents / 100:.2f} EUR", exclude_user_id=actor_user_id,
    )
    # credit_wallet commits, making the PAID transition, notifications and
    # cashback rows atomic.
    await _credit_order_cashback(db, organization_id=organization_id, order=order, version=version, actor_user_id=actor_user_id)
    await db.commit()
    await db.refresh(order)
    await _send_order_paid_email(db, order=order, version=version)
    return order


async def cancel_order(
    db: AsyncSession, *, organization_id: uuid.UUID, order_id: uuid.UUID, reason: str, actor_user_id: uuid.UUID
) -> Order:
    order = await get_org_scoped(db, organization_id=organization_id, order_id=order_id)
    if order is None:
        raise OrderError("Order not found")
    if order.status != "AWAITING_PAYMENT":
        raise InvalidOrderStateError(f"Cannot cancel an order in status {order.status}")

    if order.credit_debit_transaction_id is not None:
        # Reverse the exact PURCHASE_DEBIT row to refund the credit.
        await wallets_service.reverse_transaction(
            db, organization_id=organization_id, transaction_id=order.credit_debit_transaction_id,
            actor_user_id=actor_user_id, reason=f"Ordine annullato: {reason}",
            idempotency_key=f"order:{order.id}:cancel-refund",
        )

    order.status = "CANCELLED"
    order.cancelled_by_user_id = actor_user_id
    order.cancelled_at = utcnow()
    order.cancellation_reason = reason
    await db.commit()
    await db.refresh(order)
    return order


async def change_payment_method(
    db: AsyncSession, *, organization_id: uuid.UUID, order: Order, new_payment_method: str
) -> Order:
    """Switch an AWAITING_PAYMENT order between BANK_TRANSFER and CARD;
    ownership is checked by the router. Leaving CARD clears
    stripe_checkout_session_id, since the webhook matches orders by it and a
    stale session must not mark a bank-transfer order paid."""
    if order.status != "AWAITING_PAYMENT":
        raise InvalidOrderStateError(f"Cannot change payment method for an order in status {order.status}")
    if new_payment_method not in ORDER_PAYMENT_METHODS:
        raise InvalidPaymentMethodError(f"payment_method must be one of {ORDER_PAYMENT_METHODS}")

    if new_payment_method != order.payment_method:
        available = await get_available_payment_methods(db, organization_id=organization_id)
        if new_payment_method == "BANK_TRANSFER" and not available["bank_transfer"]:
            raise PaymentMethodNotAvailableError("Il pagamento con bonifico non è configurato.")
        if new_payment_method == "CARD" and not available["card"]:
            raise PaymentMethodNotAvailableError("Il pagamento con carta non è configurato.")
        if order.payment_method == "CARD":
            order.stripe_checkout_session_id = None
        order.payment_method = new_payment_method
        await db.commit()
        await db.refresh(order)
    return order


async def upload_payment_proof(
    db: AsyncSession, *, organization_id: uuid.UUID, order: Order,
    file_bytes: bytes, content_type: str, original_filename: str, actor_user_id: uuid.UUID,
) -> Order:
    """Attach a bank-transfer receipt to an AWAITING_PAYMENT bank-transfer
    order. Advisory evidence for the admin; never changes status. Stored in
    the private documents bucket via foundation/storage.py."""
    from app.foundation.storage import UploadValidationError
    from app.foundation.storage import upload_document as storage_upload_document

    if order.status != "AWAITING_PAYMENT":
        raise PaymentProofError(f"Cannot attach a payment proof to an order in status {order.status}")
    if order.payment_method != "BANK_TRANSFER":
        raise PaymentProofError("La prova di pagamento è prevista solo per gli ordini pagati con bonifico.")

    try:
        storage_key = storage_upload_document(
            file_bytes=file_bytes, content_type=content_type,
            key_prefix=f"order-payment-proofs/{order.customer_user_id}",
        )
    except UploadValidationError as exc:
        raise PaymentProofError(str(exc)) from exc

    order.payment_proof_storage_key = storage_key
    order.payment_proof_original_filename = original_filename
    order.payment_proof_uploaded_at = utcnow()

    version = await db.get(ProductVersion, order.product_version_id)
    await notifications_service.notify_roles(
        db, organization_id=organization_id, roles=notifications_service.STAFF_NOTIFY_ROLES,
        type_="ORDER_PAYMENT_PROOF_UPLOADED", entity_type="order", entity_id=order.id,
        title=f"Prova di pagamento caricata: {version.name if version else 'ordine'}",
        body=None, exclude_user_id=actor_user_id,
    )
    await db.commit()
    await db.refresh(order)
    return order


PAYMENT_PROOF_PRESIGNED_URL_TTL_SECONDS = 300


def presigned_payment_proof_url(order: Order) -> str:
    from app.foundation.storage import generate_presigned_document_url as storage_presign_document

    assert order.payment_proof_storage_key is not None  # guaranteed by the router's own check
    return storage_presign_document(
        storage_key=order.payment_proof_storage_key, expires_in_seconds=PAYMENT_PROOF_PRESIGNED_URL_TTL_SECONDS
    )


async def attach_stripe_checkout_session(db: AsyncSession, *, order: Order, session_id: str) -> Order:
    """Record the live Checkout Session for this order, replacing any
    earlier one so only the latest attempt is honored by the webhook. Status
    stays AWAITING_PAYMENT until Stripe confirms payment."""
    order.payment_method = "CARD"
    order.stripe_checkout_session_id = session_id
    await db.commit()
    await db.refresh(order)
    return order


async def mark_paid_via_stripe(
    db: AsyncSession, *, organization_id: uuid.UUID, stripe_checkout_session_id: str
) -> Order:
    """Mark a CARD order PAID from the Stripe webhook
    (checkout.session.completed). There is no human actor, so paid_by_user_id
    stays NULL."""
    stmt = select(Order).where(
        Order.organization_id == organization_id, Order.stripe_checkout_session_id == stripe_checkout_session_id
    )
    order = (await db.execute(stmt)).scalar_one_or_none()
    if order is None:
        raise OrderError("Order not found for this Stripe checkout session")
    if order.status != "AWAITING_PAYMENT":
        # Stripe retries deliveries; an already-PAID order is a no-op.
        return order

    order.status = "PAID"
    order.paid_at = utcnow()

    version = await db.get(ProductVersion, order.product_version_id)
    await notifications_service.notify_user(
        db, organization_id=organization_id, user_id=order.customer_user_id, type_="ORDER_PAID",
        entity_type="order", entity_id=order.id,
        title=f"Il tuo ordine per {version.name if version else 'un prodotto'} è confermato",
        body="Pagamento con carta ricevuto.",
    )
    # No human actor to exclude from the staff notification.
    await notifications_service.notify_roles(
        db, organization_id=organization_id, roles=notifications_service.STAFF_NOTIFY_ROLES,
        type_="ORDER_PAID", entity_type="order", entity_id=order.id,
        title=f"Pagamento Stripe confermato: {version.name if version else 'ordine'}",
        body=f"{order.amount_cents / 100:.2f} EUR",
    )
    await _credit_order_cashback(db, organization_id=organization_id, order=order, version=version, actor_user_id=None)
    await db.commit()
    await db.refresh(order)
    await _send_order_paid_email(db, order=order, version=version)
    return order
