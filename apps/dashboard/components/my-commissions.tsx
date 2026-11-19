"use client";

import { Fragment, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Pagination, usePagination } from "@/components/pagination";
import { formatEuroCents as euro } from "@/lib/product-audience";
import {
  CALCULATION_LABELS,
  MOVEMENT_STATUS_LABELS,
  MOVEMENT_TYPE_LABELS,
} from "@/lib/commission-labels";
import { Chip, Figure, Identity, KpiTile, Stack, type ChipTone } from "@/components/ui/data-cells";
import type { CommissionMovementDetailRead, SellerSummaryRead } from "@/lib/types";

const STATUS_TONES: Record<string, ChipTone> = {
  PENDING: "warn",
  ACCRUED: "warn",
  APPROVED: "info",
  PAYABLE: "info",
  SCHEDULED: "info",
  PAID: "ok",
  CANCELLED: "bad",
  REVERSED: "bad",
  RETAINED: "muted",
};

function shortDate(iso: string): string {
  return new Date(iso).toLocaleDateString("it-IT", { day: "2-digit", month: "short", year: "numeric" });
}

/**
 * Where a commission comes from, for its recipient: distance from the seller
 * to you (0 = your own sale, 1 = a direct recruit, ...).
 */
function levelLabel(m: CommissionMovementDetailRead): string {
  if (m.movement_type === "PROMOTER_FEE") return "Dalla tua segnalazione";
  const depth = m.depth_from_producer;
  if (depth === null) return "—";
  if (depth === 0) return "Venduto da te";
  if (depth === 1) return "Da un tuo diretto";
  return `Da ${depth} livelli sotto di te`;
}

async function fetchMyCommissionsDetailed(): Promise<CommissionMovementDetailRead[]> {
  const res = await fetch("/api/proxy/commissions/mine/detailed");
  if (!res.ok) throw new Error("Impossibile caricare le provvigioni");
  return res.json();
}

async function fetchMySummary(): Promise<SellerSummaryRead | null> {
  const res = await fetch("/api/proxy/commissions/mine/summary");
  if (!res.ok) throw new Error("Impossibile caricare il riepilogo");
  return res.json();
}

