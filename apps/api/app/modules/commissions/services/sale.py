"""Builds the engine context for a sale.

* `freeze_contract` (at activation): stores sale date, seller role, plan,
  amount, margin and sponsorship chain on the contract and network snapshot.
* `resolve_sale` (preview, simulator): same resolution, writes nothing.
* `frozen_context` (real calculation): reads only frozen data, never current
  roles, network or plans, so calculations stay reproducible.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.foundation.db import utcnow
from app.modules.catalog.models import ProductVersion
from app.modules.commercial import service as commercial_service
from app.modules.commercial.models import CommercialRole
from app.modules.commissions.engine.types import ChainNode, PlanSpec, SaleContext
from app.modules.commissions.models import SplitPlan
from app.modules.commissions.services import plans as plans_service
from app.modules.contracts.models import Contract, ContractAttribution
from app.modules.network import service as network_service
from app.modules.network.models import AgentProfile, NetworkSnapshot, NetworkSnapshotNode


def margin_for(version: ProductVersion | None, sale_amount_cents: int | None) -> int | None:
    """Reference margin: the version's fixed amount, or its percentage of the
    net sale amount rounded half-up. None if no margin is configured."""
    if version is None or version.margin_type is None:
        return None
    if version.margin_type == "FIXED":
        return int(version.margin_amount_cents or 0)
    if version.margin_type == "PERCENTAGE" and sale_amount_cents is not None:
        raw = Decimal(sale_amount_cents) * Decimal(str(version.margin_percentage or 0)) / Decimal(100)
        return int(raw.quantize(Decimal(1), rounding=ROUND_HALF_UP))
    return None


def sale_amount_for(contract: Contract, version: ProductVersion | None) -> int | None:
    if contract.net_amount_cents is not None:
        return int(contract.net_amount_cents)
    return int(version.base_price_cents) if version is not None else None


@dataclass
class SaleResolution:
    seller_agent_id: uuid.UUID | None
    sold_at: datetime
    product_id: uuid.UUID | None
    sale_amount_cents: int | None
    margin_cents: int | None
    seller_role: CommercialRole | None = None
    plan: SplitPlan | None = None
    chain: list[dict] = field(default_factory=list)
    promoter: dict | None = None
    delegation_influencer: dict | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def _node(member: dict, depth: int | None = None) -> ChainNode:
    return ChainNode(
        agent_id=str(member["agent_id"]),
        name=member["name"],
        depth=member["depth"] if depth is None else depth,
        role_id=str(member["role_id"]) if member.get("role_id") else None,
        role_code=member.get("role_code"),
        eligible=member.get("status") == "ACTIVE",
        allows_delegation=bool(member.get("allows_delegation")),
    )


async def _person(db: AsyncSession, agent_id: uuid.UUID | None, at: datetime) -> dict | None:
    if agent_id is None:
        return None
    agent = await db.get(AgentProfile, agent_id)
    if agent is None:
        return None
    role = await commercial_service.role_at(db, agent_id=agent_id, at=at)
    return {
        "agent_id": agent.id, "name": agent.display_name, "depth": -1, "status": agent.status,
        "role_id": role.id if role else None, "role_code": role.code if role else None,
        "allows_delegation": bool(role.allows_delegation) if role else False,
    }


async def _lead_promoter_id(db: AsyncSession, lead_id: uuid.UUID | None) -> uuid.UUID | None:
    if lead_id is None:
        return None
    from app.modules.leads.models import Lead

    lead = await db.get(Lead, lead_id)
    return lead.promoter_agent_id if lead is not None else None


async def resolve_sale(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    seller_agent_id: uuid.UUID | None,
    version: ProductVersion | None,
    sold_at: datetime,
    sale_amount_cents: int | None,
    lead_id: uuid.UUID | None = None,
    promoter_agent_id: uuid.UUID | None = None,
    plan_override: SplitPlan | None = None,
) -> SaleResolution:
    """Resolve engine inputs as of the sale date, without writing. Problems
    are collected in `errors` rather than raised so previews can show them."""
    res = SaleResolution(
        seller_agent_id=seller_agent_id, sold_at=sold_at,
        product_id=version.product_id if version else None,
        sale_amount_cents=sale_amount_cents, margin_cents=margin_for(version, sale_amount_cents),
    )
    if version is None:
        res.errors.append("Il contratto non ha ancora un prodotto.")
    elif version.margin_type is None:
        res.errors.append("Il prodotto non ha un margine configurato: impostalo nel catalogo.")
    elif res.margin_cents is None:
        res.errors.append("Impossibile calcolare il margine: manca l'importo della vendita.")

    if seller_agent_id is None:
        res.errors.append("La vendita non ha un venditore.")
        return res

    res.chain = await network_service.chain_at(
        db, organization_id=organization_id, seller_agent_id=seller_agent_id, at=sold_at
    )
    if not res.chain:
        res.errors.append("Il venditore non è nella rete alla data della vendita.")
        return res
    seller = res.chain[0]
    if seller.get("status") != "ACTIVE":
        res.errors.append(f"Il venditore {seller['name']} non è attivo.")
    if seller.get("role_id") is None:
        res.errors.append(f"{seller['name']} non ha un ruolo commerciale: assegnaglielo dalla scheda del collaboratore.")
    else:
        res.seller_role = await db.get(CommercialRole, seller["role_id"])
        if res.seller_role is not None and not res.seller_role.can_close_sales:
            res.errors.append(f"Il ruolo {res.seller_role.name} non può chiudere vendite.")

    promoter_id = promoter_agent_id or await _lead_promoter_id(db, lead_id)
    res.promoter = await _person(db, promoter_id, sold_at)
    influencer_id = await commercial_service.delegation_influencer_at(
        db, delegate_agent_id=seller_agent_id, at=sold_at
    )
    if influencer_id is not None:
        in_chain = next((m for m in res.chain if m["agent_id"] == influencer_id), None)
        res.delegation_influencer = in_chain or await _person(db, influencer_id, sold_at)

    if plan_override is not None:
        res.plan = plan_override
    elif version is not None and res.seller_role is not None:
        res.plan = await plans_service.resolve_plan(
            db, organization_id=organization_id, product_id=version.product_id,
            seller_role_id=res.seller_role.id, at=sold_at,
        )
    if res.plan is None and res.seller_role is not None and version is not None:
        res.errors.append(
            f"Nessuno Split Plan attivo al {sold_at:%d/%m/%Y} per questo prodotto e il ruolo "
            f"{res.seller_role.name}: crealo e attivalo nella sezione Split Plan."
        )
    return res


def context_for(res: SaleResolution) -> SaleContext:
    seller_role = res.seller_role
    return SaleContext(
        margin_cents=int(res.margin_cents or 0),
        chain=tuple(_node(m) for m in res.chain),
        max_depth=seller_role.network_depth if seller_role is not None else None,
        delegation_influencer=_node(res.delegation_influencer) if res.delegation_influencer else None,
        promoter=_node(res.promoter, depth=-1) if res.promoter else None,
    )


async def seller_for_contract(db: AsyncSession, contract: Contract) -> uuid.UUID | None:
    if contract.contract_attribution_id is None:
        return None
    attribution = await db.get(ContractAttribution, contract.contract_attribution_id)
    return attribution.producer_agent_id if attribution else None


async def resolve_contract(db: AsyncSession, *, contract: Contract) -> SaleResolution:
    version = await db.get(ProductVersion, contract.product_version_id) if contract.product_version_id else None
    return await resolve_sale(
        db, organization_id=contract.organization_id,
        seller_agent_id=await seller_for_contract(db, contract), version=version,
        sold_at=contract.sold_at or contract.created_at, sale_amount_cents=sale_amount_for(contract, version),
        lead_id=contract.lead_id,
    )


async def freeze_contract(db: AsyncSession, *, contract: Contract) -> SaleResolution:
    """Freeze chain, role, plan, amount and margin on the contract. Never
    raises: activation proceeds even with missing data, and the commission
    calculation then fails visibly with a reason instead of guessing."""
    res = await resolve_contract(db, contract=contract)
    seller_id = res.seller_agent_id
    if seller_id is not None:
        snapshot = await network_service.create_snapshot_for_contract(
            db, organization_id=contract.organization_id, producer_agent_id=seller_id, as_of=res.sold_at,
        )
        contract.network_snapshot_id = snapshot.id
    contract.sold_at = res.sold_at
    contract.sale_amount_cents = res.sale_amount_cents
    contract.reference_margin_cents = res.margin_cents
    contract.split_plan_id = res.plan.id if res.plan is not None else None
    contract.seller_role_code = res.seller_role.code if res.seller_role is not None else None
    await db.flush()
    return res


async def frozen_context(db: AsyncSession, *, contract: Contract) -> tuple[PlanSpec, SaleContext, SplitPlan]:
    """Engine context for the real calculation, from frozen data only."""
    if contract.network_snapshot_id is None:
        raise ValueError("Il contratto non ha la catena di rete congelata.")
    if contract.split_plan_id is None:
        raise ValueError("Nessuno Split Plan era valido per questa vendita alla sua data.")
    if contract.reference_margin_cents is None:
        raise ValueError("La vendita non ha un margine di riferimento.")
    plan = await db.get(SplitPlan, contract.split_plan_id)
    spec = await plans_service.plan_spec(db, plan=plan)

    snapshot = await db.get(NetworkSnapshot, contract.network_snapshot_id)
    at = (snapshot.as_of if snapshot is not None else None) or contract.sold_at or utcnow()
    rows = (
        await db.execute(
            select(NetworkSnapshotNode, AgentProfile.display_name, CommercialRole)
            .join(AgentProfile, AgentProfile.id == NetworkSnapshotNode.ancestor_agent_id)
            .join(CommercialRole, CommercialRole.id == NetworkSnapshotNode.commercial_role_id, isouter=True)
            .where(NetworkSnapshotNode.snapshot_id == contract.network_snapshot_id)
            .order_by(NetworkSnapshotNode.depth)
        )
    ).all()
    chain = [
        {
            "agent_id": node.ancestor_agent_id, "name": name, "depth": node.depth,
            # Legacy snapshots lack status; they only contained active members.
            "status": node.agent_status or "ACTIVE",
            "role_id": node.commercial_role_id, "role_code": node.role_code,
            "allows_delegation": bool(role.allows_delegation) if role else False,
        }
        for node, name, role in rows
    ]
    seller_role = await db.get(CommercialRole, chain[0]["role_id"]) if chain and chain[0]["role_id"] else None
    promoter = await _person(db, await _lead_promoter_id(db, contract.lead_id), at)
    influencer_id = (
        await commercial_service.delegation_influencer_at(db, delegate_agent_id=chain[0]["agent_id"], at=at)
        if chain else None
    )
    influencer = None
    if influencer_id is not None:
        influencer = next((m for m in chain if m["agent_id"] == influencer_id), None) or await _person(db, influencer_id, at)

    ctx = SaleContext(
        margin_cents=int(contract.reference_margin_cents),
        chain=tuple(_node(m) for m in chain),
        max_depth=seller_role.network_depth if seller_role is not None else None,
        delegation_influencer=_node(influencer) if influencer else None,
        promoter=_node(promoter, depth=-1) if promoter else None,
    )
    return spec, ctx, plan
