"""Celery application for the worker and beat services.

Lives in the api package so the worker runs the same domain code (models,
services, commission engine) as the API; both are built from the same image."""

import logging

from celery import Celery
from celery.schedules import crontab

from app.foundation.config import get_settings

# Import every domain's models so the metadata is complete before any task
# flushes; otherwise a foreign key to an unimported table raises
# NoReferencedTableError.
from app.modules.aliexpress_dropshipping import models as _aliexpress_models  # noqa: F401
from app.modules.audit import models as _audit_models  # noqa: F401
from app.modules.auth import models as _auth_models  # noqa: F401
from app.modules.catalog import models as _catalog_models  # noqa: F401
from app.modules.cj_dropshipping import models as _cj_models  # noqa: F401
from app.modules.commissions import models as _commissions_models  # noqa: F401
from app.modules.contracts import models as _contracts_models  # noqa: F401
from app.modules.customers import models as _customers_models  # noqa: F401
from app.modules.documentation import models as _documentation_models  # noqa: F401
from app.modules.documents import models as _documents_models  # noqa: F401
from app.modules.friend_referrals import models as _friend_referrals_models  # noqa: F401
from app.modules.imported_products import models as _imported_products_models  # noqa: F401
from app.modules.invoice_redemptions import models as _invoice_redemptions_models  # noqa: F401
from app.modules.network import models as _network_models  # noqa: F401
from app.modules.notifications import models as _notifications_models  # noqa: F401
from app.modules.orders import models as _orders_models  # noqa: F401
from app.modules.organizations import models as _organizations_models  # noqa: F401
from app.modules.outbox import models as _outbox_models  # noqa: F401
from app.modules.partners import models as _partners_models  # noqa: F401
from app.modules.payments import models as _payments_models  # noqa: F401
from app.modules.rbac import models as _rbac_models  # noqa: F401
from app.modules.referral import models as _referral_models  # noqa: F401
from app.modules.shopify_dropshipping import models as _shopify_models  # noqa: F401
from app.modules.support import models as _support_models  # noqa: F401
from app.modules.users import models as _users_models  # noqa: F401
from app.modules.wallets import models as _wallets_models  # noqa: F401


def _import_every_model_module() -> None:
    """Every app.modules.<x>.models, also the ones added after the list
    above was written (commercial, affiliate, mamify were missing, and the
    Mamify sync failed on its first real run with NoReferencedTableError)."""
    import importlib
    import pkgutil

    from app import modules

    for info in pkgutil.iter_modules(modules.__path__):
        if info.ispkg:
            try:
                importlib.import_module(f"app.modules.{info.name}.models")
            except ModuleNotFoundError as exc:
                if exc.name != f"app.modules.{info.name}.models":
                    raise


_import_every_model_module()

settings = get_settings()

