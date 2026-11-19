"use client";

import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Chip } from "@/components/ui/data-cells";
import { BranchSyncButton } from "@/components/branch-sync-button";
import { Empty, ErrorNote, Loading, Progress } from "@/components/affiliate/shared";
import { affiliateGet, bc, num, shortDate, type TreeBranch, type TreeRow, type TreeSearch } from "@/lib/affiliate";

/*
 * The sponsor tree, readable at any size. The tree mirrors Mamify (tens of
 * thousands of people, most of them directly under the company), so it is
 * never loaded whole: each branch is asked to the server when it is opened,
 * 100 people at a time, biggest branches first (affiliate/tree.py). Search
 * runs on the server too and opens the branch of the person found. Every
 * figure is the server's; this file only arranges them.
 */

type Level = { level: number; total_bc: number; leg_min_bc: number };
type SortKey = "size" | "bct" | "name";
type Page = { rows: TreeRow[]; total: number };
type Layout = "horizontal" | "list";

const LAYOUT_KEY = "sosnet.tree.layout";

const PAGE = 100;
const TOP_KEY = "__top__";

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  return ((parts[0]?.[0] ?? "") + (parts[1]?.[0] ?? "")).toUpperCase() || "?";
}

export function NetworkTree({
  base,
  levels,
  onOpenDetail,
  emptyText = "La rete è ancora vuota.",
}: {
  /** "admin": the whole tree. "me": the viewer's own branch. */
  base: "admin" | "me";
  levels?: Level[];
  /** Admin: opens the full card of a person. */
  onOpenDetail?: (agentId: string) => void;
  emptyText?: string;
}) {
  const qc = useQueryClient();
  const api = base === "admin" ? "/admin/network" : "/me/network";
  const [focusId, setFocusId] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [sort, setSort] = useState<SortKey>("size");
  const [onlyActive, setOnlyActive] = useState(false);
  const [open, setOpen] = useState<Set<string>>(new Set());
  // Children pages loaded on demand, by parent id; reset when the order or
  // the filter changes, since pages depend on both.
  const [pages, setPages] = useState<Map<string, Page>>(new Map());
  const [loading, setLoading] = useState<Set<string>>(new Set());
  const [loadError, setLoadError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [needle, setNeedle] = useState("");
  const [layout, setLayoutState] = useState<Layout>(() => {
    try {
      return typeof window !== "undefined" && window.localStorage.getItem(LAYOUT_KEY) === "list" ? "list" : "horizontal";
    } catch {
      return "horizontal";
    }
  });
  const setLayout = (next: Layout) => {
    setLayoutState(next);
    try { window.localStorage.setItem(LAYOUT_KEY, next); } catch { /* per-viewer convenience only */ }
  };

  useEffect(() => {
    const t = setTimeout(() => setNeedle(query.trim()), 350);
    return () => clearTimeout(t);
  }, [query]);
  // Pages depend on the order and the filter: changing either starts over.
  const changeView = (next: { sort?: SortKey; onlyActive?: boolean }) => {
    if (next.sort !== undefined) setSort(next.sort);
    if (next.onlyActive !== undefined) setOnlyActive(next.onlyActive);
    setPages(new Map());
    setOpen(new Set());
  };

  const params = (root: string | null, offset = 0) =>
    `${api}/branch?limit=${PAGE}&offset=${offset}&sort=${sort}${onlyActive ? "&active=true" : ""}${root ? `&root=${root}` : ""}`;

  const top = useQuery({
    queryKey: ["affiliate", "tree", base, focusId, sort, onlyActive],
    queryFn: () => affiliateGet<TreeBranch>(params(focusId)),
  });
  const found = useQuery({
    queryKey: ["affiliate", "tree-search", base, needle],
    queryFn: () => affiliateGet<TreeSearch>(`${api}/search?q=${encodeURIComponent(needle)}`),
    enabled: needle.length >= 2,
  });

  const branch = top.data;
  // The node whose directs are the first level on screen (null: the top of
  // the whole network). Its first page comes with the main query; further
  // pages are kept under TOP_KEY and appended.
  const topId = branch?.root?.agent.id ?? null;
  const keyOf = (id: string | null) => (id === null || id === topId ? TOP_KEY : id);

  const loadChildren = async (id: string | null, offset = 0) => {
    const key = keyOf(id);
    if (loading.has(key)) return;
    setLoading((s) => new Set(s).add(key));
    setLoadError(null);
    try {
      const b = await qc.fetchQuery({
        queryKey: ["affiliate", "tree", base, id, sort, onlyActive, offset],
        queryFn: () => affiliateGet<TreeBranch>(params(id, offset)),
        staleTime: 60_000,
      });
      setPages((m) => {
        const next = new Map(m);
        const prev = offset ? next.get(key)?.rows ?? [] : [];
        next.set(key, { rows: [...prev, ...b.children], total: b.total_children });
        return next;
      });
    } catch (e) {
      setLoadError((e as Error).message);
    } finally {
      setLoading((s) => {
        const next = new Set(s);
        next.delete(key);
        return next;
      });
    }
  };

  const pageOf = (id: string | null): Page | undefined => {
    if (!branch) return undefined;
    if (keyOf(id) === TOP_KEY) {
      const extra = pages.get(TOP_KEY)?.rows ?? [];
      return { rows: [...branch.children, ...extra], total: branch.total_children };
    }
    return id ? pages.get(id) : undefined;
  };

  const toggle = (row: TreeRow) => {
    const id = row.agent.id;
    const next = new Set(open);
    if (next.has(id)) next.delete(id);
    else {
      next.add(id);
      if (!pageOf(id) && row.direct_count > 0) void loadChildren(id);
    }
    setOpen(next);
  };

  // Every row seen so far, to name sponsors and legs in the side card.
  const known = useMemo(() => {
    const m = new Map<string, TreeRow>();
    if (branch) {
      for (const r of [...branch.path, ...(branch.root ? [branch.root] : []), ...branch.children]) m.set(r.agent.id, r);
    }
    for (const p of pages.values()) for (const r of p.rows) m.set(r.agent.id, r);
    for (const r of found.data?.results ?? []) if (!m.has(r.agent.id)) m.set(r.agent.id, r);
    return m;
  }, [branch, pages, found.data]);

  const selected = selectedId ? known.get(selectedId) ?? null : null;
  const loadedLegs = selected ? pageOf(selected.agent.id) : undefined;
  // The side card needs the person's legs even when their branch is closed.
  const legsQuery = useQuery({
    queryKey: ["affiliate", "tree", base, selectedId, sort, onlyActive, 0],
    queryFn: () => affiliateGet<TreeBranch>(params(selectedId, 0)),
    enabled: !!selected && selected.direct_count > 0 && !loadedLegs,
    staleTime: 60_000,
  });
  const selectedLegs: Page | undefined = loadedLegs
    ?? (legsQuery.data ? { rows: legsQuery.data.children, total: legsQuery.data.total_children } : undefined);

  const goTo = (id: string | null) => {
    setFocusId(id);
    setOpen(new Set());
    setPages((m) => {
      const next = new Map(m);
      next.delete(TOP_KEY);
      return next;
    });
    setSelectedId(id);
  };

  if (top.isLoading) return <Loading />;
  if (top.error || !branch) return <ErrorNote message={(top.error as Error | null)?.message} />;
  const s = branch.summary;
  const isMe = base === "me";
  if (s.people === 0 || (isMe && s.people <= 1)) return <Empty>{emptyText}</Empty>;

  const depthRows = s.by_depth;
  const maxDepthCount = Math.max(1, ...depthRows.map((d) => d.people));
  const rootLabel = branch.root ? (branch.root.agent.id === branch.scope ? "la tua rete" : `il ramo di ${branch.root.agent.name}`) : "tutta la rete";

  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Stat label="Persone" value={num(s.people)} hint={`in ${rootLabel}`} />
        <Stat label="Con punti questo mese" value={num(s.active)} hint={`${s.people ? Math.round((s.active / s.people) * 100) : 0}% del ramo`} />
        <Stat label="Mensilità pagate" value={num(s.paid)} hint="nel mese in corso" />
        <Stat label="Profondità" value={num(s.max_depth)} hint="livelli sotto la cima" />
      </div>

      <div className="panel rounded-3xl p-4">
        <p className="kpi-label mb-2">Persone per livello di profondità</p>
        <div className="flex items-end gap-1.5 overflow-x-auto pb-1" style={{ height: 76 }}>
          {depthRows.map(({ depth, people }) => (
            <div key={depth} className="flex h-full min-w-[28px] flex-1 flex-col items-center justify-end gap-1"
              title={`${depth === 0 && branch.root ? "Cima" : `${depth + (branch.root ? 0 : 1)}° livello`}: ${num(people)} persone`}>
              <span className="text-[10px] tabular-nums text-white">{num(people)}</span>
              <div className="w-full rounded-t-md bg-gradient-to-t from-brand-600 to-accent-400" style={{ height: `${(people / maxDepthCount) * 100}%`, minHeight: 4 }} />
              <span className="text-[10px] text-surface-400">{depth === 0 && branch.root ? "cima" : depth + (branch.root ? 0 : 1)}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <input
          type="search"
          placeholder="Cerca nome, codice, email, telefono o id Mamify"
          className="field min-w-0 flex-1 rounded-xl px-3 py-2 text-sm sm:max-w-sm"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          aria-label="Cerca nella rete"
        />
        <label className="act cursor-pointer select-none">
          <input type="checkbox" className="mr-1.5 accent-current" checked={onlyActive} onChange={(e) => changeView({ onlyActive: e.target.checked })} />
          Solo rami con punti
        </label>
        <select className="field rounded-xl px-3 py-2 text-sm" value={sort} onChange={(e) => changeView({ sort: e.target.value as SortKey })} aria-label="Ordina">
          <option value="size">Prima i rami più grandi</option>
          <option value="bct">Prima chi ha più volume (BCT)</option>
          <option value="name">Per nome</option>
        </select>
        <button type="button" className="act" onClick={() => setOpen(new Set())}>Chiudi tutto</button>
        <div role="group" aria-label="Vista" className="flex overflow-hidden rounded-xl border border-white/10">
          {([["horizontal", "Albero"], ["list", "Elenco"]] as const).map(([k, label]) => (
            <button key={k} type="button" aria-pressed={layout === k} onClick={() => setLayout(k)}
              className={`px-3 py-1.5 text-xs font-semibold ${layout === k ? "bg-white/15 text-white" : "text-surface-300 hover:bg-white/5"}`}>
              {label}
            </button>
          ))}
        </div>
      </div>
      {s.missing > 0 && (
        <p className="text-xs text-warn-300">{num(s.missing)} persone di questo ramo non risultano più nella rete Mamify: restano qui con lo storico dei punti.</p>
      )}

      {needle.length >= 2 && (
        <div className="panel space-y-2 rounded-3xl p-4">
          <div className="flex items-center justify-between gap-2">
            <p className="kpi-label">Risultati della ricerca</p>
            <button type="button" className="act" onClick={() => setQuery("")}>Chiudi</button>
          </div>
          {found.isFetching ? <Loading /> : found.error ? <ErrorNote message={(found.error as Error).message} /> : (found.data?.results ?? []).length === 0 ? (
            <p className="text-sm text-surface-300">Nessuna persona trovata.</p>
          ) : (
            <>
              {(found.data?.total ?? 0) > (found.data?.results.length ?? 0) && (
                <p className="text-xs text-surface-400">{num(found.data?.total)} persone trovate: ecco le prime {found.data?.results.length}, prima i rami più grandi. Scrivi di più per restringere.</p>
              )}
              <ul className="max-h-80 space-y-1 overflow-y-auto">
                {(found.data?.results ?? []).map((r) => (
                  <li key={r.agent.id}>
                    <button type="button" className="w-full rounded-2xl px-3 py-2 text-left hover:bg-white/5"
                      onClick={() => { goTo(r.agent.id); setQuery(""); }}>
                      <span className="font-semibold text-white">{r.agent.name}</span>
                      <span className="text-xs text-surface-400"> · {r.agent.code} · {num(r.direct_count)} diretti · {num(r.network_size)} in rete</span>
                      <span className="block truncate text-[11px] text-surface-400">
                        {r.path.length ? r.path.map((p) => p.name).join(" › ") : "in cima alla rete"}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}

      {(focusId || branch.path.length > 0) && (
        <nav aria-label="Percorso" className="flex flex-wrap items-center gap-1 text-xs">
          <button type="button" className="act" onClick={() => goTo(null)}>{isMe ? "La mia rete" : "Tutta la rete"}</button>
          {branch.path.map((p) => (
            <span key={p.agent.id} className="flex items-center gap-1">
              <span className="text-surface-500">›</span>
              <button type="button" className="act" onClick={() => goTo(p.agent.id)}>{p.agent.name}</button>
            </span>
          ))}
          {branch.root && focusId && (
            <>
              <span className="text-surface-500">›</span>
              <span className="font-semibold text-white">{branch.root.agent.name}</span>
            </>
          )}
        </nav>
      )}
      <ErrorNote message={loadError} />

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_340px]">
        {layout === "horizontal" ? (
          <div className="panel max-h-[75vh] min-h-[320px] overflow-auto rounded-3xl p-3 sm:p-4">
            <div role="tree" aria-label="Albero della rete" className="w-max min-w-full py-2">
              {branch.root ? (
                <HBranch row={branch.root} forceOpen pageOf={pageOf} open={open} toggle={toggle} loading={loading}
                  loadMore={loadChildren} selectedId={selectedId} onSelect={setSelectedId} selfId={branch.scope} />
              ) : (
                <div className="flex items-center">
                  <div className="w-48 shrink-0 rounded-2xl border border-white/10 bg-gradient-to-br from-brand-600/40 to-accent-500/30 px-3 py-2.5">
                    <p className="text-sm font-black text-white">Tutta la rete</p>
                    <p className="text-[11px] text-surface-300">{num(branch.total_children)} in cima · {num(s.people)} persone</p>
                  </div>
                  <span className="h-px w-6 shrink-0 bg-white/20" aria-hidden="true" />
                  <HChildren parentId={null} page={pageOf(null)} pageOf={pageOf} open={open} toggle={toggle} loading={loading}
                    loadMore={loadChildren} selectedId={selectedId} onSelect={setSelectedId} selfId={branch.scope} />
                </div>
              )}
            </div>
          </div>
        ) : (
        <div className="panel overflow-x-auto rounded-3xl p-3 sm:p-4">
          <div className="hidden grid-cols-[minmax(0,1fr)_72px_84px_64px_72px] gap-2 px-2 pb-2 text-[10px] uppercase tracking-wider text-surface-400 md:grid">
            <span>Persona</span><span className="text-right">BCP</span><span className="text-right">BCT</span><span className="text-right">Diretti</span><span className="text-right">Rete</span>
          </div>
          <ul role="tree" aria-label="Albero della rete" className="space-y-0.5">
            {branch.root ? (
              <Branch row={branch.root} forceOpen pageOf={pageOf} open={open} toggle={toggle} loading={loading}
                loadMore={loadChildren} selectedId={selectedId} onSelect={setSelectedId} selfId={branch.scope} />
            ) : (
              <Children parentId={null} page={pageOf(null)} pageOf={pageOf} open={open} toggle={toggle} loading={loading}
                loadMore={loadChildren} selectedId={selectedId} onSelect={setSelectedId} selfId={branch.scope} />
            )}
          </ul>
        </div>
        )}

        <aside className="lg:sticky lg:top-4 lg:self-start">
          {selected ? (
            <PersonCard
              row={selected}
              sponsor={selected.parent_id ? known.get(selected.parent_id) ?? null : null}
              legs={selectedLegs}
              levels={levels}
              isSelf={selected.agent.id === branch.scope}
              sync={base === "admin" ? "admin" : selected.agent.id === branch.scope ? "self" : null}
              onFocus={() => goTo(selected.agent.id)}
              onOpenDetail={onOpenDetail}
              onClose={() => setSelectedId(null)}
            />
          ) : (
            <div className="panel rounded-3xl p-5 text-sm text-surface-300">
              <p className="font-semibold text-white">Come si legge</p>
              <ul className="mt-2 space-y-1.5 text-xs">
                <li><b className="text-white">BCP</b>: punti personali del mese.</li>
                <li><b className="text-white">BCT</b>: punti di tutto il ramo, persona compresa. Ogni acquisto conta una volta sola per ogni sponsor sopra.</li>
                <li><b className="text-white">Gamba</b>: il ramo di ogni diretto. Per salire di livello servono almeno 3 gambe al minimo.</li>
                <li>I rami si aprono uno alla volta con il tasto +, 100 persone per volta, prima i più grandi. Tocca una persona per vedere le sue gambe e cosa le manca per il livello successivo.</li>
              </ul>
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}

function Stat({ label, value, hint }: { label: string; value: string; hint: string }) {
  return (
    <div className="panel rounded-3xl p-4">
      <p className="kpi-label">{label}</p>
      <p className="mt-1 text-2xl font-black tabular-nums text-white">{value}</p>
      <p className="text-[11px] text-surface-400">{hint}</p>
    </div>
  );
}

function LevelBadge({ level }: { level: number | null }) {
  return level ? (
    <span className="inline-flex h-5 min-w-[2.25rem] items-center justify-center rounded-full bg-gradient-to-r from-brand-600 to-accent-500 px-1.5 text-[10px] font-black text-white">
      L{level}
    </span>
  ) : null;
}

type TreeProps = {
  pageOf: (id: string | null) => Page | undefined;
  open: Set<string>;
  toggle: (row: TreeRow) => void;
  loading: Set<string>;
  loadMore: (id: string | null, offset: number) => void;
  selectedId: string | null;
  onSelect: (id: string) => void;
  selfId: string | null;
};

function Children({ parentId, page, ...props }: TreeProps & { parentId: string | null; page: Page | undefined }) {
  if (!page) return null;
  const more = page.total - page.rows.length;
  return (
    <>
      {page.rows.map((k) => <Branch key={k.agent.id} row={k} {...props} />)}
      {more > 0 && (
        <li>
          <button type="button" className="act my-1 ml-8" disabled={props.loading.has(parentId ?? TOP_KEY) || props.loading.has(TOP_KEY)}
            onClick={() => props.loadMore(parentId, page.rows.length)}>
            Mostra altri {num(Math.min(more, PAGE))} <span className="text-surface-400">· ne restano {num(more)}</span>
          </button>
        </li>
      )}
    </>
  );
}

function Branch({ row, forceOpen = false, ...props }: TreeProps & { row: TreeRow; forceOpen?: boolean }) {
  const id = row.agent.id;
  const hasKids = row.direct_count > 0;
  const opened = hasKids && (forceOpen || props.open.has(id));
  const page = props.pageOf(id);
  const gone = row.mamify && !row.mamify.present;
  const selected = props.selectedId === id;
  return (
    <li role="treeitem" aria-expanded={hasKids ? opened : undefined} aria-selected={selected}>
      <div
        className={`grid grid-cols-[minmax(0,1fr)_auto] items-center gap-2 rounded-2xl px-2 py-1.5 transition-colors md:grid-cols-[minmax(0,1fr)_72px_84px_64px_72px] ${
          selected ? "bg-white/15" : "hover:bg-white/5"
        }`}
      >
        <div className="flex min-w-0 items-center gap-2">
          {hasKids && !forceOpen ? (
            <button type="button" onClick={() => props.toggle(row)} aria-label={opened ? `Chiudi il ramo di ${row.agent.name}` : `Apri il ramo di ${row.agent.name}`}
              className="flex h-6 w-6 shrink-0 items-center justify-center rounded-lg text-surface-300 hover:bg-white/10 hover:text-white">
              <svg viewBox="0 0 20 20" className={`h-3.5 w-3.5 transition-transform ${opened ? "rotate-90" : ""}`} fill="currentColor" aria-hidden="true"><path d="M7 5l6 5-6 5V5z" /></svg>
            </button>
          ) : (
            <span className="flex h-6 w-6 shrink-0 items-center justify-center" aria-hidden="true"><span className="h-1.5 w-1.5 rounded-full bg-white/25" /></span>
          )}
          <button type="button" onClick={() => props.onSelect(id)} className="flex min-w-0 items-center gap-2 text-left">
            <span className={`relative flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-[11px] font-black ${
              row.level ? "bg-gradient-to-br from-brand-500 to-accent-500 text-white" : "bg-white/10 text-surface-200"} ${gone ? "opacity-50" : ""}`}>
              {initials(row.agent.name)}
              {row.subscription_paid && <span className="absolute -bottom-0.5 -right-0.5 h-2.5 w-2.5 rounded-full border-2 border-surface-900 bg-success-400" title="Mensilità del mese pagata" />}
            </span>
            <span className="min-w-0">
              <span className="flex flex-wrap items-center gap-1.5">
                <span className={`truncate font-semibold ${gone ? "text-surface-400 line-through" : "text-white"}`}>{row.agent.name}</span>
                {id === props.selfId && <Chip tone="info">tu</Chip>}
                <LevelBadge level={row.level} />
              </span>
              <span className="block truncate text-[11px] text-surface-400">
                {row.agent.code}
                {hasKids && <span className="md:hidden"> · {num(row.direct_count)} diretti · {num(row.network_size)} in rete</span>}
              </span>
            </span>
          </button>
        </div>
        <span className="hidden text-right tabular-nums text-surface-200 md:block">{num(row.bcp)}</span>
        <span className="text-right text-sm font-bold tabular-nums text-white">{num(row.bct)}<span className="ml-0.5 text-[10px] font-normal text-surface-400 md:hidden">BC</span></span>
        <span className="hidden text-right tabular-nums text-surface-200 md:block">{row.direct_count ? num(row.direct_count) : "—"}</span>
        <span className="hidden text-right tabular-nums text-surface-200 md:block">{row.network_size ? num(row.network_size) : "—"}</span>
      </div>
      {opened && (
        <ul role="group" className="ml-[19px] space-y-0.5 border-l border-white/10 pl-2.5">
          {!page && props.loading.has(id) ? (
            <li className="px-2 py-1.5 text-xs text-surface-400">Caricamento del ramo…</li>
          ) : (
            <Children parentId={id} page={page} {...props} />
          )}
        </ul>
      )}
    </li>
  );
}

/*
 * Horizontal tree: the top on the left, each opened branch grows to the
 * right. Each child row carries its own connectors (a stub from the shared
 * vertical line), so the lines follow the rows whatever their height.
 */
function HChildren({ parentId, page, ...props }: TreeProps & { parentId: string | null; page: Page | undefined }) {
  if (!page) return null;
  const more = page.total - page.rows.length;
  const items: ReactNode[] = page.rows.map((k) => <HBranch key={k.agent.id} row={k} {...props} />);
  if (more > 0) {
    items.push(
      <button key="__more" type="button" className="act whitespace-nowrap" disabled={props.loading.has(parentId ?? TOP_KEY) || props.loading.has(TOP_KEY)}
        onClick={() => props.loadMore(parentId, page.rows.length)}>
        Mostra altri {num(Math.min(more, PAGE))} <span className="text-surface-400">· ne restano {num(more)}</span>
      </button>,
    );
  }
  return <Rows items={items} />;
}

function Rows({ items }: { items: ReactNode[] }) {
  const only = items.length === 1;
  return (
    <div role="group" className="flex flex-col">
      {items.map((item, i) => (
        <div key={i} className="relative flex items-center py-1 pl-6">
          {!only && (
            <span aria-hidden="true" className="absolute left-0 w-px bg-white/20"
              style={{ top: i === 0 ? "50%" : 0, bottom: i === items.length - 1 ? "50%" : 0 }} />
          )}
          <span aria-hidden="true" className="absolute left-0 top-1/2 h-px w-6 bg-white/20" />
          {item}
        </div>
      ))}
    </div>
  );
}

function HBranch({ row, forceOpen = false, ...props }: TreeProps & { row: TreeRow; forceOpen?: boolean }) {
  const id = row.agent.id;
  const hasKids = row.direct_count > 0;
  const opened = hasKids && (forceOpen || props.open.has(id));
  const page = props.pageOf(id);
  const gone = row.mamify && !row.mamify.present;
  const selected = props.selectedId === id;
  return (
    <div className="flex items-center" role="treeitem" aria-expanded={hasKids ? opened : undefined} aria-selected={selected}>
      <div className={`relative w-56 shrink-0 rounded-2xl border px-3 py-2 transition-colors ${
        selected ? "border-accent-400/70 bg-white/15" : id === props.selfId ? "border-brand-400/60 bg-white/[0.07]" : "border-white/10 bg-white/[0.04] hover:bg-white/[0.08]"}`}>
        <button type="button" onClick={() => props.onSelect(id)} className="flex w-full min-w-0 items-center gap-2 text-left">
          <span className={`relative flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-[11px] font-black ${
            row.level ? "bg-gradient-to-br from-brand-500 to-accent-500 text-white" : "bg-white/10 text-surface-200"} ${gone ? "opacity-50" : ""}`}>
            {initials(row.agent.name)}
            {row.subscription_paid && <span className="absolute -bottom-0.5 -right-0.5 h-2.5 w-2.5 rounded-full border-2 border-surface-900 bg-success-400" title="Mensilità del mese pagata" />}
          </span>
          <span className="min-w-0 flex-1">
            <span className="flex items-center gap-1.5">
              <span className={`truncate text-sm font-semibold ${gone ? "text-surface-400 line-through" : "text-white"}`} title={row.agent.name}>{row.agent.name}</span>
              {id === props.selfId && <Chip tone="info">tu</Chip>}
            </span>
            <span className="flex items-center gap-1.5 text-[11px] text-surface-400">
              <span className="truncate">{row.agent.code}</span>
              <LevelBadge level={row.level} />
            </span>
          </span>
        </button>
        <div className="mt-1.5 flex items-center justify-between gap-2 border-t border-white/10 pt-1.5 text-[11px] text-surface-300">
          <span><b className="tabular-nums text-white">{num(row.bct)}</b> BCT</span>
          <span>{hasKids ? <>{num(row.direct_count)} dir. · {num(row.network_size)} rete</> : "nessun diretto"}</span>
        </div>
        {hasKids && !forceOpen && (
          <button type="button" onClick={() => props.toggle(row)}
            aria-label={opened ? `Chiudi il ramo di ${row.agent.name}` : `Apri il ramo di ${row.agent.name}`}
            className={`absolute -right-3 top-1/2 z-10 flex h-6 min-w-6 -translate-y-1/2 items-center justify-center rounded-full border px-1 text-[11px] font-black ${
              opened ? "border-white/30 bg-surface-800 text-white" : "border-brand-400/60 bg-brand-600 text-white hover:bg-brand-500"}`}>
            {opened ? "−" : "+"}
          </button>
        )}
      </div>
      {opened && (
        <>
          <span className={`h-px shrink-0 bg-white/20 ${forceOpen ? "w-6" : "w-9"}`} aria-hidden="true" />
          {!page && props.loading.has(id) ? (
            <span className="text-xs text-surface-400">Caricamento del ramo…</span>
          ) : (
            <HChildren parentId={id} page={page} {...props} />
          )}
        </>
      )}
    </div>
  );
}

function PersonCard({
  row,
  sponsor,
  legs,
  levels,
  isSelf,
  sync,
  onFocus,
  onOpenDetail,
  onClose,
}: {
  row: TreeRow;
  sponsor: TreeRow | null;
  legs: Page | undefined;
  levels?: Level[];
  isSelf: boolean;
  /** Who may re-read this branch from Mamify: the admin, or the person themselves. */
  sync: "admin" | "self" | null;
  onFocus: () => void;
  onOpenDetail?: (agentId: string) => void;
  onClose: () => void;
}) {
  const next = row.next_level && levels ? levels.find((l) => l.level === row.next_level) ?? null : null;
  const sortedLegs = [...(legs?.rows ?? [])].sort((a, b) => b.bct - a.bct);
  return (
    <div className="panel space-y-4 rounded-3xl p-5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="kpi-label">{isSelf ? "La tua scheda" : "Scheda"}</p>
          <h3 className="mt-1 truncate text-lg font-black text-white">{row.agent.name}</h3>
          <p className="text-xs text-surface-400">{row.agent.code} · nella rete dal {shortDate(row.joined_at)}</p>
        </div>
        <button type="button" className="act" onClick={onClose} aria-label="Chiudi la scheda">✕</button>
      </div>
      <div className="flex flex-wrap gap-1.5">
        {row.level ? <Chip tone="accent">Livello {row.level}</Chip> : <Chip tone="muted">Nessun livello nel mese</Chip>}
        <Chip tone={row.subscription_paid ? "ok" : "warn"}>{row.subscription_paid ? "Mensilità pagata" : "Mensilità non pagata"}</Chip>
        {row.mamify && !row.mamify.present && <Chip tone="bad">Uscito da Mamify</Chip>}
      </div>
      <div className="grid grid-cols-2 gap-2">
        <MiniFigure label="BCP" value={num(row.bcp)} />
        <MiniFigure label="BCT" value={num(row.bct)} />
        <MiniFigure label="Diretti" value={num(row.direct_count)} />
        <MiniFigure label="In rete" value={num(row.network_size)} />
      </div>
      <dl className="space-y-1 text-xs">
        <Info label="Sponsor">{sponsor ? sponsor.agent.name : row.parent_id ? "—" : "in cima alla rete"}</Info>
        {row.mamify?.email && <Info label="Email"><a className="underline decoration-white/30" href={`mailto:${row.mamify.email}`}>{row.mamify.email}</a></Info>}
        {row.mamify?.phone && <Info label="Telefono"><a className="underline decoration-white/30" href={`tel:${row.mamify.phone}`}>{row.mamify.phone}</a></Info>}
        {row.mamify && <Info label="Cliente Mamify">{row.mamify.id}</Info>}
      </dl>

      {next ? (
        <div className="space-y-2 rounded-2xl bg-white/5 p-3">
          <p className="text-xs font-semibold text-white">Verso il livello {next.level}</p>
          <Progress label="Volume totale" value={row.bct} target={next.total_bc} detail={`${num(row.bct)} / ${bc(next.total_bc)}`} />
          <p className="text-[11px] text-surface-300">
            Gambe al minimo di {bc(next.leg_min_bc)}: <b className="text-white">{row.qualifying_legs}</b> su 3
          </p>
        </div>
      ) : row.level ? (
        <p className="rounded-2xl bg-white/5 p-3 text-xs text-surface-200">Livello massimo raggiunto.</p>
      ) : null}

      <div>
        <p className="kpi-label mb-2">Gambe · {num(row.direct_count)}</p>
        {row.direct_count === 0 ? <p className="text-xs text-surface-400">Nessun diretto.</p> : !legs ? <Loading /> : (
          <div className="max-h-72 space-y-2 overflow-y-auto pr-1">
            {sortedLegs.map((leg) => (
              <Progress
                key={leg.agent.id}
                label={<span>{leg.agent.name} <span className="text-surface-400">· {num(leg.network_size + 1)} persone</span></span>}
                value={leg.bct}
                target={next?.leg_min_bc || 1}
                detail={bc(leg.bct)}
              />
            ))}
            {legs.total > legs.rows.length && (
              <p className="text-[11px] text-surface-400">Le prime {num(legs.rows.length)} gambe di {num(legs.total)}: le altre si vedono aprendo il ramo.</p>
            )}
          </div>
        )}
      </div>

      <div className="flex flex-wrap gap-2 border-t border-white/10 pt-3">
        {row.direct_count > 0 && <button type="button" className="act act-primary" onClick={onFocus}>Apri solo questo ramo</button>}
        {onOpenDetail && <button type="button" className="act" onClick={() => onOpenDetail(row.agent.id)}>Scheda completa</button>}
      </div>
      {sync && row.mamify && (
        <div className="border-t border-white/10 pt-3">
          <BranchSyncButton key={row.agent.id} agentId={row.agent.id} self={sync === "self"} compact />
        </div>
      )}
    </div>
  );
}

function MiniFigure({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl bg-white/5 px-3 py-2">
      <p className="kpi-label">{label}</p>
      <p className="text-base font-black tabular-nums text-white">{value}</p>
    </div>
  );
}

function Info({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex justify-between gap-3">
      <dt className="text-surface-400">{label}</dt>
      <dd className="min-w-0 truncate text-right text-surface-100">{children}</dd>
    </div>
  );
}
