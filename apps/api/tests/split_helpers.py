"""Helpers for tests that run through the real commission engine.

`install_plan` gives a product a margin and an active Split Plan for a seller
role, assigning that role to every agent in the organization that lacks one.
The default rules are easy to check by hand: on a 45.00 EUR margin the seller
gets a fixed 40.00 and the direct sponsor gets the remaining 5.00.
"""

from datetime import UTC, datetime

from sqlalchemy import select

from app.modules.commercial import service as commercial_service
from app.modules.commissions.services import plans as plans_service
from app.modules.network.models import AgentProfile

PLAN_START = datetime(2020, 1, 1, tzinfo=UTC)

SELLER_PLUS_SPONSOR = [
    {"beneficiary_type": "SELLER", "calculation_type": "FIXED_AMOUNT", "amount_cents": 4000},
    {"beneficiary_type": "UPLINE_LEVEL", "network_level": 1, "calculation_type": "REMAINDER"},
]


async def ensure_roles_for_all_agents(db, organization_id, *, role_code: str = "NETWORKER"):
    roles = await commercial_service.ensure_default_roles(db, organization_id=organization_id)
    role = roles[role_code]
    agents = (await db.execute(select(AgentProfile).where(AgentProfile.organization_id == organization_id))).scalars()
    for agent in agents:
        await commercial_service.ensure_role_for_agent(db, organization_id=organization_id, agent=agent, role_id=role.id)
    await db.commit()
    return roles


async def install_plan(
    db,
    organization_id,
    *,
    product_version,
    rules: list[dict] | None = None,
    margin_cents: int = 4500,
    role_code: str = "NETWORKER",
    fallback: str = "COMPANY",
    accrual: str = "PER_INSTALMENT",
    mode: str = "FULL",
    actor_user_id=None,
):
    roles = await ensure_roles_for_all_agents(db, organization_id, role_code=role_code)
    product_version.margin_type = "FIXED"
    product_version.margin_amount_cents = margin_cents
    product_version.margin_percentage = None
    await db.commit()
    plan = await plans_service.create_plan(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        values={
            "name": "Piano di test", "product_id": product_version.product_id,
            "seller_role_id": roles[role_code].id, "valid_from": PLAN_START,
            "fallback_strategy": fallback, "distribution_mode": mode, "accrual_trigger": accrual,
        },
        rules=rules if rules is not None else SELLER_PLUS_SPONSOR,
    )
    return await plans_service.activate(db, organization_id=organization_id, plan_id=plan.id, actor_user_id=actor_user_id)
