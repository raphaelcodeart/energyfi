"""Commission preview: who would receive what if the contract activated now.

Uses the same sale resolution (services/sale.py) and engine as the real
calculation. Anything preventing the calculation is reported in
`blocking_errors`, and the contract cannot activate until it is fixed.
Per-instalment splits use the same `instalment_share` as the real run.
"""

import hashlib
import json
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.catalog import pricing
from app.modules.catalog.models import ProductVersion
from app.modules.commissions.engine.allocate import allocate
from app.modules.commissions.engine.types import AGENT, EngineError, EngineResult
from app.modules.commissions.services import plans as plans_service
from app.modules.commissions.services import sale as sale_service
from app.modules.commissions.services.run_calculation import instalment_share, movement_type_for
from app.modules.contracts import payment_plans
from app.modules.contracts.instalments import _add_months
from app.modules.contracts.models import Contract
from app.modules.customers.models import Company, Customer, CustomerProfile

MOVEMENT_LABELS = {
    "DIRECT": "Provvigione diretta",
    "INDIRECT": "Provvigione indiretta",
    "PROMOTER_FEE": "Fee segnalazione",
    "COMPANY_SHARE": "Quota azienda",
}


def allocation_rows(result: EngineResult) -> list[dict]:
    """Engine allocations shaped for preview and simulator."""
    rows = []
    for a in result.allocations:
        movement_type = movement_type_for(a)
        rows.append({
            "key": f"{a.rule_id or 'residual'}:{a.agent_id or 'company'}",
            "rule_id": a.rule_id,
            "agent_id": a.agent_id,
            "beneficiary_kind": a.beneficiary_kind,
            "name": a.agent_name,
            "role": a.label,
            "role_code": a.role_code,
            "depth": a.network_level,
            "calculation_type": a.calculation_type,
            "calculation_value": str(a.calculation_value) if a.calculation_value is not None else None,
            "movement_type": movement_type,
            "movement_label": MOVEMENT_LABELS.get(movement_type, movement_type),
            "total_cents": a.amount_cents,
            "fallback_applied": a.fallback_applied,
            "explanation": a.explanation,
        })
    return rows


def plan_summary(plan) -> dict | None:
    if plan is None:
        return None
    return {
        "id": str(plan.id), "name": plan.name, "version": plan.version, "status": plan.status,
        "valid_from": plan.valid_from.isoformat() if plan.valid_from else None,
        "valid_to": plan.valid_to.isoformat() if plan.valid_to else None,
        "fallback_strategy": plan.fallback_strategy, "distribution_mode": plan.distribution_mode,
        "accrual_trigger": plan.accrual_trigger,
    }


