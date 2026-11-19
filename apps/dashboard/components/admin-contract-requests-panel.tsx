"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CommissionPreviewView } from "@/components/contract-commission-preview";
import { ContractDocumentsPanel } from "@/components/contract-documents-panel";
import { ContractDossierActions } from "@/components/contract-dossier-actions";
import { FullScreenPanel } from "@/components/full-screen-panel";
import { Pagination, usePagination } from "@/components/pagination";
import { Chip, Figure, IdTag, Identity, KpiTile, RowActions, type ChipTone } from "@/components/ui/data-cells";
import { friendlyApiError } from "@/lib/api-error";
import {
  CONTRACT_STATUS_LABELS,
  ENERGY_POINT_LABELS,
  PAYMENT_PLAN_LABELS,
  formatDate,
  pointCode,
} from "@/lib/contract-status";
import { formatEuroCents as euro, productAllowsCustomerKind } from "@/lib/product-audience";
import type {
  CommissionPreviewRead,
  ProductCatalogRead,
  ContractRead,
  ContractRequestDetailRead,
  ContractRequestPointRead,
  ContractRequestSummaryRead,
} from "@/lib/types";

type Filter = "ALL" | "TO_REVIEW" | "BANK_TRANSFER" | "TO_PAY" | "DOCUMENTS" | "FAILED" | "DRAFT";

const FILTERS: { key: Filter; label: string; match: (r: ContractRequestSummaryRead) => boolean }[] = [
  { key: "TO_REVIEW", label: "Da verificare", match: (r) => r.points_to_review > 0 },
  { key: "BANK_TRANSFER", label: "Bonifici da confermare", match: (r) => r.bank_transfer_pending },
  { key: "DOCUMENTS", label: "Documenti mancanti", match: (r) => r.points_documents_pending > 0 },
  { key: "TO_PAY", label: "Non pagate", match: (r) => r.status === "SUBMITTED" && r.points_payable > 0 },
  { key: "FAILED", label: "Rate non riscosse", match: (r) => r.instalments_failed > 0 },
  { key: "DRAFT", label: "In compilazione", match: (r) => r.status === "DRAFT" },
  { key: "ALL", label: "Tutte", match: (r) => r.status !== "CANCELLED" },
];

const ORIGIN_LABELS: Record<string, string> = {
  CUSTOMER: "Dal cliente",
  PROMOTER: "Dal promoter",
  ADMIN: "Dall'amministrazione",
};

/** Status to chip tone: done is ok, closed is bad, anything in progress beats. */
function statusTone(status: string): { tone: ChipTone; live: boolean } {
  switch (status) {
    case "ACTIVE":
    case "RENEWED":
    case "PAID":
    case "APPROVED":
      return { tone: "ok", live: false };
    case "DRAFT":
    case "EXPIRED":
      return { tone: "muted", live: false };
    case "REJECTED":
    case "CANCELLED":
    case "SUSPENDED":
      return { tone: "bad", live: false };
    default:
      return { tone: "warn", live: true };
  }
}

async function fetchJson<T>(path: string): Promise<T> {
  const res = await fetch(path);
  if (!res.ok) throw new Error(await friendlyApiError(res));
  return res.json();
}

/**
 * "Pratiche": every activation pratica, for the back office.
 * The list surfaces what needs attention (contracts to verify, missing
 * documents, unpaid, failed instalments). The detail shows the holder, shared
 * documents, payment attempts and each point as its own contract. Approval,
 * rejection and the commission preview stay per contract (same review modal as
 * "Tutti i Contratti"), plus a bulk approval where each preview is accepted.
 */
