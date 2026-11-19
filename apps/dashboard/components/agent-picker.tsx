"use client";

import { useEffect, useId, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { lookupAgents, useAgentNames } from "@/lib/agents";

/** "Choose a collaborator" field: type a name or code, pick from the
    matches. Replaces <select>s that listed the whole network.

    `value` is the chosen agent id ("" for none); the name of an already
    chosen one is fetched by id, so forms that open on a saved value show it. */
export function AgentPicker({
  value, onChange, placeholder = "Cerca per nome o codice…", status, allowEmpty = true, emptyLabel = "Nessuno",
  className = "", disabled = false, required = false, ariaLabel = "Collaboratore", excludeId,
}: {
  value: string;
  onChange: (id: string, label?: string) => void;
  placeholder?: string;
  /** Only collaborators in this status (e.g. ACTIVE). */
  status?: string;
  allowEmpty?: boolean;
  emptyLabel?: string;
  className?: string;
  disabled?: boolean;
  required?: boolean;
  ariaLabel?: string;
  excludeId?: string;
}) {
  const [text, setText] = useState("");
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const listId = useId();
  const box = useRef<HTMLDivElement>(null);
  const { data: names } = useAgentNames([value]);
  const chosen = value ? names?.get(value) : undefined;

  useEffect(() => {
    const t = setTimeout(() => setQuery(text.trim()), 250);
    return () => clearTimeout(t);
  }, [text]);

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => { if (box.current && !box.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  const { data: found = [], isFetching } = useQuery({
    queryKey: ["admin", "agents", "lookup", query, status ?? ""],
    queryFn: () => lookupAgents(query, status),
    enabled: open && query.length >= 2,
    staleTime: 60_000,
  });
  const options = found.filter((a) => a.id !== excludeId);

  function pick(id: string, label?: string) {
    onChange(id, label);
    setText("");
    setOpen(false);
  }

  const shown = open ? text : chosen ? `${chosen.display_name} · ${chosen.promoter_code}` : value ? "…" : "";
  return (
    <div ref={box} className={`relative ${className}`}>
      <input
        type="text"
        role="combobox"
        aria-label={ariaLabel}
        aria-expanded={open}
        aria-controls={listId}
        aria-autocomplete="list"
        disabled={disabled}
        required={required && !value}
        className="field w-full rounded-xl px-3 py-2.5 pr-8 text-sm"
        placeholder={value && !open ? "" : placeholder}
        value={shown}
        onFocus={() => { setOpen(true); setActive(0); }}
        onChange={(e) => { setText(e.target.value); setOpen(true); setActive(0); }}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") { e.preventDefault(); setActive((i) => Math.min(i + 1, options.length - 1)); }
          else if (e.key === "ArrowUp") { e.preventDefault(); setActive((i) => Math.max(i - 1, 0)); }
          else if (e.key === "Enter" && open && options[active]) { e.preventDefault(); pick(options[active].id, options[active].display_name); }
          else if (e.key === "Escape") setOpen(false);
        }}
      />
      {value && !disabled && allowEmpty && (
        <button type="button" aria-label="Togli la scelta" onClick={() => pick("")}
          className="absolute right-2 top-1/2 -translate-y-1/2 px-1 text-surface-400 hover:text-white">×</button>
      )}
      {open && (
        <ul id={listId} role="listbox"
          className="absolute z-50 mt-1 max-h-72 w-full overflow-auto rounded-xl border border-white/10 bg-surface-900 py-1 text-sm shadow-xl light:border-surface-200 light:bg-white">
          {allowEmpty && value && (
            <li><button type="button" className="w-full px-3 py-2 text-left text-surface-300 hover:bg-white/5" onClick={() => pick("")}>{emptyLabel}</button></li>
          )}
          {query.length < 2 ? (
            <li className="px-3 py-2 text-xs text-surface-400">Scrivi almeno 2 lettere del nome o del codice.</li>
          ) : isFetching && options.length === 0 ? (
            <li className="px-3 py-2 text-xs text-surface-400">Cerco…</li>
          ) : options.length === 0 ? (
            <li className="px-3 py-2 text-xs text-surface-400">Nessun collaboratore trovato.</li>
          ) : options.map((a, i) => (
            <li key={a.id} role="option" aria-selected={a.id === value}>
              <button type="button" onMouseEnter={() => setActive(i)} onClick={() => pick(a.id, a.display_name)}
                className={`flex w-full items-center justify-between gap-3 px-3 py-2 text-left ${i === active ? "bg-white/10 light:bg-surface-100" : ""}`}>
                <span className="truncate text-white light:text-surface-900">{a.display_name}</span>
                <span className="shrink-0 text-xs text-surface-400">{a.promoter_code}{a.status !== "ACTIVE" ? ` · ${a.status}` : ""}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
