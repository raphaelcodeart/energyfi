import logging
import uuid
from datetime import UTC, datetime

import stripe
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.foundation.db import utcnow
from app.modules.aliexpress_dropshipping import service as aliexpress_service
from app.modules.aliexpress_dropshipping.models import AliexpressOrder
from app.modules.cj_dropshipping import service as cj_service
from app.modules.cj_dropshipping.models import CjOrder
from app.modules.contracts import payment_plans
from app.modules.contracts.models import Contract, ContractRequest, ContractRequestCheckout
from app.modules.imported_products import service as imported_products_service
from app.modules.imported_products.models import ImportedProductOrder
from app.modules.invoice_redemptions import service as invoice_redemptions_service
from app.modules.invoice_redemptions.models import InvoiceRedemption
from app.modules.sosnet_market import service as sosnet_market_service
from app.modules.sosnet_market.models import SosnetMarketOrder
from app.modules.orders import service as orders_service
from app.modules.orders.models import Order
from app.modules.organizations import service as organizations_service
from app.modules.payments.models import StripeWebhookEvent
from app.modules.shopify_dropshipping import service as shopify_service
from app.modules.shopify_dropshipping.models import ShopifyOrder

logger = logging.getLogger(__name__)


class PaymentsError(Exception):
    pass


class StripeNotConfiguredError(PaymentsError):
    pass


class WebhookVerificationError(PaymentsError):
    pass


async def create_checkout_session_for_order(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    order: Order,
    success_url: str,
    cancel_url: str,
) -> str:
    """Create a Checkout Session for the order's residual and attach its id
    to the order. The order stays unpaid until the webhook confirms the charge.
    client_reference_id lets the webhook find the order again, and
    metadata.kind routes the event to the right domain."""
    secret_key = await organizations_service.get_stripe_secret_key(db, organization_id=organization_id)
    if not secret_key:
        raise StripeNotConfiguredError("Stripe non è configurato per questa organizzazione.")

    # Residual new money owed, cashback surcharge included; never the full
    # price.
    residual_cents = order.amount_cents - order.credit_applied_cents + order.cashback_surcharge_cents
    session = stripe.checkout.Session.create(
        api_key=secret_key,
        mode="payment",
        line_items=[
            {
                "price_data": {
                    "currency": "eur",
                    "product_data": {"name": f"Ordine {order.id}"},
                    "unit_amount": residual_cents,
                },
                "quantity": 1,
            }
        ],
        client_reference_id=str(order.id),
        metadata={"kind": "order", "order_id": str(order.id), "organization_id": str(organization_id)},
        success_url=success_url,
        cancel_url=cancel_url,
    )
    await orders_service.attach_stripe_checkout_session(db, order=order, session_id=session.id)
    if not session.url:
        # Always set for payment-mode sessions; guards the Optional type.
        raise StripeNotConfiguredError("Stripe non ha restituito un URL di checkout valido.")
    return session.url


async def create_checkout_session_for_redemption(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    redemption: InvoiceRedemption,
    success_url: str,
    cancel_url: str,
) -> str:
    """Checkout for an invoice-redemption fee: charges only
    payment_due_cents, since the invoice itself was already paid to the
    supplier."""
    secret_key = await organizations_service.get_stripe_secret_key(db, organization_id=organization_id)
    if not secret_key:
        raise StripeNotConfiguredError("Stripe non è configurato per questa organizzazione.")

    due_cents = invoice_redemptions_service.payment_due_cents(redemption.confirmed_amount_cents)
    if not due_cents or due_cents <= 0:
        raise StripeNotConfiguredError("Nessun importo da pagare per questo riscatto.")

    session = stripe.checkout.Session.create(
        api_key=secret_key,
        mode="payment",
        line_items=[
            {
                "price_data": {
                    "currency": "eur",
                    "product_data": {"name": f"Riscatto cashback {redemption.id}"},
                    "unit_amount": due_cents,
                },
                "quantity": 1,
            }
        ],
        client_reference_id=str(redemption.id),
        metadata={
            "kind": "invoice_redemption", "invoice_redemption_id": str(redemption.id),
            "organization_id": str(organization_id),
        },
        success_url=success_url,
        cancel_url=cancel_url,
    )
    await invoice_redemptions_service.attach_stripe_checkout_session(db, redemption=redemption, session_id=session.id)
    if not session.url:
        raise StripeNotConfiguredError("Stripe non ha restituito un URL di checkout valido.")
    return session.url


