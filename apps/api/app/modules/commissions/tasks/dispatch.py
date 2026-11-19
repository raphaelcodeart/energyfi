import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.foundation.db import utcnow
from app.modules.audit import service as audit_service
from app.modules.commissions.services.run_calculation import run_calculation_for_contract
from app.modules.outbox import service as outbox_service
from app.modules.outbox.models import DomainOutbox

logger = logging.getLogger(__name__)

# Other outbox event types are marked processed as no-ops by this dispatcher.
COMMISSION_TRIGGER_EVENTS = {"ContractActivated", "ContractRenewed", "ContractInstalmentPaid", "ContractCancelled"}


async def _accrual_trigger(db: AsyncSession, contract_id: uuid.UUID) -> str:
    """Accrual trigger of the contract's frozen plan. Without a plan it
    defaults to PER_INSTALMENT, whose calculation then fails visibly."""
    from app.modules.commissions.models import SplitPlan
    from app.modules.contracts.models import Contract

    contract = await db.get(Contract, contract_id)
    plan = await db.get(SplitPlan, contract.split_plan_id) if contract and contract.split_plan_id else None
    return plan.accrual_trigger if plan is not None else "PER_INSTALMENT"


async def _dispatch_commission_event(db: AsyncSession, record: dict, contract_id: uuid.UUID) -> None:
    """Per-event handling:

    * ContractInstalmentPaid: PER_INSTALMENT pays that instalment's share;
      ON_ACTIVATION computes nothing but still marks the instalment released.
    * ContractActivated: ON_ACTIVATION pays everything. PER_INSTALMENT pays
      everything only if the contract has no instalments; otherwise each is
      paid on collection, and computing here would pay the first twice.
    * ContractRenewed: a full new calculation on the same frozen data.
    * ContractCancelled: cancels unpaid shares and reverses paid ones
      (lifecycle.reverse_contract).
    """
    from app.modules.contracts import instalments as instalments_service
    from app.modules.contracts.models import Contract, ContractStatusHistory

    event = record["event_type"]
    if event == "ContractCancelled":
        from sqlalchemy import select

        from app.modules.commissions.services import lifecycle

        actor = (
            await db.execute(
                select(ContractStatusHistory.actor_user_id)
                .where(ContractStatusHistory.contract_id == contract_id, ContractStatusHistory.to_status == "CANCELLED")
                .order_by(ContractStatusHistory.created_at.desc())
            )
        ).scalars().first()
        await lifecycle.reverse_contract(
            db, organization_id=record["organization_id"], contract_id=contract_id, actor_user_id=actor,
            reason="Contratto annullato",
        )
        return

    trigger = await _accrual_trigger(db, contract_id)
    if event == "ContractInstalmentPaid":
        number = int(record["payload"]["instalment_number"])
        contract = await db.get(Contract, contract_id)
        calculation = None
        if trigger == "PER_INSTALMENT" and contract is not None and contract.status != "CANCELLED":
            calculation = await run_calculation_for_contract(
                db,
                organization_id=record["organization_id"],
                contract_id=contract_id,
                trigger_event_id=record["id"],
                instalment_number=number,
                instalments_total=int(record["payload"]["instalments_total"]),
            )
        await instalments_service.mark_commission_released(
            db, contract_id=contract_id, number=number,
            calculation_id=calculation.id if calculation is not None else None, at=utcnow(),
        )
        return
    if (
        event == "ContractActivated"
        and trigger == "PER_INSTALMENT"
        and await instalments_service.list_instalments(db, contract_id=contract_id)
    ):
        return
    await run_calculation_for_contract(
        db,
        organization_id=record["organization_id"],
        contract_id=contract_id,
        trigger_event_id=record["id"],
    )


async def process_pending_outbox_events(db: AsyncSession, *, limit: int = 100) -> int:
    """Dispatch unprocessed outbox events. Runs as a Celery beat task and is
    also called by the seed script and tests. Safe to repeat or run
    concurrently thanks to the (contract, event) idempotency of calculations.

    Events are isolated: one failure is logged and audited but never blocks
    the rest of the batch. Event data is copied into plain values first,
    because a rollback expires every ORM object in the session and a later
    lazy reload would raise MissingGreenlet."""
    events = await outbox_service.fetch_unprocessed(db, limit=limit)
    event_records = [
        {"id": e.id, "organization_id": e.organization_id, "event_type": e.event_type, "payload": e.payload}
        for e in events
    ]

    processed = 0
    for record in event_records:
        if record["event_type"] in COMMISSION_TRIGGER_EVENTS:
            contract_id = uuid.UUID(record["payload"]["contract_id"])
            try:
                await _dispatch_commission_event(db, record, contract_id)
            except Exception:
                logger.exception(
                    "Commission calculation failed for contract %s (event %s, type %s)",
                    contract_id, record["id"], record["event_type"],
                )
                await db.rollback()
                await audit_service.record(
                    db, organization_id=record["organization_id"], actor_user_id=None,
                    action="commission.calculation_error", entity_type="contract", entity_id=str(contract_id),
                    new_value={"event_id": str(record["id"]), "event_type": record["event_type"]},
                    reason="Unhandled exception during commission calculation -- see worker logs",
                )
                await db.commit()
                # Left unprocessed so it is retried once the cause is fixed.
                continue
        # Re-fetch: the original object may have expired in a rollback.
        outbox_event = await db.get(DomainOutbox, record["id"])
        await outbox_service.mark_processed(db, outbox_event)
        processed += 1
    return processed