export function AdminContractRequestsPanel({
  openRequestId,
  onOpenRequest,
  onReview,
  onCommissions,
  onHistory,
  onContractsChanged,
}: {
  openRequestId: string | null;
  onOpenRequest: (requestId: string | null) => void;
  onReview: (contract: ContractRead) => void;
  onCommissions: (contractId: string) => void;
  onHistory: (contractId: string) => void;
  /** Tells "Tutti i Contratti" to reload its own copy after approvals here. */
  onContractsChanged: () => void;
}) {
  const { data, error, isLoading } = useQuery({
    queryKey: ["admin", "contract-requests"],
    queryFn: () => fetchJson<ContractRequestSummaryRead[]>("/api/proxy/contract-requests"),
    refetchOnWindowFocus: true,
  });
  const [filter, setFilter] = useState<Filter>("TO_REVIEW");
  const [search, setSearch] = useState("");

  const all = data ?? [];
  const needle = search.trim().toLowerCase();
  const active = FILTERS.find((f) => f.key === filter)!;
  const rows = all.filter(
    (r) =>
      active.match(r) &&
      (!needle ||
        [r.code, r.customer_name, r.holder_name, r.activated_by_promoter_name, r.id]
          .filter(Boolean)
          .some((v) => v!.toLowerCase().includes(needle)))
  );
  const pagination = usePagination(rows);

  return (
    <div className="space-y-6">
      {/* Counters: each tile is also a filter */}
      <div className="stagger grid grid-cols-2 gap-4 lg:grid-cols-5">
        {FILTERS.filter((f) => f.key !== "ALL" && f.key !== "DRAFT").map((f, i) => {
          const count = all.filter(f.match).length;
          return (
            <div key={f.key} className="grid" style={{ "--i": i } as React.CSSProperties}>
              <KpiTile
                label={f.label}
                value={isLoading ? "…" : count}
                hint={count > 0 && f.key !== "TO_PAY" ? "Richiede un intervento" : "Nessuna urgenza"}
                active={filter === f.key}
                onClick={() => setFilter(f.key)}
              />
            </div>
          );
        })}
      </div>

      {/* Search and filter pills */}
      <div className="panel rounded-3xl p-4 sm:p-5 space-y-3">
        <div className="relative">
          <svg className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-surface-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Cerca per pratica, cliente, intestatario o promoter..."
            className="w-full rounded-2xl field py-2.5 pl-11 pr-4 text-sm"
          />
        </div>
        <div className="subnav" role="tablist" aria-label="Filtra pratiche">
          {FILTERS.map((f) => (
            <button
              key={f.key}
              role="tab"
              aria-selected={filter === f.key}
              data-active={filter === f.key}
              onClick={() => setFilter(f.key)}
              className="subnav-pill"
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      <div className="panel rounded-3xl p-4 sm:p-6">
        <div className="mb-2 flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="kpi-label">Richieste in corso</p>
            <h3 className="mt-1 text-xl font-black tracking-tight text-white">{active.label}</h3>
          </div>
          {!isLoading && !error && (
            <span className="text-xs font-semibold text-surface-300">
              {rows.length} {rows.length === 1 ? "pratica" : "pratiche"}
            </span>
          )}
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr>
                <th className="px-4 py-3">Intestatario</th>
                <th className="px-4 py-3">Pratica</th>
                <th className="px-4 py-3">Avanzamento</th>
                <th className="px-4 py-3">Incasso</th>
                <th className="px-4 py-3 text-right">Valore</th>
                <th className="px-4 py-3"><span className="sr-only">Azioni</span></th>
              </tr>
            </thead>
            <tbody>
              {isLoading && (
                <tr>
                  <td colSpan={6} className="px-4 py-10 text-center text-surface-300">
                    <span className="inline-flex items-center gap-2">
                      <span className="h-2 w-2 animate-pulse rounded-full bg-white" /> Caricamento...
                    </span>
                  </td>
                </tr>
              )}
              {error && (
                <tr>
                  <td colSpan={6} className="px-4 py-10 text-center text-danger-300">{(error as Error).message}</td>
                </tr>
              )}
              {pagination.pageItems.map((r) => {
                const issues = [
                  r.points_to_review > 0 && `${r.points_to_review} da verificare`,
                  r.points_documents_pending > 0 && `${r.points_documents_pending} senza documenti`,
                  r.points_without_package > 0 && `${r.points_without_package} senza pacchetto`,
                ].filter(Boolean).join(" · ");
                const plans = r.payment_plans.map((p) => PAYMENT_PLAN_LABELS[p] ?? p).join(", ");
                return (
                  <tr key={r.id} className="cursor-pointer text-surface-300" onClick={() => onOpenRequest(r.id)}>
                    <td className="px-4 py-3">
                      <Identity
                        name={r.customer_name ?? "—"}
                        detail={
                          <>
                            {ORIGIN_LABELS[r.created_by_role ?? ""] ?? "—"}
                            {r.activated_by_promoter_name ? ` · ${r.activated_by_promoter_name}` : ""}
                          </>
                        }
                      />
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-1.5">
                        <span className="tag-id" title={r.id}>#{r.code}</span>
                        {r.status === "DRAFT" && <Chip tone="muted">Bozza</Chip>}
                      </div>
                      <div className="mt-1 text-[11px] text-surface-400">{formatDate(r.submitted_at ?? r.created_at)}</div>
                    </td>
                    <td className="px-4 py-3">
                      <div className="w-40">
                        <div className="flex items-baseline justify-between gap-2">
                          <span className="text-[13px] font-bold text-white tabular-nums">
                            {r.points_active}/{r.points_total}
                          </span>
                          <span className="text-[10.5px] text-surface-400">attivi</span>
                        </div>
                        <div className="meter mt-1.5">
                          <i style={{ width: `${r.points_total > 0 ? Math.max(3, (r.points_active / r.points_total) * 100) : 3}%` }} />
                        </div>
                        <div className={`mt-1 truncate text-[10.5px] ${issues ? "text-warn-300" : "text-surface-400"}`} title={issues || undefined}>
                          {issues || "—"}
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex flex-col items-start gap-1">
                        {r.bank_transfer_pending ? (
                          <Chip tone="warn" live>
                            Bonifico da confermare{r.bank_transfer_total_cents ? ` · ${euro(r.bank_transfer_total_cents)}` : ""}
                          </Chip>
                        ) : r.points_paid > 0 ? (
                          <Chip tone={r.points_paid >= r.points_total ? "ok" : "info"}>
                            Pagati {r.points_paid}/{r.points_total}
                          </Chip>
                        ) : r.status === "DRAFT" ? (
                          <span className="text-surface-500">—</span>
                        ) : (
                          <Chip tone="warn">Non pagata</Chip>
                        )}
                        {(plans || r.instalments_failed > 0) && (
                          <span className="text-[10.5px] text-surface-400">
                            {plans}
                            {r.instalments_failed > 0 && (
                              <span className="text-danger-300">
                                {plans ? " · " : ""}
                                {r.instalments_failed} rate non riscosse
                              </span>
                            )}
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex justify-end">
                        {r.total_gross_cents > 0 ? (
                          <Figure value={euro(r.total_gross_cents)} detail={`${r.points_total} ${r.points_total === 1 ? "punto" : "punti"}`} />
                        ) : (
                          <span className="text-surface-500">—</span>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <RowActions>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            onOpenRequest(r.id);
                          }}
                          className="act act-primary"
                        >
                          Apri
                        </button>
                      </RowActions>
                    </td>
                  </tr>
                );
              })}
              {!isLoading && !error && rows.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-4 py-12">
                    <div className="flex flex-col items-center gap-3 text-center">
                      <span className="grid h-12 w-12 place-items-center rounded-2xl bg-white/10 text-white">
                        <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                        </svg>
                      </span>
                      <p className="text-sm text-surface-300">Nessuna pratica in “{active.label}”.</p>
                    </div>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        <div className="pt-3">
          <Pagination {...pagination} label="pratiche" />
        </div>
      </div>

      {openRequestId && (
        <RequestDetail
          requestId={openRequestId}
          onClose={() => onOpenRequest(null)}
          onReview={onReview}
          onCommissions={onCommissions}
          onHistory={onHistory}
          onContractsChanged={onContractsChanged}
        />
      )}
    </div>
  );
}

function RequestDetail({
  requestId,
  onClose,
  onReview,
  onCommissions,
  onHistory,
  onContractsChanged,
}: {
  requestId: string;
  onClose: () => void;
  onReview: (contract: ContractRead) => void;
  onCommissions: (contractId: string) => void;
  onHistory: (contractId: string) => void;
  onContractsChanged: () => void;
}) {
  const queryClient = useQueryClient();
  const { data: request, error } = useQuery({
    queryKey: ["contract-request", requestId],
    queryFn: () => fetchJson<ContractRequestDetailRead>(`/api/proxy/contract-requests/${requestId}`),
    refetchOnWindowFocus: true,
  });
  const [openPoint, setOpenPoint] = useState<string | null>(null);
  const [bulkOpen, setBulkOpen] = useState(false);
  const [stopping, setStopping] = useState<string | null>(null);
  const [repackaging, setRepackaging] = useState<ContractRequestPointRead | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  async function refresh() {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["contract-request", requestId] }),
      queryClient.invalidateQueries({ queryKey: ["admin", "contract-requests"] }),
    ]);
  }

  async function stopBilling(point: ContractRequestPointRead) {
    if (
      !window.confirm(
        `Interrompere gli addebiti mensili di ${pointCode(point)}? Gli altri contratti della pratica continuano a essere addebitati. Eventuali rimborsi si fanno dal pannello Stripe.`
      )
    ) {
      return;
    }
    setStopping(point.id);
    setActionError(null);
    try {
      const res = await fetch(`/api/proxy/contracts/${point.id}/stop-billing`, { method: "POST" });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      await refresh();
    } catch (err: any) {
      setActionError(err.message || "Impossibile interrompere gli addebiti.");
    } finally {
      setStopping(null);
    }
  }

  const toReview = (request?.points ?? []).filter((p) => p.status === "UNDER_REVIEW");

  return (
    <FullScreenPanel
      eyebrow="Pratica di attivazione"
      title={request ? `#${request.code} · ${request.customer_name ?? "Cliente"}` : "Pratica"}
      onClose={onClose}
      subtitle={
        request && (
          <p className="text-[11px] text-surface-400">
            {ORIGIN_LABELS[request.created_by_role ?? ""] ?? "—"}
            {request.activated_by_promoter_name ? ` (${request.activated_by_promoter_name})` : ""} ·{" "}
            {request.status === "DRAFT" ? "in compilazione" : `inviata il ${formatDate(request.submitted_at)}`} ·{" "}
            {request.points_total} punti · {request.points_active} attivi · totale{" "}
            <strong className="text-white">{euro(request.total_gross_cents)}</strong>
          </p>
        )
      }
    >
      {error && <p className="text-sm text-danger-400">{(error as Error).message}</p>}
      {!request ? (
        <div className="h-40 rounded-2xl bg-white/5 animate-pulse" />
      ) : (
        <div className="space-y-6">
          {actionError && (
            <div className="p-3 rounded-xl bg-danger-500/10 border border-danger-500/20 text-danger-400 text-xs">{actionError}</div>
          )}

          <section className="panel grid grid-cols-2 sm:grid-cols-4 gap-4 p-5 rounded-3xl text-xs">
            <Fact label="Intestatario" value={request.holder_name ?? "—"} />
            <Fact label="Email" value={request.email ?? "—"} />
            <Fact label="PEC" value={request.pec ?? "—"} />
            <Fact label="IBAN" value={request.iban ?? "—"} mono />
          </section>

          <section className="space-y-3">
            <div className="flex items-center justify-between gap-3 flex-wrap">
              <h3 className="text-xl font-black tracking-tight text-white">Contratti della pratica</h3>
              {toReview.length > 0 && (
                <button
                  onClick={() => setBulkOpen(true)}
                  className="act act-primary"
                >
                  Approva {toReview.length === 1 ? "il contratto in revisione" : `i ${toReview.length} contratti in revisione`}
                </button>
              )}
            </div>
            <div className="space-y-2">
              {request.points.map((point) => (
                <div key={point.id} className="rounded-3xl bg-white/[0.045] ring-1 ring-white/10 transition hover:bg-white/[0.07] hover:ring-white/25">
                  <div className="p-4 grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)_minmax(0,1fr)_auto] items-start gap-x-5 gap-y-3">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <span className="kpi-label">{ENERGY_POINT_LABELS[point.energy_type ?? ""] ?? "Fornitura"}</span>
                        <span title={`Contratto ${point.id}`}>
                          <IdTag id={point.id} />
                        </span>
                      </div>
                      <p className="mt-1 text-[15px] font-black text-white font-mono break-all">{pointCode(point)}</p>
                      <p className="text-[11px] text-surface-400 break-words">
                        {[point.street, point.postal_code, point.city, point.province].filter(Boolean).join(", ")}
                        {point.meter_number ? ` · contatore ${point.meter_number}` : ""}
                      </p>
                    </div>
                    <div className="min-w-0">
                      <p className={`text-[13px] font-bold break-words ${point.product_name ? "text-white" : "text-warn-300"}`}>
                        {point.product_name ?? "Senza pacchetto"}
                      </p>
                      <p className="text-[12px] font-black text-white tabular-nums">
                        {point.gross_amount_cents != null ? euro(point.gross_amount_cents) : "—"}
                        {point.vat_amount_cents ? (
                          <span className="ml-1 text-[10.5px] font-semibold text-surface-400">(IVA {point.vat_rate}%)</span>
                        ) : null}
                      </p>
                    </div>
                    <div className="min-w-0 space-y-1.5">
                      <button onClick={() => onHistory(point.id)} title="Storico stati" className="cursor-pointer transition hover:brightness-125">
                        <Chip tone={statusTone(point.status).tone} live={statusTone(point.status).live}>
                          {CONTRACT_STATUS_LABELS[point.status] ?? point.status}
                        </Chip>
                      </button>
                      <p className="text-[10.5px] text-surface-400">
                        {point.paid_at ? (
                          <span className="text-success-300">
                            Pagato{point.payment_plan ? ` · ${PAYMENT_PLAN_LABELS[point.payment_plan] ?? point.payment_plan}` : ""}
                          </span>
                        ) : (
                          "Non pagato"
                        )}
                        {point.instalments_total && point.instalments_total > 1
                          ? ` · rate ${point.instalments_paid}/${point.instalments_total}`
                          : ""}
                        {point.instalments_failed > 0 && <span className="text-danger-300"> · {point.instalments_failed} non riscosse</span>}
                        {point.billing_stopped_at && <span className="text-danger-300"> · addebiti interrotti</span>}
                      </p>
                      <p className={`text-[10.5px] ${point.documents_missing > 0 || point.documents_rejected > 0 ? "text-warn-300" : "text-surface-400"}`}>
                        {point.documents_missing > 0
                          ? `${point.documents_missing} documenti mancanti`
                          : point.documents_rejected > 0
                            ? `${point.documents_rejected} documenti respinti`
                            : "Documenti completi"}
                      </p>
                    </div>
                    <div className="min-w-0 flex flex-wrap items-center gap-1.5 sm:col-span-2 xl:col-span-1 xl:justify-end">
                      <button onClick={() => setOpenPoint(openPoint === point.id ? null : point.id)} className="act">
                        {openPoint === point.id ? "Chiudi" : "Documenti"}
                      </button>
                      {canRepackage(point) && (
                        <button
                          onClick={() => setRepackaging(point)}
                          className={`act ${point.product_version_id ? "" : "ring-1 ring-warn-400/60"}`}
                          style={point.product_version_id ? undefined : { color: "#fcd34d" }}
                        >
                          {point.product_version_id ? "Cambia pacchetto" : "Scegli pacchetto"}
                        </button>
                      )}
                      {point.product_version_id && (
                        <button onClick={() => onCommissions(point.id)} className="act">
                          Provvigioni
                        </button>
                      )}
                      {point.status !== "DRAFT" && (
                        <button onClick={() => onReview(point)} className="act act-primary">
                          Recensisci
                        </button>
                      )}
                      {point.billing_active && (
                        <button
                          onClick={() => stopBilling(point)}
                          disabled={stopping === point.id}
                          className="act"
                          style={{ color: "#b4d3ff" }}
                        >
                          {stopping === point.id ? "..." : "Interrompi addebiti"}
                        </button>
                      )}
                    </div>
                  </div>
                  {openPoint === point.id && (
                    <div className="border-t border-white/10 p-4 space-y-4">
                      <ContractDocumentsPanel contractId={point.id} isStaff />
                      <ContractDossierActions contractId={point.id} />
                    </div>
                  )}
                </div>
              ))}
            </div>
          </section>

          <section className="space-y-3">
            <h3 className="text-xl font-black tracking-tight text-white">Documenti dell&apos;intestatario</h3>
            <p className="text-xs text-surface-400">
              Caricati una volta sulla pratica: valgono per ogni contratto qui sopra, e compaiono anche nel fascicolo di
              ciascuno.
            </p>
            <ContractDocumentsPanel requestId={request.id} isStaff />
          </section>

          {request.bank_transfer_pending && (
            <BankTransferConfirm request={request} onDone={async () => { await refresh(); onContractsChanged(); }} />
          )}

          <section className="space-y-3">
            <h3 className="text-xl font-black tracking-tight text-white">Tentativi di pagamento</h3>
            {request.checkouts.length === 0 ? (
              <p className="text-xs text-surface-500">
                Nessun pagamento con carta avviato per questa pratica
                {request.points_paid > 0 ? " (i contratti pagati lo sono stati singolarmente o con bonifico confermato)." : "."}
              </p>
            ) : (
              <div className="space-y-2 text-xs">
                {request.checkouts.map((c) => (
                  <div key={c.id} className="px-4 py-3 flex flex-wrap items-center justify-between gap-2 rounded-2xl bg-white/[0.045] ring-1 ring-white/10">
                    <div>
                      <p className="font-semibold text-white">
                        {PAYMENT_PLAN_LABELS[c.payment_plan] ?? c.payment_plan} · {c.contracts} contratti ·{" "}
                        {c.payment_plan === "FULL" ? euro(c.total_cents) : `${euro(c.instalment_cents)}/mese (${euro(c.total_cents)})`}
                      </p>
                      <p className="text-[10px] text-surface-500 font-mono">
                        {c.stripe_checkout_session_id}
                        {c.stripe_subscription_id ? ` · ${c.stripe_subscription_id}` : ""}
                      </p>
                    </div>
                    <div className="text-right">
                      <p className={c.completed_at ? "text-success-400 font-semibold" : "text-surface-500"}>
                        {c.completed_at ? `Completato il ${formatDate(c.completed_at)}` : `Aperto il ${formatDate(c.created_at)}, non completato`}
                      </p>
                      {c.outcome && <p className="text-[10px] text-surface-500">{c.outcome}</p>}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>
        </div>
      )}

      {repackaging && (
        <PackagePicker
          point={repackaging}
          customerKind={request?.customer_kind ?? null}
          onClose={() => setRepackaging(null)}
          onChosen={async (versionId) => {
            const res = await fetch(`/api/proxy/contract-requests/${requestId}/points/${repackaging.id}/product`, {
              method: "PUT",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ product_version_id: versionId }),
            });
            if (!res.ok) throw new Error(await friendlyApiError(res));
            setRepackaging(null);
            await refresh();
            onContractsChanged();
          }}
        />
      )}

      {bulkOpen && request && (
        <BulkApproveModal
          points={toReview}
          onClose={() => setBulkOpen(false)}
          onDone={async () => {
            await refresh();
            onContractsChanged();
          }}
        />
      )}
    </FullScreenPanel>
  );
}

/**
 * Whether the administrator may still change a POD's package: not while that
 * contract is paid, being charged or active (same rule server-side, requests.py).
 */
const REPACKAGEABLE_STATUSES = ["DRAFT", "SUBMITTED", "DOCUMENTS_PENDING", "UNDER_REVIEW", "APPROVED", "PAYMENT_PENDING"];

function canRepackage(point: ContractRequestPointRead): boolean {
  return !point.paid_at && !point.billing_active && REPACKAGEABLE_STATUSES.includes(point.status);
}

/**
 * Choose or correct a POD's package: the same packages the customer would
 * see, filtered by their customer type.
 */
function PackagePicker({
  point,
  customerKind,
  onClose,
  onChosen,
}: {
  point: ContractRequestPointRead;
  customerKind: string | null;
  onClose: () => void;
  onChosen: (versionId: string) => Promise<void>;
}) {
  const [saving, setSaving] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { data: products } = useQuery({
    queryKey: ["admin", "products", "catalog"],
    queryFn: () => fetchJson<ProductCatalogRead[]>("/api/proxy/products"),
  });
  const packages = (products ?? []).filter(
    (p) =>
      p.category === "INTERNAL" &&
      p.status === "ACTIVE" &&
      p.current_version?.status === "ACTIVE" &&
      productAllowsCustomerKind(p.customer_type, customerKind)
  );

  async function choose(versionId: string) {
    setSaving(versionId);
    setError(null);
    try {
      await onChosen(versionId);
    } catch (err: any) {
      setError(err.message || "Impossibile cambiare il pacchetto.");
    } finally {
      setSaving(null);
    }
  }

  return (
    <FullScreenPanel title={`Pacchetto di ${pointCode(point)}`} onClose={onClose}>
      <div className="space-y-3">
        <p className="text-xs text-surface-400">
          {point.product_name
            ? `Ora è attivo “${point.product_name}”. Scegliendone un altro il prezzo del contratto viene ricalcolato subito.`
            : "Questo contratto non ha ancora un'offerta: sceglila qui per poter proseguire con la pratica."}
        </p>
        {error && <p className="text-xs text-danger-400">{error}</p>}
        {packages.length === 0 && <p className="text-xs text-surface-500">Nessun pacchetto disponibile per questo cliente.</p>}
        {packages.map((product) => {
          const version = product.current_version!;
          const current = version.id === point.product_version_id;
          return (
            <button
              key={version.id}
              disabled={current || saving !== null}
              onClick={() => choose(version.id)}
              className={`w-full text-left p-3.5 rounded-2xl border transition cursor-pointer disabled:cursor-default ${
                current
                  ? "border-success-500/40 bg-success-500/5"
                  : "border-white/10 bg-surface-950/40 hover:border-brand-500/40"
              }`}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-sm font-bold text-white break-words">{version.name}</p>
                  <p className="text-[11px] text-surface-400 break-words">
                    {ENERGY_POINT_LABELS[product.energy_type ?? ""] ?? "Fornitura"} · {product.code}
                  </p>
                </div>
                <p className="text-xs font-semibold text-surface-200 tabular-nums whitespace-nowrap">
                  {euro(version.contract_net_amount_cents || version.base_price_cents)}
                  {current ? " · attuale" : saving === version.id ? " · ..." : ""}
                </p>
              </div>
            </button>
          );
        })}
      </div>
    </FullScreenPanel>
  );
}

function Fact({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="min-w-0">
      <p className="kpi-label">{label}</p>
      <p className={`mt-1 text-[13px] text-white font-bold break-words ${mono ? "font-mono" : ""}`}>{value}</p>
    </div>
  );
}

type BulkResult = { contractId: string; ok: boolean; message: string };

/**
 * Bulk approval of every contract awaiting review, keeping the safeguards:
 * each preview is loaded and shown, the administrator accepts all at once, and
 * each transition is sent separately with its own checksum, so a changed
 * preview is refused for that contract alone.
 */
function BulkApproveModal({
  points,
  onClose,
  onDone,
}: {
  points: ContractRequestPointRead[];
  onClose: () => void;
  onDone: () => void;
}) {
  const [reason, setReason] = useState("Documenti verificati");
  const [checked, setChecked] = useState(false);
  const [running, setRunning] = useState(false);
  const [results, setResults] = useState<BulkResult[] | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);

  const { data: previews, error } = useQuery({
    queryKey: ["admin", "bulk-previews", points.map((p) => p.id).join(",")],
    queryFn: async () => {
      const out: Record<string, CommissionPreviewRead> = {};
      for (const point of points) {
        out[point.id] = await fetchJson<CommissionPreviewRead>(`/api/proxy/contracts/${point.id}/commission-preview`);
      }
      return out;
    },
    staleTime: 0,
    gcTime: 0,
  });

  async function approveAll() {
    if (!previews) return;
    setRunning(true);
    const out: BulkResult[] = [];
    for (const point of points) {
      const preview = previews[point.id];
      if (!preview) continue;
      try {
        const res = await fetch(`/api/proxy/contracts/${point.id}/transition`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            to_status: "APPROVED",
            reason,
            notes: null,
            accept_commission_preview_checksum: preview.already_accepted ? null : preview.checksum,
          }),
        });
        if (!res.ok) throw new Error(await friendlyApiError(res));
        const updated = (await res.json()) as ContractRead;
        out.push({
          contractId: point.id,
          ok: true,
          message: `${pointCode(point)}: ${CONTRACT_STATUS_LABELS[updated.status] ?? updated.status}`,
        });
      } catch (err: any) {
        out.push({ contractId: point.id, ok: false, message: `${pointCode(point)}: ${err.message}` });
      }
    }
    setResults(out);
    setRunning(false);
    onDone();
  }

  const total = previews ? Object.values(previews).reduce((sum, p) => sum + p.total_commission_cents, 0) : 0;

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm">
      <div className="w-full max-w-3xl max-h-[88vh] overflow-y-auto panel rounded-3xl p-6 border-white/10 bg-surface-950 space-y-4 pop">
        <div className="flex items-center justify-between">
          <h3 className="text-xl font-black tracking-tight text-white">
            Approva {points.length} {points.length === 1 ? "contratto" : "contratti"}
          </h3>
          <button onClick={onClose} className="p-1 rounded-lg hover:bg-white/5 text-surface-400 cursor-pointer">✕</button>
        </div>

        {results ? (
          <>
            <div className="space-y-1.5">
              {results.map((r) => (
                <p key={r.contractId} className={`text-xs ${r.ok ? "text-success-400" : "text-danger-400"}`}>
                  {r.ok ? "✓" : "✕"} {r.message}
                </p>
              ))}
            </div>
            <button onClick={onClose} className="w-full rounded-xl bg-white/10 hover:bg-white/20 py-2.5 text-sm font-semibold text-white cursor-pointer">
              Chiudi
            </button>
          </>
        ) : (
          <>
            <p className="text-xs text-surface-400">
              Approvare un contratto fa partire le sue provvigioni (subito se già pagato, a ogni rata se a rate). Controlla le
              anteprime: ognuna viene accettata e salvata nel registro del suo contratto.
            </p>
            {error && <p className="text-xs text-danger-400">{(error as Error).message}</p>}
            {!previews ? (
              <div className="h-32 rounded-xl bg-white/5 animate-pulse" />
            ) : (
              <div className="space-y-2">
                {points.map((point) => {
                  const preview = previews[point.id];
                  if (!preview) return null;
                  return (
                    <div key={point.id} className="rounded-xl border border-white/10">
                      <button
                        onClick={() => setExpanded(expanded === point.id ? null : point.id)}
                        className="w-full flex items-center justify-between gap-3 px-4 py-3 text-left cursor-pointer"
                      >
                        <span className="min-w-0">
                          <span className="block text-sm font-semibold text-white font-mono">{pointCode(point)}</span>
                          <span className="block text-[11px] text-surface-400">
                            {point.product_name} · {preview.beneficiaries.filter((b) => b.total_cents > 0).length} beneficiari
                            {preview.warnings.length > 0 && <span className="text-warn-400"> · {preview.warnings.length} avvisi</span>}
                            {preview.already_accepted && " · anteprima già accettata"}
                          </span>
                        </span>
                        <span className="text-sm font-black text-white tabular-nums shrink-0">
                          {euro(preview.total_commission_cents)} {expanded === point.id ? "▾" : "▸"}
                        </span>
                      </button>
                      {expanded === point.id && (
                        <div className="border-t border-white/5 p-4">
                          <CommissionPreviewView preview={preview} />
                        </div>
                      )}
                    </div>
                  );
                })}
                <p className="text-xs text-surface-300 text-right">
                  Provvigioni totali: <strong className="text-white">{euro(total)}</strong>
                </p>
              </div>
            )}
            <div className="space-y-1">
              <label className="text-xs font-semibold text-surface-300 block">Motivazione</label>
              <input
                required
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                className="w-full rounded-xl field px-3 py-2 text-sm focus:border-brand-500"
              />
            </div>
            <label className="flex items-start gap-2 cursor-pointer">
              <input type="checkbox" checked={checked} onChange={(e) => setChecked(e.target.checked)} className="mt-0.5 accent-brand-500" />
              <span className="text-xs text-surface-300">
                Ho verificato i documenti e controllato le anteprime: accetto che le provvigioni di ogni contratto partano
                come indicato.
              </span>
            </label>
            <div className="flex justify-end gap-2">
              <button onClick={onClose} className="px-4 py-2 rounded-xl bg-white/5 hover:bg-white/10 text-xs font-semibold text-surface-300 cursor-pointer">
                Annulla
              </button>
              <button
                onClick={approveAll}
                disabled={!previews || !checked || !reason.trim() || running}
                className="act act-primary"
              >
                {running ? "Approvazione in corso..." : `Accetta e approva ${points.length}`}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}


/**
 * Pratica paid by bank transfer: the contracts are marked paid (at the
 * discounted amount frozen at selection) only once an administrator confirms
 * receipt.
 */
function BankTransferConfirm({ request, onDone }: { request: ContractRequestDetailRead; onDone: () => Promise<void> }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const toPay = request.points.filter((p) => p.payment_method === "BANK_TRANSFER" && !p.paid_at);

  async function openProof() {
    setError(null);
    try {
      const res = await fetch(`/api/proxy/contract-requests/${request.id}/bank-transfer/proof-url`);
      if (!res.ok) throw new Error(await friendlyApiError(res));
      const { url } = await res.json();
      window.open(url, "_blank", "noopener,noreferrer");
    } catch (err: any) {
      setError(err.message);
    }
  }

  async function confirm() {
    if (!window.confirm(`Confermi di aver ricevuto il bonifico di ${euro(request.bank_transfer_total_cents ?? 0)} per la pratica #${request.code}? I ${toPay.length} contratti risulteranno pagati.`)) return;
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/proxy/contract-requests/${request.id}/bank-transfer/confirm`, { method: "POST" });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      await onDone();
    } catch (err: any) {
      setError(err.message || "Impossibile confermare il bonifico.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel rounded-3xl p-6 space-y-3 ring-1 ring-warn-400/40">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <Chip tone="warn" live>Bonifico da confermare</Chip>
          <p className="kpi-value mt-3">{euro(request.bank_transfer_total_cents ?? 0)}</p>
          <p className="text-xs text-surface-400">
            {toPay.length} {toPay.length === 1 ? "contratto" : "contratti"} · scelto il {formatDate(request.bank_transfer_requested_at)} ·
            causale “Pratica {request.code}”
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {request.payment_proof_uploaded_at ? (
            <button onClick={openProof} className="act">
              Vedi ricevuta ({formatDate(request.payment_proof_uploaded_at)})
            </button>
          ) : (
            <span className="px-3 py-2 text-xs text-surface-500">Nessuna ricevuta caricata</span>
          )}
          <button onClick={confirm} disabled={busy} className="act act-primary">
            {busy ? "Conferma..." : "Conferma bonifico ricevuto"}
          </button>
        </div>
      </div>
      <div className="text-[11px] text-surface-400 space-y-0.5">
        {toPay.map((p) => (
          <p key={p.id}>
            {pointCode(p)} · {p.product_name ?? "—"} · {euro((p.gross_amount_cents ?? 0) - (p.payment_discount_cents ?? 0))}
            {p.payment_discount_cents ? <span className="text-success-400"> (listino {euro(p.gross_amount_cents ?? 0)}, sconto pagamento unico)</span> : null}
          </p>
        ))}
      </div>
      {error && <p className="text-xs text-danger-400">{error}</p>}
    </section>
  );
}