celery_app = Celery("sosnet", broker=settings.redis_url, backend=settings.redis_url)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        "process-domain-outbox": {
            "task": "app.celery_app.process_outbox_task",
            "schedule": crontab(minute="*/1"),
        },
        "cj-sync-orders": {
            # Status and tracking of orders placed on CJ.
            "task": "app.celery_app.cj_sync_orders_task",
            "schedule": crontab(minute="*/30"),
        },
        "cj-retry-orders": {
            # Unsent orders, temporary failures, and orders waiting for CJ
            # balance (paid once the balance covers them).
            "task": "app.celery_app.cj_retry_orders_task",
            "schedule": crontab(minute="*/10"),
        },
        "cj-sync-products": {
            # Cost, stock and availability of the imported CJ products.
            "task": "app.celery_app.cj_sync_products_task",
            "schedule": crontab(hour=3, minute=30),
        },
        "shopify-sync-orders": {
            # Fulfilment and tracking of orders in the Shopify store.
            "task": "app.celery_app.shopify_sync_orders_task",
            "schedule": crontab(minute="*/30"),
        },
        "shopify-retry-orders": {
            # Paid but unsent orders and temporary failures.
            "task": "app.celery_app.shopify_retry_orders_task",
            "schedule": crontab(minute="*/10"),
        },
        "shopify-sync-products": {
            # Cost, price and stock of the imported Shopify products.
            "task": "app.celery_app.shopify_sync_products_task",
            "schedule": crontab(hour=3, minute=45),
        },
        "aliexpress-sync-orders": {
            # Shipping and tracking of orders on AliExpress.
            "task": "app.celery_app.aliexpress_sync_orders_task",
            "schedule": crontab(minute="*/30"),
        },
        "aliexpress-retry-orders": {
            # Paid but unsent orders and temporary failures. Orders whose
            # outcome is unknown are left for a human to resolve.
            "task": "app.celery_app.aliexpress_retry_orders_task",
            "schedule": crontab(minute="*/10"),
        },
        "affiliate-close-previous-month": {
            # SOS Affiliate: consolidates last month's career levels and BC
            # bonuses on the 1st, 02:30 UTC (03:30/04:30 in Rome), so the
            # month is over in every timezone the network works in.
            "task": "app.celery_app.affiliate_close_previous_month_task",
            "schedule": crontab(day_of_month=1, hour=2, minute=30),
        },
        "aliexpress-sync-products": {
            # Cost, price and stock of the imported AliExpress products.
            "task": "app.celery_app.aliexpress_sync_products_task",
            "schedule": crontab(hour=4, minute=0),
        },
        # Mamify is read only and serves 50 people a call with 60 calls a
        # minute per key, so its reads run one at a time in the `mamify`
        # queue (worker celery-mamify, concurrency 1). `expires` drops the
        # runs that queued up behind the long nightly copy.
        "mamify-network-full": {
            # The whole tree (moves, departures): ~20 minutes for 50,000 people.
            "task": "app.celery_app.mamify_sync_network_task",
            "schedule": crontab(hour=2, minute=15),
        },
        "mamify-network-new": {
            # People registered since the last check: one or two calls.
            "task": "app.celery_app.mamify_new_members_periodic_task",
            "schedule": crontab(minute="*/5"),
            "options": {"expires": 240},
        },
        "mamify-orders": {
            # One person's orders per call, everyone in turn, within the
            # configured share of the key's budget.
            "task": "app.celery_app.mamify_orders_task",
            "schedule": crontab(minute="*/2"),
            "options": {"expires": 100},
        },
    },
    task_routes={"app.celery_app.mamify_*": {"queue": "mamify"}},
)


def _run_async(make_coro):
    import asyncio

    from app.foundation.db import AsyncSessionLocal, engine

    async def _run():
        try:
            async with AsyncSessionLocal() as db:
                return await make_coro(db)
        finally:
            # Pooled connections belong to this event loop; the next task
            # runs in a new one.
            await engine.dispose()

    return asyncio.run(_run())


@celery_app.task(name="app.celery_app.mamify_sync_network_task")
def mamify_sync_network_task() -> int:
    from app.modules.mamify import service as mamify_service

    return _run_async(mamify_service.periodic_network_sync)


@celery_app.task(name="app.celery_app.mamify_orders_task")
def mamify_orders_task() -> int:
    from app.modules.mamify import service as mamify_service

    return _run_async(mamify_service.periodic_orders)


@celery_app.task(name="app.celery_app.mamify_new_members_periodic_task")
def mamify_new_members_periodic_task() -> int:
    from app.modules.mamify import service as mamify_service

    return _run_async(mamify_service.periodic_new_members)


def _for_org(organization_id: str, run):
    import uuid

    from app.modules.mamify import service as mamify_service

    org = uuid.UUID(organization_id)

    async def go(db):
        try:
            return await run(mamify_service, db, org)
        except mamify_service.MamifyError as exc:
            return {"error": str(exc)}

    return _run_async(go)


@celery_app.task(name="app.celery_app.mamify_full_sync_task")
def mamify_full_sync_task(organization_id: str) -> dict:
    return _for_org(organization_id, lambda s, db, org: s.sync_network(db, org))


@celery_app.task(name="app.celery_app.mamify_new_members_task")
def mamify_new_members_task(organization_id: str) -> dict:
    """Queued by a customers/new webhook and by the admin page."""
    return _for_org(organization_id, lambda s, db, org: s.sync_new_members(db, org))


@celery_app.task(name="app.celery_app.mamify_branch_task")
def mamify_branch_task(organization_id: str, agent_id: str) -> dict:
    """"Aggiorna rete" of one person: re-reads their branch from Mamify."""
    import uuid

    return _for_org(organization_id, lambda s, db, org: s.sync_branch(db, org, uuid.UUID(agent_id)))


@celery_app.task(name="app.celery_app.mamify_own_orders_task", expires=300)
def mamify_own_orders_task(organization_id: str, customer_id: str) -> dict:
    """A person opened their dashboard: re-reads their own latest orders."""
    return _for_org(organization_id, lambda s, db, org: s.read_own_orders(db, org, customer_id))


