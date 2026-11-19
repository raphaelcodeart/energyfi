"""SOS Affiliate on top of Mamify, read only.

Mamify owns people, the sponsor tree, orders and wallets; SOS Affiliate owns
the compensation plan. SOS Affiliate **only reads** Mamify (the client
refuses any other call, see client.READ_ONLY_PATHS):

- **network**: the whole Mamify tree below the configured root is mirrored
  as the SOS tree (one agent per person, sponsor = Mamify sponsor). Mamify
  sends no webhook when the tree changes and serves 50 people a call, so:
  a full copy at night (moves and departures), the newest registrations
  every few minutes and as soon as a `customers/new` webhook arrives;
- **orders**: the service API lists orders one person at a time, so a
  poller reads each person's latest orders in turn, within a budget of
  calls a minute, people with a downline or open orders first. Webhooks, if
  Mamify registers them, make it immediate. An order paid on Mamify becomes
  a confirmed operation per mapped product unit (idempotent); a cancelled or
  refunded one is reversed;
- **commissions** are computed here and paid on Mamify by its staff: SOS
  never credits a wallet;
- **login**: an affiliate signs in with the Mamify email and password.

Which numbers a product is worth stays in the plan: the mapping only says
"this Mamify product is LARGE".
"""

import hashlib
import json
import logging
import secrets
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from sqlalchemy import BigInteger, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.foundation.config import get_settings
from app.foundation.db import utcnow
from app.modules.affiliate import licenses as license_register
from app.modules.affiliate import service as affiliate_service
from app.modules.affiliate.licenses import RESALE_CODE
from app.modules.affiliate.models import AffiliateClient, AffiliateCommission, AffiliateOperation
from app.modules.affiliate.plan import product_index
from app.modules.audit.models import AuditLog
from app.modules.mamify import parsing
from app.modules.mamify.client import MamifyApiError, MamifyClient
from app.modules.mamify.models import (
    MamifyConfig,
    MamifyMember,
    MamifyOrder,
    MamifyProductMap,
    MamifyWebhookEvent,
)
from app.modules.network import service as network_service
from app.modules.network.models import AgentProfile, NetworkClosure, NetworkNode

logger = logging.getLogger(__name__)

TOPUP_CODE = "MAMICASH_TOPUP"
#: Mamify serves at most 50 rows a page, whatever `limit` asks.
PAGE_SIZE = 50
#: Safety stop for one read: a loop in Mamify's paging must not run forever.
MAX_PAGES = 5000
#: The newest-registrations check reads at most this many pages; more new
#: people than that wait for the night's full copy.
MAX_NEW_PAGES = 40
#: How long a started network sync holds the tree before another may start
#: (a full copy of ~50,000 people takes about 20 minutes at 60 calls/minute).
SYNC_LEASE = timedelta(minutes=120)
#: People with a downline or an open order are re-read at least this often.
PRIORITY_EVERY = timedelta(hours=1)
#: Apps whose products count for SOS Affiliate, unless configured otherwise.
DEFAULT_ORDER_APPS = ["sos-affiliate", "digitalambassador"]
DEFAULT_CANCELLED = ["annullato", "rimborsato", "cancellato", "rifiutato"]
#: Webhooks Mamify can send here. SOS never registers them (that would be a
#: write on Mamify): Mamify's staff can, from the CRM, with webhook_url().
WEBHOOK_TYPES = ("orders/new", "orders/status_update", "customers/new")


class MamifyError(Exception):
    """Configuration or data problem; the message is shown as is."""


# --- Configuration -----------------------------------------------------------


async def get_config(db: AsyncSession, organization_id: uuid.UUID) -> MamifyConfig:
    cfg = (await db.execute(
        select(MamifyConfig).where(MamifyConfig.organization_id == organization_id)
    )).scalar_one_or_none()
    if cfg is None:
        cfg = MamifyConfig(
            organization_id=organization_id, webhook_token=secrets.token_urlsafe(32), paid_statuses=[],
            cancelled_statuses=list(DEFAULT_CANCELLED), payout_wallets={}, webhook_ids={},
            last_network_sync_result={}, order_apps=list(DEFAULT_ORDER_APPS), product_catalog={},
            network_sync_progress={},
        )
        db.add(cfg)
        await db.flush()
    return cfg


def webhook_url(cfg: MamifyConfig, event_type: str | None = None) -> str:
    base = f"{get_settings().public_app_base_url.rstrip('/')}/api/mamify/webhook/{cfg.webhook_token}"
    return f"{base}/{event_type.replace('/', '-')}" if event_type else base


def config_view(cfg: MamifyConfig) -> dict:
    """What the admin page shows. The key leaves only as "set" and last 4."""
    return {
        "enabled": cfg.enabled,
        "base_url": cfg.base_url,
        "api_key_set": bool(cfg.api_key),
        "api_key_last4": cfg.api_key[-4:] if cfg.api_key else None,
        "functionality": cfg.functionality,
        "root_customer": cfg.root_customer,
        "paid_statuses": cfg.paid_statuses or [],
        "cancelled_statuses": cfg.cancelled_statuses or [],
        "order_apps": cfg.order_apps or [],
        "orders_calls_per_minute": cfg.orders_calls_per_minute,
        "webhook_url": webhook_url(cfg),
        "webhook_urls": {t: webhook_url(cfg, t) for t in WEBHOOK_TYPES},
        "read_only": True,
        "last_network_sync_at": cfg.last_network_sync_at,
        "last_network_sync_result": cfg.last_network_sync_result or {},
        "last_new_members_at": cfg.last_new_members_at,
        "network_sync_running": cfg.network_sync_started_at is not None,
        "network_sync_progress": cfg.network_sync_progress or {},
        "last_orders_sync_at": cfg.last_orders_sync_at,
        "catalog_refreshed_at": (cfg.product_catalog or {}).get("at"),
        "last_error": cfg.last_error,
        "last_error_at": cfg.last_error_at,
    }


def _statuses(values: Any) -> list[str]:
    if isinstance(values, str):
        values = values.replace("\n", ",").split(",")
    return [str(v).strip() for v in values or [] if str(v).strip()][:50]


async def update_config(db: AsyncSession, *, organization_id: uuid.UUID, changes: dict, actor_user_id: uuid.UUID) -> MamifyConfig:
    """Applies only the fields present. An empty key means "leave as is",
    so the form never has to show or resend it."""
    cfg = await get_config(db, organization_id)
    before = config_view(cfg)
    if "base_url" in changes:
        url = (changes["base_url"] or "").strip().rstrip("/")
        if not url.startswith("https://"):
            raise MamifyError("L'indirizzo delle API Mamify deve iniziare con https://.")
        cfg.base_url = url
    if changes.get("api_key"):
        cfg.api_key = str(changes["api_key"]).strip()
    for field in ("functionality", "root_customer"):
        if field in changes:
            setattr(cfg, field, (str(changes[field] or "").strip() or None))
    for field in ("paid_statuses", "cancelled_statuses", "order_apps"):
        if field in changes:
            setattr(cfg, field, _statuses(changes[field]))
    if "orders_calls_per_minute" in changes:
        try:
            rate = int(changes["orders_calls_per_minute"])
        except (TypeError, ValueError) as exc:
            raise MamifyError("Le chiamate al minuto per gli ordini devono essere un numero intero.") from exc
        if not 0 <= rate <= 50:
            raise MamifyError("Le chiamate al minuto per gli ordini vanno da 0 a 50 (il limite della chiave è 60).")
        cfg.orders_calls_per_minute = rate
    if "enabled" in changes:
        cfg.enabled = bool(changes["enabled"])
    if cfg.enabled and not (cfg.api_key and cfg.root_customer):
        raise MamifyError("Per attivare il collegamento servono la chiave API e il cliente in cima alla rete.")
    cfg.sync_actor_user_id = actor_user_id
    db.add(AuditLog(
        organization_id=organization_id, actor_user_id=actor_user_id, action="mamify.config.updated",
        entity_type="mamify_config", entity_id=str(cfg.id), previous_value=json.loads(json.dumps(before, default=str)),
        new_value=json.loads(json.dumps(config_view(cfg), default=str)),
    ))
    await db.commit()
    return cfg


def client_for(cfg: MamifyConfig) -> MamifyClient:
    if not cfg.api_key:
        raise MamifyError("Manca la chiave API di Mamify (CRM: Sviluppatori → API → Chiavi API).")
    return MamifyClient(cfg.base_url, cfg.api_key, functionality=cfg.functionality)


async def _record_error(db: AsyncSession, cfg: MamifyConfig, message: str) -> None:
    cfg.last_error = message[:1000]
    cfg.last_error_at = utcnow()
    await db.commit()


def _customer_ref(value: str) -> dict:
    """How the service API identifies a customer (§11): id, email or invite code."""
    value = value.strip()
    if "@" in value:
        return {"email": value.lower()}
    if value.isdigit():
        return {"customer_id": int(value)}
    return {"code": value}


def _cid(value: str) -> int | str:
    """Customer and order ids go to Mamify as numbers, as it sends them."""
    return int(value) if str(value).isdigit() else value


async def test_connection(db: AsyncSession, organization_id: uuid.UUID) -> dict:
    """Checks the key and the root customer with two read-only calls."""
    cfg = await get_config(db, organization_id)
    client = client_for(cfg)
    out: dict[str, Any] = {"key": False, "root": None}
    try:
        await client.call("plugins/mamify/rag/apps/list", {"app": cfg.functionality or "sos-affiliate"})
        out["key"] = True
        if cfg.root_customer:
            answer = await client.call("plugins/mamify/rag/customer/find", _customer_ref(cfg.root_customer))
            member = parsing.member(parsing.customer_of(answer))
            network = (answer or {}).get("network") if isinstance(answer, dict) else None
            out["root"] = {
                "id": member.customer_id if member else None,
                "name": f"{member.first_name} {member.last_name}".strip() if member else None,
                "network": network,
            }
    except MamifyApiError as exc:
        out["error"] = str(exc)
        await _record_error(db, cfg, str(exc))
        return out
    cfg.last_error = None
    await db.commit()
    return out


