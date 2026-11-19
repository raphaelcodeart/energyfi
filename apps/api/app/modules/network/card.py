"""The collaborator card: everything about one member of the network in one
read, for the page opened from the network tree.

Identity and position (sponsors above, commercial role history,
delegations), the network below by level, sales made and generated, and
earnings: by state, by month, by type and by Split Plan. For each plan the
card lists the people whose sales paid this collaborator under it.

Read-only. Access rules are the router's (same as the branch views).
"""

import uuid
from collections import defaultdict
from datetime import datetime, timedelta

from sqlalchemy import func, select

from app.foundation.db import utcnow
from app.modules.catalog.models import ProductCategory, ProductVersion
from app.modules.commercial.models import CommercialRole, Delegation, SellerRoleHistory
from app.modules.commissions.models import CommissionMovement, Rank, SplitPlan
from app.modules.contracts.models import Contract, ContractAttribution
from app.modules.leads.models import Lead
from app.modules.network.models import AgentProfile, NetworkClosure
from app.modules.users.models import User
from app.modules.wallets.models import Wallet

#: Contract states counted as a closed sale.
SOLD_STATUSES = {"ACTIVE", "RENEWED", "SUSPENDED", "EXPIRED"}
#: Contract states still moving through the pipeline.
OPEN_STATUSES = {"SUBMITTED", "DOCUMENTS_PENDING", "UNDER_REVIEW", "APPROVED", "PAYMENT_PENDING", "PAID",
                 "ACTIVATION_PENDING"}
#: Movement states that still count toward what the collaborator earns.
EARNING_STATUSES = {"PENDING", "ACCRUED", "APPROVED", "PAYABLE", "PAID"}

MONTHS = 12


def _month_key(moment: datetime) -> str:
    return f"{moment.year:04d}-{moment.month:02d}"


def _last_months(now: datetime, count: int) -> list[str]:
    keys = []
    year, month = now.year, now.month
    for _ in range(count):
        keys.append(f"{year:04d}-{month:02d}")
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    return list(reversed(keys))


async def _names(db, ids: set[uuid.UUID]) -> dict[uuid.UUID, AgentProfile]:
    if not ids:
        return {}
    return {a.id: a for a in (await db.execute(select(AgentProfile).where(AgentProfile.id.in_(ids)))).scalars()}


