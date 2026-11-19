"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { AccountingDetailModal } from "@/components/accounting-detail-modal";
import { SosnetCashAmount } from "@/components/sosnet-cash-amount";
import { Pagination, usePagination } from "@/components/pagination";
import {
  euro, formatDate, formatDayShort, formatTime, sosnetCash, monthKey, monthLabel, movementCategory,
  movementDetailRef, movementDirection, movementEntity, movementLabel, movementReferenceLink,
} from "@/lib/accounting-format";
import { downloadCsv } from "@/lib/csv-export";
import { ExternalWalletStats } from "@/components/external-wallet-stats";
import { PointsCounters } from "@/components/affiliate/mamify-orders";
import type { AccountingSummaryRead, FinancialMovementRead } from "@/lib/types";
import { Chip, type ChipTone, Figure, Identity, KpiTile, Orb } from "@/components/ui/data-cells";

const SHOW_MONEY_COUNTERS = false;

type Filter = "ALL" | "PAYMENTS" | "CONTRACTS" | "CASHBACK" | "SOSNETCASH" | "CARD" | "BANK_TRANSFER" | "IN" | "OUT";

const FILTERS: { key: Filter; label: string; match: (m: FinancialMovementRead) => boolean }[] = [
  { key: "ALL", label: "Tutti", match: () => true },
  { key: "PAYMENTS", label: "Pagamenti", match: (m) => m.currency === "EUR" },
  { key: "CASHBACK", label: "Cashback", match: (m) => movementCategory(m) === "Cashback" },
  { key: "SOSNETCASH", label: "SosnetCash", match: (m) => m.currency === "SOSNETCASH" },
  { key: "CARD", label: "Carta", match: (m) => m.payment_method === "CARD" },
  { key: "BANK_TRANSFER", label: "Bonifico", match: (m) => m.payment_method === "BANK_TRANSFER" },
  { key: "IN", label: "Entrate", match: (m) => movementDirection(m) === "in" },
  { key: "OUT", label: "Uscite", match: (m) => movementDirection(m) === "out" },
];

const CATEGORY_STYLE: Record<string, { tone: ChipTone; icon: string }> = {
  Pagamento: { tone: "accent", icon: "M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z" },
  Contratto: { tone: "warn", icon: "M13 10V3L4 14h7v7l9-11h-7z" },
  Cashback: { tone: "ok", icon: "M9 14l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" },
  Ricarica: { tone: "info", icon: "M12 4v16m8-8H4" },
  Trasferimento: { tone: "info", icon: "M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4" },
  Storno: { tone: "muted", icon: "M3 10h10a8 8 0 018 8v2M3 10l6 6m-6-6l6-6" },
  Altro: { tone: "muted", icon: "M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" },
};

async function fetchJson<T>(path: string): Promise<T> {
  const res = await fetch(path);
  if (!res.ok) throw new Error("Impossibile caricare la contabilità.");
  return res.json();
}

function Kpi({
  label,
  value,
  hint,
}: {
  label: string;
  value: React.ReactNode;
  hint?: React.ReactNode;
}) {
  return <KpiTile label={label} value={value} hint={hint} />;
}

/**
 * "Contabilità": the customer's own money in one place. Totals come from the
 * server; below, every movement grouped by month and filterable. Each row and
 * each order / redemption / contract chip opens its detail, so every euro and
 * SosnetCash can be traced to its origin.
 */
