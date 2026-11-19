"""Licence register: who owns each licence, which company it was assigned to,
and what the resales earned.

Mamify sells the licence packages but does not know which company a
Digital Ambassador gives each licence to: that assignment lives only here.
An assignment is the existing resale operation (`service.create_resale`):
the licence is RESERVED for the company until the 500 € is paid, then RESOLD
with the 450 € owed to the seller. This module adds the register views, the
commercial margin and the resale paid on Mamify; it never changes the rules
of the plan.

Margin of a licence = what the seller is owed for the resale (450 €) minus
what the licence cost him (package price / licences; 0 for a gift licence).
"""

import uuid
from decimal import Decimal

from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.affiliate import engine, service
from app.modules.affiliate.models import (
    AffiliateClient,
    AffiliateCommission,
    AffiliateLicense,
    AffiliateOperation,
)
from app.modules.affiliate.service import AffiliateError
from app.modules.network.models import AgentProfile

#: Plan code a Mamify product is mapped to when the company buys the licence
#: itself on Mamify (the «Licenze» 500 € product).
RESALE_CODE = "LICENSE_RESALE"
STATUSES = ("AVAILABLE", "RESERVED", "RESOLD", "VOID")
LIVE_COMMISSION = ("PAYABLE", "PAID")


def _like(text: str) -> str:
    return "%" + text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


# --- Assignment ---------------------------------------------------------------


async def assign_license(
    db: AsyncSession, *, organization_id: uuid.UUID, agent_id: uuid.UUID, license_id: uuid.UUID,
    client_id: uuid.UUID | None, new_client: dict | None, actor_user_id: uuid.UUID | None,
    payment_method: str | None = None, note: str | None = None,
) -> AffiliateOperation:
    """Gives one of the agent's free licences to a company, an existing one
    or one typed in now. The licence stays reserved for that company until
    the 500 € is paid (confirmed by the office, or by the Mamify order)."""
    if client_id is None:
        if not new_client or not (new_client.get("company_name") or "").strip():
            raise AffiliateError("Scegli l'impresa a cui assegnare la licenza, o scrivi la ragione sociale di una nuova.")
        lic = await db.get(AffiliateLicense, license_id)
        if lic is None or lic.organization_id != organization_id or lic.owner_agent_id != agent_id:
            raise AffiliateError("Licenza non trovata tra quelle disponibili.")
        if lic.status != "AVAILABLE":
            raise AffiliateError("Questa licenza non è più disponibile.")
        client = await service.create_client(
            db, organization_id=organization_id, agent_id=agent_id, company_name=new_client.get("company_name") or "",
            vat_number=new_client.get("vat_number"), contact_name=new_client.get("contact_name"),
            email=new_client.get("email"), phone=new_client.get("phone"),
        )
        client_id = client.id
    return await service.create_resale(
        db, organization_id=organization_id, agent_id=agent_id, license_id=license_id, client_id=client_id,
        actor_user_id=actor_user_id, payment_method=payment_method, note=note,
    )


async def record_external_resale(
    db: AsyncSession, *, organization_id: uuid.UUID, seller_agent_id: uuid.UUID, client_id: uuid.UUID,
    idempotency_key: str, note: str | None = None,
) -> tuple[AffiliateOperation, bool]:
    """A company paid a licence on Mamify: the resale is already paid.

    The licence is the one the seller had already assigned to that company,
    if any (that pending assignment is closed and replaced); otherwise his
    oldest free licence. No free licence: refused, and the order is retried
    once the seller has one. The key is the order line's, so the same line
    read again returns the same resale."""
    existing = (await db.execute(select(AffiliateOperation).where(
        AffiliateOperation.organization_id == organization_id, AffiliateOperation.idempotency_key == idempotency_key,
    ))).scalar_one_or_none()
    if existing is not None:
        if existing.status == "PENDING":
            existing = await service.confirm_operation(db, organization_id=organization_id, operation_id=existing.id,
                                                       actor_user_id=None)
        return existing, False

    pending = (await db.execute(select(AffiliateOperation).where(
        AffiliateOperation.organization_id == organization_id, AffiliateOperation.kind == "LICENSE_RESALE",
        AffiliateOperation.status == "PENDING", AffiliateOperation.agent_id == seller_agent_id,
        AffiliateOperation.client_id == client_id,
    ).order_by(AffiliateOperation.created_at).limit(1).with_for_update())).scalar_one_or_none()
    if pending is not None:
        license_id = pending.license_id
        pending.status = "CANCELLED"
        lic = await db.get(AffiliateLicense, license_id, with_for_update=True)
        lic.status, lic.client_id = "AVAILABLE", None
        await service._audit(db, organization_id, None, "affiliate.operation.cancelled", "affiliate_operation",
                             pending.id, previous={"status": "PENDING"}, new={"status": "CANCELLED"},
                             reason=f"Assegnazione pagata su Mamify ({note or idempotency_key}).")
        await db.flush()
    else:
        license_id = await db.scalar(select(AffiliateLicense.id).where(
            AffiliateLicense.organization_id == organization_id, AffiliateLicense.owner_agent_id == seller_agent_id,
            AffiliateLicense.status == "AVAILABLE",
        ).order_by(AffiliateLicense.created_at, AffiliateLicense.code).limit(1))
        if license_id is None:
            seller = await db.get(AgentProfile, seller_agent_id)
            raise AffiliateError(
                f"{seller.display_name if seller else 'Il Digital Ambassador'} non ha licenze libere da assegnare "
                "all'impresa che ha pagato: l'ordine verrà riapplicato appena ne avrà una."
            )

    plan = await service.get_plan(db, organization_id)
    price = engine.money(plan.config["license_resale"]["price"])
    lic = await db.get(AffiliateLicense, license_id, with_for_update=True)
    op = AffiliateOperation(
        organization_id=organization_id, kind="LICENSE_RESALE", status="PENDING", agent_id=seller_agent_id,
        client_id=client_id, license_id=lic.id, product_code="LICENSE_RESALE", nominal_amount=price,
        paid_amount=price, bc_points=0, plan_version_id=plan.id, idempotency_key=idempotency_key,
        payment_method="MAMIFY", note=note,
    )
    await service._insert_operation(db, op)
    lic.status, lic.client_id = "RESERVED", client_id
    await db.commit()
    return await service.confirm_operation(db, organization_id=organization_id, operation_id=op.id,
                                           actor_user_id=None), True


