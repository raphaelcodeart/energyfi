"use client";

import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";

export interface PaletteEntry {
  key: string;
  label: string;
  description?: string;
  icon: ReactNode;
}

/**
 * Quick jump between sections with ⌘K (Ctrl+K on Windows/Linux).
 * Keyboard support: the filter is focused on open, arrows move the selection,
 * Enter confirms, Esc closes, and the selected item is scrolled into view.
 */
export function CommandPalette({
  entries,
  open,
  onClose,
  onSelect,
  activeKey,
}: {
  entries: PaletteEntry[];
  open: boolean;
  onClose: () => void;
  onSelect: (key: string) => void;
  activeKey?: string;
}) {
  const [query, setQuery] = useState("");
  const [cursor, setCursor] = useState(0);
  const listRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const results = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return entries;
    return entries.filter(
      (e) => e.label.toLowerCase().includes(q) || (e.description ?? "").toLowerCase().includes(q),
    );
  }, [entries, query]);

  // Reset the cursor on each new query so it never highlights a filtered-out item.
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setCursor(0);
  }, [query]);

  useEffect(() => {
    if (!open) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setQuery("");
    const id = requestAnimationFrame(() => inputRef.current?.focus());
    return () => cancelAnimationFrame(id);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    listRef.current?.querySelector<HTMLElement>('[data-cursor="true"]')?.scrollIntoView({ block: "nearest" });
  }, [cursor, open]);

  if (!open) return null;

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setCursor((c) => (results.length === 0 ? 0 : (c + 1) % results.length));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setCursor((c) => (results.length === 0 ? 0 : (c - 1 + results.length) % results.length));
    } else if (e.key === "Enter") {
      e.preventDefault();
      const picked = results[cursor];
      if (picked) {
        onSelect(picked.key);
        onClose();
      }
    } else if (e.key === "Escape") {
      e.preventDefault();
      onClose();
    }
  }

  return (
    <div className="fixed inset-0 z-[70] flex items-start justify-center px-4 pt-[12vh]">
      <div className="animate-fade-in absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />

      <div
        className="pop panel panel-ring relative z-10 w-full max-w-xl overflow-hidden rounded-2xl"
        onKeyDown={handleKeyDown}
      >
        <div className="flex items-center gap-3 border-b border-white/5 light:border-surface-200 px-4 py-3">
          <svg className="h-4 w-4 shrink-0 text-surface-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Vai a…"
            className="w-full bg-transparent text-sm text-white light:text-surface-900 outline-none placeholder:text-surface-500"
          />
          <kbd className="hidden sm:block rounded border border-white/10 light:border-surface-300 px-1.5 py-0.5 font-mono text-[10px] text-surface-500">
            esc
          </kbd>
        </div>

        <div ref={listRef} className="max-h-80 overflow-y-auto p-2">
          {results.length === 0 ? (
            <p className="py-8 text-center text-xs text-surface-500">Nessuna sezione trovata.</p>
          ) : (
            results.map((entry, i) => (
              <button
                key={entry.key}
                data-cursor={i === cursor}
                onMouseEnter={() => setCursor(i)}
                onClick={() => {
                  onSelect(entry.key);
                  onClose();
                }}
                className={`flex w-full cursor-pointer items-center gap-3 rounded-xl px-3 py-2.5 text-left transition ${
                  i === cursor ? "bg-brand-500/15 text-white light:text-surface-900" : "text-surface-300 light:text-surface-600"
                }`}
              >
                <span
                  className={`grid h-8 w-8 shrink-0 place-items-center rounded-lg transition [&_svg]:h-4 [&_svg]:w-4 ${
                    i === cursor ? "bg-brand-500/25 text-brand-300" : "bg-white/5 light:bg-surface-900/5"
                  }`}
                >
                  {entry.icon}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium">{entry.label}</span>
                  {entry.description && (
                    <span className="block truncate text-[11px] text-surface-500">{entry.description}</span>
                  )}
                </span>
                {entry.key === activeKey && (
                  <span className="shrink-0 rounded-full bg-white/5 light:bg-surface-900/5 px-2 py-0.5 text-[9px] font-bold uppercase tracking-wider text-surface-400">
                    qui
                  </span>
                )}
              </button>
            ))
          )}
        </div>
      </div>
    </div>
  );
}

/** Registers ⌘K / Ctrl+K here so users of the palette need not wire the shortcut. */
export function usePaletteShortcut(onOpen: () => void) {
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        onOpen();
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onOpen]);
}
