"""The sponsor tree at any size, one branch at a time.

The SOS tree is a copy of the Mamify network: tens of thousands of people,
tens of thousands of them directly under the company. Sending it whole to a
browser does not work, so the tree view asks for one branch at a time: a
person and their directs (the biggest branches first, 100 a page), with
every figure the view shows already computed here: this month's volumes,
branch size, legs, level, subscription, Mamify contact.

Building those figures means reading the whole tree and the month's points;
the result is kept in memory for CACHE_SECONDS, so opening branches one after
the other costs one build. Figures may therefore lag by that much. Past that
age the old copy is still served at once while a new one is built in the
background (stale-while-revalidate): nobody waits for a rebuild except the
very first viewer, or after the Mamify worker changed the tree.
"""

import asyncio
import logging
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.affiliate import engine
from app.modules.affiliate.models import AffiliateOperation

CACHE_SECONDS = 90
#: A Digital Ambassador's whole branch in one answer (the virtual tour);
#: past this many people only the nearest levels are sent.
GALAXY_MAX = 5_000
PAGE = 100
MAX_PAGE = 500
SORTS = ("size", "bct", "name")


@dataclass(slots=True)
class Node:
    id: uuid.UUID
    name: str
    code: str
    status: str
    joined_at: datetime | None
    parent: uuid.UUID | None
    depth: int = 0
    bcp: int = 0
    bct: int = 0
    level: int | None = None
    next_level: int | None = None
    active_legs: int = 0
    qualifying_legs: int = 0
    size: int = 0
    paid: bool = False
    mamify_id: str | None = None
    present: bool = True
    email: str | None = None
    phone: str | None = None


@dataclass
class Snapshot:
    period: str
    nodes: dict[uuid.UUID, Node]
    children: dict[uuid.UUID | None, list[uuid.UUID]]
    built_at: float
    #: Rows and newest row of the tree table when built: a copy or a move
    #: made by the Mamify worker changes it, and the cache is rebuilt.
    stamp: tuple = ()
    _sorted: dict[tuple, list[uuid.UUID]] = field(default_factory=dict)
    _summary: dict[uuid.UUID | None, dict] = field(default_factory=dict)

    def kids(self, parent: uuid.UUID | None, sort: str) -> list[uuid.UUID]:
        key = (parent, sort)
        if key not in self._sorted:
            ids = self.children.get(parent, [])
            n = self.nodes
            if sort == "bct":
                ordered = sorted(ids, key=lambda i: (-n[i].bct, -n[i].size, n[i].name.lower()))
            elif sort == "name":
                ordered = sorted(ids, key=lambda i: n[i].name.lower())
            else:
                ordered = sorted(ids, key=lambda i: (-n[i].size, -n[i].bct, n[i].name.lower()))
            self._sorted[key] = ordered
        return self._sorted[key]

    def subtree(self, root: uuid.UUID | None):
        """Everyone in the branch (root included), with depth below it."""
        stack = [(r, 0) for r in ([root] if root else self.children.get(None, []))]
        while stack:
            node, d = stack.pop()
            yield node, d
            stack.extend((c, d + 1) for c in self.children.get(node, []))

    def within(self, node: uuid.UUID, scope: uuid.UUID | None) -> bool:
        """Whether `node` is `scope` or below it (any node when scope is None)."""
        if scope is None:
            return node in self.nodes
        cur: uuid.UUID | None = node
        seen = 0
        while cur is not None and seen < 10_000:
            if cur == scope:
                return True
            cur = self.nodes[cur].parent if cur in self.nodes else None
            seen += 1
        return False


_cache: dict[uuid.UUID, Snapshot] = {}
_locks: dict[uuid.UUID, asyncio.Lock] = {}
_refreshing: set[uuid.UUID] = set()
log = logging.getLogger(__name__)


async def _stamp(db: AsyncSession, organization_id: uuid.UUID) -> tuple:
    from app.modules.network.models import NetworkNode

    return tuple((await db.execute(select(func.count(), func.max(NetworkNode.created_at)).where(
        NetworkNode.organization_id == organization_id))).one())


async def snapshot(db: AsyncSession, organization_id: uuid.UUID, *, fresh: bool = False) -> Snapshot:
    from app.modules.affiliate import service

    period = service.current_period()
    stamp = await _stamp(db, organization_id)
    cached = _cache.get(organization_id)
    if cached and not fresh and cached.period == period and cached.stamp == stamp:
        if time.monotonic() - cached.built_at >= CACHE_SECONDS:
            _refresh_later(db, organization_id)
        return cached
    lock = _locks.setdefault(organization_id, asyncio.Lock())
    async with lock:
        # Someone else may have built it while this request waited.
        cached = _cache.get(organization_id)
        if cached and not fresh and cached.period == period and cached.stamp == stamp:
            return cached
        return await _build(db, organization_id, period, stamp)


