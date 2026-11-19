"""Commission simulation for a hypothetical sale.

Follows the real calculation path (services/sale.py resolves role, network and
plan; engine/allocate.py splits the margin) but writes nothing. `plan_id`
tests a specific plan, including an unactivated draft.
"""

import uuid
from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.catalog.models import Product, ProductVersion
from app.modules.commissions.engine.allocate import allocate
from app.modules.commissions.engine.types import AGENT, EngineError
from app.modules.commissions.services import plans as plans_service
from app.modules.commissions.services import sale as sale_service
from app.modules.commissions.services.preview import allocation_rows, plan_summary


class SimulationError(Exception):
    pass


async def version_at(db: AsyncSession, *, product_id: uuid.UUID, at: datetime) -> ProductVersion | None:
    """Product version in force at `at`, else the latest (future dates are
    valid simulation inputs)."""
    in_force = (
        await db.execute(
            select(ProductVersion)
            .where(
                ProductVersion.product_id == product_id,
                ProductVersion.valid_from <= at,
                or_(ProductVersion.valid_to.is_(None), ProductVersion.valid_to > at),
            )
            .order_by(ProductVersion.valid_from.desc())
        )
    ).scalars().first()
    if in_force is not None:
        return in_force
    return (
        await db.execute(
            select(ProductVersion).where(ProductVersion.product_id == product_id).order_by(ProductVersion.valid_from.desc())
        )
    ).scalars().first()


async def simulate_sale(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    seller_agent_id: uuid.UUID,
    product_id: uuid.UUID,
    sold_at: datetime,
    sale_amount_cents: int | None = None,
    promoter_agent_id: uuid.UUID | None = None,
    plan_id: uuid.UUID | None = None,
) -> dict:
    product = await db.get(Product, product_id)
    if product is None or product.organization_id != organization_id:
        raise SimulationError("Prodotto non trovato.")
    version = await version_at(db, product_id=product_id, at=sold_at)
    amount = sale_amount_cents if sale_amount_cents is not None else (version.base_price_cents if version else None)
    override = None
    if plan_id is not None:
        override = await plans_service.get_plan(db, organization_id=organization_id, plan_id=plan_id)
        if override is None:
            raise SimulationError("Piano non trovato.")

    res = await sale_service.resolve_sale(
        db, organization_id=organization_id, seller_agent_id=seller_agent_id, version=version,
        sold_at=sold_at, sale_amount_cents=amount, promoter_agent_id=promoter_agent_id, plan_override=override,
    )
    rows: list[dict] = []
    warnings: list[str] = []
    errors = list(res.errors)
    if override is not None:
        # With an explicit plan, "no active plan" errors are irrelevant.
        errors = [e for e in errors if "Split Plan" not in e and "non può chiudere" not in e]
    if not errors and res.plan is not None:
        try:
            result = allocate(await plans_service.plan_spec(db, plan=res.plan), sale_service.context_for(res))
            rows = allocation_rows(result)
            warnings = list(result.warnings)
        except EngineError as exc:
            errors.append(exc.message)

    agents = sum(r["total_cents"] for r in rows if r["beneficiary_kind"] == AGENT)
    company = sum(r["total_cents"] for r in rows if r["beneficiary_kind"] != AGENT)
    return {
        "product_name": version.name if version else product.code,
        "product_code": product.code,
        "sold_at": sold_at.isoformat(),
        "sale_amount_cents": amount,
        "reference_margin_cents": res.margin_cents,
        "seller_role": res.seller_role.name if res.seller_role is not None else None,
        "plan": plan_summary(res.plan),
        "chain": [
            {"agent_id": str(m["agent_id"]), "name": m["name"], "depth": m["depth"],
             "role_code": m.get("role_code"), "status": m.get("status")}
            for m in res.chain
        ],
        "rows": rows,
        "agents_cents": agents,
        "company_cents": company,
        "distributed_cents": agents + company,
        "errors": errors,
        "warnings": warnings,
    }
