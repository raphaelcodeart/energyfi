"""Split Plan creation, validation, activation and versioning.

  DRAFT    editable, never used by the engine;
  ACTIVE   immutable, used for sales dated within its period;
  RETIRED  no longer used for new sales, kept because past sales reference it.

Changing an active plan means creating the next version (same `plan_key`,
`version` + 1) with its own start date. Activating it closes the open previous
version at that date; already calculated commissions are never touched.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.foundation.db import utcnow
from app.modules.audit import service as audit_service
from app.modules.catalog.models import Product, ProductCategory, ProductVersion
from app.modules.commercial.models import CommercialRole
from app.modules.commissions.engine.types import PlanSpec, RuleSpec
from app.modules.commissions.engine.validation import PlanValidation, validate_plan
from app.modules.commissions.models import SplitPlan, SplitRule

PLAN_FIELDS = ("name", "valid_from", "valid_to", "fallback_strategy", "distribution_mode", "accrual_trigger", "notes")
RULE_FIELDS = (
    "sequence", "label", "beneficiary_type", "network_level", "required_role_id", "calculation_type",
    "percentage", "amount_cents", "min_amount_cents", "max_amount_cents", "fallback_strategy",
)


class SplitPlanError(Exception):
    def __init__(self, message: str, errors: list[str] | None = None):
        super().__init__(message)
        self.message = message
        self.errors = errors or []


# --- Reads ----------------------------------------------------------------------


async def get_plan(db: AsyncSession, *, organization_id: uuid.UUID, plan_id: uuid.UUID) -> SplitPlan | None:
    plan = await db.get(SplitPlan, plan_id)
    if plan is None or plan.organization_id != organization_id or plan.status == "LEGACY":
        return None
    return plan


async def plan_rules(db: AsyncSession, *, plan_id: uuid.UUID) -> list[SplitRule]:
    return list(
        (
            await db.execute(
                select(SplitRule).where(SplitRule.commission_plan_version_id == plan_id)
                .order_by(SplitRule.sequence, SplitRule.created_at)
            )
        ).scalars()
    )


async def list_plans(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    status: str | None = None,
    product_id: uuid.UUID | None = None,
    seller_role_id: uuid.UUID | None = None,
) -> list[SplitPlan]:
    stmt = select(SplitPlan).where(SplitPlan.organization_id == organization_id, SplitPlan.status != "LEGACY")
    if status:
        stmt = stmt.where(SplitPlan.status == status)
    if product_id:
        stmt = stmt.where(SplitPlan.product_id == product_id)
    if seller_role_id:
        stmt = stmt.where(SplitPlan.seller_role_id == seller_role_id)
    return list((await db.execute(stmt.order_by(SplitPlan.name, SplitPlan.version.desc()))).scalars())


async def role_codes(db: AsyncSession, *, organization_id: uuid.UUID) -> dict[uuid.UUID, str]:
    return dict(
        (await db.execute(
            select(CommercialRole.id, CommercialRole.code).where(CommercialRole.organization_id == organization_id)
        )).all()
    )


def to_rule_spec(rule: SplitRule, codes: dict[uuid.UUID, str]) -> RuleSpec:
    return RuleSpec(
        id=str(rule.id),
        sequence=rule.sequence,
        beneficiary_type=rule.beneficiary_type or "",
        calculation_type=rule.calculation_type or "",
        label=rule.label,
        network_level=rule.network_level,
        required_role_id=str(rule.required_role_id) if rule.required_role_id else None,
        required_role_code=codes.get(rule.required_role_id) if rule.required_role_id else None,
        percentage=Decimal(str(rule.percentage)) if rule.percentage is not None else None,
        amount_cents=rule.amount_cents,
        min_amount_cents=rule.min_amount_cents,
        max_amount_cents=rule.max_amount_cents,
        fallback_strategy=rule.fallback_strategy,
    )


async def plan_spec(db: AsyncSession, *, plan: SplitPlan) -> PlanSpec:
    codes = await role_codes(db, organization_id=plan.organization_id)
    rules = await plan_rules(db, plan_id=plan.id)
    return PlanSpec(
        id=str(plan.id), version=plan.version, name=plan.name or plan.version_label,
        fallback_strategy=plan.fallback_strategy, distribution_mode=plan.distribution_mode,
        rules=tuple(to_rule_spec(r, codes) for r in rules),
    )


# --- Plan selection for a sale ----------------------------------------------------


async def resolve_plan(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    product_id: uuid.UUID,
    seller_role_id: uuid.UUID | None,
    at: datetime,
) -> SplitPlan | None:
    """ACTIVE plan valid at `at` for (product, seller role), falling back to
    (product category, role). Without a plan no commission can be computed."""
    if seller_role_id is None:
        return None
    valid = and_(
        SplitPlan.organization_id == organization_id,
        SplitPlan.status == "ACTIVE",
        SplitPlan.seller_role_id == seller_role_id,
        SplitPlan.valid_from <= at,
        or_(SplitPlan.valid_to.is_(None), SplitPlan.valid_to > at),
    )
    by_product = (
        await db.execute(select(SplitPlan).where(valid, SplitPlan.product_id == product_id)
                         .order_by(SplitPlan.valid_from.desc()))
    ).scalars().first()
    if by_product is not None:
        return by_product
    product = await db.get(Product, product_id)
    if product is None or product.commercial_category_id is None:
        return None
    return (
        await db.execute(select(SplitPlan).where(valid, SplitPlan.category_id == product.commercial_category_id)
                         .order_by(SplitPlan.valid_from.desc()))
    ).scalars().first()


# --- Validation ---------------------------------------------------------------------


async def reference_margin(db: AsyncSession, plan: SplitPlan) -> int | None:
    """Margin for the distributed/residual summary: the current product
    version's margin, when it is a fixed amount."""
    if plan.product_id is None:
        return None
    version = (
        await db.execute(
            select(ProductVersion)
            .where(ProductVersion.product_id == plan.product_id)
            .order_by(ProductVersion.valid_from.desc())
        )
    ).scalars().first()
    if version is not None and version.margin_type == "FIXED":
        return int(version.margin_amount_cents or 0)
    return None