# --- Network -----------------------------------------------------------------


async def _root_member(client: MamifyClient, cfg: MamifyConfig) -> parsing.Member:
    if not cfg.root_customer:
        raise MamifyError("Indica il cliente Mamify in cima alla rete SOS.")
    found = await client.call("plugins/mamify/rag/customer/find", _customer_ref(cfg.root_customer))
    member = parsing.member(parsing.customer_of(found))
    if member is None:
        raise MamifyError("Il cliente in cima alla rete non è stato trovato su Mamify.")
    return member


async def _network_page(client: MamifyClient, root: str, page: int) -> tuple[list[parsing.Member], int | None]:
    answer = await client.call("plugins/mamify/rag/customer/network",
                               {"customer_id": _cid(root), "scope": "all", "page": page, "limit": PAGE_SIZE})
    people = [m for m in (parsing.member(r) for r in parsing.items(answer)) if m and m.customer_id != root]
    return people, parsing.total_count(answer)


async def _set_progress(db: AsyncSession, cfg_id: uuid.UUID, progress: dict) -> None:
    await db.execute(update(MamifyConfig).where(MamifyConfig.id == cfg_id).values(network_sync_progress=progress))
    await db.commit()


async def fetch_network(db: AsyncSession, client: MamifyClient, cfg: MamifyConfig) -> tuple[str, dict[str, parsing.Member]]:
    """The whole tree below the root, each person with their sponsor, read
    page by page (scope "all"). New people arriving during the read push
    rows down a page: they are read twice, which the dict absorbs."""
    root = (await _root_member(client, cfg)).customer_id
    members: dict[str, parsing.Member] = {}
    total: int | None = None
    cfg_id = cfg.id
    for page in range(1, MAX_PAGES + 1):
        people, total = await _network_page(client, root, page)
        for m in people:
            members[m.customer_id] = m
        if page % 20 == 0 or not people:
            await _set_progress(db, cfg_id, {"phase": "read", "pages": page, "people": len(members), "total": total})
        if not people or (total is not None and page * PAGE_SIZE >= total):
            break
    for m in members.values():
        if m.sponsor_id is None:
            m.sponsor_id = root
    return root, members


async def fetch_new_members(client: MamifyClient, cfg: MamifyConfig, known_max: int) -> tuple[str, dict[str, parsing.Member], bool]:
    """People registered after the newest one already copied. Mamify lists
    the network newest first and ids grow with time, so the read stops at
    the first page holding someone already known. The flag says the check
    ran out of pages (a big batch): the full copy will catch the rest."""
    root = (await _root_member(client, cfg)).customer_id
    found: dict[str, parsing.Member] = {}
    for page in range(1, MAX_NEW_PAGES + 1):
        people, _ = await _network_page(client, root, page)
        fresh = [m for m in people if m.customer_id.isdigit() and int(m.customer_id) > known_max]
        for m in fresh:
            found[m.customer_id] = m
        if not people or len(fresh) < len(people):
            return root, found, False
    return root, found, True


def _display_names(m: parsing.Member) -> tuple[str, str]:
    if m.first_name or m.last_name:
        return m.first_name or "", m.last_name or ""
    if m.email:
        return m.email.split("@")[0], ""
    return f"Cliente {m.customer_id}", ""


def _top_down(root: str, members: dict[str, parsing.Member]) -> list[parsing.Member]:
    """Members ordered so every sponsor in the batch comes before its people.
    Sponsors outside the batch (the root, or people already copied) put
    their people at the start."""
    children: dict[str, list[str]] = defaultdict(list)
    for m in members.values():
        sponsor = m.sponsor_id if m.sponsor_id in members else root
        children[sponsor].append(m.customer_id)
    out, queue, seen = [], deque(children.get(root, [])), set()
    while queue:
        cid = queue.popleft()
        if cid in seen:
            continue
        seen.add(cid)
        out.append(members[cid])
        queue.extend(children.get(cid, []))
    # Cycles reported by the source would leave people out: keep them, at the top.
    out.extend(m for cid, m in members.items() if cid not in seen)
    return out


async def _claim_sync(db: AsyncSession, cfg: MamifyConfig) -> uuid.UUID | None:
    # A lease on the config row rather than an advisory lock: the session
    # commits many times during a sync and may change connection in between.
    now = utcnow()
    claimed = (await db.execute(
        update(MamifyConfig).where(
            MamifyConfig.id == cfg.id,
            or_(MamifyConfig.network_sync_started_at.is_(None), MamifyConfig.network_sync_started_at < now - SYNC_LEASE),
        ).values(network_sync_started_at=now).returning(MamifyConfig.id)
    )).scalar_one_or_none()
    await db.commit()
    return claimed


async def _release_sync(db: AsyncSession, claimed: uuid.UUID) -> None:
    await db.execute(update(MamifyConfig).where(MamifyConfig.id == claimed).values(
        network_sync_started_at=None, network_sync_progress={}))
    await db.commit()


async def sync_network(db: AsyncSession, organization_id: uuid.UUID) -> dict:
    """Full copy of the Mamify tree. Safe to run at any time: new people are
    added, changed sponsors are moved with their whole subtree (history
    kept), and people no longer in Mamify are flagged, not deleted, because
    their points and commissions are history."""
    cfg = await get_config(db, organization_id)
    await db.commit()
    claimed = await _claim_sync(db, cfg)
    if claimed is None:
        raise MamifyError("Una copia della rete è già in corso.")
    try:
        client = client_for(cfg)
        try:
            root, members = await fetch_network(db, client, cfg)
            await refresh_catalog(db, cfg, client)
        except MamifyApiError as exc:
            await _record_error(db, cfg, f"Rete: {exc}")
            raise MamifyError(str(exc)) from exc
        await _set_progress(db, claimed, {"phase": "apply", "people": len(members)})
        result = await _apply_network(db, cfg, root, members, full=True)
        result["calls"] = client.calls
        cfg = await get_config(db, organization_id)
        now = utcnow()
        cfg.last_network_sync_at = cfg.last_new_members_at = now
        cfg.last_network_sync_result = result
        if not result["errors"]:
            cfg.last_error = None
        await db.commit()
        # People who were missing when their orders arrived may be here now.
        await retry_waiting_orders(db, organization_id)
        return result
    except BaseException:
        await db.rollback()
        raise
    finally:
        await _release_sync(db, claimed)


async def sync_new_members(db: AsyncSession, organization_id: uuid.UUID) -> dict:
    """Adds the people registered on Mamify since the last copy: one or two
    calls when nothing is new. Moves and departures wait for the full copy.
    Before the first full copy it does nothing."""
    cfg = await get_config(db, organization_id)
    await db.commit()
    known_max = await db.scalar(select(func.max(func.cast(MamifyMember.mamify_customer_id, BigInteger))).where(
        MamifyMember.organization_id == organization_id, MamifyMember.mamify_customer_id.regexp_match(r"^\d+$")))
    if not known_max:
        return {"skipped": "Nessuna copia completa della rete ancora fatta."}
    claimed = await _claim_sync(db, cfg)
    if claimed is None:
        return {"skipped": "Una copia della rete è già in corso."}
    try:
        client = client_for(cfg)
        try:
            root, members, truncated = await fetch_new_members(client, cfg, int(known_max))
        except MamifyApiError as exc:
            await _record_error(db, cfg, f"Rete (nuovi iscritti): {exc}")
            raise MamifyError(str(exc)) from exc
        result = await _apply_network(db, cfg, root, members, full=False) if members else {
            "members": 0, "created": 0, "moved": 0, "updated": 0, "missing": 0, "errors": [], "error_count": 0}
        result.update({"calls": client.calls, "truncated": truncated})
        cfg = await get_config(db, organization_id)
        cfg.last_new_members_at = utcnow()
        await db.commit()
        if result["created"]:
            await retry_waiting_orders(db, organization_id)
        return result
    except BaseException:
        await db.rollback()
        raise
    finally:
        await _release_sync(db, claimed)


#: A branch bigger than this is left to the full copy (about 2 calls a
#: second of 50 people each: 10,000 people is 200 calls, under 4 minutes).
BRANCH_MAX_PEOPLE = 10_000
#: People who left a branch are looked up one by one, up to this many.
BRANCH_MAX_LOOKUPS = 40
#: Minimum time between two branch updates of the same person.
BRANCH_COOLDOWN_ADMIN = timedelta(minutes=1)
BRANCH_COOLDOWN_SELF = timedelta(minutes=15)


async def _find(client: MamifyClient, customer_id: str) -> tuple[parsing.Member | None, str | None]:
    """A person and their sponsor id, by Mamify id (rag/customer/find)."""
    try:
        found = await client.call("plugins/mamify/rag/customer/find", _customer_ref(customer_id))
    except MamifyApiError as exc:
        if exc.code == "customer_not_found":
            return None, None
        raise
    person = parsing.member(parsing.customer_of(found))
    sponsor = found.get("sponsor") if isinstance(found, dict) else None
    sponsor_id = parsing.ident(sponsor.get("id")) if isinstance(sponsor, dict) else None
    if person is not None:
        person.sponsor_id = sponsor_id
    return person, sponsor_id


