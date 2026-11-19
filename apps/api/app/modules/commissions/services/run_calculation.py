"""Real commission calculation for a contract.

Reads only frozen data (sale.frozen_context), runs the engine and writes in
one transaction: the calculation, one step per rule and one movement per
non-zero share, company share included, so movements sum to the margin.

Idempotent twice over: (contract, event) is unique per calculation and every
movement has a deterministic unique key, so retries and concurrent workers
find the work already done.
"""

import hashlib
import json
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit import service as audit_service
from app.modules.catalog.models import ProductVersion
from app.modules.commissions.engine.allocate import allocate, euro
from app.modules.commissions.engine.types import AGENT, Allocation, EngineError
from app.modules.commissions.models import (
    CommissionCalculation,
    CommissionCalculationStep,
    CommissionMovement,
)
from app.modules.commissions.services import sale as sale_service
from app.modules.contracts.models import Contract
from app.modules.network.models import AgentProfile
from app.modules.notifications import service as notifications_service

#: Engine label stored in `rule_version_id`; plan and version have own columns.
RULE_VERSION = "split-plan-v1"

MOVEMENT_TYPE_BY_BENEFICIARY = {
    "SELLER": "DIRECT",
    "UPLINE_LEVEL": "INDIRECT",
    "ROLE_IN_UPLINE": "INDIRECT",
    "INFLUENCER": "INDIRECT",
    "PROMOTER": "PROMOTER_FEE",
    "COMPANY": "COMPANY_SHARE",
}


def movement_type_for(allocation: Allocation) -> str:
    if allocation.beneficiary_kind != AGENT:
        return "COMPANY_SHARE"
    return MOVEMENT_TYPE_BY_BENEFICIARY.get(allocation.beneficiary_type, "INDIRECT")


def instalment_share(total_cents: int, *, number: int, instalments: int) -> int:
    """Equal split per instalment; the division remainder goes on the last
    one so shares sum exactly to the total."""
    if instalments <= 1:
        return total_cents
    base = total_cents // instalments
    if number == instalments:
        return total_cents - base * (instalments - 1)
    return base


def _idempotency_key(contract_id: uuid.UUID, trigger_event_id: uuid.UUID, allocation: Allocation) -> str:
    beneficiary = allocation.agent_id or "company"
    rule = allocation.rule_id or "residual"
    raw = f"{contract_id}:{trigger_event_id}:{rule}:{beneficiary}"
    return hashlib.sha256(raw.encode()).hexdigest()


async def _get_existing(
    db: AsyncSession, *, contract_id: uuid.UUID, trigger_event_id: uuid.UUID
) -> CommissionCalculation | None:
    return (
        await db.execute(
            select(CommissionCalculation).where(
                CommissionCalculation.contract_id == contract_id,
                CommissionCalculation.trigger_event_id == trigger_event_id,
            )
        )
    ).scalar_one_or_none()


async def _record_failure(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    contract: Contract,
    trigger_event_id: uuid.UUID,
    code: str,
    message: str,
) -> CommissionCalculation:
    """Persist an impossible calculation as FAILED with its reason and an
    audit entry, so a contract never silently pays nobody."""
    calculation = CommissionCalculation(
        organization_id=organization_id,
        contract_id=contract.id,
        network_snapshot_id=contract.network_snapshot_id,
        trigger_event_id=trigger_event_id,
        commission_plan_version_id=contract.split_plan_id,
        reference_margin_cents=contract.reference_margin_cents,
        input_snapshot={"contract_id": str(contract.id)},
        output_snapshot={"steps": [], "error": code, "message": message},
        checksum=hashlib.sha256(f"{code}:{contract.id}".encode()).hexdigest(),
        status="FAILED",
    )
    db.add(calculation)
    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=None,
        action="commission.calculation_failed", entity_type="contract", entity_id=str(contract.id),
        new_value={"reason": code, "message": message}, reason=message,
    )
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        existing = await _get_existing(db, contract_id=contract.id, trigger_event_id=trigger_event_id)
        if existing is not None:
            return existing
        raise
    await db.refresh(calculation)
    return calculation