async def validate(db: AsyncSession, *, plan: SplitPlan) -> PlanValidation:
    spec = await plan_spec(db, plan=plan)
    role = await db.get(CommercialRole, plan.seller_role_id) if plan.seller_role_id else None
    result = validate_plan(
        list(spec.rules),
        distribution_mode=plan.distribution_mode,
        fallback_strategy=plan.fallback_strategy,
        reference_margin_cents=await reference_margin(db, plan),
        seller_role_can_close_sales=role.can_close_sales if role else None,
    )
    if role is None:
        result.errors.append("Indica il ruolo del venditore a cui si applica il piano.")
    if (plan.product_id is None) == (plan.category_id is None):
        result.errors.append("Il piano vale per un prodotto oppure per una categoria, non per entrambi né per nessuno.")
    if plan.valid_to is not None and plan.valid_to <= plan.valid_from:
        result.errors.append("La fine della validità deve essere successiva all'inizio.")
    if plan.product_id is not None:
        # The product's company caps how far into the network it pays.
        from app.modules.catalog.models import Company, Product

        product = await db.get(Product, plan.product_id)
        company = await db.get(Company, product.company_id) if product and product.company_id else None
        if company is not None and company.max_network_depth:
            deepest = max((r.network_level or 0 for r in spec.rules), default=0)
            if deepest > company.max_network_depth:
                result.errors.append(
                    f"{company.name} paga al massimo {company.max_network_depth} "
                    f"{'livello' if company.max_network_depth == 1 else 'livelli'} di rete: "
                    f"questo piano arriva al livello {deepest}."
                )
    return result


# --- Writes -------------------------------------------------------------------------


def _plan_snapshot(plan: SplitPlan, rules: list[SplitRule]) -> dict:
    def _v(value):
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, (uuid.UUID, Decimal)):
            return str(value)
        return value

    return {
        "plan": {f: _v(getattr(plan, f)) for f in ("status", "version", "product_id", "category_id", "seller_role_id", *PLAN_FIELDS)},
        "rules": [{f: _v(getattr(r, f)) for f in RULE_FIELDS} for r in rules],
    }


async def _check_scope(db: AsyncSession, *, organization_id: uuid.UUID, values: dict) -> None:
    if values.get("product_id"):
        product = await db.get(Product, values["product_id"])
        if product is None or product.organization_id != organization_id:
            raise SplitPlanError("Prodotto non trovato.")
    if values.get("category_id"):
        category = await db.get(ProductCategory, values["category_id"])
        if category is None or category.organization_id != organization_id:
            raise SplitPlanError("Categoria non trovata.")
    if values.get("seller_role_id"):
        role = await db.get(CommercialRole, values["seller_role_id"])
        if role is None or role.organization_id != organization_id:
            raise SplitPlanError("Ruolo non trovato.")


async def _write_rules(db: AsyncSession, *, plan: SplitPlan, rules: list[dict]) -> list[SplitRule]:
    existing = await plan_rules(db, plan_id=plan.id)
    for rule in existing:
        await db.delete(rule)
    await db.flush()
    created = []
    for index, values in enumerate(rules):
        data = {f: values.get(f) for f in RULE_FIELDS}
        if data["sequence"] is None:
            data["sequence"] = (index + 1) * 10
        rule = SplitRule(commission_plan_version_id=plan.id, rule_type="SPLIT", **data)
        db.add(rule)
        created.append(rule)
    await db.flush()
    return created