async def create_checkout_session_for_imported_order(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    order: ImportedProductOrder,
    success_url: str,
    cancel_url: str,
) -> str:
    """Checkout for an imported-products order (kind="imported_order")."""
    secret_key = await organizations_service.get_stripe_secret_key(db, organization_id=organization_id)
    if not secret_key:
        raise StripeNotConfiguredError("Stripe non è configurato per questa organizzazione.")

    # Card pays the full residual, so the bank-transfer discount is cleared
    # server-side here.
    amount_due_cents = await imported_products_service.prepare_card_payment(db, order=order)
    session = stripe.checkout.Session.create(
        api_key=secret_key,
        mode="payment",
        line_items=[
            {
                "price_data": {
                    "currency": "eur",
                    "product_data": {"name": f"Ordine {str(order.id)[:8].upper()} — SOSNET"},
                    "unit_amount": amount_due_cents,
                },
                "quantity": 1,
            }
        ],
        client_reference_id=str(order.id),
        metadata={"kind": "imported_order", "imported_order_id": str(order.id), "organization_id": str(organization_id)},
        success_url=success_url,
        cancel_url=cancel_url,
    )
    await imported_products_service.attach_stripe_checkout_session(db, order=order, session_id=session.id)
    if not session.url:
        raise StripeNotConfiguredError("Stripe non ha restituito un URL di checkout valido.")
    return session.url


async def create_checkout_session_for_cj_order(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    order: CjOrder,
    success_url: str,
    cancel_url: str,
) -> str:
    """Checkout for a dropshipping partner-store order (kind="cj_order")."""
    secret_key = await organizations_service.get_stripe_secret_key(db, organization_id=organization_id)
    if not secret_key:
        raise StripeNotConfiguredError("Stripe non è configurato per questa organizzazione.")

    # Card pays the full residual, so the bank-transfer discount is cleared
    # server-side here.
    amount_due_cents = await cj_service.prepare_card_payment(db, order=order)
    session = stripe.checkout.Session.create(
        api_key=secret_key,
        mode="payment",
        line_items=[
            {
                "price_data": {
                    "currency": "eur",
                    "product_data": {"name": f"Ordine {str(order.id)[:8].upper()} — SOSNET"},
                    "unit_amount": amount_due_cents,
                },
                "quantity": 1,
            }
        ],
        client_reference_id=str(order.id),
        metadata={"kind": "cj_order", "cj_order_id": str(order.id), "organization_id": str(organization_id)},
        success_url=success_url,
        cancel_url=cancel_url,
    )
    await cj_service.attach_stripe_checkout_session(db, order=order, session_id=session.id)
    if not session.url:
        raise StripeNotConfiguredError("Stripe non ha restituito un URL di checkout valido.")
    return session.url


async def create_checkout_session_for_shopify_order(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    order: ShopifyOrder,
    success_url: str,
    cancel_url: str,
) -> str:
    """Checkout for an external-store marketplace order
    (kind="shopify_order")."""
    secret_key = await organizations_service.get_stripe_secret_key(db, organization_id=organization_id)
    if not secret_key:
        raise StripeNotConfiguredError("Stripe non è configurato per questa organizzazione.")

    # Card pays the full residual, so the bank-transfer discount is cleared
    # server-side here.
    amount_due_cents = await shopify_service.prepare_card_payment(db, order=order)
    session = stripe.checkout.Session.create(
        api_key=secret_key,
        mode="payment",
        line_items=[
            {
                "price_data": {
                    "currency": "eur",
                    "product_data": {"name": f"Ordine {str(order.id)[:8].upper()} — SOSNET"},
                    "unit_amount": amount_due_cents,
                },
                "quantity": 1,
            }
        ],
        client_reference_id=str(order.id),
        metadata={"kind": "shopify_order", "shopify_order_id": str(order.id), "organization_id": str(organization_id)},
        success_url=success_url,
        cancel_url=cancel_url,
    )
    await shopify_service.attach_stripe_checkout_session(db, order=order, session_id=session.id)
    if not session.url:
        raise StripeNotConfiguredError("Stripe non ha restituito un URL di checkout valido.")
    return session.url


async def create_checkout_session_for_aliexpress_order(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    order: AliexpressOrder,
    success_url: str,
    cancel_url: str,
) -> str:
    """Checkout for an external-store marketplace order
    (kind="aliexpress_order")."""
    secret_key = await organizations_service.get_stripe_secret_key(db, organization_id=organization_id)
    if not secret_key:
        raise StripeNotConfiguredError("Stripe non è configurato per questa organizzazione.")

    # Card pays the full residual, so the bank-transfer discount is cleared
    # server-side here.
    amount_due_cents = await aliexpress_service.prepare_card_payment(db, order=order)
    session = stripe.checkout.Session.create(
        api_key=secret_key,
        mode="payment",
        line_items=[
            {
                "price_data": {
                    "currency": "eur",
                    "product_data": {"name": f"Ordine {str(order.id)[:8].upper()} — SOSNET"},
                    "unit_amount": amount_due_cents,
                },
                "quantity": 1,
            }
        ],
        client_reference_id=str(order.id),
        metadata={
            "kind": "aliexpress_order", "aliexpress_order_id": str(order.id),
            "organization_id": str(organization_id),
        },
        success_url=success_url,
        cancel_url=cancel_url,
    )
    await aliexpress_service.attach_stripe_checkout_session(db, order=order, session_id=session.id)
    if not session.url:
        raise StripeNotConfiguredError("Stripe non ha restituito un URL di checkout valido.")
    return session.url


