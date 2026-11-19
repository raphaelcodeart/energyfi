"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { downloadCsv } from "@/lib/csv-export";
import { Pagination, usePagination } from "@/components/pagination";
import {
  euro, formatDate, sosnetCash, movementCategory, movementDirection, movementLabel, movementSignedAmountCents,
  shortCode,
} from "@/lib/accounting-format";
import type { FinancialMovementRead } from "@/lib/types";
import { SosnetCashAmount } from "@/components/sosnet-cash-amount";
import { AccountingDetailModal } from "@/components/accounting-detail-modal";
import { movementDetailRef, movementEntity } from "@/lib/accounting-format";
import { Chip, type ChipTone, Figure, Identity, KpiTile, Orb, Stack } from "@/components/ui/data-cells";

type MovementFilter = "ALL" | "SOSNETCASH" | "BANK_TRANSFER" | "CARD";

const FILTER_TABS: { key: MovementFilter; label: string }[] = [
  { key: "ALL", label: "Tutte" },
  { key: "SOSNETCASH", label: "SosnetCash" },
  { key: "BANK_TRANSFER", label: "Bonifico" },
  { key: "CARD", label: "Carta" },
];

const CATEGORY_TONES: Record<string, ChipTone> = {
  Ricarica: "info",
  Cashback: "ok",
  Pagamento: "accent",
  Contratto: "warn",
  Trasferimento: "info",
  Storno: "muted",
  Altro: "muted",
};

function DirectionIcon({ direction }: { direction: "in" | "out" }) {
  return direction === "in" ? (
    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-label="Entrata">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M19 14l-7 7m0 0l-7-7m7 7V3" />
    </svg>
  ) : (
    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-label="Uscita">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 10l7-7m0 0l7 7m-7-7v18" />
    </svg>
  );
}

function CurrencyChip({ m }: { m: FinancialMovementRead }) {
  if (m.currency === "SOSNETCASH") return <Chip tone="accent">SosnetCash</Chip>;
  return <Chip tone="info">{m.payment_method === "CARD" ? "Carta" : m.payment_method === "BANK_TRANSFER" ? "Bonifico" : "Euro"}</Chip>;
}

async function fetchAllMovements(): Promise<FinancialMovementRead[]> {
  const res = await fetch("/api/proxy/accounting/admin");
  if (!res.ok) throw new Error("Impossibile caricare la contabilità.");
  return res.json();
}

/**
 * Admin "Contabilità": every customer's SosnetCash and real-money movements,
 * filterable down to one customer with their own totals. Uses the same visual
 * language as accounting-panel.tsx so a movement reads the same for customer
 * and admin.
 */