async def create_plan(
    db: AsyncSession, *, organization_id: uuid.UUID, actor_user_id: uuid.UUID | None, values: dict, rules: list[dict]
) -> SplitPlan:
    await _check_scope(db, organization_id=organization_id, values=values)
    plan = SplitPlan(
        organization_id=organization_id,
        status="DRAFT",
        version=1,
        plan_key=uuid.uuid4(),
        version_label="v1",
        product_id=values.get("product_id"),
        category_id=values.get("category_id"),
        seller_role_id=values.get("seller_role_id"),
        created_by_user_id=actor_user_id,
        **{f: values[f] for f in PLAN_FIELDS if values.get(f) is not None},
    )
    if plan.valid_from is None:
        plan.valid_from = utcnow()
    db.add(plan)
    await db.flush()
    created = await _write_rules(db, plan=plan, rules=rules)
    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="split_plan.created", entity_type="split_plan", entity_id=str(plan.id),
        new_value=_plan_snapshot(plan, created),
    )
    await db.commit()
    await db.refresh(plan)
    return plan


async def update_draft(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    plan_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    values: dict,
    rules: list[dict] | None,
) -> SplitPlan:
    plan = await get_plan(db, organization_id=organization_id, plan_id=plan_id)
    if plan is None:
        raise SplitPlanError("Piano non trovato.")
    if plan.status != "DRAFT":
        raise SplitPlanError(
            "Un piano attivo o ritirato non si modifica: crea una nuova versione, così le vendite "
            "già calcolate restano legate alle regole con cui sono nate."
        )
    before = _plan_snapshot(plan, await plan_rules(db, plan_id=plan.id))
    await _check_scope(db, organization_id=organization_id, values=values)
    for field in ("product_id", "category_id", "seller_role_id"):
        if field in values:
            setattr(plan, field, values[field])
    for field in PLAN_FIELDS:
        if field in values:
            setattr(plan, field, values[field])
    new_rules = await _write_rules(db, plan=plan, rules=rules) if rules is not None else await plan_rules(db, plan_id=plan.id)
    plan.updated_at = utcnow()
    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="split_plan.updated", entity_type="split_plan", entity_id=str(plan.id),
        previous_value=before, new_value=_plan_snapshot(plan, new_rules),
    )
    await db.commit()
    await db.refresh(plan)
    return plan


async def activate(
    db: AsyncSession, *, organization_id: uuid.UUID, plan_id: uuid.UUID, actor_user_id: uuid.UUID | None
) -> SplitPlan:
    """DRAFT -> ACTIVE. Rejected if the plan is invalid or overlaps another
    active plan for the same scope and role, except the plan's own open
    previous version, which is closed at this version's start date."""
    plan = (
        await db.execute(select(SplitPlan).where(SplitPlan.id == plan_id).with_for_update())
    ).scalar_one_or_none()
    if plan is None or plan.organization_id != organization_id or plan.status == "LEGACY":
        raise SplitPlanError("Piano non trovato.")
    if plan.status != "DRAFT":
        raise SplitPlanError("Solo un piano in bozza può essere attivato.")

    result = await validate(db, plan=plan)
    if not result.ok:
        raise SplitPlanError("Il piano non è valido e non può essere attivato.", result.errors)

    scope = (
        SplitPlan.product_id == plan.product_id if plan.product_id else SplitPlan.category_id == plan.category_id
    )
    overlapping = list(
        (
            await db.execute(
                select(SplitPlan).where(
                    SplitPlan.organization_id == organization_id,
                    SplitPlan.status == "ACTIVE",
                    SplitPlan.seller_role_id == plan.seller_role_id,
                    scope,
                    SplitPlan.id != plan.id,
                    or_(SplitPlan.valid_to.is_(None), SplitPlan.valid_to > plan.valid_from),
                    *( [SplitPlan.valid_from < plan.valid_to] if plan.valid_to else [] ),
                ).with_for_update()
            )
        ).scalars()
    )
    closed = []
    for other in overlapping:
        if other.plan_key == plan.plan_key and other.valid_to is None and other.valid_from < plan.valid_from:
            other.valid_to = plan.valid_from
            other.updated_at = utcnow()
            closed.append(other)
            continue
        raise SplitPlanError(
            f"Il periodo si sovrappone al piano attivo «{other.name}» v{other.version} "
            f"(dal {other.valid_from:%d/%m/%Y}"
            + (f" al {other.valid_to:%d/%m/%Y})" if other.valid_to else ", senza scadenza)")
            + ". Chiudi quel piano o cambia le date."
        )
    # Close previous versions first: the no-overlap constraint is checked row
    # by row, so they must be written before this plan turns ACTIVE.
    if closed:
        await db.flush()

    plan.status = "ACTIVE"
    plan.activated_at = utcnow()
    plan.activated_by_user_id = actor_user_id
    plan.updated_at = utcnow()
    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="split_plan.activated", entity_type="split_plan", entity_id=str(plan.id),
        previous_value={"status": "DRAFT"},
        new_value={
            "status": "ACTIVE", "version": plan.version,
            "closed_previous_versions": [str(c.id) for c in closed],
            **_plan_snapshot(plan, await plan_rules(db, plan_id=plan.id)),
        },
    )
    await db.commit()
    await db.refresh(plan)
    return plan


