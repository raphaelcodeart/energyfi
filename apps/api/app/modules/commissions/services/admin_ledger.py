"""Organization-wide commission traceability and payment tracking for staff:
why an agent earned a commission (contract, network level, calculation step)
and whether it has been paid (see docs/business-rules.md)."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.catalog.models import ProductVersion
from app.modules.commercial.models import CommercialRole
from app.modules.commissions.models import CommissionMovement, SplitPlan
from app.modules.commissions.services import lifecycle
from app.modules.contracts.models import Contract, ContractAttribution
from app.modules.customers.models import Company, Customer, CustomerProfile
from app.modules.customers.service import display_name_for
from app.modules.network.models import AgentProfile

PAYABLE_STATUSES = {"APPROVED", "PAYABLE"}


class CommissionPaymentError(Exception):
    pass


async def get_commission_movements(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    agent_id: uuid.UUID | None = None,
    status: str | None = None,
    contract_id: uuid.UUID | None = None,
    include_company: bool = False,
) -> list[dict]:
    stmt = (
        select(CommissionMovement, Contract.customer_id, ContractAttribution.producer_agent_id,
               ProductVersion.name, Contract.sale_amount_cents, ProductVersion.base_price_cents)
        .select_from(CommissionMovement)
        .join(Contract, Contract.id == CommissionMovement.contract_id)
        .join(ContractAttribution, ContractAttribution.id == Contract.contract_attribution_id)
        .join(ProductVersion, ProductVersion.id == Contract.product_version_id)
        .where(CommissionMovement.organization_id == organization_id)
        .order_by(CommissionMovement.created_at.desc())
    )
    if not include_company:
        stmt = stmt.where(CommissionMovement.beneficiary_kind == "AGENT")
    if agent_id is not None:
        stmt = stmt.where(CommissionMovement.agent_id == agent_id)
    if status is not None:
        stmt = stmt.where(CommissionMovement.status == status)
    if contract_id is not None:
        stmt = stmt.where(CommissionMovement.contract_id == contract_id)

    rows = (await db.execute(stmt)).all()
    if not rows:
        return []

    agent_ids = {r[0].agent_id for r in rows if r[0].agent_id} | {r[2] for r in rows}
    customer_ids = {r[1] for r in rows}
    agents = {
        a.id: a for a in (await db.execute(select(AgentProfile).where(AgentProfile.id.in_(agent_ids)))).scalars()
    }
    customers = {c.id: c for c in (await db.execute(select(Customer).where(Customer.id.in_(customer_ids)))).scalars()}
    profiles = {
        p.customer_id: p
        for p in (await db.execute(select(CustomerProfile).where(CustomerProfile.customer_id.in_(customer_ids)))).scalars()
    }
    companies = {
        c.customer_id: c
        for c in (await db.execute(select(Company).where(Company.customer_id.in_(customer_ids)))).scalars()
    }
    role_codes = dict(
        (await db.execute(
            select(CommercialRole.id, CommercialRole.code).where(CommercialRole.organization_id == organization_id)
        )).all()
    )
    plan_names = dict(
        (await db.execute(select(SplitPlan.id, SplitPlan.name).where(SplitPlan.organization_id == organization_id))).all()
    )

    result = []
    for movement, customer_id, producer_agent_id, product_name, sale_amount, base_price in rows:
        agent = agents.get(movement.agent_id) if movement.agent_id else None
        producer = agents.get(producer_agent_id)
        customer = customers.get(customer_id)
        snapshot = movement.snapshot or {}
        result.append({
            "id": movement.id,
            "contract_id": movement.contract_id,
            "customer_id": customer_id,
            "customer_name": display_name_for(customer.kind, profiles.get(customer_id), companies.get(customer_id)) if customer else "—",
            "product_name": product_name,
            "value_cents": int(sale_amount if sale_amount is not None else base_price or 0),
            "beneficiary_kind": movement.beneficiary_kind,
            "agent_id": movement.agent_id,
            "agent_name": agent.display_name if agent else "Azienda",
            "agent_promoter_code": agent.promoter_code if agent else "—",
            "agent_current_role_code": role_codes.get(agent.current_commercial_role_id) if agent else None,
            "producer_agent_id": producer_agent_id,
            "producer_name": producer.display_name if producer else "—",
            "depth_from_producer": movement.network_level,
            "movement_type": movement.movement_type,
            "beneficiary_type": movement.beneficiary_type,
            "role_at_calculation": movement.role_code_snapshot,
            "plan_id": movement.split_plan_id,
            "plan_name": plan_names.get(movement.split_plan_id) if movement.split_plan_id else None,
            "plan_version": movement.plan_version,
            "rule_label": snapshot.get("label"),
            "calculation_type": movement.calculation_type,
            "calculation_value": float(movement.calculation_value) if movement.calculation_value is not None else None,
            "reference_margin_cents": movement.reference_margin_cents,
            "fallback_applied": movement.fallback_applied,
            "amount_cents": movement.amount_cents,
            "explanation": snapshot.get("explanation"),
            "status": movement.status,
            "effective_date": movement.effective_date,
            "approved_at": movement.approved_at,
            "paid_date": movement.paid_date,
        })
    return result


async def get_commission_totals_by_level(db: AsyncSession, *, organization_id: uuid.UUID) -> list[dict]:
    """Per network level relative to the seller (0 = seller): sale count,
    sale value and amount paid at that level. Company shares have no level."""
    stmt = (
        select(
            CommissionMovement.network_level,
            func.count(func.distinct(CommissionMovement.contract_id)),
            func.coalesce(func.sum(CommissionMovement.amount_cents), 0),
        )
        .where(
            CommissionMovement.organization_id == organization_id,
            CommissionMovement.beneficiary_kind == "AGENT",
            CommissionMovement.network_level.is_not(None),
            CommissionMovement.status.notin_(["CANCELLED"]),
        )
        .group_by(CommissionMovement.network_level)
        .order_by(CommissionMovement.network_level.asc())
    )
    rows = (await db.execute(stmt)).all()
    value_by_level = {}
    for level, *_ in rows:
        contract_ids = select(CommissionMovement.contract_id).where(
            CommissionMovement.organization_id == organization_id, CommissionMovement.network_level == level
        ).distinct()
        value_by_level[level] = int(
            (await db.execute(
                select(func.coalesce(func.sum(Contract.sale_amount_cents), 0)).where(Contract.id.in_(contract_ids))
            )).scalar_one()
        )
    return [
        {"depth": level, "contracts": contracts, "value_cents": value_by_level.get(level, 0),
         "commission_cents": int(commission_cents)}
        for level, contracts, commission_cents in rows
    ]


async def pay_all_for_contract(
    db: AsyncSession, *, organization_id: uuid.UUID, contract_id: uuid.UUID, actor_user_id: uuid.UUID, note: str | None = None
) -> list[CommissionMovement]:
    """Pay all APPROVED or PAYABLE shares of a contract. Unapproved shares are
    left alone so payment never bypasses approval."""
    ids = list(
        (
            await db.execute(
                select(CommissionMovement.id).where(
                    CommissionMovement.organization_id == organization_id,
                    CommissionMovement.contract_id == contract_id,
                    CommissionMovement.beneficiary_kind == "AGENT",
                    CommissionMovement.status.in_(PAYABLE_STATUSES),
                )
            )
        ).scalars()
    )
    return await lifecycle.transition(
        db, organization_id=organization_id, movement_ids=ids, to_status="PAID", actor_user_id=actor_user_id, note=note
    )


async def mark_movement_paid(
    db: AsyncSession, *, organization_id: uuid.UUID, movement_id: uuid.UUID, actor_user_id: uuid.UUID, note: str | None = None
) -> CommissionMovement | None:
    movement = await db.get(CommissionMovement, movement_id)
    if movement is None or movement.organization_id != organization_id:
        return None
    try:
        (paid,) = await lifecycle.transition(
            db, organization_id=organization_id, movement_ids=[movement_id], to_status="PAID",
            actor_user_id=actor_user_id, note=note,
        )
    except lifecycle.CommissionLifecycleError as exc:
        raise CommissionPaymentError(str(exc)) from exc
    return paid
