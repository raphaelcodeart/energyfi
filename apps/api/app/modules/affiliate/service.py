"""SOS Affiliate services: operations, their effects, the monthly close.

Flow of every operation:

1. created PENDING by the affiliate (or by an admin) with a deterministic
   idempotency key, so a double click hits the UNIQUE constraint instead of
   creating a second order;
2. CONFIRMED by an admin when the money arrives: only then points, licences
   and commissions are written, under a row lock on the operation (INT-07);
3. corrected, if needed, only through a REVERSAL operation (INT-05).

The browser chooses a product code, never a price: every amount comes from
the plan version stored on the operation.
"""

import csv
import io
import uuid
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.foundation.db import utcnow
from app.modules.affiliate import engine
from app.modules.affiliate.models import (
    AffiliateClient,
    AffiliateCommission,
    AffiliateLicense,
    AffiliateMonthlyResult,
    AffiliateOperation,
    AffiliatePeriodClose,
    AffiliatePlanVersion,
    AffiliatePointEntry,
    AffiliateSubscription,
)
from app.modules.affiliate.plan import DEFAULT_PLAN, PLAN_VERSION_LABEL, product_index, validate_plan
from app.modules.audit.models import AuditLog
from app.modules.network.models import AgentProfile, NetworkNode

ROME = ZoneInfo("Europe/Rome")
#: Validity of the plan shipped with the code: the specification's date.
DEFAULT_PLAN_VALID_FROM = datetime(2026, 10, 28, tzinfo=UTC)
MAX_TOPUP = Decimal("1000000.00")
POINT_KINDS = ("SUBSCRIPTION_PAYMENT", "LICENSE_PURCHASE", "EVENT_TICKET_PURCHASE")


class AffiliateError(Exception):
    """A rule of the plan forbids the request; the message is shown as is."""


# --- Calendar ---------------------------------------------------------------


def period_of(moment: datetime) -> str:
    """Months follow the Italian calendar: a payment at 00:30 on 1 November
    in Rome belongs to November even though it is still October in UTC."""
    return moment.astimezone(ROME).strftime("%Y-%m")


def current_period(now: datetime | None = None) -> str:
    return period_of(now or utcnow())


def period_end(period: str) -> datetime:
    nxt = engine.next_period(period)
    year, month = (int(x) for x in nxt.split("-"))
    return datetime(year, month, 1, tzinfo=ROME) - timedelta(microseconds=1)


def career_pay_date(period: str, pay_day: int) -> date:
    year, month = (int(x) for x in engine.next_period(period).split("-"))
    return date(year, month, pay_day)


def today_rome() -> date:
    return utcnow().astimezone(ROME).date()


# --- Plan -------------------------------------------------------------------


