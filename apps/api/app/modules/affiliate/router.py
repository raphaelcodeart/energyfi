"""SOS Affiliate API.

`/affiliate/me/*` is the Digital Ambassador area: the affiliate is always
the one tied to the session, never an id from the request. `/affiliate/admin/*`
reuses the existing permissions: reading needs commissions.read_branch,
confirming money needs payments.manage, closing months and corrections need
commissions.approve, payouts need commissions.pay.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.foundation.db import get_db
from app.foundation.deps import CurrentUser, get_current_user, require_permission
from app.foundation.rate_limit import rate_limit
from app.modules.affiliate import licenses, service, tree
from app.modules.affiliate.plan import PlanValidationError, product_index
from app.modules.affiliate.schemas import (
    AdminPurchaseCreate,
    ClientCreate,
    CommissionPayout,
    LicenseAssign,
    OperationDecision,
    PackSaleCreate,
    PlanVersionCreate,
    PurchaseCreate,
    ResaleCreate,
    SubscriptionStatusUpdate,
    TopupCreate,
)

router = APIRouter(prefix="/affiliate", tags=["affiliate"])


def _out(value: Any) -> Any:
    """Decimals leave as strings ("12.50"): a float would lose cents on the
    way to the browser (INT-06)."""
    if isinstance(value, Decimal):
        return f"{value:.2f}" if value == value.quantize(Decimal("0.01")) else str(value)
    if isinstance(value, dict):
        return {str(k): _out(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_out(v) for v in value]
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    return value


def _uuid(value: str, label: str = "identificativo") -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"{label.capitalize()} non valido.") from exc


def _bad(exc: Exception) -> HTTPException:
    return HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


async def _me(db: AsyncSession, user: CurrentUser):
    try:
        return await service.agent_for_user(db, user.organization_id, user.user_id)
    except service.AffiliateError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


def _operation(op) -> dict:
    return _out({
        "id": op.id, "kind": op.kind, "status": op.status, "product_code": op.product_code, "quantity": op.quantity,
        "period": op.period, "paid_amount": op.paid_amount, "bc_points": op.bc_points,
    })


# --- Catalogue ---------------------------------------------------------------


@router.get("/catalog")
async def get_catalog(
    current_user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> dict:
    from app.modules.mamify.models import MamifyConfig

    plan = await service.get_plan(db, current_user.organization_id)
    await db.commit()
    external = await db.scalar(select(MamifyConfig.enabled).where(MamifyConfig.organization_id == current_user.organization_id))
    return _out({"plan_version": {"id": plan.id, "label": plan.label, "valid_from": plan.valid_from},
                 "config": plan.config, "external_shop": bool(external)})


# --- Digital Ambassador area -------------------------------------------------


@router.get("/me")
async def my_summary(current_user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> dict:
    agent = await _me(db, current_user)
    summary = await service.affiliate_summary(db, current_user.organization_id, agent.id)
    await db.commit()
    # Their own Mamify purchases, re-read in the background (read only); the
    # page asks again a little later when a read was queued.
    try:
        from app.modules.mamify import service as mamify_service

        summary["orders_check"] = "queued" if await mamify_service.request_own_orders(
            db, current_user.organization_id, agent.id) else "recent"
    except Exception:  # noqa: BLE001 - the summary never fails for this
        await db.rollback()
        summary["orders_check"] = "unavailable"
    return _out(summary)


@router.get("/me/mamify-orders")
async def my_mamify_orders(current_user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> list:
    """One's own purchases on Mamify (as last read, read only) and what they gave."""
    from app.modules.mamify import service as mamify_service

    agent = await _me(db, current_user)
    return _out(await mamify_service.list_own_orders(db, current_user.organization_id, agent.id))