async def retire(
    db: AsyncSession, *, organization_id: uuid.UUID, plan_id: uuid.UUID, actor_user_id: uuid.UUID | None,
    effective_at: datetime | None = None,
) -> SplitPlan:
    """ACTIVE -> RETIRED from `effective_at` (default now). Past calculations
    are unaffected."""
    plan = await get_plan(db, organization_id=organization_id, plan_id=plan_id)
    if plan is None:
        raise SplitPlanError("Piano non trovato.")
    if plan.status != "ACTIVE":
        raise SplitPlanError("Solo un piano attivo può essere ritirato.")
    when = effective_at or utcnow()
    previous = {"status": plan.status, "valid_to": plan.valid_to.isoformat() if plan.valid_to else None}
    plan.status = "RETIRED"
    plan.retired_at = utcnow()
    if plan.valid_to is None or plan.valid_to > when:
        plan.valid_to = max(when, plan.valid_from)
    plan.updated_at = utcnow()
    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="split_plan.retired", entity_type="split_plan", entity_id=str(plan.id),
        previous_value=previous, new_value={"status": "RETIRED", "valid_to": plan.valid_to.isoformat()},
    )
    await db.commit()
    await db.refresh(plan)
    return plan


async def new_version(
    db: AsyncSession, *, organization_id: uuid.UUID, plan_id: uuid.UUID, actor_user_id: uuid.UUID | None,
    valid_from: datetime | None = None,
) -> SplitPlan:
    """Create a draft copying a plan's rules and settings as version + 1."""
    source = await get_plan(db, organization_id=organization_id, plan_id=plan_id)
    if source is None:
        raise SplitPlanError("Piano non trovato.")
    latest = (
        await db.execute(select(func.max(SplitPlan.version)).where(SplitPlan.plan_key == source.plan_key))
    ).scalar_one()
    draft_exists = (
        await db.execute(
            select(SplitPlan.id).where(SplitPlan.plan_key == source.plan_key, SplitPlan.status == "DRAFT")
        )
    ).first()
    if draft_exists is not None:
        raise SplitPlanError("Esiste già una bozza della versione successiva di questo piano.")
    version = int(latest or source.version) + 1
    plan = SplitPlan(
        organization_id=organization_id, status="DRAFT", plan_key=source.plan_key, version=version,
        version_label=f"v{version}", product_id=source.product_id, category_id=source.category_id,
        seller_role_id=source.seller_role_id, name=source.name, fallback_strategy=source.fallback_strategy,
        distribution_mode=source.distribution_mode, accrual_trigger=source.accrual_trigger, notes=source.notes,
        valid_from=valid_from or utcnow(), created_by_user_id=actor_user_id,
    )
    db.add(plan)
    await db.flush()
    rules = [{f: getattr(r, f) for f in RULE_FIELDS} for r in await plan_rules(db, plan_id=source.id)]
    created = await _write_rules(db, plan=plan, rules=rules)
    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="split_plan.version_created", entity_type="split_plan", entity_id=str(plan.id),
        new_value={"from_plan_id": str(source.id), **_plan_snapshot(plan, created)},
    )
    await db.commit()
    await db.refresh(plan)
    return plan


async def delete_draft(
    db: AsyncSession, *, organization_id: uuid.UUID, plan_id: uuid.UUID, actor_user_id: uuid.UUID | None
) -> None:
    plan = await get_plan(db, organization_id=organization_id, plan_id=plan_id)
    if plan is None:
        raise SplitPlanError("Piano non trovato.")
    if plan.status != "DRAFT":
        raise SplitPlanError("Si possono eliminare solo le bozze: un piano attivo si ritira.")
    rules = await plan_rules(db, plan_id=plan.id)
    snapshot = _plan_snapshot(plan, rules)
    for rule in rules:
        await db.delete(rule)
    await db.delete(plan)
    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="split_plan.draft_deleted", entity_type="split_plan", entity_id=str(plan_id),
        previous_value=snapshot,
    )
    await db.commit()
