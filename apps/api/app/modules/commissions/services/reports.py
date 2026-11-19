"""Management reports and seller summary, built only from frozen movement
columns, so closed periods never change when plans, roles or products do.
"""

import uuid
from collections import defaultdict
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.catalog.models import Product, ProductCategory
from app.modules.commissions.models import CommissionMovement, SplitPlan
from app.modules.contracts.models import Contract, ContractAttribution
from app.modules.network.models import AgentProfile

EXCLUDED_STATUSES = ("CANCELLED",)
PENDING = ("PENDING", "ACCRUED")
APPROVED = ("APPROVED", "PAYABLE")


async def commission_report(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    product_id: uuid.UUID | None = None,
    category_id: uuid.UUID | None = None,
    agent_id: uuid.UUID | None = None,
    role_code: str | None = None,
    plan_id: uuid.UUID | None = None,
    level: int | None = None,
    status: str | None = None,
) -> dict:
    """Date filters apply to the sale date, not the movement's creation."""
    sold_at = func.coalesce(Contract.sold_at, Contract.created_at)
    stmt = (
        select(
            CommissionMovement.contract_id,
            CommissionMovement.beneficiary_kind,
            CommissionMovement.agent_id,
            CommissionMovement.movement_type,
            CommissionMovement.amount_cents,
            CommissionMovement.status,
            CommissionMovement.network_level,
            CommissionMovement.role_code_snapshot,
            CommissionMovement.split_plan_id,
            CommissionMovement.plan_version,
            CommissionMovement.product_id,
            Contract.sale_amount_cents,
            Contract.reference_margin_cents,
            Contract.seller_role_code,
            Product.code,
            Product.commercial_category_id,
        )
        .select_from(CommissionMovement)
        .join(Contract, Contract.id == CommissionMovement.contract_id)
        .join(Product, Product.id == CommissionMovement.product_id, isouter=True)
        .where(
            CommissionMovement.organization_id == organization_id,
            CommissionMovement.status.notin_(EXCLUDED_STATUSES),
            CommissionMovement.split_plan_id.is_not(None),
        )
    )
    if date_from is not None:
        stmt = stmt.where(sold_at >= date_from)
    if date_to is not None:
        stmt = stmt.where(sold_at < date_to)
    if product_id is not None:
        stmt = stmt.where(CommissionMovement.product_id == product_id)
    if category_id is not None:
        stmt = stmt.where(Product.commercial_category_id == category_id)
    if plan_id is not None:
        stmt = stmt.where(CommissionMovement.split_plan_id == plan_id)
    if role_code:
        stmt = stmt.where(Contract.seller_role_code == role_code)
    if agent_id is not None:
        stmt = stmt.where(CommissionMovement.source_seller_agent_id == agent_id)
    if level is not None:
        stmt = stmt.where(CommissionMovement.network_level == level)
    if status:
        stmt = stmt.where(CommissionMovement.status == status)
    rows = (await db.execute(stmt)).all()

    contracts: dict[uuid.UUID, tuple[int, int]] = {}
    totals = defaultdict(int)
    by_role: dict[str, dict] = defaultdict(lambda: defaultdict(int))
    by_product: dict[str, dict] = defaultdict(lambda: defaultdict(int))
    by_level: dict[str, dict] = defaultdict(lambda: defaultdict(int))
    by_plan: dict[tuple, dict] = defaultdict(lambda: defaultdict(int))
    by_status: dict[str, int] = defaultdict(int)
    by_beneficiary_role: dict[str, int] = defaultdict(int)
    product_contracts: dict[str, set] = defaultdict(set)
    role_contracts: dict[str, set] = defaultdict(set)
    categories: dict[uuid.UUID | None, set] = defaultdict(set)

    for (
        contract_id, kind, _agent, movement_type, amount, mv_status, net_level, role_snapshot, plan, version,
        _product, sale_amount, margin, seller_role, product_code, category,
    ) in rows:
        contracts.setdefault(contract_id, (int(sale_amount or 0), int(margin or 0)))
        is_agent = kind == "AGENT"
        key_role = seller_role or "—"
        key_product = product_code or "—"
        if is_agent:
            totals["agents_cents"] += amount
            by_role[key_role]["commission_cents"] += amount
            by_product[key_product]["commission_cents"] += amount
            by_level[str(net_level) if net_level is not None else "—"]["commission_cents"] += amount
            by_plan[(plan, version)]["commission_cents"] += amount
            by_status[mv_status] += amount
            by_beneficiary_role[role_snapshot or "—"] += amount
            totals[f"{movement_type.lower()}_cents"] += amount
        else:
            totals["company_cents"] += amount
            by_role[key_role]["company_cents"] += amount
            by_product[key_product]["company_cents"] += amount
            by_plan[(plan, version)]["company_cents"] += amount
        product_contracts[key_product].add(contract_id)
        role_contracts[key_role].add(contract_id)
        categories[category].add(contract_id)

    plan_names = dict(
        (await db.execute(select(SplitPlan.id, SplitPlan.name).where(SplitPlan.organization_id == organization_id))).all()
    )
    category_names = dict(
        (await db.execute(
            select(ProductCategory.id, ProductCategory.name).where(ProductCategory.organization_id == organization_id)
        )).all()
    )

    def _with_sales(bucket: dict, sets: dict) -> list[dict]:
        out = []
        for key, values in sorted(bucket.items()):
            ids = sets.get(key, set())
            out.append({
                "key": key, "sales": len(ids),
                "revenue_cents": sum(contracts[c][0] for c in ids),
                "margin_cents": sum(contracts[c][1] for c in ids),
                "commission_cents": values.get("commission_cents", 0),
                "company_cents": values.get("company_cents", 0),
            })
        return out

    return {
        "totals": {
            "sales": len(contracts),
            "revenue_cents": sum(v[0] for v in contracts.values()),
            "margin_cents": sum(v[1] for v in contracts.values()),
            "commissions_cents": totals["agents_cents"],
            "company_cents": totals["company_cents"],
            "direct_cents": totals["direct_cents"],
            "indirect_cents": totals["indirect_cents"],
            "promoter_fee_cents": totals["promoter_fee_cents"],
            "reversal_cents": totals["reversal_cents"],
        },
        "by_seller_role": _with_sales(by_role, role_contracts),
        "by_product": _with_sales(by_product, product_contracts),
        "by_level": [
            {"key": k, "commission_cents": v["commission_cents"]}
            for k, v in sorted(by_level.items(), key=lambda kv: (kv[0] == "—", kv[0].zfill(3)))
        ],
        "by_plan": [
            {"key": f"{plan_names.get(p) or '—'} v{ver}", "plan_id": str(p) if p else None,
             "commission_cents": v["commission_cents"], "company_cents": v["company_cents"]}
            for (p, ver), v in by_plan.items()
        ],
        "by_category": [
            {"key": category_names.get(c, "Senza categoria"), "sales": len(ids),
             "revenue_cents": sum(contracts[i][0] for i in ids), "margin_cents": sum(contracts[i][1] for i in ids)}
            for c, ids in categories.items()
        ],
        "by_status": [{"key": k, "commission_cents": v} for k, v in sorted(by_status.items())],
        "by_beneficiary_role": [{"key": k, "commission_cents": v} for k, v in sorted(by_beneficiary_role.items())],
    }