@router.get("/me/network")
async def my_network(current_user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> list:
    agent = await _me(db, current_user)
    return _out(await service.network_tree(db, current_user.organization_id, agent.id))


@router.get("/me/network/branch")
async def my_network_branch(
    root: str | None = None, offset: int = 0, limit: int = tree.PAGE, sort: str = "size", active: bool = False,
    current_user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db),
) -> dict:
    """One branch of the viewer's own tree; nobody above them is ever shown."""
    agent = await _me(db, current_user)
    snap = await tree.snapshot(db, current_user.organization_id)
    node = _uuid(root) if root else agent.id
    if not snap.within(node, agent.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Persona non trovata nella tua rete.")
    out = tree.branch(snap, node, offset=offset, limit=limit, sort=sort, active_only=active, scope=agent.id)
    out["summary"] = tree.summary(snap, node)
    out["scope"] = agent.id
    return _out(out)


@router.get("/me/network/galaxy")
async def my_network_galaxy(current_user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> dict:
    """The viewer's whole branch in one answer, for the virtual tour (only
    for a Digital Ambassador's own branch: there is no admin version)."""
    agent = await _me(db, current_user)
    snap = await tree.snapshot(db, current_user.organization_id)
    if agent.id not in snap.nodes:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Non sei ancora nella rete.")
    return tree.galaxy(snap, agent.id)


@router.get("/me/network/search")
async def my_network_search(q: str, current_user: CurrentUser = Depends(get_current_user),
                            db: AsyncSession = Depends(get_db)) -> dict:
    agent = await _me(db, current_user)
    snap = await tree.snapshot(db, current_user.organization_id)
    return _out(tree.search(snap, q, scope=agent.id))


@router.get("/me/operations")
async def my_operations(current_user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> list:
    agent = await _me(db, current_user)
    return _out(await service.list_operations(db, current_user.organization_id, agent_id=agent.id))


@router.get("/me/commissions")
async def my_commissions(
    kind: str | None = None, current_user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list:
    agent = await _me(db, current_user)
    return _out(await service.list_commissions(db, current_user.organization_id, agent_id=agent.id, kind=kind))


@router.get("/me/licenses")
async def my_licenses(current_user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> list:
    agent = await _me(db, current_user)
    return _out(await service.list_licenses(db, current_user.organization_id, agent_id=agent.id))


@router.get("/me/licenses/page")
async def my_licenses_page(
    page: int = 1, page_size: int = 25, status_filter: str | None = None, search: str | None = None,
    origin: str | None = None,
    current_user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db),
) -> dict:
    agent = await _me(db, current_user)
    return _out(await licenses.licenses_page(db, current_user.organization_id, agent_id=agent.id, page=page,
                                             page_size=page_size, status=status_filter, search=search, origin=origin))


@router.get("/me/licenses/margins")
async def my_license_margins(
    current_user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> dict:
    agent = await _me(db, current_user)
    result = await licenses.agent_margins(db, current_user.organization_id, agent.id)
    await db.commit()
    return _out(result)


@router.post("/me/licenses/assign", status_code=status.HTTP_201_CREATED)
async def assign_my_license(
    payload: LicenseAssign,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(rate_limit("affiliate-resale", max_requests=30, window_seconds=60)),
) -> dict:
    agent = await _me(db, current_user)
    try:
        op = await licenses.assign_license(
            db, organization_id=current_user.organization_id, agent_id=agent.id,
            license_id=_uuid(payload.license_id, "licenza"),
            client_id=_uuid(payload.client_id, "cliente") if payload.client_id else None,
            new_client=payload.new_client.model_dump() if payload.new_client else None,
            actor_user_id=current_user.user_id, payment_method=payload.payment_method, note=payload.note,
        )
    except service.AffiliateError as exc:
        raise _bad(exc) from exc
    return _operation(op)


@router.get("/me/clients")
async def my_clients(current_user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> list:
    agent = await _me(db, current_user)
    clients = await service.list_clients(db, current_user.organization_id, agent.id)
    return _out([{"id": c.id, "company_name": c.company_name, "vat_number": c.vat_number, "contact_name": c.contact_name,
                  "email": c.email, "phone": c.phone, "mamicash_balance": c.mamicash_balance, "created_at": c.created_at}
                 for c in clients])


@router.post("/me/clients", status_code=status.HTTP_201_CREATED)
async def create_my_client(
    payload: ClientCreate, current_user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> dict:
    agent = await _me(db, current_user)
    try:
        client = await service.create_client(db, organization_id=current_user.organization_id, agent_id=agent.id,
                                             **payload.model_dump())
    except service.AffiliateError as exc:
        raise _bad(exc) from exc
    return _out({"id": client.id, "company_name": client.company_name})


@router.post("/me/purchases", status_code=status.HTTP_201_CREATED)
async def create_my_purchase(
    payload: PurchaseCreate,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(rate_limit("affiliate-purchase", max_requests=20, window_seconds=60)),
) -> dict:
    agent = await _me(db, current_user)
    try:
        op = await service.create_purchase(db, organization_id=current_user.organization_id, agent_id=agent.id,
                                           actor_user_id=current_user.user_id, **payload.model_dump())
    except (service.AffiliateError, ValueError) as exc:
        raise _bad(exc) from exc
    return _operation(op)


@router.post("/me/pack-sales", status_code=status.HTTP_201_CREATED)
async def create_my_pack_sale(
    payload: PackSaleCreate,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(rate_limit("affiliate-pack-sale", max_requests=20, window_seconds=60)),
) -> dict:
    agent = await _me(db, current_user)
    try:
        op = await service.create_pack_sale(
            db, organization_id=current_user.organization_id, agent_id=agent.id,
            client_id=_uuid(payload.client_id, "cliente"), pack_code=payload.pack_code,
            actor_user_id=current_user.user_id, payment_method=payload.payment_method, note=payload.note,
        )
    except service.AffiliateError as exc:
        raise _bad(exc) from exc
    return _operation(op)


@router.post("/me/topups", status_code=status.HTTP_201_CREATED)
async def create_my_topup(
    payload: TopupCreate,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(rate_limit("affiliate-topup", max_requests=20, window_seconds=60)),
) -> dict:
    agent = await _me(db, current_user)
    try:
        op = await service.create_topup(
            db, organization_id=current_user.organization_id, agent_id=agent.id,
            client_id=_uuid(payload.client_id, "cliente"), amount=payload.amount,
            actor_user_id=current_user.user_id, payment_method=payload.payment_method, note=payload.note,
        )
    except service.AffiliateError as exc:
        raise _bad(exc) from exc
    return _operation(op)


@router.post("/me/resales", status_code=status.HTTP_201_CREATED)
async def create_my_resale(
    payload: ResaleCreate,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(rate_limit("affiliate-resale", max_requests=30, window_seconds=60)),
) -> dict:
    agent = await _me(db, current_user)
    try:
        op = await service.create_resale(
            db, organization_id=current_user.organization_id, agent_id=agent.id,
            license_id=_uuid(payload.license_id, "licenza"), client_id=_uuid(payload.client_id, "cliente"),
            actor_user_id=current_user.user_id, payment_method=payload.payment_method, note=payload.note,
        )
    except service.AffiliateError as exc:
        raise _bad(exc) from exc
    return _operation(op)


@router.post("/me/operations/{operation_id}/cancel")
async def cancel_my_operation(
    operation_id: str, current_user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> dict:
    agent = await _me(db, current_user)
    try:
        op = await service.cancel_operation(db, organization_id=current_user.organization_id,
                                            operation_id=_uuid(operation_id), actor_user_id=current_user.user_id,
                                            reason="Annullata dal Digital Ambassador", agent_id=agent.id)
    except service.AffiliateError as exc:
        raise _bad(exc) from exc
    return _operation(op)


# --- Administration ----------------------------------------------------------


@router.get("/admin/overview")
async def admin_overview(
    current_user: CurrentUser = Depends(require_permission("commissions.read_branch")), db: AsyncSession = Depends(get_db)
) -> dict:
    data = await service.admin_overview(db, current_user.organization_id)
    await db.commit()
    return _out(data)


@router.get("/admin/affiliates")
async def admin_affiliates(
    search: str | None = None,
    limit: int = 300,
    current_user: CurrentUser = Depends(require_permission("commissions.read_branch")),
    db: AsyncSession = Depends(get_db),
) -> list:
    """The month's figures per person, highest volume first. The network
    mirrors Mamify (tens of thousands of people): the list stops at `limit`,
    and the search narrows it."""
    rows = await service.list_affiliates(db, current_user.organization_id, search)
    return _out(rows[: max(1, min(limit, 2000))])


@router.get("/admin/affiliates/{agent_id}")
async def admin_affiliate_detail(
    agent_id: str,
    current_user: CurrentUser = Depends(require_permission("commissions.read_branch")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        summary = await service.affiliate_summary(db, current_user.organization_id, _uuid(agent_id))
    except service.AffiliateError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return _out(summary)


@router.get("/admin/network")
async def admin_network(
    root: str | None = None,
    current_user: CurrentUser = Depends(require_permission("commissions.read_branch")),
    db: AsyncSession = Depends(get_db),
) -> list:
    return _out(await service.network_tree(db, current_user.organization_id, _uuid(root) if root else None))


@router.get("/admin/network/branch")
async def admin_network_branch(
    root: str | None = None, offset: int = 0, limit: int = tree.PAGE, sort: str = "size", active: bool = False,
    fresh: bool = False,
    current_user: CurrentUser = Depends(require_permission("commissions.read_branch")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """One branch of the whole tree: a person (or the top) and a page of
    their directs, biggest branches first. See affiliate/tree.py."""
    snap = await tree.snapshot(db, current_user.organization_id, fresh=fresh)
    node = _uuid(root) if root else None
    if node is not None and node not in snap.nodes:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Persona non trovata nella rete.")
    out = tree.branch(snap, node, offset=offset, limit=limit, sort=sort, active_only=active)
    out["summary"] = tree.summary(snap, node)
    out["scope"] = None
    return _out(out)


@router.get("/admin/network/search")
async def admin_network_search(
    q: str,
    current_user: CurrentUser = Depends(require_permission("commissions.read_branch")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    snap = await tree.snapshot(db, current_user.organization_id)
    return _out(tree.search(snap, q, scope=None))


@router.patch("/admin/affiliates/{agent_id}/subscription")
async def admin_subscription_status(
    agent_id: str, payload: SubscriptionStatusUpdate,
    current_user: CurrentUser = Depends(require_permission("payments.manage")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        sub = await service.set_subscription_status(db, organization_id=current_user.organization_id,
                                                    agent_id=_uuid(agent_id), status=payload.status,
                                                    actor_user_id=current_user.user_id, reason=payload.reason)
    except service.AffiliateError as exc:
        raise _bad(exc) from exc
    return _out({"status": sub.status})


@router.get("/admin/operations")
async def admin_operations(
    status_filter: str | None = None, kind: str | None = None, agent_id: str | None = None,
    current_user: CurrentUser = Depends(require_permission("commissions.read_branch")),
    db: AsyncSession = Depends(get_db),
) -> list:
    return _out(await service.list_operations(db, current_user.organization_id, status=status_filter, kind=kind,
                                              agent_id=_uuid(agent_id) if agent_id else None))


@router.post("/admin/purchases", status_code=status.HTTP_201_CREATED)
async def admin_register_purchase(
    payload: AdminPurchaseCreate,
    current_user: CurrentUser = Depends(require_permission("payments.manage")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """A purchase recorded by the office (e.g. a monthly fee paid by bank
    transfer), optionally confirmed in the same step."""
    try:
        op = await service.create_purchase(
            db, organization_id=current_user.organization_id, agent_id=_uuid(payload.agent_id),
            product_code=payload.product_code, period=payload.period, payment_method=payload.payment_method,
            note=payload.note, actor_user_id=current_user.user_id,
        )
        if payload.confirm_now:
            op = await service.confirm_operation(db, organization_id=current_user.organization_id, operation_id=op.id,
                                                 actor_user_id=current_user.user_id)
    except (service.AffiliateError, ValueError) as exc:
        raise _bad(exc) from exc
    return _operation(op)


@router.post("/admin/operations/{operation_id}/confirm")
async def admin_confirm_operation(
    operation_id: str, payload: OperationDecision | None = None,
    current_user: CurrentUser = Depends(require_permission("payments.manage")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        op = await service.confirm_operation(db, organization_id=current_user.organization_id,
                                             operation_id=_uuid(operation_id), actor_user_id=current_user.user_id,
                                             payment_method=payload.payment_method if payload else None)
    except service.AffiliateError as exc:
        raise _bad(exc) from exc
    return _operation(op)


@router.post("/admin/operations/{operation_id}/cancel")
async def admin_cancel_operation(
    operation_id: str, payload: OperationDecision | None = None,
    current_user: CurrentUser = Depends(require_permission("payments.manage")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        op = await service.cancel_operation(db, organization_id=current_user.organization_id,
                                            operation_id=_uuid(operation_id), actor_user_id=current_user.user_id,
                                            reason=payload.reason if payload else None)
    except service.AffiliateError as exc:
        raise _bad(exc) from exc
    return _operation(op)


@router.post("/admin/operations/{operation_id}/reverse")
async def admin_reverse_operation(
    operation_id: str, payload: OperationDecision,
    current_user: CurrentUser = Depends(require_permission("commissions.approve")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        op = await service.reverse_operation(db, organization_id=current_user.organization_id,
                                             operation_id=_uuid(operation_id), actor_user_id=current_user.user_id,
                                             reason=payload.reason or "")
    except service.AffiliateError as exc:
        raise _bad(exc) from exc
    return _operation(op)


@router.get("/admin/commissions")
async def admin_commissions(
    kind: str | None = None, status_filter: str | None = None, agent_id: str | None = None,
    current_user: CurrentUser = Depends(require_permission("commissions.read_branch")),
    db: AsyncSession = Depends(get_db),
) -> list:
    return _out(await service.list_commissions(db, current_user.organization_id, kind=kind, status=status_filter,
                                               agent_id=_uuid(agent_id) if agent_id else None))


@router.post("/admin/commissions/pay")
async def admin_pay_commissions(
    payload: CommissionPayout,
    current_user: CurrentUser = Depends(require_permission("commissions.pay")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    paid = await service.mark_commissions_paid(db, organization_id=current_user.organization_id,
                                               commission_ids=[_uuid(i) for i in payload.commission_ids],
                                               actor_user_id=current_user.user_id)
    return {"paid": paid}


@router.get("/admin/licenses")
async def admin_licenses(
    current_user: CurrentUser = Depends(require_permission("commissions.read_branch")), db: AsyncSession = Depends(get_db)
) -> list:
    return _out(await service.list_licenses(db, current_user.organization_id))


@router.get("/admin/licenses/page")
async def admin_licenses_page(
    page: int = 1, page_size: int = 25, status_filter: str | None = None, search: str | None = None,
    origin: str | None = None, agent_id: str | None = None,
    current_user: CurrentUser = Depends(require_permission("commissions.read_branch")), db: AsyncSession = Depends(get_db),
) -> dict:
    return _out(await licenses.licenses_page(
        db, current_user.organization_id, agent_id=_uuid(agent_id, "affiliato") if agent_id else None, page=page,
        page_size=page_size, status=status_filter, search=search, origin=origin))


@router.get("/admin/licenses/margins")
async def admin_license_margins(
    page: int = 1, page_size: int = 25, search: str | None = None,
    current_user: CurrentUser = Depends(require_permission("commissions.read_branch")), db: AsyncSession = Depends(get_db),
) -> dict:
    result = await licenses.margins_page(db, current_user.organization_id, page=page, page_size=page_size, search=search)
    await db.commit()
    return _out(result)


@router.get("/admin/licenses/margins/{agent_id}")
async def admin_agent_license_margins(
    agent_id: str,
    current_user: CurrentUser = Depends(require_permission("commissions.read_branch")), db: AsyncSession = Depends(get_db),
) -> dict:
    result = await licenses.agent_margins(db, current_user.organization_id, _uuid(agent_id, "affiliato"))
    await db.commit()
    return _out(result)


@router.post("/admin/licenses/assign", status_code=status.HTTP_201_CREATED)
async def admin_assign_license(
    payload: LicenseAssign,
    current_user: CurrentUser = Depends(require_permission("payments.manage")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """The office assigns a licence on behalf of its owner."""
    from app.modules.affiliate.models import AffiliateLicense

    lic = await db.get(AffiliateLicense, _uuid(payload.license_id, "licenza"))
    if lic is None or lic.organization_id != current_user.organization_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Licenza non trovata.")
    try:
        op = await licenses.assign_license(
            db, organization_id=current_user.organization_id, agent_id=lic.owner_agent_id, license_id=lic.id,
            client_id=_uuid(payload.client_id, "cliente") if payload.client_id else None,
            new_client=payload.new_client.model_dump() if payload.new_client else None,
            actor_user_id=current_user.user_id, payment_method=payload.payment_method, note=payload.note,
        )
    except service.AffiliateError as exc:
        raise _bad(exc) from exc
    return _operation(op)


@router.get("/admin/clients")
async def admin_clients(
    agent_id: str | None = None,
    current_user: CurrentUser = Depends(require_permission("commissions.read_branch")), db: AsyncSession = Depends(get_db)
) -> list:
    clients = await service.list_clients(db, current_user.organization_id,
                                         _uuid(agent_id, "affiliato") if agent_id else None)
    agents = await service.agents_by_id(db, current_user.organization_id)
    return _out([{"id": c.id, "company_name": c.company_name, "vat_number": c.vat_number, "email": c.email,
                  "mamicash_balance": c.mamicash_balance,
                  "agent": {"id": c.agent_id, "name": agents[c.agent_id].display_name} if c.agent_id in agents else None}
                 for c in clients])


@router.get("/admin/periods")
async def admin_periods(
    current_user: CurrentUser = Depends(require_permission("commissions.read_branch")), db: AsyncSession = Depends(get_db)
) -> dict:
    return _out(await service.list_periods(db, current_user.organization_id))


@router.get("/admin/periods/{period}/results")
async def admin_period_results(
    period: str,
    current_user: CurrentUser = Depends(require_permission("commissions.read_branch")),
    db: AsyncSession = Depends(get_db),
) -> list:
    try:
        return _out(await service.period_results(db, current_user.organization_id, period))
    except ValueError as exc:
        raise _bad(exc) from exc


@router.post("/admin/periods/{period}/close")
async def admin_close_period(
    period: str,
    current_user: CurrentUser = Depends(require_permission("commissions.approve")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        close = await service.close_period(db, organization_id=current_user.organization_id, period=period,
                                           actor_user_id=current_user.user_id)
    except (service.AffiliateError, ValueError) as exc:
        raise _bad(exc) from exc
    return _out({"period": close.period, "qualified_count": close.qualified_count, "total_bonus": close.total_bonus})


@router.get("/admin/plan")
async def admin_plan_versions(
    current_user: CurrentUser = Depends(require_permission("commissions.read_branch")), db: AsyncSession = Depends(get_db)
) -> list:
    versions = await service.list_plan_versions(db, current_user.organization_id)
    await db.commit()
    current = await service.get_plan(db, current_user.organization_id)
    return _out([{"id": v.id, "label": v.label, "valid_from": v.valid_from, "notes": v.notes, "config": v.config,
                  "is_current": v.id == current.id, "products": list(product_index(v.config))} for v in versions])


@router.post("/admin/plan", status_code=status.HTTP_201_CREATED)
async def admin_create_plan_version(
    payload: PlanVersionCreate,
    current_user: CurrentUser = Depends(require_permission("commissions.approve")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        row = await service.create_plan_version(db, organization_id=current_user.organization_id, config=payload.config,
                                                valid_from=payload.valid_from, label=payload.label, notes=payload.notes,
                                                actor_user_id=current_user.user_id)
    except (service.AffiliateError, PlanValidationError, KeyError, TypeError) as exc:
        raise _bad(exc if not isinstance(exc, KeyError | TypeError) else ValueError("Configurazione del piano incompleta.")) from exc
    return _out({"id": row.id, "label": row.label, "valid_from": row.valid_from})


@router.get("/admin/export/{dataset}")
async def admin_export(
    dataset: str, period: str | None = None,
    current_user: CurrentUser = Depends(require_permission("commissions.read_branch")),
    db: AsyncSession = Depends(get_db),
) -> Response:
    if dataset not in service.EXPORTS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Esportazione non disponibile.")
    body = await service.export_csv(db, current_user.organization_id, dataset, period)
    filename = f"sos-affiliate-{dataset}{'-' + period if period else ''}.csv"
    return Response(content="﻿" + body, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})