async def create_checkout_session_for_sosnet_market_order(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    order: SosnetMarketOrder,
    success_url: str,
    cancel_url: str,
) -> str:
    """Checkout for a grocery marketplace order
    (kind="sosnet_market_order")."""
    secret_key = await organizations_service.get_stripe_secret_key(db, organization_id=organization_id)
    if not secret_key:
        raise StripeNotConfiguredError("Stripe non è configurato per questa organizzazione.")

    # Card pays the full residual, so the bank-transfer discount is cleared
    # server-side here.
    amount_due_cents = await sosnet_market_service.prepare_card_payment(db, order=order)
    session = stripe.checkout.Session.create(
        api_key=secret_key,
        mode="payment",
        line_items=[
            {
                "price_data": {
                    "currency": "eur",
                    "product_data": {"name": f"Ordine {str(order.id)[:8].upper()} — SOSNET"},
                    "unit_amount": amount_due_cents,
                },
                "quantity": 1,
            }
        ],
        client_reference_id=str(order.id),
        metadata={
            "kind": "sosnet_market_order", "sosnet_market_order_id": str(order.id),
            "organization_id": str(organization_id),
        },
        success_url=success_url,
        cancel_url=cancel_url,
    )
    await sosnet_market_service.attach_stripe_checkout_session(db, order=order, session_id=session.id)
    if not session.url:
        raise StripeNotConfiguredError("Stripe non ha restituito un URL di checkout valido.")
    return session.url

async def create_checkout_session_for_contract(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    contract: Contract,
    plan_key: str,
    success_url: str,
    cancel_url: str,
) -> str:
    """Checkout for a contract: a single payment, or a Stripe subscription
    that stops after N instalments.

    Prices are built inline from the contract's frozen, VAT-correct
    gross_amount_cents, so nothing in the Stripe dashboard must be kept in sync
    and later catalog changes cannot alter an agreed contract. Instalments are
    SOSNET splitting its own invoice, not third-party financing.

    Never marks the contract paid; only the verified webhook does. The success
    URL proves nothing.
    """
    secret_key = await organizations_service.get_stripe_secret_key(db, organization_id=organization_id)
    if not secret_key:
        raise StripeNotConfiguredError("Stripe non è configurato per questa organizzazione.")

    plan = payment_plans.plan_by_key(plan_key)
    if plan is None:
        raise PaymentsError("Modalità di pagamento non valida.")
    total_cents = contract.gross_amount_cents
    if not total_cents or total_cents <= 0:
        raise PaymentsError("Questo contratto non ha un importo da pagare.")
    discount_percentage = await organizations_service.get_contract_full_payment_discount_percentage(
        db, organization_id=organization_id
    )
    breakdown = payment_plans.breakdown_for(plan, total_cents, discount_percentage=discount_percentage)
    if breakdown.instalment_cents <= 0:
        raise PaymentsError("Importo troppo basso per questa modalità di pagamento.")

    product_name = f"Contratto SOSNET {str(contract.id)[:8].upper()}"
    metadata = {
        "kind": "contract",
        "contract_id": str(contract.id),
        "organization_id": str(organization_id),
        "payment_plan": plan.key,
    }

    if not breakdown.is_subscription:
        session = stripe.checkout.Session.create(
            api_key=secret_key,
            mode="payment",
            line_items=[{
                "price_data": {
                    "currency": "eur",
                    "product_data": {
                        "name": product_name,
                        **(
                            {"description": f"Pagamento unico: sconto {breakdown.discount_percentage}% "
                                            f"(prezzo {_euro(total_cents)})"}
                            if breakdown.discount_cents else {}
                        ),
                    },
                    "unit_amount": breakdown.total_cents,
                },
                "quantity": 1,
            }],
            client_reference_id=str(contract.id),
            metadata=metadata,
            success_url=success_url,
            cancel_url=cancel_url,
        )
    else:
        # No invoice item for the rounding remainder: that would require a
        # pre-created Stripe Product per contract to recover a few cents. The
        # instalment is rounded and the resulting total shown to the customer
        # (see payment_plans.PlanBreakdown).
        session = stripe.checkout.Session.create(
            api_key=secret_key,
            mode="subscription",
            line_items=[{
                "price_data": {
                    "currency": "eur",
                    "product_data": {"name": f"{product_name} — rata mensile"},
                    "unit_amount": breakdown.instalment_cents,
                    "recurring": {"interval": "month"},
                },
                "quantity": 1,
            }],
            client_reference_id=str(contract.id),
            metadata=metadata,
            subscription_data={"metadata": metadata},
            success_url=success_url,
            cancel_url=cancel_url,
        )

    from app.modules.contracts import service as contracts_service

    await contracts_service.attach_stripe_checkout_session(
        db, contract=contract, session_id=session.id, plan_key=plan.key, discount_cents=breakdown.discount_cents
    )
    if not session.url:
        raise StripeNotConfiguredError("Stripe non ha restituito un URL di checkout valido.")
    return session.url