# --- Register -----------------------------------------------------------------


def _register_filters(organization_id: uuid.UUID, agent_id: uuid.UUID | None, search: str | None,
                      origin: str | None) -> list:
    where = [AffiliateLicense.organization_id == organization_id]
    if agent_id:
        where.append(AffiliateLicense.owner_agent_id == agent_id)
    if origin in ("PURCHASE", "GIFT"):
        where.append(AffiliateLicense.origin == origin)
    text = (search or "").strip()
    if text:
        pattern = _like(text)
        where.append(or_(
            AffiliateLicense.code.ilike(pattern),
            AffiliateClient.company_name.ilike(pattern),
            AffiliateClient.vat_number.ilike(pattern),
            AgentProfile.display_name.ilike(pattern),
            AgentProfile.promoter_code.ilike(pattern),
        ))
    return where


def _register_query(*columns):
    return (select(*columns)
            .select_from(AffiliateLicense)
            .join(AgentProfile, AgentProfile.id == AffiliateLicense.owner_agent_id)
            .outerjoin(AffiliateClient, AffiliateClient.id == AffiliateLicense.client_id))


async def licenses_page(
    db: AsyncSession, organization_id: uuid.UUID, *, agent_id: uuid.UUID | None = None, page: int = 1,
    page_size: int = 25, status: str | None = None, search: str | None = None, origin: str | None = None,
) -> dict:
    """One page of the register, searched on the server: licence code, owner
    (name or code), company (name or VAT number). `counts` are per status
    with the same search, so the tabs show what each one holds."""
    page, page_size = max(1, page), min(max(1, page_size), 100)
    where = _register_filters(organization_id, agent_id, search, origin)
    counts = {s: 0 for s in STATUSES}
    for st, n in (await db.execute(
        _register_query(AffiliateLicense.status, func.count()).where(*where).group_by(AffiliateLicense.status)
    )).all():
        counts[st] = int(n)
    if status in STATUSES:
        where.append(AffiliateLicense.status == status)
    total = sum(counts.values()) if status not in STATUSES else counts[status]
    rows = (await db.execute(
        _register_query(AffiliateLicense, AgentProfile, AffiliateClient).where(*where)
        .order_by(AffiliateLicense.created_at.desc(), AffiliateLicense.code)
        .offset((page - 1) * page_size).limit(page_size)
    )).all()
    return {"total": total, "page": page, "page_size": page_size, "counts": counts,
            "items": await _describe(db, organization_id, rows)}


