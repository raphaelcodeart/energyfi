"use client";

import { Fragment, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Pagination, usePagination } from "@/components/pagination";
import { friendlyApiError } from "@/lib/api-error";
import type { InvoiceRedemptionRead } from "@/lib/types";
import { Chip, Figure, Identity, RowActions, Stack, type ChipTone } from "@/components/ui/data-cells";

const STATUS_LABELS: Record<string, string> = {
  SUBMITTED: "Da verificare",
  PAYMENT_PENDING: "Attesa pagamento 5%",
  CREDITED: "Accreditata",
  REJECTED: "Rifiutata",
};
const PAYMENT_METHOD_LABELS: Record<string, string> = {
  BANK_TRANSFER: "Bonifico",
  CARD: "Carta (Stripe)",
};
const STATUS_TONES: Record<string, ChipTone> = {
  SUBMITTED: "warn",
  PAYMENT_PENDING: "warn",
  CREDITED: "ok",
  REJECTED: "bad",
};

function euro(cents: number): string {
  return (cents / 100).toLocaleString("it-IT", { style: "currency", currency: "EUR" });
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("it-IT", { day: "2-digit", month: "short", year: "numeric" });
}

function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" });
}

async function fetchQueue(statusFilter: string): Promise<InvoiceRedemptionRead[]> {
  const qs = statusFilter !== "ALL" ? `?status_filter=${statusFilter}` : "";
  const res = await fetch(`/api/proxy/invoice-redemptions/admin${qs}`);
  if (!res.ok) throw new Error("Impossibile caricare le richieste di riscatto.");
  return res.json();
}

/**
 * Admin queue for partner-invoice cashback. Two actions per redemption:
 * "verify" (confirms the amount, opens the 5% payment window) and
 * "confirm-payment" (credits the wallet). Gated by wallet.manage server-side.
 */