export function MyCommissions() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["commissions", "mine", "detailed"],
    queryFn: fetchMyCommissionsDetailed,
  });
  const { data: summary } = useQuery({ queryKey: ["commissions", "mine", "summary"], queryFn: fetchMySummary });
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [kind, setKind] = useState("ALL");
  const filtered = (data ?? []).filter((m) => kind === "ALL" || m.movement_type === kind);
  // Before the early returns: hooks run on every render.
  const pagination = usePagination(filtered);

  if (isLoading) {
    return <div className="flex items-center justify-center py-12 text-surface-300 gap-2">Caricamento provvigioni...</div>;
  }
  if (error) {
    return (
      <div className="p-4 rounded-2xl bg-danger-500/10 border border-danger-500/30 text-danger-300 text-sm">
        Errore nel caricamento delle provvigioni.
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {summary && (
        <>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
            {[
              { label: "Provvigioni dirette", hint: "Sulle vendite che hai chiuso tu", value: summary.direct_cents },
              { label: "Provvigioni indirette", hint: "Dalle vendite della tua rete", value: summary.indirect_cents },
              { label: "Fee segnalazioni", hint: "Dalle opportunità che hai portato", value: summary.promoter_fee_cents },
            ].map((k) => (
              <KpiTile key={k.label} label={k.label} value={euro(k.value)} hint={k.hint} />
            ))}
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            {([
              { label: "In attesa di approvazione", value: summary.pending_cents, tone: "warn" },
              { label: "Approvate, in pagamento", value: summary.approved_cents, tone: "info" },
              { label: "Già pagate", value: summary.paid_cents, tone: "ok" },
            ] as const).map((k) => (
              <div key={k.label} data-tilt className="panel flex flex-wrap items-center justify-between gap-x-3 gap-y-2 rounded-3xl px-5 py-4">
                <Chip tone={k.tone} live={k.tone === "warn"}>{k.label}</Chip>
                <span className="text-xl font-black tabular-nums text-white">{euro(k.value)}</span>
              </div>
            ))}
          </div>
          <p className="text-xs text-surface-300">
            Vendite personali attive: <strong className="text-white">{summary.personal_sales}</strong>
            {" "}per <strong className="text-white">{euro(summary.personal_sales_amount_cents)}</strong>
            {summary.reversal_cents !== 0 && <> · storni <strong className="text-danger-400">{euro(summary.reversal_cents)}</strong></>}
          </p>
        </>
      )}

      {(data ?? []).length === 0 ? (
        <div className="flex flex-col items-center gap-3 py-12 text-center">
          <svg className="float-soft h-10 w-10 text-surface-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V6m0 10v2M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <p className="text-sm text-surface-300">Nessuna provvigione maturata al momento.</p>
        </div>
      ) : (
        <>
          <div className="subnav">
            {([["ALL", "Tutte"], ["DIRECT", "Dirette"], ["INDIRECT", "Indirette"], ["PROMOTER_FEE", "Segnalazioni"], ["REVERSAL", "Storni"]] as const).map(([key, label]) => (
              <button
                key={key}
                onClick={() => setKind(key)}
                className="subnav-pill"
                data-active={kind === key || undefined}
              >
                {label}
              </button>
            ))}
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr>
                  <th className="px-4 py-3">Intestatario</th>
                  <th className="px-4 py-3">Origine</th>
                  <th className="px-4 py-3">Situazione</th>
                  <th className="px-4 py-3 text-right">Valore</th>
                  <th className="px-4 py-3"><span className="sr-only">Dettaglio</span></th>
                </tr>
              </thead>
              <tbody>
                {pagination.pageItems.map((m) => (
                  <Fragment key={m.id}>
                    <tr className="cursor-pointer" onClick={() => setExpandedId(expandedId === m.id ? null : m.id)}>
                      <td className="px-4 py-3">
                        <Identity name={m.customer_name} detail={m.product_name} />
                      </td>
                      <td className="px-4 py-3">
                        <Stack title={levelLabel(m)} detail={MOVEMENT_TYPE_LABELS[m.movement_type] ?? m.movement_type} />
                      </td>
                      <td className="px-4 py-3">
                        <Chip tone={STATUS_TONES[m.status] ?? "muted"} live={m.status === "PENDING" || m.status === "ACCRUED"}>
                          {MOVEMENT_STATUS_LABELS[m.status] ?? m.status}
                        </Chip>
                      </td>
                      <td className="px-4 py-3 text-right">
                        <Figure
                          value={<span className={m.amount_cents < 0 ? "text-danger-300" : ""}>{euro(m.amount_cents)}</span>}
                          detail={shortDate(m.effective_date)}
                        />
                      </td>
                      <td className="px-4 py-3 text-right">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" className={`inline h-4 w-4 text-surface-300 transition-transform ${expandedId === m.id ? "rotate-180" : ""}`}>
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                        </svg>
                      </td>
                    </tr>
                    {expandedId === m.id && (
                      <tr>
                        <td colSpan={5} className="px-5 py-5">
                          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
                            <div className="space-y-1.5">
                              <p><span className="text-surface-400">Venduto da:</span> {m.producer_name}</p>
                              <p><span className="text-surface-400">Importo della vendita:</span> {euro(m.value_cents)}</p>
                              <p><span className="text-surface-400">Margine distribuito:</span> {m.reference_margin_cents != null ? euro(m.reference_margin_cents) : "—"}</p>
                              <p><span className="text-surface-400">Il tuo ruolo alla data della vendita:</span> <span className="font-semibold text-white">{m.role_at_calculation ?? "—"}</span></p>
                            </div>
                            <div className="space-y-1.5">
                              <p><span className="text-surface-400">Regola:</span> {m.rule_label ?? "—"} · {CALCULATION_LABELS[m.calculation_type ?? ""] ?? "—"}</p>
                              {m.plan_name && <p><span className="text-surface-400">Piano:</span> {m.plan_name} (versione {m.plan_version})</p>}
                              <p><span className="text-surface-400">Maturata il:</span> {shortDate(m.effective_date)}</p>
                              {m.paid_date && <p><span className="text-surface-400">Pagata il:</span> <span className="text-success-300">{shortDate(m.paid_date)}</span></p>}
                            </div>
                          </div>
                          {m.explanation && (
                            <div className="mt-4 p-4 rounded-2xl bg-gradient-to-br from-brand-500/15 to-accent-500/5 border border-brand-500/25 text-surface-100">
                              <span className="kpi-label block mb-1">Perché questo importo</span>
                              {m.explanation}
                            </div>
                          )}
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
          <Pagination {...pagination} label="provvigioni" />
        </>
      )}
    </div>
  );
}