async def _describe(db: AsyncSession, organization_id: uuid.UUID, rows: list) -> list[dict]:
    licenses = [r[0] for r in rows]
    if not licenses:
        return []
    ids = [lic.id for lic in licenses]
    purchase_ids = {lic.purchase_operation_id for lic in licenses}
    purchases = {op.id: op for op in (await db.execute(
        select(AffiliateOperation).where(AffiliateOperation.id.in_(purchase_ids)))).scalars()}
    # The assignment of each licence: the live resale (pending or confirmed).
    resales: dict[uuid.UUID, AffiliateOperation] = {}
    for op in (await db.execute(select(AffiliateOperation).where(
        AffiliateOperation.organization_id == organization_id, AffiliateOperation.kind == "LICENSE_RESALE",
        AffiliateOperation.license_id.in_(ids), AffiliateOperation.status.in_(("PENDING", "CONFIRMED")),
    ).order_by(AffiliateOperation.created_at))).scalars():
        resales[op.license_id] = op
    owed = {op_id: amount for op_id, amount in (await db.execute(
        select(AffiliateCommission.operation_id, func.sum(AffiliateCommission.amount)).where(
            AffiliateCommission.kind == "RESALE", AffiliateCommission.status.in_(LIVE_COMMISSION),
            AffiliateCommission.operation_id.in_([op.id for op in resales.values()] or [uuid.uuid4()]),
        ).group_by(AffiliateCommission.operation_id))).all()}
    out = []
    for lic, owner, client in rows:
        purchase = purchases.get(lic.purchase_operation_id)
        resale = resales.get(lic.id)
        seller_amount = owed.get(resale.id) if resale is not None and resale.status == "CONFIRMED" else None
        out.append({
            "id": lic.id, "code": lic.code, "status": lic.status, "origin": lic.origin, "unit_cost": lic.unit_cost,
            "owner": service._agent_brief(owner),
            "client": client.company_name if client else None,
            "client_detail": {"id": client.id, "name": client.company_name, "vat_number": client.vat_number,
                              "email": client.email, "phone": client.phone,
                              "mamify_customer_id": client.mamify_customer_id} if client else None,
            "purchase": {"product_code": purchase.product_code if purchase else None,
                         "kind": purchase.kind if purchase else None,
                         "at": (purchase.confirmed_at or purchase.created_at) if purchase else lic.created_at,
                         "via_mamify": bool(purchase and purchase.payment_method == "MAMIFY")},
            "assignment": None if resale is None else {
                "operation_id": resale.id, "status": resale.status, "assigned_at": resale.created_at,
                "paid_at": resale.confirmed_at, "via_mamify": resale.payment_method == "MAMIFY",
                "note": resale.note,
            },
            "seller_amount": seller_amount,
            "margin": (seller_amount - lic.unit_cost) if seller_amount is not None else None,
            "resold_at": lic.resold_at, "created_at": lic.created_at,
            "purchase_operation_id": lic.purchase_operation_id, "resale_operation_id": lic.resale_operation_id,
        })
    return out


# --- Commercial margin ----------------------------------------------------------


async def agent_margins(db: AsyncSession, organization_id: uuid.UUID, agent_id: uuid.UUID) -> dict:
    """The agent's licences grouped by the purchase that gave them (a SMALL,
    a MEDIUM, a gift...): how many are free, assigned, resold; what they cost,
    what the resales earned, the margin made and the one still possible if
    every remaining licence is resold at the plan's price."""
    plan = await service.get_plan(db, organization_id)
    seller_amount = engine.money(plan.config["license_resale"]["seller_amount"])
    collected = (
        select(AffiliateCommission.operation_id.label("op_id"), func.sum(AffiliateCommission.amount).label("amount"))
        .where(AffiliateCommission.kind == "RESALE", AffiliateCommission.status.in_(LIVE_COMMISSION))
        .group_by(AffiliateCommission.operation_id).subquery()
    )
    resold = AffiliateLicense.status == "RESOLD"
    rows = (await db.execute(
        select(
            AffiliateLicense.purchase_operation_id, AffiliateLicense.origin,
            func.count(),
            func.sum(case((AffiliateLicense.status == "AVAILABLE", 1), else_=0)),
            func.sum(case((AffiliateLicense.status == "RESERVED", 1), else_=0)),
            func.sum(case((resold, 1), else_=0)),
            func.sum(AffiliateLicense.unit_cost),
            func.sum(case((resold, AffiliateLicense.unit_cost), else_=0)),
            func.coalesce(func.sum(collected.c.amount), 0),
        )
        .outerjoin(collected, collected.c.op_id == AffiliateLicense.resale_operation_id)
        .where(AffiliateLicense.organization_id == organization_id, AffiliateLicense.owner_agent_id == agent_id,
               AffiliateLicense.status != "VOID")
        .group_by(AffiliateLicense.purchase_operation_id, AffiliateLicense.origin)
    )).all()
    purchases = {op.id: op for op in (await db.execute(select(AffiliateOperation).where(
        AffiliateOperation.id.in_([r[0] for r in rows] or [uuid.uuid4()])))).scalars()}
    groups = []
    for purchase_id, origin, n, available, reserved, sold, cost, sold_cost, earned in rows:
        op = purchases.get(purchase_id)
        # What the package really cost: 1.600 € for 12 licences, not twelve
        # rounded 133,33 €.
        cost = Decimal(op.paid_amount) if op is not None else Decimal(cost or 0)
        sold_cost, earned = Decimal(sold_cost or 0), Decimal(earned or 0)
        groups.append({
            "purchase_operation_id": purchase_id, "origin": origin,
            "product_code": op.product_code if op else None,
            "purchased_at": (op.confirmed_at or op.created_at) if op else None,
            "via_mamify": bool(op and op.payment_method == "MAMIFY"),
            "licenses": int(n), "available": int(available or 0), "reserved": int(reserved or 0),
            "resold": int(sold or 0), "cost": cost, "collected": earned,
            "margin": earned - sold_cost,
            "potential_margin": seller_amount * int(n) - cost,
        })
    groups.sort(key=lambda g: g["purchased_at"] or 0, reverse=True)
    totals = {k: sum((g[k] for g in groups), Decimal("0") if k in ("cost", "collected", "margin", "potential_margin") else 0)
              for k in ("licenses", "available", "reserved", "resold", "cost", "collected", "margin", "potential_margin")}
    return {"seller_amount": seller_amount, "resale_price": engine.money(plan.config["license_resale"]["price"]),
            "totals": totals, "groups": groups}