async def _stop_subscription_after_last_instalment(
    *, secret_key: str, subscription_id: str, instalments: int
) -> None:
    """Set the subscription to cancel at the end of the period containing
    the last instalment.

    Fixed up front instead of counting invoices, so a missed webhook can never
    keep charging a customer who has finished paying. proration_behavior="none"
    prevents Stripe from crediting the partial period after the last
    instalment."""
    subscription = stripe.Subscription.retrieve(subscription_id, api_key=secret_key)
    # Newer API versions expose the billing period on the items; the anchor is
    # always on the subscription.
    start = (
        getattr(subscription, "billing_cycle_anchor", None)
        or getattr(subscription, "start_date", None)
        or int(datetime.now(UTC).timestamp())
    )
    # The first instalment is charged immediately.
    cancel_at = start + (instalments - 1) * 31 * 24 * 3600
    stripe.Subscription.modify(
        subscription_id, api_key=secret_key, cancel_at=cancel_at, proration_behavior="none"
    )


async def create_checkout_session_for_request(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    request: ContractRequest,
    plan_key: str,
    actor_user_id: uuid.UUID,
    success_url: str,
    cancel_url: str,
) -> str:
    """One Checkout for every payable contract of a contract request.

    Each line carries its contract id in the inline product metadata, which
    ties every subscription item (and so every monthly invoice line) back to
    its contract. The customer pays the sum; each contract receives its own
    instalment.

    Contracts and amounts are frozen in a contract_request_checkouts row before
    redirecting to Stripe, and the webhook pays exactly that. Other open
    sessions for the same request are expired (best effort) so a second tab
    cannot take a second payment."""
    from app.modules.contracts import requests as requests_service

    secret_key = await organizations_service.get_stripe_secret_key(db, organization_id=organization_id)
    if not secret_key:
        raise StripeNotConfiguredError("Il pagamento con carta non è attivo al momento. Riprova più tardi.")
    plan = payment_plans.plan_by_key(plan_key)
    if plan is None:
        raise PaymentsError("Modalità di pagamento non valida.")

    points = requests_service.payable_points(await requests_service.list_points(db, request=request))
    if not points:
        raise PaymentsError("In questa pratica non c'è nessun contratto da pagare.")
    discount_percentage = await organizations_service.get_contract_full_payment_discount_percentage(
        db, organization_id=organization_id
    )
    option = next(
        o for o in requests_service.plan_options(points, discount_percentage=discount_percentage)
        if o.plan.key == plan.key
    )
    if not option.available:
        raise PaymentsError(option.unavailable_reason or "Modalità di pagamento non disponibile.")

    code = str(request.id)[:8].upper()
    metadata = {
        "kind": "contract_request",
        "contract_request_id": str(request.id),
        "organization_id": str(organization_id),
        "payment_plan": plan.key,
    }
    frozen_lines = []
    line_items = []
    labels = await _point_labels(db, points)
    for contract in points:
        breakdown = payment_plans.breakdown_for(
            plan, int(contract.gross_amount_cents or 0), discount_percentage=discount_percentage
        )
        frozen_lines.append({
            "contract_id": str(contract.id),
            "gross_cents": int(contract.gross_amount_cents or 0),
            "instalment_cents": breakdown.instalment_cents,
            "discount_cents": breakdown.discount_cents,
        })
        price_data = {
            "currency": "eur",
            "product_data": {
                "name": labels[contract.id],
                # Stripe only shows the monthly amount; this makes the instalment
                # count and total visible.
                "description": (
                    f"{plan.instalments} rate mensili da {_euro(breakdown.instalment_cents)} · "
                    f"totale {_euro(breakdown.total_cents)}"
                    if breakdown.is_subscription
                    else (
                        f"Pagamento unico, sconto {breakdown.discount_percentage}% "
                        f"(prezzo {_euro(int(contract.gross_amount_cents or 0))}) · pratica {code}"
                        if breakdown.discount_cents else f"Pagamento unico · pratica {code}"
                    )
                ),
                "metadata": {"contract_id": str(contract.id), "contract_request_id": str(request.id)},
            },
            "unit_amount": breakdown.instalment_cents,
        }
        if breakdown.is_subscription:
            price_data["recurring"] = {"interval": "month"}
        line_items.append({"price_data": price_data, "quantity": 1})

    params = {
        "api_key": secret_key,
        "mode": "subscription" if plan.instalments > 1 else "payment",
        "line_items": line_items,
        "client_reference_id": str(request.id),
        "metadata": metadata,
        "success_url": success_url,
        "cancel_url": cancel_url,
        # Shown above the pay button: Stripe displays only the monthly figure,
        # so state the number of instalments and that they stop automatically.
        "custom_text": {"submit": {"message": _checkout_summary(plan, option, len(points))}},
    }
    if plan.instalments > 1:
        params["subscription_data"] = {"metadata": metadata, "description": f"Pratica SOSNET {code}"}
    else:
        params["payment_intent_data"] = {"metadata": metadata, "description": f"Pratica SOSNET {code}"}

    previous_open = list(
        (
            await db.execute(
                select(ContractRequestCheckout).where(
                    ContractRequestCheckout.contract_request_id == request.id,
                    ContractRequestCheckout.completed_at.is_(None),
                )
            )
        ).scalars()
    )
    session = stripe.checkout.Session.create(**params)
    if not session.url:
        raise StripeNotConfiguredError("Stripe non ha restituito un indirizzo di pagamento valido.")

    db.add(
        ContractRequestCheckout(
            organization_id=organization_id,
            contract_request_id=request.id,
            stripe_checkout_session_id=session.id,
            payment_plan=plan.key,
            lines=frozen_lines,
            total_cents=option.total_cents,
            instalment_cents=option.instalment_cents,
            created_by_user_id=actor_user_id,
        )
    )
    await db.commit()

    for old in previous_open:
        try:
            stripe.checkout.Session.expire(old.stripe_checkout_session_id, api_key=secret_key)
        except Exception:  # noqa: BLE001 -- already completed or expired: nothing to stop
            logger.info("Checkout %s of pratica %s not expired (already closed)", old.stripe_checkout_session_id, code)
    return session.url