def branch_view(row: MamifyMember | None) -> dict:
    if row is None:
        return {"available": False}
    return {"available": True, "mamify_customer_id": row.mamify_customer_id,
            "requested_at": row.branch_sync_requested_at, "synced_at": row.branch_synced_at,
            "running": bool(row.branch_sync_requested_at and (
                row.branch_synced_at is None or row.branch_synced_at < row.branch_sync_requested_at)),
            "result": row.branch_sync_result or {}}


async def member_of_agent(db: AsyncSession, organization_id: uuid.UUID, agent_id: uuid.UUID) -> MamifyMember | None:
    return await db.scalar(select(MamifyMember).where(
        MamifyMember.organization_id == organization_id, MamifyMember.agent_id == agent_id))


async def request_branch_sync(db: AsyncSession, organization_id: uuid.UUID, agent_id: uuid.UUID, *,
                              by_self: bool = False) -> dict:
    """Queues the update of one person's branch (see sync_branch)."""
    cfg = await get_config(db, organization_id)
    if not (cfg.enabled and cfg.api_key and cfg.root_customer):
        raise MamifyError("Il collegamento con Mamify non è attivo.")
    row = await member_of_agent(db, organization_id, agent_id)
    if row is None:
        raise MamifyError("Questa persona non viene da Mamify: non c'è una rete Mamify da aggiornare.")
    view = branch_view(row)
    now = utcnow()
    cooldown = BRANCH_COOLDOWN_SELF if by_self else BRANCH_COOLDOWN_ADMIN
    stale = row.branch_sync_requested_at and now - row.branch_sync_requested_at > SYNC_LEASE
    if view["running"] and not stale:
        return {**view, "queued": False}
    if row.branch_synced_at and now - row.branch_synced_at < cooldown:
        wait = int((cooldown - (now - row.branch_synced_at)).total_seconds() // 60) + 1
        raise MamifyError(f"Rete appena aggiornata: riprova tra {wait} minuti.")
    row.branch_sync_requested_at = now
    await db.commit()
    from app.celery_app import mamify_branch_task

    mamify_branch_task.delay(str(organization_id), str(agent_id))
    return {**branch_view(row), "queued": True}


async def sync_branch(db: AsyncSession, organization_id: uuid.UUID, agent_id: uuid.UUID) -> dict:
    """Brings one person's branch in line with Mamify, read only: the
    person (and their sponsor), then everyone below them (scope "all", 50 a
    call). New people are added, changed sponsors moved; people who are in
    the SOS branch but no longer in the Mamify one are looked up one by one:
    moved under their new sponsor, or flagged as gone. Waits for nothing:
    if a full copy is running it says so and stops."""
    cfg = await get_config(db, organization_id)
    row = await member_of_agent(db, organization_id, agent_id)
    if row is None:
        raise MamifyError("Questa persona non viene da Mamify.")
    row_id, cid, base_level = row.id, row.mamify_customer_id, row.mamify_level
    await db.commit()

    async def finish(result: dict) -> dict:
        await db.execute(update(MamifyMember).where(MamifyMember.id == row_id).values(
            branch_synced_at=utcnow(), branch_sync_result=json.loads(json.dumps(result, default=str))))
        await db.commit()
        return result

    claimed = await _claim_sync(db, cfg)
    if claimed is None:
        return await finish({"skipped": "È in corso un'altra lettura della rete: riprova tra qualche minuto."})
    try:
        client = client_for(cfg)
        try:
            root = (await _root_member(client, cfg)).customer_id
            person, _ = await _find(client, cid)
            if person is None:
                await db.execute(update(MamifyMember).where(MamifyMember.id == row_id).values(present=False))
                await db.commit()
                return await finish({"gone": True, "calls": client.calls,
                                     "message": "La persona non c'è più su Mamify: segnata come uscita."})
            members: dict[str, parsing.Member] = {cid: person}
            total = None
            for page in range(1, BRANCH_MAX_PEOPLE // PAGE_SIZE + 2):
                answer = await client.call("plugins/mamify/rag/customer/network",
                                           {"customer_id": _cid(cid), "scope": "all", "page": page, "limit": PAGE_SIZE})
                total = parsing.total_count(answer)
                if total is not None and total > BRANCH_MAX_PEOPLE:
                    return await finish({"skipped": f"Ramo troppo grande ({total} persone): lo aggiorna la copia "
                                                    "completa di ogni notte, o il pulsante nella pagina Mamify.",
                                         "calls": client.calls})
                people = [m for m in (parsing.member(r, parent_hint=cid) for r in parsing.items(answer))
                          if m and m.customer_id != cid]
                for m in people:
                    if m.level is not None and base_level is not None:
                        m.level += base_level  # Mamify counts levels from the person asked for
                    members[m.customer_id] = m
                if not people or (total is not None and page * PAGE_SIZE >= total):
                    break

            # In the SOS branch but not in the Mamify one any more.
            below = select(MamifyMember.mamify_customer_id).join(
                NetworkClosure, (NetworkClosure.descendant_agent_id == MamifyMember.agent_id)
                & (NetworkClosure.effective_to.is_(None)) & (NetworkClosure.depth > 0),
            ).where(MamifyMember.organization_id == organization_id, NetworkClosure.ancestor_agent_id == agent_id,
                    MamifyMember.present.is_(True))
            left = [x for x in (await db.execute(below)).scalars() if x not in members]
            gone: list[str] = []
            for other in left[:BRANCH_MAX_LOOKUPS]:
                found, _ = await _find(client, other)
                if found is None:
                    gone.append(other)
                else:
                    members[found.customer_id] = found
        except MamifyApiError as exc:
            await _record_error(db, cfg, f"Rete (ramo {cid}): {exc}")
            raise MamifyError(str(exc)) from exc

        for m in members.values():
            if m.sponsor_id is None:
                m.sponsor_id = root
        result = await _apply_network(db, cfg, root, members, full=False, moves=True)
        if gone:
            await db.execute(update(MamifyMember).where(
                MamifyMember.organization_id == organization_id, MamifyMember.mamify_customer_id.in_(gone),
            ).values(present=False))
            await db.commit()
        result.update({"calls": client.calls, "branch_total": total, "left_branch": len(left) - len(gone),
                       "missing": len(gone), "unchecked": max(0, len(left) - BRANCH_MAX_LOOKUPS)})
        result.pop("root", None)
        if result["created"]:
            await retry_waiting_orders(db, organization_id)
        return await finish(result)
    except BaseException:
        await db.rollback()
        raise
    finally:
        await _release_sync(db, claimed)


def _fingerprint(m: parsing.Member, sponsor: str | None) -> dict:
    return {"first_name": m.first_name or None, "last_name": m.last_name or None, "email": m.email, "phone": m.phone,
            "level": m.level, "sponsor": sponsor, "registered_at": m.registered_at}


def _stored_fingerprint(row: MamifyMember) -> dict:
    return {"first_name": row.first_name, "last_name": row.last_name, "email": row.email, "phone": row.phone,
            "level": row.mamify_level, "sponsor": row.sponsor_customer_id, "registered_at": row.registered_at}


async def _apply_network(db: AsyncSession, cfg: MamifyConfig, root: str, members: dict[str, parsing.Member],
                         *, full: bool, moves: bool | None = None) -> dict:
    """Writes the people read from Mamify into the SOS tree.

    `full` means `members` is the whole tree: only then are absent people
    flagged. Changed sponsors are moved when `moves` (default: `full`): a
    branch read knows every sponsor in it, a batch of new registrations
    only adds people. Unchanged people cost no write."""
    if moves is None:
        moves = full
    # Plain values: a rollback after one bad person expires every ORM object.
    org, cfg_id = cfg.organization_id, cfg.id
    actor = cfg.sync_actor_user_id
    now = utcnow()
    existing = {m.mamify_customer_id: m for m in (await db.execute(
        select(MamifyMember).where(MamifyMember.organization_id == org)
    )).scalars()}
    parents = await affiliate_service.parent_map(db, org)
    agents = await affiliate_service.agents_by_id(db, org)
    created = moved = updated = 0
    errors: list[str] = []
    agent_of: dict[str, uuid.UUID] = {cid: m.agent_id for cid, m in existing.items()}

    for n, m in enumerate(_top_down(root, members), start=1):
        sponsor_cid = m.sponsor_id if m.sponsor_id and m.sponsor_id != root and (
            m.sponsor_id in members or m.sponsor_id in agent_of) else None
        parent_agent = agent_of.get(sponsor_cid) if sponsor_cid else None
        first, last = _display_names(m)
        row = existing.get(m.customer_id)
        try:
            changed = False
            if row is None:
                agent = await network_service.create_agent(
                    db, organization_id=org, first_name=first[:120], last_name=last[:120],
                    promoter_code=f"MF{m.customer_id}"[:32], parent_agent_id=parent_agent,
                    joined_at=m.registered_at or now, status="ACTIVE",
                )
                row = MamifyMember(organization_id=org, mamify_customer_id=m.customer_id, agent_id=agent.id,
                                   last_seen_at=now)
                db.add(row)
                existing[m.customer_id] = row
                agent_of[m.customer_id] = agent.id
                parents[agent.id] = parent_agent
                agents[agent.id] = agent
                created += 1
                changed = True
            else:
                if moves and parents.get(row.agent_id) != parent_agent:
                    if actor is None:
                        errors.append(f"{first} {last}: sponsor cambiato su Mamify, ma manca l'account che autorizza "
                                      "lo spostamento (salva di nuovo la configurazione).")
                    else:
                        await network_service.move_agent(
                            db, organization_id=org, agent_id=row.agent_id, new_parent_agent_id=parent_agent,
                            requested_by=actor, approved_by=actor,
                            reason="Sincronizzazione Mamify: lo sponsor è cambiato su Mamify.",
                        )
                        parents[row.agent_id] = parent_agent
                        moved += 1
                        changed = True
                agent = agents.get(row.agent_id)
                if agent is not None and (agent.first_name, agent.last_name) != (first[:120], last[:120]):
                    agent.first_name, agent.last_name = first[:120], last[:120]
                    agent.display_name = f"{first} {last}".strip()[:255]
                    updated += 1
                    changed = True
            if changed or _fingerprint(m, sponsor_cid) != _stored_fingerprint(row) or not row.present:
                row.sponsor_customer_id = sponsor_cid
                row.email, row.first_name, row.last_name, row.phone = m.email, m.first_name or None, m.last_name or None, m.phone
                row.mamify_level, row.registered_at, row.present = m.level, m.registered_at, True
                row.raw = json.loads(json.dumps(m.raw, default=str))
                changed = True
            row.last_seen_at = now
            if changed or n % 500 == 0:
                await db.commit()
        except Exception as exc:  # one bad person must not stop the whole tree
            await db.rollback()
            logger.exception("Mamify sync failed for customer %s", m.customer_id)
            errors.append(f"{first} {last} ({m.customer_id}): {exc}")
            existing = {x.mamify_customer_id: x for x in (await db.execute(
                select(MamifyMember).where(MamifyMember.organization_id == org)
            )).scalars()}
            agent_of = {cid: x.agent_id for cid, x in existing.items()}
            agents = await affiliate_service.agents_by_id(db, org)
        if n % 1000 == 0:
            await _set_progress(db, cfg_id, {"phase": "apply", "done": n, "people": len(members)})
    await db.commit()

    missing = 0
    if full:
        for cid, row in existing.items():
            if cid not in members and row.present:
                row.present = False
                missing += 1
        await db.commit()
    await _refresh_direct_counts(db, org)
    return {"members": len(members), "created": created, "moved": moved, "updated": updated,
            "missing": missing, "root": root, "errors": errors[:30], "error_count": len(errors), "full": full}


async def _refresh_direct_counts(db: AsyncSession, org: uuid.UUID) -> None:
    """How many people each person brought in: the order poller reads people
    with a downline more often."""
    counts = (select(MamifyMember.sponsor_customer_id.label("cid"), func.count().label("n"))
              .where(MamifyMember.organization_id == org, MamifyMember.present.is_(True),
                     MamifyMember.sponsor_customer_id.is_not(None))
              .group_by(MamifyMember.sponsor_customer_id).subquery())
    await db.execute(update(MamifyMember).where(MamifyMember.organization_id == org, MamifyMember.direct_count != 0)
                     .values(direct_count=0))
    await db.execute(update(MamifyMember).where(
        MamifyMember.organization_id == org, MamifyMember.mamify_customer_id == counts.c.cid,
    ).values(direct_count=counts.c.n))
    await db.commit()


async def members_by_agent(db: AsyncSession, organization_id: uuid.UUID) -> dict[uuid.UUID, MamifyMember]:
    return {m.agent_id: m for m in (await db.execute(
        select(MamifyMember).where(MamifyMember.organization_id == organization_id)
    )).scalars()}


# --- Orders ------------------------------------------------------------------


def _body_hash(event_type: str | None, payload: Any) -> str:
    canonical = json.dumps({"t": event_type, "p": payload}, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


async def config_by_token(db: AsyncSession, token: str) -> MamifyConfig | None:
    if not token or len(token) < 20:
        return None
    cfg = (await db.execute(select(MamifyConfig).where(MamifyConfig.webhook_token == token))).scalar_one_or_none()
    if cfg is None or not secrets.compare_digest(cfg.webhook_token, token):
        return None
    return cfg


def _queue_new_members(organization_id: uuid.UUID) -> bool:
    """Asks the worker for the newest-registrations check, now."""
    try:
        from app.celery_app import mamify_new_members_task

        mamify_new_members_task.delay(str(organization_id))
        return True
    except Exception:  # the periodic check runs anyway in a few minutes
        logger.exception("Could not queue the Mamify new-members check")
        return False


async def handle_webhook(db: AsyncSession, cfg: MamifyConfig, event_type: str | None, payload: Any) -> str:
    """Stores the call first, then handles it. An exact redelivery is dropped
    by the UNIQUE hash; a different call about the same order is handled, and
    the order's own idempotency keeps it from counting twice."""
    if not isinstance(payload, dict):
        payload = {"body": payload}
    event_type = event_type or payload.get("type") or payload.get("event")
    org = cfg.organization_id
    event = MamifyWebhookEvent(organization_id=org, event_type=event_type,
                               body_hash=_body_hash(event_type, payload), payload=json.loads(json.dumps(payload, default=str)))
    db.add(event)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        return "duplicate"
    event_id = event.id
    try:
        if event_type in ("orders/new", "orders/status_update") or "order" in payload:
            parsed = parsing.order(payload)
            if parsed is None:
                raise MamifyError("Avviso d'ordine senza numero d'ordine.")
            await ingest_order(db, cfg, parsed, payload, source="webhook")
            outcome = "order"
        elif event_type == "customers/new":
            # The body's sponsor field is not documented: the check reads
            # the new person from the network, sponsor included.
            outcome = "customer" if _queue_new_members(org) else "customer-later"
        else:
            outcome = "ignored"
        stored = await db.get(MamifyWebhookEvent, event_id)
        stored.processed_at = utcnow()
        await db.commit()
        return outcome
    except Exception as exc:  # the event is stored, the error is shown on the admin page
        await db.rollback()
        logger.exception("Mamify webhook failed")
        stored = await db.get(MamifyWebhookEvent, event_id)
        if stored is not None:
            stored.error = str(exc)[:4000]
            await db.commit()
        return "error"


def _catalog(cfg: MamifyConfig) -> list[dict]:
    return list((cfg.product_catalog or {}).get("items") or [])


def is_relevant(parsed: parsing.Order, cfg: MamifyConfig, mapped: set[str]) -> bool:
    """An order worth keeping: a line of an SOS app, or of a mapped product.
    Everything else a person buys on Mamify (gift cards, other apps) is not
    stored at all."""
    apps = set(cfg.order_apps or [])
    catalog = _catalog(cfg)
    for line in parsed.lines:
        if line.app and line.app in apps:
            return True
        pid = parsing.resolve_line(line, catalog)
        if pid and pid in mapped:
            return True
    return False


async def ingest_order(db: AsyncSession, cfg: MamifyConfig, parsed: parsing.Order, raw: dict, *, source: str) -> MamifyOrder:
    org = cfg.organization_id
    row = (await db.execute(
        select(MamifyOrder).where(MamifyOrder.organization_id == org, MamifyOrder.mamify_order_id == parsed.order_id)
        .with_for_update()
    )).scalar_one_or_none()
    if row is None:
        row = MamifyOrder(organization_id=org, mamify_order_id=parsed.order_id, source=source, raw={})
        db.add(row)
        try:
            await db.flush()
        except IntegrityError:
            # The same order arriving twice at once: the other request owns it.
            await db.rollback()
            return (await db.execute(select(MamifyOrder).where(
                MamifyOrder.organization_id == org, MamifyOrder.mamify_order_id == parsed.order_id))).scalar_one()
    row.raw = _merge_raw(row.raw or {}, raw)
    row.buyer_customer_id = parsed.buyer_id or row.buyer_customer_id
    row.status_code = parsed.status_code or row.status_code
    row.status_title = parsed.status_title or row.status_title
    row.total = parsed.total if parsed.total is not None else row.total
    row.ordered_at = parsed.ordered_at or row.ordered_at
    row_id = row.id
    await db.commit()
    return await process_order(db, cfg, row_id)


def _merge_raw(stored: dict, incoming: dict) -> dict:
    """Keeps one shape, {"order": {...}, "status": ...}, whatever the source.

    A status webhook can carry less than the first one, so order fields are
    merged, not replaced. The outer status is the webhook's "new status"; a
    read from the service API carries the status inside the order, and then
    the outer one, older, is dropped so it cannot win."""
    incoming = json.loads(json.dumps(incoming, default=str))
    if isinstance(incoming.get("order"), dict):
        order_part, status_part = incoming["order"], incoming.get("status")
    else:
        order_part, status_part = incoming, None
    merged_order = {**(stored.get("order") or {}), **order_part}
    out = {"order": merged_order}
    if status_part is not None:
        out["status"] = status_part
    elif "status" in stored and not any(k in order_part for k in ("status", "status_id", "state", "stato")):
        out["status"] = stored["status"]
    if "old_status" in incoming:
        out["old_status"] = incoming["old_status"]
    return out


async def _complete_order(client: MamifyClient, buyer_id: str | None, order_id: str) -> tuple[parsing.Order, dict] | None:
    """The order as the service API describes it, for webhooks that do not
    list the products or the buyer."""
    if not buyer_id:
        return None
    answer = await client.call("plugins/mamify/rag/customer/orders",
                               {"customer_id": _cid(buyer_id), "order_id": _cid(order_id)})
    for item in parsing.items(answer) or ([answer] if isinstance(answer, dict) else []):
        parsed = parsing.order(item)
        if parsed and parsed.order_id == order_id:
            return parsed, item
    return None


async def _set_state(db: AsyncSession, row: MamifyOrder, state: str, message: str | None) -> MamifyOrder:
    row.state, row.message = state, (message or None) and message[:1000]
    await db.commit()
    return row


async def process_order(db: AsyncSession, cfg: MamifyConfig, order_row_id: uuid.UUID) -> MamifyOrder:
    """Turns a stored order into operations, or reverses them. Re-running it
    is harmless: lines already applied find their operation by key."""
    row = await db.get(MamifyOrder, order_row_id)
    parsed = parsing.order(row.raw or {}) or parsing.Order(row.mamify_order_id, None, None, None, None, None, None, [])
    parsed.buyer_id = parsed.buyer_id or row.buyer_customer_id
    parsed.status_code, parsed.status_title = row.status_code, row.status_title
    paid = parsed.paid is True or parsing.matches_status(parsed, cfg.paid_statuses)
    cancelled = parsing.matches_status(parsed, cfg.cancelled_statuses)

    if cancelled:
        if row.state == "CANCELLED":
            return row
        return await _cancel_order(db, row, parsed)
    # Once applied, later steps of the order (shipped, delivered...) change
    # nothing: only a cancellation undoes it.
    if row.state == "APPLIED":
        return row
    if not paid:
        if not (cfg.paid_statuses or parsed.paid is not None):
            return await _set_state(db, row, "RECEIVED", "Nessuno stato «pagato» configurato: indicalo nel collegamento Mamify.")
        return await _set_state(db, row, "RECEIVED", f"In attesa di pagamento (stato «{parsed.status_title or parsed.status_code or '—'}»).")

    if not parsed.lines or not parsed.buyer_id:
        try:
            full = await _complete_order(client_for(cfg), row.buyer_customer_id, row.mamify_order_id)
        except (MamifyApiError, MamifyError) as exc:
            return await _set_state(db, row, "ERROR", f"Dettaglio dell'ordine non leggibile da Mamify: {exc}")
        if full is not None:
            detail, item = full
            # Only the missing parts: the status stays the one just received.
            row.raw = {**(row.raw or {}), "order": {**item, **((row.raw or {}).get("order") or {})}}
            parsed.lines = parsed.lines or detail.lines
            parsed.buyer_id = parsed.buyer_id or detail.buyer_id
            row.buyer_customer_id = parsed.buyer_id
            await db.commit()
    if not parsed.lines:
        return await _set_state(db, row, "ERROR", "L'ordine non elenca prodotti leggibili.")

    # Plain values from here on: the affiliate service rolls back on some
    # refusals, and a rollback expires every ORM object in the session.
    org, order_no = row.organization_id, row.mamify_order_id
    mapping = {p.mamify_product_id: p.plan_code for p in (await db.execute(
        select(MamifyProductMap).where(MamifyProductMap.organization_id == org)
    )).scalars()}
    catalog = _catalog(cfg)
    for line in parsed.lines:
        line.product_id = parsing.resolve_line(line, catalog)
    lines = [(i, line, mapping[line.product_id]) for i, line in enumerate(parsed.lines)
             if line.product_id and line.product_id in mapping]
    if not lines:
        labels = ", ".join(sorted({line.label for line in parsed.lines}))
        return await _set_state(db, row, "IGNORED", f"Nessun prodotto abbinato al piano nell'ordine ({labels}).")
    buyer_row = (await db.execute(select(MamifyMember).where(
        MamifyMember.organization_id == org, MamifyMember.mamify_customer_id == parsed.buyer_id
    ))).scalar_one_or_none() if parsed.buyer_id else None
    if buyer_row is None:
        return await _set_state(db, row, "UNMATCHED",
                                f"Chi ha comprato (cliente Mamify {parsed.buyer_id or '?'}) non è ancora nella rete SOS: "
                                "l'ordine verrà riapplicato dopo la prossima copia della rete.")
    buyer = _Buyer(
        customer_id=buyer_row.mamify_customer_id, agent_id=buyer_row.agent_id, sponsor_id=buyer_row.sponsor_customer_id,
        name=" ".join(x for x in (buyer_row.first_name, buyer_row.last_name) if x) or buyer_row.email
        or f"Cliente {buyer_row.mamify_customer_id}",
        email=buyer_row.email, phone=buyer_row.phone,
    )

    plan = await affiliate_service.get_plan(db, org)
    index = product_index(plan.config)
    op_ids: list[str] = list(row.operation_ids or [])
    try:
        for i, line, code in lines:
            kind = ("MAMICASH_TOPUP" if code == TOPUP_CODE else "LICENSE_RESALE" if code == RESALE_CODE
                    else (index.get(code) or {}).get("kind"))
            if kind is None:
                raise MamifyError(f"Il prodotto Mamify {line.label} è abbinato a {code}, che non esiste nel piano.")
            if kind == "LICENSE_RESALE":
                # The company bought the licence itself: the seller is its
                # Mamify sponsor, the licence one of his (already assigned to
                # this company, or his oldest free one).
                seller_agent, client_id = await _seller_and_client(db, org, buyer)
                for unit in range(line.quantity):
                    op, _ = await license_register.record_external_resale(
                        db, organization_id=org, seller_agent_id=seller_agent, client_id=client_id,
                        idempotency_key=f"MAMIFY:{order_no}:{i}:{unit + 1}", note=f"Ordine Mamify {order_no}",
                    )
                    op_ids.append(str(op.id))
                continue
            if kind in ("PACK_SALE", "MAMICASH_TOPUP"):
                seller_agent, client_id = await _seller_and_client(db, org, buyer)
                if kind == "MAMICASH_TOPUP":
                    value = line.amount if line.amount is not None else parsed.total
                    op, _ = await affiliate_service.record_external_operation(
                        db, organization_id=org, plan_code=code, agent_id=seller_agent,
                        client_id=client_id, topup_amount=value, idempotency_key=f"MAMIFY:{order_no}:{i}",
                        note=f"Ordine Mamify {order_no}",
                    )
                    op_ids.append(str(op.id))
                    continue
            else:
                seller_agent, client_id = buyer.agent_id, None
            for unit in range(line.quantity):
                op, _ = await affiliate_service.record_external_operation(
                    db, organization_id=org, plan_code=code, agent_id=seller_agent, client_id=client_id,
                    idempotency_key=f"MAMIFY:{order_no}:{i}:{unit + 1}", note=f"Ordine Mamify {order_no}",
                )
                op_ids.append(str(op.id))
    except (affiliate_service.AffiliateError, MamifyError) as exc:
        row = await db.get(MamifyOrder, order_row_id)
        row.operation_ids = sorted(set(op_ids))
        return await _set_state(db, row, "ERROR", str(exc))
    row = await db.get(MamifyOrder, order_row_id)
    row.operation_ids = sorted(set(op_ids))
    return await _set_state(db, row, "APPLIED", None)


@dataclass(frozen=True)
class _Buyer:
    customer_id: str
    agent_id: uuid.UUID
    sponsor_id: str | None
    name: str
    email: str | None
    phone: str | None


async def _seller_and_client(db: AsyncSession, org: uuid.UUID, buyer: _Buyer) -> tuple[uuid.UUID, uuid.UUID]:
    """For a Pack or a MamiCash top-up the buyer is a client company and the
    seller is the Digital Ambassador who brought it in: its Mamify sponsor."""
    if not buyer.sponsor_id:
        raise MamifyError("L'impresa che ha comprato è in cima alla rete: non ha un Digital Ambassador a cui attribuire la vendita.")
    sponsor_agent = await db.scalar(select(MamifyMember.agent_id).where(
        MamifyMember.organization_id == org, MamifyMember.mamify_customer_id == buyer.sponsor_id))
    if sponsor_agent is None:
        raise MamifyError("Lo sponsor dell'impresa non è nella rete SOS.")
    client = (await db.execute(select(AffiliateClient).where(
        AffiliateClient.organization_id == org, AffiliateClient.mamify_customer_id == buyer.customer_id,
    ))).scalar_one_or_none()
    if client is None and buyer.email:
        # A company the ambassador typed in himself (to assign it a licence)
        # is the same company when the email matches: link it, do not
        # create a second one.
        client = (await db.execute(select(AffiliateClient).where(
            AffiliateClient.organization_id == org, AffiliateClient.agent_id == sponsor_agent,
            AffiliateClient.mamify_customer_id.is_(None),
            func.lower(AffiliateClient.email) == buyer.email.strip().lower(),
        ).order_by(AffiliateClient.created_at).limit(1))).scalar_one_or_none()
        if client is not None:
            client.mamify_customer_id = buyer.customer_id
    if client is None:
        client = AffiliateClient(organization_id=org, agent_id=sponsor_agent, company_name=buyer.name[:255],
                                 email=buyer.email, phone=buyer.phone, mamify_customer_id=buyer.customer_id)
        db.add(client)
    else:
        # The company follows its Mamify sponsor if it was moved.
        client.agent_id = sponsor_agent
    await db.flush()
    client_id = client.id
    await db.commit()
    return sponsor_agent, client_id


async def _cancel_order(db: AsyncSession, row: MamifyOrder, parsed: parsing.Order) -> MamifyOrder:
    reason = f"Ordine Mamify {row.mamify_order_id} annullato o rimborsato (stato «{parsed.status_title or parsed.status_code}»)."
    problems = []
    row_id, org, op_ids = row.id, row.organization_id, list(row.operation_ids or [])
    for op_id in op_ids:
        op = await db.get(AffiliateOperation, uuid.UUID(op_id))
        if op is None or op.status != "CONFIRMED":
            continue
        try:
            await affiliate_service.reverse_operation(db, organization_id=org, operation_id=op.id,
                                                      actor_user_id=None, reason=reason)
        except affiliate_service.AffiliateError as exc:
            problems.append(str(exc))
    row = await db.get(MamifyOrder, row_id)
    if problems:
        return await _set_state(db, row, "ERROR", "Rettifica non completa: " + " ".join(problems))
    return await _set_state(db, row, "CANCELLED", reason)


async def retry_waiting_orders(db: AsyncSession, organization_id: uuid.UUID) -> int:
    """Re-applies orders that could not be applied yet (buyer not in the
    tree, product not mapped, temporary error)."""
    cfg = await get_config(db, organization_id)
    ids = list((await db.execute(select(MamifyOrder.id).where(
        MamifyOrder.organization_id == organization_id, MamifyOrder.state.in_(("UNMATCHED", "ERROR", "IGNORED", "RECEIVED")),
    ).order_by(MamifyOrder.created_at).limit(500))).scalars())
    for order_id in ids:
        await process_order(db, cfg, order_id)
    return len(ids)


async def _read_member_orders(db: AsyncSession, cfg: MamifyConfig, client: MamifyClient, customer_id: str,
                              mapped: set[str]) -> int:
    """One call: the person's latest 50 orders. Only the relevant ones are
    stored; known ones are refreshed (a status may have changed)."""
    answer = await client.call("plugins/mamify/rag/customer/orders",
                               {"customer_id": _cid(customer_id), "page": 1, "limit": PAGE_SIZE})
    known = set((await db.execute(select(MamifyOrder.mamify_order_id).where(
        MamifyOrder.organization_id == cfg.organization_id, MamifyOrder.buyer_customer_id == customer_id,
    ))).scalars())
    seen = 0
    for item in parsing.items(answer):
        parsed = parsing.order(item)
        if parsed is None:
            continue
        if parsed.order_id not in known and not is_relevant(parsed, cfg, mapped):
            continue
        parsed.buyer_id = parsed.buyer_id or customer_id
        await ingest_order(db, cfg, parsed, {**item, "customer_id": parsed.buyer_id}, source="sync")
        seen += 1
    return seen


async def poll_orders(db: AsyncSession, organization_id: uuid.UUID, *, calls: int) -> dict:
    """Reads the latest orders of up to `calls` people, one call each.

    The service API has no "all orders" list, only one person's orders, so
    the whole network is read in turn. Half of the calls go to the people
    who matter most for the plan (a downline, or an order already stored)
    once their last check is older than PRIORITY_EVERY; the rest to the
    people checked longest ago (never checked first)."""
    cfg = await get_config(db, organization_id)
    await db.commit()
    if calls <= 0:
        return {"people": 0, "orders": 0, "calls": 0}
    client = client_for(cfg)
    now = utcnow()
    mapped = {p.mamify_product_id for p in await list_product_map(db, organization_id)}
    buyers = select(MamifyOrder.buyer_customer_id).where(
        MamifyOrder.organization_id == organization_id, MamifyOrder.buyer_customer_id.is_not(None))
    base = select(MamifyMember.id, MamifyMember.mamify_customer_id).where(
        MamifyMember.organization_id == organization_id, MamifyMember.present.is_(True))
    priority = list((await db.execute(base.where(
        or_(MamifyMember.direct_count > 0, MamifyMember.mamify_customer_id.in_(buyers)),
        or_(MamifyMember.orders_checked_at.is_(None), MamifyMember.orders_checked_at < now - PRIORITY_EVERY),
    ).order_by(MamifyMember.orders_checked_at.asc().nulls_first()).limit((calls + 1) // 2))).all())
    taken = [r[0] for r in priority]
    rest_q = base.where(MamifyMember.id.not_in(taken)) if taken else base
    rest = list((await db.execute(rest_q.order_by(MamifyMember.orders_checked_at.asc().nulls_first())
                                  .limit(calls - len(priority)))).all())
    people = orders = 0
    for member_id, customer_id in priority + rest:
        try:
            orders += await _read_member_orders(db, cfg, client, customer_id, mapped)
        except MamifyApiError as exc:
            await db.rollback()
            cfg = await get_config(db, organization_id)
            await _record_error(db, cfg, f"Ordini: {exc}")
            if exc.code in ("rate_limited", "wrong_api_key", "insufficient_permissions", "network"):
                break
        await db.execute(update(MamifyMember).where(MamifyMember.id == member_id).values(orders_checked_at=utcnow()))
        await db.commit()
        people += 1
    cfg = await get_config(db, organization_id)
    cfg.last_orders_sync_at = utcnow()
    await db.commit()
    return {"people": people, "orders": orders, "calls": client.calls}


OWN_ORDERS_EVERY = timedelta(minutes=2)


async def request_own_orders(db: AsyncSession, organization_id: uuid.UUID, agent_id: uuid.UUID) -> bool:
    """Opening one's own dashboard re-reads one's latest orders from Mamify
    (one read-only call, in the `mamify` queue), at most every
    OWN_ORDERS_EVERY. The network poller reaches each of 50,000 people only
    about once an hour; this way a purchase shows up a few seconds after its
    buyer looks for it. True when a read was queued."""
    cfg = await get_config(db, organization_id)
    if not (cfg.enabled and cfg.api_key):
        return False
    row = await member_of_agent(db, organization_id, agent_id)
    if row is None:
        return False
    now = utcnow()
    if row.orders_checked_at and now - row.orders_checked_at < OWN_ORDERS_EVERY:
        return False
    # Claims the slot first, so a burst of page loads queues a single read.
    row.orders_checked_at = now
    customer_id = row.mamify_customer_id
    await db.commit()
    from app.celery_app import mamify_own_orders_task

    mamify_own_orders_task.delay(str(organization_id), customer_id)
    return True


async def read_own_orders(db: AsyncSession, organization_id: uuid.UUID, customer_id: str) -> dict:
    """The read queued by request_own_orders."""
    cfg = await get_config(db, organization_id)
    await db.commit()
    client = client_for(cfg)
    mapped = {p.mamify_product_id for p in await list_product_map(db, organization_id)}
    try:
        orders = await _read_member_orders(db, cfg, client, customer_id, mapped)
    except MamifyApiError as exc:
        await db.rollback()
        return {"error": str(exc)}
    await db.commit()
    return {"orders": orders, "calls": client.calls}


async def list_own_orders(db: AsyncSession, organization_id: uuid.UUID, agent_id: uuid.UUID,
                          limit: int = 100) -> list[dict]:
    """The Mamify orders a Digital Ambassador made, as last read from Mamify,
    with what SOS Affiliate made of each (points, licences). Local data only."""
    row = await member_of_agent(db, organization_id, agent_id)
    if row is None:
        return []
    orders = list((await db.execute(
        select(MamifyOrder).where(MamifyOrder.organization_id == organization_id,
                                  MamifyOrder.buyer_customer_id == row.mamify_customer_id)
        .order_by(MamifyOrder.ordered_at.desc().nulls_last()).limit(limit))).scalars())
    op_ids = {uuid.UUID(str(i)) for o in orders for i in (o.operation_ids or [])}
    ops = {op.id: op for op in (await db.execute(
        select(AffiliateOperation).where(AffiliateOperation.id.in_(op_ids)))).scalars()} if op_ids else {}
    out = []
    for o in orders:
        raw = (o.raw or {}).get("order") or {}
        mine = [ops[uuid.UUID(str(i))] for i in (o.operation_ids or []) if uuid.UUID(str(i)) in ops]
        out.append({
            "mamify_order_id": o.mamify_order_id, "ordered_at": o.ordered_at, "total": o.total,
            "status": o.status_title, "paid": raw.get("paid"), "state": o.state,
            "products": [{"name": str(p.get("name") or ""), "quantity": p.get("quantity") or 1, "price": p.get("price")}
                         for p in raw.get("products") or [] if isinstance(p, dict)],
            "bc_points": sum((op.bc_points or 0) for op in mine if op.status == "CONFIRMED"),
            "operations": [{"id": op.id, "kind": op.kind, "status": op.status} for op in mine],
        })
    return out


async def recheck_all_orders(db: AsyncSession, organization_id: uuid.UUID) -> int:
    """Puts everyone back at the front of the order poller's line."""
    result = await db.execute(update(MamifyMember).where(MamifyMember.organization_id == organization_id)
                              .values(orders_checked_at=None))
    await db.commit()
    return result.rowcount or 0


async def orders_coverage(db: AsyncSession, organization_id: uuid.UUID) -> dict:
    present = (MamifyMember.organization_id == organization_id, MamifyMember.present.is_(True))
    total = await db.scalar(select(func.count()).select_from(MamifyMember).where(*present)) or 0
    checked = await db.scalar(select(func.count()).select_from(MamifyMember).where(
        *present, MamifyMember.orders_checked_at.is_not(None))) or 0
    oldest = await db.scalar(select(func.min(MamifyMember.orders_checked_at)).where(*present))
    return {"people": total, "checked_once": checked, "oldest_check": oldest if total and checked == total else None}


# --- Products ----------------------------------------------------------------


async def refresh_catalog(db: AsyncSession, cfg: MamifyConfig, client: MamifyClient | None = None) -> list[dict]:
    """The products of the SOS apps (rag/products/search), kept to match
    order lines, which carry only app, name and price."""
    client = client or client_for(cfg)
    found: dict[str, dict] = {}
    for app in cfg.order_apps or DEFAULT_ORDER_APPS:
        for page in range(1, 21):
            answer = await client.call("plugins/mamify/rag/products/search",
                                       {"app": app, "page": page, "limit": PAGE_SIZE})
            rows = parsing.items(answer)
            for p in rows:
                pid = parsing.ident(p.get("id"))
                if not pid:
                    continue
                app_info = p.get("app") if isinstance(p.get("app"), dict) else {"code": p.get("app")}
                found[pid] = {"id": pid, "name": p.get("name") or p.get("title"), "app": app_info.get("code"),
                              "app_name": app_info.get("name"), "price": p.get("price"),
                              "promo_price": p.get("promo_price"), "categories": p.get("categories") or [],
                              "available": p.get("available"), "url": p.get("url")}
            total = parsing.total_count(answer)
            if len(rows) < PAGE_SIZE or (total is not None and page * PAGE_SIZE >= total):
                break
    catalog = sorted(found.values(), key=lambda p: (p["app"] or "", str(p["name"] or ""), str(p["price"])))
    cfg.product_catalog = {"items": catalog, "at": utcnow().isoformat()}
    await db.commit()
    return catalog


async def list_remote_products(db: AsyncSession, organization_id: uuid.UUID, refresh: bool = False) -> list[dict]:
    cfg = await get_config(db, organization_id)
    if refresh or not _catalog(cfg):
        return await refresh_catalog(db, cfg)
    return _catalog(cfg)


async def list_product_map(db: AsyncSession, organization_id: uuid.UUID) -> list[MamifyProductMap]:
    return list((await db.execute(select(MamifyProductMap).where(
        MamifyProductMap.organization_id == organization_id).order_by(MamifyProductMap.plan_code))).scalars())


async def set_product_map(db: AsyncSession, *, organization_id: uuid.UUID, mamify_product_id: str, plan_code: str | None,
                          title: str | None, actor_user_id: uuid.UUID | None) -> MamifyProductMap | None:
    pid = (mamify_product_id or "").strip()
    if not pid:
        raise MamifyError("Indica l'id del prodotto Mamify.")
    row = (await db.execute(select(MamifyProductMap).where(
        MamifyProductMap.organization_id == organization_id, MamifyProductMap.mamify_product_id == pid))).scalar_one_or_none()
    if not plan_code:
        if row is not None:
            await db.delete(row)
            db.add(AuditLog(organization_id=organization_id, actor_user_id=actor_user_id, action="mamify.product.unmapped",
                            entity_type="mamify_product", entity_id=pid, new_value={}))
        await db.commit()
        return None
    plan = await affiliate_service.get_plan(db, organization_id)
    if plan_code not in (TOPUP_CODE, RESALE_CODE) and plan_code not in product_index(plan.config):
        raise MamifyError("Prodotto del piano sconosciuto.")
    if row is None:
        row = MamifyProductMap(organization_id=organization_id, mamify_product_id=pid, plan_code=plan_code)
        db.add(row)
    row.plan_code, row.title = plan_code, (title or "").strip()[:255] or row.title
    db.add(AuditLog(organization_id=organization_id, actor_user_id=actor_user_id, action="mamify.product.mapped",
                    entity_type="mamify_product", entity_id=pid, new_value={"plan_code": plan_code}))
    await db.commit()
    return row


# --- Commissions to pay on Mamify --------------------------------------------


async def payable_for_mamify(db: AsyncSession, organization_id: uuid.UUID) -> list[dict]:
    """Commissions due today, with the Mamify customer of each beneficiary:
    the list Mamify's staff credits from their side. SOS never credits a
    wallet itself; once paid, the commission is marked paid as usual."""
    rows = list((await db.execute(select(AffiliateCommission).where(
        AffiliateCommission.organization_id == organization_id, AffiliateCommission.status == "PAYABLE",
        AffiliateCommission.payable_on <= affiliate_service.today_rome(),
    ).order_by(AffiliateCommission.payable_on))).scalars())
    members = await members_by_agent(db, organization_id)
    agents = await affiliate_service.agents_by_id(db, organization_id)
    out = []
    for c in rows:
        member = members.get(c.beneficiary_agent_id)
        agent = agents.get(c.beneficiary_agent_id)
        problem = None
        if c.amount <= 0:
            problem = "Recupero di un compenso già pagato: va trattenuto a mano."
        elif member is None:
            problem = "Il beneficiario non è collegato a un cliente Mamify."
        out.append({"commission_id": c.id, "kind": c.kind, "period": c.period, "amount": c.amount,
                    "payable_on": c.payable_on, "beneficiary": agent.display_name if agent else None,
                    "mamify_customer_id": member.mamify_customer_id if member else None,
                    "mamify_email": member.email if member else None, "problem": problem})
    return out


# --- Login with the Mamify account -------------------------------------------


async def login_via_mamify(db: AsyncSession, *, organization_id: uuid.UUID, email: str, password: str) -> bool:
    """Signs in an affiliate with their Mamify credentials.

    Mamify checks the password (auth/login: a check, nothing on Mamify's data
    changes); if it is right and the person is in the SOS network, their
    local login is created (or its password aligned) so the usual session
    machinery takes over. A local account not tied to that person is never
    touched: a Mamify account cannot take over an admin login that happens
    to share the email."""
    from app.foundation.security import hash_password
    from app.modules.rbac import service as rbac_service
    from app.modules.users.models import User

    cfg = (await db.execute(select(MamifyConfig).where(MamifyConfig.organization_id == organization_id))).scalar_one_or_none()
    if cfg is None or not cfg.enabled or not cfg.api_key or not email or not password:
        return False
    try:
        answer = await client_for(cfg).call("plugins/mamify/auth/login", {"email": email.strip(), "password": password})
    except MamifyApiError:
        return False
    person = parsing.member(parsing.customer_of(answer))
    member = None
    if person is not None:
        member = (await db.execute(select(MamifyMember).where(
            MamifyMember.organization_id == organization_id, MamifyMember.mamify_customer_id == person.customer_id
        ))).scalar_one_or_none()
    if member is None:
        member = (await db.execute(select(MamifyMember).where(
            MamifyMember.organization_id == organization_id, func.lower(MamifyMember.email) == email.strip().lower()
        ))).scalars().first()
    if member is None:
        return False
    agent = await db.get(AgentProfile, member.agent_id)
    if agent is None:
        return False
    if agent.user_id is not None:
        user = await db.get(User, agent.user_id)
        if user is None:
            return False
        user.password_hash = hash_password(password)
        user.failed_login_attempts, user.locked_until = 0, None
    else:
        clash = (await db.execute(select(User).where(
            User.organization_id == organization_id, func.lower(User.email) == email.strip().lower()))).scalar_one_or_none()
        if clash is not None:
            return False
        user = User(organization_id=organization_id, email=email.strip().lower(), password_hash=hash_password(password),
                    status="ACTIVE", email_verified_at=utcnow())
        db.add(user)
        await db.flush()
        await rbac_service.assign_role(db, user_id=user.id, organization_id=organization_id, role_code="PROMOTER")
        agent.user_id = user.id
        await network_service.ensure_customer_side(db, organization_id=organization_id, agent=agent)
    db.add(AuditLog(organization_id=organization_id, actor_user_id=user.id, action="mamify.login",
                    entity_type="user", entity_id=str(user.id), new_value={"mamify_customer_id": member.mamify_customer_id}))
    await db.commit()
    return True


# --- Status page --------------------------------------------------------------


async def status(db: AsyncSession, organization_id: uuid.UUID) -> dict:
    cfg = await get_config(db, organization_id)
    await db.commit()
    members = dict((await db.execute(select(MamifyMember.present, func.count()).where(
        MamifyMember.organization_id == organization_id).group_by(MamifyMember.present))).all())
    orders = dict((await db.execute(select(MamifyOrder.state, func.count()).where(
        MamifyOrder.organization_id == organization_id).group_by(MamifyOrder.state))).all())
    failed_events = await db.scalar(select(func.count()).select_from(MamifyWebhookEvent).where(
        MamifyWebhookEvent.organization_id == organization_id, MamifyWebhookEvent.error.is_not(None)))
    last_event = await db.scalar(select(func.max(MamifyWebhookEvent.created_at)).where(
        MamifyWebhookEvent.organization_id == organization_id))
    # Products seen in orders but not mapped: the list to work through.
    mapped = {p.mamify_product_id for p in await list_product_map(db, organization_id)}
    catalog = _catalog(cfg)
    unmapped: dict[str, int] = defaultdict(int)
    for raw in (await db.execute(select(MamifyOrder.raw).where(MamifyOrder.organization_id == organization_id)
                                 .order_by(MamifyOrder.created_at.desc()).limit(500))).scalars():
        parsed = parsing.order(raw or {})
        for line in parsed.lines if parsed else []:
            pid = parsing.resolve_line(line, catalog)
            if pid not in mapped:
                unmapped[pid or line.label] += 1
    nodes = await db.scalar(select(func.count()).select_from(NetworkNode).where(
        NetworkNode.organization_id == organization_id, NetworkNode.effective_to.is_(None)))
    return {
        "config": config_view(cfg),
        "members": {"present": members.get(True, 0), "missing": members.get(False, 0), "tree_nodes": nodes or 0},
        "orders": orders, "orders_coverage": await orders_coverage(db, organization_id),
        "failed_webhooks": failed_events or 0, "last_webhook_at": last_event,
        "unmapped_products": [{"id": k, "orders": v} for k, v in sorted(unmapped.items(), key=lambda x: -x[1])][:50],
    }


async def list_orders(db: AsyncSession, organization_id: uuid.UUID, state: str | None = None, limit: int = 200) -> list[dict]:
    q = select(MamifyOrder).where(MamifyOrder.organization_id == organization_id)
    if state:
        q = q.where(MamifyOrder.state == state)
    rows = list((await db.execute(q.order_by(MamifyOrder.created_at.desc()).limit(limit))).scalars())
    buyers = {m.mamify_customer_id: m for m in (await db.execute(select(MamifyMember).where(
        MamifyMember.organization_id == organization_id,
        MamifyMember.mamify_customer_id.in_({r.buyer_customer_id for r in rows if r.buyer_customer_id}),
    ))).scalars()} if rows else {}
    out = []
    for r in rows:
        b = buyers.get(r.buyer_customer_id or "")
        out.append({
            "id": r.id, "mamify_order_id": r.mamify_order_id, "state": r.state, "message": r.message,
            "status": r.status_title or r.status_code, "total": r.total, "ordered_at": r.ordered_at,
            "buyer": {"mamify_id": r.buyer_customer_id,
                      "name": " ".join(x for x in (b.first_name, b.last_name) if x) if b else None},
            "operations": len(r.operation_ids or []), "source": r.source, "received_at": r.created_at, "raw": r.raw,
        })
    return out


ORDER_STATES = ("APPLIED", "RECEIVED", "UNMATCHED", "IGNORED", "CANCELLED", "ERROR")
MAX_LIST_PAGE = 200


def _order_lines(raw: dict) -> list[dict]:
    order = raw.get("order", raw) if isinstance(raw, dict) else {}
    lines = order.get("products") if isinstance(order, dict) else None
    return [{"name": x.get("name"), "app": x.get("app"), "quantity": x.get("quantity"), "price": x.get("price")}
            for x in (lines or []) if isinstance(x, dict)]


def _like(text: str) -> str:
    return f"%{text.strip().replace('%', '').replace('_', ' ')}%"


async def orders_page(db: AsyncSession, organization_id: uuid.UUID, *, page: int = 1, page_size: int = 25,
                      state: str | None = None, search: str | None = None) -> dict:
    """Mamify orders stored by SOS, a page at a time, newest first, with
    the buyer and the product lines; counts by state for the tabs."""
    page_size, page = max(1, min(page_size, MAX_LIST_PAGE)), max(1, page)
    base = select(MamifyOrder).where(MamifyOrder.organization_id == organization_id)
    if state and state != "ALL":
        base = base.where(MamifyOrder.state == state)
    if (search or "").strip():
        like = _like(search)
        buyers = select(MamifyMember.mamify_customer_id).where(
            MamifyMember.organization_id == organization_id,
            or_(func.concat(MamifyMember.first_name, " ", MamifyMember.last_name).ilike(like),
                MamifyMember.email.ilike(like)))
        base = base.where(or_(MamifyOrder.mamify_order_id.ilike(like), MamifyOrder.buyer_customer_id == search.strip(),
                              MamifyOrder.buyer_customer_id.in_(buyers)))
    total = await db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = list((await db.execute(base.order_by(
        MamifyOrder.ordered_at.desc().nulls_last(), MamifyOrder.created_at.desc(),
    ).offset((page - 1) * page_size).limit(page_size))).scalars())
    buyers_by_id = {m.mamify_customer_id: m for m in (await db.execute(select(MamifyMember).where(
        MamifyMember.organization_id == organization_id,
        MamifyMember.mamify_customer_id.in_({r.buyer_customer_id for r in rows if r.buyer_customer_id}),
    ))).scalars()} if rows else {}
    items = []
    for r in rows:
        b = buyers_by_id.get(r.buyer_customer_id or "")
        items.append({
            "id": r.id, "mamify_order_id": r.mamify_order_id, "state": r.state, "message": r.message,
            "status": r.status_title or r.status_code, "total": r.total, "ordered_at": r.ordered_at,
            "buyer": {"mamify_id": r.buyer_customer_id, "agent_id": b.agent_id if b else None,
                      "name": " ".join(x for x in (b.first_name, b.last_name) if x) if b else None,
                      "email": b.email if b else None},
            "lines": _order_lines(r.raw or {}), "operations": len(r.operation_ids or []), "source": r.source,
            "received_at": r.created_at,
        })
    by_state = dict((await db.execute(select(MamifyOrder.state, func.count()).where(
        MamifyOrder.organization_id == organization_id).group_by(MamifyOrder.state))).all())
    paid_total = await db.scalar(select(func.coalesce(func.sum(MamifyOrder.total), 0)).where(
        MamifyOrder.organization_id == organization_id, MamifyOrder.state == "APPLIED")) or 0
    return {"items": items, "total": total, "page": page, "page_size": page_size,
            "pages": max(1, -(-total // page_size)),
            "counts": {"ALL": sum(by_state.values()), **by_state}, "applied_total": paid_total,
            "coverage": await orders_coverage(db, organization_id)}


async def customers_page(db: AsyncSession, organization_id: uuid.UUID, *, page: int = 1, page_size: int = 25,
                         search: str | None = None, buyers_only: bool = False) -> dict:
    """Mamify customers as SOS sees them: everyone copied from the network,
    or only those with SOS orders, with how many and how much, and when
    their orders were last read."""
    page_size, page = max(1, min(page_size, MAX_LIST_PAGE)), max(1, page)
    orders = (select(MamifyOrder.buyer_customer_id.label("cid"), func.count().label("n"),
                     func.coalesce(func.sum(MamifyOrder.total).filter(MamifyOrder.state == "APPLIED"), 0).label("paid"),
                     func.max(MamifyOrder.ordered_at).label("last"))
              .where(MamifyOrder.organization_id == organization_id).group_by(MamifyOrder.buyer_customer_id).subquery())
    base = (select(MamifyMember, orders.c.n, orders.c.paid, orders.c.last)
            .join(orders, orders.c.cid == MamifyMember.mamify_customer_id, isouter=not buyers_only)
            .where(MamifyMember.organization_id == organization_id))
    if (search or "").strip():
        like = _like(search)
        base = base.where(or_(func.concat(MamifyMember.first_name, " ", MamifyMember.last_name).ilike(like),
                              MamifyMember.email.ilike(like), MamifyMember.phone.ilike(like),
                              MamifyMember.mamify_customer_id == search.strip()))
    total = await db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = (await db.execute(base.order_by(orders.c.last.desc().nulls_last(), MamifyMember.registered_at.desc().nulls_last(),
                                           MamifyMember.id).offset((page - 1) * page_size).limit(page_size))).all()
    sponsors = {m.mamify_customer_id: m for m in (await db.execute(select(MamifyMember).where(
        MamifyMember.organization_id == organization_id,
        MamifyMember.mamify_customer_id.in_({r[0].sponsor_customer_id for r in rows if r[0].sponsor_customer_id}),
    ))).scalars()} if rows else {}
    items = []
    for m, n, paid, last in rows:
        sp = sponsors.get(m.sponsor_customer_id or "")
        items.append({
            "mamify_id": m.mamify_customer_id, "agent_id": m.agent_id,
            "name": " ".join(x for x in (m.first_name, m.last_name) if x) or m.email or f"Cliente {m.mamify_customer_id}",
            "email": m.email, "phone": m.phone, "registered_at": m.registered_at, "present": m.present,
            "sponsor": {"mamify_id": sp.mamify_customer_id,
                        "name": " ".join(x for x in (sp.first_name, sp.last_name) if x)} if sp else None,
            "direct_count": m.direct_count, "orders": n or 0, "paid_total": paid or 0, "last_order_at": last,
            "orders_checked_at": m.orders_checked_at,
        })
    buyers = await db.scalar(select(func.count(func.distinct(MamifyOrder.buyer_customer_id))).where(
        MamifyOrder.organization_id == organization_id)) or 0
    return {"items": items, "total": total, "page": page, "page_size": page_size,
            "pages": max(1, -(-total // page_size)), "buyers": buyers,
            "coverage": await orders_coverage(db, organization_id)}


async def recheck_member_orders(db: AsyncSession, organization_id: uuid.UUID, mamify_customer_id: str) -> dict:
    """Reads one customer's latest orders now (one read-only call)."""
    cfg = await get_config(db, organization_id)
    if not (cfg.enabled and cfg.api_key):
        raise MamifyError("Il collegamento con Mamify non è attivo.")
    row = await db.scalar(select(MamifyMember).where(
        MamifyMember.organization_id == organization_id, MamifyMember.mamify_customer_id == mamify_customer_id))
    if row is None:
        raise MamifyError("Cliente non trovato nella rete copiata.")
    if row.orders_checked_at and utcnow() - row.orders_checked_at < timedelta(seconds=30):
        raise MamifyError("Ordini appena letti: riprova tra qualche secondo.")
    row_id = row.id
    mapped = {p.mamify_product_id for p in await list_product_map(db, organization_id)}
    client = client_for(cfg)
    try:
        found = await _read_member_orders(db, cfg, client, mamify_customer_id, mapped)
    except MamifyApiError as exc:
        raise MamifyError(str(exc)) from exc
    await db.execute(update(MamifyMember).where(MamifyMember.id == row_id).values(orders_checked_at=utcnow()))
    await db.commit()
    return {"read": True, "calls": client.calls, "found": found}


# --- Periodic tasks -----------------------------------------------------------


async def enabled_organizations(db: AsyncSession) -> list[uuid.UUID]:
    return list((await db.execute(select(MamifyConfig.organization_id).where(MamifyConfig.enabled.is_(True)))).scalars())


async def _each_org(db: AsyncSession, label: str, run) -> int:
    done = 0
    for org in await enabled_organizations(db):
        try:
            await run(org)
            done += 1
        except Exception:  # logged; the next run retries
            await db.rollback()
            logger.exception("Mamify %s failed for %s", label, org)
    return done


async def periodic_network_sync(db: AsyncSession) -> int:
    return await _each_org(db, "network sync", lambda org: sync_network(db, org))


async def periodic_new_members(db: AsyncSession) -> int:
    return await _each_org(db, "new members", lambda org: sync_new_members(db, org))


async def periodic_orders(db: AsyncSession, minutes: int = 2) -> int:
    async def run(org: uuid.UUID) -> None:
        cfg = await get_config(db, org)
        await poll_orders(db, org, calls=cfg.orders_calls_per_minute * minutes)
        await retry_waiting_orders(db, org)

    return await _each_org(db, "orders", run)