export function AccountingPanel({ onOpenTab }: { onOpenTab?: (tab: string) => void }) {
  const { data: movements, error } = useQuery({
    queryKey: ["accounting", "mine"],
    queryFn: () => fetchJson<FinancialMovementRead[]>("/api/proxy/accounting/mine"),
    refetchOnWindowFocus: true,
  });
  const { data: summary } = useQuery({
    queryKey: ["accounting", "mine", "summary"],
    queryFn: () => fetchJson<AccountingSummaryRead>("/api/proxy/accounting/mine/summary"),
    refetchOnWindowFocus: true,
  });
  const [filter, setFilter] = useState<Filter>("ALL");
  const [search, setSearch] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [detailRef, setDetailRef] = useState<string | null>(null);

  const list = movements ?? [];
  const needle = search.trim().toLowerCase();
  const active = FILTERS.find((f) => f.key === filter)!;
  const filtered = list.filter((m) => {
    if (!active.match(m)) return false;
    const day = m.created_at.slice(0, 10);
    if (from && day < from) return false;
    if (to && day > to) return false;
    if (!needle) return true;
    const amount = (Math.abs(m.amount_cents) / 100).toFixed(2);
    return [movementLabel(m), m.product_name, m.note, movementEntity(m)?.label, amount, amount.replace(".", ",")]
      .filter(Boolean)
      .some((v) => v!.toLowerCase().includes(needle));
  });
  const pagination = usePagination(filtered, 25);

  const outEur = filtered.filter((m) => m.currency === "EUR").reduce((s, m) => s + Math.abs(m.amount_cents), 0);
  const inSosnetCash = filtered
    .filter((m) => m.currency === "SOSNETCASH" && m.amount_cents > 0)
    .reduce((s, m) => s + m.amount_cents, 0);
  const filtersActive = Boolean(filter !== "ALL" || needle || from || to);

  const groups: { key: string; rows: FinancialMovementRead[] }[] = [];
  for (const m of pagination.pageItems) {
    const key = monthKey(m.created_at);
    const last = groups[groups.length - 1];
    if (last && last.key === key) last.rows.push(m);
    else groups.push({ key, rows: [m] });
  }

  function exportCsv() {
    downloadCsv(
      `contabilita-${new Date().toISOString().slice(0, 10)}.csv`,
      ["Data", "Tipo", "Movimento", "Descrizione", "Riferimento", "Valuta", "Metodo di pagamento", "Entrata/Uscita", "Importo", "Nota"],
      filtered.map((m) => [
        formatDate(m.created_at),
        movementCategory(m),
        movementLabel(m),
        m.product_name ?? "",
        movementReferenceLink(m, "/customer")?.label ?? "",
        m.currency === "SOSNETCASH" ? "SosnetCash" : "EUR",
        m.payment_method ? (m.payment_method === "CARD" ? "Carta" : "Bonifico") : "",
        movementDirection(m) === "in" ? "Entrata" : "Uscita",
        (Math.abs(m.amount_cents) / 100).toLocaleString("it-IT", { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
        m.note ?? "",
      ])
    );
  }

  if (error) return <p className="text-sm text-danger-300">Impossibile caricare la contabilità.</p>;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="kpi-label">Estratto conto</p>
          <h2 className="mt-1 text-3xl font-black tracking-tight text-white">Contabilità</h2>
          <p className="mt-1 text-xs text-surface-300">
            Ogni euro pagato e ogni SosnetCash, con il dettaglio di ciascun movimento.
          </p>
        </div>
        <button onClick={exportCsv} disabled={filtered.length === 0} className="act">
          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
          </svg>
          Esporta CSV
        </button>
      </div>

      {/* For now only points, licences and the Mamify wallets: the money
          counters (spent, card, bank transfer, SosnetCash...) are hidden. */}
      {SHOW_MONEY_COUNTERS && summary ? (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <Kpi
              label="Totale speso"
              value={euro(summary.spent_total_cents)}
              hint={`${summary.payments_count} pagamenti · carta ${euro(summary.spent_card_cents)} · bonifico ${euro(summary.spent_bank_transfer_cents)}`}
            />
            <Kpi label="Speso questo mese" value={euro(summary.spent_this_month_cents)} />
            <Kpi
              label="Saldo SosnetCash"
              value={<SosnetCashAmount cents={summary.sosnetcash_balance_cents} align="left" />}
            />
            <Kpi
              label="Cashback ricevuto"
              value={<SosnetCashAmount cents={summary.cashback_received_cents} align="left" />}
            />
          </div>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-5 [&_.kpi-value]:text-xl">
            <Kpi label="Pagato con carta" value={euro(summary.spent_card_cents)} hint="Stripe" />
            <Kpi label="Pagato con bonifico" value={euro(summary.spent_bank_transfer_cents)} />
            <Kpi
              label="Shop e riscatti"
              value={euro(summary.spent_orders_cents + summary.spent_redemptions_cents)}
              hint={`ordini ${euro(summary.spent_orders_cents)} · riscatti ${euro(summary.spent_redemptions_cents)}`}
            />
            <Kpi
              label="SosnetCash ricevuti"
              value={sosnetCash(summary.sosnetcash_received_cents)}
              hint={`spesi ${sosnetCash(summary.sosnetcash_spent_cents)}`}
            />
            {summary.commissions_total_cents != null ? (
              <Kpi
                label="Provvigioni maturate"
                value={euro(summary.commissions_total_cents)}
                hint={`da incassare ${euro(summary.commissions_to_collect_cents ?? 0)} · pagate ${euro(summary.commissions_paid_cents ?? 0)}`}
              />
            ) : (
              <Kpi label="Movimenti totali" value={list.length} hint="SosnetCash e pagamenti" />
            )}
          </div>
        </div>
      ) : (
        <div className="space-y-4">
          <ExternalWalletStats />
          <PointsCounters />
        </div>
      )}

      <div className="panel space-y-3 rounded-3xl p-4 sm:p-5">
        <div className="flex flex-col gap-2 lg:flex-row">
          <div className="relative flex-1">
            <svg className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-surface-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-4.35-4.35M17 11a6 6 0 11-12 0 6 6 0 0112 0z" />
            </svg>
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Cerca per descrizione, prodotto, importo, n° ordine / riscatto…"
              className="field w-full rounded-xl py-2.5 pl-9 pr-3 text-sm"
            />
          </div>
          <div className="flex items-center gap-2">
            <label className="kpi-label">Dal</label>
            <input type="date" value={from} onChange={(e) => setFrom(e.target.value)} className="field rounded-xl px-2.5 py-2 text-xs" />
            <label className="kpi-label">al</label>
            <input type="date" value={to} onChange={(e) => setTo(e.target.value)} className="field rounded-xl px-2.5 py-2 text-xs" />
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div className="subnav min-w-0 flex-1" role="tablist" aria-label="Filtra i movimenti">
            {FILTERS.map((f) => (
              <button
                key={f.key}
                type="button"
                role="tab"
                aria-selected={filter === f.key}
                data-active={filter === f.key}
                onClick={() => setFilter(f.key)}
                className="subnav-pill"
              >
                {f.label}
                <span className="opacity-60">{list.filter(f.match).length}</span>
              </button>
            ))}
          </div>
          {filtersActive && (
            <button
              onClick={() => { setFilter("ALL"); setSearch(""); setFrom(""); setTo(""); }}
              className="act"
            >
              Azzera filtri
            </button>
          )}
        </div>
        {filtersActive && (
          <div className="flex flex-wrap gap-2">
            <Chip tone="info">{filtered.length} movimenti</Chip>
            <Chip tone="accent">pagati {euro(outEur)}</Chip>
            <Chip tone="ok">SosnetCash ricevuti {sosnetCash(inSosnetCash)}</Chip>
          </div>
        )}
      </div>

      {movements === undefined ? (
        <div className="h-64 animate-pulse rounded-3xl bg-white/5" />
      ) : filtered.length === 0 ? (
        <div className="panel flex flex-col items-center gap-3 rounded-3xl p-10 text-center text-surface-300">
          <Orb name="ricerca" icon={<span className="text-sm">∅</span>} />
          <span className="text-sm">Nessun movimento corrisponde alla ricerca.</span>
        </div>
      ) : (
        <div className="space-y-6">
          {groups.map((group) => {
            const spent = group.rows.filter((m) => m.currency === "EUR").reduce((s, m) => s + Math.abs(m.amount_cents), 0);
            return (
              <section key={group.key} className="panel rounded-3xl p-5">
                <div className="mb-3 flex items-baseline justify-between px-1">
                  <h3 className="text-xl font-black capitalize tracking-tight text-white">{monthLabel(group.key)}</h3>
                  {spent > 0 && (
                    <span className="text-[11px] text-surface-300">
                      pagati <strong className="text-lg font-black tabular-nums text-white">{euro(spent)}</strong>
                    </span>
                  )}
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs">
                    <thead>
                      <tr>
                        <th className="px-4 py-3">Operazione</th>
                        <th className="hidden px-4 py-3 sm:table-cell">Natura</th>
                        <th className="hidden px-4 py-3 sm:table-cell">Quando</th>
                        <th className="px-4 py-3 text-right">Valore</th>
                        <th className="hidden w-8 px-2 py-3 sm:table-cell" />
                      </tr>
                    </thead>
                    <tbody>
                      {group.rows.map((m) => (
                        <MovementRow key={m.id} m={m} onOpen={setDetailRef} />
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            );
          })}
          <Pagination {...pagination} label="movimenti" />
        </div>
      )}

      {detailRef && (
        <AccountingDetailModal
          initialRef={detailRef}
          scope="mine"
          movements={list}
          onClose={() => setDetailRef(null)}
          onOpenTab={
            onOpenTab
              ? (tab) => {
                  setDetailRef(null);
                  onOpenTab(tab);
                }
              : undefined
          }
        />
      )}
    </div>
  );
}

function MovementRow({ m, onOpen }: { m: FinancialMovementRead; onOpen: (ref: string) => void }) {
  const direction = movementDirection(m);
  const category = movementCategory(m);
  const style = CATEGORY_STYLE[category] ?? CATEGORY_STYLE.Altro!;
  const entity = movementEntity(m);
  const detail = movementDetailRef(m);
  const out = direction === "out";

  return (
    <tr
      tabIndex={0}
      onClick={() => detail && onOpen(detail)}
      onKeyDown={(e) => e.key === "Enter" && detail && onOpen(detail)}
      className="group cursor-pointer"
    >
      <td className="px-4 py-3">
        <Identity
          name={movementLabel(m)}
          icon={
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d={style.icon} />
            </svg>
          }
          detail={
            <>
              <span className="font-bold text-surface-300 sm:hidden">
                {formatDayShort(m.created_at)} {formatTime(m.created_at)} ·{" "}
              </span>
              {[m.product_name, m.kind === "WALLET" ? m.note : null].filter(Boolean).join(" · ") || category}
            </>
          }
        >
          {entity && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                onOpen(entity.ref);
              }}
              className="mt-1 inline-flex cursor-pointer items-center gap-1 rounded-md border border-white/15 bg-white/10 px-2 py-0.5 text-[10px] font-bold text-white hover:bg-white/20"
            >
              {entity.label} →
            </button>
          )}
        </Identity>
      </td>
      <td className="hidden px-4 py-3 sm:table-cell">
        <Chip tone={style.tone}>{category}</Chip>
      </td>
      <td className="hidden whitespace-nowrap px-4 py-3 sm:table-cell">
        <div className="text-[12px] font-extrabold uppercase text-white">{formatDayShort(m.created_at)}</div>
        <div className="text-[10.5px] tabular-nums text-surface-400">{formatTime(m.created_at)}</div>
      </td>
      <td className="px-4 py-3">
        <div className={`ml-auto w-fit ${out ? "" : "[&_.text-white]:text-success-300"}`}>
          <Figure
            value={m.currency === "SOSNETCASH" ? (
              <SosnetCashAmount cents={Math.abs(m.amount_cents)} sign={out ? "-" : "+"} />
            ) : (
              `${out ? "-" : "+"}${euro(Math.abs(m.amount_cents))}`
            )}
            detail={m.currency === "EUR"
              ? (m.payment_method === "CARD" ? "Carta · Stripe" : m.payment_method === "BANK_TRANSFER" ? "Bonifico" : "Euro")
              : undefined}
          />
        </div>
      </td>
      <td className="hidden px-2 py-3 sm:table-cell">
        <svg className="h-4 w-4 text-surface-400 group-hover:text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
        </svg>
      </td>
    </tr>
  );
}
