"use client";

import { useFeatures } from "@/lib/features";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { friendlyApiError } from "@/lib/api-error";
import { ProductThumbnail } from "@/components/product-thumbnail";
import { useMarketplaceConfig } from "@/components/marketplace-rules-card";
import { useCartActions } from "@/components/shop-cart";
import {
  AddressFields,
  DeliveryAddress,
  Section,
  addressComplete,
  bankTransferDiscount,
  euro,
  inputClass,
  sosnetCash,
} from "@/components/marketplace-checkout-bits";
import { vatLineLabel } from "@/lib/product-audience";
import type { AliexpressOrderRead, CartSectionRead, CustomerRead } from "@/lib/types";

/**
 * Cart checkout.
 * One order for all lines of a shop: one shipment, one payment, one OTP code.
 * The browser never sends what is being bought (the server reads the caller's
 * cart) nor its price: every amount here is a preview of what the server
 * recomputes and freezes on the order. The shop is a prop so the same window
 * serves any shop with a cart.
 */

type Step = "checkout" | "bank_instructions" | "card_redirect" | "success";

/** Routes are the same for every shop, only the prefix changes. */
const shopRoutes = (shop: string) => ({
  quote: `/api/proxy/${shop}/orders/quote/mine/cart`,
  otp: `/api/proxy/${shop}/orders/mine/cart/request-credit-otp`,
  create: `/api/proxy/${shop}/orders/mine/cart`,
  session: (id: string) => `/api/proxy/${shop}/orders/mine/${id}/checkout-session`,
});

const ROUTES = {
  aliexpress: shopRoutes("aliexpress"),
  cj: shopRoutes("cj"),
  shopify: shopRoutes("shopify"),
  sosnet_market: shopRoutes("sosnet-market"),
} as const;

export type CartCheckoutShop = keyof typeof ROUTES;

async function fetchCartQuote(shop: CartCheckoutShop): Promise<CartSectionRead> {
  const res = await fetch(ROUTES[shop].quote);
  if (!res.ok) throw new Error(await friendlyApiError(res));
  return res.json();
}

async function fetchMyCustomer(): Promise<CustomerRead | null> {
  const res = await fetch("/api/proxy/customers/me");
  if (!res.ok) return null;
  return res.json();
}

async function fetchPaymentInfo(): Promise<{ iban: string | null; holder: string; instructions: string | null }> {
  const res = await fetch("/api/proxy/invoice-redemptions/payment-info");
  if (!res.ok) throw new Error("Impossibile caricare le coordinate di pagamento.");
  return res.json();
}