async def seller_summary(db: AsyncSession, *, organization_id: uuid.UUID, agent_id: uuid.UUID) -> dict:
    """Seller dashboard: direct, indirect and fee totals, plus by status."""
    rows = (
        await db.execute(
            select(CommissionMovement.movement_type, CommissionMovement.status, func.sum(CommissionMovement.amount_cents))
            .where(
                CommissionMovement.organization_id == organization_id,
                CommissionMovement.agent_id == agent_id,
                CommissionMovement.status.notin_(EXCLUDED_STATUSES),
            )
            .group_by(CommissionMovement.movement_type, CommissionMovement.status)
        )
    ).all()
    out = defaultdict(int)
    for movement_type, mv_status, amount in rows:
        amount = int(amount or 0)
        if movement_type in ("DIRECT", "PERSONAL_TOKEN"):
            out["direct_cents"] += amount
        elif movement_type == "PROMOTER_FEE":
            out["promoter_fee_cents"] += amount
        elif movement_type == "REVERSAL":
            out["reversal_cents"] += amount
        else:
            out["indirect_cents"] += amount
        if mv_status in PENDING:
            out["pending_cents"] += amount
        elif mv_status in APPROVED:
            out["approved_cents"] += amount
        elif mv_status == "PAID":
            out["paid_cents"] += amount

    sales = (
        await db.execute(
            select(func.count(Contract.id), func.coalesce(func.sum(Contract.sale_amount_cents), 0))
            .join(ContractAttribution, ContractAttribution.id == Contract.contract_attribution_id)
            .where(
                Contract.organization_id == organization_id,
                ContractAttribution.producer_agent_id == agent_id,
                Contract.status.in_(("ACTIVE", "RENEWED", "EXPIRED", "SUSPENDED")),
            )
        )
    ).one()
    agent = await db.get(AgentProfile, agent_id)
    return {
        "direct_cents": out["direct_cents"],
        "indirect_cents": out["indirect_cents"],
        "promoter_fee_cents": out["promoter_fee_cents"],
        "reversal_cents": out["reversal_cents"],
        "pending_cents": out["pending_cents"],
        "approved_cents": out["approved_cents"],
        "paid_cents": out["paid_cents"],
        "personal_sales": int(sales[0] or 0),
        "personal_sales_amount_cents": int(sales[1] or 0),
        "agent_name": agent.display_name if agent else None,
    }
