"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Pagination, usePagination } from "@/components/pagination";
import { SosnetCashAmount } from "@/components/sosnet-cash-amount";
import { Chip, Identity, Stack } from "@/components/ui/data-cells";
import { friendlyApiError } from "@/lib/api-error";
import type { WalletRead, WalletTransactionRead } from "@/lib/types";

const TYPE_LABELS: Record<string, string> = {
  ADMIN_CREDIT: "Ricarica/Cashback",
  TRANSFER: "Trasferimento",
  PURCHASE_DEBIT: "Pagamento ordine (crediti)",
  REVERSAL: "Storno",
};

// Finer labels than TYPE_LABELS: tells a manual top-up apart from the
// base/bonus lines written by redemptions and order cashback
// (orders/service.py::_credit_order_cashback).
const SOURCE_LABELS: Record<string, string> = {
  MANUAL_ADMIN: "Ricarica manuale",
  WELCOME_BONUS: "Omaggio di benvenuto",
  INVOICE_REDEMPTION_BASE: "Riscatto fattura",
  INVOICE_REDEMPTION_BONUS: "Bonus 5% riscatto fattura",
  ORDER_CASHBACK_BASE: "Cashback ordine",
  ORDER_CASHBACK_BONUS: "Bonus 5% cashback ordine",
  // Automatic credit on a paid contract; not a 5% bonus rule.
  CONTRACT_CASHBACK: "Cashback SOSNET",
};

function transactionLabel(t: { type: string; source: string | null }): string {
  const sourceLabel = t.source ? SOURCE_LABELS[t.source] : undefined;
  return sourceLabel ?? TYPE_LABELS[t.type] ?? t.type;
}

function shortCode(id: string): string {
  return id.slice(0, 8).toUpperCase();
}

/** Chip linking a cashback/bonus credit to its order or redemption
    (wallets/schemas.py::WalletTransactionRead), in the customer or promoter
    area this panel is mounted in. */
function referenceLink(t: WalletTransactionRead): { label: string; href: string } | null {
  const basePath = typeof window !== "undefined" && window.location.pathname.startsWith("/promoter") ? "/promoter" : "/customer";
  // Every order reference column opens the same unified "I miei Ordini" list.
  const orderId =
    t.reference_order_id ?? t.reference_imported_order_id ?? t.reference_cj_order_id ?? t.reference_shopify_order_id
    ?? t.reference_aliexpress_order_id;
  if (orderId) {
    return { label: `Ordine #${shortCode(orderId)}`, href: `${basePath}?tab=orders` };
  }
  if (t.reference_invoice_redemption_id) {
    return { label: `Riscatto #${shortCode(t.reference_invoice_redemption_id)}`, href: `${basePath}?tab=cashback` };
  }
  return null;
}

// Wallet amounts are SosnetCash, never EUR (docs/business-rules.md, "Internal
// wallet"). Real-money payments use euro() elsewhere.
function sosnetCash(cents: number): string {
  return `${(cents / 100).toLocaleString("it-IT", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} SosnetCash`;
}

async function fetchMyWallet(): Promise<WalletRead> {
  const res = await fetch("/api/proxy/wallets/me");
  if (!res.ok) throw new Error("Impossibile caricare il wallet.");
  return res.json();
}

async function fetchMyTransactions(): Promise<WalletTransactionRead[]> {
  const res = await fetch("/api/proxy/wallets/me/transactions");
  if (!res.ok) throw new Error("Impossibile caricare le transazioni.");
  return res.json();
}

