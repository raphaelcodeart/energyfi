"use client";

import { Fragment, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Pagination, usePagination } from "@/components/pagination";
import { CameraCaptureModal } from "@/components/camera-capture-modal";
import { friendlyApiError } from "@/lib/api-error";
import { Chip, Figure, IdTag, Identity, RowActions, type ChipTone } from "@/components/ui/data-cells";
import type { InvoiceRedemptionRead, PartnerRead } from "@/lib/types";

const STATUS_LABELS: Record<string, string> = {
  SUBMITTED: "In verifica",
  PAYMENT_PENDING: "Da pagare",
  CREDITED: "Accreditata",
  REJECTED: "Rifiutata",
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

// The invoice and the 5% transfer are real EUR; only the resulting wallet
// credit is SosnetCash (same helper as wallet-panel.tsx).
function sosnetCash(cents: number): string {
  return `${(cents / 100).toLocaleString("it-IT", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} SosnetCash`;
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("it-IT", { day: "2-digit", month: "short", year: "numeric" });
}

function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" });
}

async function fetchPartners(): Promise<PartnerRead[]> {
  const res = await fetch("/api/proxy/partners?active_only=true");
  if (!res.ok) throw new Error("Impossibile caricare i fornitori partner.");
  return res.json();
}

async function fetchMine(): Promise<InvoiceRedemptionRead[]> {
  const res = await fetch("/api/proxy/invoice-redemptions/mine");
  if (!res.ok) throw new Error("Impossibile caricare le tue richieste.");
  return res.json();
}

async function fetchPaymentInfo(): Promise<{ iban: string | null; holder: string }> {
  const res = await fetch("/api/proxy/invoice-redemptions/payment-info");
  if (!res.ok) throw new Error("Impossibile caricare le coordinate di pagamento.");
  return res.json();
}

/**
 * "Riscatta Cashback": turns proof of payment to an external energy partner
 * into wallet credit. An admin verifies the document and amount, the
 * customer pays 5% by bank transfer, an admin confirms receipt; only then is
 * credit issued.
 */