async def get_plan(db: AsyncSession, organization_id: uuid.UUID, at: datetime | None = None) -> AffiliatePlanVersion:
    """The plan version valid at `at`. The first call of an organization
    stores the plan shipped with the code, so there is always one."""
    at = at or utcnow()
    row = (
        await db.execute(
            select(AffiliatePlanVersion)
            .where(AffiliatePlanVersion.organization_id == organization_id, AffiliatePlanVersion.valid_from <= at)
            .order_by(AffiliatePlanVersion.valid_from.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if row:
        return row
    earliest = (
        await db.execute(
            select(AffiliatePlanVersion)
            .where(AffiliatePlanVersion.organization_id == organization_id)
            .order_by(AffiliatePlanVersion.valid_from)
            .limit(1)
        )
    ).scalar_one_or_none()
    if earliest:
        return earliest
    row = AffiliatePlanVersion(
        organization_id=organization_id, label=PLAN_VERSION_LABEL, valid_from=DEFAULT_PLAN_VALID_FROM,
        config=DEFAULT_PLAN, notes="Specifica tecnica 1.1 del 28/10/2026 e Piano Compensi del 29/10/2026.",
    )
    db.add(row)
    await db.flush()
    return row


async def list_plan_versions(db: AsyncSession, organization_id: uuid.UUID) -> list[AffiliatePlanVersion]:
    await get_plan(db, organization_id)
    return list(
        (
            await db.execute(
                select(AffiliatePlanVersion)
                .where(AffiliatePlanVersion.organization_id == organization_id)
                .order_by(AffiliatePlanVersion.valid_from.desc())
            )
        ).scalars()
    )


async def create_plan_version(
    db: AsyncSession, *, organization_id: uuid.UUID, config: dict[str, Any], valid_from: datetime,
    label: str, notes: str | None, actor_user_id: uuid.UUID,
) -> AffiliatePlanVersion:
    """A new version only takes effect from now on: starting it in the past
    would change the rules of operations already computed (INT-10)."""
    validate_plan(config)
    if valid_from.tzinfo is None:
        valid_from = valid_from.replace(tzinfo=ROME)
    if valid_from < utcnow() - timedelta(minutes=5):
        raise AffiliateError("Una nuova versione del piano non può valere per il passato.")
    current = await get_plan(db, organization_id)
    row = AffiliatePlanVersion(
        id=uuid.uuid4(), organization_id=organization_id, label=label, valid_from=valid_from, config=config, notes=notes,
        created_by_user_id=actor_user_id,
    )
    db.add(row)
    await _audit(db, organization_id, actor_user_id, "affiliate.plan.version_created", "affiliate_plan", row.id,
                 previous={"version_id": str(current.id), "label": current.label},
                 new={"label": label, "valid_from": valid_from.isoformat()})
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise AffiliateError("Esiste già una versione del piano con la stessa data di inizio.") from exc
    await db.commit()
    return row


# --- Network ----------------------------------------------------------------


async def parent_map(db: AsyncSession, organization_id: uuid.UUID) -> dict[uuid.UUID, uuid.UUID | None]:
    rows = await db.execute(
        select(NetworkNode.agent_id, NetworkNode.direct_parent_agent_id).where(
            NetworkNode.organization_id == organization_id, NetworkNode.effective_to.is_(None)
        )
    )
    return {agent: parent for agent, parent in rows.all()}


async def agents_by_id(db: AsyncSession, organization_id: uuid.UUID) -> dict[uuid.UUID, AgentProfile]:
    rows = await db.execute(select(AgentProfile).where(AgentProfile.organization_id == organization_id))
    return {a.id: a for a in rows.scalars()}


async def agent_for_user(db: AsyncSession, organization_id: uuid.UUID, user_id: uuid.UUID) -> AgentProfile:
    agent = (
        await db.execute(
            select(AgentProfile).where(AgentProfile.organization_id == organization_id, AgentProfile.user_id == user_id)
        )
    ).scalar_one_or_none()
    if agent is None:
        raise AffiliateError("Questo account non ha un profilo Digital Ambassador.")
    return agent


async def _get_agent(db: AsyncSession, organization_id: uuid.UUID, agent_id: uuid.UUID) -> AgentProfile:
    agent = await db.get(AgentProfile, agent_id)
    if agent is None or agent.organization_id != organization_id:
        raise AffiliateError("Digital Ambassador non trovato.")
    return agent


# --- Clients ----------------------------------------------------------------


async def create_client(
    db: AsyncSession, *, organization_id: uuid.UUID, agent_id: uuid.UUID, company_name: str,
    vat_number: str | None, contact_name: str | None, email: str | None, phone: str | None,
) -> AffiliateClient:
    name = (company_name or "").strip()
    if len(name) < 2:
        raise AffiliateError("Scrivi la ragione sociale dell'impresa cliente.")
    client = AffiliateClient(
        organization_id=organization_id, agent_id=agent_id, company_name=name,
        vat_number=(vat_number or "").strip() or None, contact_name=(contact_name or "").strip() or None,
        email=(email or "").strip().lower() or None, phone=(phone or "").strip() or None,
    )
    db.add(client)
    await db.commit()
    return client


async def list_clients(
    db: AsyncSession, organization_id: uuid.UUID, agent_id: uuid.UUID | None = None
) -> list[AffiliateClient]:
    q = select(AffiliateClient).where(AffiliateClient.organization_id == organization_id)
    if agent_id:
        q = q.where(AffiliateClient.agent_id == agent_id)
    return list((await db.execute(q.order_by(AffiliateClient.company_name))).scalars())


async def _get_client(db: AsyncSession, organization_id: uuid.UUID, client_id: uuid.UUID) -> AffiliateClient:
    client = await db.get(AffiliateClient, client_id)
    if client is None or client.organization_id != organization_id:
        raise AffiliateError("Impresa cliente non trovata.")
    return client


# --- Operations: creation ---------------------------------------------------


async def _next_sequence(db: AsyncSession, organization_id: uuid.UUID, prefix: str) -> int:
    """Next number for a deterministic idempotency key. Two concurrent
    requests compute the same number and the second hits the UNIQUE key."""
    count = await db.scalar(
        select(func.count()).select_from(AffiliateOperation).where(
            AffiliateOperation.organization_id == organization_id,
            AffiliateOperation.idempotency_key.like(f"{prefix}:%"),
        )
    )
    return int(count or 0) + 1


async def _insert_operation(db: AsyncSession, op: AffiliateOperation) -> AffiliateOperation:
    db.add(op)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise AffiliateError(
            "Questa operazione è già stata registrata: aggiorna la pagina prima di riprovare."
        ) from exc
    return op


async def create_purchase(
    db: AsyncSession, *, organization_id: uuid.UUID, agent_id: uuid.UUID, product_code: str,
    actor_user_id: uuid.UUID | None, period: str | None = None, payment_method: str | None = None,
    note: str | None = None,
) -> AffiliateOperation:
    """Subscription month, licence package or event tickets bought by the
    affiliate. Price and points are taken from the plan, never from input."""
    plan = await get_plan(db, organization_id)
    product = product_index(plan.config).get(product_code)
    if product is None or product["kind"] not in POINT_KINDS:
        raise AffiliateError("Prodotto non disponibile nel piano attuale.")
    agent = await _get_agent(db, organization_id, agent_id)
    kind = product["kind"]
    price = engine.money(product["price"])
    nominal = engine.money(product.get("nominal", product["price"]))
    if kind == "SUBSCRIPTION_PAYMENT":
        period = engine.validate_period(period or current_period())
        if await _is_closed(db, organization_id, period):
            raise AffiliateError(f"Il mese {period} è già chiuso: la mensilità non può più generare punti.")
        prefix = f"SUB:{agent.id}:{period}"
        quantity = 1
    else:
        period = None
        prefix = f"{kind}:{agent.id}:{product_code}"
        quantity = int(product.get("licenses") or product.get("tickets") or 1)
    seq = await _next_sequence(db, organization_id, prefix)
    op = AffiliateOperation(
        organization_id=organization_id, kind=kind, status="PENDING", agent_id=agent.id,
        product_code=product_code, quantity=quantity, period=period, nominal_amount=nominal,
        discount_amount=nominal - price, paid_amount=price, bc_points=int(product["bc"]),
        plan_version_id=plan.id, idempotency_key=f"{prefix}:{seq}", payment_method=payment_method,
        note=note, created_by_user_id=actor_user_id,
    )
    await _insert_operation(db, op)
    if kind == "SUBSCRIPTION_PAYMENT":
        await _ensure_subscription(db, organization_id, agent.id)
    await db.commit()
    return op


async def create_pack_sale(
    db: AsyncSession, *, organization_id: uuid.UUID, agent_id: uuid.UUID, client_id: uuid.UUID,
    pack_code: str, actor_user_id: uuid.UUID | None, payment_method: str | None = None, note: str | None = None,
) -> AffiliateOperation:
    plan = await get_plan(db, organization_id)
    pack = next((p for p in plan.config["packs"] if p["code"] == pack_code), None)
    if pack is None:
        raise AffiliateError("Pack non disponibile nel piano attuale.")
    client = await _own_client(db, organization_id, agent_id, client_id)
    prefix = f"PACK:{client.id}:{pack_code}"
    price = engine.money(pack["price"])
    op = AffiliateOperation(
        organization_id=organization_id, kind="PACK_SALE", status="PENDING", agent_id=agent_id,
        client_id=client.id, product_code=pack_code, nominal_amount=price, paid_amount=price, bc_points=0,
        plan_version_id=plan.id, idempotency_key=f"{prefix}:{await _next_sequence(db, organization_id, prefix)}",
        payment_method=payment_method, note=note, created_by_user_id=actor_user_id,
    )
    await _insert_operation(db, op)
    await db.commit()
    return op


async def create_topup(
    db: AsyncSession, *, organization_id: uuid.UUID, agent_id: uuid.UUID, client_id: uuid.UUID,
    amount: Decimal, actor_user_id: uuid.UUID | None, payment_method: str | None = None, note: str | None = None,
) -> AffiliateOperation:
    """A client's MamiCash top-up. The value is the client's choice, so it is
    the one amount that comes from input; it is the base of BM, not a price."""
    value = engine.money(amount)
    if value <= 0 or value > MAX_TOPUP:
        raise AffiliateError("Indica un valore di ricarica maggiore di zero.")
    plan = await get_plan(db, organization_id)
    client = await _own_client(db, organization_id, agent_id, client_id)
    prefix = f"TOPUP:{client.id}"
    op = AffiliateOperation(
        organization_id=organization_id, kind="MAMICASH_TOPUP", status="PENDING", agent_id=client.agent_id,
        client_id=client.id, nominal_amount=value, paid_amount=value, bc_points=0, plan_version_id=plan.id,
        idempotency_key=f"{prefix}:{await _next_sequence(db, organization_id, prefix)}",
        payment_method=payment_method, note=note, created_by_user_id=actor_user_id,
    )
    await _insert_operation(db, op)
    await db.commit()
    return op


async def create_resale(
    db: AsyncSession, *, organization_id: uuid.UUID, agent_id: uuid.UUID, license_id: uuid.UUID,
    client_id: uuid.UUID, actor_user_id: uuid.UUID | None, payment_method: str | None = None,
    note: str | None = None,
) -> AffiliateOperation:
    """Resale of an available licence to a client company. The licence is
    reserved now and becomes RESOLD when the payment is confirmed."""
    plan = await get_plan(db, organization_id)
    resale = plan.config["license_resale"]
    client = await _own_client(db, organization_id, agent_id, client_id)
    lic = (
        await db.execute(select(AffiliateLicense).where(AffiliateLicense.id == license_id).with_for_update())
    ).scalar_one_or_none()
    if lic is None or lic.organization_id != organization_id or lic.owner_agent_id != agent_id:
        raise AffiliateError("Licenza non trovata tra quelle disponibili.")
    if lic.status != "AVAILABLE":
        raise AffiliateError("Questa licenza non è più disponibile.")
    prefix = f"RESALE:{lic.id}"
    price = engine.money(resale["price"])
    op = AffiliateOperation(
        organization_id=organization_id, kind="LICENSE_RESALE", status="PENDING", agent_id=agent_id,
        client_id=client.id, license_id=lic.id, product_code="LICENSE_RESALE", nominal_amount=price,
        paid_amount=price, bc_points=0, plan_version_id=plan.id,
        idempotency_key=f"{prefix}:{await _next_sequence(db, organization_id, prefix)}",
        payment_method=payment_method, note=note, created_by_user_id=actor_user_id,
    )
    await _insert_operation(db, op)
    lic.status = "RESERVED"
    lic.client_id = client.id
    await db.commit()
    return op


async def _own_client(
    db: AsyncSession, organization_id: uuid.UUID, agent_id: uuid.UUID, client_id: uuid.UUID
) -> AffiliateClient:
    client = await _get_client(db, organization_id, client_id)
    if client.agent_id != agent_id:
        raise AffiliateError("Questa impresa cliente è seguita da un altro Digital Ambassador.")
    return client


async def _ensure_subscription(db: AsyncSession, organization_id: uuid.UUID, agent_id: uuid.UUID) -> AffiliateSubscription:
    sub = (
        await db.execute(
            select(AffiliateSubscription).where(
                AffiliateSubscription.organization_id == organization_id, AffiliateSubscription.agent_id == agent_id
            )
        )
    ).scalar_one_or_none()
    if sub is None:
        sub = AffiliateSubscription(organization_id=organization_id, agent_id=agent_id, status="ACTIVE", started_at=utcnow())
        db.add(sub)
        await db.flush()
    return sub


async def set_subscription_status(
    db: AsyncSession, *, organization_id: uuid.UUID, agent_id: uuid.UUID, status: str, actor_user_id: uuid.UUID,
    reason: str | None,
) -> AffiliateSubscription:
    if status not in ("ACTIVE", "SUSPENDED", "CANCELLED"):
        raise AffiliateError("Stato dell'abbonamento non valido.")
    sub = await _ensure_subscription(db, organization_id, agent_id)
    previous = sub.status
    sub.status = status
    sub.cancelled_at = utcnow() if status == "CANCELLED" else None
    await _audit(db, organization_id, actor_user_id, "affiliate.subscription.status", "affiliate_subscription", sub.id,
                 previous={"status": previous}, new={"status": status}, reason=reason)
    await db.commit()
    return sub


# --- Operations from an external shop (Mamify) -------------------------------


async def record_external_operation(
    db: AsyncSession, *, organization_id: uuid.UUID, plan_code: str, agent_id: uuid.UUID,
    idempotency_key: str, client_id: uuid.UUID | None = None, topup_amount: Decimal | None = None,
    note: str | None = None,
) -> tuple[AffiliateOperation, bool]:
    """An order already paid on the external shop, recorded and confirmed in
    one step. Returns (operation, created).

    The key is the order line's, so the same line received again (webhook
    redelivered, or seen also by the periodic check) returns the operation
    already written instead of a second one. Prices and points still come
    from the plan; only a top-up's value comes from the order, as it does
    from the form."""
    existing = (await db.execute(
        select(AffiliateOperation).where(
            AffiliateOperation.organization_id == organization_id, AffiliateOperation.idempotency_key == idempotency_key
        )
    )).scalar_one_or_none()
    if existing is not None:
        if existing.status == "PENDING":
            # Recorded, but the confirmation failed last time (e.g. a closed
            # month): try it again rather than leave it pending forever.
            existing = await confirm_operation(db, organization_id=organization_id, operation_id=existing.id,
                                               actor_user_id=None)
        return existing, False

    plan = await get_plan(db, organization_id)
    agent = await _get_agent(db, organization_id, agent_id)
    base = {
        "organization_id": organization_id, "status": "PENDING", "agent_id": agent.id, "plan_version_id": plan.id,
        "idempotency_key": idempotency_key, "payment_method": "MAMIFY", "note": note, "client_id": client_id,
    }
    if plan_code == "MAMICASH_TOPUP":
        value = engine.money(topup_amount or 0)
        if value <= 0 or value > MAX_TOPUP or client_id is None:
            raise AffiliateError("Ricarica MamiCash senza un valore o senza impresa cliente.")
        op = AffiliateOperation(**base, kind="MAMICASH_TOPUP", nominal_amount=value, paid_amount=value, bc_points=0)
    else:
        product = product_index(plan.config).get(plan_code)
        if product is None:
            raise AffiliateError(f"Il prodotto {plan_code} non esiste nel piano attuale.")
        kind = product["kind"]
        price = engine.money(product["price"])
        nominal = engine.money(product.get("nominal", product["price"]))
        if kind == "PACK_SALE":
            if client_id is None:
                raise AffiliateError("Vendita di un Pack senza impresa cliente.")
            op = AffiliateOperation(**base, kind=kind, product_code=plan_code, nominal_amount=price,
                                    paid_amount=price, bc_points=0)
        else:
            period = None
            if kind == "SUBSCRIPTION_PAYMENT":
                period = await _first_unpaid_month(db, organization_id, agent.id)
                await _ensure_subscription(db, organization_id, agent.id)
            op = AffiliateOperation(
                **base, kind=kind, product_code=plan_code, period=period,
                quantity=int(product.get("licenses") or product.get("tickets") or 1),
                nominal_amount=nominal, discount_amount=nominal - price, paid_amount=price,
                bc_points=int(product["bc"]),
            )
    db.add(op)
    try:
        await db.commit()
    except IntegrityError:
        # The same line handled at the same moment by another request (two
        # webhooks for one order): that request owns it.
        await db.rollback()
        other = (await db.execute(select(AffiliateOperation).where(
            AffiliateOperation.organization_id == organization_id, AffiliateOperation.idempotency_key == idempotency_key
        ))).scalar_one_or_none()
        if other is None:
            raise AffiliateError("Questo mese di abbonamento risulta già pagato.") from None
        return other, False
    return await confirm_operation(db, organization_id=organization_id, operation_id=op.id, actor_user_id=None), True


async def _first_unpaid_month(db: AsyncSession, organization_id: uuid.UUID, agent_id: uuid.UUID) -> str:
    """The month a subscription payment pays: the current one, or the next
    not yet paid when the affiliate pays in advance."""
    paid = set((await db.execute(
        select(AffiliateOperation.period).where(
            AffiliateOperation.organization_id == organization_id, AffiliateOperation.agent_id == agent_id,
            AffiliateOperation.kind == "SUBSCRIPTION_PAYMENT", AffiliateOperation.status != "CANCELLED",
        )
    )).scalars())
    period = current_period()
    while period in paid:
        period = engine.next_period(period)
    return period


# --- Operations: confirmation -----------------------------------------------


async def _lock_operation(db: AsyncSession, organization_id: uuid.UUID, operation_id: uuid.UUID) -> AffiliateOperation:
    op = (
        await db.execute(select(AffiliateOperation).where(AffiliateOperation.id == operation_id).with_for_update())
    ).scalar_one_or_none()
    if op is None or op.organization_id != organization_id:
        raise AffiliateError("Operazione non trovata.")
    return op


async def confirm_operation(
    db: AsyncSession, *, organization_id: uuid.UUID, operation_id: uuid.UUID, actor_user_id: uuid.UUID | None,
    payment_method: str | None = None,
) -> AffiliateOperation:
    """Records that the money arrived and applies the operation's effects.

    Running it twice is harmless (TEST-10, TEST-33): the row lock serializes
    concurrent confirmations, a confirmed operation is returned untouched,
    and the UNIQUE keys on points and commissions would refuse a second
    write anyway."""
    op = await _lock_operation(db, organization_id, operation_id)
    if op.status == "CONFIRMED":
        return op
    if op.status != "PENDING":
        raise AffiliateError("Solo un'operazione in attesa di pagamento può essere confermata.")
    plan = await db.get(AffiliatePlanVersion, op.plan_version_id)
    config = plan.config
    now = utcnow()
    if op.kind != "SUBSCRIPTION_PAYMENT":
        op.period = current_period(now)
    if await _is_closed(db, organization_id, op.period):
        raise AffiliateError(f"Il mese {op.period} è già chiuso.")

    if op.kind in POINT_KINDS:
        db.add(AffiliatePointEntry(
            organization_id=organization_id, operation_id=op.id, agent_id=op.agent_id, period=op.period,
            points=op.bc_points,
        ))
    if op.kind == "LICENSE_PURCHASE":
        unit_cost = engine.money(op.paid_amount / op.quantity)
        for i in range(op.quantity):
            db.add(AffiliateLicense(
                organization_id=organization_id, code=f"L-{op.id.hex[:8].upper()}-{i + 1:02d}",
                owner_agent_id=op.agent_id, purchase_operation_id=op.id, origin="PURCHASE", unit_cost=unit_cost,
            ))
    elif op.kind == "PACK_SALE":
        await _write_distribution(db, op, config, kind="BD", rates=config["bd_rates"], paid_on=now)
    elif op.kind == "MAMICASH_TOPUP":
        await _write_distribution(db, op, config, kind="BM", rates=config["bm_rates"], paid_on=now)
        client = await db.get(AffiliateClient, op.client_id, with_for_update=True)
        client.mamicash_balance = (client.mamicash_balance or Decimal("0")) + op.paid_amount
    elif op.kind == "LICENSE_RESALE":
        await _apply_resale(db, op, config, now)

    op.status = "CONFIRMED"
    op.confirmed_at = now
    op.confirmed_by_user_id = actor_user_id
    if payment_method:
        op.payment_method = payment_method
    await db.flush()
    if op.kind == "SUBSCRIPTION_PAYMENT":
        await _maybe_gift_license(db, op, config, now)
    await _audit(db, organization_id, actor_user_id, "affiliate.operation.confirmed", "affiliate_operation", op.id,
                 new={"kind": op.kind, "amount": str(op.paid_amount), "bc": op.bc_points, "period": op.period})
    await db.commit()
    return op


async def _write_distribution(
    db: AsyncSession, op: AffiliateOperation, config: dict, *, kind: str, rates: list, paid_on: datetime
) -> None:
    parents = await parent_map(db, op.organization_id)
    chain = engine.upline(op.agent_id, parents, limit=len(rates))
    shares = engine.distribute(op.paid_amount, rates, chain)
    theoretical = engine.theoretical_total(op.paid_amount, rates)
    for share in shares:
        if share.beneficiary is None:
            continue
        db.add(AffiliateCommission(
            organization_id=op.organization_id, kind=kind, operation_id=op.id, period=op.period,
            beneficiary_agent_id=share.beneficiary, position=share.position, rate=share.rate,
            base_amount=op.paid_amount, amount=share.amount, status="PAYABLE", payable_on=paid_on.astimezone(ROME).date(),
            plan_version_id=op.plan_version_id,
            details={"theoretical_total": str(theoretical), "assigned_positions": len(chain)},
        ))


async def _apply_resale(db: AsyncSession, op: AffiliateOperation, config: dict, now: datetime) -> None:
    resale = config["license_resale"]
    lic = await db.get(AffiliateLicense, op.license_id, with_for_update=True)
    if lic is None or lic.status != "RESERVED":
        raise AffiliateError("La licenza di questa rivendita non è più riservata.")
    lic.status = "RESOLD"
    lic.resale_operation_id = op.id
    lic.client_id = op.client_id
    lic.resold_at = now
    seller = engine.money(resale["seller_amount"])
    db.add(AffiliateCommission(
        organization_id=op.organization_id, kind="RESALE", operation_id=op.id, period=op.period,
        beneficiary_agent_id=op.agent_id, position=1, rate=None, base_amount=op.paid_amount, amount=seller,
        status="PAYABLE", payable_on=now.astimezone(ROME).date(), plan_version_id=op.plan_version_id,
        details={
            "license_code": lic.code, "company_amount": resale["company_amount"],
            "client_mamicash": resale["client_mamicash"], "license_unit_cost": str(lic.unit_cost),
            "margin": str(seller - lic.unit_cost),
        },
    ))
    client = await db.get(AffiliateClient, op.client_id, with_for_update=True)
    client.mamicash_balance = (client.mamicash_balance or Decimal("0")) + engine.money(resale["client_mamicash"])


async def _maybe_gift_license(db: AsyncSession, op: AffiliateOperation, config: dict, now: datetime) -> None:
    """Promo: one free licence for every completed cycle of paid months. The
    cycle number is in the idempotency key, so a cycle can award once."""
    every = int(config.get("promotions", {}).get("gift_license_every_paid_months") or 0)
    if every <= 0:
        return
    paid = await db.scalar(
        select(func.count()).select_from(AffiliateOperation).where(
            AffiliateOperation.organization_id == op.organization_id, AffiliateOperation.agent_id == op.agent_id,
            AffiliateOperation.kind == "SUBSCRIPTION_PAYMENT", AffiliateOperation.status == "CONFIRMED",
        )
    )
    if not paid or paid % every:
        return
    cycle = paid // every
    key = f"GIFT:{op.agent_id}:{cycle}"
    exists = await db.scalar(
        select(AffiliateOperation.id).where(
            AffiliateOperation.organization_id == op.organization_id, AffiliateOperation.idempotency_key == key
        )
    )
    if exists:
        return
    gift = AffiliateOperation(
        organization_id=op.organization_id, kind="GIFT_LICENSE", status="CONFIRMED", agent_id=op.agent_id,
        product_code="LICENSE_1", quantity=1, period=op.period, bc_points=0, plan_version_id=op.plan_version_id,
        idempotency_key=key, note=f"Licenza in omaggio per il ciclo {cycle} di {every} mensilità pagate.",
        confirmed_at=now,
    )
    db.add(gift)
    await db.flush()
    db.add(AffiliateLicense(
        organization_id=op.organization_id, code=f"G-{gift.id.hex[:8].upper()}-01", owner_agent_id=op.agent_id,
        purchase_operation_id=gift.id, origin="GIFT", unit_cost=Decimal("0.00"),
    ))


async def cancel_operation(
    db: AsyncSession, *, organization_id: uuid.UUID, operation_id: uuid.UUID, actor_user_id: uuid.UUID,
    reason: str | None, agent_id: uuid.UUID | None = None,
) -> AffiliateOperation:
    """Withdraws an order that was never paid. `agent_id` restricts the
    action to the affiliate's own orders."""
    op = await _lock_operation(db, organization_id, operation_id)
    if agent_id is not None and op.agent_id != agent_id:
        raise AffiliateError("Operazione non trovata.")
    if op.status != "PENDING":
        raise AffiliateError("Si può annullare solo un'operazione non ancora pagata.")
    op.status = "CANCELLED"
    if op.license_id:
        lic = await db.get(AffiliateLicense, op.license_id, with_for_update=True)
        if lic and lic.status == "RESERVED":
            lic.status = "AVAILABLE"
            lic.client_id = None
    await _audit(db, organization_id, actor_user_id, "affiliate.operation.cancelled", "affiliate_operation", op.id,
                 previous={"status": "PENDING"}, new={"status": "CANCELLED"}, reason=reason)
    await db.commit()
    return op


async def reverse_operation(
    db: AsyncSession, *, organization_id: uuid.UUID, operation_id: uuid.UUID, actor_user_id: uuid.UUID, reason: str,
) -> AffiliateOperation:
    """Authorized correction of a confirmed operation (ADM-05). Nothing is
    deleted: a REVERSAL operation carries negative points and, for amounts
    already paid, negative commissions to recover. Points of a closed month
    are reversed in the current month, so consolidated history stays as it
    was computed (INT-10)."""
    if not (reason or "").strip():
        raise AffiliateError("Indica il motivo della rettifica.")
    op = await _lock_operation(db, organization_id, operation_id)
    if op.kind in ("REVERSAL", "GIFT_LICENSE") or op.status != "CONFIRMED":
        raise AffiliateError("Si può rettificare solo un'operazione confermata.")
    now = utcnow()
    open_period = current_period(now)
    reversal = AffiliateOperation(
        organization_id=organization_id, kind="REVERSAL", status="CONFIRMED", agent_id=op.agent_id,
        client_id=op.client_id, product_code=op.product_code, quantity=op.quantity, period=open_period,
        nominal_amount=op.nominal_amount, paid_amount=op.paid_amount, bc_points=-op.bc_points,
        plan_version_id=op.plan_version_id, idempotency_key=f"REVERSAL:{op.id}", reverses_operation_id=op.id,
        note=reason.strip(), created_by_user_id=actor_user_id, confirmed_at=now, confirmed_by_user_id=actor_user_id,
    )
    await _insert_operation(db, reversal)

    if op.kind == "LICENSE_PURCHASE":
        licenses = list((await db.execute(
            select(AffiliateLicense).where(AffiliateLicense.purchase_operation_id == op.id).with_for_update()
        )).scalars())
        if any(lic.status != "AVAILABLE" for lic in licenses):
            await db.rollback()
            raise AffiliateError("Alcune licenze di questo acquisto sono già state rivendute: rettifica prima le rivendite.")
        for lic in licenses:
            lic.status = "VOID"
    if op.kind in POINT_KINDS and op.bc_points:
        point_period = op.period if not await _is_closed(db, organization_id, op.period) else open_period
        db.add(AffiliatePointEntry(
            organization_id=organization_id, operation_id=reversal.id, agent_id=op.agent_id, period=point_period,
            points=-op.bc_points,
        ))
    if op.kind == "LICENSE_RESALE":
        lic = await db.get(AffiliateLicense, op.license_id, with_for_update=True)
        lic.status, lic.resale_operation_id, lic.client_id, lic.resold_at = "AVAILABLE", None, None, None
        client = await db.get(AffiliateClient, op.client_id, with_for_update=True)
        mamicash = engine.money((await db.get(AffiliatePlanVersion, op.plan_version_id)).config["license_resale"]["client_mamicash"])
        client.mamicash_balance -= mamicash
    if op.kind == "MAMICASH_TOPUP":
        client = await db.get(AffiliateClient, op.client_id, with_for_update=True)
        client.mamicash_balance -= op.paid_amount

    commissions = list((await db.execute(
        select(AffiliateCommission).where(AffiliateCommission.operation_id == op.id).with_for_update()
    )).scalars())
    for c in commissions:
        if c.status == "PAYABLE":
            c.status = "CANCELLED"
        elif c.status == "PAID":
            db.add(AffiliateCommission(
                organization_id=organization_id, kind=c.kind, operation_id=reversal.id, period=open_period,
                beneficiary_agent_id=c.beneficiary_agent_id, position=c.position, rate=c.rate,
                base_amount=c.base_amount, amount=-c.amount, status="PAYABLE",
                payable_on=now.astimezone(ROME).date(), plan_version_id=c.plan_version_id,
                details={"recovers_commission_id": str(c.id)},
            ))
    op.status = "REVERSED"
    await _audit(db, organization_id, actor_user_id, "affiliate.operation.reversed", "affiliate_operation", op.id,
                 previous={"status": "CONFIRMED"}, new={"status": "REVERSED", "reversal_id": str(reversal.id)},
                 reason=reason)
    await db.commit()
    return reversal


# --- Volumes and the monthly close ------------------------------------------


async def _is_closed(db: AsyncSession, organization_id: uuid.UUID, period: str | None) -> bool:
    if not period:
        return False
    return bool(await db.scalar(
        select(AffiliatePeriodClose.id).where(
            AffiliatePeriodClose.organization_id == organization_id, AffiliatePeriodClose.period == period
        )
    ))


async def period_points(db: AsyncSession, organization_id: uuid.UUID, period: str) -> dict[uuid.UUID, int]:
    rows = await db.execute(
        select(AffiliatePointEntry.agent_id, func.sum(AffiliatePointEntry.points))
        .where(AffiliatePointEntry.organization_id == organization_id, AffiliatePointEntry.period == period)
        .group_by(AffiliatePointEntry.agent_id)
    )
    return {agent: int(points or 0) for agent, points in rows.all()}


async def compute_period(
    db: AsyncSession, organization_id: uuid.UUID, period: str
) -> tuple[dict[uuid.UUID, engine.VolumeSheet], AffiliatePlanVersion, dict[uuid.UUID, uuid.UUID | None]]:
    """Live volumes of a month: always recomputed from the point entries,
    with the sponsor tree as it is now and the plan valid at month end."""
    parents = await parent_map(db, organization_id)
    sheets = engine.aggregate_volumes(await period_points(db, organization_id, period), parents)
    plan = await get_plan(db, organization_id, at=min(period_end(period), utcnow()))
    return sheets, plan, parents


def _career(sheet: engine.VolumeSheet | None, config: dict) -> engine.CareerResult:
    sheet = sheet or engine.VolumeSheet()
    return engine.evaluate_career(
        sheet.bcp, list(sheet.legs.values()), engine.career_levels(config), required_legs=int(config["required_legs"])
    )


async def close_period(
    db: AsyncSession, *, organization_id: uuid.UUID, period: str, actor_user_id: uuid.UUID | None
) -> AffiliatePeriodClose:
    """Consolidates a finished month: freezes every affiliate's volumes and
    level and writes one BC bonus per qualified affiliate, payable on the
    15th of the following month. The UNIQUE keys make a second close fail
    instead of paying twice (INT-04)."""
    period = engine.validate_period(period)
    if period >= current_period():
        raise AffiliateError("Si può chiudere solo un mese già terminato.")
    if await _is_closed(db, organization_id, period):
        raise AffiliateError(f"Il mese {period} è già chiuso.")
    pending = await db.scalar(
        select(func.count()).select_from(AffiliateOperation).where(
            AffiliateOperation.organization_id == organization_id, AffiliateOperation.status == "PENDING",
            AffiliateOperation.kind == "SUBSCRIPTION_PAYMENT", AffiliateOperation.period == period,
        )
    )
    if pending:
        raise AffiliateError(
            f"Ci sono {pending} mensilità di {period} in attesa di pagamento: confermale o annullale prima di chiudere."
        )
    sheets, plan, _ = await compute_period(db, organization_id, period)
    config = plan.config
    pay_on = career_pay_date(period, int(config.get("career_bonus_pay_day", 15)))
    qualified, total_bonus = 0, Decimal("0")
    for agent_id, sheet in sheets.items():
        result = _career(sheet, config)
        legs = sorted(({"leg_agent_id": str(k), "points": v} for k, v in sheet.legs.items()),
                      key=lambda x: -x["points"])
        db.add(AffiliateMonthlyResult(
            organization_id=organization_id, period=period, agent_id=agent_id, bcp=sheet.bcp, bct=result.bct,
            legs=legs, career_level=result.level, bonus_amount=result.bonus, plan_version_id=plan.id,
        ))
        if result.level:
            qualified += 1
            total_bonus += result.bonus
            db.add(AffiliateCommission(
                organization_id=organization_id, kind="BC", operation_id=None, period=period,
                beneficiary_agent_id=agent_id, position=1, base_amount=Decimal(result.bct), amount=result.bonus,
                career_level=result.level, status="PAYABLE", payable_on=pay_on, plan_version_id=plan.id,
                details={"bcp": sheet.bcp, "bct": result.bct, "legs": legs[:10]},
            ))
    close = AffiliatePeriodClose(
        id=uuid.uuid4(), organization_id=organization_id, period=period, plan_version_id=plan.id, closed_by_user_id=actor_user_id,
        affiliates_count=len(sheets), qualified_count=qualified,
        total_points=sum(s.bcp for s in sheets.values()), total_bonus=total_bonus,
    )
    db.add(close)
    await _audit(db, organization_id, actor_user_id, "affiliate.period.closed", "affiliate_period", close.id,
                 new={"period": period, "qualified": qualified, "total_bonus": str(total_bonus)})
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise AffiliateError(f"Il mese {period} è già stato chiuso da un'altra elaborazione.") from exc
    return close


async def close_previous_period_for_all(db: AsyncSession) -> int:
    """Celery entry point: closes last month for every organization using
    the plan. A month already closed by hand is skipped silently."""
    previous = current_period(utcnow().astimezone(ROME).replace(day=1) - timedelta(days=1))
    org_ids = list((await db.execute(select(AffiliatePlanVersion.organization_id).distinct())).scalars())
    closed = 0
    for org_id in org_ids:
        if await _is_closed(db, org_id, previous):
            continue
        try:
            await close_period(db, organization_id=org_id, period=previous, actor_user_id=None)
            closed += 1
        except AffiliateError:
            await db.rollback()
    return closed


async def mark_commissions_paid(
    db: AsyncSession, *, organization_id: uuid.UUID, commission_ids: list[uuid.UUID], actor_user_id: uuid.UUID
) -> int:
    """Only due, unpaid rows move to PAID; the row lock and the status
    filter make a repeated click a no-op (INT-04)."""
    rows = list((await db.execute(
        select(AffiliateCommission).where(
            AffiliateCommission.organization_id == organization_id, AffiliateCommission.id.in_(commission_ids),
            AffiliateCommission.status == "PAYABLE", AffiliateCommission.payable_on <= today_rome(),
        ).with_for_update()
    )).scalars())
    now = utcnow()
    for c in rows:
        c.status, c.paid_at, c.paid_by_user_id = "PAID", now, actor_user_id
    if rows:
        await _audit(db, organization_id, actor_user_id, "affiliate.commissions.paid", "affiliate_commission",
                     rows[0].id, new={"ids": [str(c.id) for c in rows], "total": str(sum(c.amount for c in rows))})
    await db.commit()
    return len(rows)


# --- Read models ------------------------------------------------------------


def _agent_brief(agent: AgentProfile | None) -> dict | None:
    if agent is None:
        return None
    return {"id": agent.id, "name": agent.display_name, "code": agent.promoter_code, "status": agent.status}


async def subscription_info(db: AsyncSession, organization_id: uuid.UUID, agent_id: uuid.UUID, config: dict) -> dict:
    sub = (await db.execute(select(AffiliateSubscription).where(
        AffiliateSubscription.organization_id == organization_id, AffiliateSubscription.agent_id == agent_id
    ))).scalar_one_or_none()
    paid_periods = list((await db.execute(
        select(AffiliateOperation.period).where(
            AffiliateOperation.organization_id == organization_id, AffiliateOperation.agent_id == agent_id,
            AffiliateOperation.kind == "SUBSCRIPTION_PAYMENT", AffiliateOperation.status == "CONFIRMED",
        ).order_by(AffiliateOperation.period.desc())
    )).scalars())
    every = int(config.get("promotions", {}).get("gift_license_every_paid_months") or 0)
    this = current_period()
    return {
        "status": sub.status if sub else "NONE",
        "started_at": sub.started_at if sub else None,
        "monthly_fee": engine.money(config["subscription"]["price"]),
        "paid_months": len(paid_periods),
        "last_paid_period": paid_periods[0] if paid_periods else None,
        "current_period_paid": this in paid_periods,
        "months_to_gift_license": (every - len(paid_periods) % every) if every else None,
    }


async def affiliate_summary(db: AsyncSession, organization_id: uuid.UUID, agent_id: uuid.UUID) -> dict:
    """Everything the Digital Ambassador area shows (UI-01..UI-10), and the
    admin's detail page of one affiliate (ADM-02)."""
    agent = await _get_agent(db, organization_id, agent_id)
    period = current_period()
    sheets, plan, parents = await compute_period(db, organization_id, period)
    agents = await agents_by_id(db, organization_id)
    config = plan.config
    sheet = sheets.get(agent.id) or engine.VolumeSheet()
    career = _career(sheet, config)
    children = [a for a, p in parents.items() if p == agent.id]
    legs = sorted(
        ({"agent": _agent_brief(agents.get(c)), "points": sheet.legs.get(c, 0),
          "descendants": _count_descendants(c, parents)} for c in children),
        key=lambda x: -x["points"],
    )
    commissions = await db.execute(
        select(AffiliateCommission.kind, AffiliateCommission.status, func.sum(AffiliateCommission.amount))
        .where(AffiliateCommission.organization_id == organization_id,
               AffiliateCommission.beneficiary_agent_id == agent.id)
        .group_by(AffiliateCommission.kind, AffiliateCommission.status)
    )
    totals: dict[str, dict[str, Decimal]] = defaultdict(lambda: {"PAYABLE": Decimal("0"), "PAID": Decimal("0")})
    for kind, status, amount in commissions.all():
        if status in ("PAYABLE", "PAID"):
            totals[kind][status] += amount or Decimal("0")
    licenses = await db.execute(
        select(AffiliateLicense.status, func.count()).where(
            AffiliateLicense.organization_id == organization_id, AffiliateLicense.owner_agent_id == agent.id
        ).group_by(AffiliateLicense.status)
    )
    license_counts = {status: count for status, count in licenses.all()}
    history = list((await db.execute(
        select(AffiliateMonthlyResult).where(
            AffiliateMonthlyResult.organization_id == organization_id, AffiliateMonthlyResult.agent_id == agent.id
        ).order_by(AffiliateMonthlyResult.period.desc()).limit(12)
    )).scalars())
    return {
        "agent": _agent_brief(agent),
        "joined_at": agent.joined_at,
        "sponsor": _agent_brief(agents.get(parents.get(agent.id))) if parents.get(agent.id) else None,
        "direct_count": len(children),
        "network_size": _count_descendants(agent.id, parents),
        "subscription": await subscription_info(db, organization_id, agent.id, config),
        "period": period,
        "plan_version": {"id": plan.id, "label": plan.label},
        "career": {
            "bcp": career.bcp, "bct": career.bct, "level": career.level, "bonus": career.bonus,
            "next_level": career.next_level, "next_total_bc": career.next_total_bc,
            "next_leg_min_bc": career.next_leg_min_bc, "next_qualifying_legs": career.next_qualifying_legs,
            "required_legs": career.required_legs, "pay_on": career_pay_date(period, int(config.get("career_bonus_pay_day", 15))),
        },
        "legs": legs,
        "commissions": {k: {"payable": v["PAYABLE"], "paid": v["PAID"]} for k, v in totals.items()},
        "licenses": {
            "available": license_counts.get("AVAILABLE", 0), "reserved": license_counts.get("RESERVED", 0),
            "resold": license_counts.get("RESOLD", 0),
        },
        "history": [
            {"period": h.period, "bcp": h.bcp, "bct": h.bct, "level": h.career_level, "bonus": h.bonus_amount}
            for h in history
        ],
        "rome_event": _rome_event_status(config, period, career.bct, history),
    }


def _rome_event_status(config: dict, period: str, live_bct: int, history: list[AffiliateMonthlyResult]) -> dict | None:
    promo = config.get("promotions", {}).get("rome_launch_event")
    if not promo:
        return None
    target_period, target = promo["period"], int(promo["target_bc"])
    if period == target_period:
        bct = live_bct
    else:
        bct = next((h.bct for h in history if h.period == target_period), 0)
    return {"period": target_period, "target_bc": target, "bct": bct, "qualified": bct >= target,
            "open": period <= target_period}


def _count_descendants(agent_id: uuid.UUID, parents: dict[uuid.UUID, uuid.UUID | None]) -> int:
    children: dict[uuid.UUID | None, list[uuid.UUID]] = defaultdict(list)
    for a, p in parents.items():
        children[p].append(a)
    count, stack, seen = 0, list(children.get(agent_id, [])), {agent_id}
    while stack:
        node = stack.pop()
        if node in seen:
            continue
        seen.add(node)
        count += 1
        stack.extend(children.get(node, []))
    return count


async def network_tree(db: AsyncSession, organization_id: uuid.UUID, root_agent_id: uuid.UUID | None) -> list[dict]:
    """Flat list of the (sub)tree, parents before children, with this month's
    volumes per node (NET-01..04) and what the tree view needs to read a
    branch at a glance: its size, the legs that already count, whether the
    month's subscription is paid and the Mamify person behind the node."""
    from app.modules.mamify.models import MamifyMember

    period = current_period()
    sheets, plan, parents = await compute_period(db, organization_id, period)
    agents = await agents_by_id(db, organization_id)
    children: dict[uuid.UUID | None, list[uuid.UUID]] = defaultdict(list)
    for a, p in parents.items():
        children[p].append(a)
    paid_now = set((await db.execute(select(AffiliateOperation.agent_id).where(
        AffiliateOperation.organization_id == organization_id, AffiliateOperation.kind == "SUBSCRIPTION_PAYMENT",
        AffiliateOperation.status == "CONFIRMED", AffiliateOperation.period == period,
    ))).scalars())
    mamify = {m.agent_id: m for m in (await db.execute(
        select(MamifyMember).where(MamifyMember.organization_id == organization_id)
    )).scalars()}
    leg_min = {lv.level: lv.leg_min_bc for lv in engine.career_levels(plan.config)}
    roots = [root_agent_id] if root_agent_id else children.get(None, [])
    out: list[dict] = []
    stack = [(r, 0, None) for r in reversed(roots)]
    seen: set = set()
    while stack:
        node, depth, parent = stack.pop()
        if node in seen or node not in agents:
            continue
        seen.add(node)
        sheet = sheets.get(node) or engine.VolumeSheet()
        career = _career(sheet, plan.config)
        agent = agents[node]
        member = mamify.get(node)
        # Legs meeting the minimum of the next level: what the person is
        # missing to climb, the number a sponsor looks for first.
        target = leg_min.get(career.next_level or 0)
        out.append({
            "agent": _agent_brief(agent), "parent_id": parent, "depth": depth, "bcp": sheet.bcp,
            "bct": sheet.bct, "level": career.level, "direct_count": len(children.get(node, [])),
            "network_size": 0, "active_legs": len([v for v in sheet.legs.values() if v > 0]),
            "qualifying_legs": len([v for v in sheet.legs.values() if target and v >= target]),
            "next_level": career.next_level, "joined_at": agent.joined_at, "subscription_paid": node in paid_now,
            "mamify": {"id": member.mamify_customer_id, "present": member.present, "email": member.email,
                       "phone": member.phone} if member else None,
        })
        for child in reversed(sorted(children.get(node, []), key=lambda c: agents[c].display_name if c in agents else "")):
            stack.append((child, depth + 1, node))
    # Branch sizes bottom-up: rows are in pre-order, so walking them backwards
    # reaches every child before its parent.
    size: dict[uuid.UUID, int] = defaultdict(int)
    for row in reversed(out):
        node_id = row["agent"]["id"]
        row["network_size"] = size[node_id]
        if row["parent_id"] is not None:
            size[row["parent_id"]] += size[node_id] + 1
    return out


async def list_affiliates(db: AsyncSession, organization_id: uuid.UUID, search: str | None = None) -> list[dict]:
    period = current_period()
    sheets, plan, parents = await compute_period(db, organization_id, period)
    agents = await agents_by_id(db, organization_id)
    subs = {s.agent_id: s.status for s in (await db.execute(
        select(AffiliateSubscription).where(AffiliateSubscription.organization_id == organization_id)
    )).scalars()}
    needle = (search or "").strip().lower()
    out = []
    for agent in agents.values():
        if needle and needle not in agent.display_name.lower() and needle not in agent.promoter_code.lower():
            continue
        sheet = sheets.get(agent.id) or engine.VolumeSheet()
        career = _career(sheet, plan.config)
        sponsor = agents.get(parents.get(agent.id)) if parents.get(agent.id) else None
        out.append({
            "agent": _agent_brief(agent), "sponsor": _agent_brief(sponsor), "subscription_status": subs.get(agent.id, "NONE"),
            "bcp": sheet.bcp, "bct": sheet.bct, "legs_count": len([v for v in sheet.legs.values() if v > 0]),
            "level": career.level, "bonus": career.bonus, "joined_at": agent.joined_at,
        })
    return sorted(out, key=lambda x: (-x["bct"], x["agent"]["name"]))


async def list_operations(
    db: AsyncSession, organization_id: uuid.UUID, *, agent_id: uuid.UUID | None = None, status: str | None = None,
    kind: str | None = None, limit: int = 300,
) -> list[dict]:
    q = select(AffiliateOperation).where(AffiliateOperation.organization_id == organization_id)
    if agent_id:
        q = q.where(AffiliateOperation.agent_id == agent_id)
    if status:
        q = q.where(AffiliateOperation.status == status)
    if kind:
        q = q.where(AffiliateOperation.kind == kind)
    ops = list((await db.execute(q.order_by(AffiliateOperation.created_at.desc()).limit(limit))).scalars())
    agents = await agents_by_id(db, organization_id)
    client_ids = {o.client_id for o in ops if o.client_id}
    clients = {c.id: c for c in (await db.execute(
        select(AffiliateClient).where(AffiliateClient.id.in_(client_ids))
    )).scalars()} if client_ids else {}
    license_ids = {o.license_id for o in ops if o.license_id}
    licenses = {lic.id: lic.code for lic in (await db.execute(
        select(AffiliateLicense).where(AffiliateLicense.id.in_(license_ids))
    )).scalars()} if license_ids else {}
    return [{
        "id": o.id, "kind": o.kind, "status": o.status, "agent": _agent_brief(agents.get(o.agent_id)),
        "client": {"id": o.client_id, "name": clients[o.client_id].company_name} if o.client_id in clients else None,
        "product_code": o.product_code, "quantity": o.quantity, "period": o.period,
        "nominal_amount": o.nominal_amount, "discount_amount": o.discount_amount, "paid_amount": o.paid_amount,
        "bc_points": o.bc_points, "license_code": licenses.get(o.license_id), "payment_method": o.payment_method,
        "note": o.note, "reverses_operation_id": o.reverses_operation_id, "created_at": o.created_at,
        "confirmed_at": o.confirmed_at,
    } for o in ops]


async def list_commissions(
    db: AsyncSession, organization_id: uuid.UUID, *, agent_id: uuid.UUID | None = None, kind: str | None = None,
    status: str | None = None, limit: int = 500,
) -> list[dict]:
    q = select(AffiliateCommission).where(AffiliateCommission.organization_id == organization_id)
    if agent_id:
        q = q.where(AffiliateCommission.beneficiary_agent_id == agent_id)
    if kind:
        q = q.where(AffiliateCommission.kind == kind)
    if status:
        q = q.where(AffiliateCommission.status == status)
    rows = list((await db.execute(q.order_by(AffiliateCommission.created_at.desc()).limit(limit))).scalars())
    agents = await agents_by_id(db, organization_id)
    op_ids = {c.operation_id for c in rows if c.operation_id}
    ops = {o.id: o for o in (await db.execute(
        select(AffiliateOperation).where(AffiliateOperation.id.in_(op_ids))
    )).scalars()} if op_ids else {}
    return [{
        "id": c.id, "kind": c.kind, "status": c.status, "period": c.period, "position": c.position, "rate": c.rate,
        "base_amount": c.base_amount, "amount": c.amount, "career_level": c.career_level, "payable_on": c.payable_on,
        "paid_at": c.paid_at, "beneficiary": _agent_brief(agents.get(c.beneficiary_agent_id)),
        "operation": {
            "id": ops[c.operation_id].id, "kind": ops[c.operation_id].kind,
            "product_code": ops[c.operation_id].product_code,
            "seller": _agent_brief(agents.get(ops[c.operation_id].agent_id)),
        } if c.operation_id in ops else None,
        "details": c.details, "created_at": c.created_at,
    } for c in rows]


async def list_licenses(db: AsyncSession, organization_id: uuid.UUID, agent_id: uuid.UUID | None = None) -> list[dict]:
    q = select(AffiliateLicense).where(AffiliateLicense.organization_id == organization_id)
    if agent_id:
        q = q.where(AffiliateLicense.owner_agent_id == agent_id)
    rows = list((await db.execute(q.order_by(AffiliateLicense.created_at.desc(), AffiliateLicense.code))).scalars())
    clients = {c.id: c.company_name for c in await list_clients(db, organization_id)}
    agents = await agents_by_id(db, organization_id)
    return [{
        "id": lic.id, "code": lic.code, "status": lic.status, "origin": lic.origin, "unit_cost": lic.unit_cost,
        "owner": _agent_brief(agents.get(lic.owner_agent_id)), "client": clients.get(lic.client_id),
        "purchase_operation_id": lic.purchase_operation_id, "resale_operation_id": lic.resale_operation_id,
        "resold_at": lic.resold_at, "created_at": lic.created_at,
    } for lic in rows]


async def list_periods(db: AsyncSession, organization_id: uuid.UUID) -> dict:
    closes = list((await db.execute(
        select(AffiliatePeriodClose).where(AffiliatePeriodClose.organization_id == organization_id)
        .order_by(AffiliatePeriodClose.period.desc())
    )).scalars())
    open_periods = sorted({p for p in (await db.execute(
        select(AffiliatePointEntry.period).where(AffiliatePointEntry.organization_id == organization_id).distinct()
    )).scalars()} - {c.period for c in closes}, reverse=True)
    return {
        "current_period": current_period(),
        "open_periods": open_periods,
        "closed": [{
            "period": c.period, "closed_at": c.created_at, "affiliates_count": c.affiliates_count,
            "qualified_count": c.qualified_count, "total_points": c.total_points, "total_bonus": c.total_bonus,
            "automatic": c.closed_by_user_id is None,
        } for c in closes],
    }


async def period_results(db: AsyncSession, organization_id: uuid.UUID, period: str) -> list[dict]:
    """Closed month: frozen rows. Open month: the same shape, computed live."""
    period = engine.validate_period(period)
    agents = await agents_by_id(db, organization_id)
    if await _is_closed(db, organization_id, period):
        rows = (await db.execute(select(AffiliateMonthlyResult).where(
            AffiliateMonthlyResult.organization_id == organization_id, AffiliateMonthlyResult.period == period
        ))).scalars()
        out = [{"agent": _agent_brief(agents.get(r.agent_id)), "bcp": r.bcp, "bct": r.bct, "legs": r.legs,
                "level": r.career_level, "bonus": r.bonus_amount} for r in rows]
        closed = True
    else:
        sheets, plan, _ = await compute_period(db, organization_id, period)
        out = []
        for agent_id, sheet in sheets.items():
            career = _career(sheet, plan.config)
            out.append({"agent": _agent_brief(agents.get(agent_id)), "bcp": sheet.bcp, "bct": career.bct,
                        "legs": sorted(({"leg_agent_id": str(k), "points": v} for k, v in sheet.legs.items()),
                                       key=lambda x: -x["points"]),
                        "level": career.level, "bonus": career.bonus})
        closed = False
    for row in out:
        for leg in row["legs"]:
            leg_agent = agents.get(uuid.UUID(leg["leg_agent_id"]))
            leg["name"] = leg_agent.display_name if leg_agent else None
        row["closed"] = closed
    return sorted(out, key=lambda x: -x["bct"])


async def admin_overview(db: AsyncSession, organization_id: uuid.UUID) -> dict:
    period = current_period()
    sheets, plan, parents = await compute_period(db, organization_id, period)
    config = plan.config
    results = {a: _career(s, config) for a, s in sheets.items()}
    pending = await db.execute(
        select(AffiliateOperation.kind, func.count(), func.sum(AffiliateOperation.paid_amount))
        .where(AffiliateOperation.organization_id == organization_id, AffiliateOperation.status == "PENDING")
        .group_by(AffiliateOperation.kind)
    )
    payable = await db.execute(
        select(AffiliateCommission.kind, func.sum(AffiliateCommission.amount))
        .where(AffiliateCommission.organization_id == organization_id, AffiliateCommission.status == "PAYABLE",
               AffiliateCommission.payable_on <= today_rome())
        .group_by(AffiliateCommission.kind)
    )
    month_ops = await db.execute(
        select(AffiliateOperation.kind, func.count(), func.sum(AffiliateOperation.paid_amount))
        .where(AffiliateOperation.organization_id == organization_id, AffiliateOperation.status == "CONFIRMED",
               AffiliateOperation.period == period)
        .group_by(AffiliateOperation.kind)
    )
    promo = config.get("promotions", {}).get("rome_launch_event")
    rome = None
    if promo:
        agents = await agents_by_id(db, organization_id)
        if promo["period"] == period:
            bct_by_agent = {a: r.bct for a, r in results.items()}
        else:
            bct_by_agent = {r.agent_id: r.bct for r in (await db.execute(select(AffiliateMonthlyResult).where(
                AffiliateMonthlyResult.organization_id == organization_id,
                AffiliateMonthlyResult.period == promo["period"],
            ))).scalars()}
        qualified = [{"agent": _agent_brief(agents.get(a)), "bct": v} for a, v in bct_by_agent.items()
                     if v >= int(promo["target_bc"])]
        rome = {"period": promo["period"], "target_bc": promo["target_bc"],
                "qualified": sorted(qualified, key=lambda x: -x["bct"])}
    return {
        "period": period,
        "plan_version": {"id": plan.id, "label": plan.label},
        "affiliates": len(parents),
        "active_this_month": len([s for s in sheets.values() if s.bcp > 0]),
        "total_points": sum(s.bcp for s in sheets.values()),
        "qualified_this_month": len([r for r in results.values() if r.level]),
        "career_bonus_estimate": sum((r.bonus for r in results.values()), Decimal("0")),
        "levels_distribution": {str(lv): len([r for r in results.values() if r.level == lv]) for lv in range(1, 12)},
        "pending": [{"kind": k, "count": c, "amount": a or Decimal("0")} for k, c, a in pending.all()],
        "payable_now": {k: a or Decimal("0") for k, a in payable.all()},
        "month_operations": [{"kind": k, "count": c, "amount": a or Decimal("0")} for k, c, a in month_ops.all()],
        "rome_event": rome,
    }


# --- Export -----------------------------------------------------------------

EXPORTS = ("operations", "commissions", "licenses", "affiliates")


async def export_csv(db: AsyncSession, organization_id: uuid.UUID, dataset: str, period: str | None = None) -> str:
    """CSV with semicolons and comma decimals, the format Italian Excel opens (ADM-07)."""
    def num(v: Any) -> str:
        return "" if v is None else str(v).replace(".", ",")

    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    if dataset == "operations":
        w.writerow(["id", "tipo", "stato", "affiliato", "codice", "cliente", "prodotto", "quantità", "mese",
                    "nominale", "sconto", "pagato", "BC", "licenza", "creata", "confermata"])
        for o in await list_operations(db, organization_id, limit=100000):
            if period and o["period"] != period:
                continue
            w.writerow([o["id"], o["kind"], o["status"], o["agent"]["name"] if o["agent"] else "",
                        o["agent"]["code"] if o["agent"] else "", o["client"]["name"] if o["client"] else "",
                        o["product_code"] or "", o["quantity"], o["period"] or "", num(o["nominal_amount"]),
                        num(o["discount_amount"]), num(o["paid_amount"]), o["bc_points"], o["license_code"] or "",
                        o["created_at"].isoformat(), o["confirmed_at"].isoformat() if o["confirmed_at"] else ""])
    elif dataset == "commissions":
        w.writerow(["id", "bonus", "stato", "mese", "beneficiario", "codice", "posizione", "aliquota %", "base",
                    "importo", "livello", "pagabile dal", "pagato il", "operazione"])
        for c in await list_commissions(db, organization_id, limit=100000):
            if period and c["period"] != period:
                continue
            w.writerow([c["id"], c["kind"], c["status"], c["period"], c["beneficiary"]["name"] if c["beneficiary"] else "",
                        c["beneficiary"]["code"] if c["beneficiary"] else "", c["position"], num(c["rate"]),
                        num(c["base_amount"]), num(c["amount"]), c["career_level"] or "", c["payable_on"].isoformat(),
                        c["paid_at"].isoformat() if c["paid_at"] else "", c["operation"]["id"] if c["operation"] else ""])
    elif dataset == "licenses":
        w.writerow(["codice", "stato", "origine", "titolare", "costo unitario", "cliente", "rivenduta il"])
        for lic in await list_licenses(db, organization_id):
            w.writerow([lic["code"], lic["status"], lic["origin"], lic["owner"]["name"] if lic["owner"] else "",
                        num(lic["unit_cost"]), lic["client"] or "", lic["resold_at"].isoformat() if lic["resold_at"] else ""])
    elif dataset == "affiliates":
        w.writerow(["nome", "codice", "sponsor", "abbonamento", "BCP", "BCT", "gambe attive", "livello", "bonus stimato"])
        for a in await list_affiliates(db, organization_id):
            w.writerow([a["agent"]["name"], a["agent"]["code"], a["sponsor"]["name"] if a["sponsor"] else "",
                        a["subscription_status"], a["bcp"], a["bct"], a["legs_count"], a["level"] or "", num(a["bonus"])])
    else:
        raise AffiliateError("Esportazione non disponibile.")
    return buf.getvalue()


# --- Audit ------------------------------------------------------------------


async def _audit(
    db: AsyncSession, organization_id: uuid.UUID, actor_user_id: uuid.UUID | None, action: str, entity_type: str,
    entity_id: Any, *, previous: dict | None = None, new: dict | None = None, reason: str | None = None,
) -> None:
    db.add(AuditLog(
        organization_id=organization_id, actor_user_id=actor_user_id, action=action, entity_type=entity_type,
        entity_id=str(entity_id), previous_value=previous, new_value=new, reason=(reason or None),
    ))
