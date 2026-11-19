"""Contract instalments and the commissions each one releases.

- A single payment releases commissions once; a 3- or 12-instalment plan
  releases them in 3 or 12 slices, each only after that instalment is
  actually paid (confirmed by Stripe, or by an administrator when Stripe
  could not collect it).
- Nothing is released before the contract is ACTIVE (documents approved and
  commission preview accepted); instalments paid earlier are released
  together at activation.

Each slice is 1/N of every beneficiary's commission
(commissions/services/run_calculation.py::instalment_share), not the whole
commission N times.

A release is one ContractInstalmentPaid outbox event, claimed per row with a
conditional UPDATE on commission_event_id, so repeated webhooks or clicks can
never release the same instalment twice.
"""

import calendar
import uuid
from datetime import date, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.foundation.db import utcnow
from app.modules.contracts import payment_plans
from app.modules.contracts.models import Contract, ContractInstalment
from app.modules.outbox import service as outbox_service

INSTALMENT_PAID_EVENT = "ContractInstalmentPaid"

SOURCE_STRIPE_CHECKOUT = "STRIPE_CHECKOUT"
SOURCE_STRIPE_INVOICE = "STRIPE_INVOICE"
SOURCE_ADMIN = "ADMIN"

#: Statuses in which a paid instalment releases its commissions straight away.
RELEASING_CONTRACT_STATUSES = frozenset({"ACTIVE", "RENEWED"})


class InstalmentError(Exception):
    pass


def _add_months(d: date, months: int) -> date:
    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def instalments_for(contract: Contract) -> int:
    plan = payment_plans.plan_by_key(contract.payment_plan)
    return plan.instalments if plan is not None else 1


async def list_instalments(db: AsyncSession, *, contract_id: uuid.UUID) -> list[ContractInstalment]:
    return list(
        (
            await db.execute(
                select(ContractInstalment)
                .where(ContractInstalment.contract_id == contract_id)
                .order_by(ContractInstalment.number)
            )
        ).scalars()
    )


async def ensure_schedule(db: AsyncSession, *, contract: Contract) -> list[ContractInstalment]:
    """Create the instalment rows on the first recorded payment, when the
    plan the customer actually paid with is known."""
    existing = await list_instalments(db, contract_id=contract.id)
    if existing:
        return existing
    plan = payment_plans.plan_by_key(contract.payment_plan)
    total = instalments_for(contract)
    gross = int(contract.gross_amount_cents or 0)
    amount = payment_plans.contract_breakdown(plan, contract).instalment_cents if plan is not None else gross
    start = (contract.paid_at or utcnow()).date()
    rows = [
        ContractInstalment(
            organization_id=contract.organization_id,
            contract_id=contract.id,
            number=n,
            instalments_total=total,
            due_date=_add_months(start, n - 1),
            amount_cents=amount,
            status="SCHEDULED",
        )
        for n in range(1, total + 1)
    ]
    db.add_all(rows)
    await db.flush()
    return rows


async def _find_row(
    db: AsyncSession, *, contract: Contract, number: int | None, invoice_id: str | None
) -> ContractInstalment | None:
    rows = await ensure_schedule(db, contract=contract)
    if invoice_id:
        for row in rows:
            if row.stripe_invoice_id == invoice_id:
                return row
    if number is not None:
        return next((r for r in rows if r.number == number), None)
    # New invoice: earliest unpaid instalment not tied to another invoice. A
    # FAILED row keeps its invoice id, so retries match it by id above.
    return next((r for r in rows if r.status != "PAID" and r.stripe_invoice_id is None), None)


async def record_payment(
    db: AsyncSession,
    *,
    contract: Contract,
    source: str,
    number: int | None = None,
    invoice_id: str | None = None,
    actor_user_id: uuid.UUID | None = None,
) -> ContractInstalment | None:
    """Mark one instalment paid and release its commissions if the contract
    is active. Returns None for duplicates or when no instalment is left.
    Does not commit."""
    row = await _find_row(db, contract=contract, number=number, invoice_id=invoice_id)
    if row is None or row.status == "PAID":
        return None
    row.status = "PAID"
    row.paid_at = utcnow()
    row.payment_source = source
    row.confirmed_by_user_id = actor_user_id
    if invoice_id and row.stripe_invoice_id is None:
        row.stripe_invoice_id = invoice_id
    await db.flush()
    if contract.status in RELEASING_CONTRACT_STATUSES:
        await release(db, contract=contract, row=row)
    return row


async def record_failure(db: AsyncSession, *, contract: Contract, invoice_id: str | None) -> ContractInstalment | None:
    row = await _find_row(db, contract=contract, number=None, invoice_id=invoice_id)
    if row is None or row.status == "PAID":
        return None
    row.status = "FAILED"
    if invoice_id and row.stripe_invoice_id is None:
        row.stripe_invoice_id = invoice_id
    await db.flush()
    return row


async def release(db: AsyncSession, *, contract: Contract, row: ContractInstalment) -> bool:
    """Enqueue the event paying this instalment's commission slice; at most
    once per row, first caller wins."""
    event = outbox_service.enqueue(
        organization_id=contract.organization_id,
        event_type=INSTALMENT_PAID_EVENT,
        payload={
            "contract_id": str(contract.id),
            "instalment_number": row.number,
            "instalments_total": row.instalments_total,
        },
    )
    event.id = uuid.uuid4()
    claimed = await db.execute(
        update(ContractInstalment)
        .where(ContractInstalment.id == row.id, ContractInstalment.commission_event_id.is_(None))
        .values(commission_event_id=event.id)
    )
    if claimed.rowcount != 1:
        return False
    db.add(event)
    row.commission_event_id = event.id
    await db.flush()
    return True


async def release_paid_instalments(db: AsyncSession, *, contract: Contract) -> int:
    """At activation, release every instalment already paid."""
    released = 0
    for row in await list_instalments(db, contract_id=contract.id):
        if row.status == "PAID" and row.commission_event_id is None and await release(db, contract=contract, row=row):
            released += 1
    return released


async def confirm_manually(
    db: AsyncSession, *, contract: Contract, number: int, actor_user_id: uuid.UUID
) -> ContractInstalment:
    """Admin confirmation of an instalment Stripe did not collect (e.g. bank
    transfer). Commits."""
    rows = await list_instalments(db, contract_id=contract.id)
    if not rows:
        raise InstalmentError("Questo contratto non ha ancora un piano di rate: nessun pagamento registrato.")
    row = next((r for r in rows if r.number == number), None)
    if row is None:
        raise InstalmentError("Rata inesistente.")
    if row.status == "PAID":
        raise InstalmentError("Questa rata risulta già pagata.")
    await record_payment(
        db, contract=contract, source=SOURCE_ADMIN, number=number, actor_user_id=actor_user_id
    )
    await db.commit()
    await db.refresh(row)
    return row


async def mark_commission_released(
    db: AsyncSession, *, contract_id: uuid.UUID, number: int, calculation_id: uuid.UUID | None, at: datetime
) -> None:
    row = (
        await db.execute(
            select(ContractInstalment).where(
                ContractInstalment.contract_id == contract_id, ContractInstalment.number == number
            )
        )
    ).scalar_one_or_none()
    if row is not None and row.commission_released_at is None:
        row.commission_released_at = at
        row.commission_calculation_id = calculation_id
        await db.commit()