export function CartCheckoutModal({
  shop, onClose,
}: { shop: CartCheckoutShop; onClose: () => void }) {
  const queryClient = useQueryClient();
  const { invalidate: invalidateCart } = useCartActions();
  const { data: marketplaceConfig } = useMarketplaceConfig();
  const [step, setStep] = useState<Step>("checkout");

  const { data: quote, error: quoteError } = useQuery({
    queryKey: ["customer", "cart", "quote", shop],
    queryFn: () => fetchCartQuote(shop),
    retry: false,
  });
  const { data: me } = useQuery({ queryKey: ["customer", "me", "record"], queryFn: fetchMyCustomer });
  const { data: paymentInfo } = useQuery({
    queryKey: ["customer", "payment-info"],
    queryFn: fetchPaymentInfo,
    enabled: step === "bank_instructions",
  });

  // Prefilled from the customer's record; what they type wins.
  const [addressEdits, setAddressEdits] = useState<Partial<DeliveryAddress>>({});
  const address: DeliveryAddress = {
    recipient_name: [me?.first_name, me?.last_name].filter(Boolean).join(" "),
    recipient_phone: me?.phone ?? "",
    address_line1: quote?.default_address.street ?? "",
    address_line2: "",
    city: quote?.default_address.city ?? "",
    province: quote?.default_address.province ?? "",
    postal_code: quote?.default_address.postal_code ?? "",
    ...addressEdits,
  };

  const [useCredit, setUseCredit] = useState(false);
  const [creditAmount, setCreditAmount] = useState("0.00");
  const [chosenMethod, setPaymentMethod] = useState<"BANK_TRANSFER" | "CARD" | null>(null);
  const [otpCode, setOtpCode] = useState("");
  const [otpRequested, setOtpRequested] = useState(false);
  const [otpRequesting, setOtpRequesting] = useState(false);
  const [otpError, setOtpError] = useState<string | null>(null);
  const [submitLoading, setSubmitLoading] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [placedOrder, setPlacedOrder] = useState<AliexpressOrderRead | null>(null);

  const paymentMethod = chosenMethod
    ?? (quote?.bank_transfer_available ? "BANK_TRANSFER" : quote?.card_available ? "CARD" : null);
  // SosnetCash can pay only while the wallet feature is on.
  const walletOn = useFeatures().wallet;
  const maxUsableCents = quote && walletOn ? Math.min(quote.max_creditable_cents, quote.customer_wallet_balance_cents) : 0;
  const creditCents = quote && useCredit
    ? Math.max(0, Math.min(Math.round((parseFloat(creditAmount.replace(",", ".")) || 0) * 100), maxUsableCents))
    : 0;
  const residualCents = quote ? quote.amount_cents - creditCents : 0;
  const needsPaymentMethod = residualCents > 0;
  const discountPercentage = quote?.bank_transfer_discount_percentage ?? 0;
  const bankDiscountCents = bankTransferDiscount(residualCents, discountPercentage);
  const payingByBank = needsPaymentMethod && paymentMethod === "BANK_TRANSFER";
  const totalDueCents = Math.max(residualCents, 0) - (payingByBank ? bankDiscountCents : 0);
  // VAT is added on top of the listed price and comes pre-computed in the
  // server quote's amount_cents; the row is shown as the server sent it.
  const vatPercentage = quote?.vat_percentage ?? marketplaceConfig?.vat_percentage ?? 0;
  const vatCents = quote?.vat_cents ?? 0;
  // What the customer typed, before clamping: used only to tell them they exceeded the maximum.
  const typedCents = Math.max(0, Math.round((parseFloat(creditAmount.replace(",", ".")) || 0) * 100));
  const overTheCap = useCredit && typedCents > maxUsableCents;

  const ready = !!quote && addressComplete(address) && (creditCents === 0 || !!otpCode.trim())
    && (!needsPaymentMethod || !!paymentMethod) && !overTheCap;

  /**
   * Single writer of the amount: always clamped between zero and the spendable
   * maximum, so the field never holds a value the server would refuse. The
   * server checks again.
   */
  function setCredit(cents: number) {
    setCreditAmount((Math.max(0, Math.min(cents, maxUsableCents)) / 100).toFixed(2));
    setOtpRequested(false);
    setOtpCode("");
  }

  function toggleCredit(next: boolean) {
    setUseCredit(next);
    setOtpRequested(false);
    setOtpCode("");
    setCreditAmount(next ? (maxUsableCents / 100).toFixed(2) : "0.00");
  }

  async function handleRequestOtp() {
    setOtpRequesting(true);
    setOtpError(null);
    try {
      const res = await fetch(ROUTES[shop].otp, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ credit_applied_cents: creditCents }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      setOtpRequested(true);
    } catch (err) {
      setOtpError((err as Error).message || "Impossibile inviare il codice.");
    } finally {
      setOtpRequesting(false);
    }
  }

  async function handleConfirm() {
    if (!quote) return;
    setSubmitLoading(true);
    setSubmitError(null);
    try {
      const res = await fetch(ROUTES[shop].create, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          address: {
            recipient_name: address.recipient_name.trim(),
            recipient_phone: address.recipient_phone.trim(),
            address_line1: address.address_line1.trim(),
            address_line2: address.address_line2.trim() || null,
            city: address.city.trim(),
            province: address.province.trim(),
            postal_code: address.postal_code.trim(),
          },
          credit_applied_cents: creditCents,
          otp_code: creditCents > 0 ? otpCode.trim() : null,
          payment_method: needsPaymentMethod ? paymentMethod : "BANK_TRANSFER",
        }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      const order: AliexpressOrderRead = await res.json();
      setPlacedOrder(order);
      // The server already emptied the cart after creating the order.
      await invalidateCart();
      await queryClient.invalidateQueries({ queryKey: ["customer", "wallet"] });
      await queryClient.invalidateQueries({ queryKey: ["wallet"] });
      await queryClient.invalidateQueries({ queryKey: ["customer", "orders"] });
      if (order.status === "PAID") return setStep("success");
      if (order.payment_method === "CARD") {
        const returnUrl = window.location.href;
        const sessionRes = await fetch(
          `${ROUTES[shop].session(order.id)}?success_url=${encodeURIComponent(returnUrl)}&cancel_url=${encodeURIComponent(returnUrl)}`,
          { method: "POST" },
        );
        if (!sessionRes.ok) throw new Error(await friendlyApiError(sessionRes));
        const { checkout_url } = await sessionRes.json();
        window.open(checkout_url, "_blank", "noopener,noreferrer");
        return setStep("card_redirect");
      }
      setStep("bank_instructions");
    } catch (err) {
      setSubmitError((err as Error).message || "Impossibile completare l'acquisto.");
    } finally {
      setSubmitLoading(false);
    }
  }

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-black/70 light:bg-surface-900/40 backdrop-blur-sm animate-fade-in">
      <div className="w-full max-w-2xl panel panel-hover rounded-2xl border-white/10 light:border-surface-300 bg-surface-950 light:bg-white pop max-h-[92vh] overflow-y-auto">
        <div className="sticky top-0 z-10 flex items-center justify-between gap-3 px-6 py-4 border-b border-white/5 light:border-surface-200 bg-surface-950/95 light:bg-white/95 backdrop-blur">
          <h3 className="text-base font-bold text-white light:text-surface-900">Completa l&apos;acquisto</h3>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-white/10 light:hover:bg-surface-900/10 text-surface-400 transition cursor-pointer" aria-label="Chiudi">
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="p-6 space-y-4">
          {quoteError && (
            <div className="p-3 rounded-lg bg-danger-500/10 border border-danger-500/20 text-danger-400 text-xs">
              {(quoteError as Error).message}
            </div>
          )}
          {!quote && !quoteError && <p className="py-10 text-center text-sm text-surface-500">Calcolo in corso…</p>}

          {step === "checkout" && quote && (
            <>
              <div className="rounded-xl border border-white/10 light:border-surface-200 divide-y divide-white/5 light:divide-surface-200">
                {quote.items.map((line) => (
                  <div key={line.cart_item_id} className="flex items-center gap-3 p-3">
                    <ProductThumbnail imageUrl={line.image_url} alt={line.product_name} className="w-11 h-11 rounded-lg shrink-0 object-cover" />
                    <div className="min-w-0 flex-1">
                      <p className="text-xs font-semibold text-white light:text-surface-900 truncate">{line.product_name}</p>
                      <p className="text-[11px] text-surface-500 truncate">
                        {line.variant_label ? `${line.variant_label} · ` : ""}{line.quantity} {line.quantity === 1 ? "pezzo" : "pezzi"}
                      </p>
                      {/* Each product's SosnetCash share; the order cap is their sum. */}
                      {walletOn && !!line.max_creditable_cents && (
                        <p className="text-[11px] text-success-400/80 truncate">
                          fino a {sosnetCash(line.max_creditable_cents)} ({line.credit_discount_percentage}%)
                        </p>
                      )}
                    </div>
                    <p className="text-xs font-bold text-white light:text-surface-900 tabular-nums">{euro(line.line_total_cents)}</p>
                  </div>
                ))}
              </div>

              <Section n={1} title="Dove lo spediamo?" done={addressComplete(address)}>
                <AddressFields address={address} onChange={setAddressEdits} />
                <p className="text-[11px] text-surface-500">
                  Spedizione in Italia{quote.shipping_days ? ` · consegna stimata in ${quote.shipping_days} giorni lavorativi` : ""}.
                  {" "}Un indirizzo solo per tutti gli articoli di questo ordine.
                </p>
              </Section>

              {quote.max_creditable_cents > 0 && maxUsableCents > 0 && (
                <Section n={2} title="Vuoi usare i tuoi SosnetCash?" done={creditCents > 0 && !!otpCode.trim()}>
                  <div className="flex flex-wrap items-center gap-2">
                    <button
                      type="button"
                      onClick={() => toggleCredit(!useCredit)}
                      className={`px-3 py-1.5 rounded-lg text-xs font-semibold border transition cursor-pointer ${
                        useCredit
                          ? "bg-brand-600 border-brand-600 text-white"
                          : "bg-white/5 light:bg-surface-900/5 border-white/10 light:border-surface-300 text-surface-300 light:text-surface-600"
                      }`}
                    >
                      {useCredit ? "Sì, uso i SosnetCash" : "Usa i SosnetCash"}
                    </button>
                    {/* Two limits (what the products allow, what the wallet holds): show both and
                       say which one applies, so the per-line shares above add up. */}
                    <span className="block w-full text-[11px] text-surface-500">
                      I prodotti nel carrello concedono fino a{" "}
                      <strong className="text-surface-300 light:text-surface-600">{sosnetCash(quote.max_creditable_cents)}</strong>
                      {" "}— la somma di quanto concede ciascuno, per la quantità che hai scelto.
                    </span>
                    {quote.customer_wallet_balance_cents < quote.max_creditable_cents ? (
                      <div className="w-full flex items-start gap-2.5 p-3 rounded-xl bg-warn-500/10 border border-warn-500/30">
                        <svg className="w-5 h-5 text-warn-400 shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v4m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
                        </svg>
                        <div className="text-xs text-warn-200 light:text-warn-700 leading-relaxed">
                          <p className="font-bold text-warn-300 light:text-warn-800">
                            Puoi usarne al massimo {sosnetCash(maxUsableCents)}
                          </p>
                          <p className="mt-0.5">
                            I prodotti ne concederebbero {sosnetCash(quote.max_creditable_cents)}, ma nel tuo wallet
                            ce ne sono {sosnetCash(quote.customer_wallet_balance_cents)}. Il resto lo paghi con bonifico o carta.
                          </p>
                        </div>
                      </div>
                    ) : (
                      <span className="block w-full text-[11px] text-surface-500">
                        Saldo {sosnetCash(quote.customer_wallet_balance_cents)}: puoi usarli tutti fino a {sosnetCash(maxUsableCents)}.
                      </span>
                    )}
                  </div>
                  {useCredit && (
                    <div className="space-y-3">
                      <div className="flex flex-wrap items-center gap-2">
                        {[0.25, 0.5, 1].map((f) => (
                          <button
                            key={f}
                            type="button"
                            onClick={() => setCredit(Math.round(maxUsableCents * f))}
                            className="px-2.5 py-1 rounded-lg text-[11px] font-semibold border border-white/10 light:border-surface-300 text-surface-300 light:text-surface-600 hover:bg-white/10 cursor-pointer"
                          >
                            {f === 1 ? "Massimo" : `${f * 100}%`}
                          </button>
                        ))}
                        <input
                          inputMode="decimal"
                          value={creditAmount}
                          onChange={(e) => { setCreditAmount(e.target.value); setOtpRequested(false); setOtpCode(""); }}
                          className={`w-28 rounded-lg field px-3 py-1.5 text-sm ${
                            overTheCap ? "border-danger-500 text-danger-300" : ""
                          }`}
                        />
                        <span className="text-xs text-surface-500">SosnetCash</span>
                      </div>
                      {/* Block rather than silently correct: the code button stays disabled until
                         the amount is fixed. The server checks again. */}
                      {overTheCap && (
                        <div className="flex items-start gap-2 p-3 rounded-xl bg-danger-500/10 border border-danger-500/30">
                          <svg className="w-4 h-4 text-danger-400 shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v4m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
                          </svg>
                          <div className="text-xs text-danger-300 leading-relaxed">
                            <p className="font-bold">Hai scritto {sosnetCash(typedCents)}, ma non puoi usarne così tanti.</p>
                            <p className="mt-0.5">
                              {quote.customer_wallet_balance_cents < quote.max_creditable_cents
                                ? `Nel tuo wallet ci sono ${sosnetCash(quote.customer_wallet_balance_cents)}.`
                                : `Su questo ordine il massimo è ${sosnetCash(quote.max_creditable_cents)}.`}{" "}
                              <button
                                type="button"
                                onClick={() => setCredit(maxUsableCents)}
                                className="font-bold underline underline-offset-2 hover:text-danger-200 cursor-pointer"
                              >
                                Usa il massimo ({sosnetCash(maxUsableCents)})
                              </button>
                            </p>
                          </div>
                        </div>
                      )}
                      {creditCents > 0 && !overTheCap && (
                        !otpRequested ? (
                          <button
                            type="button"
                            onClick={handleRequestOtp}
                            disabled={otpRequesting}
                            className="px-4 py-2 rounded-lg bg-brand-600/15 hover:bg-brand-600/25 border border-brand-500/30 text-xs font-semibold text-brand-400 transition cursor-pointer disabled:opacity-50"
                          >
                            {otpRequesting ? "Invio in corso…" : "Conferma con il codice via email"}
                          </button>
                        ) : (
                          <div className="flex flex-wrap items-center gap-2">
                            <input
                              inputMode="numeric"
                              autoFocus
                              value={otpCode}
                              onChange={(e) => setOtpCode(e.target.value)}
                              placeholder="Codice ricevuto via email"
                              className="w-full max-w-[200px] rounded-lg field px-3 py-2 text-sm font-mono tracking-wider"
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
                        )
                      )}
                      {otpError && <p className="text-[11px] text-danger-400">{otpError}</p>}
                    </div>
                  )}
                </Section>
              )}

              {needsPaymentMethod && (
                <Section n={quote.max_creditable_cents > 0 && maxUsableCents > 0 ? 3 : 2} title="Come vuoi pagare?" done={!!paymentMethod}>
                  <div className="flex flex-wrap gap-2">
                    {quote.bank_transfer_available && (
                      <button
                        onClick={() => setPaymentMethod("BANK_TRANSFER")}
                        className={`flex-1 min-w-[180px] px-4 py-3 rounded-xl border text-xs font-semibold transition cursor-pointer ${
                          paymentMethod === "BANK_TRANSFER"
                            ? "border-brand-500 bg-brand-500/10 text-white light:text-surface-900"
                            : "border-white/10 light:border-surface-200 text-surface-400 light:text-surface-500"
                        }`}
                      >
                        Bonifico istantaneo · {euro(residualCents - bankDiscountCents)}
                        {bankDiscountCents > 0 && (
                          <span className="block text-[10px] font-bold text-success-400">Risparmi {euro(bankDiscountCents)}</span>
                        )}
                      </button>
                    )}
                    {quote.card_available && (
                      <button
                        onClick={() => setPaymentMethod("CARD")}
                        className={`flex-1 min-w-[180px] px-4 py-3 rounded-xl border text-xs font-semibold transition cursor-pointer ${
                          paymentMethod === "CARD"
                            ? "border-brand-500 bg-brand-500/10 text-white light:text-surface-900"
                            : "border-white/10 light:border-surface-200 text-surface-400 light:text-surface-500"
                        }`}
                      >
                        Carta · {euro(residualCents)}
                      </button>
                    )}
                  </div>
                  {!quote.bank_transfer_available && !quote.card_available && (
                    <p className="text-[11px] text-danger-400">
                      Nessun metodo di pagamento è configurato: contatta l&apos;amministrazione.
                    </p>
                  )}
                </Section>
              )}

              <div className="p-4 rounded-xl bg-gradient-to-br from-brand-600/10 to-accent-500/5 border border-brand-500/20 space-y-1.5 text-xs">
                <div className="flex justify-between text-surface-400 light:text-surface-500">
                  <span>Articoli ({quote.items.length})</span><span className="tabular-nums">{euro(quote.items_cents)}</span>
                </div>
                <div className="flex justify-between text-surface-400 light:text-surface-500">
                  <span>Spedizione</span>
                  <span className="tabular-nums">
                    {quote.shipping_included || quote.shipping_cents === 0 ? "Inclusa" : euro(quote.shipping_cents)}
                  </span>
                </div>
                {creditCents > 0 && (
                  <div className="flex justify-between text-success-400">
                    <span>SosnetCash usati</span><span>-{sosnetCash(creditCents)}</span>
                  </div>
                )}
                {payingByBank && bankDiscountCents > 0 && (
                  <div className="flex justify-between text-success-400">
                    <span>Sconto pagamento con bonifico (-{discountPercentage}%)</span>
                    <span>-{euro(bankDiscountCents)}</span>
                  </div>
                )}
                {/* VAT sits in the list above the total, labelled as already included, since
                   with SosnetCash it can exceed the amount left to pay. */}
                {vatCents > 0 && (
                  <div className="flex justify-between text-surface-400 light:text-surface-500">
                    <span>{vatLineLabel(vatPercentage)}</span><span className="tabular-nums">{euro(vatCents)}</span>
                  </div>
                )}
                <div className="flex items-center justify-between pt-1.5 border-t border-white/10 light:border-surface-300">
                  <span className="text-sm font-bold text-white light:text-surface-900">Totale da pagare</span>
                  <span className={`text-xl font-extrabold tabular-nums ${residualCents > 0 ? "text-brand-400" : "text-success-400"}`}>
                    {euro(totalDueCents)}
                  </span>
                </div>
              </div>

              {submitError && (
                <div className="p-3 rounded-lg bg-danger-500/10 border border-danger-500/20 text-danger-400 text-xs">{submitError}</div>
              )}

              <button
                onClick={handleConfirm}
                disabled={!ready || submitLoading}
                className="w-full px-4 py-3 rounded-xl bg-brand-600 hover:bg-brand-500 disabled:opacity-40 disabled:cursor-not-allowed text-sm font-semibold text-white transition cursor-pointer"
              >
                {submitLoading ? "Elaborazione…" : residualCents > 0 ? "Conferma e paga" : "Conferma ordine"}
              </button>
            </>
          )}

          {step === "success" && placedOrder && (
            <div className="text-center py-8 space-y-3">
              <p className="text-4xl">🎉</p>
              <p className="text-sm text-surface-300 light:text-surface-600">
                Ordine confermato, pagato con i tuoi SosnetCash. Ti avvisiamo appena parte: lo segui da &ldquo;I miei Ordini&rdquo;.
              </p>
              <button onClick={onClose} className="px-4 py-2 rounded-xl bg-brand-600 hover:bg-brand-500 text-xs font-semibold text-white transition cursor-pointer">Chiudi</button>
            </div>
          )}

          {step === "card_redirect" && placedOrder && (
            <div className="text-center py-8 space-y-3">
              <p className="text-sm text-surface-300 light:text-surface-600">
                Abbiamo aperto il pagamento con carta in una nuova scheda: <strong className="text-brand-400">{euro(placedOrder.amount_due_cents)}</strong>.
              </p>
              <p className="text-xs text-surface-500">L&apos;ordine è anche in &ldquo;I miei Ordini&rdquo;, dove puoi pagarlo e seguirne la spedizione.</p>
              <button onClick={onClose} className="px-4 py-2 rounded-xl bg-brand-600 hover:bg-brand-500 text-xs font-semibold text-white transition cursor-pointer">Chiudi</button>
            </div>
          )}

          {step === "bank_instructions" && placedOrder && (
            <div className="space-y-3">
              <p className="text-sm text-surface-300 light:text-surface-600">
                Ordine creato. Paga <strong className="text-brand-400">{euro(placedOrder.amount_due_cents)}</strong> con bonifico: lo spediamo appena riceviamo il pagamento.
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
                <p className="pt-1"><span className="text-surface-500">Causale:</span> <span className="font-mono text-brand-400">Ordine {placedOrder.id.slice(0, 8).toUpperCase()}</span></p>
              </div>
              <button onClick={onClose} className="w-full px-4 py-2 rounded-xl bg-brand-600 hover:bg-brand-500 text-xs font-semibold text-white transition cursor-pointer">Ho capito</button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
