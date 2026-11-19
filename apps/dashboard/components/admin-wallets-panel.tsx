"use client";

import { Fragment, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import type { WalletAdminListItemRead, WalletTransactionRead } from "@/lib/types";
import { friendlyApiError } from "@/lib/api-error";
import { downloadCsv } from "@/lib/csv-export";
import { Pagination, usePagination } from "@/components/pagination";
import { SosnetCashAmount } from "@/components/sosnet-cash-amount";
import { Chip, type ChipTone, Figure, IdTag, Identity, KpiTile, Orb, RowActions, Stack } from "@/components/ui/data-cells";

const TYPE_LABELS: Record<string, string> = {
  ADMIN_CREDIT: "Ricarica/Cashback",
  TRANSFER: "Trasferimento",
  PURCHASE_DEBIT: "Pagamento ordine (crediti)",
  REVERSAL: "Storno",
};

const TYPE_TONES: Record<string, ChipTone> = {
  ADMIN_CREDIT: "ok",
  TRANSFER: "info",
  PURCHASE_DEBIT: "warn",
  REVERSAL: "bad",
};

const TYPE_FILTERS: { value: string; label: string }[] = [
  { value: "ALL", label: "Tutti i tipi" },
  { value: "ADMIN_CREDIT", label: "Solo ricariche/cashback" },
  { value: "TRANSFER", label: "Solo trasferimenti" },
  { value: "REVERSAL", label: "Solo storni" },
];

function shortDate(iso: string): string {
  return new Date(iso).toLocaleDateString("it-IT", { day: "2-digit", month: "short", year: "numeric" });
}

// Finer label than TYPE_LABELS: tells a plain admin top-up apart from the two
// lines a partner-invoice redemption writes, without reading the note.
const SOURCE_LABELS: Record<string, string> = {
  MANUAL_ADMIN: "Ricarica manuale",
  WELCOME_BONUS: "Omaggio di benvenuto",
  INVOICE_REDEMPTION_BASE: "Riscatto fattura",
  INVOICE_REDEMPTION_BONUS: "Bonus 5% riscatto fattura",
  ORDER_CASHBACK_BASE: "Cashback ordine",
  ORDER_CASHBACK_BONUS: "Bonus 5% cashback ordine",
  // Automatic, surcharge-free credit on a paid SOSNET contract (a different rule
  // from the two 5% ones above).
  CONTRACT_CASHBACK: "Cashback SOSNET",
};

function transactionLabel(t: { type: string; source: string | null }): string {
  const sourceLabel = t.source ? SOURCE_LABELS[t.source] : undefined;
  return sourceLabel ?? TYPE_LABELS[t.type] ?? t.type;
}

// The wallet holds SosnetCash, never EUR (same helper as wallet-panel.tsx).
function sosnetCash(cents: number): string {
  return `${(cents / 100).toLocaleString("it-IT", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} SosnetCash`;
}

async function fetchWallets(): Promise<WalletAdminListItemRead[]> {
  const res = await fetch("/api/proxy/wallets/admin");
  if (!res.ok) throw new Error("Impossibile caricare i wallet.");
  return res.json();
}

async function fetchTransactions(type?: string): Promise<WalletTransactionRead[]> {
  const search = new URLSearchParams();
  if (type && type !== "ALL") search.set("type", type);
  const qs = search.toString();
  const res = await fetch(`/api/proxy/wallets/admin/transactions${qs ? `?${qs}` : ""}`);
  if (!res.ok) throw new Error("Impossibile caricare le transazioni.");
  return res.json();
}

interface AdminWalletsPanelProps {
  /**
   * Only SUPER_ADMIN may credit ("Ricarica"); the form is hidden otherwise. UI
   * only: the `wallet.credit` permission on POST /wallets/admin/topup
   * (wallets/router.py) is the real check.
   */
  isSuperAdmin?: boolean;
}

export function AdminWalletsPanel({ isSuperAdmin = false }: AdminWalletsPanelProps = {}) {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState("ALL");
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [reversingId, setReversingId] = useState<string | null>(null);
  const [reverseError, setReverseError] = useState<string | null>(null);
  const [topUpForUserId, setTopUpForUserId] = useState<string | null>(null);
  const [topUpAmount, setTopUpAmount] = useState("");
  const [topUpNote, setTopUpNote] = useState("");
  const [topUpLoading, setTopUpLoading] = useState(false);
  const [topUpError, setTopUpError] = useState<string | null>(null);
  const topUpKeyRef = useRef<string>("");

  const { data: wallets, error: walletsError } = useQuery({
    queryKey: ["admin", "wallets", "all"],
    queryFn: fetchWallets,
  });
  const { data: transactions, error: transactionsError, isLoading } = useQuery({
    queryKey: ["admin", "wallets", "transactions", typeFilter],
    queryFn: () => fetchTransactions(typeFilter),
  });

  const filteredWallets = (wallets ?? []).filter(
    (w) =>
      w.owner_display_name.toLowerCase().includes(search.toLowerCase()) ||
      w.owner_email.toLowerCase().includes(search.toLowerCase()) ||
      w.address.toLowerCase().includes(search.toLowerCase())
  );

  // Two lists with independent paging; CSV exports always use the full arrays.
  const walletsPagination = usePagination(filteredWallets);
  const transactionsPagination = usePagination(transactions ?? []);

  const totalBalance = (wallets ?? []).reduce((sum, w) => sum + w.balance_cents, 0);
  const totalCredited = (transactions ?? [])
    .filter((t) => t.type === "ADMIN_CREDIT")
    .reduce((sum, t) => sum + t.amount_cents, 0);

  async function handleReverse(transactionId: string) {
    const reason = window.prompt("Motivo dello storno:");
    if (!reason) return;
    setReversingId(transactionId);
    setReverseError(null);
    try {
      const res = await fetch(`/api/proxy/wallets/admin/transactions/${transactionId}/reverse`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reason, idempotency_key: crypto.randomUUID() }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      await queryClient.invalidateQueries({ queryKey: ["admin", "wallets"] });
    } catch (err: any) {
      setReverseError(err.message || "Impossibile stornare la transazione.");
    } finally {
      setReversingId(null);
    }
  }

  function openTopUp(userId: string) {
    setTopUpForUserId(topUpForUserId === userId ? null : userId);
    setTopUpAmount("");
    setTopUpNote("");
    setTopUpError(null);
    // One idempotency key per top-up being composed, not per click. The backend
    // returns the original transaction for a repeated key, so retrying after an
    // error (e.g. the confirmation email failing after the credit was committed)
    // never credits twice.
    topUpKeyRef.current = crypto.randomUUID();
  }

  async function handleTopUp(e: React.FormEvent, userId: string) {
    e.preventDefault();
    const amountCents = Math.round(parseFloat(topUpAmount.replace(",", ".")) * 100);
    if (!Number.isFinite(amountCents) || amountCents <= 0) {
      setTopUpError("Inserisci un importo valido.");
      return;
    }
    setTopUpLoading(true);
    setTopUpError(null);
    try {
      const res = await fetch("/api/proxy/wallets/admin/topup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_id: userId,
          amount_cents: amountCents,
          note: topUpNote || null,
          idempotency_key: topUpKeyRef.current,
        }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      setTopUpForUserId(null);
      await queryClient.invalidateQueries({ queryKey: ["admin", "wallets"] });
    } catch (err: any) {
      setTopUpError(err.message || "Impossibile ricaricare il wallet.");
    } finally {
      setTopUpLoading(false);
    }
  }

  function handleExportCsv() {
    downloadCsv(
      `wallet_transazioni_${new Date().toISOString().slice(0, 10)}`,
      ["ID", "Tipo", "Da", "A", "Importo (SosnetCash)", "Nota", "Data"],
      (transactions ?? []).map((t) => [
        t.id, transactionLabel(t), t.from_display_name ?? "Sistema", t.to_display_name ?? "Sistema",
        (t.amount_cents / 100).toFixed(2), t.note ?? "", t.created_at,
      ])
    );
  }

  const maxBalance = (wallets ?? []).reduce((m, w) => Math.max(m, w.balance_cents), 0);

  return (
    <div className="space-y-6">
      {/* KPI */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <KpiTile label="Saldo totale wallet" value={sosnetCash(totalBalance)} hint={`${(wallets ?? []).length} wallet`} />
        <KpiTile label="Totale ricaricato" value={sosnetCash(totalCredited)} hint="nel filtro corrente" />
      </div>

      {/* Wallet balances */}
      <section className="panel rounded-3xl p-6">
        <div className="mb-4 flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="kpi-label">Wallet</p>
            <h3 className="mt-1 text-xl font-black tracking-tight text-white">Saldi per utente</h3>
          </div>
          <input
            type="text"
            placeholder="Cerca per nome, email o indirizzo..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="field w-full max-w-xs rounded-xl px-3 py-2 text-xs"
          />
        </div>
        {walletsError && <p className="pb-3 text-sm text-danger-300">Impossibile caricare i wallet.</p>}
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr>
                <th className="px-4 py-3">Titolare</th>
                <th className="px-4 py-3">Profilo</th>
                <th className="px-4 py-3">Indirizzo wallet</th>
                <th className="px-4 py-3 text-right">Disponibile</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {wallets === undefined ? (
                <tr><td colSpan={5} className="px-4 py-10 text-center text-surface-400">Caricamento...</td></tr>
              ) : filteredWallets.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-4 py-10">
                    <div className="flex flex-col items-center gap-2 text-center text-surface-400">
                      <Orb name="wallet" icon={<span className="text-sm">∅</span>} />
                      <span className="text-sm">Nessun wallet trovato.</span>
                    </div>
                  </td>
                </tr>
              ) : (
                walletsPagination.pageItems.map((w) => (
                  <Fragment key={w.id}>
                    <tr>
                      <td className="px-4 py-3">
                        <Identity name={w.owner_display_name} detail={w.owner_email} />
                      </td>
                      <td className="px-4 py-3">
                        {w.owner_roles.length > 0 ? (
                          <div className="flex flex-wrap gap-1">
                            {w.owner_roles.map((r) => <Chip key={r} tone="muted">{r}</Chip>)}
                          </div>
                        ) : (
                          <span className="text-surface-400">—</span>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        <span className="tag-id max-w-[180px] truncate" title={w.address}>{w.address}</span>
                      </td>
                      <td className="px-4 py-3">
                        <div className="ml-auto w-fit">
                          <Figure
                            value={<SosnetCashAmount cents={w.balance_cents} />}
                            ratio={maxBalance > 0 ? Math.max(0, w.balance_cents) / maxBalance : null}
                          />
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <RowActions>
                          {isSuperAdmin ? (
                            <button
                              onClick={() => openTopUp(w.user_id)}
                              className={topUpForUserId === w.user_id ? "act" : "act act-primary"}
                            >
                              {topUpForUserId === w.user_id ? "Annulla" : "Ricarica"}
                            </button>
                          ) : (
                            <span className="text-[10px] text-surface-400" title="Solo il Super Admin può caricare cashback">—</span>
                          )}
                        </RowActions>
                      </td>
                    </tr>
                    {isSuperAdmin && topUpForUserId === w.user_id && (
                      <tr>
                        <td colSpan={5} className="px-5 py-4">
                          <form onSubmit={(e) => handleTopUp(e, w.user_id)} className="rise flex flex-wrap items-end gap-3">
                            <div className="max-w-[180px] flex-1 space-y-1">
                              <label className="kpi-label block">Importo (SosnetCash)</label>
                              <input
                                required
                                autoFocus
                                inputMode="decimal"
                                value={topUpAmount}
                                onChange={(e) => setTopUpAmount(e.target.value)}
                                placeholder="0,00"
                                className="field w-full rounded-xl px-3 py-2 text-lg font-black tabular-nums"
                              />
                            </div>
                            <div className="min-w-[180px] flex-1 space-y-1">
                              <label className="kpi-label block">Nota (opzionale)</label>
                              <input
                                value={topUpNote}
                                onChange={(e) => setTopUpNote(e.target.value)}
                                placeholder="Cashback ordine..."
                                className="field w-full rounded-xl px-3 py-2 text-sm"
                              />
                            </div>
                            <button type="submit" disabled={topUpLoading} className="act act-primary !h-10 shrink-0 !px-5">
                              {topUpLoading ? "..." : "Conferma"}
                            </button>
                          </form>
                          {topUpError && (
                            <div className="mt-2 rounded-xl border border-danger-500/30 bg-danger-500/15 p-2 text-xs text-danger-300">{topUpError}</div>
                          )}
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))
              )}
            </tbody>
          </table>
        </div>
        <div className="pt-3">
          <Pagination {...walletsPagination} label="wallet" />
        </div>
      </section>

      {/* Filters + export */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="subnav" role="tablist" aria-label="Filtra per tipo">
          {TYPE_FILTERS.map((f) => (
            <button
              key={f.value}
              type="button"
              role="tab"
              aria-selected={typeFilter === f.value}
              data-active={typeFilter === f.value}
              onClick={() => setTypeFilter(f.value)}
              className="subnav-pill"
            >
              {f.label}
            </button>
          ))}
        </div>
        <button onClick={handleExportCsv} className="act">
          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
          </svg>
          Esporta CSV
        </button>
      </div>

      {reverseError && (
        <div className="rounded-xl border border-danger-500/30 bg-danger-500/15 p-3 text-xs text-danger-300">{reverseError}</div>
      )}
      {transactionsError && <p className="text-sm text-danger-300">Impossibile caricare le transazioni.</p>}

      {/* Global transaction ledger */}
      <section className="panel rounded-3xl p-6">
        <div className="mb-4">
          <p className="kpi-label">Registro</p>
          <h3 className="mt-1 text-xl font-black tracking-tight text-white">Transazioni SosnetCash</h3>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr>
                <th className="px-4 py-3">Destinatario</th>
                <th className="px-4 py-3">Causale</th>
                <th className="px-4 py-3">Quando</th>
                <th className="px-4 py-3 text-right">Valore</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {isLoading && (
                <tr><td colSpan={5} className="px-4 py-10 text-center text-surface-400">Caricamento...</td></tr>
              )}
              {!isLoading && (transactions ?? []).length === 0 && (
                <tr>
                  <td colSpan={5} className="px-4 py-10">
                    <div className="flex flex-col items-center gap-2 text-center text-surface-400">
                      <Orb name="transazioni" icon={<span className="text-sm">∅</span>} />
                      <span className="text-sm">Nessuna transazione.</span>
                    </div>
                  </td>
                </tr>
              )}
              {transactionsPagination.pageItems.map((t) => (
                <Fragment key={t.id}>
                  <tr className="cursor-pointer" onClick={() => setExpandedId(expandedId === t.id ? null : t.id)}>
                    <td className="px-4 py-3">
                      <Identity name={t.to_display_name ?? "Sistema"} detail={`da ${t.from_display_name ?? "Sistema"}`} />
                    </td>
                    <td className="px-4 py-3">
                      <Chip tone={TYPE_TONES[t.type] ?? "muted"}>{transactionLabel(t)}</Chip>
                    </td>
                    <td className="px-4 py-3">
                      <Stack title={shortDate(t.created_at)} detail={new Date(t.created_at).toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" })} />
                    </td>
                    <td className="px-4 py-3">
                      <div className={`ml-auto w-fit ${t.type === "REVERSAL" ? "[&_.text-white]:text-danger-300" : ""}`}>
                        <Figure value={<SosnetCashAmount cents={t.amount_cents} />} />
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <RowActions>
                        {t.type !== "REVERSAL" && (
                          <button
                            onClick={(e) => { e.stopPropagation(); handleReverse(t.id); }}
                            disabled={reversingId === t.id}
                            className="act"
                          >
                            {reversingId === t.id ? "..." : "Storna"}
                          </button>
                        )}
                      </RowActions>
                    </td>
                  </tr>
                  {expandedId === t.id && (
                    <tr>
                      <td colSpan={5} className="space-y-1.5 px-5 py-4 text-xs text-surface-300">
                        {t.note && <p><span className="text-surface-400">Nota:</span> {t.note}</p>}
                        {t.reference_contract_id && (
                          <p><span className="text-surface-400">Riferimento:</span> <span className="font-mono text-[10px]">{t.reference_contract_id}</span></p>
                        )}
                        {(t.reference_order_id || t.reference_imported_order_id || t.reference_cj_order_id || t.reference_shopify_order_id || t.reference_aliexpress_order_id) && (
                          <p><span className="text-surface-400">Ordine collegato:</span> <span className="font-mono text-[10px]">{t.reference_order_id ?? t.reference_imported_order_id ?? t.reference_cj_order_id ?? t.reference_shopify_order_id ?? t.reference_aliexpress_order_id}</span> <span className="text-surface-400">(vedi Ordini)</span></p>
                        )}
                        {t.reference_invoice_redemption_id && (
                          <p><span className="text-surface-400">Riscatto collegato:</span> <span className="font-mono text-[10px]">{t.reference_invoice_redemption_id}</span> <span className="text-surface-400">(vedi Riscatti Fatture)</span></p>
                        )}
                        {t.from_address && <p><span className="text-surface-400">Indirizzo mittente:</span> <span className="font-mono text-[10px]">{t.from_address}</span></p>}
                        {t.to_address && <p><span className="text-surface-400">Indirizzo destinatario:</span> <span className="font-mono text-[10px]">{t.to_address}</span></p>}
                        <p className="flex items-center gap-2"><span className="text-surface-400">Riferimento:</span> <IdTag id={t.id} /> <span className="font-mono text-[10px] text-surface-400">{t.id}</span></p>
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
        <div className="pt-3">
          <Pagination {...transactionsPagination} label="transazioni" />
        </div>
      </section>
    </div>
  );
}