async def margins_page(
    db: AsyncSession, organization_id: uuid.UUID, *, page: int = 1, page_size: int = 25, search: str | None = None,
) -> dict:
    """Office view: one row per Digital Ambassador who holds licences, the
    most licences first, searched by name or code."""
    page, page_size = max(1, page), min(max(1, page_size), 100)
    plan = await service.get_plan(db, organization_id)
    seller_amount = engine.money(plan.config["license_resale"]["seller_amount"])
    collected = (
        select(AffiliateCommission.operation_id.label("op_id"), func.sum(AffiliateCommission.amount).label("amount"))
        .where(AffiliateCommission.kind == "RESALE", AffiliateCommission.status.in_(LIVE_COMMISSION))
        .group_by(AffiliateCommission.operation_id).subquery()
    )
    where = [AffiliateLicense.organization_id == organization_id, AffiliateLicense.status != "VOID"]
    text = (search or "").strip()
    if text:
        pattern = _like(text)
        where.append(or_(AgentProfile.display_name.ilike(pattern), AgentProfile.promoter_code.ilike(pattern)))
    resold = AffiliateLicense.status == "RESOLD"
    n = func.count().label("n")
    base = (
        select(
            AgentProfile, n,
            func.sum(case((AffiliateLicense.status == "AVAILABLE", 1), else_=0)),
            func.sum(case((AffiliateLicense.status == "RESERVED", 1), else_=0)),
            func.sum(case((resold, 1), else_=0)),
            func.sum(AffiliateLicense.unit_cost),
            func.sum(case((resold, AffiliateLicense.unit_cost), else_=0)),
            func.coalesce(func.sum(collected.c.amount), 0),
        )
        .select_from(AffiliateLicense)
        .join(AgentProfile, AgentProfile.id == AffiliateLicense.owner_agent_id)
        .outerjoin(collected, collected.c.op_id == AffiliateLicense.resale_operation_id)
        .where(*where).group_by(AgentProfile.id)
    )
    total = await db.scalar(select(func.count()).select_from(base.subquery()))
    rows = (await db.execute(
        base.order_by(n.desc(), AgentProfile.display_name).offset((page - 1) * page_size).limit(page_size)
    )).all()
    # Cost = what each package really cost, summed once per purchase.
    paid: dict[uuid.UUID, Decimal] = {}
    if rows:
        for owner_id, _purchase, amount in (await db.execute(
            select(AffiliateLicense.owner_agent_id, AffiliateOperation.id, AffiliateOperation.paid_amount)
            .join(AffiliateOperation, AffiliateOperation.id == AffiliateLicense.purchase_operation_id)
            .where(AffiliateLicense.organization_id == organization_id, AffiliateLicense.status != "VOID",
                   AffiliateLicense.owner_agent_id.in_([r[0].id for r in rows]))
            .distinct()
        )).all():
            paid[owner_id] = paid.get(owner_id, Decimal("0")) + Decimal(amount or 0)
    items = []
    for agent, count, available, reserved, sold, cost, sold_cost, earned in rows:
        cost = paid.get(agent.id, Decimal(cost or 0))
        sold_cost, earned = Decimal(sold_cost or 0), Decimal(earned or 0)
        items.append({
            "agent": service._agent_brief(agent), "licenses": int(count), "available": int(available or 0),
            "reserved": int(reserved or 0), "resold": int(sold or 0), "cost": cost, "collected": earned,
            "margin": earned - sold_cost, "potential_margin": seller_amount * int(count) - cost,
        })
    return {"total": int(total or 0), "page": page, "page_size": page_size, "items": items}