def _euro(cents: int) -> str:
    return f"{cents / 100:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")


def _checkout_summary(plan: payment_plans.PaymentPlan, option, contracts: int) -> str:
    what = "1 contratto" if contracts == 1 else f"{contracts} contratti"
    if plan.instalments <= 1:
        if getattr(option, "discount_cents", 0):
            return (
                f"Pagamento unico di {_euro(option.total_cents)} per {what} SOSNET: "
                f"sconto del {option.discount_percentage}% già applicato (risparmi {_euro(option.discount_cents)})."
            )
        return f"Pagamento unico di {_euro(option.total_cents)} per {what} SOSNET."
    return (
        f"Paghi {plan.instalments} rate mensili da {_euro(option.instalment_cents)}, per un totale di "
        f"{_euro(option.total_cents)} ({what}). La prima rata oggi, le altre addebitate automaticamente ogni "
        f"mese: gli addebiti si fermano da soli dopo la {plan.instalments}ª rata."
    )


async def _point_labels(db: AsyncSession, points: list[Contract]) -> dict[uuid.UUID, str]:
    """Per-line label shown on the Stripe page: product and POD code, or
    the address when the POD is unknown."""
    from app.modules.catalog.models import ProductVersion
    from app.modules.customers.models import Address, SupplyPoint

    out = {}
    for contract in points:
        supply_point = await db.get(SupplyPoint, contract.supply_point_id)
        address = await db.get(Address, supply_point.supply_address_id) if supply_point else None
        version = await db.get(ProductVersion, contract.product_version_id) if contract.product_version_id else None
        if supply_point is not None and supply_point.pod_code:
            point = f"POD {supply_point.pod_code}"
        elif supply_point is not None and supply_point.pdr_code:
            point = f"PDR {supply_point.pdr_code}"
        elif address is not None:
            point = f"{address.street}, {address.city}"
        else:
            point = f"Contratto {str(contract.id)[:8].upper()}"
        out[contract.id] = f"{version.name} — {point}" if version else point
    return out