def _refresh_later(db: AsyncSession, organization_id: uuid.UUID) -> None:
    """Rebuilds the copy in the background with its own session on the same
    engine; the current request keeps the old copy."""
    from sqlalchemy.ext.asyncio import AsyncEngine

    from app.modules.affiliate import service

    bind = db.bind
    if organization_id in _refreshing or not isinstance(bind, AsyncEngine):
        return
    _refreshing.add(organization_id)

    async def run() -> None:
        try:
            async with AsyncSession(bind, expire_on_commit=False) as own, _locks.setdefault(organization_id, asyncio.Lock()):
                await _build(own, organization_id, service.current_period(), await _stamp(own, organization_id))
        except Exception:
            log.exception("tree refresh failed")
        finally:
            _refreshing.discard(organization_id)

    asyncio.get_running_loop().create_task(run())


async def _build(db: AsyncSession, organization_id: uuid.UUID, period: str, stamp: tuple) -> Snapshot:
    from app.modules.affiliate import service
    from app.modules.mamify.models import MamifyMember
    from app.modules.network.models import AgentProfile

    sheets, plan, parents = await service.compute_period(db, organization_id, period)
    rows = (await db.execute(select(
        AgentProfile.id, AgentProfile.display_name, AgentProfile.promoter_code, AgentProfile.status, AgentProfile.joined_at,
    ).where(AgentProfile.organization_id == organization_id))).all()
    nodes: dict[uuid.UUID, Node] = {
        r.id: Node(id=r.id, name=r.display_name, code=r.promoter_code, status=r.status, joined_at=r.joined_at,
                   parent=parents.get(r.id)) for r in rows if r.id in parents
    }
    children: dict[uuid.UUID | None, list[uuid.UUID]] = defaultdict(list)
    for nid, node in nodes.items():
        if node.parent is not None and node.parent not in nodes:
            node.parent = None
        children[node.parent].append(nid)

    paid_now = set((await db.execute(select(AffiliateOperation.agent_id).where(
        AffiliateOperation.organization_id == organization_id, AffiliateOperation.kind == "SUBSCRIPTION_PAYMENT",
        AffiliateOperation.status == "CONFIRMED", AffiliateOperation.period == period,
    ))).scalars())
    for m in (await db.execute(select(
        MamifyMember.agent_id, MamifyMember.mamify_customer_id, MamifyMember.present, MamifyMember.email, MamifyMember.phone,
    ).where(MamifyMember.organization_id == organization_id))).all():
        node = nodes.get(m.agent_id)
        if node is not None:
            node.mamify_id, node.present, node.email, node.phone = m.mamify_customer_id, m.present, m.email, m.phone

    levels = engine.career_levels(plan.config)
    leg_min = {lv.level: lv.leg_min_bc for lv in levels}
    required = int(plan.config["required_legs"])
    for nid, node in nodes.items():
        sheet = sheets.get(nid)
        node.paid = nid in paid_now
        if sheet is None:
            continue
        career = engine.evaluate_career(sheet.bcp, list(sheet.legs.values()), levels, required_legs=required)
        target = leg_min.get(career.next_level or 0)
        node.bcp, node.bct, node.level, node.next_level = sheet.bcp, sheet.bct, career.level, career.next_level
        node.active_legs = len([v for v in sheet.legs.values() if v > 0])
        node.qualifying_legs = len([v for v in sheet.legs.values() if target and v >= target])

    # Depth from the top and branch sizes, without recursion.
    order: list[uuid.UUID] = []
    stack = [(r, 0) for r in children.get(None, [])]
    while stack:
        nid, d = stack.pop()
        nodes[nid].depth = d
        order.append(nid)
        stack.extend((c, d + 1) for c in children.get(nid, []))
    for nid in reversed(order):
        parent = nodes[nid].parent
        if parent is not None:
            nodes[parent].size += nodes[nid].size + 1

    snap = Snapshot(period=period, nodes=nodes, children=dict(children), built_at=time.monotonic(), stamp=stamp)
    _cache[organization_id] = snap
    return snap


def row(snap: Snapshot, nid: uuid.UUID) -> dict:
    """One person as the tree view shows them (the TreeRow of the dashboard)."""
    n = snap.nodes[nid]
    return {
        "agent": {"id": n.id, "name": n.name, "code": n.code, "status": n.status},
        "parent_id": n.parent, "depth": n.depth, "bcp": n.bcp, "bct": n.bct, "level": n.level,
        "direct_count": len(snap.children.get(nid, [])), "network_size": n.size,
        "active_legs": n.active_legs, "qualifying_legs": n.qualifying_legs, "next_level": n.next_level,
        "joined_at": n.joined_at, "subscription_paid": n.paid,
        "mamify": {"id": n.mamify_id, "present": n.present, "email": n.email, "phone": n.phone} if n.mamify_id else None,
    }


