"use client";

import { useFeatures } from "@/lib/features";
import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { friendlyApiError } from "@/lib/api-error";
import type { OrderQuoteRead, OrderRead } from "@/lib/types";

function euro(cents: number): string {
  return (cents / 100).toLocaleString("it-IT", { style: "currency", currency: "EUR" });
}

function sosnetCash(cents: number): string {
  return `${(cents / 100).toLocaleString("it-IT", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} SosnetCash`;
}

async function fetchQuote(productVersionId: string): Promise<OrderQuoteRead> {
  const res = await fetch(`/api/proxy/orders/quote/mine?product_version_id=${productVersionId}`);
  if (!res.ok) throw new Error("Impossibile calcolare il preventivo.");
  return res.json();
}

async function fetchPaymentInfo(): Promise<{ iban: string | null; holder: string; instructions: string | null }> {
  const res = await fetch("/api/proxy/invoice-redemptions/payment-info");
  if (!res.ok) throw new Error("Impossibile caricare le coordinate di pagamento.");
  return res.json();
}

/** Numbered badge for a checkout step. Purely visual: all applicable steps
    are shown at once. */
function StepBadge({ n, done }: { n: number; done?: boolean }) {
  return (
    <span
      className={`flex items-center justify-center w-6 h-6 rounded-full text-[11px] font-bold shrink-0 ${
        done ? "bg-success-500 text-white" : "bg-brand-600 text-white"
      }`}
    >
      {done ? (
        <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
        </svg>
      ) : (
        n
      )}
    </span>
  );
}