async def get_agent_card(db, *, organization_id: uuid.UUID, agent_id: uuid.UUID, include_contact: bool) -> dict | None:
    agent = await db.get(AgentProfile, agent_id)
    if agent is None or agent.organization_id != organization_id:
        return None
    now = utcnow()

    role = await db.get(CommercialRole, agent.current_commercial_role_id) if agent.current_commercial_role_id else None
    rank = await db.get(Rank, agent.current_rank_id) if agent.current_rank_id else None
    user = await db.get(User, agent.user_id) if agent.user_id else None
    roles_by_id = {r.id: r for r in (await db.execute(
        select(CommercialRole).where(CommercialRole.organization_id == organization_id))).scalars()}

    # --- position: sponsors above, role history, delegations ---------------------
    ancestors = (await db.execute(
        select(NetworkClosure.ancestor_agent_id, NetworkClosure.depth).where(
            NetworkClosure.organization_id == organization_id,
            NetworkClosure.descendant_agent_id == agent_id,
            NetworkClosure.effective_to.is_(None),
            NetworkClosure.depth > 0,
        ).order_by(NetworkClosure.depth)
    )).all()
    ancestor_agents = await _names(db, {a for a, _ in ancestors})
    upline = [
        {
            "agent_id": a, "name": ancestor_agents[a].display_name, "depth": depth,
            "status": ancestor_agents[a].status,
            "role_name": roles_by_id[ancestor_agents[a].current_commercial_role_id].name
            if ancestor_agents[a].current_commercial_role_id in roles_by_id else None,
        }
        for a, depth in ancestors if a in ancestor_agents
    ]

    history = [
        {"role_name": roles_by_id[h.role_id].name if h.role_id in roles_by_id else "—",
         "valid_from": h.valid_from, "valid_to": h.valid_to, "reason": h.reason}
        for h in (await db.execute(
            select(SellerRoleHistory).where(SellerRoleHistory.agent_id == agent_id)
            .order_by(SellerRoleHistory.valid_from.desc())
        )).scalars()
    ]

    delegation_rows = list((await db.execute(select(Delegation).where(
        Delegation.organization_id == organization_id,
        (Delegation.influencer_agent_id == agent_id) | (Delegation.delegate_agent_id == agent_id),
    ))).scalars())
    others = await _names(db, {d.influencer_agent_id for d in delegation_rows} | {d.delegate_agent_id for d in delegation_rows})

    def _delegation(d: Delegation, other_id: uuid.UUID) -> dict:
        other = others.get(other_id)
        return {"agent_id": other_id, "name": other.display_name if other else "—", "valid_from": d.valid_from,
                "valid_to": d.valid_to, "active": d.valid_to is None or d.valid_to > now}

    delegations = {
        # People who sell on this collaborator's behalf.
        "delegates": [_delegation(d, d.delegate_agent_id) for d in delegation_rows if d.influencer_agent_id == agent_id],
        # Influencers this collaborator sells for.
        "represents": [_delegation(d, d.influencer_agent_id) for d in delegation_rows if d.delegate_agent_id == agent_id],
    }

    # --- the network below ------------------------------------------------------
    descendants = (await db.execute(
        select(NetworkClosure.descendant_agent_id, NetworkClosure.depth).where(
            NetworkClosure.organization_id == organization_id,
            NetworkClosure.ancestor_agent_id == agent_id,
            NetworkClosure.effective_to.is_(None),
            NetworkClosure.depth > 0,
        )
    )).all()
    below = await _names(db, {d for d, _ in descendants})
    levels: dict[int, dict] = defaultdict(lambda: {"people": 0, "active": 0})
    for d, depth in descendants:
        levels[depth]["people"] += 1
        if d in below and below[d].status == "ACTIVE":
            levels[depth]["active"] += 1
    joined = [below[d].joined_at for d, _ in descendants if d in below and below[d].joined_at]
    network = {
        "direct": levels[1]["people"] if 1 in levels else 0,
        "total": len(descendants),
        "active": sum(v["active"] for v in levels.values()),
        "levels": [{"depth": depth, **levels[depth]} for depth in sorted(levels)],
        "joined_last_30_days": sum(1 for j in joined if j >= now - timedelta(days=30)),
        "joined_last_90_days": sum(1 for j in joined if j >= now - timedelta(days=90)),
    }

    # --- sales: own and generated by the network ---------------------------------
    branch_ids = [agent_id] + [d for d, _ in descendants]
    sale_rows = (await db.execute(
        select(ContractAttribution.producer_agent_id, Contract.status, Contract.sale_amount_cents,
               Contract.gross_amount_cents, Contract.product_version_id, Contract.created_at)
        .join(Contract, Contract.contract_attribution_id == ContractAttribution.id)
        .where(ContractAttribution.organization_id == organization_id,
               ContractAttribution.producer_agent_id.in_(branch_ids))
    )).all()
    version_names = {v.id: v.name for v in (await db.execute(select(ProductVersion).where(
        ProductVersion.id.in_({r[4] for r in sale_rows if r[4]})))).scalars()} if sale_rows else {}

    def _value(row) -> int:
        return int(row[2] or row[3] or 0)

    own = [r for r in sale_rows if r[0] == agent_id]
    branch = [r for r in sale_rows if r[0] != agent_id]
    by_product: dict[str, dict] = defaultdict(lambda: {"contracts": 0, "value_cents": 0})
    for r in own:
        if r[1] in SOLD_STATUSES:
            entry = by_product[version_names.get(r[4], "Senza prodotto")]
            entry["contracts"] += 1
            entry["value_cents"] += _value(r)
    sales = {
        "own_total": len(own),
        "own_sold": sum(1 for r in own if r[1] in SOLD_STATUSES),
        "own_open": sum(1 for r in own if r[1] in OPEN_STATUSES),
        "own_lost": sum(1 for r in own if r[1] in ("REJECTED", "CANCELLED")),
        "own_value_cents": sum(_value(r) for r in own if r[1] in SOLD_STATUSES),
        "network_sold": sum(1 for r in branch if r[1] in SOLD_STATUSES),
        "network_value_cents": sum(_value(r) for r in branch if r[1] in SOLD_STATUSES),
        "by_product": sorted(
            ({"product": name, **values} for name, values in by_product.items()),
            key=lambda p: p["value_cents"], reverse=True,
        ),
    }

    # --- earnings -------------------------------------------------------------------
    movements = list((await db.execute(select(CommissionMovement).where(
        CommissionMovement.organization_id == organization_id,
        CommissionMovement.agent_id == agent_id,
        CommissionMovement.beneficiary_kind == "AGENT",
    ))).scalars())
    by_status: dict[str, int] = defaultdict(int)
    by_type: dict[str, int] = defaultdict(int)
    months = {key: 0 for key in _last_months(now, MONTHS)}
    earned = 0
    last_30 = 0
    for m in movements:
        by_status[m.status] += m.amount_cents
        if m.status not in EARNING_STATUSES:
            continue
        earned += m.amount_cents
        by_type[m.movement_type] += m.amount_cents
        key = _month_key(m.created_at)
        if key in months:
            months[key] += m.amount_cents
        if m.created_at >= now - timedelta(days=30):
            last_30 += m.amount_cents
    earnings = {
        "total_cents": earned,
        "last_30_days_cents": last_30,
        "pending_cents": by_status.get("PENDING", 0) + by_status.get("ACCRUED", 0),
        "approved_cents": by_status.get("APPROVED", 0),
        "payable_cents": by_status.get("PAYABLE", 0),
        "paid_cents": by_status.get("PAID", 0),
        "cancelled_cents": by_status.get("CANCELLED", 0),
        "by_type": [{"type": t, "cents": c} for t, c in sorted(by_type.items(), key=lambda i: -i[1])],
        "by_month": [{"month": k, "cents": v} for k, v in months.items()],
        "movements": len(movements),
    }

    # --- per Split Plan, with the people behind each amount ------------------------------
    plan_ids = {m.split_plan_id for m in movements if m.split_plan_id}
    plans_by_id = {p.id: p for p in (await db.execute(select(SplitPlan).where(SplitPlan.id.in_(plan_ids)))).scalars()} if plan_ids else {}
    categories = {c.id: c.name for c in (await db.execute(select(ProductCategory).where(
        ProductCategory.organization_id == organization_id))).scalars()}
    plan_products = {v.product_id: v.name for v in (await db.execute(select(ProductVersion).where(
        ProductVersion.product_id.in_({p.product_id for p in plans_by_id.values() if p.product_id}),
        ProductVersion.status == "ACTIVE",
    ))).scalars()} if plans_by_id else {}
    sellers = await _names(db, {m.source_seller_agent_id for m in movements if m.source_seller_agent_id})

    grouped: dict[uuid.UUID | None, list[CommissionMovement]] = defaultdict(list)
    for m in movements:
        if m.status in EARNING_STATUSES:
            grouped[m.split_plan_id].append(m)
    plans = []
    for plan_id, rows in grouped.items():
        plan = plans_by_id.get(plan_id)
        people: dict[uuid.UUID | None, dict] = {}
        for m in rows:
            seller_id = m.source_seller_agent_id
            entry = people.setdefault(seller_id, {
                "agent_id": seller_id,
                "name": "Vendita propria" if seller_id == agent_id
                else (sellers[seller_id].display_name if seller_id in sellers else "—"),
                "level": m.network_level, "via": m.beneficiary_type, "earned_cents": 0, "contracts": set(),
            })
            entry["earned_cents"] += m.amount_cents
            entry["contracts"].add(m.contract_id)
        scope = None
        if plan is not None:
            scope = plan_products.get(plan.product_id) if plan.product_id else categories.get(plan.category_id)
        plans.append({
            "plan_id": plan_id,
            "name": (plan.name if plan else None) or "Regole precedenti",
            "version": plan.version if plan else None,
            "status": plan.status if plan else "LEGACY",
            "scope": scope,
            "seller_role_name": roles_by_id[plan.seller_role_id].name
            if plan and plan.seller_role_id in roles_by_id else None,
            "earned_cents": sum(m.amount_cents for m in rows),
            "contracts": len({m.contract_id for m in rows}),
            "people": sorted(
                ({**p, "contracts": len(p["contracts"])} for p in people.values()),
                key=lambda p: -p["earned_cents"],
            ),
        })
    plans.sort(key=lambda p: -p["earned_cents"])

    # --- extras ------------------------------------------------------------------------
    wallet_cents = None
    if agent.user_id:
        wallet = (await db.execute(select(Wallet).where(Wallet.user_id == agent.user_id))).scalars().first()
        wallet_cents = wallet.balance_cents if wallet else 0
    lead_counts = dict((await db.execute(
        select(Lead.status, func.count()).where(Lead.promoter_agent_id == agent_id).group_by(Lead.status)
    )).all())

    return {
        "agent": {
            "id": agent.id, "display_name": agent.display_name, "promoter_code": agent.promoter_code,
            "status": agent.status, "joined_at": agent.joined_at, "photo_url": agent.photo_url,
            "role_name": role.name if role else None, "role_code": role.code if role else None,
            "rank_code": rank.code if rank else None, "rank_name": rank.name if rank else None,
            "email": user.email if (include_contact and user) else None,
            "has_login": user is not None,
        },
        "upline": upline,
        "role_history": history,
        "delegations": delegations,
        "network": network,
        "sales": sales,
        "earnings": earnings,
        "plans": plans,
        "wallet_cents": wallet_cents,
        "leads": {
            "total": sum(lead_counts.values()),
            "open": lead_counts.get("NEW", 0) + lead_counts.get("QUALIFIED", 0),
            "converted": lead_counts.get("CONVERTED", 0),
        },
    }