export function AdminInvoiceRedemptionsPanel() {
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState("SUBMITTED");
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [verifyAmount, setVerifyAmount] = useState("");
  const [actionLoadingId, setActionLoadingId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [rejectingId, setRejectingId] = useState<string | null>(null);
  const [rejectReason, setRejectReason] = useState("");

  const { data: queue, error: loadError } = useQuery({
    queryKey: ["admin", "invoice-redemptions", statusFilter],
    queryFn: () => fetchQueue(statusFilter),
  });

  async function invalidate() {
    await queryClient.invalidateQueries({ queryKey: ["admin", "invoice-redemptions"] });
    await queryClient.invalidateQueries({ queryKey: ["admin", "wallets"] });
  }

  async function handleViewPhoto(id: string) {
    const res = await fetch(`/api/proxy/invoice-redemptions/admin/${id}/photo-url`);
    if (!res.ok) return;
    const { url } = await res.json();
    window.open(url, "_blank", "noopener,noreferrer");
  }

  async function handleViewPaymentProof(id: string) {
    const res = await fetch(`/api/proxy/invoice-redemptions/admin/${id}/payment-proof-url`);
    if (!res.ok) return;
    const { url } = await res.json();
    window.open(url, "_blank", "noopener,noreferrer");
  }

  async function handleVerify(id: string) {
    const amountCents = Math.round(parseFloat(verifyAmount.replace(",", ".")) * 100);
    if (!Number.isFinite(amountCents) || amountCents <= 0) {
      setActionError("Inserisci un importo valido.");
      return;
    }
    setActionLoadingId(id);
    setActionError(null);
    try {
      const res = await fetch(`/api/proxy/invoice-redemptions/admin/${id}/verify`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ confirmed_amount_cents: amountCents }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      setExpandedId(null);
      setVerifyAmount("");
      await invalidate();
    } catch (err: any) {
      setActionError(err.message || "Impossibile verificare la richiesta.");
    } finally {
      setActionLoadingId(null);
    }
  }

  const pagination = usePagination(queue ?? []);

  async function handleConfirmPayment(id: string) {
    setActionLoadingId(id);
    setActionError(null);
    try {
      const res = await fetch(`/api/proxy/invoice-redemptions/admin/${id}/confirm-payment`, { method: "POST" });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      await invalidate();
    } catch (err: any) {
      setActionError(err.message || "Impossibile confermare il pagamento.");
    } finally {
      setActionLoadingId(null);
    }
  }

  async function handleReject(id: string) {
    if (!rejectReason.trim()) return;
    setActionLoadingId(id);
    setActionError(null);
    try {
      const res = await fetch(`/api/proxy/invoice-redemptions/admin/${id}/reject`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reason: rejectReason.trim() }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      setRejectingId(null);
      setRejectReason("");
      await invalidate();
    } catch (err: any) {
      setActionError(err.message || "Impossibile rifiutare la richiesta.");
    } finally {
      setActionLoadingId(null);
    }
  }

  return (
    <div className="space-y-5">
      <div className="subnav">
        {["SUBMITTED", "PAYMENT_PENDING", "CREDITED", "REJECTED", "ALL"].map((s) => (
          <button key={s} onClick={() => setStatusFilter(s)} data-active={statusFilter === s} className="subnav-pill">
            {s === "ALL" ? "Tutte" : STATUS_LABELS[s]}
          </button>
        ))}
      </div>

      {actionError && (
        <div className="p-3 rounded-2xl bg-danger-500/10 border border-danger-500/20 text-danger-400 text-xs pop">{actionError}</div>
      )}
      {loadError && <p className="text-sm text-danger-400">Impossibile caricare le richieste.</p>}

      <div className="panel rounded-3xl p-4 md:p-6">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr>
                <th className="px-4 py-3">Richiedente</th>
                <th className="px-4 py-3">Quando</th>
                <th className="px-4 py-3">Situazione</th>
                <th className="px-4 py-3 text-right">Valore fattura</th>
                <th className="px-4 py-3"><span className="sr-only">Azioni</span></th>
              </tr>
            </thead>
            <tbody className="text-surface-300">
              {queue === undefined ? (
                <tr><td colSpan={5} className="px-4 py-8 text-center text-surface-400">Caricamento...</td></tr>
              ) : queue.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-4 py-10">
                    <div className="flex flex-col items-center gap-2 text-center">
                      <svg viewBox="0 0 24 24" className="h-8 w-8 text-accent-300 float-soft" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
                        <path d="M6 2h9l5 5v15H6zM14 2v6h6M9 13h8M9 17h5" strokeLinejoin="round" />
                      </svg>
                      <span className="text-sm font-semibold text-surface-200">Nessuna richiesta in questo stato.</span>
                    </div>
                  </td>
                </tr>
              ) : (
                pagination.pageItems.map((r) => (
                  <Fragment key={r.id}>
                    <tr>
                      <td className="px-4 py-3">
                        <Identity name={r.customer_display_name} detail={`Partner: ${r.partner_name}`} />
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap">
                        <Stack
                          title={formatDate(r.created_at)}
                          detail={
                            r.status === "CREDITED" && r.credited_at
                              ? `accreditata il ${formatDate(r.credited_at)}, ${formatTime(r.credited_at)}`
                              : `ore ${formatTime(r.created_at)}`
                          }
                        />
                      </td>
                      <td className="px-4 py-3">
                        <div className="space-y-1">
                          <Chip tone={STATUS_TONES[r.status] ?? "muted"} live={r.status === "SUBMITTED" || r.status === "PAYMENT_PENDING"}>
                            {STATUS_LABELS[r.status]}
                          </Chip>
                          {r.status === "PAYMENT_PENDING" && (
                            <div className="font-mono text-[10.5px] text-surface-400">
                              Metodo: {r.payment_method ? PAYMENT_METHOD_LABELS[r.payment_method] ?? r.payment_method : "—"}
                              {r.payment_reference_code && <> · Codice bonifico: {r.payment_reference_code}</>}
                              {r.payment_due_cents != null && <> · Atteso: {euro(r.payment_due_cents)}</>}
                            </div>
                          )}
                          {r.rejection_reason && (
                            <div className="max-w-[260px] truncate text-[10.5px] text-danger-400" title={r.rejection_reason}>Motivo rifiuto: {r.rejection_reason}</div>
                          )}
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <Figure
                          value={euro(r.confirmed_amount_cents ?? r.declared_amount_cents)}
                          detail={
                            r.confirmed_amount_cents != null
                              ? `confermato · dichiarato ${euro(r.declared_amount_cents)}`
                              : "dichiarato"
                          }
                          ratio={
                            r.confirmed_amount_cents != null && r.declared_amount_cents > 0
                              ? r.confirmed_amount_cents / r.declared_amount_cents
                              : null
                          }
                        />
                      </td>
                      <td className="px-4 py-3">
                        <RowActions>
                          <button onClick={() => handleViewPhoto(r.id)} className="act">
                            Documento
                          </button>
                          {r.status === "SUBMITTED" && (
                            <button
                              onClick={() => { setExpandedId(expandedId === r.id ? null : r.id); setVerifyAmount((r.declared_amount_cents / 100).toFixed(2)); }}
                              className="act act-primary"
                            >
                              Verifica importo
                            </button>
                          )}
                          {r.status === "PAYMENT_PENDING" && r.payment_proof_uploaded_at && (
                            <button onClick={() => handleViewPaymentProof(r.id)} className="act">
                              Prova pagamento
                            </button>
                          )}
                          {r.status === "PAYMENT_PENDING" && (
                            r.payment_method === "CARD" ? (
                              <Chip tone="info" live>In attesa di conferma Stripe</Chip>
                            ) : (
                              <button onClick={() => handleConfirmPayment(r.id)} disabled={actionLoadingId === r.id} className="act act-primary">
                                {actionLoadingId === r.id ? "..." : "Conferma bonifico ricevuto"}
                              </button>
                            )
                          )}
                          {(r.status === "SUBMITTED" || r.status === "PAYMENT_PENDING") && (
                            <button onClick={() => setRejectingId(rejectingId === r.id ? null : r.id)} className="act !text-danger-400">
                              Rifiuta
                            </button>
                          )}
                        </RowActions>
                      </td>
                    </tr>

                    {expandedId === r.id && (
                      <tr>
                        <td colSpan={5} className="px-5 py-4">
                          <div className="flex flex-wrap items-end gap-3 pop">
                            <div className="space-y-1">
                              <label className="kpi-label block">Importo reale della fattura (EUR)</label>
                              <input
                                autoFocus
                                inputMode="decimal"
                                value={verifyAmount}
                                onChange={(e) => setVerifyAmount(e.target.value)}
                                className="rounded-xl field px-3 py-1.5 text-sm w-40 focus:border-brand-500"
                              />
                            </div>
                            <button onClick={() => handleVerify(r.id)} disabled={actionLoadingId === r.id} className="act act-primary">
                              {actionLoadingId === r.id ? "..." : "Conferma importo"}
                            </button>
                            <p className="text-[11px] text-surface-400 pb-2">
                              Il cliente verrà avvisato di pagare il 5% ({(() => {
                                const v = Math.round(parseFloat(verifyAmount.replace(",", ".")) * 100);
                                return Number.isFinite(v) ? euro(Math.round(v * 0.05)) : "—";
                              })()})
                            </p>
                          </div>
                        </td>
                      </tr>
                    )}

                    {rejectingId === r.id && (
                      <tr>
                        <td colSpan={5} className="px-5 py-4">
                          <div className="flex flex-wrap items-end gap-3 pop">
                            <div className="space-y-1 flex-1 max-w-sm">
                              <label className="kpi-label block">Motivo del rifiuto</label>
                              <input
                                autoFocus
                                value={rejectReason}
                                onChange={(e) => setRejectReason(e.target.value)}
                                className="w-full rounded-xl field px-3 py-1.5 text-sm focus:border-brand-500"
                              />
                            </div>
                            <button onClick={() => handleReject(r.id)} disabled={actionLoadingId === r.id} className="act !text-danger-400">
                              {actionLoadingId === r.id ? "..." : "Conferma rifiuto"}
                            </button>
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
      <Pagination {...pagination} label="richieste" />
    </div>
  );
}
