import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.foundation.db import get_db, utcnow
from app.foundation.deps import CurrentUser, get_current_user, require_permission
from app.modules.rbac.service import get_permission_codes_for_user
from app.modules.catalog.models import Product, ProductCategory
from app.modules.commercial.models import CommercialRole
from app.modules.commissions.models import CommissionMovement, Rank, SplitPlan, SplitRule
from app.modules.commissions.schemas import (
    CommissionLevelTotalsRead,
    CommissionMovementDetailRead,
    CommissionMovementRead,
    CommissionPaymentRequest,
    MovementTransitionRequest,
    NewVersionRequest,
    PlanValidationRead,
    RankRead,
    RetirePlanRequest,
    SellerSummaryRead,
    SimulateSaleRequest,
    SplitPlanIn,
    SplitPlanRead,
    SplitPlanUpdate,
    SplitRuleRead,
)
from app.modules.commissions.services import admin_ledger, lifecycle, reports
from app.modules.commissions.services import plans as plans_service
from app.modules.commissions.simulations.simulate import SimulationError, simulate_sale
from app.modules.network.models import AgentProfile

router = APIRouter(prefix="/commissions", tags=["commissions"])


async def _has(db: AsyncSession, current_user: CurrentUser, code: str) -> bool:
    granted = await get_permission_codes_for_user(
        db, user_id=current_user.user_id, organization_id=current_user.organization_id
    )
    return code in granted


async def _own_agent_id(db: AsyncSession, current_user: CurrentUser) -> uuid.UUID | None:
    return (
        await db.execute(
            select(AgentProfile.id).where(
                AgentProfile.organization_id == current_user.organization_id,
                AgentProfile.user_id == current_user.user_id,
            )
        )
    ).scalar_one_or_none()


# --- Seller -------------------------------------------------------------------------


@router.get("/mine", response_model=list[CommissionMovementRead])
async def get_my_commissions(
    current_user: CurrentUser = Depends(require_permission("commissions.read_own")),
    db: AsyncSession = Depends(get_db),
) -> list[CommissionMovementRead]:
    agent_id = await _own_agent_id(db, current_user)
    if agent_id is None:
        return []
    stmt = select(CommissionMovement).where(
        CommissionMovement.organization_id == current_user.organization_id,
        CommissionMovement.agent_id == agent_id,
    )
    return [CommissionMovementRead.model_validate(m) for m in (await db.execute(stmt)).scalars().all()]


@router.get("/mine/detailed", response_model=list[CommissionMovementDetailRead])
async def get_my_commissions_detailed(
    current_user: CurrentUser = Depends(require_permission("commissions.read_own")),
    db: AsyncSession = Depends(get_db),
) -> list[CommissionMovementDetailRead]:
    """Admin ledger detail, restricted to the caller's own rows."""
    agent_id = await _own_agent_id(db, current_user)
    if agent_id is None:
        return []
    rows = await admin_ledger.get_commission_movements(db, organization_id=current_user.organization_id, agent_id=agent_id)
    return [CommissionMovementDetailRead(**row) for row in rows]


@router.get("/mine/summary", response_model=SellerSummaryRead | None)
async def get_my_summary(
    current_user: CurrentUser = Depends(require_permission("commissions.read_own")),
    db: AsyncSession = Depends(get_db),
) -> SellerSummaryRead | None:
    agent_id = await _own_agent_id(db, current_user)
    if agent_id is None:
        return None
    return SellerSummaryRead(
        **await reports.seller_summary(db, organization_id=current_user.organization_id, agent_id=agent_id)
    )