@celery_app.task(name="app.celery_app.affiliate_close_previous_month_task")
def affiliate_close_previous_month_task() -> int:
    import asyncio

    from app.foundation.db import AsyncSessionLocal
    from app.modules.affiliate import service as affiliate_service

    async def _run() -> int:
        async with AsyncSessionLocal() as db:
            return await affiliate_service.close_previous_period_for_all(db)

    return asyncio.run(_run())


@celery_app.task(name="app.celery_app.process_outbox_task")
def process_outbox_task() -> int:
    """Dispatch unprocessed domain_outbox events, chiefly triggering commission
    calculation after a contract activation commits (see ADR 0005)."""
    import asyncio

    from app.foundation.db import AsyncSessionLocal
    from app.modules.commissions.tasks.dispatch import process_pending_outbox_events

    async def _run() -> int:
        async with AsyncSessionLocal() as db:
            return await process_pending_outbox_events(db)

    return asyncio.run(_run())


def _cj_run(job):
    """Runs a CJ job for every organization that has a CJ key."""
    import asyncio

    from sqlalchemy import select

    from app.foundation.db import AsyncSessionLocal
    from app.modules.cj_dropshipping import client as cj_client
    from app.modules.cj_dropshipping.models import CjSettings

    async def _run() -> int:
        cj_client.reset_redis()
        total = 0
        async with AsyncSessionLocal() as db:
            org_ids = list(
                (await db.execute(select(CjSettings.organization_id).where(CjSettings.api_key.is_not(None)))).scalars()
            )
            for org_id in org_ids:
                try:
                    total += await job(db, org_id)
                except Exception:
                    logging.getLogger(__name__).exception("CJ job failed for organization %s", org_id)
                    await db.rollback()
        return total

    return asyncio.run(_run())


@celery_app.task(name="app.celery_app.cj_sync_orders_task")
def cj_sync_orders_task() -> int:
    from app.modules.cj_dropshipping import service as cj_service

    return _cj_run(lambda db, org_id: cj_service.sync_orders(db, organization_id=org_id))


@celery_app.task(name="app.celery_app.cj_retry_orders_task")
def cj_retry_orders_task() -> int:
    from app.modules.cj_dropshipping import service as cj_service

    return _cj_run(lambda db, org_id: cj_service.retry_due_orders(db, organization_id=org_id))


@celery_app.task(name="app.celery_app.cj_sync_products_task")
def cj_sync_products_task() -> int:
    from app.modules.cj_dropshipping import service as cj_service

    return _cj_run(lambda db, org_id: cj_service.sync_all_products(db, organization_id=org_id))


@celery_app.task(name="app.celery_app.cj_forward_order_task")
def cj_forward_order_task(order_id: str) -> str:
    """Automatic "Invia a CJ" right after payment, when enabled."""
    import asyncio
    import uuid

    from app.foundation.db import AsyncSessionLocal
    from app.modules.cj_dropshipping import client as cj_client
    from app.modules.cj_dropshipping import service as cj_service
    from app.modules.cj_dropshipping.models import CjOrder

    async def _run() -> str:
        cj_client.reset_redis()
        async with AsyncSessionLocal() as db:
            order = await db.get(CjOrder, uuid.UUID(order_id))
            if order is None:
                return "missing"
            try:
                order = await cj_service.forward_order(
                    db, organization_id=order.organization_id, order_id=order.id, actor_user_id=None
                )
            except cj_service.CjError as exc:
                return f"skipped: {exc}"
            return order.fulfillment_status

    return asyncio.run(_run())


def _shopify_run(job):
    """Runs a Shopify job for every organization that has a store configured."""
    import asyncio

    from sqlalchemy import select

    from app.foundation.db import AsyncSessionLocal
    from app.modules.shopify_dropshipping.models import ShopifySettings

    async def _run() -> int:
        total = 0
        async with AsyncSessionLocal() as db:
            org_ids = list(
                (
                    await db.execute(
                        select(ShopifySettings.organization_id).where(
                            ShopifySettings.access_token.is_not(None), ShopifySettings.shop_domain.is_not(None)
                        )
                    )
                ).scalars()
            )
            for org_id in org_ids:
                try:
                    total += await job(db, org_id)
                except Exception:
                    logging.getLogger(__name__).exception("Shopify job failed for organization %s", org_id)
                    await db.rollback()
        return total

    return asyncio.run(_run())