async def get_my_plans(db, *, organization_id: uuid.UUID, agent_id: uuid.UUID) -> dict:
    """The plans a collaborator works with: for every product they can sell
    today, what a sale would pay them, their network and the company (the same
    engine as real sales, via the simulator), grouped by Split Plan, next to
    what each plan has already paid them."""
    from app.modules.catalog.models import Product
    from app.modules.commissions.simulations.simulate import SimulationError, simulate_sale

    agent = await db.get(AgentProfile, agent_id)
    card = await get_agent_card(db, organization_id=organization_id, agent_id=agent_id, include_contact=False)
    categories = {c.id: c.name for c in (await db.execute(select(ProductCategory).where(
        ProductCategory.organization_id == organization_id))).scalars()}
    products = list((await db.execute(select(Product).where(
        Product.organization_id == organization_id, Product.category == "INTERNAL", Product.status == "ACTIVE",
    ).order_by(Product.code))).scalars())
    from app.modules.catalog.models import Company

    companies = {c.id: c for c in (await db.execute(select(Company).where(
        Company.organization_id == organization_id))).scalars()}

    now = utcnow()
    plans: dict[str, dict] = {}
    unavailable = []
    # A collaborator whose role cannot close sales earns through referrals: the
    # sale is simulated as closed by the nearest sponsor who can, with them as
    # the referring promoter.
    role = await db.get(CommercialRole, agent.current_commercial_role_id) if agent and agent.current_commercial_role_id else None
    refers_only = role is not None and not role.can_close_sales
    closers: list[uuid.UUID] = []
    if refers_only:
        ancestors = (await db.execute(
            select(NetworkClosure.ancestor_agent_id).where(
                NetworkClosure.organization_id == organization_id,
                NetworkClosure.descendant_agent_id == agent_id,
                NetworkClosure.effective_to.is_(None),
                NetworkClosure.depth > 0,
            ).order_by(NetworkClosure.depth)
        )).scalars().all()
        closers = list(ancestors)

    for product in products:
        sim = None
        try:
            if refers_only:
                for closer in closers:
                    attempt = await simulate_sale(db, organization_id=organization_id, seller_agent_id=closer,
                                                  product_id=product.id, sold_at=now, promoter_agent_id=agent_id)
                    if not attempt["errors"]:
                        sim = attempt
                        break
                if sim is None:
                    unavailable.append({"product": product.code, "reason": "Nessuno sopra di te può chiudere questa vendita."})
                    continue
            else:
                sim = await simulate_sale(db, organization_id=organization_id, seller_agent_id=agent_id,
                                          product_id=product.id, sold_at=now)
        except SimulationError as exc:
            unavailable.append({"product": product.code, "reason": str(exc)})
            continue
        if sim["errors"] or not sim["plan"]:
            unavailable.append({"product": sim["product_name"], "reason": "; ".join(sim["errors"]) or "Nessun piano"})
            continue
        mine = sum(r["total_cents"] for r in sim["rows"] if r["agent_id"] and str(r["agent_id"]) == str(agent_id))
        plan = sim["plan"]
        entry = plans.setdefault(plan["id"], {"plan": plan, "products": [], "distribution": []})
        entry["products"].append({
            "product_id": product.id,
            "name": sim["product_name"],
            "category": categories.get(product.commercial_category_id),
            "company_id": product.company_id,
            "image_url": (await db.execute(select(ProductVersion.image_url).where(
                ProductVersion.product_id == product.id, ProductVersion.status == "ACTIVE"))).scalars().first(),
            "price_cents": sim["sale_amount_cents"],
            "margin_cents": sim["reference_margin_cents"],
            "mine_cents": mine,
            "network_cents": sim["agents_cents"] - mine,
            "company_cents": sim["company_cents"],
        })
        if not entry["distribution"]:
            entry["distribution"] = [
                {"who": r["role"], "name": r["name"], "is_me": bool(r["agent_id"]) and str(r["agent_id"]) == str(agent_id),
                 "cents": r["total_cents"], "calculation": r["calculation_type"], "value": r["calculation_value"]}
                for r in sim["rows"]
            ]

    from app.modules.catalog.models import CompanyMembership

    joined = {m.company_id: m.joined_at for m in (await db.execute(select(CompanyMembership).where(
        CompanyMembership.agent_id == agent_id, CompanyMembership.left_at.is_(None)))).scalars()}
    earned = {str(p["plan_id"]): p for p in (card or {}).get("plans", [])}
    result = []
    for plan_id, entry in plans.items():
        history = earned.pop(plan_id, None)
        result.append({
            **entry,
            "earned_cents": history["earned_cents"] if history else 0,
            "contracts": history["contracts"] if history else 0,
            "people": history["people"][:6] if history else [],
        })
    # Plans that paid them in the past but no longer apply to what they sell today.
    past = [p for p in earned.values()]
    result.sort(key=lambda p: -max((x["mine_cents"] for x in p["products"]), default=0))
    return {
        "agent_id": agent_id,
        "role_name": card["agent"]["role_name"] if card else None,
        "refers_only": refers_only,
        "agent_name": agent.display_name if agent else None,
        "plans": result,
        "past_plans": past,
        "unavailable": unavailable,
        "earnings": card["earnings"] if card else None,
        "companies": [
            {"id": c.id, "name": c.name, "description": c.description, "logo_url": c.logo_url,
             "max_network_depth": c.max_network_depth, "joined_at": joined.get(c.id)}
            for c in sorted(companies.values(), key=lambda c: c.name) if c.is_active
        ],
    }


