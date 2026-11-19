"""Mamify connection API.

`/mamify/admin/*` is the connection page (settings.manage; the list of
commissions to pay on Mamify needs commissions.pay). Long reads of Mamify
(the full network copy, the order poller) run in the `mamify` worker, so
these routes only queue them. `/mamify/webhook/{token}/{type}` is public:
Mamify does not sign its calls, so the unguessable token in the URL is what
identifies them. Nothing here ever writes to Mamify.
"""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.foundation.db import get_db
from app.foundation.deps import CurrentUser, get_current_user, require_permission
from app.modules.affiliate.router import _out
from app.modules.mamify import service
from app.modules.mamify.client import MamifyApiError

router = APIRouter(prefix="/mamify", tags=["mamify"])


class ConfigUpdate(BaseModel):
    enabled: bool | None = None
    base_url: str | None = None
    api_key: str | None = None
    functionality: str | None = None
    root_customer: str | None = None
    paid_statuses: list[str] | str | None = None
    cancelled_statuses: list[str] | str | None = None
    order_apps: list[str] | str | None = None
    orders_calls_per_minute: int | None = None


class ProductMapUpdate(BaseModel):
    mamify_product_id: str
    plan_code: str | None = None
    title: str | None = None


def _bad(exc: Exception) -> HTTPException:
    return HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


def _uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Identificativo non valido.") from exc


ERRORS = (service.MamifyError, MamifyApiError)


@router.get("/admin/status")
async def get_status(
    current_user: CurrentUser = Depends(require_permission("settings.manage")), db: AsyncSession = Depends(get_db)
) -> dict:
    return _out(await service.status(db, current_user.organization_id))


@router.patch("/admin/config")
async def patch_config(
    payload: ConfigUpdate,
    current_user: CurrentUser = Depends(require_permission("settings.manage")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        cfg = await service.update_config(db, organization_id=current_user.organization_id,
                                          changes=payload.model_dump(exclude_unset=True),
                                          actor_user_id=current_user.user_id)
    except ERRORS as exc:
        await db.rollback()
        raise _bad(exc) from exc
    return _out(service.config_view(cfg))


@router.post("/admin/test")
async def post_test(
    current_user: CurrentUser = Depends(require_permission("settings.manage")), db: AsyncSession = Depends(get_db)
) -> dict:
    try:
        return _out(await service.test_connection(db, current_user.organization_id))
    except ERRORS as exc:
        raise _bad(exc) from exc


async def _ready(db: AsyncSession, organization_id: uuid.UUID) -> None:
    cfg = await service.get_config(db, organization_id)
    await db.commit()
    if not (cfg.api_key and cfg.root_customer):
        raise _bad(service.MamifyError("Servono la chiave API e il cliente in cima alla rete."))


@router.post("/admin/sync-network")
async def post_sync_network(
    current_user: CurrentUser = Depends(require_permission("settings.manage")), db: AsyncSession = Depends(get_db)
) -> dict:
    """Queues the full copy of the tree (about 20 minutes for 50,000 people);
    the status page shows its progress."""
    from app.celery_app import mamify_full_sync_task

    await _ready(db, current_user.organization_id)
    mamify_full_sync_task.delay(str(current_user.organization_id))
    return {"queued": True}


@router.post("/admin/sync-new-members")
async def post_sync_new_members(
    current_user: CurrentUser = Depends(require_permission("settings.manage")), db: AsyncSession = Depends(get_db)
) -> dict:
    from app.celery_app import mamify_new_members_task

    await _ready(db, current_user.organization_id)
    mamify_new_members_task.delay(str(current_user.organization_id))
    return {"queued": True}


@router.post("/admin/import-orders")
async def post_import_orders(
    current_user: CurrentUser = Depends(require_permission("settings.manage")), db: AsyncSession = Depends(get_db)
) -> dict:
    """Puts everyone back at the front of the order poller's line: their
    orders are read again, within the poller's budget of calls."""
    await _ready(db, current_user.organization_id)
    return {"people": await service.recheck_all_orders(db, current_user.organization_id)}


@router.post("/admin/retry-orders")
async def post_retry_orders(
    current_user: CurrentUser = Depends(require_permission("settings.manage")), db: AsyncSession = Depends(get_db)
) -> dict:
    try:
        return {"retried": await service.retry_waiting_orders(db, current_user.organization_id)}
    except ERRORS as exc:
        raise _bad(exc) from exc


@router.get("/admin/orders")
async def get_orders(
    state: str | None = None,
    current_user: CurrentUser = Depends(require_permission("settings.manage")),
    db: AsyncSession = Depends(get_db),
) -> list:
    return _out(await service.list_orders(db, current_user.organization_id, state=state))


@router.get("/admin/orders/page")
async def get_orders_page(
    page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=service.MAX_LIST_PAGE),
    state: str | None = Query(None, max_length=16), search: str | None = Query(None, max_length=120),
    current_user: CurrentUser = Depends(require_permission("network.manage")), db: AsyncSession = Depends(get_db),
) -> dict:
    """Orders received from Mamify, a page at a time (the Vendite → Ordini screen)."""
    return _out(await service.orders_page(db, current_user.organization_id, page=page, page_size=page_size,
                                          state=state, search=search))


@router.get("/admin/customers/page")
async def get_customers_page(
    page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=service.MAX_LIST_PAGE),
    search: str | None = Query(None, max_length=120), buyers_only: bool = False,
    current_user: CurrentUser = Depends(require_permission("network.manage")), db: AsyncSession = Depends(get_db),
) -> dict:
    """Mamify customers with their SOS orders (the Vendite → Clienti screen)."""
    return _out(await service.customers_page(db, current_user.organization_id, page=page, page_size=page_size,
                                             search=search, buyers_only=buyers_only))


