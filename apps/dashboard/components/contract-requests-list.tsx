"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ContractDocumentsPanel } from "@/components/contract-documents-panel";
import { friendlyApiError } from "@/lib/api-error";
import {
  CONTRACT_STATUS_LABELS,
  ENERGY_POINT_LABELS,
  PAYMENT_PLAN_LABELS,
  formatDate,
  pointCode,
} from "@/lib/contract-status";
import { formatEuroCents as euro } from "@/lib/product-audience";
import { Chip, Figure, Identity, type ChipTone } from "@/components/ui/data-cells";
import type { ContractRequestDetailRead, ContractRequestPointRead, ContractRequestSummaryRead } from "@/lib/types";

export type WizardTarget = {
  requestId: string;
  step?: "documents" | "packages" | "summary";
  /** The pratica's customer, when the list spans several (the promoter's "Attivazioni"). */
  customer?: { id: string; kind: string | null; email: string | null; firstName?: string | null; lastName?: string | null };
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

/** One-sentence summary of what the pratica is waiting for. */
function nextStepFor(r: ContractRequestSummaryRead, canPay: boolean): { text: string; tone: "action" | "wait" | "done" } {
  if (r.status === "DRAFT") {
    return {
      text: r.points_total === 0
        ? "Bozza: completa i dati."
        : r.points_without_package > 0
          ? `Bozza: scegli l'offerta per ${r.points_without_package} ${r.points_without_package === 1 ? "contratto" : "contratti"} e invia.`
          : "Bozza: pronta da inviare.",
      tone: "action",
    };
  }
  if (r.instalments_failed > 0) return { text: "Una rata non è stata addebitata: controlla la carta.", tone: "action" };
  if (r.bank_transfer_pending) {
    return {
      text: canPay
        ? `Bonifico scelto${r.bank_transfer_total_cents ? ` (${euro(r.bank_transfer_total_cents)})` : ""}: in attesa di conferma dall'amministrazione.`
        : "Bonifico in attesa di conferma dall'amministrazione.",
      tone: "wait",
    };
  }
  if (r.points_payable > 0) {
    return {
      text: canPay
        ? `Da pagare: ${r.points_payable} ${r.points_payable === 1 ? "contratto" : "contratti"}.`
        : `In attesa del pagamento del cliente (${r.points_payable} ${r.points_payable === 1 ? "contratto" : "contratti"}).`,
      tone: "action",
    };
  }
  if (r.points_documents_pending > 0) {
    return {
      text: `Mancano documenti per ${r.points_documents_pending} ${r.points_documents_pending === 1 ? "contratto" : "contratti"}.`,
      tone: "action",
    };
  }
  if (r.points_active === r.points_total && r.points_total > 0) return { text: "Tutti i contratti sono attivi.", tone: "done" };
  if (r.points_to_review > 0) return { text: "Documenti in verifica dall'amministrazione.", tone: "wait" };
  return { text: "In lavorazione.", tone: "wait" };
}

/**
 * "I miei Contratti" as a list of pratiche; each opens on its supply points,
 * each point its own contract with status, package and documents.
 * `mode="customer"`: the logged-in customer's own. `mode="promoter"`: one of
 * the promoter's customers (`customerId`), everything except payment.
 */
export function ContractRequestsList({
  mode,
  customerId,
  onOpenWizard,
}: {
  /** "admin": pratiche opened by the administration, or one customer's; no payment. */
  mode: "customer" | "promoter" | "admin";
  /** Omitted in promoter mode: every pratica of every customer. */
  customerId?: string;
  onOpenWizard: (target: WizardTarget) => void;
}) {
  const allCustomers = mode !== "customer" && !customerId;
  const path =
    mode === "customer"
      ? "/api/proxy/contract-requests/mine"
      : mode === "admin"
        ? customerId
          ? `/api/proxy/contract-requests?customer_id=${customerId}`
          : "/api/proxy/contract-requests?created_by_role=ADMIN&limit=100"
        : allCustomers
          ? "/api/proxy/contract-requests/for-my-customers"
          : `/api/proxy/contract-requests/for-customer/${customerId}`;
  const { data, error, isLoading } = useQuery({
    queryKey: ["contract-requests", mode, customerId ?? (allCustomers ? "all" : "mine")],
    queryFn: () => fetchJson<ContractRequestSummaryRead[]>(path),
    refetchOnWindowFocus: true,
  });
  const [expanded, setExpanded] = useState<string | null>(null);
  const [summaryOf, setSummaryOf] = useState<string | null>(null);

  if (isLoading) return <div className="h-28 rounded-3xl bg-white/5 animate-pulse" />;
  if (error) return <p className="text-sm text-danger-300">{(error as Error).message}</p>;
  if (!data || data.length === 0) {
    return (
      <div className="panel rounded-3xl p-10 flex flex-col items-center gap-3 text-center">
        <span className="grid h-12 w-12 place-items-center rounded-2xl bg-white/10 text-white float-soft">
          <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
        </span>
        <p className="text-base font-black text-white">Nessuna pratica</p>
        <p className="text-xs text-surface-300 max-w-sm">
          {mode === "customer"
            ? "Attiva il tuo primo contratto: puoi inserire uno o più punti di fornitura insieme."
            : mode === "admin" && allCustomers
              ? "L'amministrazione non ha ancora aperto nessuna pratica."
              : allCustomers
              ? "Nessuna pratica per i tuoi clienti: aprine una con “Attiva contratti”."
              : "Questo cliente non ha ancora nessuna pratica di attivazione."}
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {data.map((r) => {
        const next = nextStepFor(r, mode === "customer");
        const isOpen = expanded === r.id;
        const title = allCustomers && r.customer_name ? r.customer_name : `Pratica #${r.code}`;
        return (
          <div
            key={r.id}
            className={`panel rounded-3xl overflow-hidden transition ${isOpen ? "ring-1 ring-white/40" : ""}`}
          >
            <div className="p-4 sm:p-5 grid grid-cols-1 items-center gap-4 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)_auto]">
              {/* Identity and origin */}
              <button onClick={() => setExpanded(isOpen ? null : r.id)} className="text-left min-w-0 cursor-pointer">
                <Identity
                  name={title}
                  detail={
                    <>
                      {formatDate(r.submitted_at ?? r.created_at)} · {r.points_total} {r.points_total === 1 ? "contratto" : "contratti"}
                      {r.payment_plans.length > 0 && ` · ${r.payment_plans.map((p) => PAYMENT_PLAN_LABELS[p] ?? p).join(", ")}`}
                    </>
                  }
                >
                  <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                    {allCustomers && <span className="tag-id" title={r.id}>#{r.code}</span>}
                    {r.status === "DRAFT" && <Chip tone="muted">Bozza</Chip>}
                    {r.created_by_role === "ADMIN" && mode !== "customer" && (
                      <Chip tone="accent">Aperta dall&apos;amministrazione</Chip>
                    )}
                    {r.activated_by_promoter_name && (
                      <Chip tone="info">
                        {mode === "customer"
                          ? r.created_by_role === "ADMIN"
                            ? "Preparata da SOSNET"
                            : `Preparata dal tuo promoter ${r.activated_by_promoter_name}`
                          : r.created_by_role === "ADMIN"
                            ? `Promoter: ${r.activated_by_promoter_name}`
                            : `Compilata da ${r.activated_by_promoter_name}`}
                      </Chip>
                    )}
                  </div>
                  {r.holder_name && <p className="mt-1 text-[11px] text-surface-400">Intestatario: {r.holder_name}</p>}
                </Identity>
              </button>

              {/* Next step and progress */}
              <div className="min-w-0 space-y-2">
                <Chip tone={next.tone === "action" ? "warn" : next.tone === "done" ? "ok" : "info"} live={next.tone === "action"}>
                  <span className="whitespace-normal">{next.text}</span>
                </Chip>
                {r.status !== "DRAFT" && r.points_total > 0 && (
                  <div className="flex items-center gap-2">
                    <div className="meter flex-1 max-w-48">
                      <i style={{ width: `${Math.max(3, (r.points_active / r.points_total) * 100)}%` }} />
                    </div>
                    <span className="text-[10.5px] text-surface-300 tabular-nums">
                      {r.points_active}/{r.points_total} attivi
                    </span>
                  </div>
                )}
              </div>

              {/* Value and actions */}
              <div className="flex items-center justify-between gap-3 lg:justify-end">
                {r.total_gross_cents > 0 && (
                  <Figure
                    value={euro(r.total_gross_cents)}
                    detail={
                      r.points_paid > 0 && r.total_paid_cents > 0 && r.total_paid_cents !== r.total_gross_cents ? (
                        <span className="text-success-300">pagati {euro(r.total_paid_cents)}</span>
                      ) : undefined
                    }
                  />
                )}
                <div className="flex items-center gap-1.5">
                  {r.status !== "DRAFT" && (
                    <button onClick={() => setSummaryOf(r.id)} className="act">
                      Riepilogo
                    </button>
                  )}
                  {r.status === "DRAFT" ? (
                    <button
                      onClick={() => onOpenWizard({ requestId: r.id, customer: wizardCustomer(r) })}
                      className="act act-primary"
                    >
                      Riprendi
                    </button>
                  ) : mode === "customer" && r.points_payable > 0 ? (
                    <button
                      onClick={() => onOpenWizard({ requestId: r.id, step: "summary", customer: wizardCustomer(r) })}
                      className="act act-primary"
                    >
                      {r.bank_transfer_pending ? "Dati bonifico" : "Paga"}
                    </button>
                  ) : (
                    <button onClick={() => setExpanded(isOpen ? null : r.id)} className="act" aria-expanded={isOpen}>
                      {isOpen ? "Chiudi" : "Dettagli"}
                    </button>
                  )}
                </div>
              </div>
            </div>
            {isOpen && (
              <RequestPoints requestId={r.id} mode={mode === "customer" ? "customer" : "promoter"} onOpenWizard={onOpenWizard} />
            )}
          </div>
        );
      })}
      {summaryOf && <RequestSummaryModal requestId={summaryOf} onClose={() => setSummaryOf(null)} />}
    </div>
  );
}

const PAYMENT_METHOD_LABELS: Record<string, string> = { CARD: "Carta", BANK_TRANSFER: "Bonifico" };

/**
 * Everything filled in and each POD's cost at a glance: holder, address,
 * IBAN, and per POD its package, price with VAT, payment and status.
 */
function RequestSummaryModal({ requestId, onClose }: { requestId: string; onClose: () => void }) {
  const { data, error } = useQuery({
    queryKey: ["contract-request", requestId],
    queryFn: () => fetchJson<ContractRequestDetailRead>(`/api/proxy/contract-requests/${requestId}`),
  });
  const live = (data?.points ?? []).filter((p) => !["REJECTED", "CANCELLED"].includes(p.status));
  const listTotal = live.reduce((sum, p) => sum + (p.gross_amount_cents ?? 0), 0);
  const discounts = live.reduce((sum, p) => sum + (p.payment_discount_cents ?? 0), 0);
  const address = data ? [data.street, [data.postal_code, data.city].filter(Boolean).join(" "), data.province && `(${data.province})`].filter(Boolean).join(", ") : "";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-fade-in" onClick={onClose}>
      <div
        className="w-full max-w-2xl max-h-[90vh] overflow-y-auto panel rounded-3xl border-white/10 bg-surface-950 pop"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="sticky top-0 z-10 flex items-center justify-between gap-3 px-6 py-4 border-b border-white/5 bg-surface-950/95 backdrop-blur">
          <div>
            <p className="kpi-label">Riepilogo pratica</p>
            <h3 className="mt-1 text-xl font-black tracking-tight text-white">{data ? `Pratica #${data.code}` : "Pratica"}</h3>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-white/10 text-surface-400 cursor-pointer" aria-label="Chiudi">✕</button>
        </div>
        <div className="p-6 space-y-5">
          {error && <p className="text-sm text-danger-400">{(error as Error).message}</p>}
          {!data && !error && <div className="h-40 rounded-xl bg-white/5 animate-pulse" />}
          {data && (
            <>
              <section className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-2 text-xs">
                <SummaryFact label="Intestatario" value={data.holder_name ?? "—"} />
                <SummaryFact label="Inviata il" value={formatDate(data.submitted_at ?? data.created_at)} />
                <SummaryFact label="Email" value={data.email ?? "—"} />
                <SummaryFact label="PEC" value={data.pec ?? "—"} />
                <SummaryFact label="IBAN per addebito" value={data.iban ?? "—"} mono />
                <SummaryFact label="Indirizzo di fornitura" value={address || "—"} />
                {data.activated_by_promoter_name && <SummaryFact label="Compilata da" value={data.activated_by_promoter_name} />}
              </section>

              <section className="space-y-2">
                <p className="kpi-label">
                  Punti di fornitura ({data.points.length})
                </p>
                {data.points.map((p) => {
                  const discount = p.payment_discount_cents ?? 0;
                  const paid = (p.gross_amount_cents ?? 0) - discount;
                  return (
                    <div key={p.id} className="rounded-2xl bg-white/[0.045] ring-1 ring-white/10 p-4">
                      <div className="flex flex-wrap items-start justify-between gap-2">
                        <div className="min-w-0">
                          <p className="text-sm font-semibold text-white">
                            {pointCode(p)} · {ENERGY_POINT_LABELS[p.energy_type ?? ""] ?? "Fornitura"}
                          </p>
                          <p className="text-xs text-surface-300">{p.product_name ?? "Contratto non scelto"}</p>
                          <p className="text-[11px] text-surface-500">
                            {[p.street, [p.postal_code, p.city].filter(Boolean).join(" ")].filter(Boolean).join(", ") || "—"}
                            {p.meter_number ? ` · contatore ${p.meter_number}` : ""}
                          </p>
                        </div>
                        <Chip tone={statusTone(p.status).tone} live={statusTone(p.status).live}>
                          {CONTRACT_STATUS_LABELS[p.status] ?? p.status}
                        </Chip>
                      </div>
                      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mt-3 text-[11px]">
                        <SummaryFact label="Prezzo" value={p.net_amount_cents != null ? euro(p.net_amount_cents) : "—"} />
                        <SummaryFact
                          label={p.vat_rate ? `IVA ${p.vat_rate}%` : "IVA"}
                          value={p.vat_amount_cents ? euro(p.vat_amount_cents) : "non applicata"}
                        />
                        <SummaryFact label="Totale" value={p.gross_amount_cents != null ? euro(p.gross_amount_cents) : "—"} strong />
                        <SummaryFact
                          label="Pagamento"
                          value={
                            p.paid_at
                              ? `${PAYMENT_PLAN_LABELS[p.payment_plan ?? ""] ?? "Pagato"}${p.payment_method ? ` · ${PAYMENT_METHOD_LABELS[p.payment_method] ?? p.payment_method}` : ""}`
                              : p.payment_method === "BANK_TRANSFER"
                                ? "Bonifico in attesa"
                                : "Da pagare"
                          }
                        />
                      </div>
                      {discount > 0 && (
                        <p className="mt-2 text-[11px] text-success-400">
                          Sconto pagamento unico: -{euro(discount)} → {p.paid_at ? "pagati" : "da pagare"} {euro(paid)}
                        </p>
                      )}
                      {p.instalments_total && p.instalments_total > 1 ? (
                        <p className="mt-1 text-[11px] text-surface-500">Rate pagate {p.instalments_paid}/{p.instalments_total}</p>
                      ) : null}
                      {(p.activated_at || p.expires_at) && (
                        <p className="mt-1 text-[11px] text-surface-500">
                          Attivo dal {formatDate(p.activated_at)} · scadenza {formatDate(p.expires_at)}
                        </p>
                      )}
                    </div>
                  );
                })}
              </section>

              <section className="rounded-2xl bg-white/[0.06] ring-1 ring-white/15 p-4 space-y-1 text-sm">
                <div className="flex justify-between text-surface-400">
                  <span>Totale contratti</span>
                  <span className="tabular-nums">{euro(listTotal)}</span>
                </div>
                {discounts > 0 && (
                  <div className="flex justify-between text-success-400">
                    <span>Sconti pagamento unico</span>
                    <span className="tabular-nums">-{euro(discounts)}</span>
                  </div>
                )}
                <div className="flex justify-between text-lg font-black text-white pt-2 mt-1 border-t border-white/10">
                  <span>Totale</span>
                  <span className="tabular-nums">{euro(listTotal - discounts)}</span>
                </div>
              </section>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function SummaryFact({ label, value, mono = false, strong = false }: { label: string; value: string; mono?: boolean; strong?: boolean }) {
  return (
    <div className="min-w-0">
      <p className="text-surface-500">{label}</p>
      <p className={`truncate ${strong ? "text-white font-bold" : "text-surface-300 font-semibold"} ${mono ? "font-mono" : ""}`}>
        {value}
      </p>
    </div>
  );
}

/** Enough for the wizard to open an existing pratica from the all-customers list. */
function wizardCustomer(r: ContractRequestSummaryRead) {
  const [firstName, ...rest] = (r.holder_name ?? "").split(" ");
  return {
    id: r.customer_id,
    kind: r.customer_kind,
    email: null,
    firstName: firstName || null,
    lastName: rest.join(" ") || null,
  };
}

function RequestPoints({
  requestId,
  mode,
  onOpenWizard,
}: {
  requestId: string;
  mode: "customer" | "promoter";
  onOpenWizard: (target: WizardTarget) => void;
}) {
  const { data, error } = useQuery({
    queryKey: ["contract-request", requestId],
    queryFn: () => fetchJson<ContractRequestDetailRead>(`/api/proxy/contract-requests/${requestId}`),
  });
  const [openPoint, setOpenPoint] = useState<string | null>(null);

  if (error) return <p className="px-5 pb-4 text-sm text-danger-400">{(error as Error).message}</p>;
  if (!data) return <div className="mx-5 mb-4 h-20 rounded-xl bg-white/5 animate-pulse" />;

  return (
    <div className="border-t border-white/10 px-4 sm:px-5 py-4 space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2 text-[11px] text-surface-400">
        <span>
          Intestatario: <strong className="text-surface-300">{data.holder_name ?? "—"}</strong>
          {data.email ? ` · ${data.email}` : ""}
          {data.activated_by_promoter_name ? ` · compilata da ${data.activated_by_promoter_name}` : ""}
        </span>
        {data.status !== "DRAFT" && (
          <button
            onClick={() => onOpenWizard({ requestId, step: "documents", customer: wizardCustomer(data) })}
            className="act"
          >
            Documenti d&apos;identità →
          </button>
        )}
      </div>

      {data.points.map((point) => (
        <PointRow
          key={point.id}
          point={point}
          open={openPoint === point.id}
          onToggle={() => setOpenPoint(openPoint === point.id ? null : point.id)}
          mode={mode}
        />
      ))}
    </div>
  );
}

function PointRow({
  point,
  open,
  onToggle,
  mode,
}: {
  point: ContractRequestPointRead;
  open: boolean;
  onToggle: () => void;
  mode: "customer" | "promoter";
}) {
  return (
    <div className="rounded-2xl bg-white/[0.045] ring-1 ring-white/10 transition hover:bg-white/[0.07] hover:ring-white/25">
      <button onClick={onToggle} className="w-full flex items-center justify-between gap-3 p-3 text-left cursor-pointer">
        <div className="min-w-0">
          <p className="kpi-label truncate">
            {ENERGY_POINT_LABELS[point.energy_type ?? ""] ?? "Fornitura"} · {point.product_name ?? "Contratto da scegliere"}
          </p>
          <p className="mt-0.5 text-[15px] font-black text-white font-mono truncate">{pointCode(point)}</p>
          <p className="text-[11px] text-surface-400 truncate">
            {[point.street, point.city].filter(Boolean).join(", ")}
          </p>
        </div>
        <div className="flex flex-col items-end gap-1 shrink-0">
          <Chip tone={statusTone(point.status).tone} live={statusTone(point.status).live}>
            {CONTRACT_STATUS_LABELS[point.status] ?? point.status}
          </Chip>
          <span className="text-[10px] text-surface-500">
            {point.paid_at ? "Pagato" : point.gross_amount_cents != null ? euro(point.gross_amount_cents) : ""}
            {point.instalments_total && point.instalments_total > 1 ? ` · rate ${point.instalments_paid}/${point.instalments_total}` : ""}
          </span>
        </div>
      </button>
      {open && (
        <div className="border-t border-white/5 p-3 space-y-3">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-[11px]">
            <Fact label="Contratto" value={point.id.slice(0, 8).toUpperCase()} mono />
            <Fact label="Attivo dal" value={formatDate(point.activated_at)} />
            <Fact label="Scadenza" value={formatDate(point.expires_at)} />
            <Fact label="Contatore" value={point.meter_number ?? "—"} />
          </div>
          {point.status === "REJECTED" && (
            <p className="text-xs text-danger-400">
              Questo contratto non è stato approvato. Gli altri punti della pratica non ne risentono. Contatta il supporto per
              i dettagli.
            </p>
          )}
          {point.documents_missing > 0 && (
            <p className="text-xs text-warn-400">
              {mode === "customer" ? "Carica" : "Manca"} la bolletta di questo punto (oppure un&apos;unica bolletta sulla pratica).
            </p>
          )}
          {mode === "customer" && <IbanEditor contractId={point.id} initialIban={point.iban} />}
          <ContractDocumentsPanel contractId={point.id} />
        </div>
      )}
    </div>
  );
}

/** A contract's IBAN, editable after submission (changed bank or typo). */
function IbanEditor({ contractId, initialIban }: { contractId: string; initialIban: string | null }) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(initialIban ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      const res = await fetch(`/api/proxy/contracts/${contractId}/iban`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ iban: value.replace(/\s/g, "").toUpperCase() }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      setEditing(false);
      await queryClient.invalidateQueries({ queryKey: ["contract-request"] });
    } catch (err: any) {
      setError(err.message || "IBAN non valido. Controlla il formato inserito.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="text-[11px]">
      <span className="text-surface-500">IBAN per addebito</span>
      {editing ? (
        <div className="flex items-center gap-2 mt-0.5">
          <input
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder="IT00A0000000000000000000000"
            className="w-full max-w-xs rounded-lg field px-2 py-1 text-xs uppercase font-mono focus:border-brand-500"
          />
          <button onClick={handleSave} disabled={saving} className="font-semibold text-success-400 cursor-pointer disabled:opacity-50">
            {saving ? "..." : "Salva"}
          </button>
          <button onClick={() => setEditing(false)} className="font-semibold text-surface-500 cursor-pointer">
            Annulla
          </button>
        </div>
      ) : (
        <div className="flex items-center gap-2 mt-0.5">
          <span className="font-mono text-surface-300">{initialIban ?? "Non impostato"}</span>
          <button onClick={() => { setValue(initialIban ?? ""); setEditing(true); }} className="font-semibold text-brand-400 cursor-pointer">
            {initialIban ? "Modifica" : "Aggiungi"}
          </button>
        </div>
      )}
      {error && <p className="text-danger-400 mt-1">{error}</p>}
    </div>
  );
}

function Fact({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div>
      <p className="text-surface-500">{label}</p>
      <p className={`text-surface-300 font-semibold ${mono ? "font-mono" : ""}`}>{value}</p>
    </div>
  );
}

/** For callers that just need to refresh every pratiche list. */
export function useInvalidateContractRequests() {
  const queryClient = useQueryClient();
  return () => {
    queryClient.invalidateQueries({ queryKey: ["contract-requests"] });
    queryClient.invalidateQueries({ queryKey: ["contract-request"] });
  };
}