async def _handle_request_checkout(db: AsyncSession, *, organization_id: uuid.UUID, session, secret_key: str) -> str:
    from app.modules.contracts import requests as requests_service

    checkout = (
        await db.execute(
            select(ContractRequestCheckout).where(
                ContractRequestCheckout.organization_id == organization_id,
                ContractRequestCheckout.stripe_checkout_session_id == session["id"],
            )
        )
    ).scalar_one_or_none()
    if checkout is None:
        return "nessuna pratica per questa sessione"

    subscription_id = getattr(session, "subscription", None)
    subscription_id = str(subscription_id) if subscription_id else None
    items: dict[str, str] = {}
    if subscription_id:
        try:
            items = _subscription_items_by_contract(secret_key=secret_key, subscription_id=subscription_id)
        except Exception:
            # The payment must be recorded regardless. Without the item map later
            # invoices cannot be split per contract, so log loudly: that is fixable
            # by hand, a lost payment is not.
            logger.exception("Could not map subscription items of %s", subscription_id)
    invoice = getattr(session, "invoice", None)
    outcome = await requests_service.apply_checkout(
        db, checkout=checkout, stripe_invoice_id=str(invoice) if invoice else None,
        stripe_subscription_id=subscription_id,
        stripe_customer_id=str(getattr(session, "customer", "") or "") or None,
        subscription_items=items,
    )

    plan = payment_plans.plan_by_key(checkout.payment_plan)
    if subscription_id and plan is not None and plan.instalments > 1:
        if len(items) < len(checkout.lines):
            outcome += "; ATTENZIONE: voci dell'abbonamento non abbinate a tutti i contratti"
        try:
            await _stop_subscription_after_last_instalment(
                secret_key=secret_key, subscription_id=subscription_id, instalments=plan.instalments
            )
        except Exception:
            logger.exception("Could not set cancel_at on subscription %s (checkout %s)", subscription_id, checkout.id)
            outcome += "; ATTENZIONE: cancel_at non impostato"
    return outcome


def _subscription_items_by_contract(*, secret_key: str, subscription_id: str) -> dict[str, str]:
    """Map contract id to subscription item id, from line metadata."""
    subscription = stripe.Subscription.retrieve(
        subscription_id, api_key=secret_key, expand=["items.data.price.product"]
    )
    out = {}
    for item in subscription["items"]["data"]:
        product = item["price"]["product"]
        metadata = getattr(product, "metadata", None)
        contract_id = getattr(metadata, "contract_id", None) if metadata is not None else None
        if contract_id:
            out[str(contract_id)] = str(item["id"])
    return out


def _invoice_lines(*, secret_key: str, invoice) -> list[tuple[str, int]]:
    """(subscription item id, amount) for every invoice line, read from the
    API because webhook payloads include only the first lines."""
    lines = stripe.Invoice.list_lines(str(invoice["id"]), api_key=secret_key, limit=100)
    out = []
    for line in lines.auto_paging_iter():
        item_id = getattr(line, "subscription_item", None)
        if not item_id:
            parent = getattr(line, "parent", None)
            details = getattr(parent, "subscription_item_details", None) if parent is not None else None
            item_id = getattr(details, "subscription_item", None) if details is not None else None
        if item_id:
            out.append((str(item_id), int(getattr(line, "amount", 0) or 0)))
    return out


async def stop_contract_billing(
    db: AsyncSession, *, organization_id: uuid.UUID, contract: Contract, actor_user_id: uuid.UUID
) -> Contract:
    """Stop monthly charges for one rejected or cancelled contract.

    Within a shared subscription only that contract's item is removed; if it
    was the last item, or the subscription was the contract's own, the
    subscription is cancelled. Refunds stay a manual decision in Stripe.
    Commits."""
    from app.modules.audit import service as audit_service

    if contract.stripe_subscription_id is None:
        raise PaymentsError("Questo contratto non ha addebiti mensili attivi.")
    if contract.billing_stopped_at is not None:
        raise PaymentsError("Gli addebiti di questo contratto sono già stati interrotti.")
    secret_key = await organizations_service.get_stripe_secret_key(db, organization_id=organization_id)
    if not secret_key:
        raise StripeNotConfiguredError("Stripe non è configurato per questa organizzazione.")

    siblings = list(
        (
            await db.execute(
                select(Contract).where(
                    Contract.organization_id == organization_id,
                    Contract.stripe_subscription_id == contract.stripe_subscription_id,
                    Contract.id != contract.id,
                    Contract.billing_stopped_at.is_(None),
                )
            )
        ).scalars()
    )
    try:
        if contract.stripe_subscription_item_id and siblings:
            stripe.SubscriptionItem.delete(
                contract.stripe_subscription_item_id, api_key=secret_key, proration_behavior="none"
            )
            action = "riga rimossa dall'abbonamento"
        else:
            stripe.Subscription.cancel(contract.stripe_subscription_id, api_key=secret_key)
            action = "abbonamento annullato"
    except stripe.error.StripeError as exc:
        raise PaymentsError(f"Stripe ha rifiutato l'operazione: {exc.user_message or exc}") from exc

    contract.billing_stopped_at = utcnow()
    contract.updated_at = utcnow()
    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="contract.billing_stopped", entity_type="contract", entity_id=str(contract.id),
        new_value={"subscription_id": contract.stripe_subscription_id, "action": action},
    )
    await db.commit()
    await db.refresh(contract)
    return contract