async def get_product_network(
    db, *, organization_id: uuid.UUID, agent_id: uuid.UUID, product_id: uuid.UUID
) -> dict | None:
    """A collaborator's network seen through one product: only the people who
    bought it, down to the depth the product's company reaches.

    The global network is untouched; this is a filter on it. Buyers are the
    customers with a contract in force for the product, placed under the
    collaborator who referred them (one level below), and collaborators who
    bought it for themselves, placed on their own node. The branches leading
    to them are kept so the tree stays connected."""
    from app.modules.catalog.models import Company, Product
    from app.modules.customers.models import Company as CustomerCompany
    from app.modules.customers.models import Customer, CustomerProfile
    from app.modules.network.models import NetworkNode

    product = await db.get(Product, product_id)
    root = await db.get(AgentProfile, agent_id)
    if product is None or product.organization_id != organization_id or root is None:
        return None
    company = await db.get(Company, product.company_id) if product.company_id else None
    limit = company.max_network_depth if company and company.max_network_depth else 12
    version = (await db.execute(select(ProductVersion).where(
        ProductVersion.product_id == product_id, ProductVersion.status == "ACTIVE"))).scalars().first()

    below = dict((await db.execute(
        select(NetworkClosure.descendant_agent_id, NetworkClosure.depth).where(
            NetworkClosure.organization_id == organization_id,
            NetworkClosure.ancestor_agent_id == agent_id,
            NetworkClosure.effective_to.is_(None),
            NetworkClosure.depth <= limit,
        )
    )).all())
    agents = await _names(db, set(below))
    agent_by_user = {a.user_id: a.id for a in agents.values() if a.user_id}

    rows = (await db.execute(
        select(Contract.id, Contract.customer_id, Contract.status, Contract.sale_amount_cents, Contract.gross_amount_cents,
               Contract.activated_at, ContractAttribution.attributed_promoter_id, ContractAttribution.producer_agent_id)
        .join(ContractAttribution, ContractAttribution.id == Contract.contract_attribution_id)
        .join(ProductVersion, ProductVersion.id == Contract.product_version_id)
        .where(Contract.organization_id == organization_id, ProductVersion.product_id == product_id)
    )).all()
    customers = {c.id: c for c in (await db.execute(select(Customer).where(
        Customer.id.in_({r[1] for r in rows})))).scalars()} if rows else {}
    profiles = {p.customer_id: p for p in (await db.execute(select(CustomerProfile).where(
        CustomerProfile.customer_id.in_(customers)))).scalars()} if customers else {}
    firms = {f.customer_id: f for f in (await db.execute(select(CustomerCompany).where(
        CustomerCompany.customer_id.in_(customers)))).scalars()} if customers else {}

    def customer_name(customer_id) -> str:
        if customer_id in firms:
            return firms[customer_id].company_name
        profile = profiles.get(customer_id)
        return f"{profile.first_name} {profile.last_name}".strip() if profile else "Cliente"

    # buyer key -> details; agents who bought are keyed by agent id.
    buyers: dict[str, dict] = {}
    in_progress = 0
    for contract_id, customer_id, status, sale, gross, activated, attributed, producer in rows:
        customer = customers.get(customer_id)
        buyer_agent = agent_by_user.get(customer.user_id) if customer and customer.user_id else None
        host = buyer_agent or attributed
        if host not in below:
            continue
        depth = below[host] + (0 if buyer_agent else 1)
        if depth > limit:
            continue
        if status in OPEN_STATUSES:
            in_progress += 1
            continue
        if status not in SOLD_STATUSES:
            continue
        key = str(buyer_agent) if buyer_agent else f"c:{customer_id}"
        entry = buyers.setdefault(key, {
            "key": key, "host": host, "depth": depth, "is_agent": bool(buyer_agent),
            "name": agents[buyer_agent].display_name if buyer_agent else customer_name(customer_id),
            "contracts": 0, "value_cents": 0, "since": activated,
        })
        entry["contracts"] += 1
        entry["value_cents"] += int(sale or gross or 0)
        if activated and (entry["since"] is None or activated < entry["since"]):
            entry["since"] = activated

    # Keep the agents on the way from the root to every buyer.
    parents = dict((await db.execute(select(NetworkNode.agent_id, NetworkNode.direct_parent_agent_id).where(
        NetworkNode.agent_id.in_(below), NetworkNode.effective_to.is_(None)))).all()) if below else {}
    keep: set[uuid.UUID] = {agent_id}
    for buyer in buyers.values():
        node = buyer["host"]
        while node is not None and node in below and node not in keep:
            keep.add(node)
            node = parents.get(node)

    roles = {r.id: r.name for r in (await db.execute(select(CommercialRole).where(
        CommercialRole.organization_id == organization_id))).scalars()}

    def agent_node(aid: uuid.UUID) -> dict:
        agent = agents[aid]
        bought = buyers.get(str(aid))
        return {
            "agent_id": str(aid), "depth": below[aid], "display_name": agent.display_name,
            "promoter_code": agent.promoter_code, "status": agent.status,
            "role_label": ("Ha acquistato · " if bought else "") + (roles.get(agent.current_commercial_role_id) or "Collaboratore"),
            "bought": bool(bought), "children": [],
        }

    nodes = {aid: agent_node(aid) for aid in keep if aid in agents}
    for aid in keep:
        parent = parents.get(aid)
        if aid != agent_id and parent in nodes:
            nodes[parent]["children"].append(nodes[aid])
    for buyer in buyers.values():
        if buyer["is_agent"]:
            continue
        nodes[buyer["host"]]["children"].append({
            "agent_id": buyer["key"], "depth": buyer["depth"], "display_name": buyer["name"],
            "promoter_code": f"{buyer['contracts']} contr.", "status": "ACTIVE",
            "role_label": "Cliente · ha acquistato", "bought": True, "children": [],
        })

    levels: dict[int, dict] = defaultdict(lambda: {"buyers": 0, "contracts": 0, "value_cents": 0})
    for buyer in buyers.values():
        level = levels[buyer["depth"]]
        level["buyers"] += 1
        level["contracts"] += buyer["contracts"]
        level["value_cents"] += buyer["value_cents"]

    earned = (await db.execute(select(func.coalesce(func.sum(CommissionMovement.amount_cents), 0)).where(
        CommissionMovement.organization_id == organization_id, CommissionMovement.agent_id == agent_id,
        CommissionMovement.product_id == product_id,
        CommissionMovement.status.in_(EARNING_STATUSES),
    ))).scalar_one()

    return {
        "product": {"id": product.id, "name": version.name if version else product.code, "image_url": version.image_url if version else None},
        "company": {"id": company.id, "name": company.name, "max_network_depth": company.max_network_depth} if company else None,
        "depth_limit": limit,
        "tree": nodes.get(agent_id),
        "levels": [{"depth": d, **levels[d]} for d in sorted(levels)],
        "buyers": sorted(
            ({k: v for k, v in b.items() if k != "host"} for b in buyers.values()),
            key=lambda b: (b["depth"], b["name"]),
        ),
        "totals": {
            "buyers": len(buyers),
            "contracts": sum(b["contracts"] for b in buyers.values()),
            "value_cents": sum(b["value_cents"] for b in buyers.values()),
            "in_progress": in_progress,
            "network_people_in_reach": sum(1 for d in below.values() if d > 0),
        },
        "earned_cents": int(earned),
    }


