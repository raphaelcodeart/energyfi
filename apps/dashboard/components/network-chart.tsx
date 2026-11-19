"use client";

import { useCallback, useMemo, useRef, useState, type CSSProperties } from "react";

/* Commercial network org chart. Horizontal by default (the top person on
   the left, branches opening to the right); "Verticale" gives the classic
   chart with the root at the top. The choice stays in the browser.

   1. Flex layout with CSS connectors (globals.css §7): no JS measuring, so
      lines stay correct when branches open, on zoom and on resize.
   2. Open/closed state is one `Set` of ids in the parent, not per-node
      state, so expand all, collapse all and search auto-open are set
      operations.
   3. The level color is passed as an inline CSS variable (`--lvl`), since
      Tailwind cannot see classes composed at runtime. */

export interface TreeNode {
  agent_id: string;
  depth: number;
  display_name: string;
  promoter_code: string;
  status: string;
  role_label: string | null;
  /** The account is frozen (cannot log in), unlike `status`, the agent
      lifecycle. Only admins ever see true: for everyone else the server
      prunes the member and its subtree (network/service.py::get_branch). */
  is_frozen?: boolean;
  children: TreeNode[];
}

/** "Mario Rossi" -> "Mario R.", keeping cards narrow. */
export function formatShortName(displayName: string): string {
  const parts = displayName.trim().split(/\s+/).filter(Boolean);
  if (parts.length <= 1) return displayName;
  const given = parts.slice(0, -1).join(" ");
  const surnameInitial = parts[parts.length - 1]!.charAt(0).toUpperCase();
  return `${given} ${surnameInitial}.`;
}

function initialsOf(displayName: string): string {
  const parts = displayName.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0]!.slice(0, 2).toUpperCase();
  return (parts[0]![0]! + parts[parts.length - 1]![0]!).toUpperCase();
}

/* --- Color by depth ---
   Shallow levels stay close to the brand; deeper levels use distant hues
   that only need to tell levels apart. Colors repeat past twelve levels. */
const ROOT_TINT = "#1e6cf8";

const DEPTH_TINTS = [
  "#4dd7ff",
  "#d946ef",
  "#a855f7",
  "#71a9fb",
  "#fbbf24",
  "#34d399",
  "#38bdf8",
  "#81b9f0",
  "#c084fc",
  "#2dd4bf",
  "#a5b9fc",
  "#818cf8",
];

export function depthTint(depth: number): string {
  if (depth === 0) return ROOT_TINT;
  return DEPTH_TINTS[(depth - 1) % DEPTH_TINTS.length]!;
}

export function depthLabel(depth: number): string {
  if (depth === 0) return "Tu";
  if (depth === 1) return "Livello 1 · Diretto";
  return `Livello ${depth}`;
}

const STATUS_TINT: Record<string, string> = {
  ACTIVE: "#34d399",
  SUSPENDED: "#fbbf24",
  TERMINATED: "#71a9fb",
};

const STATUS_TITLE: Record<string, string> = {
  ACTIVE: "Attivo",
  SUSPENDED: "Sospeso",
  TERMINATED: "Cessato",
};

/** Legend of the levels actually present. */
export function LevelLegend({ maxDepth }: { maxDepth: number }) {
  return (
    <div className="flex flex-wrap items-center gap-1.5 mb-5 pb-4 border-b border-white/5 light:border-surface-200">
      {Array.from({ length: maxDepth + 1 }, (_, depth) => (
        <span
          key={depth}
          className="inline-flex items-center gap-1.5 rounded-lg border px-2 py-1 text-[10px] font-bold"
          style={
            {
              "--lvl": depthTint(depth),
              color: "var(--lvl)",
              background: "color-mix(in srgb, var(--lvl) 12%, transparent)",
              borderColor: "color-mix(in srgb, var(--lvl) 30%, transparent)",
            } as CSSProperties
          }
        >
          <span className="h-1.5 w-1.5 rounded-full" style={{ background: "var(--lvl)" }} />
          {depthLabel(depth)}
        </span>
      ))}
    </div>
  );
}

