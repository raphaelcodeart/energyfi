"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { SosnetCashAmount } from "@/components/sosnet-cash-amount";
import { friendlyApiError } from "@/lib/api-error";
import {
  euro, formatDateTimeFull, movementDetailRef, movementDirection, movementLabel, movementsOfEntity,
} from "@/lib/accounting-format";
import type { AccountingDetailRead, FinancialMovementRead } from "@/lib/types";
import { Chip, type ChipTone, Figure, Identity } from "@/components/ui/data-cells";

const TONE_CHIP: Record<string, ChipTone> = {
  success: "ok",
  warning: "warn",
  danger: "bad",
  neutral: "muted",
};

const KIND_LABELS: Record<string, string> = {
  WALLET: "Movimento SosnetCash",
  ORDER: "Ordine",
  REDEMPTION: "Riscatto cashback",
  CONTRACT: "Pagamento SOSNET",
};

const TAB_LABELS: Record<string, string> = {
  orders: "Apri in I miei Ordini",
  cashback: "Apri in Riscatta Cashback",
  wallet: "Apri il Wallet",
};

const INSTALMENT_STATUS: Record<string, { label: string; tone: ChipTone }> = {
  PAID: { label: "Pagata", tone: "ok" },
  SCHEDULED: { label: "Prevista", tone: "muted" },
  FAILED: { label: "Non addebitata", tone: "bad" },
};

/**
 * Detail of one movement, or of the order, cashback redemption or contract it
 * belongs to. Related records open in place (with "Indietro" to go back), and
 * the timeline shows when each step happened and who performed it (Stripe or
 * the administrator who confirmed a transfer).
 */