@celery_app.task(name="app.celery_app.shopify_sync_orders_task")
def shopify_sync_orders_task() -> int:
    from app.modules.shopify_dropshipping import service as shopify_service

    return _shopify_run(lambda db, org_id: shopify_service.sync_orders(db, organization_id=org_id))


@celery_app.task(name="app.celery_app.shopify_retry_orders_task")
def shopify_retry_orders_task() -> int:
    from app.modules.shopify_dropshipping import service as shopify_service

    return _shopify_run(lambda db, org_id: shopify_service.retry_due_orders(db, organization_id=org_id))


@celery_app.task(name="app.celery_app.shopify_sync_products_task")
def shopify_sync_products_task() -> int:
    from app.modules.shopify_dropshipping import service as shopify_service

    return _shopify_run(lambda db, org_id: shopify_service.sync_all_products(db, organization_id=org_id))


@celery_app.task(name="app.celery_app.shopify_forward_order_task")
def shopify_forward_order_task(order_id: str) -> str:
    """Automatic "Invia a Shopify" right after payment, when enabled."""
    import asyncio
    import uuid

    from app.foundation.db import AsyncSessionLocal
    from app.modules.shopify_dropshipping import service as shopify_service
    from app.modules.shopify_dropshipping.models import ShopifyOrder

    async def _run() -> str:
        async with AsyncSessionLocal() as db:
            order = await db.get(ShopifyOrder, uuid.UUID(order_id))
            if order is None:
                return "missing"
            try:
                order = await shopify_service.forward_order(
                    db, organization_id=order.organization_id, order_id=order.id, actor_user_id=None
                )
            except shopify_service.ShopifyError as exc:
                return f"skipped: {exc}"
            return order.fulfillment_status

    return asyncio.run(_run())


def _aliexpress_run(job):
    """Runs an AliExpress job for every organization whose account is linked."""
    import asyncio

    from sqlalchemy import select

    from app.foundation.db import AsyncSessionLocal
    from app.modules.aliexpress_dropshipping.models import AliexpressSettings

    async def _run() -> int:
        total = 0
        async with AsyncSessionLocal() as db:
            org_ids = list(
                (
                    await db.execute(
                        select(AliexpressSettings.organization_id).where(
                            AliexpressSettings.access_token.is_not(None),
                            AliexpressSettings.app_key.is_not(None),
                        )
                    )
                ).scalars()
            )
            for org_id in org_ids:
                try:
                    total += await job(db, org_id)
                except Exception:
                    logging.getLogger(__name__).exception("AliExpress job failed for organization %s", org_id)
                    await db.rollback()
        return total

    return asyncio.run(_run())


@celery_app.task(name="app.celery_app.aliexpress_sync_orders_task")
def aliexpress_sync_orders_task() -> int:
    from app.modules.aliexpress_dropshipping import service as aliexpress_service

    return _aliexpress_run(lambda db, org_id: aliexpress_service.sync_orders(db, organization_id=org_id))


@celery_app.task(name="app.celery_app.aliexpress_retry_orders_task")
def aliexpress_retry_orders_task() -> int:
    from app.modules.aliexpress_dropshipping import service as aliexpress_service

    return _aliexpress_run(lambda db, org_id: aliexpress_service.retry_due_orders(db, organization_id=org_id))


@celery_app.task(name="app.celery_app.aliexpress_sync_products_task")
def aliexpress_sync_products_task() -> int:
    from app.modules.aliexpress_dropshipping import service as aliexpress_service

    return _aliexpress_run(lambda db, org_id: aliexpress_service.sync_all_products(db, organization_id=org_id))


@celery_app.task(name="app.celery_app.aliexpress_forward_order_task")
def aliexpress_forward_order_task(order_id: str) -> str:
    """Automatic "Invia ad AliExpress" right after payment, when enabled."""
    import asyncio
    import uuid

    from app.foundation.db import AsyncSessionLocal
    from app.modules.aliexpress_dropshipping import service as aliexpress_service
    from app.modules.aliexpress_dropshipping.models import AliexpressOrder

    async def _run() -> str:
        async with AsyncSessionLocal() as db:
            order = await db.get(AliexpressOrder, uuid.UUID(order_id))
            if order is None:
                return "missing"
            try:
                order = await aliexpress_service.forward_order(
                    db, organization_id=order.organization_id, order_id=order.id, actor_user_id=None
                )
            except aliexpress_service.AliexpressError as exc:
                return f"skipped: {exc}"
            return order.fulfillment_status

    return asyncio.run(_run())