# --- Companies a collaborator works with ------------------------------------------


async def _company_products(db, organization_id: uuid.UUID) -> dict[uuid.UUID, list]:
    from app.modules.catalog.models import Product

    rows = (await db.execute(
        select(Product, ProductVersion).join(ProductVersion, ProductVersion.product_id == Product.id)
        .where(Product.organization_id == organization_id, Product.company_id.is_not(None),
               Product.status == "ACTIVE", ProductVersion.status == "ACTIVE")
    )).all()
    grouped: dict[uuid.UUID, list] = defaultdict(list)
    for product, version in rows:
        grouped[product.company_id].append({"id": product.id, "name": version.name, "image_url": version.image_url})
    return grouped


async def get_my_companies(db, *, organization_id: uuid.UUID, agent_id: uuid.UUID) -> list[dict]:
    """Every active company with products, whether this collaborator takes
    part in it, and their results with its products: what they earned, what
    they sold and how many people in their network bought, within the
    company's depth."""
    from app.modules.catalog.models import Company, CompanyMembership

    companies = (await db.execute(select(Company).where(
        Company.organization_id == organization_id, Company.is_active.is_(True)).order_by(Company.name))).scalars().all()
    products_by_company = await _company_products(db, organization_id)
    memberships = {m.company_id: m for m in (await db.execute(select(CompanyMembership).where(
        CompanyMembership.agent_id == agent_id, CompanyMembership.left_at.is_(None)))).scalars()}
    below = dict((await db.execute(select(NetworkClosure.descendant_agent_id, NetworkClosure.depth).where(
        NetworkClosure.organization_id == organization_id, NetworkClosure.ancestor_agent_id == agent_id,
        NetworkClosure.effective_to.is_(None)))).all())

    result = []
    for company in companies:
        products = products_by_company.get(company.id, [])
        if not products:
            continue
        product_ids = [p["id"] for p in products]
        limit = company.max_network_depth or 12
        earned = (await db.execute(select(func.coalesce(func.sum(CommissionMovement.amount_cents), 0)).where(
            CommissionMovement.agent_id == agent_id, CommissionMovement.product_id.in_(product_ids),
            CommissionMovement.status.in_(EARNING_STATUSES)))).scalar_one()
        sales = (await db.execute(
            select(ContractAttribution.producer_agent_id, ContractAttribution.attributed_promoter_id, Contract.customer_id)
            .join(Contract, Contract.contract_attribution_id == ContractAttribution.id)
            .join(ProductVersion, ProductVersion.id == Contract.product_version_id)
            .where(ProductVersion.product_id.in_(product_ids), Contract.status.in_(SOLD_STATUSES))
        )).all()
        own_sales = sum(1 for producer, _a, _c in sales if producer == agent_id)
        buyers = {customer for _p, attributed, customer in sales
                  if attributed in below and below[attributed] + 1 <= limit}
        membership = memberships.get(company.id)
        result.append({
            "id": company.id, "name": company.name, "description": company.description,
            "logo_url": company.logo_url, "max_network_depth": company.max_network_depth,
            "joined_at": membership.joined_at if membership else None,
            "products": products,
            "earned_cents": int(earned),
            "own_sales": own_sales,
            "network_buyers": len(buyers),
        })
    return result