async def build_commission_preview(db: AsyncSession, *, organization_id: uuid.UUID, contract: Contract) -> dict:
    from app.modules.customers.service import display_name_for

    version = await db.get(ProductVersion, contract.product_version_id)
    warnings: list[str] = []
    blocking: list[str] = []

    customer = await db.get(Customer, contract.customer_id)
    customer_name = (
        display_name_for(customer.kind, await db.get(CustomerProfile, customer.id), await db.get(Company, customer.id))
        if customer is not None
        else "Cliente"
    )

    # Activated contracts show their frozen data; others what would be frozen now.
    res = await sale_service.resolve_contract(db, contract=contract)
    beneficiaries: list[dict] = []
    if contract.split_plan_id is not None and contract.network_snapshot_id is not None:
        try:
            spec, ctx, plan = await sale_service.frozen_context(db, contract=contract)
            result = allocate(spec, ctx)
            beneficiaries = allocation_rows(result)
            warnings.extend(result.warnings)
            res.plan = plan
            res.margin_cents = contract.reference_margin_cents
        except (ValueError, EngineError) as exc:
            blocking.append(getattr(exc, "message", str(exc)))
    elif res.ok and res.plan is not None:
        try:
            spec = await plans_service.plan_spec(db, plan=res.plan)
            result = allocate(spec, sale_service.context_for(res))
            beneficiaries = allocation_rows(result)
            warnings.extend(result.warnings)
        except EngineError as exc:
            blocking.append(exc.message)
    else:
        blocking.extend(res.errors)

    inactive = [m["name"] for m in res.chain[1:] if m.get("status") != "ACTIVE"]
    if inactive:
        warnings.append(
            "Non attivi nella catena (tengono il loro livello ma non ricevono quote): " + ", ".join(inactive) + "."
        )
    bonus = None

    total_commission = sum(b["total_cents"] for b in beneficiaries if b["beneficiary_kind"] == AGENT)
    company_share = sum(b["total_cents"] for b in beneficiaries if b["beneficiary_kind"] != AGENT)
    plan = payment_plans.plan_by_key(contract.payment_plan) if contract.paid_at else None
    if contract.paid_at and plan is None:
        # Paid, but not through a plan (a confirmed bank transfer): one payment.
        plan = payment_plans.plan_by_key(payment_plans.PLAN_FULL)
    gross = int(contract.gross_amount_cents or 0)

    def _schedule(p: payment_plans.PaymentPlan) -> list[dict]:
        start = (contract.paid_at.date() if contract.paid_at else None)
        if not gross:
            instalment_cents = 0
        elif contract.paid_at and p.key == contract.payment_plan:
            instalment_cents = payment_plans.contract_breakdown(p, contract).instalment_cents
        else:
            instalment_cents = payment_plans.breakdown_for(p, gross).instalment_cents
        rows = []
        for n in range(1, p.instalments + 1):
            rows.append({
                "number": n,
                "due_date": _add_months(start, n - 1).isoformat() if start else None,
                "customer_amount_cents": instalment_cents,
                "commission_cents": sum(
                    instalment_share(b["total_cents"], number=n, instalments=p.instalments)
                    for b in beneficiaries if b["beneficiary_kind"] == AGENT
                ),
                "per_beneficiary_cents": {
                    b["key"]: instalment_share(b["total_cents"], number=n, instalments=p.instalments)
                    for b in beneficiaries
                },
                "release": (
                    "Alla tua conferma di questa anteprima" if n == 1
                    else "Quando Stripe conferma l'incasso della rata (o la confermi tu a mano)"
                ),
            })
        return rows

    if plan is not None:
        payment = {
            "paid": True,
            "paid_at": contract.paid_at.isoformat() if contract.paid_at else None,
            "plan_key": plan.key,
            "plan_label": plan.label,
            "instalments": plan.instalments,
            "schedule": _schedule(plan),
            "last_release_date": _schedule(plan)[-1]["due_date"],
            "scenarios": [],
        }
    else:
        warnings.append(
            "Il cliente non ha ancora pagato: accettando, le provvigioni partiranno da sole al primo pagamento, "
            "divise secondo la modalità che sceglierà."
        )
        payment = {
            "paid": False,
            "paid_at": None,
            "plan_key": None,
            "plan_label": None,
            "instalments": None,
            "schedule": [],
            "last_release_date": None,
            "scenarios": [
                {
                    "plan_key": p.key,
                    "plan_label": p.label,
                    "instalments": p.instalments,
                    "commission_per_instalment_cents": sum(
                        instalment_share(b["total_cents"], number=1, instalments=p.instalments)
                        for b in beneficiaries if b["beneficiary_kind"] == AGENT
                    ),
                }
                for p in payment_plans.PAYMENT_PLANS
            ],
        }

    paid_gross = gross - int(contract.payment_discount_cents or 0) if contract.paid_at else gross
    cashback_cents = (
        pricing.contract_cashback_cents(version=version, gross_amount_cents=paid_gross)
        if version is not None and gross else 0
    )

    body = {
        "contract_id": str(contract.id),
        "customer_name": customer_name,
        "gross_amount_cents": gross,
        "beneficiaries": beneficiaries,
        "first_referrer_bonus": bonus,
        "total_commission_cents": total_commission,
        "company_share_cents": company_share,
        "reference_margin_cents": res.margin_cents,
        "sale_amount_cents": res.sale_amount_cents,
        "sold_at": res.sold_at.isoformat() if res.sold_at else None,
        "seller_role": res.seller_role.name if res.seller_role is not None else None,
        "plan": plan_summary(res.plan),
        "blocking_errors": blocking,
        "payment": payment,
        "customer_cashback_cents": cashback_cents,
    }
    checksum = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
    return {**body, "warnings": warnings, "checksum": checksum}
