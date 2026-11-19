import type { CSSProperties, ReactNode } from "react";

/*
 * Building blocks for table rows (styles in globals.css §12). Rows put the
 * identity first (orb + name + detail), state as a glowing chip, money as a
 * big figure with an optional meter, and actions at the end.
 */

/** Stable hue per name, so a person keeps their color everywhere. */
function hueFor(text: string): number {
  let hash = 0;
  for (let i = 0; i < text.length; i++) hash = (hash * 31 + text.charCodeAt(i)) >>> 0;
  return 330 + (hash % 70); // magenta .. red .. orange
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "·";
  const first = parts[0]?.[0] ?? "";
  const last = parts.length > 1 ? (parts[parts.length - 1]?.[0] ?? "") : "";
  return (first + last).toUpperCase();
}

/** Initials in a tilted gradient tile. */
export function Orb({ name, icon }: { name: string; icon?: ReactNode }) {
  return (
    <span className="orb" style={{ "--orb-h": hueFor(name) } as CSSProperties} aria-hidden="true">
      {icon ?? initials(name)}
    </span>
  );
}

/** Identity cell: orb, title, and a quieter detail line. */
export function Identity({ name, detail, icon, children }: { name: string; detail?: ReactNode; icon?: ReactNode; children?: ReactNode }) {
  return (
    <div className="flex min-w-0 items-center gap-3">
      <Orb name={name} icon={icon} />
      <div className="min-w-0">
        <div className="truncate text-[13.5px] font-bold text-white">{name}</div>
        {detail && <div className="truncate text-[11px] text-surface-400">{detail}</div>}
        {children}
      </div>
    </div>
  );
}

/** Two-line cell without the orb. */
export function Stack({ title, detail, className = "" }: { title: ReactNode; detail?: ReactNode; className?: string }) {
  return (
    <div className={`min-w-0 ${className}`}>
      <div className="truncate text-[13px] font-semibold text-white">{title}</div>
      {detail && <div className="truncate text-[11px] text-surface-400">{detail}</div>}
    </div>
  );
}

export type ChipTone = "ok" | "warn" | "bad" | "info" | "muted" | "accent";

/** State chip with a glowing dot; `live` makes the dot beat. */
export function Chip({ tone, children, live = false }: { tone: ChipTone; children: ReactNode; live?: boolean }) {
  return (
    <span className={`chip chip-${tone}`} data-live={live || undefined}>
      {children}
    </span>
  );
}

/** Short reference instead of a full UUID; the full value stays in the tooltip. */
export function IdTag({ id, prefix = "#" }: { id: string | null | undefined; prefix?: string }) {
  if (!id) return <span className="text-surface-500">—</span>;
  return (
    <span className="tag-id" title={id}>
      {prefix}
      {id.replace(/-/g, "").slice(0, 6).toUpperCase()}
    </span>
  );
}

/** Figure plus an optional meter (0..1) and detail line. */
export function Figure({ value, detail, ratio }: { value: ReactNode; detail?: ReactNode; ratio?: number | null }) {
  return (
    <div className="min-w-[96px] text-right">
      <div className="text-[15px] font-black tabular-nums text-white">{value}</div>
      {detail && <div className="text-[10.5px] text-surface-400 tabular-nums">{detail}</div>}
      {ratio != null && (
        <div className="meter mt-1.5">
          <i style={{ width: `${Math.max(3, Math.min(100, ratio * 100))}%` }} />
        </div>
      )}
    </div>
  );
}

/** Container for the row's buttons (use `.act` / `.act act-primary`). */
export function RowActions({ children }: { children: ReactNode }) {
  return <div className="row-actions">{children}</div>;
}

/** Big number tile for summaries above a table. */
export function KpiTile({ label, value, hint, onClick, active = false }: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  onClick?: () => void;
  active?: boolean;
}) {
  const Tag = onClick ? "button" : "div";
  return (
    <Tag
      onClick={onClick}
      data-tilt
      className={`panel relative w-full overflow-hidden rounded-3xl p-5 text-left ${onClick ? "cursor-pointer" : ""} ${
        active ? "ring-2 ring-white/70" : ""
      }`}
    >
      <div className="kpi-label">{label}</div>
      <div className="kpi-value mt-3">{value}</div>
      {hint && <div className="mt-2 text-[11px] text-surface-300">{hint}</div>}
      <span className="pointer-events-none absolute -right-6 -top-6 h-24 w-24 rounded-full bg-gradient-to-br from-brand-400/40 to-accent-400/10 blur-2xl" />
    </Tag>
  );
}