export function InvoiceRedemptionPanel() {
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [partnerId, setPartnerId] = useState("");
  const [amount, setAmount] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [submitLoading, setSubmitLoading] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [cameraOpen, setCameraOpen] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const proofInputRef = useRef<HTMLInputElement>(null);
  const [payingId, setPayingId] = useState<string | null>(null);
  const [switchingId, setSwitchingId] = useState<string | null>(null);
  const [uploadingProofId, setUploadingProofId] = useState<string | null>(null);
  const [proofRedemptionId, setProofRedemptionId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const { data: partners, isLoading: partnersLoading } = useQuery({ queryKey: ["invoice-redemptions", "partners"], queryFn: fetchPartners });
  const noPartnersConfigured = !partnersLoading && (partners ?? []).length === 0;
  const { data: mine, error: loadError } = useQuery({ queryKey: ["invoice-redemptions", "mine"], queryFn: fetchMine });
  const { data: paymentInfo } = useQuery({ queryKey: ["invoice-redemptions", "payment-info"], queryFn: fetchPaymentInfo });

  const pagination = usePagination(mine ?? []);

  async function invalidate() {
    await queryClient.invalidateQueries({ queryKey: ["invoice-redemptions", "mine"] });
  }

  async function startCardCheckout(redemption: InvoiceRedemptionRead) {
    setActionError(null);
    setPayingId(redemption.id);
    try {
      // Opens Stripe in a new tab so an abandoned payment never loses the
      // dashboard; success_url returns here with a banner (see
      // customer-client-page.tsx's PaymentReturnBanner).
      const returnUrl = new URL("/customer", window.location.origin);
      returnUrl.searchParams.set("tab", "cashback");
      const successUrl = new URL(returnUrl);
      successUrl.searchParams.set("payment", "success");
      const cancelUrl = new URL(returnUrl);
      cancelUrl.searchParams.set("payment", "cancelled");

      const res = await fetch(
        `/api/proxy/invoice-redemptions/mine/${redemption.id}/checkout-session?success_url=${encodeURIComponent(successUrl.toString())}&cancel_url=${encodeURIComponent(cancelUrl.toString())}`,
        { method: "POST" }
      );
      if (!res.ok) throw new Error(await friendlyApiError(res));
      const { checkout_url } = await res.json();
      window.open(checkout_url, "_blank", "noopener,noreferrer");
    } catch (err: any) {
      setActionError(err.message || "Impossibile avviare il pagamento.");
    } finally {
      setPayingId(null);
    }
  }

  function handlePay(r: InvoiceRedemptionRead) {
    setActionError(null);
    if (r.payment_method === "BANK_TRANSFER") {
      setExpandedId(expandedId === r.id ? null : r.id);
      return;
    }
    startCardCheckout(r);
  }

  async function handleSwitchMethod(r: InvoiceRedemptionRead, newMethod: "CARD" | "BANK_TRANSFER") {
    setActionError(null);
    setSwitchingId(r.id);
    try {
      const res = await fetch(`/api/proxy/invoice-redemptions/mine/${r.id}/payment-method`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ payment_method: newMethod }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      const updated: InvoiceRedemptionRead = await res.json();
      await invalidate();
      if (newMethod === "CARD") {
        await startCardCheckout(updated);
      } else {
        setExpandedId(r.id);
      }
    } catch (err: any) {
      setActionError(err.message || "Impossibile cambiare il metodo di pagamento.");
    } finally {
      setSwitchingId(null);
    }
  }

  function openProofPicker(redemptionId: string) {
    setActionError(null);
    setProofRedemptionId(redemptionId);
    proofInputRef.current?.click();
  }

  async function handleProofSelected(e: React.ChangeEvent<HTMLInputElement>) {
    const proofFile = e.target.files?.[0];
    e.target.value = "";
    if (!proofFile || !proofRedemptionId) return;
    setUploadingProofId(proofRedemptionId);
    setActionError(null);
    try {
      const body = new FormData();
      body.append("file", proofFile);
      const res = await fetch(`/api/proxy/invoice-redemptions/mine/${proofRedemptionId}/payment-proof`, { method: "POST", body });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      await invalidate();
    } catch (err: any) {
      setActionError(err.message || "Impossibile caricare la prova di pagamento.");
    } finally {
      setUploadingProofId(null);
      setProofRedemptionId(null);
    }
  }

  async function handleViewPaymentProof(redemptionId: string) {
    setActionError(null);
    try {
      const res = await fetch(`/api/proxy/invoice-redemptions/mine/${redemptionId}/payment-proof-url`);
      if (!res.ok) throw new Error(await friendlyApiError(res));
      const { url } = await res.json();
      window.open(url, "_blank", "noopener,noreferrer");
    } catch (err: any) {
      setActionError(err.message || "Impossibile aprire la prova di pagamento.");
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!file || !partnerId) return;
    const amountCents = Math.round(parseFloat(amount.replace(",", ".")) * 100);
    if (!Number.isFinite(amountCents) || amountCents <= 0) {
      setSubmitError("Inserisci un importo valido.");
      return;
    }
    setSubmitLoading(true);
    setSubmitError(null);
    try {
      const formData = new FormData();
      formData.append("partner_id", partnerId);
      formData.append("declared_amount_cents", String(amountCents));
      formData.append("file", file);
      const res = await fetch("/api/proxy/invoice-redemptions", { method: "POST", body: formData });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      setShowForm(false);
      setPartnerId("");
      setAmount("");
      setFile(null);
      await queryClient.invalidateQueries({ queryKey: ["invoice-redemptions", "mine"] });
    } catch (err: any) {
      setSubmitError(err.message || "Impossibile inviare la richiesta.");
    } finally {
      setSubmitLoading(false);
    }
  }

  async function handleViewPhoto(id: string) {
    const res = await fetch(`/api/proxy/invoice-redemptions/mine/${id}/photo-url`);
    if (!res.ok) return;
    const { url } = await res.json();
    window.open(url, "_blank", "noopener,noreferrer");
  }


  return (
    <div className="space-y-6">
      <div className="panel rise rounded-3xl p-6 sm:p-7">
        <div className="flex flex-wrap items-start justify-between gap-4 mb-2">
          <div>
            <p className="kpi-label">Da fattura ad SosnetCash</p>
            <h3 className="mt-1 text-xl font-black tracking-tight text-white">Riscatta Cashback</h3>
          </div>
          <button
            onClick={() => setShowForm(!showForm)}
            disabled={noPartnersConfigured}
            title={noPartnersConfigured ? "Nessun fornitore partner configurato" : undefined}
            className={`act ${showForm ? "" : "act-primary"} !px-4 !py-2 disabled:opacity-40 disabled:cursor-not-allowed`}
          >
            {showForm ? "Annulla" : "Nuova richiesta"}
          </button>
        </div>
        <p className="text-sm text-surface-300 max-w-3xl">
          Hai già pagato una fattura a uno dei nostri fornitori partner? Carica la foto e riscatta il suo valore in
          SosnetCash, pagando solo il 5% del totale (con carta, subito, o con bonifico) — riceverai il 100% + un ulteriore 5% di bonus.
        </p>

        {noPartnersConfigured && (
          <div className="mt-4 p-3 rounded-2xl bg-warn-500/10 border border-warn-500/20 text-warn-400 text-xs flex gap-2">
            <svg className="w-4 h-4 shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <span>Nessun fornitore partner è ancora configurato: contatta l&apos;amministrazione per attivare questa funzione.</span>
          </div>
        )}

        {showForm && (
          <form onSubmit={handleSubmit} className="pop mt-5 pt-5 border-t border-white/10 space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <label className="kpi-label block">Fornitore partner</label>
                <select
                  required
                  value={partnerId}
                  onChange={(e) => setPartnerId(e.target.value)}
                  className="w-full rounded-xl field px-3 py-2.5 text-sm bg-surface-900 focus:border-brand-500"
                >
                  <option value="">Seleziona...</option>
                  {(partners ?? []).map((p) => (
                    <option key={p.id} value={p.id}>{p.name}</option>
                  ))}
                </select>
              </div>
              <div className="space-y-1.5">
                <label className="kpi-label block">Importo totale della fattura (EUR)</label>
                <input
                  required
                  inputMode="decimal"
                  value={amount}
                  onChange={(e) => setAmount(e.target.value)}
                  placeholder="0,00"
                  className="w-full rounded-xl field px-3 py-2.5 text-sm focus:border-brand-500"
                />
              </div>
            </div>
            <div className="space-y-2">
              <label className="kpi-label block">Foto o PDF della fattura</label>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => setCameraOpen(true)}
                  className="flex-1 min-w-[140px] flex items-center justify-center gap-2 px-3 py-3 rounded-2xl bg-brand-600/15 hover:bg-brand-600/25 border border-brand-500/30 text-brand-300 text-xs font-bold transition cursor-pointer"
                >
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M3 9a2 2 0 012-2h.93a2 2 0 001.664-.89l.812-1.22A2 2 0 0110.07 4h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0018.07 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9z" />
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M15 13a3 3 0 11-6 0 3 3 0 016 0z" />
                  </svg>
                  Scatta foto
                </button>
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  className="flex-1 min-w-[140px] flex items-center justify-center gap-2 px-3 py-3 rounded-2xl bg-white/5 hover:bg-white/10 border border-white/10 text-surface-200 text-xs font-bold transition cursor-pointer"
                >
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M9 13h6m-3-3v6m5 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                  </svg>
                  Carica file
                </button>
              </div>
              <input
                ref={fileInputRef}
                type="file"
                accept="image/jpeg,image/png,application/pdf"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                className="hidden"
              />
              {file && (
                <p className="text-[11px] text-success-400 flex items-center gap-1.5">
                  <svg className="w-3.5 h-3.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
                  </svg>
                  {file.name}
                </p>
              )}
              {cameraOpen && (
                <CameraCaptureModal
                  onCapture={(captured) => {
                    setFile(captured);
                    setCameraOpen(false);
                  }}
                  onClose={() => setCameraOpen(false)}
                />
              )}
            </div>
            <button
              type="submit"
              disabled={submitLoading}
              className="act act-primary !px-5 !py-2.5 disabled:opacity-50"
            >
              {submitLoading ? "Invio..." : "Invia per la verifica"}
            </button>
            {submitError && (
              <div className="p-3 rounded-xl bg-danger-500/10 border border-danger-500/20 text-danger-400 text-xs">{submitError}</div>
            )}
          </form>
        )}
      </div>

      <input ref={proofInputRef} type="file" accept="application/pdf,image/jpeg,image/png" className="hidden" onChange={handleProofSelected} />

      {actionError && (
        <div className="p-3 rounded-xl bg-danger-500/10 border border-danger-500/20 text-danger-400 text-xs">{actionError}</div>
      )}

      <div className="panel rise rounded-3xl p-6 sm:p-7">
        <p className="kpi-label">Storico</p>
        <h3 className="mt-1 mb-4 text-xl font-black tracking-tight text-white">Le tue richieste</h3>
        {loadError && <p className="pb-3 text-sm text-danger-400">Impossibile caricare le richieste.</p>}
        {mine === undefined ? (
          <p className="text-center py-10 text-surface-300 text-sm animate-pulse">Caricamento...</p>
        ) : mine.length === 0 ? (
          <div className="flex flex-col items-center gap-3 py-12 text-center">
            <span className="float-soft grid h-14 w-14 place-items-center rounded-2xl bg-brand-500/15 text-brand-300">
              <svg className="w-7 h-7" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M9 14l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </span>
            <p className="text-sm text-surface-300">Nessuna richiesta ancora: carica la tua prima fattura qui sopra.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr>
                  <th className="px-4 py-3">Fornitore</th>
                  <th className="px-4 py-3">Inviata</th>
                  <th className="px-4 py-3 text-right">Valore fattura</th>
                  <th className="px-4 py-3">Situazione</th>
                  <th className="px-4 py-3"></th>
                </tr>
              </thead>
              <tbody>
                {pagination.pageItems.map((r) => (
                  renderRows(r)
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div className="pt-2">
          <Pagination {...pagination} label="richieste" />
        </div>
      </div>
    </div>
  );

  // Main row plus the optional payment-options row of one request.
  function renderRows(r: InvoiceRedemptionRead) {
    const expanded = r.status === "PAYMENT_PENDING" && expandedId === r.id;
    return (
      <Fragment key={r.id}>
        <tr>
          <td className="px-4 py-3">
            <Identity name={r.partner_name} detail={<>Richiesta <IdTag id={r.id} /></>} />
          </td>
          <td className="px-4 py-3 whitespace-nowrap">
            <div className="text-[13px] font-semibold text-white">{formatDate(r.created_at)}</div>
            <div className="text-[11px] text-surface-400">
              ore {formatTime(r.created_at)}
              {r.status === "CREDITED" && r.credited_at && <> · accreditata il {formatDate(r.credited_at)}</>}
            </div>
          </td>
          <td className="px-4 py-3">
            <div className="flex justify-end">
              <Figure
                value={euro(r.confirmed_amount_cents ?? r.declared_amount_cents)}
                detail={r.confirmed_amount_cents != null ? `confermato · dichiarato ${euro(r.declared_amount_cents)}` : "dichiarato"}
              />
            </div>
          </td>
          <td className="px-4 py-3">
            <Chip tone={STATUS_TONES[r.status] ?? "muted"} live={r.status === "SUBMITTED" || r.status === "PAYMENT_PENDING"}>
              {STATUS_LABELS[r.status]}
            </Chip>
            {r.rejection_reason && <p className="mt-1 max-w-[220px] text-[11px] text-danger-400">{r.rejection_reason}</p>}
          </td>
          <td className="px-4 py-3">
            <RowActions>
              {r.status === "PAYMENT_PENDING" && (
                <>
                  <button onClick={() => handlePay(r)} disabled={payingId === r.id} className="act act-primary">
                    {payingId === r.id ? "Apertura Stripe..." : r.payment_method === "CARD" ? "Paga con carta" : "Vedi coordinate bonifico"}
                  </button>
                  <button onClick={() => setExpandedId(expandedId === r.id ? null : r.id)} title="Altre opzioni di pagamento" className="act">
                    {expandedId === r.id ? "Nascondi" : "Altre opzioni"}
                  </button>
                </>
              )}
              <button onClick={() => handleViewPhoto(r.id)} className="act">
                Vedi fattura
              </button>
            </RowActions>
          </td>
        </tr>
        {expanded && (
          <tr>
            <td colSpan={5} className="px-4 py-4">
              <div className="pop text-xs space-y-3">
                <p className="text-surface-200">
                  Paga <strong className="text-brand-300">{euro(r.payment_due_cents ?? 0)}</strong> per riscattare{" "}
                  <strong className="text-success-400">{sosnetCash(r.confirmed_amount_cents ?? 0)}</strong> in SosnetCash.
                </p>

                <div className="flex flex-wrap gap-2">
                  {r.payment_method === "BANK_TRANSFER" ? (
                    <button onClick={() => handleSwitchMethod(r, "CARD")} disabled={switchingId === r.id} className="act">
                      {switchingId === r.id ? "..." : "Paga subito con carta"}
                    </button>
                  ) : (
                    <button onClick={() => handleSwitchMethod(r, "BANK_TRANSFER")} disabled={switchingId === r.id} className="act">
                      {switchingId === r.id ? "..." : "Paga con bonifico"}
                    </button>
                  )}
                  {r.payment_method === "BANK_TRANSFER" && (
                    <>
                      <button onClick={() => openProofPicker(r.id)} disabled={uploadingProofId === r.id} className="act">
                        {uploadingProofId === r.id ? "Caricamento..." : r.payment_proof_uploaded_at ? "Sostituisci prova bonifico" : "Aggiungi prova bonifico"}
                      </button>
                      {r.payment_proof_uploaded_at && (
                        <button onClick={() => handleViewPaymentProof(r.id)} className="act act-primary">
                          Vedi prova caricata
                        </button>
                      )}
                    </>
                  )}
                </div>

                {r.payment_method === "BANK_TRANSFER" && (
                  <div className="grid gap-2 sm:grid-cols-3 rounded-2xl bg-black/25 border border-white/10 p-4">
                    {paymentInfo?.iban ? (
                      <>
                        <div><div className="kpi-label">IBAN</div><div className="mt-1 font-mono text-white break-all">{paymentInfo.iban}</div></div>
                        <div><div className="kpi-label">Intestatario</div><div className="mt-1 text-white">{paymentInfo.holder}</div></div>
                      </>
                    ) : (
                      <p className="text-surface-300 sm:col-span-2">Contatta l&apos;amministrazione per le coordinate bancarie.</p>
                    )}
                    <div><div className="kpi-label">Causale (obbligatoria)</div><div className="mt-1 font-mono text-brand-300">{r.payment_reference_code}</div></div>
                  </div>
                )}
              </div>
            </td>
          </tr>
        )}
      </Fragment>
    );
  }
}
