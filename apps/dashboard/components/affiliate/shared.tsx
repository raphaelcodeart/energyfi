"use client";

import type { ReactNode } from "react";

/* Small building blocks shared by the Digital Ambassador and admin views. */

export function SectionTitle({ eyebrow, title, children }: { eyebrow?: string; title: string; children?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-3">
      <div>
        {eyebrow && <p className="kpi-label">{eyebrow}</p>}
        <h2 className="mt-1 text-xl font-black tracking-tight text-white sm:text-2xl">{title}</h2>
      </div>
      {children}
    </div>
  );
}

export function ErrorNote({ message }: { message: string | null | undefined }) {
  if (!message) return null;
  return (
    <div role="alert" className="rounded-2xl border border-danger-500/30 bg-danger-500/10 p-3.5 text-xs text-danger-300">
      {message}
    </div>
  );
}

export function OkNote({ message }: { message: string | null | undefined }) {
  if (!message) return null;
  return (
    <div role="status" className="rounded-2xl border border-success-500/30 bg-success-500/10 p-3.5 text-xs text-success-300">
      {message}
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="panel rounded-3xl p-8 text-center text-sm text-surface-300">{children}</div>;
}

export function Loading() {
  return <div className="panel rounded-3xl p-8 text-center text-sm text-surface-300">Caricamento…</div>;
}

/** Progress towards a threshold; full when reached. */
export function Progress({ value, target, label, detail }: { value: number; target: number; label: ReactNode; detail?: ReactNode }) {
  const ratio = target > 0 ? Math.min(1, value / target) : 0;
  const done = target > 0 && value >= target;
  return (
    <div>
      <div className="flex items-baseline justify-between gap-3 text-xs">
        <span className="text-surface-200">{label}</span>
        <span className={`tabular-nums font-semibold ${done ? "text-success-300" : "text-white"}`}>{detail}</span>
      </div>
      <div className="meter mt-1.5">
        <i style={{ width: `${Math.round(ratio * 100)}%` }} />
      </div>
    </div>
  );
}

/** The brand's rainbow underline, from the SOS Affiliate logo. */
export function Rainbow({ className = "" }: { className?: string }) {
  return <span aria-hidden="true" className={`sos-rainbow block h-1 rounded-full ${className}`} />;
}

export function Modal({ title, onClose, children, wide = false }: { title: string; onClose: () => void; children: ReactNode; wide?: boolean }) {
  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm animate-fade-in"
      role="dialog"
      aria-modal="true"
      aria-label={title}
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div className={`panel max-h-[90vh] w-full overflow-y-auto rounded-3xl p-6 ${wide ? "max-w-3xl" : "max-w-lg"}`}>
        <div className="mb-4 flex items-center justify-between gap-4">
          <h3 className="text-lg font-black tracking-tight text-white">{title}</h3>
          <button type="button" onClick={onClose} className="act" aria-label="Chiudi">
            ✕
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: ReactNode }) {
  return (
    <label className="block">
      <span className="kpi-label">{label}</span>
      <div className="mt-1.5">{children}</div>
      {hint && <span className="mt-1 block text-[11px] text-surface-400">{hint}</span>}
    </label>
  );
}