/* --- Tree helpers --- */

export function countNodes(node: TreeNode): number {
  return 1 + node.children.reduce((total, child) => total + countNodes(child), 0);
}

/** Total descendants, not just direct children (shown on the branch pill). */
function countDescendants(node: TreeNode): number {
  return node.children.reduce((total, child) => total + countNodes(child), 0);
}

function collectIds(node: TreeNode, into: Set<string>): Set<string> {
  into.add(node.agent_id);
  node.children.forEach((child) => collectIds(child, into));
  return into;
}

/** Ancestor ids of the search matches: opening only these reveals the
    results without expanding the whole network. */
function pathsToMatches(node: TreeNode, matches: (n: TreeNode) => boolean, into: Set<string>): boolean {
  const childHit = node.children.map((child) => pathsToMatches(child, matches, into)).some(Boolean);
  if (childHit) into.add(node.agent_id);
  return childHit || matches(node);
}

/* --- Card --- */

function NodeCard({
  node,
  open,
  onToggle,
  onSelect,
  onCopy,
  copied,
  focused,
}: {
  node: TreeNode;
  open: boolean;
  onToggle: () => void;
  onSelect?: (agentId: string, displayName: string) => void;
  onCopy: (agentId: string) => void;
  copied: boolean;
  focused: boolean;
}) {
  const tint = depthTint(node.depth);
  const descendants = countDescendants(node);
  const statusTint = STATUS_TINT[node.status] ?? "#6f666a";

  return (
    <div className="org-card" style={{ "--lvl": tint } as CSSProperties} data-focus={focused}>
      {/* Monogram */}
      <span
        className="relative grid h-9 w-9 shrink-0 place-items-center rounded-xl text-[11px] font-bold text-white"
        style={{ background: `linear-gradient(135deg, ${tint}, color-mix(in srgb, ${tint} 45%, #03163c))` }}
      >
        {initialsOf(node.display_name)}
        <span
          className="absolute -bottom-0.5 -right-0.5 h-2.5 w-2.5 rounded-full border-2"
          style={{ background: statusTint, borderColor: "var(--bg-base)" }}
          title={STATUS_TITLE[node.status] ?? node.status}
        />
      </span>

      <span className="flex min-w-0 flex-col items-start">
        <span className="flex items-center gap-1.5">
          {onSelect ? (
            <button
              onClick={() => onSelect(node.agent_id, node.display_name)}
              className="cursor-pointer text-sm font-semibold text-white light:text-surface-900 transition hover:text-brand-400"
              title="Apri la scheda completa del collaboratore"
            >
              {formatShortName(node.display_name)}
            </button>
          ) : (
            <span className="text-sm font-semibold text-white light:text-surface-900">
              {formatShortName(node.display_name)}
            </span>
          )}

          {node.role_label && (
            <span className="rounded-md border border-white/10 light:border-surface-300 bg-white/5 light:bg-surface-900/5 px-1.5 py-px text-[9px] font-bold text-surface-300 light:text-surface-600">
              {node.role_label}
            </span>
          )}

          {node.is_frozen && (
            <span
              className="rounded-md border border-danger-500/40 bg-danger-500/15 px-1.5 py-px text-[9px] font-bold text-danger-400"
              title="Account congelato: non può accedere. Visibile solo agli amministratori."
            >
              CONGELATO
            </span>
          )}
        </span>

        <span className="mt-0.5 flex items-center gap-1.5">
          <span className="font-mono text-[10px] text-surface-500">{node.promoter_code}</span>
          <button
            onClick={() => onCopy(node.agent_id)}
            className="cursor-pointer rounded p-0.5 text-surface-500 transition hover:bg-white/5 hover:text-white light:hover:text-surface-900"
            title="Copia UUID completo"
          >
            {copied ? (
              <svg className="h-3 w-3 text-success-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
              </svg>
            ) : (
              <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 012-2h2a2 2 0 012 2" />
              </svg>
            )}
          </button>
          <span className="text-[10px] font-semibold" style={{ color: tint }}>
            {depthLabel(node.depth)}
          </span>
        </span>
      </span>

      {descendants > 0 && (
        <button className="org-toggle shrink-0" data-open={open} onClick={onToggle} title={open ? "Chiudi il ramo" : "Apri il ramo"}>
          {descendants}
          <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M19 9l-7 7-7-7" />
          </svg>
        </button>
      )}
    </div>
  );
}