@router.get("/ranks", response_model=list[RankRead])
async def list_ranks(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[RankRead]:
    """Legacy career levels, read-only. The engine uses commercial roles."""
    stmt = select(Rank).where(Rank.organization_id == current_user.organization_id).order_by(Rank.level.asc())
    return [RankRead.model_validate(r) for r in (await db.execute(stmt)).scalars().all()]


# --- Simulator ------------------------------------------------------------------------


@router.post("/simulate")
async def simulate(
    payload: SimulateSaleRequest,
    current_user: CurrentUser = Depends(require_permission("commissions.simulate")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Simulate a sale with the real engine, writing nothing. Agents simulate
    only their own sales; staff can simulate anyone's, including against a
    draft plan (`plan_id`)."""
    is_staff = await _has(db, current_user, "commissions.approve")
    if not is_staff:
        own = await _own_agent_id(db, current_user)
        if own != payload.seller_agent_id or payload.plan_id is not None:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Puoi simulare solo le tue vendite, con i piani attivi.")
    seller = await db.get(AgentProfile, payload.seller_agent_id)
    if seller is None or seller.organization_id != current_user.organization_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Collaboratore non trovato.")
    try:
        return await simulate_sale(
            db, organization_id=current_user.organization_id, seller_agent_id=payload.seller_agent_id,
            product_id=payload.product_id, sold_at=payload.sold_at or utcnow(),
            sale_amount_cents=payload.sale_amount_cents, promoter_agent_id=payload.promoter_agent_id,
            plan_id=payload.plan_id,
        )
    except SimulationError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc


# --- Ledger and lifecycle -----------------------------------------------------------------


@router.get("/movements", response_model=list[CommissionMovementDetailRead])
async def list_commission_movements(
    agent_id: uuid.UUID | None = None,
    status_filter: str | None = None,
    contract_id: uuid.UUID | None = None,
    include_company: bool = False,
    current_user: CurrentUser = Depends(require_permission("commissions.approve")),
    db: AsyncSession = Depends(get_db),
) -> list[CommissionMovementDetailRead]:
    """Organization-wide ledger for staff, not limited to a branch."""
    rows = await admin_ledger.get_commission_movements(
        db, organization_id=current_user.organization_id, agent_id=agent_id, status=status_filter,
        contract_id=contract_id, include_company=include_company,
    )
    return [CommissionMovementDetailRead(**row) for row in rows]


@router.get("/movements/by-level", response_model=list[CommissionLevelTotalsRead])
async def get_commission_totals_by_level(
    current_user: CurrentUser = Depends(require_permission("commissions.approve")),
    db: AsyncSession = Depends(get_db),
) -> list[CommissionLevelTotalsRead]:
    rows = await admin_ledger.get_commission_totals_by_level(db, organization_id=current_user.organization_id)
    return [CommissionLevelTotalsRead(**row) for row in rows]


@router.post("/movements/transition", response_model=list[CommissionMovementRead])
async def transition_movements(
    payload: MovementTransitionRequest,
    current_user: CurrentUser = Depends(require_permission("commissions.approve")),
    db: AsyncSession = Depends(get_db),
) -> list[CommissionMovementRead]:
    """Approve, make payable or pay movements in bulk. PAYABLE/PAID also
    require commissions.pay, so approval and payment can be separate duties."""
    if payload.to_status in ("PAYABLE", "PAID") and not await _has(db, current_user, "commissions.pay"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Non hai il permesso di pagare le provvigioni.")
    try:
        movements = await lifecycle.transition(
            db, organization_id=current_user.organization_id, movement_ids=payload.movement_ids,
            to_status=payload.to_status, actor_user_id=current_user.user_id, note=payload.note,
        )
    except lifecycle.CommissionLifecycleError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return [CommissionMovementRead.model_validate(m) for m in movements]


@router.patch("/movements/{movement_id}/pay", response_model=CommissionMovementRead)
async def pay_commission_movement(
    movement_id: uuid.UUID,
    payload: CommissionPaymentRequest,
    current_user: CurrentUser = Depends(require_permission("commissions.pay")),
    db: AsyncSession = Depends(get_db),
) -> CommissionMovementRead:
    try:
        movement = await admin_ledger.mark_movement_paid(
            db, organization_id=current_user.organization_id, movement_id=movement_id,
            actor_user_id=current_user.user_id, note=payload.note,
        )
    except admin_ledger.CommissionPaymentError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    if movement is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Movimento non trovato.")
    return CommissionMovementRead.model_validate(movement)


@router.patch("/contracts/{contract_id}/pay-all", response_model=list[CommissionMovementRead])
async def pay_all_commission_movements_for_contract(
    contract_id: uuid.UUID,
    payload: CommissionPaymentRequest,
    current_user: CurrentUser = Depends(require_permission("commissions.pay")),
    db: AsyncSession = Depends(get_db),
) -> list[CommissionMovementRead]:
    try:
        movements = await admin_ledger.pay_all_for_contract(
            db, organization_id=current_user.organization_id, contract_id=contract_id,
            actor_user_id=current_user.user_id, note=payload.note,
        )
    except lifecycle.CommissionLifecycleError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return [CommissionMovementRead.model_validate(m) for m in movements]


# --- Report ---------------------------------------------------------------------------------


@router.get("/reports")
async def commission_report(
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    product_id: uuid.UUID | None = None,
    category_id: uuid.UUID | None = None,
    agent_id: uuid.UUID | None = None,
    role_code: str | None = None,
    plan_id: uuid.UUID | None = None,
    level: int | None = None,
    status_filter: str | None = None,
    current_user: CurrentUser = Depends(require_permission("reports.read")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await reports.commission_report(
        db, organization_id=current_user.organization_id, date_from=date_from, date_to=date_to,
        product_id=product_id, category_id=category_id, agent_id=agent_id, role_code=role_code,
        plan_id=plan_id, level=level, status=status_filter,
    )


# --- Split Plan ------------------------------------------------------------------------------


async def _plan_read(db: AsyncSession, plan: SplitPlan, *, with_validation: bool = True) -> SplitPlanRead:
    roles = {
        r.id: r for r in (
            await db.execute(select(CommercialRole).where(CommercialRole.organization_id == plan.organization_id))
        ).scalars()
    }
    product = await db.get(Product, plan.product_id) if plan.product_id else None
    category = await db.get(ProductCategory, plan.category_id) if plan.category_id else None
    rules = await plans_service.plan_rules(db, plan_id=plan.id)
    seller_role = roles.get(plan.seller_role_id) if plan.seller_role_id else None
    validation = None
    if with_validation:
        v = await plans_service.validate(db, plan=plan)
        validation = PlanValidationRead(
            ok=v.ok, errors=v.errors, warnings=v.warnings, percentage_total=v.percentage_total,
            fixed_total_cents=v.fixed_total_cents, has_remainder=v.has_remainder,
            reference_margin_cents=v.reference_margin_cents, distributed_cents=v.distributed_cents,
            residual_cents=v.residual_cents,
        )
    return SplitPlanRead(
        id=plan.id, plan_key=plan.plan_key, name=plan.name, version=plan.version, status=plan.status,
        product_id=plan.product_id, product_code=product.code if product else None,
        category_id=plan.category_id, category_name=category.name if category else None,
        seller_role_id=plan.seller_role_id,
        seller_role_code=seller_role.code if seller_role else None,
        seller_role_name=seller_role.name if seller_role else None,
        valid_from=plan.valid_from, valid_to=plan.valid_to, fallback_strategy=plan.fallback_strategy,
        distribution_mode=plan.distribution_mode, accrual_trigger=plan.accrual_trigger, notes=plan.notes or "",
        activated_at=plan.activated_at, retired_at=plan.retired_at, created_at=plan.created_at,
        rules=[
            SplitRuleRead(
                id=r.id, sequence=r.sequence, label=r.label, beneficiary_type=r.beneficiary_type or "",
                network_level=r.network_level, required_role_id=r.required_role_id,
                required_role_code=roles[r.required_role_id].code if r.required_role_id in roles else None,
                calculation_type=r.calculation_type or "", percentage=r.percentage, amount_cents=r.amount_cents,
                min_amount_cents=r.min_amount_cents, max_amount_cents=r.max_amount_cents,
                fallback_strategy=r.fallback_strategy,
            )
            for r in rules
        ],
        validation=validation,
    )


def _plan_error(exc: plans_service.SplitPlanError) -> HTTPException:
    if exc.errors:
        return HTTPException(status.HTTP_400_BAD_REQUEST, {"message": exc.message, "errors": exc.errors})
    return HTTPException(status.HTTP_400_BAD_REQUEST, exc.message)


@router.get("/plans", response_model=list[SplitPlanRead])
async def list_split_plans(
    status_filter: str | None = None,
    product_id: uuid.UUID | None = None,
    seller_role_id: uuid.UUID | None = None,
    current_user: CurrentUser = Depends(require_permission("split_plans.manage")),
    db: AsyncSession = Depends(get_db),
) -> list[SplitPlanRead]:
    plans = await plans_service.list_plans(
        db, organization_id=current_user.organization_id, status=status_filter, product_id=product_id,
        seller_role_id=seller_role_id,
    )
    return [await _plan_read(db, p, with_validation=p.status == "DRAFT") for p in plans]


@router.post("/plans/validate", response_model=PlanValidationRead)
async def validate_split_plan_draft(
    payload: SplitPlanIn,
    current_user: CurrentUser = Depends(require_permission("split_plans.manage")),
    db: AsyncSession = Depends(get_db),
) -> PlanValidationRead:
    """Validate an unsaved plan; totals are computed server-side."""
    from app.modules.commissions.engine.validation import validate_plan

    codes = await plans_service.role_codes(db, organization_id=current_user.organization_id)
    rules = [
        plans_service.to_rule_spec(
            SplitRule(id=uuid.uuid4(), **{**r.model_dump(), "sequence": r.sequence if r.sequence is not None else (i + 1) * 10}),
            codes,
        )
        for i, r in enumerate(payload.rules)
    ]
    role = await db.get(CommercialRole, payload.seller_role_id)
    probe = SplitPlan(product_id=payload.product_id, category_id=payload.category_id)
    v = validate_plan(
        rules, distribution_mode=payload.distribution_mode, fallback_strategy=payload.fallback_strategy,
        reference_margin_cents=await plans_service.reference_margin(db, probe),
        seller_role_can_close_sales=role.can_close_sales if role is not None else None,
    )
    if (payload.product_id is None) == (payload.category_id is None):
        v.errors.append("Scegli un prodotto oppure una categoria.")
    return PlanValidationRead(
        ok=v.ok, errors=v.errors, warnings=v.warnings, percentage_total=v.percentage_total,
        fixed_total_cents=v.fixed_total_cents, has_remainder=v.has_remainder,
        reference_margin_cents=v.reference_margin_cents, distributed_cents=v.distributed_cents,
        residual_cents=v.residual_cents,
    )


@router.get("/plans/{plan_id}", response_model=SplitPlanRead)
async def get_split_plan(
    plan_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("split_plans.manage")),
    db: AsyncSession = Depends(get_db),
) -> SplitPlanRead:
    plan = await plans_service.get_plan(db, organization_id=current_user.organization_id, plan_id=plan_id)
    if plan is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Piano non trovato.")
    return await _plan_read(db, plan)


@router.post("/plans", response_model=SplitPlanRead, status_code=status.HTTP_201_CREATED)
async def create_split_plan(
    payload: SplitPlanIn,
    current_user: CurrentUser = Depends(require_permission("split_plans.manage")),
    db: AsyncSession = Depends(get_db),
) -> SplitPlanRead:
    try:
        plan = await plans_service.create_plan(
            db, organization_id=current_user.organization_id, actor_user_id=current_user.user_id,
            values=payload.model_dump(exclude={"rules"}), rules=[r.model_dump() for r in payload.rules],
        )
    except plans_service.SplitPlanError as exc:
        raise _plan_error(exc) from exc
    return await _plan_read(db, plan)


@router.patch("/plans/{plan_id}", response_model=SplitPlanRead)
async def update_split_plan(
    plan_id: uuid.UUID,
    payload: SplitPlanUpdate,
    current_user: CurrentUser = Depends(require_permission("split_plans.manage")),
    db: AsyncSession = Depends(get_db),
) -> SplitPlanRead:
    values = payload.model_dump(exclude={"rules"}, exclude_unset=True)
    rules = [r.model_dump() for r in payload.rules] if payload.rules is not None else None
    try:
        plan = await plans_service.update_draft(
            db, organization_id=current_user.organization_id, plan_id=plan_id,
            actor_user_id=current_user.user_id, values=values, rules=rules,
        )
    except plans_service.SplitPlanError as exc:
        raise _plan_error(exc) from exc
    return await _plan_read(db, plan)


@router.delete("/plans/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_split_plan_draft(
    plan_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("split_plans.manage")),
    db: AsyncSession = Depends(get_db),
) -> None:
    try:
        await plans_service.delete_draft(
            db, organization_id=current_user.organization_id, plan_id=plan_id, actor_user_id=current_user.user_id
        )
    except plans_service.SplitPlanError as exc:
        raise _plan_error(exc) from exc


@router.post("/plans/{plan_id}/activate", response_model=SplitPlanRead)
async def activate_split_plan(
    plan_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("split_plans.activate")),
    db: AsyncSession = Depends(get_db),
) -> SplitPlanRead:
    try:
        plan = await plans_service.activate(
            db, organization_id=current_user.organization_id, plan_id=plan_id, actor_user_id=current_user.user_id
        )
    except plans_service.SplitPlanError as exc:
        raise _plan_error(exc) from exc
    return await _plan_read(db, plan)


@router.post("/plans/{plan_id}/retire", response_model=SplitPlanRead)
async def retire_split_plan(
    plan_id: uuid.UUID,
    payload: RetirePlanRequest,
    current_user: CurrentUser = Depends(require_permission("split_plans.activate")),
    db: AsyncSession = Depends(get_db),
) -> SplitPlanRead:
    try:
        plan = await plans_service.retire(
            db, organization_id=current_user.organization_id, plan_id=plan_id,
            actor_user_id=current_user.user_id, effective_at=payload.effective_at,
        )
    except plans_service.SplitPlanError as exc:
        raise _plan_error(exc) from exc
    return await _plan_read(db, plan, with_validation=False)


@router.post("/plans/{plan_id}/new-version", response_model=SplitPlanRead, status_code=status.HTTP_201_CREATED)
async def new_split_plan_version(
    plan_id: uuid.UUID,
    payload: NewVersionRequest,
    current_user: CurrentUser = Depends(require_permission("split_plans.manage")),
    db: AsyncSession = Depends(get_db),
) -> SplitPlanRead:
    try:
        plan = await plans_service.new_version(
            db, organization_id=current_user.organization_id, plan_id=plan_id,
            actor_user_id=current_user.user_id, valid_from=payload.valid_from,
        )
    except plans_service.SplitPlanError as exc:
        raise _plan_error(exc) from exc
    return await _plan_read(db, plan)
