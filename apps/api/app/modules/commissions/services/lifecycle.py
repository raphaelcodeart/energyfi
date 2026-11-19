"""Commission lifecycle after calculation.

    PENDING --approve--> APPROVED --make payable--> PAYABLE --pay--> PAID
       \\______________________________________________/
                 contract cancelled -> CANCELLED (never paid)
    PAID  -- contract cancelled -> stays PAID, plus a negative REVERSAL row

Amounts are never modified and rows never deleted; only status changes, each
with an audit entry. Company shares (RETAINED) are never paid and are
CANCELLED on cancellation like the rest.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.foundation.db import utcnow
from app.modules.audit import service as audit_service
from app.modules.commissions.models import CommissionMovement, CommissionReversal

#: Target status -> allowed source statuses (legacy ACCRUED counts as PENDING).
TRANSITIONS: dict[str, tuple[str, ...]] = {
    "APPROVED": ("PENDING", "ACCRUED"),
    "PAYABLE": ("APPROVED",),
    "PAID": ("APPROVED", "PAYABLE"),
}
OPEN_STATUSES = ("PENDING", "ACCRUED", "APPROVED", "PAYABLE")

ACTION_LABELS = {"APPROVED": "approvata", "PAYABLE": "resa pagabile", "PAID": "pagata"}


class CommissionLifecycleError(Exception):
    pass


async def transition(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    movement_ids: list[uuid.UUID],
    to_status: str,
    actor_user_id: uuid.UUID,
    note: str | None = None,
) -> list[CommissionMovement]:
    """Move movements to `to_status`, all or nothing. Rows are locked FOR
    UPDATE so concurrent admins cannot pay the same row twice."""
    allowed = TRANSITIONS.get(to_status)
    if allowed is None:
        raise CommissionLifecycleError("Stato di destinazione non valido.")
    if not movement_ids:
        return []
    movements = list(
        (
            await db.execute(
                select(CommissionMovement)
                .where(CommissionMovement.id.in_(movement_ids), CommissionMovement.organization_id == organization_id)
                .with_for_update()
            )
        ).scalars()
    )
    if len(movements) != len(set(movement_ids)):
        raise CommissionLifecycleError("Uno o più movimenti non esistono.")
    for movement in movements:
        if movement.beneficiary_kind != "AGENT":
            raise CommissionLifecycleError("La quota dell'azienda non si approva né si paga.")
        if movement.status not in allowed:
            raise CommissionLifecycleError(
                f"Un movimento è {movement.status}: non può essere {ACTION_LABELS[to_status]}."
            )

    now = utcnow()
    for movement in movements:
        previous = movement.status
        movement.status = to_status
        if to_status == "APPROVED":
            movement.approved_at = now
            movement.approved_by_user_id = actor_user_id
        if to_status == "PAID":
            movement.paid_date = now.date()
            if movement.approved_at is None:
                movement.approved_at = now
                movement.approved_by_user_id = actor_user_id
        await audit_service.record(
            db, organization_id=organization_id, actor_user_id=actor_user_id,
            action=f"commission.movement_{to_status.lower()}", entity_type="commission_movement",
            entity_id=str(movement.id), previous_value={"status": previous},
            new_value={"status": to_status, "amount_cents": movement.amount_cents}, reason=note,
        )
    await db.commit()
    for movement in movements:
        await db.refresh(movement)
    return movements


async def reverse_contract(
    db: AsyncSession, *, organization_id: uuid.UUID, contract_id: uuid.UUID, actor_user_id: uuid.UUID | None,
    reason: str,
) -> dict:
    """Handle contract cancellation without deleting movements.

    * unpaid or company share -> CANCELLED;
    * paid -> stays PAID, and a negative REVERSAL row linked through
      `sn_payout_reversals` records the amount to recover.

    Idempotent: reversal keys derive from the original movement."""
    movements = list(
        (
            await db.execute(
                select(CommissionMovement)
                .where(
                    CommissionMovement.organization_id == organization_id,
                    CommissionMovement.contract_id == contract_id,
                    CommissionMovement.movement_type != "REVERSAL",
                )
                .with_for_update()
            )
        ).scalars()
    )
    reversed_ids = set(
        (
            await db.execute(
                select(CommissionReversal.original_movement_id).where(
                    CommissionReversal.original_movement_id.in_([m.id for m in movements])
                )
            )
        ).scalars()
    ) if movements else set()

    cancelled = 0
    clawbacks = 0
    for movement in movements:
        if movement.status in (*OPEN_STATUSES, "RETAINED"):
            previous = movement.status
            movement.status = "CANCELLED"
            cancelled += 1
            await audit_service.record(
                db, organization_id=organization_id, actor_user_id=actor_user_id,
                action="commission.movement_cancelled", entity_type="commission_movement",
                entity_id=str(movement.id), previous_value={"status": previous},
                new_value={"status": "CANCELLED"}, reason=reason,
            )
        elif movement.status == "PAID" and movement.id not in reversed_ids:
            reversal = CommissionMovement(
                organization_id=organization_id,
                beneficiary_kind=movement.beneficiary_kind,
                agent_id=movement.agent_id,
                contract_id=movement.contract_id,
                origin_event_id=movement.origin_event_id,
                calculation_id=movement.calculation_id,
                movement_type="REVERSAL",
                amount_cents=-movement.amount_cents,
                currency=movement.currency,
                status="PENDING",
                effective_date=utcnow().date(),
                rule_version_id=movement.rule_version_id,
                network_snapshot_id=movement.network_snapshot_id,
                idempotency_key=f"reversal:{movement.id}",
                split_plan_id=movement.split_plan_id,
                plan_version=movement.plan_version,
                rule_id=movement.rule_id,
                beneficiary_type=movement.beneficiary_type,
                network_level=movement.network_level,
                role_code_snapshot=movement.role_code_snapshot,
                calculation_type=movement.calculation_type,
                calculation_value=movement.calculation_value,
                reference_margin_cents=movement.reference_margin_cents,
                source_seller_agent_id=movement.source_seller_agent_id,
                product_id=movement.product_id,
                snapshot={"reverses": str(movement.id), "reason": reason},
            )
            db.add(reversal)
            await db.flush()
            db.add(CommissionReversal(
                organization_id=organization_id, original_movement_id=movement.id,
                new_movement_id=reversal.id, reason=reason, requested_by=actor_user_id,
            ))
            clawbacks += 1
            await audit_service.record(
                db, organization_id=organization_id, actor_user_id=actor_user_id,
                action="commission.movement_reversed", entity_type="commission_movement",
                entity_id=str(movement.id), new_value={"reversal_movement_id": str(reversal.id),
                                                       "amount_cents": reversal.amount_cents},
                reason=reason,
            )
    await db.commit()
    return {"cancelled": cancelled, "reversed": clawbacks}