@router.post("/admin/customers/{mamify_customer_id}/read-orders")
async def post_read_customer_orders(
    mamify_customer_id: str,
    current_user: CurrentUser = Depends(require_permission("network.manage")), db: AsyncSession = Depends(get_db),
) -> dict:
    """Reads this customer's latest orders from Mamify now (one read-only call)."""
    try:
        return _out(await service.recheck_member_orders(db, current_user.organization_id, mamify_customer_id[:64]))
    except service.MamifyError as exc:
        raise _bad(exc) from exc


@router.get("/admin/remote-products")
async def get_remote_products(
    refresh: bool = False,
    current_user: CurrentUser = Depends(require_permission("settings.manage")),
    db: AsyncSession = Depends(get_db),
) -> list:
    try:
        return _out(await service.list_remote_products(db, current_user.organization_id, refresh=refresh))
    except ERRORS as exc:
        raise _bad(exc) from exc


@router.get("/admin/products")
async def get_products(
    current_user: CurrentUser = Depends(require_permission("settings.manage")), db: AsyncSession = Depends(get_db)
) -> list:
    rows = await service.list_product_map(db, current_user.organization_id)
    return _out([{"mamify_product_id": r.mamify_product_id, "title": r.title, "plan_code": r.plan_code} for r in rows])


@router.put("/admin/products")
async def put_product(
    payload: ProductMapUpdate,
    current_user: CurrentUser = Depends(require_permission("settings.manage")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        row = await service.set_product_map(db, organization_id=current_user.organization_id,
                                            mamify_product_id=payload.mamify_product_id, plan_code=payload.plan_code,
                                            title=payload.title, actor_user_id=current_user.user_id)
    except ERRORS as exc:
        await db.rollback()
        raise _bad(exc) from exc
    # Orders received before the mapping existed are applied now.
    await service.retry_waiting_orders(db, current_user.organization_id)
    return _out({"mamify_product_id": payload.mamify_product_id, "plan_code": row.plan_code if row else None})


@router.get("/admin/payouts/due")
async def get_payouts_due(
    current_user: CurrentUser = Depends(require_permission("commissions.pay")), db: AsyncSession = Depends(get_db)
) -> list:
    return _out(await service.payable_for_mamify(db, current_user.organization_id))


@router.post("/webhook/{token}")
@router.post("/webhook/{token}/{event_slug}")
async def receive_webhook(token: str, request: Request, event_slug: str | None = None,
                          db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    cfg = await service.config_by_token(db, token)
    if cfg is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    try:
        payload = await request.json()
    except ValueError:
        # A body that is not JSON is stored as text: it is still evidence.
        payload = {"body": (await request.body()).decode("utf-8", "replace")[:20000]}
    event_type = event_slug.replace("-", "/", 1) if event_slug else None
    outcome = await service.handle_webhook(db, cfg, event_type, payload)
    # Always 200 once stored: an error is ours to fix from the admin page,
    # and a non-2xx would only make Mamify resend the same body.
    return {"ok": True, "outcome": outcome}


# --- "Aggiorna rete" of one person ---------------------------------------------


@router.get("/admin/members/{agent_id}/branch-sync")
async def get_branch_sync(
    agent_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("network.manage")), db: AsyncSession = Depends(get_db),
) -> dict:
    """Whether this collaborator comes from Mamify, and the last update of their branch."""
    return _out(service.branch_view(await service.member_of_agent(db, current_user.organization_id, agent_id)))


@router.post("/admin/members/{agent_id}/branch-sync")
async def post_branch_sync(
    agent_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("network.manage")), db: AsyncSession = Depends(get_db),
) -> dict:
    """Queues the re-read of this collaborator's branch from Mamify (read only)."""
    try:
        return _out(await service.request_branch_sync(db, current_user.organization_id, agent_id))
    except service.MamifyError as exc:
        raise _bad(exc) from exc


async def _my_agent_id(db: AsyncSession, user: CurrentUser) -> uuid.UUID:
    from app.modules.affiliate import service as affiliate_service

    try:
        return (await affiliate_service.agent_for_user(db, user.organization_id, user.user_id)).id
    except affiliate_service.AffiliateError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.get("/me/branch-sync")
async def get_my_branch_sync(
    current_user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db),
) -> dict:
    agent_id = await _my_agent_id(db, current_user)
    return _out(service.branch_view(await service.member_of_agent(db, current_user.organization_id, agent_id)))


@router.post("/me/branch-sync")
async def post_my_branch_sync(
    current_user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db),
) -> dict:
    """A Digital Ambassador updates their own branch (at most every 15 minutes)."""
    agent_id = await _my_agent_id(db, current_user)
    try:
        return _out(await service.request_branch_sync(db, current_user.organization_id, agent_id, by_self=True))
    except service.MamifyError as exc:
        raise _bad(exc) from exc