async def _claim_event(
    db: AsyncSession, *, organization_id: uuid.UUID, event_id: str, event_type: str
) -> StripeWebhookEvent | None:
    """Record the event id before processing; return None if already seen.

    Insert-first, not check-then-insert: Stripe delivers at-least-once and two
    concurrent deliveries would both pass a check. The UNIQUE constraint
    decides which one proceeds."""
    row = StripeWebhookEvent(
        organization_id=organization_id, stripe_event_id=event_id, event_type=event_type
    )
    db.add(row)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        return None
    await db.refresh(row)
    return row


async def _finish_event(db: AsyncSession, *, row: StripeWebhookEvent | None, outcome: str) -> None:
    if row is None:
        return
    row.processed_at = datetime.now(UTC)
    row.outcome = outcome[:255]
    await db.commit()


async def _handle_contract_checkout(
    db: AsyncSession, *, organization_id: uuid.UUID, session, secret_key: str
) -> str:
    """First payment of a contract: mark it paid, credit SosnetCash and,
    for instalment plans, set the subscription stop date.

    If documents are already approved the contract becomes ACTIVE and
    commissions fire, as with a confirmed bank transfer; otherwise it waits
    for approval."""
    from app.modules.contracts import service as contracts_service

    invoice = getattr(session, "invoice", None)
    contract = await contracts_service.mark_paid_via_stripe(
        db, organization_id=organization_id, stripe_checkout_session_id=session["id"],
        stripe_invoice_id=str(invoice) if invoice else None,
    )
    if contract is None:
        return "nessun contratto per questa sessione"

    subscription_id = getattr(session, "subscription", None)
    if subscription_id:
        plan = payment_plans.plan_by_key(contract.payment_plan)
        await contracts_service.attach_stripe_subscription(
            db, contract=contract, subscription_id=str(subscription_id),
            customer_id=str(getattr(session, "customer", "") or "") or None,
        )
        if plan is not None and plan.instalments > 1:
            await contracts_service.credit_contract_instalment_cashback(
                db, organization_id=organization_id, contract=contract, instalment_number=1
            )
            try:
                await _stop_subscription_after_last_instalment(
                    secret_key=secret_key,
                    subscription_id=str(subscription_id),
                    instalments=plan.instalments,
                )
            except Exception:
                # Log loudly and record on the event row: a subscription without a
                # stop date keeps charging. Do not fail the webhook, which would make
                # Stripe retry an already-applied event.
                logger.exception(
                    "Could not set cancel_at on subscription %s (contract %s)",
                    subscription_id, contract.id,
                )
                return f"contratto {contract.id} pagato; ATTENZIONE: cancel_at non impostato"
    return f"contratto {contract.id} pagato"


def _invoice_subscription_id(invoice) -> str | None:
    """Subscription id of an invoice.

    Older Stripe API versions use `invoice.subscription`; newer ones use
    `invoice.parent.subscription_details.subscription`. Both are read so an
    endpoint pinned to either version works; missing it would silently skip
    cashback, commissions and failed-charge alerts."""
    legacy = getattr(invoice, "subscription", None)
    if legacy:
        return str(legacy)
    parent = getattr(invoice, "parent", None)
    details = getattr(parent, "subscription_details", None) if parent is not None else None
    subscription = getattr(details, "subscription", None) if details is not None else None
    return str(subscription) if subscription else None


async def _subscription_is_shared(db: AsyncSession, *, organization_id: uuid.UUID, subscription_id: str) -> bool:
    """True when the subscription came from a multi-contract checkout,
    whose invoices must be split per contract item."""
    row = (
        await db.execute(
            select(Contract.id).where(
                Contract.organization_id == organization_id,
                Contract.stripe_subscription_id == subscription_id,
                Contract.stripe_subscription_item_id.is_not(None),
            ).limit(1)
        )
    ).first()
    return row is not None