def summary(snap: Snapshot, root: uuid.UUID | None) -> dict:
    """Figures of a whole branch (or of the whole network): people, active,
    paid, gone from Mamify, people per depth."""
    if root in snap._summary:
        return snap._summary[root]
    people = active = paid = missing = 0
    by_depth: dict[int, int] = defaultdict(int)
    for nid, d in snap.subtree(root):
        n = snap.nodes[nid]
        people += 1
        active += n.bcp > 0
        paid += n.paid
        missing += bool(n.mamify_id and not n.present)
        by_depth[d] += 1
    out = {"people": people, "active": active, "paid": paid, "missing": missing,
           "by_depth": [{"depth": d, "people": c} for d, c in sorted(by_depth.items())],
           "max_depth": max(by_depth) if by_depth else 0, "period": snap.period}
    snap._summary[root] = out
    return out


def branch(snap: Snapshot, root: uuid.UUID | None, *, offset: int = 0, limit: int = PAGE, sort: str = "size",
           active_only: bool = False, scope: uuid.UUID | None = None) -> dict:
    """A person (or the top of the network when root is None), the path to
    them from the top of the viewer's tree (`scope`: nobody above it is
    shown), and one page of their directs."""
    sort = sort if sort in SORTS else "size"
    limit = max(1, min(int(limit), MAX_PAGE))
    offset = max(0, int(offset))
    ids = snap.kids(root, sort)
    if active_only:
        ids = [i for i in ids if snap.nodes[i].bct > 0]
    page = ids[offset: offset + limit]
    path = []
    cur = snap.nodes[root].parent if root and root != scope else None
    while cur is not None:
        path.append(row(snap, cur))
        if cur == scope:
            break
        cur = snap.nodes[cur].parent
    return {
        "root": row(snap, root) if root else None,
        "path": list(reversed(path)),
        "children": [row(snap, i) for i in page],
        "total_children": len(ids), "offset": offset, "limit": limit,
    }


def search(snap: Snapshot, query: str, *, scope: uuid.UUID | None, limit: int = 50) -> dict:
    """People whose name, code, email or phone contains the text, each with
    the path to them from the top of the viewer's tree."""
    needle = (query or "").strip().lower()
    if len(needle) < 2:
        return {"results": [], "total": 0}
    hits = []
    for n in snap.nodes.values():
        hay = f"{n.name} {n.code} {n.email or ''} {n.phone or ''} {n.mamify_id or ''}".lower()
        if needle in hay and snap.within(n.id, scope):
            hits.append(n.id)
    hits.sort(key=lambda i: (-snap.nodes[i].size, snap.nodes[i].name.lower()))
    results = []
    for nid in hits[:limit]:
        path = []
        cur = snap.nodes[nid].parent
        while cur is not None and (scope is None or cur != snap.nodes[scope].parent):
            path.append({"id": cur, "name": snap.nodes[cur].name})
            if cur == scope:
                break
            cur = snap.nodes[cur].parent
        results.append({**row(snap, nid), "path": list(reversed(path))})
    return {"results": results, "total": len(hits)}


GALAXY_FIELDS = ("id", "parent", "name", "code", "level", "next_level", "bcp", "bct", "size", "directs",
                 "depth", "paid", "gone", "qualifying_legs", "active_legs")


def galaxy(snap: Snapshot, root: uuid.UUID, *, limit: int = GALAXY_MAX) -> dict:
    """A Digital Ambassador's whole branch in one compact answer, for the
    virtual tour: one row per person (fields in GALAXY_FIELDS), in breadth
    order so that a parent always comes before its directs; `parent` is the
    index of the sponsor's row (-1 for the viewer). No contact data: the tour
    only draws. Past `limit` people the deepest levels are left out and
    `truncated` says so."""
    rows: list[list] = []
    index: dict[uuid.UUID, int] = {}
    queue = [root]
    head = 0
    while head < len(queue) and len(rows) < limit:
        nid = queue[head]
        head += 1
        n = snap.nodes[nid]
        index[nid] = len(rows)
        kids = snap.kids(nid, "size")
        rows.append([str(nid), index.get(n.parent, -1) if nid != root else -1, n.name, n.code, n.level, n.next_level,
                     n.bcp, n.bct, n.size, len(kids), n.depth - snap.nodes[root].depth, int(n.paid),
                     int(bool(n.mamify_id and not n.present)), n.qualifying_legs, n.active_legs])
        queue.extend(kids)
    people = snap.nodes[root].size + 1
    return {"scope": str(root), "period": snap.period, "people": people, "shown": len(rows),
            "truncated": len(rows) < people, "fields": list(GALAXY_FIELDS), "nodes": rows}