export function AccountingDetailModal({
  initialRef,
  scope,
  movements,
  onClose,
  onOpenTab,
}: {
  initialRef: string;
  scope: "mine" | "admin";
  /** Movements already on screen, used to list those tied to the opened record. */
  movements: FinancialMovementRead[];
  onClose: () => void;
  onOpenTab?: (tab: string) => void;
}) {
  const [stack, setStack] = useState<string[]>([initialRef]);
  const ref = stack[stack.length - 1]!;
  const { data, error, isLoading } = useQuery<AccountingDetailRead>({
    queryKey: ["accounting", scope, "detail", ref],
    queryFn: async () => {
      const res = await fetch(`/api/proxy/accounting/${scope}/detail?ref=${encodeURIComponent(ref)}`);
      if (!res.ok) throw new Error(await friendlyApiError(res));
      return res.json();
    },
  });

  function open(next: string) {
    if (next !== ref) setStack((s) => [...s, next]);
  }

  const linked = data
    ? movementsOfEntity(movements, data).filter((m) => movementDetailRef(m) !== ref || m.kind === "WALLET")
    : [];

  return (
    <div
      className="animate-fade-in fixed inset-0 z-[60] flex items-end justify-center bg-black/70 backdrop-blur-sm sm:items-center sm:p-4"
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="pop max-h-[92vh] w-full overflow-y-auto rounded-t-3xl border border-white/15 bg-surface-950 shadow-2xl sm:max-w-2xl sm:rounded-3xl"
      >
        <div className="sticky top-0 z-10 flex items-center justify-between gap-3 border-b border-white/10 bg-surface-950/95 px-6 py-3 backdrop-blur">
          <div className="flex items-center gap-2 min-w-0">
            {stack.length > 1 && (
              <button
                onClick={() => setStack((s) => s.slice(0, -1))}
                className="act"
              >
                ← Indietro
              </button>
            )}
            <span className="kpi-label truncate">
              {data ? KIND_LABELS[data.kind] : "Dettaglio"}
            </span>
          </div>
          <button onClick={onClose} aria-label="Chiudi" className="act !px-2">
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {isLoading && <div className="m-6 h-48 animate-pulse rounded-3xl bg-white/5" />}
        {error && <p className="m-6 text-sm text-danger-300">{(error as Error).message}</p>}

        {data && (
          <div className="space-y-7 p-6">
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0">
                <h3 className="text-2xl font-black leading-tight tracking-tight text-white">{data.title}</h3>
                {data.subtitle && <p className="mt-1 text-xs text-surface-300">{data.subtitle}</p>}
                {data.status && (
                  <div className="mt-3">
                    <Chip tone={TONE_CHIP[data.status_tone] ?? "muted"} live={data.status_tone === "warning"}>{data.status}</Chip>
                  </div>
                )}
              </div>
              {data.amount_cents != null && (
                <div className={`kpi-value shrink-0 text-right ${data.direction === "in" ? "!text-success-300" : ""}`}>
                  {data.currency === "SOSNETCASH" ? (
                    <SosnetCashAmount cents={Math.abs(data.amount_cents)} sign={data.direction === "out" ? "-" : "+"} />
                  ) : (
                    euro(Math.abs(data.amount_cents))
                  )}
                </div>
              )}
            </div>

            {data.facts.length > 0 && (
              <section>
                <h4 className="kpi-label mb-3">Dettagli</h4>
                <dl className="grid grid-cols-1 gap-x-6 rounded-3xl border border-white/10 bg-white/5 px-5 sm:grid-cols-2">
                  {data.facts.map((fact) => (
                    <div key={fact.label} className="min-w-0 border-b border-white/5 py-3">
                      <dt className="text-[11px] text-surface-400">{fact.label}</dt>
                      <dd className={`break-words text-sm font-semibold text-white ${fact.mono ? "font-mono text-xs" : ""}`}>
                        {fact.value}
                      </dd>
                    </div>
                  ))}
                </dl>
              </section>
            )}

            {data.timeline.length > 0 && (
              <section>
                <h4 className="kpi-label mb-3">Cronologia</h4>
                <ol className="relative ml-2 space-y-4 border-l border-white/15">
                  {data.timeline.map((event, i) => (
                    <li key={`${event.label}-${i}`} className="ml-4">
                      <span
                        className={`absolute -left-[5px] mt-1.5 w-2.5 h-2.5 rounded-full ${
                          event.tone === "pending"
                            ? "bg-surface-600 ring-2 ring-surface-500/30"
                            : event.tone === "warning"
                              ? "bg-warn-400 shadow-[0_0_10px] shadow-warn-400"
                              : "bg-success-400 shadow-[0_0_10px] shadow-success-400"
                        }`}
                      />
                      <p className={`text-sm font-bold ${event.tone === "pending" ? "text-surface-400" : "text-white"}`}>
                        {event.label}
                      </p>
                      <p className="text-[11px] text-surface-400">
                        {event.at ? <span className="font-bold tabular-nums">{formatDateTimeFull(event.at)}</span> : "In attesa"}
                        {event.by && <> · {event.by}</>}
                      </p>
                    </li>
                  ))}
                </ol>
              </section>
            )}

            {data.instalments.length > 0 && (
              <section>
                <h4 className="kpi-label mb-3">
                  {data.instalments.length === 1 ? "Pagamento" : `Rate (${data.instalments.filter((r) => r.status === "PAID").length}/${data.instalments.length} pagate)`}
                </h4>
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs">
                    <thead>
                      <tr>
                        <th className="px-4 py-3">Rata</th>
                        <th className="px-4 py-3">Situazione</th>
                        <th className="px-4 py-3">Incassata</th>
                        <th className="px-4 py-3 text-right">Valore</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.instalments.map((row) => (
                        <tr key={row.number}>
                          <td className="px-4 py-3">
                            <Identity
                              name={`Rata ${row.number}`}
                              detail={`prevista ${new Date(row.due_date).toLocaleDateString("it-IT", { day: "2-digit", month: "short", year: "numeric" })}`}
                              icon={<span className="text-sm font-black">{row.number}</span>}
                            />
                          </td>
                          <td className="px-4 py-3">
                            <Chip tone={INSTALMENT_STATUS[row.status]?.tone ?? "info"}>{INSTALMENT_STATUS[row.status]?.label ?? row.status}</Chip>
                          </td>
                          <td className="px-4 py-3 text-surface-300">
                            {row.paid_at ? (
                              <>
                                <span className="font-bold tabular-nums text-white">{formatDateTimeFull(row.paid_at)}</span>
                                {row.source && <span className="block text-[10px] text-surface-400">{row.source}{row.confirmed_by ? ` · ${row.confirmed_by}` : ""}</span>}
                              </>
                            ) : "—"}
                          </td>
                          <td className="px-4 py-3">
                            <div className="ml-auto w-fit"><Figure value={euro(row.amount_cents)} /></div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            )}

            {(linked.length > 0 || data.related_refs.length > 0) && (
              <section>
                <h4 className="kpi-label mb-3">Collegati</h4>
                <div className="space-y-2">
                  {data.related_refs.map((related) => (
                    <button
                      key={related}
                      onClick={() => open(related)}
                      className="flex w-full cursor-pointer items-center justify-between gap-3 rounded-2xl border border-white/20 bg-white/10 px-4 py-3 text-left transition hover:bg-white/15"
                    >
                      <span className="text-sm font-bold text-white">
                        {related.startsWith("order:") ? "Ordine" : related.startsWith("redemption:") ? "Riscatto cashback" : "Pagamento"} #
                        {related.split(":")[1]!.slice(0, 8).toUpperCase()}
                      </span>
                      <span className="text-white">→</span>
                    </button>
                  ))}
                  {linked.map((m) => {
                    const target = movementDetailRef(m);
                    const out = movementDirection(m) === "out";
                    return (
                      <button
                        key={m.id}
                        onClick={() => target && open(target)}
                        disabled={!target || target === ref}
                        className="flex w-full cursor-pointer items-center justify-between gap-3 rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-left transition hover:bg-white/10 disabled:cursor-default"
                      >
                        <span className="min-w-0">
                          <span className="block truncate text-sm font-bold text-white">{movementLabel(m)}</span>
                          <span className="block text-[11px] font-bold tabular-nums text-surface-400">{formatDateTimeFull(m.created_at)}</span>
                        </span>
                        <span className={`shrink-0 text-base font-black tabular-nums ${out ? "text-danger-300" : "text-success-300"}`}>
                          {m.currency === "SOSNETCASH" ? (
                            <SosnetCashAmount cents={Math.abs(m.amount_cents)} sign={out ? "-" : "+"} />
                          ) : (
                            `${out ? "-" : "+"}${euro(Math.abs(m.amount_cents))}`
                          )}
                        </span>
                      </button>
                    );
                  })}
                </div>
              </section>
            )}

            {onOpenTab && data.tab && TAB_LABELS[data.tab] && (
              <button
                onClick={() => onOpenTab(data.tab!)}
                className="act act-primary !h-11 w-full justify-center"
              >
                {TAB_LABELS[data.tab]}
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