/* --- Recursive branch --- */

function Branch({
  node,
  isOpen,
  onToggle,
  onSelect,
  onCopy,
  copiedId,
  matchIds,
}: {
  node: TreeNode;
  isOpen: (id: string) => boolean;
  onToggle: (id: string) => void;
  onSelect?: (agentId: string, displayName: string) => void;
  onCopy: (agentId: string) => void;
  copiedId: string | null;
  matchIds: Set<string> | null;
}) {
  const open = isOpen(node.agent_id) && node.children.length > 0;

  return (
    <div className="org-node">
      <NodeCard
        node={node}
        open={open}
        onToggle={() => onToggle(node.agent_id)}
        onSelect={onSelect}
        onCopy={onCopy}
        copied={copiedId === node.agent_id}
        focused={matchIds?.has(node.agent_id) ?? false}
      />

      {open && (
        <>
          <span className="org-trunk" />
          {/* Keyed on the child count so the row remounts and replays its entry
              animation on every open. */}
          <div className="org-children" data-entering="true" key={`${node.agent_id}-open`}>
            {node.children.map((child, i) => (
              <div className="org-child" key={child.agent_id} style={{ "--i": i } as CSSProperties}>
                <Branch
                  node={child}
                  isOpen={isOpen}
                  onToggle={onToggle}
                  onSelect={onSelect}
                  onCopy={onCopy}
                  copiedId={copiedId}
                  matchIds={matchIds}
                />
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

/* --- Container: zoom, drag, open state --- */

type Orientation = "horizontal" | "vertical";
const ORIENT_KEY = "sosnet.orgchart.orient";

function readOrientation(): Orientation {
  try {
    return typeof window !== "undefined" && window.localStorage.getItem(ORIENT_KEY) === "vertical" ? "vertical" : "horizontal";
  } catch {
    return "horizontal";
  }
}

const ZOOM_MIN = 0.45;
const ZOOM_MAX = 1.5;
const ZOOM_STEP = 0.15;

export function NetworkChart({
  roots,
  onCopy,
  copiedId,
  onNodeSelect,
  expandAll = false,
  highlight,
}: {
  roots: TreeNode[];
  onCopy: (agentId: string) => void;
  copiedId: string | null;
  onNodeSelect?: (agentId: string, displayName: string) => void;
  /** Driven by the panel's "Espandi tutto" button. */
  expandAll?: boolean;
  /** Search text: matches are highlighted and their ancestors opened. */
  highlight?: string;
}) {
  // Roots and their first level start open.
  const [openIds, setOpenIds] = useState<Set<string>>(() => {
    const initial = new Set<string>();
    roots.forEach((root) => {
      initial.add(root.agent_id);
      root.children.forEach((child) => initial.add(child.agent_id));
    });
    return initial;
  });
  const [orient, setOrientState] = useState<Orientation>(readOrientation);
  const setOrient = (next: Orientation) => {
    setOrientState(next);
    setPan({ x: 0, y: 0 });
    try { window.localStorage.setItem(ORIENT_KEY, next); } catch { /* per-viewer convenience only */ }
  };
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const panOrigin = useRef<{ x: number; y: number; panX: number; panY: number } | null>(null);
  const [panning, setPanning] = useState(false);

  const query = (highlight ?? "").trim().toLowerCase();

  // Search matches plus their ancestors.
  const { matchIds, forcedOpen } = useMemo(() => {
    if (!query) return { matchIds: null as Set<string> | null, forcedOpen: null as Set<string> | null };
    const matches = (n: TreeNode) =>
      n.display_name.toLowerCase().includes(query) || n.promoter_code.toLowerCase().includes(query);
    const ancestors = new Set<string>();
    const hits = new Set<string>();
    const walk = (n: TreeNode) => {
      if (matches(n)) hits.add(n.agent_id);
      n.children.forEach(walk);
    };
    roots.forEach((root) => {
      walk(root);
      pathsToMatches(root, matches, ancestors);
    });
    return { matchIds: hits, forcedOpen: ancestors };
  }, [roots, query]);

  const allIds = useMemo(() => {
    const ids = new Set<string>();
    roots.forEach((root) => collectIds(root, ids));
    return ids;
  }, [roots]);

  const isOpen = useCallback(
    (id: string) => {
      if (expandAll) return true;
      if (forcedOpen?.has(id)) return true;
      return openIds.has(id);
    },
    [expandAll, forcedOpen, openIds],
  );

  const toggle = useCallback(
    (id: string) => {
      // With "expand all" on, the panel button owns the open state.
      if (expandAll) return;
      setOpenIds((prev) => {
        const next = new Set(prev);
        if (next.has(id)) next.delete(id);
        else next.add(id);
        return next;
      });
    },
    [expandAll],
  );

  const maxDepth = useMemo(() => {
    let deepest = 0;
    const walk = (n: TreeNode) => {
      deepest = Math.max(deepest, n.depth);
      n.children.forEach(walk);
    };
    roots.forEach(walk);
    return deepest;
  }, [roots]);

  function onPointerDown(e: React.PointerEvent<HTMLDivElement>) {
    // Left button only, and never from a control, so a drag cannot open a
    // branch by accident.
    if (e.button !== 0 || (e.target as HTMLElement).closest("button")) return;
    panOrigin.current = { x: e.clientX, y: e.clientY, panX: pan.x, panY: pan.y };
    setPanning(true);
    e.currentTarget.setPointerCapture(e.pointerId);
  }

  function onPointerMove(e: React.PointerEvent<HTMLDivElement>) {
    const origin = panOrigin.current;
    if (!origin) return;
    setPan({ x: origin.panX + (e.clientX - origin.x), y: origin.panY + (e.clientY - origin.y) });
  }

  function endPan(e: React.PointerEvent<HTMLDivElement>) {
    panOrigin.current = null;
    setPanning(false);
    if (e.currentTarget.hasPointerCapture(e.pointerId)) e.currentTarget.releasePointerCapture(e.pointerId);
  }

  function resetView() {
    setZoom(1);
    setPan({ x: 0, y: 0 });
  }

  if (roots.length === 0) return null;

  return (
    <div className="space-y-4">
      <LevelLegend maxDepth={maxDepth} />

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-1 rounded-xl border border-white/5 light:border-surface-200 bg-white/5 light:bg-surface-900/5 p-1">
          <button
            onClick={() => setZoom((z) => Math.max(ZOOM_MIN, +(z - ZOOM_STEP).toFixed(2)))}
            disabled={zoom <= ZOOM_MIN}
            className="grid h-7 w-7 cursor-pointer place-items-center rounded-lg text-surface-300 light:text-surface-600 transition hover:bg-white/10 light:hover:bg-surface-900/10 disabled:cursor-not-allowed disabled:opacity-35"
            title="Riduci"
          >
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeWidth={2} d="M5 12h14" />
            </svg>
          </button>
          <span className="min-w-[3.25rem] text-center font-mono text-[11px] font-semibold text-surface-400 light:text-surface-500">
            {Math.round(zoom * 100)}%
          </span>
          <button
            onClick={() => setZoom((z) => Math.min(ZOOM_MAX, +(z + ZOOM_STEP).toFixed(2)))}
            disabled={zoom >= ZOOM_MAX}
            className="grid h-7 w-7 cursor-pointer place-items-center rounded-lg text-surface-300 light:text-surface-600 transition hover:bg-white/10 light:hover:bg-surface-900/10 disabled:cursor-not-allowed disabled:opacity-35"
            title="Ingrandisci"
          >
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeWidth={2} d="M12 5v14M5 12h14" />
            </svg>
          </button>
          <span className="mx-1 h-4 w-px bg-white/10 light:bg-surface-300" />
          <button
            onClick={resetView}
            className="cursor-pointer rounded-lg px-2 py-1 text-[11px] font-semibold text-surface-300 light:text-surface-600 transition hover:bg-white/10 light:hover:bg-surface-900/10"
            title="Torna alla vista iniziale"
          >
            Centra
          </button>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <div role="group" aria-label="Direzione dell'albero" className="flex overflow-hidden rounded-lg border border-white/5 light:border-surface-200">
            {([["horizontal", "Orizzontale →"], ["vertical", "Verticale ↓"]] as const).map(([k, label]) => (
              <button
                key={k}
                type="button"
                aria-pressed={orient === k}
                onClick={() => setOrient(k)}
                className={`cursor-pointer px-2.5 py-1.5 text-[11px] font-semibold transition ${
                  orient === k
                    ? "bg-brand-600/30 text-white light:text-surface-900"
                    : "bg-white/5 light:bg-surface-900/5 text-surface-300 light:text-surface-600 hover:bg-white/10"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
          <button
            onClick={() => setOpenIds(new Set(allIds))}
            className="cursor-pointer rounded-lg border border-white/5 light:border-surface-200 bg-white/5 light:bg-surface-900/5 px-2.5 py-1.5 text-[11px] font-semibold text-surface-300 light:text-surface-600 transition hover:bg-white/10 light:hover:bg-surface-900/10"
          >
            Apri tutti i rami
          </button>
          <button
            onClick={() => setOpenIds(new Set(roots.map((r) => r.agent_id)))}
            className="cursor-pointer rounded-lg border border-white/5 light:border-surface-200 bg-white/5 light:bg-surface-900/5 px-2.5 py-1.5 text-[11px] font-semibold text-surface-300 light:text-surface-600 transition hover:bg-white/10 light:hover:bg-surface-900/10"
          >
            Chiudi tutti i rami
          </button>
          <span className="hidden sm:inline text-[10px] text-surface-500">trascina per spostare</span>
        </div>
      </div>

      <div
        className="org-viewport relative flex overflow-auto rounded-2xl border border-white/5 light:border-surface-200 bg-surface-950/30 light:bg-white/50 p-6"
        data-panning={panning}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={endPan}
        onPointerCancel={endPan}
        style={{ minHeight: 320, maxHeight: "72vh" }}
      >
        <div
          // `m-auto` in a flex container, not `mx-auto`: on a block, an overflowing
          // chart would get an unreachable left margin and be cut off.
          className={`org-canvas flex w-max flex-col gap-10 ${orient === "horizontal" ? "my-auto items-start" : "m-auto items-center"}`}
          data-orient={orient}
          style={{ transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})` }}
        >
          {roots.map((root) => (
            <div key={root.agent_id} className={`flex flex-col gap-2 ${orient === "horizontal" ? "items-start" : "items-center"}`}>
              {roots.length > 1 && (
                <span className="text-[10px] font-bold uppercase tracking-wider text-surface-500">
                  Radice di rete · {countNodes(root)} membri
                </span>
              )}
              <Branch
                node={root}
                isOpen={isOpen}
                onToggle={toggle}
                onSelect={onNodeSelect}
                onCopy={onCopy}
                copiedId={copiedId}
                matchIds={matchIds}
              />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