async def run_calculation_for_contract(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    contract_id: uuid.UUID,
    trigger_event_id: uuid.UUID,
    instalment_number: int = 1,
    instalments_total: int = 1,
) -> CommissionCalculation | None:
    """Idempotent on (contract, event). With N instalments, each collected
    instalment distributes 1/N of every share from the same frozen context."""
    existing = await _get_existing(db, contract_id=contract_id, trigger_event_id=trigger_event_id)
    if existing is not None:
        return existing

    contract = await db.get(Contract, contract_id)
    if contract is None:
        raise ValueError("Contratto non trovato")
    if contract.network_snapshot_id is None:
        raise ValueError("Contract has no network snapshot; cannot calculate commissions")

    try:
        spec, ctx, plan = await sale_service.frozen_context(db, contract=contract)
        result = allocate(spec, ctx)
    except ValueError as exc:
        return await _record_failure(
            db, organization_id=organization_id, contract=contract, trigger_event_id=trigger_event_id,
            code="missing_context", message=str(exc),
        )
    except EngineError as exc:
        return await _record_failure(
            db, organization_id=organization_id, contract=contract, trigger_event_id=trigger_event_id,
            code=exc.code, message=exc.message,
        )

    split = instalments_total > 1

    def _amount(a: Allocation) -> int:
        return instalment_share(a.amount_cents, number=instalment_number, instalments=instalments_total)

    def _explanation(a: Allocation) -> str:
        if not split:
            return a.explanation
        return f"{a.explanation} — quota rata {instalment_number} di {instalments_total} (totale {euro(a.amount_cents)})"

    version = await db.get(ProductVersion, contract.product_version_id) if contract.product_version_id else None
    input_snapshot = {
        "contract_id": str(contract.id),
        "sold_at": contract.sold_at.isoformat() if contract.sold_at else None,
        "product_id": str(version.product_id) if version else None,
        "product_version_id": str(contract.product_version_id) if contract.product_version_id else None,
        "sale_amount_cents": contract.sale_amount_cents,
        "reference_margin_cents": contract.reference_margin_cents,
        "seller_role_code": contract.seller_role_code,
        "plan": {"id": spec.id, "version": spec.version, "name": spec.name,
                 "fallback_strategy": spec.fallback_strategy, "distribution_mode": spec.distribution_mode},
        "rules": [
            {"id": r.id, "sequence": r.sequence, "beneficiary_type": r.beneficiary_type,
             "calculation_type": r.calculation_type, "network_level": r.network_level,
             "required_role_code": r.required_role_code,
             "percentage": str(r.percentage) if r.percentage is not None else None,
             "amount_cents": r.amount_cents, "min_amount_cents": r.min_amount_cents,
             "max_amount_cents": r.max_amount_cents, "fallback_strategy": r.fallback_strategy}
            for r in spec.rules
        ],
        "chain": [
            {"agent_id": n.agent_id, "name": n.name, "depth": n.depth, "role_code": n.role_code, "eligible": n.eligible}
            for n in ctx.chain
        ],
        "promoter": ctx.promoter.agent_id if ctx.promoter else None,
        "delegation_influencer": ctx.delegation_influencer.agent_id if ctx.delegation_influencer else None,
        "instalment_number": instalment_number,
        "instalments_total": instalments_total,
    }
    output_snapshot = {
        "steps": [
            {"rule_id": a.rule_id, "beneficiary_kind": a.beneficiary_kind, "agent_id": a.agent_id,
             "beneficiary_type": a.beneficiary_type, "total_cents": a.amount_cents,
             "amount_cents": _amount(a), "fallback_applied": a.fallback_applied, "explanation": _explanation(a)}
            for a in result.allocations
        ],
        "warnings": list(result.warnings),
    }
    checksum = hashlib.sha256(
        json.dumps({"input": input_snapshot, "output": output_snapshot}, sort_keys=True).encode()
    ).hexdigest()

    calculation = CommissionCalculation(
        organization_id=organization_id,
        contract_id=contract.id,
        network_snapshot_id=contract.network_snapshot_id,
        trigger_event_id=trigger_event_id,
        commission_plan_version_id=plan.id,
        reference_margin_cents=contract.reference_margin_cents,
        input_snapshot=input_snapshot,
        output_snapshot=output_snapshot,
        checksum=checksum,
        status="COMPLETED",
    )
    db.add(calculation)
    try:
        # The unique (contract, event) constraint stops a concurrent duplicate here.
        await db.flush()
    except IntegrityError:
        await db.rollback()
        existing = await _get_existing(db, contract_id=contract_id, trigger_event_id=trigger_event_id)
        if existing is not None:
            return existing
        raise

    today = datetime.now(UTC).date()
    agent_ids = {uuid.UUID(a.agent_id) for a in result.allocations if a.agent_id}
    user_by_agent = dict(
        (await db.execute(select(AgentProfile.id, AgentProfile.user_id).where(AgentProfile.id.in_(agent_ids)))).all()
    ) if agent_ids else {}
    seller_id = uuid.UUID(ctx.chain[0].agent_id) if ctx.chain else None

    for order, allocation in enumerate(result.allocations):
        amount = _amount(allocation)
        agent_uuid = uuid.UUID(allocation.agent_id) if allocation.agent_id else None
        rule_uuid = uuid.UUID(allocation.rule_id) if allocation.rule_id else None
        db.add(
            CommissionCalculationStep(
                calculation_id=calculation.id,
                step_order=order,
                beneficiary_agent_id=agent_uuid,
                rule_id=rule_uuid,
                rank_at_calculation=allocation.role_code,
                base_amount_cents=contract.reference_margin_cents or 0,
                already_distributed_cents=0,
                entrepreneurial_difference_cents=0,
                personal_bonus_cents=0,
                gross_amount_cents=amount,
                movement_type=movement_type_for(allocation),
                explanation=_explanation(allocation)[:1000],
            )
        )
        if amount <= 0:
            continue
        is_agent = allocation.beneficiary_kind == AGENT
        db.add(
            CommissionMovement(
                organization_id=organization_id,
                beneficiary_kind=allocation.beneficiary_kind,
                agent_id=agent_uuid,
                contract_id=contract.id,
                origin_event_id=trigger_event_id,
                calculation_id=calculation.id,
                movement_type=movement_type_for(allocation),
                amount_cents=amount,
                currency="EUR",
                status="PENDING" if is_agent else "RETAINED",
                effective_date=today,
                rule_version_id=RULE_VERSION,
                network_snapshot_id=contract.network_snapshot_id,
                idempotency_key=_idempotency_key(contract.id, trigger_event_id, allocation),
                split_plan_id=plan.id,
                plan_version=plan.version,
                rule_id=rule_uuid,
                beneficiary_type=allocation.beneficiary_type,
                network_level=allocation.network_level,
                role_code_snapshot=allocation.role_code,
                calculation_type=allocation.calculation_type,
                calculation_value=allocation.calculation_value,
                reference_margin_cents=contract.reference_margin_cents,
                source_seller_agent_id=seller_id,
                product_id=version.product_id if version else None,
                fallback_applied=allocation.fallback_applied,
                snapshot={
                    "plan": input_snapshot["plan"],
                    "rule_id": allocation.rule_id,
                    "label": allocation.label,
                    "total_cents": allocation.amount_cents,
                    "instalment": [instalment_number, instalments_total],
                    "sold_at": input_snapshot["sold_at"],
                    "sale_amount_cents": contract.sale_amount_cents,
                    "chain": input_snapshot["chain"],
                    "explanation": _explanation(allocation),
                },
            )
        )
        user_id = user_by_agent.get(agent_uuid) if agent_uuid else None
        if is_agent and user_id is not None:
            await notifications_service.notify_user(
                db, organization_id=organization_id, user_id=user_id,
                type_="COMMISSION_EARNED", entity_type="contract", entity_id=contract.id,
                title=f"Nuova provvigione: {euro(amount)}",
                body=_explanation(allocation)[:500],
            )

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        existing = await _get_existing(db, contract_id=contract_id, trigger_event_id=trigger_event_id)
        if existing is not None:
            return existing
        raise
    await db.refresh(calculation)
    return calculation