export function AdminAccountingPanel() {
  const { data: movements, error } = useQuery({
    queryKey: ["admin", "accounting", "all"],
    queryFn: fetchAllMovements,
  });

  const [customerId, setCustomerId] = useState<string>("ALL");
  const [filter, setFilter] = useState<MovementFilter>("ALL");
  const [search, setSearch] = useState("");
  // Each row opens the same detail view the customer sees.
  const [detailRef, setDetailRef] = useState<string | null>(null);

  const list = useMemo(() => movements ?? [], [movements]);

  const customers = useMemo(() => {
    const byId = new Map<string, string>();
    for (const m of list) {
      if (m.customer_user_id && !byId.has(m.customer_user_id)) {
        byId.set(m.customer_user_id, m.customer_display_name ?? shortCode(m.customer_user_id));
      }
    }
    return Array.from(byId.entries())
      .map(([id, name]) => ({ id, name }))
      .sort((a, b) => a.name.localeCompare(b.name));
  }, [list]);

  const matchesFilter = (m: FinancialMovementRead, f: MovementFilter) => {
    if (f === "ALL") return true;
    if (f === "SOSNETCASH") return m.currency === "SOSNETCASH";
    return m.currency === "EUR" && m.payment_method === f;
  };

  const normalizedSearch = search.trim().toLowerCase();
  const scopedList = customerId === "ALL" ? list : list.filter((m) => m.customer_user_id === customerId);
  const filteredList = scopedList.filter((m) => {
    if (!matchesFilter(m, filter)) return false;
    if (!normalizedSearch) return true;
    return (
      movementLabel(m).toLowerCase().includes(normalizedSearch) ||
      (m.product_name ?? "").toLowerCase().includes(normalizedSearch) ||
      (m.customer_display_name ?? "").toLowerCase().includes(normalizedSearch)
    );
  });

  const totalSosnetCashCents = scopedList.filter((m) => m.currency === "SOSNETCASH").reduce((sum, m) => sum + movementSignedAmountCents(m), 0);
  const totalBankTransferCents = scopedList
    .filter((m) => m.currency === "EUR" && m.payment_method === "BANK_TRANSFER")
    .reduce((sum, m) => sum + Math.abs(m.amount_cents), 0);
  const totalCardCents = scopedList
    .filter((m) => m.currency === "EUR" && m.payment_method === "CARD")
    .reduce((sum, m) => sum + Math.abs(m.amount_cents), 0);

  // Pages the filtered list; the CSV export uses the full filtered set.
  const pagination = usePagination(filteredList);

  function handleExportCsv() {
    downloadCsv(
      `contabilita-admin-${new Date().toISOString().slice(0, 10)}.csv`,
      ["Data", "Cliente", "Tipo", "Movimento", "Descrizione", "Valuta", "Metodo di pagamento", "Entrata/Uscita", "Importo", "Nota"],
      filteredList.map((m) => [
        formatDate(m.created_at),
        m.customer_display_name ?? "",
        movementCategory(m),
        movementLabel(m),
        m.product_name ?? "",
        m.currency === "SOSNETCASH" ? "SosnetCash" : "EUR",
        m.payment_method ? (m.payment_method === "CARD" ? "Carta" : "Bonifico") : "",
        movementDirection(m) === "in" ? "Entrata" : "Uscita",
        (Math.abs(m.amount_cents) / 100).toLocaleString("it-IT", { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
        m.note ?? "",
      ])
    );
  }

  if (error) {
    return <p className="text-sm text-danger-300">Impossibile caricare la contabilità.</p>;
  }

  const colCount = customerId === "ALL" ? 6 : 5;

  return (
    <div className="space-y-6">
      <div>
        <p className="kpi-label">Estratto conto</p>
        <h3 className="mt-1 text-2xl font-black tracking-tight text-white">Contabilità</h3>
        <p className="mt-1 text-xs text-surface-300">
          Ogni movimento SosnetCash e ogni pagamento reale (carta o bonifico) di tutti i clienti, in un unico posto.
          Filtra per cliente per vedere il suo estratto conto personale.
        </p>
      </div>

      {/* Customer filter */}
      <div className="panel flex flex-wrap items-end gap-3 rounded-3xl p-5">
        <div className="space-y-1">
          <label className="kpi-label block">Cliente</label>
          <select
            value={customerId}
            onChange={(e) => setCustomerId(e.target.value)}
            className="field w-full max-w-xs rounded-xl px-3 py-2 text-sm"
          >
            <option value="ALL">Tutti i clienti ({customers.length})</option>
            {customers.map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
        </div>
        <div className="min-w-[200px] flex-1 space-y-1">
          <label className="kpi-label block">Cerca</label>
          <div className="relative">
            <svg className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-surface-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-4.35-4.35M17 11a6 6 0 11-12 0 6 6 0 0112 0z" />
            </svg>
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Prodotto, cliente, tipo movimento..."
              className="field w-full rounded-xl py-2 pl-9 pr-3 text-sm"
            />
          </div>
        </div>
      </div>

      {/* Totals: for the selected customer, or organization-wide for "Tutti" */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <KpiTile
          label="Saldo netto SosnetCash"
          value={<span className={totalSosnetCashCents < 0 ? "text-danger-300" : undefined}>{sosnetCash(totalSosnetCashCents)}</span>}
          hint={customerId === "ALL" ? "tutti i clienti" : "cliente selezionato"}
        />
        <KpiTile label="Incassato con Bonifico" value={euro(totalBankTransferCents)} />
        <KpiTile label="Incassato con Carta (Stripe)" value={euro(totalCardCents)} />
      </div>

      {/* Filters + export */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="subnav" role="tablist" aria-label="Filtra per canale">
          {FILTER_TABS.map((tab) => {
            const count = scopedList.filter((m) => matchesFilter(m, tab.key)).length;
            return (
              <button
                key={tab.key}
                type="button"
                role="tab"
                aria-selected={filter === tab.key}
                data-active={filter === tab.key}
                onClick={() => setFilter(tab.key)}
                className="subnav-pill"
              >
                {tab.label}
                <span className="opacity-60">{count}</span>
              </button>
            );
          })}
        </div>
        <button onClick={handleExportCsv} disabled={filteredList.length === 0} className="act">
          Scarica report CSV
        </button>
      </div>

      {/* Movements */}
      <section className="panel rounded-3xl p-6">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr>
                {customerId === "ALL" && <th className="px-4 py-3">Intestatario</th>}
                <th className="px-4 py-3">Operazione</th>
                <th className="px-4 py-3">Natura</th>
                <th className="px-4 py-3">Canale</th>
                <th className="px-4 py-3">Quando</th>
                <th className="px-4 py-3 text-right">Valore</th>
              </tr>
            </thead>
            <tbody>
              {movements === undefined ? (
                <tr><td colSpan={colCount} className="px-4 py-10 text-center text-surface-400">Caricamento...</td></tr>
              ) : filteredList.length === 0 ? (
                <tr>
                  <td colSpan={colCount} className="px-4 py-12">
                    <div className="flex flex-col items-center gap-2 text-center text-surface-400">
                      <Orb name="contabilita" icon={<span className="text-sm">€</span>} />
                      <span className="text-sm">Nessuna transazione in questa categoria.</span>
                    </div>
                  </td>
                </tr>
              ) : (
                pagination.pageItems.map((m) => {
                  const direction = movementDirection(m);
                  const category = movementCategory(m);
                  const entity = movementEntity(m);
                  const created = new Date(m.created_at);
                  return (
                    <tr
                      key={m.id}
                      onClick={() => {
                        const ref = movementDetailRef(m);
                        if (ref) setDetailRef(ref);
                      }}
                      className="cursor-pointer"
                    >
                      {customerId === "ALL" && (
                        <td className="px-4 py-3">
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              if (m.customer_user_id) setCustomerId(m.customer_user_id);
                            }}
                            className="cursor-pointer text-left transition hover:opacity-80"
                            title="Mostra solo questo cliente"
                          >
                            <Identity name={m.customer_display_name ?? "—"} detail="apri estratto conto" />
                          </button>
                        </td>
                      )}
                      <td className="px-4 py-3">
                        <Identity
                          name={movementLabel(m)}
                          detail={m.product_name ?? (direction === "in" ? "Entrata" : "Uscita")}
                          icon={<DirectionIcon direction={direction} />}
                        >
                          {entity && (
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                setDetailRef(entity.ref);
                              }}
                              className="mt-0.5 cursor-pointer text-[10px] font-bold text-brand-300 hover:text-white"
                            >
                              {entity.label} →
                            </button>
                          )}
                        </Identity>
                      </td>
                      <td className="px-4 py-3">
                        <Chip tone={CATEGORY_TONES[category] ?? "muted"}>{category}</Chip>
                      </td>
                      <td className="px-4 py-3"><CurrencyChip m={m} /></td>
                      <td className="px-4 py-3 whitespace-nowrap">
                        <Stack
                          title={created.toLocaleDateString("it-IT", { day: "2-digit", month: "short", year: "numeric" })}
                          detail={created.toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" })}
                        />
                      </td>
                      <td className="px-4 py-3">
                        <div className={`ml-auto w-fit ${direction === "out" ? "[&_.text-white]:text-danger-300" : "[&_.text-white]:text-success-300"}`}>
                          <Figure
                            value={m.currency === "SOSNETCASH" ? (
                              <SosnetCashAmount cents={Math.abs(m.amount_cents)} sign={direction === "out" ? "-" : "+"} />
                            ) : (
                              `${direction === "out" ? "-" : "+"}${euro(Math.abs(m.amount_cents))}`
                            )}
                            detail={direction === "in" ? "entrata" : "uscita"}
                          />
                        </div>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
        <div className="pt-3">
          <Pagination {...pagination} label="movimenti" />
        </div>
      </section>

      {detailRef && (
        <AccountingDetailModal
          initialRef={detailRef}
          scope="admin"
          movements={list}
          onClose={() => setDetailRef(null)}
        />
      )}
    </div>
  );
}