export function WalletPanel() {
  const queryClient = useQueryClient();
  const [toAddress, setToAddress] = useState("");
  const [amount, setAmount] = useState("");
  const [note, setNote] = useState("");
  const [copied, setCopied] = useState(false);
  const [sendLoading, setSendLoading] = useState(false);
  const [sendError, setSendError] = useState<string | null>(null);
  const [sendSuccess, setSendSuccess] = useState(false);

  const { data: wallet, error: walletError } = useQuery({
    queryKey: ["wallet", "me"],
    queryFn: fetchMyWallet,
  });
  const { data: transactions, error: transactionsError } = useQuery({
    queryKey: ["wallet", "me", "transactions"],
    queryFn: fetchMyTransactions,
  });

  const pagination = usePagination(transactions ?? []);

  async function handleCopyAddress() {
    if (!wallet) return;
    try {
      await navigator.clipboard.writeText(wallet.address);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard access can fail (permissions, non-HTTPS context) -- the
      // address is still visible on screen to copy manually, so this is a
      // silent no-op, not an error worth surfacing.
    }
  }

  async function handleSend(e: React.FormEvent) {
    e.preventDefault();
    const amountCents = Math.round(parseFloat(amount.replace(",", ".")) * 100);
    if (!Number.isFinite(amountCents) || amountCents <= 0) {
      setSendError("Inserisci un importo valido.");
      return;
    }
    setSendLoading(true);
    setSendError(null);
    try {
      const res = await fetch("/api/proxy/wallets/transfer", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          to_address: toAddress.trim(),
          amount_cents: amountCents,
          note: note || null,
          idempotency_key: crypto.randomUUID(),
        }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      setSendSuccess(true);
      setToAddress("");
      setAmount("");
      setNote("");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["wallet", "me"] }),
        queryClient.invalidateQueries({ queryKey: ["wallet", "me", "transactions"] }),
      ]);
      setTimeout(() => setSendSuccess(false), 3000);
    } catch (err: any) {
      setSendError(err.message || "Impossibile inviare il pagamento.");
    } finally {
      setSendLoading(false);
    }
  }

  if (walletError) {
    return <p className="text-sm text-danger-400">Impossibile caricare il wallet.</p>;
  }

  return (
    <div className="space-y-6">
      {/* Balance + address */}
      <div className="panel relative overflow-hidden rounded-3xl p-6 sm:p-8">
        <span className="pointer-events-none absolute -right-10 -top-10 h-40 w-40 rounded-full bg-gradient-to-br from-brand-400/40 to-accent-400/10 blur-3xl" />
        {wallet === undefined ? (
          <p className="text-sm text-surface-400">Caricamento...</p>
        ) : (
          <div className="relative flex flex-col gap-6 sm:flex-row sm:items-end sm:justify-between">
            <div className="rise">
              <p className="kpi-label">Saldo disponibile</p>
              <p className="kpi-value mt-3 text-gradient">{sosnetCash(wallet.balance_cents)}</p>
            </div>
            <div className="min-w-0">
              <p className="kpi-label mb-2">Il tuo indirizzo wallet</p>
              <button
                onClick={handleCopyAddress}
                title="Copia indirizzo"
                className="flex max-w-full items-center gap-2 rounded-2xl border border-white/10 bg-white/5 px-4 py-2.5 font-mono text-xs text-surface-200 transition hover:bg-white/10 cursor-pointer"
              >
                <span className="truncate">{wallet.address}</span>
                <svg className="w-3.5 h-3.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  {copied ? (
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  ) : (
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                  )}
                </svg>
              </button>
              {copied && <p className="pop mt-1.5 text-[11px] text-success-400">Indirizzo copiato</p>}
            </div>
          </div>
        )}
      </div>

      {/* Transfer form, only when an admin enabled can_transfer */}
      {wallet && !wallet.can_transfer ? (
        <div className="panel rounded-3xl p-6 sm:p-8">
          <p className="kpi-label">Trasferimenti</p>
          <h3 className="mt-1 text-xl font-black tracking-tight text-white">Invia denaro</h3>
          <p className="mt-2 text-sm text-surface-400">L&apos;invio di bonifici wallet non è abilitato per il tuo account.</p>
        </div>
      ) : wallet ? (
      <div className="panel rounded-3xl p-6 sm:p-8">
        <p className="kpi-label">Trasferimenti</p>
        <h3 className="mt-1 mb-5 text-xl font-black tracking-tight text-white">Invia denaro</h3>
        <form onSubmit={handleSend} className="grid grid-cols-1 sm:grid-cols-[2fr_1fr_2fr_auto] gap-3 items-end">
          <div className="space-y-1">
            <label className="kpi-label block">Indirizzo destinatario</label>
            <input
              required
              value={toAddress}
              onChange={(e) => setToAddress(e.target.value)}
              placeholder="0x..."
              className="w-full rounded-xl field px-3 py-2 text-sm font-mono focus:border-brand-500"
            />
          </div>
          <div className="space-y-1">
            <label className="kpi-label block">Importo (SosnetCash)</label>
            <input
              required
              inputMode="decimal"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              placeholder="0,00"
              className="w-full rounded-xl field px-3 py-2 text-sm focus:border-brand-500"
            />
          </div>
          <div className="space-y-1">
            <label className="kpi-label block">Nota (opzionale)</label>
            <input
              value={note}
              onChange={(e) => setNote(e.target.value)}
              className="w-full rounded-xl field px-3 py-2 text-sm focus:border-brand-500"
            />
          </div>
          <button
            type="submit"
            disabled={sendLoading}
            className="act act-primary justify-center whitespace-nowrap px-5 py-2.5 disabled:opacity-50"
          >
            {sendLoading ? "Invio..." : "Invia"}
          </button>
        </form>
        {sendError && (
          <div className="pop mt-4 rounded-2xl border border-danger-500/20 bg-danger-500/10 p-3 text-xs text-danger-400">{sendError}</div>
        )}
        {sendSuccess && (
          <div className="pop mt-4 rounded-2xl border border-success-500/20 bg-success-500/10 p-3 text-xs text-success-400">Pagamento inviato con successo.</div>
        )}
      </div>
      ) : null}

      {/* Transaction history */}
      <div className="panel rounded-3xl overflow-hidden">
        <div className="px-6 pt-6 pb-3 sm:px-8">
          <p className="kpi-label">Movimenti</p>
          <h3 className="mt-1 text-xl font-black tracking-tight text-white">Storico transazioni</h3>
        </div>
        {transactionsError && <p className="px-6 pb-3 text-sm text-danger-400 sm:px-8">Impossibile caricare le transazioni.</p>}
        {transactions === undefined ? (
          <p className="px-6 py-10 text-center text-sm text-surface-400">Caricamento...</p>
        ) : transactions.length === 0 ? (
          <div className="flex flex-col items-center gap-3 px-6 py-12 text-center">
            <span className="float-soft flex h-12 w-12 items-center justify-center rounded-2xl bg-brand-500/15 text-brand-300">
              <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a2 2 0 00-2-2H7a2 2 0 00-2 2m16 0v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6m16 0V9a2 2 0 00-2-2H5a2 2 0 00-2 2v3m16 0h-4a1 1 0 00-1 1v0a1 1 0 001 1h4" />
              </svg>
            </span>
            <p className="text-sm text-surface-300">Nessuna transazione, il tuo wallet è ancora intatto.</p>
          </div>
        ) : (
          <div className="overflow-x-auto px-2 sm:px-4">
            <table className="w-full border-collapse text-left text-xs">
              <thead>
                <tr>
                  <th className="px-4 py-3">Movimento</th>
                  <th className="px-4 py-3">Collegato a</th>
                  <th className="px-4 py-3">Quando</th>
                  <th className="px-4 py-3 text-right">Valore</th>
                </tr>
              </thead>
              <tbody>
                {pagination.pageItems.map((t) => {
                  const isOutgoing = t.from_wallet_id === wallet?.id;
                  const ref = referenceLink(t);
                  const counterpart = isOutgoing ? (t.to_display_name ?? "Sistema") : (t.from_display_name ?? "Sistema");
                  const when = new Date(t.created_at);
                  return (
                    <tr key={t.id}>
                      <td className="px-4 py-3">
                        <Identity
                          name={transactionLabel(t)}
                          detail={`${isOutgoing ? "Verso" : "Da"} ${counterpart}`}
                          icon={
                            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d={isOutgoing ? "M7 17L17 7M17 7H8M17 7v9" : "M17 7L7 17M7 17h9M7 17V8"} />
                            </svg>
                          }
                        />
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex min-w-0 flex-col items-start gap-1">
                          {ref ? (
                            <a href={ref.href} className="act">
                              {ref.label}
                              <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                              </svg>
                            </a>
                          ) : (
                            !t.note && <span className="text-surface-500">—</span>
                          )}
                          {t.note && <span className="max-w-[260px] truncate text-[11px] text-surface-400" title={t.note}>“{t.note}”</span>}
                        </div>
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap">
                        <Stack
                          title={when.toLocaleDateString("it-IT", { day: "2-digit", month: "short", year: "numeric" })}
                          detail={when.toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" })}
                        />
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex flex-col items-end gap-1">
                          <span className={`text-[15px] font-black tabular-nums ${isOutgoing ? "text-danger-400" : "text-success-400"}`}>
                            <SosnetCashAmount cents={t.amount_cents} sign={isOutgoing ? "-" : "+"} />
                          </span>
                          <Chip tone={isOutgoing ? "bad" : "ok"}>{isOutgoing ? "Uscita" : "Entrata"}</Chip>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
        <div className="px-6 pb-5 sm:px-8">
          <Pagination {...pagination} label="transazioni" />
        </div>
      </div>
    </div>
  );
}