/** Large on/off switch for the SosnetCash and cashback choices. */
function Toggle({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className="flex items-center gap-2.5 cursor-pointer group"
    >
      <span
        className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors ${
          checked ? "bg-brand-600" : "bg-white/15 light:bg-surface-300"
        }`}
      >
        <span
          className={`inline-block h-4.5 w-4.5 transform rounded-full bg-white shadow transition-transform ${
            checked ? "translate-x-6" : "translate-x-1"
          }`}
          style={{ height: "18px", width: "18px" }}
        />
      </span>
      <span className="text-sm font-semibold text-white light:text-surface-900">{label}</span>
    </button>
  );
}

/** Self-checkout for a DROPSHIPPING/PARTNER product (INTERNAL products have
    no "Acquista" button). Each optional choice (SosnetCash, OTP, cashback,
    payment method) is a numbered section, with a live price summary.
    Amounts shown come from the server quote. */
export function ProductCheckoutModal({
  productVersionId,
  productName,
  onClose,
}: {
  productVersionId: string;
  productName: string;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const { data: quote, error: quoteError } = useQuery({
    queryKey: ["customer", "orders", "quote", productVersionId],
    queryFn: () => fetchQuote(productVersionId),
  });

  const [creditAmount, setCreditAmount] = useState("0.00");
  const [useCredit, setUseCredit] = useState(false);
  const [paymentMethod, setPaymentMethod] = useState<"BANK_TRANSFER" | "CARD" | null>(null);
  const [cashbackRequested, setCashbackRequested] = useState(false);
  const [step, setStep] = useState<"choose" | "bank_instructions" | "card_redirect" | "success">("choose");
  const [placedOrder, setPlacedOrder] = useState<OrderRead | null>(null);
  const [submitLoading, setSubmitLoading] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  // Spending SosnetCash requires an emailed OTP
  // (POST /orders/mine/request-credit-otp, orders/service.py::create_order).
  const [otpCode, setOtpCode] = useState("");
  const [otpRequested, setOtpRequested] = useState(false);
  const [otpRequesting, setOtpRequesting] = useState(false);
  const [otpError, setOtpError] = useState<string | null>(null);

  const { data: paymentInfo } = useQuery({
    queryKey: ["customer", "payment-info"],
    queryFn: fetchPaymentInfo,
    enabled: step === "bank_instructions",
  });

  // SosnetCash can pay only while the wallet feature is on.
  const walletOn = useFeatures().wallet;
  const maxUsableCents = quote && walletOn ? Math.min(quote.max_creditable_cents, quote.customer_wallet_balance_cents) : 0;

  useEffect(() => {
    if (!quote) return;
    // Credit starts off: spending SosnetCash is an explicit choice.
    setUseCredit(false);
    setCreditAmount("0.00");
    if (quote.bank_transfer_available) setPaymentMethod("BANK_TRANSFER");
    else if (quote.card_available) setPaymentMethod("CARD");
    else setPaymentMethod(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [quote?.product_version_id]);

  const creditCents = quote && useCredit
    ? Math.min(
        Math.round((parseFloat(creditAmount.replace(",", ".")) || 0) * 100),
        quote.max_creditable_cents,
        quote.customer_wallet_balance_cents
      )
    : 0;
  // Share of the price actually covered, unlike quote.credit_discount_percentage
  // (the configured cap).
  const effectiveDiscountPct = quote && quote.amount_cents > 0 ? Math.round((creditCents / quote.amount_cents) * 100) : 0;
  const residualCents = quote ? quote.amount_cents - creditCents : 0;
  const canRequestCashback = !!quote?.cashback_available && residualCents > 0;
  const cashbackSurchargeCents = canRequestCashback && cashbackRequested
    ? Math.round((residualCents * (quote?.cashback_percentage ?? 0)) / 100)
    : 0;
  const totalToPayCents = residualCents + cashbackSurchargeCents;
  const needsPaymentMethod = totalToPayCents > 0;
  const noMethodAvailable = quote ? !quote.bank_transfer_available && !quote.card_available : false;
  const otpConfirmed = creditCents === 0 || !!otpCode.trim();

  function setCreditFraction(fraction: number) {
    const cents = Math.round(maxUsableCents * fraction);
    setCreditAmount((cents / 100).toFixed(2));
    setOtpRequested(false);
    setOtpCode("");
  }

  function handleToggleCredit(next: boolean) {
    setUseCredit(next);
    setOtpRequested(false);
    setOtpCode("");
    if (next) {
      // Enabling defaults to the maximum usable amount.
      setCreditAmount((maxUsableCents / 100).toFixed(2));
    } else {
      setCreditAmount("0.00");
    }
  }

  async function handleRequestOtp() {
    setOtpRequesting(true);
    setOtpError(null);
    try {
      const res = await fetch("/api/proxy/orders/mine/request-credit-otp", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ product_version_id: productVersionId, credit_applied_cents: creditCents }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      setOtpRequested(true);
    } catch (err: any) {
      setOtpError(err.message || "Impossibile inviare il codice.");
    } finally {
      setOtpRequesting(false);
    }
  }

  async function handleConfirm() {
    if (!quote) return;
    if (needsPaymentMethod && !paymentMethod) {
      setSubmitError("Seleziona un metodo di pagamento.");
      return;
    }
    if (creditCents > 0 && !otpCode.trim()) {
      setSubmitError("Inserisci il codice di conferma ricevuto via email per usare i tuoi SosnetCash.");
      return;
    }
    setSubmitLoading(true);
    setSubmitError(null);
    try {
      const res = await fetch("/api/proxy/orders/mine", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          product_version_id: productVersionId,
          credit_applied_cents: creditCents,
          cashback_requested: cashbackRequested,
          otp_code: creditCents > 0 ? otpCode.trim() : null,
          payment_method: needsPaymentMethod ? paymentMethod : "BANK_TRANSFER",
        }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      const order: OrderRead = await res.json();
      setPlacedOrder(order);
      await queryClient.invalidateQueries({ queryKey: ["customer", "wallet"] });
      await queryClient.invalidateQueries({ queryKey: ["wallet"] });

      if (order.status === "PAID") {
        setStep("success");
        return;
      }
      if (order.payment_method === "CARD") {
        const returnUrl = window.location.href;
        const sessionRes = await fetch(
          `/api/proxy/orders/mine/${order.id}/checkout-session?success_url=${encodeURIComponent(returnUrl)}&cancel_url=${encodeURIComponent(returnUrl)}`,
          { method: "POST" }
        );
        if (!sessionRes.ok) throw new Error(await friendlyApiError(sessionRes));
        const { checkout_url } = await sessionRes.json();
        // New tab, so a failed payment never loses this page.
        window.open(checkout_url, "_blank", "noopener,noreferrer");
        setStep("card_redirect");
        return;
      }
      setStep("bank_instructions");
    } catch (err: any) {
      setSubmitError(err.message || "Impossibile completare l'acquisto.");
    } finally {
      setSubmitLoading(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 light:bg-surface-900/40 backdrop-blur-sm animate-fade-in">
      <div className="w-full max-w-xl panel panel-hover rounded-2xl p-6 border-white/10 light:border-surface-300 bg-surface-950 light:bg-white pop max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-bold text-white light:text-surface-900">Acquista {quote ? "" : productName}</h3>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg hover:bg-white/10 light:hover:bg-surface-900/10 text-surface-400 transition cursor-pointer"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {quoteError && <p className="text-sm text-danger-400">Impossibile caricare il preventivo.</p>}
        {step === "choose" && !quote && !quoteError && (
          <div className="py-10 text-center text-sm text-surface-500">Caricamento preventivo...</div>
        )}

        {step === "success" && placedOrder && (
          <div className="text-center py-6 space-y-3">
            <svg className="w-14 h-14 text-success-400 mx-auto" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <p className="text-sm text-surface-300 light:text-surface-600">
              Ordine confermato -- pagato interamente con i tuoi SosnetCash.
            </p>
            <button
              onClick={onClose}
              className="px-4 py-2 rounded-xl bg-brand-600 hover:bg-brand-500 text-xs font-semibold text-white transition cursor-pointer"
            >
              Chiudi
            </button>
          </div>
        )}

        {step === "card_redirect" && placedOrder && (
          <div className="text-center py-6 space-y-3">
            <svg className="w-14 h-14 text-brand-400 mx-auto" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
            </svg>
            <p className="text-sm text-surface-300 light:text-surface-600">
              Abbiamo aperto Stripe in una nuova scheda per completare il pagamento di{" "}
              <strong className="text-brand-400">{euro(placedOrder.residual_amount_cents)}</strong>.
            </p>
            <p className="text-xs text-surface-500">
              Puoi tornare qui in qualsiasi momento: trovi l&apos;ordine anche in &ldquo;I miei Ordini&rdquo;.
            </p>
            <button
              onClick={onClose}
              className="px-4 py-2 rounded-xl bg-brand-600 hover:bg-brand-500 text-xs font-semibold text-white transition cursor-pointer"
            >
              Chiudi
            </button>
          </div>
        )}

        {step === "bank_instructions" && placedOrder && (
          <div className="space-y-3">
            <p className="text-sm text-surface-300 light:text-surface-600">
              Ordine creato. Paga <strong className="text-brand-400">{euro(placedOrder.residual_amount_cents)}</strong> tramite
              bonifico per confermarlo.
            </p>
            <div className="p-4 rounded-xl bg-white/5 light:bg-surface-900/5 border border-white/10 light:border-surface-200 text-xs space-y-1.5">
              {paymentInfo?.iban ? (
                <>
                  <p><span className="text-surface-500">IBAN:</span> <span className="font-mono">{paymentInfo.iban}</span></p>
                  <p><span className="text-surface-500">Intestatario:</span> {paymentInfo.holder}</p>
                  {paymentInfo.instructions && <p className="text-surface-400 light:text-surface-500 pt-1">{paymentInfo.instructions}</p>}
                </>
              ) : (
                <p className="text-surface-500">Contatta l&apos;amministrazione per le coordinate bancarie.</p>
              )}
              <p className="pt-1"><span className="text-surface-500">Causale consigliata:</span> <span className="font-mono text-brand-400">Ordine {placedOrder.id.slice(0, 8).toUpperCase()}</span></p>
            </div>
            <button
              onClick={onClose}
              className="w-full px-4 py-2 rounded-xl bg-brand-600 hover:bg-brand-500 text-xs font-semibold text-white transition cursor-pointer"
            >
              Ho capito
            </button>
          </div>
        )}

        {step === "choose" && quote && (
          <div className="space-y-5">
            {/* Product and price, discounted live once SosnetCash is applied */}
            <div className="p-4 rounded-xl bg-white/5 light:bg-surface-900/5 border border-white/10 light:border-surface-200">
              <p className="text-sm font-semibold text-white light:text-surface-900 mb-2">{quote.product_name}</p>
              <div className="flex items-end gap-3 flex-wrap">
                <div>
                  <p className="text-[10px] text-surface-500 uppercase tracking-wide">
                    {creditCents > 0 ? "Prezzo scontato" : "Prezzo"}
                  </p>
                  <p className={`text-2xl font-extrabold ${creditCents > 0 ? "text-success-400" : "text-white light:text-surface-900"}`}>
                    {euro(Math.max(residualCents, 0))}
                  </p>
                </div>
                {creditCents > 0 && (
                  <div className="pb-1">
                    <p className="text-[10px] text-surface-500 uppercase tracking-wide">Prezzo pieno</p>
                    <p className="text-sm text-surface-500 line-through">{euro(quote.amount_cents)}</p>
                  </div>
                )}
                {creditCents > 0 && (
                  <span className="mb-1 px-2 py-1 rounded-full text-[11px] font-bold bg-success-500/15 text-success-400 border border-success-500/30">
                    -{effectiveDiscountPct}%
                  </span>
                )}
              </div>
              {quote.max_creditable_cents > 0 && (
                <p className="text-[11px] text-surface-500 mt-2">
                  Il tuo saldo: <strong className="text-white light:text-surface-900">{sosnetCash(quote.customer_wallet_balance_cents)}</strong>
                  {" "}· su questo prodotto puoi usarne fino a {sosnetCash(maxUsableCents)} (max {quote.credit_discount_percentage}% di sconto)
                </p>
              )}
            </div>

            {/* Step 1: SosnetCash */}
            {quote.max_creditable_cents > 0 && (
              <div className="p-4 rounded-xl border border-white/10 light:border-surface-200 space-y-3">
                <div className="flex items-center justify-between gap-3 flex-wrap">
                  <div className="flex items-center gap-2.5">
                    <StepBadge n={1} />
                    <Toggle checked={useCredit} onChange={handleToggleCredit} label="Usa i tuoi SosnetCash per abbassare il prezzo" />
                  </div>
                </div>

                {useCredit && (
                  <div className="pl-8 space-y-3">
                    <p className="text-[11px] text-surface-500">
                      I tuoi SosnetCash valgono 1:1 come sconto: ogni SosnetCash speso abbassa il prezzo di 1&euro;.
                    </p>
                    <div className="flex flex-wrap gap-2">
                      {[0.25, 0.5, 0.75, 1].map((fraction) => {
                        const presetCents = Math.round(maxUsableCents * fraction);
                        const isActive = Math.round((parseFloat(creditAmount.replace(",", ".")) || 0) * 100) === presetCents;
                        return (
                          <button
                            key={fraction}
                            type="button"
                            onClick={() => setCreditFraction(fraction)}
                            className={`px-3 py-1.5 rounded-lg text-xs font-semibold border transition cursor-pointer ${
                              isActive
                                ? "bg-brand-600 border-brand-600 text-white"
                                : "bg-white/5 light:bg-surface-900/5 border-white/10 light:border-surface-300 text-surface-300 light:text-surface-600 hover:bg-white/10"
                            }`}
                          >
                            {fraction === 1 ? "Massimo" : `${Math.round(fraction * 100)}%`}
                          </button>
                        );
                      })}
                    </div>
                    <div className="flex items-center gap-2">
                      <label className="text-[10px] font-semibold text-surface-300 light:text-surface-600 uppercase shrink-0">
                        Importo personalizzato
                      </label>
                      <input
                        inputMode="decimal"
                        value={creditAmount}
                        onChange={(e) => { setCreditAmount(e.target.value); setOtpRequested(false); setOtpCode(""); }}
                        className="w-full max-w-[140px] rounded-lg field px-3 py-1.5 text-sm focus:border-brand-500"
                      />
                      <span className="text-xs text-surface-500 shrink-0">SosnetCash</span>
                    </div>
                    <p className="text-xs px-3 py-2 rounded-lg bg-brand-500/10 border border-brand-500/20 text-brand-300">
                      Stai usando <strong>{sosnetCash(creditCents)}</strong> = <strong>{effectiveDiscountPct}% di sconto</strong> su questo ordine.
                    </p>
                  </div>
                )}
              </div>
            )}

            {/* Step 2: OTP, only when spending credit */}
            {creditCents > 0 && (
              <div className="p-4 rounded-xl border border-white/10 light:border-surface-200 space-y-2.5">
                <div className="flex items-center gap-2.5">
                  <StepBadge n={2} done={!!otpCode.trim()} />
                  <p className="text-sm font-semibold text-white light:text-surface-900">Conferma via email</p>
                </div>
                <p className="text-[11px] text-surface-500 pl-8">
                  Per sicurezza, ti mandiamo un codice via email per confermare l&apos;uso dei tuoi SosnetCash su questo ordine.
                </p>
                <div className="pl-8">
                  {!otpRequested ? (
                    <button
                      type="button"
                      onClick={handleRequestOtp}
                      disabled={otpRequesting}
                      className="px-4 py-2 rounded-lg bg-brand-600/15 hover:bg-brand-600/25 border border-brand-500/30 text-xs font-semibold text-brand-400 transition cursor-pointer disabled:opacity-50"
                    >
                      {otpRequesting ? "Invio in corso..." : "Invia codice via email"}
                    </button>
                  ) : (
                    <div className="space-y-1.5">
                      <p className="text-[11px] text-success-400 flex items-center gap-1">
                        <svg className="w-3.5 h-3.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
                        </svg>
                        Codice inviato -- controlla la tua email
                      </p>
                      <div className="flex items-center gap-2">
                        <input
                          inputMode="numeric"
                          autoFocus
                          value={otpCode}
                          onChange={(e) => setOtpCode(e.target.value)}
                          placeholder="Codice ricevuto via email"
                          className="w-full max-w-[200px] rounded-lg field px-3 py-2 text-sm font-mono tracking-wider focus:border-brand-500"
                        />
                        <button
                          type="button"
                          onClick={handleRequestOtp}
                          disabled={otpRequesting}
                          className="text-[11px] font-semibold text-brand-400 hover:text-brand-300 cursor-pointer disabled:opacity-50"
                        >
                          Rinvia
                        </button>
                      </div>
                    </div>
                  )}
                  {otpError && <p className="text-[11px] text-danger-400 mt-1.5">{otpError}</p>}
                </div>
              </div>
            )}

            {/* Step 3: optional cashback */}
            {canRequestCashback && (
              <div className="p-4 rounded-xl border border-white/10 light:border-surface-200 space-y-2.5">
                <div className="flex items-center gap-2.5">
                  <StepBadge n={creditCents > 0 ? 3 : 2} />
                  <Toggle checked={cashbackRequested} onChange={setCashbackRequested} label="Riscuoti subito cashback" />
                </div>
                <p className="text-[11px] text-surface-500 pl-8">
                  Paga il <strong className="text-brand-400">{quote.cashback_percentage}%</strong> in più ora
                  ({euro(Math.round((residualCents * quote.cashback_percentage) / 100))}) e ricevi l&apos;intero importo
                  pagato oggi accreditato come SosnetCash sul tuo wallet, non appena il pagamento è confermato.
                </p>
              </div>
            )}

            {/* Step 4: payment method for the amount still due */}
            {needsPaymentMethod && (
              <div className="p-4 rounded-xl border border-white/10 light:border-surface-200 space-y-2.5">
                <div className="flex items-center gap-2.5">
                  <StepBadge n={[creditCents > 0, canRequestCashback].filter(Boolean).length + 2} done={!!paymentMethod} />
                  <p className="text-sm font-semibold text-white light:text-surface-900">Come vuoi pagare il resto?</p>
                </div>
                {noMethodAvailable ? (
                  <p className="text-xs text-danger-400 pl-8">
                    Nessun metodo di pagamento è al momento disponibile per completare questo ordine. Contatta l&apos;amministrazione.
                  </p>
                ) : (
                  <div className="pl-8 flex gap-2.5">
                    {quote.bank_transfer_available && (
                      <button
                        type="button"
                        onClick={() => setPaymentMethod("BANK_TRANSFER")}
                        className={`flex-1 flex items-center justify-center gap-2 px-3 py-3 rounded-xl text-sm font-semibold border-2 transition cursor-pointer ${
                          paymentMethod === "BANK_TRANSFER"
                            ? "bg-brand-600 border-brand-600 text-white shadow-lg shadow-brand-500/20"
                            : "bg-white/5 light:bg-surface-900/5 border-white/10 light:border-surface-300 text-surface-300 light:text-surface-600 hover:bg-white/10"
                        }`}
                      >
                        <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M3 21h18M4 10h16M4 10l8-6 8 6M6 10v9m4-9v9m4-9v9m4-9v9" />
                        </svg>
                        Bonifico
                      </button>
                    )}
                    {quote.card_available && (
                      <button
                        type="button"
                        onClick={() => setPaymentMethod("CARD")}
                        className={`flex-1 flex items-center justify-center gap-2 px-3 py-3 rounded-xl text-sm font-semibold border-2 transition cursor-pointer ${
                          paymentMethod === "CARD"
                            ? "bg-brand-600 border-brand-600 text-white shadow-lg shadow-brand-500/20"
                            : "bg-white/5 light:bg-surface-900/5 border-white/10 light:border-surface-300 text-surface-300 light:text-surface-600 hover:bg-white/10"
                        }`}
                      >
                        <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M2 10h20M6 15h4M2 7a2 2 0 012-2h16a2 2 0 012 2v10a2 2 0 01-2 2H4a2 2 0 01-2-2V7z" />
                        </svg>
                        Carta
                      </button>
                    )}
                  </div>
                )}
              </div>
            )}

            {/* Running total */}
            <div className="p-4 rounded-xl bg-gradient-to-br from-brand-600/10 to-accent-500/5 border border-brand-500/20 space-y-1.5">
              <div className="flex items-center justify-between">
                <p className="text-xs text-surface-400 light:text-surface-500">Prezzo prodotto</p>
                <p className="text-xs text-surface-400 light:text-surface-500">{euro(quote.amount_cents)}</p>
              </div>
              {creditCents > 0 && (
                <div className="flex items-center justify-between">
                  <p className="text-xs text-surface-400 light:text-surface-500">SosnetCash usati</p>
                  <p className="text-xs text-success-400">-{sosnetCash(creditCents)}</p>
                </div>
              )}
              {cashbackSurchargeCents > 0 && (
                <div className="flex items-center justify-between">
                  <p className="text-xs text-surface-400 light:text-surface-500">Cashback ({quote.cashback_percentage}%)</p>
                  <p className="text-xs text-brand-400">+{euro(cashbackSurchargeCents)}</p>
                </div>
              )}
              <div className="flex items-center justify-between pt-1.5 border-t border-white/10 light:border-surface-300">
                <p className="text-sm font-bold text-white light:text-surface-900">Totale da pagare ora</p>
                <p className={`text-xl font-extrabold ${totalToPayCents > 0 ? "text-brand-400" : "text-success-400"}`}>
                  {euro(Math.max(totalToPayCents, 0))}
                </p>
              </div>
              {totalToPayCents <= 0 && (
                <p className="text-[11px] text-success-400 text-right">Coperto interamente dai tuoi SosnetCash</p>
              )}
            </div>

            {submitError && (
              <div className="p-3 rounded-lg bg-danger-500/10 border border-danger-500/20 text-danger-400 text-xs">{submitError}</div>
            )}

            <button
              onClick={handleConfirm}
              disabled={
                submitLoading
                || (needsPaymentMethod && (noMethodAvailable || !paymentMethod))
                || !otpConfirmed
              }
              className="w-full px-4 py-3 rounded-xl bg-gradient-to-r from-brand-600 to-accent-500 hover:from-brand-500 hover:to-accent-400 text-sm font-bold text-white shadow-lg shadow-brand-500/20 transition-all duration-200 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed active:scale-[0.99]"
            >
              {submitLoading ? "Elaborazione..." : totalToPayCents > 0 ? "Conferma e procedi al pagamento" : "Conferma ordine"}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