async def handle_webhook_event(
    db: AsyncSession, *, organization_id: uuid.UUID, payload: bytes, sig_header: str
) -> None:
    """Verify and dispatch a Stripe webhook event for one organization.

    The per-organization URL means each event is verified with that
    organization's own webhook secret, and every handler is scoped to
    organization_id, so one tenant's Stripe account can never affect another's
    data. Checkout events are routed by metadata.kind rather than by trying
    each table in turn; a missing kind defaults to "order"."""
    webhook_secret = await organizations_service.get_stripe_webhook_secret(db, organization_id=organization_id)
    if not webhook_secret:
        raise StripeNotConfiguredError("Il webhook Stripe non è configurato per questa organizzazione.")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
    except (ValueError, stripe.error.SignatureVerificationError) as exc:
        raise WebhookVerificationError(str(exc)) from exc

    # Only the contract branch needs it, to set a subscription stop date.
    secret_key = await organizations_service.get_stripe_secret_key(db, organization_id=organization_id) or ""

    # Event-level exactly-once: subscriptions fire invoice.paid monthly, so a
    # redelivered event must be distinguishable from the next instalment.
    event_row = await _claim_event(
        db, organization_id=organization_id,
        event_id=str(event["id"]), event_type=str(event["type"]),
    )
    if event_row is None:
        return  # already processed; acknowledge and do nothing

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        # StripeObject has no .get(); getattr with a default handles both a
        # missing metadata object and a missing kind key.
        kind = getattr(getattr(session, "metadata", None), "kind", "order")
        if kind == "invoice_redemption":
            try:
                await invoice_redemptions_service.mark_paid_via_stripe(
                    db, organization_id=organization_id, stripe_checkout_session_id=session["id"]
                )
            except invoice_redemptions_service.InvoiceRedemptionError:
                # No matching redemption in this organization; ignore rather than
                # make Stripe retry indefinitely.
                pass
        elif kind == "imported_order":
            try:
                await imported_products_service.mark_paid_via_stripe(
                    db, organization_id=organization_id, stripe_checkout_session_id=session["id"],
                    order_id=getattr(getattr(session, "metadata", None), "imported_order_id", None),
                )
            except imported_products_service.ImportedProductsError:
                pass
        elif kind == "cj_order":
            await cj_service.mark_paid_via_stripe(
                db, organization_id=organization_id, stripe_checkout_session_id=session["id"],
                order_id=getattr(getattr(session, "metadata", None), "cj_order_id", None),
            )
        elif kind == "shopify_order":
            await shopify_service.mark_paid_via_stripe(
                db, organization_id=organization_id, stripe_checkout_session_id=session["id"],
                order_id=getattr(getattr(session, "metadata", None), "shopify_order_id", None),
            )
        elif kind == "aliexpress_order":
            await aliexpress_service.mark_paid_via_stripe(
                db, organization_id=organization_id, stripe_checkout_session_id=session["id"],
                order_id=getattr(getattr(session, "metadata", None), "aliexpress_order_id", None),
            )
        elif kind == "sosnet_market_order":
            await sosnet_market_service.mark_paid_by_session(
                db, organization_id=organization_id, stripe_checkout_session_id=session["id"],
                order_id=getattr(getattr(session, "metadata", None), "sosnet_market_order_id", None),
            )
        elif kind == "contract_request":
            outcome = await _handle_request_checkout(
                db, organization_id=organization_id, session=session, secret_key=secret_key
            )
            await _finish_event(db, row=event_row, outcome=outcome)
            return
        elif kind == "contract":
            outcome = await _handle_contract_checkout(
                db, organization_id=organization_id, session=session, secret_key=secret_key
            )
            await _finish_event(db, row=event_row, outcome=outcome)
            return
        else:
            try:
                await orders_service.mark_paid_via_stripe(
                    db, organization_id=organization_id, stripe_checkout_session_id=session["id"]
                )
            except orders_service.OrderError:
                pass

    elif event["type"] in ("invoice.paid", "invoice.payment_failed"):
        # Instalments after the first. The contract is already ACTIVE; the point
        # is recording each charge and alerting when one fails.
        from app.modules.contracts import service as contracts_service

        invoice = event["data"]["object"]
        subscription_id = _invoice_subscription_id(invoice)
        if subscription_id:
            lines = None
            if await _subscription_is_shared(db, organization_id=organization_id, subscription_id=str(subscription_id)):
                # Shared subscription: route each invoice line to its own contract.
                lines = _invoice_lines(secret_key=secret_key, invoice=invoice)
            outcome = await contracts_service.record_subscription_invoice(
                db,
                organization_id=organization_id,
                subscription_id=str(subscription_id),
                paid=event["type"] == "invoice.paid",
                amount_cents=int(getattr(invoice, "amount_paid", 0) or getattr(invoice, "amount_due", 0) or 0),
                invoice_id=str(invoice["id"]),
                billing_reason=getattr(invoice, "billing_reason", None),
                lines=lines,
            )
            await _finish_event(db, row=event_row, outcome=outcome)
            return

    await _finish_event(db, row=event_row, outcome=f"gestito: {event['type']}")