async def set_membership(db, *, organization_id: uuid.UUID, agent_id: uuid.UUID, company_id: uuid.UUID, join: bool) -> None:
    """Join (idempotent) or leave a company's plans. Commits."""
    from app.modules.audit import service as audit_service
    from app.modules.catalog.models import Company, CompanyMembership

    company = await db.get(Company, company_id)
    if company is None or company.organization_id != organization_id or not company.is_active:
        raise LookupError("Azienda non trovata.")
    current = (await db.execute(select(CompanyMembership).where(
        CompanyMembership.company_id == company_id, CompanyMembership.agent_id == agent_id,
        CompanyMembership.left_at.is_(None)))).scalars().first()
    now = utcnow()
    if join and current is None:
        db.add(CompanyMembership(organization_id=organization_id, company_id=company_id, agent_id=agent_id, joined_at=now))
    elif not join and current is not None:
        current.left_at = now
    else:
        return
    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=None,
        action="company.member_joined" if join else "company.member_left", entity_type="company",
        entity_id=str(company_id), new_value={"agent_id": str(agent_id)},
    )
    await db.commit()


async def get_company_participants(db, *, organization_id: uuid.UUID, company_id: uuid.UUID) -> dict | None:
    """Who takes part in a company's plans: the collaborators who joined, the
    ones who sell its products without having joined, and the customers
    with a contract in force on them."""
    from app.modules.catalog.models import Company, CompanyMembership, Product
    from app.modules.customers.models import Company as CustomerCompany
    from app.modules.customers.models import Customer, CustomerProfile

    company = await db.get(Company, company_id)
    if company is None or company.organization_id != organization_id:
        return None
    product_ids = list((await db.execute(select(Product.id).where(Product.company_id == company_id))).scalars())
    rows = (await db.execute(
        select(Contract.customer_id, Contract.status, Contract.sale_amount_cents, Contract.gross_amount_cents,
               Contract.activated_at, ContractAttribution.producer_agent_id, ProductVersion.name)
        .join(ContractAttribution, ContractAttribution.id == Contract.contract_attribution_id)
        .join(ProductVersion, ProductVersion.id == Contract.product_version_id)
        .where(ProductVersion.product_id.in_(product_ids), Contract.status.in_(SOLD_STATUSES))
    )).all() if product_ids else []
    members = list((await db.execute(select(CompanyMembership).where(
        CompanyMembership.company_id == company_id).order_by(CompanyMembership.joined_at))).scalars())

    sellers: dict[uuid.UUID, dict] = defaultdict(lambda: {"contracts": 0, "value_cents": 0})
    for customer_id, _s, sale, gross, _a, producer, _n in rows:
        sellers[producer]["contracts"] += 1
        sellers[producer]["value_cents"] += int(sale or gross or 0)
    agents = await _names(db, {m.agent_id for m in members} | set(sellers))
    roles = {r.id: r.name for r in (await db.execute(select(CommercialRole).where(
        CommercialRole.organization_id == organization_id))).scalars()}

    def agent_row(aid: uuid.UUID, membership) -> dict:
        agent = agents.get(aid)
        return {
            "agent_id": aid, "name": agent.display_name if agent else "—",
            "promoter_code": agent.promoter_code if agent else None,
            "role_name": roles.get(agent.current_commercial_role_id) if agent else None,
            "joined_at": membership.joined_at if membership else None,
            "left_at": membership.left_at if membership else None,
            **sellers.get(aid, {"contracts": 0, "value_cents": 0}),
        }

    open_members = {m.agent_id: m for m in members if m.left_at is None}
    customers_by_id = {c.id: c for c in (await db.execute(select(Customer).where(
        Customer.id.in_({r[0] for r in rows})))).scalars()} if rows else {}
    profiles = {p.customer_id: p for p in (await db.execute(select(CustomerProfile).where(
        CustomerProfile.customer_id.in_(customers_by_id)))).scalars()} if customers_by_id else {}
    firms = {f.customer_id: f.company_name for f in (await db.execute(select(CustomerCompany).where(
        CustomerCompany.customer_id.in_(customers_by_id)))).scalars()} if customers_by_id else {}
    customers: dict[uuid.UUID, dict] = {}
    for customer_id, _s, sale, gross, activated, producer, product_name in rows:
        profile = profiles.get(customer_id)
        entry = customers.setdefault(customer_id, {
            "customer_id": customer_id,
            "name": firms.get(customer_id) or (f"{profile.first_name} {profile.last_name}".strip() if profile else "Cliente"),
            "products": [], "value_cents": 0, "since": activated,
            "seller": agents[producer].display_name if producer in agents else "—",
        })
        if product_name not in entry["products"]:
            entry["products"].append(product_name)
        entry["value_cents"] += int(sale or gross or 0)
        if activated and (entry["since"] is None or activated < entry["since"]):
            entry["since"] = activated

    return {
        "company": {"id": company.id, "name": company.name, "max_network_depth": company.max_network_depth},
        "members": [agent_row(aid, m) for aid, m in open_members.items()],
        "former_members": [agent_row(m.agent_id, m) for m in members if m.left_at is not None],
        "sellers_not_members": [agent_row(aid, None) for aid in sellers if aid not in open_members],
        "customers": sorted(customers.values(), key=lambda c: c["name"]),
    }
