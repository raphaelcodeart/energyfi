"use client";

import { type CSSProperties, Fragment, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Pagination, usePagination } from "@/components/pagination";
import type { CommissionLevelTotalsRead, CommissionMovementDetailRead } from "@/lib/types";
import { friendlyApiError } from "@/lib/api-error";
import { downloadCsv } from "@/lib/csv-export";
import { formatEuroCents as euro } from "@/lib/product-audience";
import {
  BENEFICIARY_LABELS,
  CALCULATION_LABELS,
  FALLBACK_LABELS,
  MOVEMENT_STATUS_LABELS,
  MOVEMENT_TYPE_LABELS,
} from "@/lib/commission-labels";
import { Chip, type ChipTone, Figure, IdTag, Identity, KpiTile, Orb, RowActions, Stack } from "@/components/ui/data-cells";

const STATUS_FILTERS: { value: string; label: string }[] = [
  { value: "ALL", label: "Tutti" },
  { value: "PENDING", label: "Da approvare" },
  { value: "APPROVED", label: "Approvate" },
  { value: "PAYABLE", label: "Pagabili" },
  { value: "PAID", label: "Pagate" },
  { value: "CANCELLED", label: "Annullate" },
];

function statusTone(status: string): ChipTone {
  switch (status) {
    case "PAID":
    case "APPROVED":
      return "ok";
    case "PAYABLE":
      return "accent";
    case "PENDING":
    case "ACCRUED":
      return "warn";
    case "CANCELLED":
    case "REVERSED":
      return "bad";
    case "RETAINED":
      return "muted";
    default:
      return "info";
  }
}

function typeTone(type: string): ChipTone {
  switch (type) {
    case "DIRECT":
      return "accent";
    case "REVERSAL":
      return "bad";
    case "COMPANY_SHARE":
      return "muted";
    default:
      return "info";
  }
}

function shortDate(iso: string): string {
  return new Date(iso).toLocaleDateString("it-IT", { day: "2-digit", month: "short", year: "numeric" });
}

async function fetchMovements(includeCompany: boolean): Promise<CommissionMovementDetailRead[]> {
  const res = await fetch(`/api/proxy/commissions/movements${includeCompany ? "?include_company=true" : ""}`);
  if (!res.ok) throw new Error("Impossibile caricare il registro provvigioni.");
  return res.json();
}

async function fetchLevelTotals(): Promise<CommissionLevelTotalsRead[]> {
  const res = await fetch("/api/proxy/commissions/movements/by-level");
  if (!res.ok) throw new Error("Impossibile caricare il riepilogo per livello.");
  return res.json();
}

/**
 * States from which each action is allowed, mirroring
 * commissions/services/lifecycle.py::TRANSITIONS. The server still decides.
 */
const ACTIONS: { to: string; label: string; from: string[] }[] = [
  { to: "APPROVED", label: "Approva", from: ["PENDING", "ACCRUED"] },
  { to: "PAYABLE", label: "Rendi pagabile", from: ["APPROVED"] },
  { to: "PAID", label: "Segna pagata", from: ["APPROVED", "PAYABLE"] },
];

export function AdminCommissionsPanel({ initialStatusFilter }: { initialStatusFilter?: string }) {
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState(initialStatusFilter ?? "ALL");
  const [agentFilter, setAgentFilter] = useState("ALL");
  const [typeFilter, setTypeFilter] = useState("ALL");
  const [includeCompany, setIncludeCompany] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const { data: movements, error: movementsError, isLoading } = useQuery({
    queryKey: ["admin", "commissions", "movements", includeCompany],
    queryFn: () => fetchMovements(includeCompany),
  });
  const { data: levelTotals } = useQuery({
    queryKey: ["admin", "commissions", "by-level"],
    queryFn: fetchLevelTotals,
  });

  const agents = useMemo(() => {
    const map = new Map<string, string>();
    (movements ?? []).forEach((m) => {
      if (m.agent_id) map.set(m.agent_id, `${m.agent_name} (${m.agent_promoter_code})`);
    });
    return Array.from(map.entries()).sort((a, b) => a[1].localeCompare(b[1]));
  }, [movements]);

  const filtered = (movements ?? []).filter((m) => {
    const statusOk =
      statusFilter === "ALL"
      || (statusFilter === "PENDING" ? m.status === "PENDING" || m.status === "ACCRUED" : m.status === statusFilter);
    return statusOk
      && (agentFilter === "ALL" || m.agent_id === agentFilter)
      && (typeFilter === "ALL" || m.movement_type === typeFilter);
  });
  const pagination = usePagination(filtered);

  const sum = (pred: (m: CommissionMovementDetailRead) => boolean) =>
    filtered.filter((m) => m.beneficiary_kind === "AGENT" && pred(m)).reduce((acc, m) => acc + m.amount_cents, 0);
  const totals = {
    pending: sum((m) => m.status === "PENDING" || m.status === "ACCRUED"),
    approved: sum((m) => m.status === "APPROVED" || m.status === "PAYABLE"),
    paid: sum((m) => m.status === "PAID"),
    company: filtered.filter((m) => m.beneficiary_kind === "COMPANY" && m.status !== "CANCELLED").reduce((a, m) => a + m.amount_cents, 0),
  };

  const selectedRows = filtered.filter((m) => selected.has(m.id));

  function toggle(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function runAction(to: string, ids: string[]) {
    setBusy(to);
    setActionError(null);
    try {
      const res = await fetch("/api/proxy/commissions/movements/transition", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ movement_ids: ids, to_status: to, note: "Dal registro provvigioni" }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      setSelected(new Set());
      await queryClient.invalidateQueries({ queryKey: ["admin", "commissions"] });
    } catch (err: any) {
      setActionError(err.message || "Operazione non riuscita.");
    } finally {
      setBusy(null);
    }
  }

  function handleExportCsv() {
    downloadCsv(
      `provvigioni_${new Date().toISOString().slice(0, 10)}`,
      ["ID Movimento", "Contratto", "Cliente", "Prodotto", "Beneficiario", "Codice", "Livello", "Ruolo alla vendita",
        "Piano", "Versione", "Regola", "Calcolo", "Margine (EUR)", "Tipo", "Importo (EUR)", "Stato", "Maturazione", "Pagamento"],
      filtered.map((m) => [
        m.id, m.contract_id, m.customer_name, m.product_name, m.agent_name, m.agent_promoter_code,
        m.depth_from_producer ?? "", m.role_at_calculation ?? "", m.plan_name ?? "", m.plan_version ?? "",
        m.rule_label ?? "", CALCULATION_LABELS[m.calculation_type ?? ""] ?? m.calculation_type ?? "",
        m.reference_margin_cents != null ? (m.reference_margin_cents / 100).toFixed(2) : "",
        MOVEMENT_TYPE_LABELS[m.movement_type] ?? m.movement_type, (m.amount_cents / 100).toFixed(2),
        MOVEMENT_STATUS_LABELS[m.status] ?? m.status, m.effective_date, m.paid_date ?? "",
      ])
    );
  }

  const levelCommissionTotal = (levelTotals ?? []).reduce((a, r) => a + r.commission_cents, 0);

  return (
    <div className="space-y-6">
      <div className="stagger grid grid-cols-2 gap-4 lg:grid-cols-4">
        {[
          { label: "Da approvare", value: totals.pending, hint: "nel filtro corrente" },
          { label: "Approvate, da pagare", value: totals.approved, hint: "nel filtro corrente" },
          { label: "Pagate", value: totals.paid, hint: "nel filtro corrente" },
          { label: "Quota azienda", value: totals.company, hint: includeCompany ? "nel filtro corrente" : "attiva «Mostra quote azienda»" },
        ].map((k, i) => (
          <div key={k.label} style={{ "--i": i } as CSSProperties}>
            <KpiTile label={k.label} value={euro(k.value)} hint={k.hint} />
          </div>
        ))}
      </div>

      <section className="panel rounded-3xl p-6">
        <div className="mb-4">
          <p className="kpi-label">Rete</p>
          <h3 className="mt-1 text-xl font-black tracking-tight text-white">Distribuzione per livello di rete</h3>
          <p className="mt-1 text-[11px] text-surface-400">
            Livello 0 = chi ha venduto; livello N = N passaggi di sponsorizzazione sopra di lui, alla data della vendita.
          </p>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr>
                <th className="px-4 py-3">Gradino</th>
                <th className="px-4 py-3 text-right">Provvigioni generate</th>
                <th className="px-4 py-3 text-right">Volume venduto</th>
                <th className="px-4 py-3 text-right">Vendite</th>
              </tr>
            </thead>
            <tbody>
              {(levelTotals ?? []).map((row) => (
                <tr key={row.depth}>
                  <td className="px-4 py-3">
                    <Identity
                      name={row.depth === 0 ? "Venditore" : `Livello ${row.depth}`}
                      detail={row.depth === 0 ? "livello 0, chi ha chiuso" : `${row.depth} passaggi sopra il venditore`}
                      icon={<span className="text-sm font-black">{row.depth}</span>}
                    />
                  </td>
                  <td className="px-4 py-3">
                    <div className="ml-auto w-fit">
                      <Figure
                        value={euro(row.commission_cents)}
                        detail={levelCommissionTotal > 0 ? `${Math.round((row.commission_cents / levelCommissionTotal) * 100)}% del totale` : undefined}
                        ratio={levelCommissionTotal > 0 ? row.commission_cents / levelCommissionTotal : null}
                      />
                    </div>
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums text-surface-300">{euro(row.value_cents)}</td>
                  <td className="px-4 py-3 text-right tabular-nums font-bold text-white">{row.contracts}</td>
                </tr>
              ))}
              {(levelTotals ?? []).length === 0 && (
                <tr>
                  <td colSpan={4} className="px-4 py-10">
                    <div className="flex flex-col items-center gap-2 text-center text-surface-400">
                      <Orb name="rete" icon={<span className="text-sm">∅</span>} />
                      <span className="text-sm">Nessun dato di rete ancora disponibile.</span>
                    </div>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <div className="space-y-3">
        <div className="subnav" role="tablist" aria-label="Filtra per stato">
          {STATUS_FILTERS.map((f) => (
            <button
              key={f.value}
              type="button"
              role="tab"
              aria-selected={statusFilter === f.value}
              data-active={statusFilter === f.value}
              onClick={() => setStatusFilter(f.value)}
              className="subnav-pill"
            >
              {f.label}
            </button>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <select value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)} className="field rounded-xl px-3 py-2 text-xs">
            <option value="ALL">Tutti i tipi</option>
            {Object.entries(MOVEMENT_TYPE_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
          <select value={agentFilter} onChange={(e) => setAgentFilter(e.target.value)} className="field max-w-[220px] rounded-xl px-3 py-2 text-xs">
            <option value="ALL">Tutti i collaboratori</option>
            {agents.map(([id, label]) => <option key={id} value={id}>{label}</option>)}
          </select>
          <label className="inline-flex cursor-pointer items-center gap-1.5 text-xs text-surface-300">
            <input type="checkbox" checked={includeCompany} onChange={(e) => setIncludeCompany(e.target.checked)} />
            Mostra quote azienda
          </label>
          <button onClick={handleExportCsv} className="act ml-auto">
            Esporta CSV
          </button>
        </div>
      </div>

      {selectedRows.length > 0 && (
        <div className="panel pop flex flex-wrap items-center gap-3 rounded-2xl p-4">
          <div className="mr-2">
            <p className="kpi-label">{selectedRows.length} selezionate</p>
            <p className="text-2xl font-black tabular-nums text-white">{euro(selectedRows.reduce((a, m) => a + m.amount_cents, 0))}</p>
          </div>
          {ACTIONS.map((a) => {
            const eligible = selectedRows.filter((m) => a.from.includes(m.status));
            return (
              <button
                key={a.to}
                disabled={eligible.length === 0 || busy !== null}
                onClick={() => runAction(a.to, eligible.map((m) => m.id))}
                className="act act-primary"
              >
                {busy === a.to ? "..." : `${a.label} (${eligible.length})`}
              </button>
            );
          })}
          <button onClick={() => setSelected(new Set())} className="act">Deseleziona</button>
        </div>
      )}

      {actionError && <div className="rounded-xl border border-danger-500/30 bg-danger-500/15 p-3 text-xs text-danger-300">{actionError}</div>}
      {movementsError && <p className="text-sm text-danger-300">Impossibile caricare il registro provvigioni.</p>}

      <section className="panel rounded-3xl p-6">
        <div className="mb-4 flex flex-wrap items-end justify-between gap-2">
          <div>
            <p className="kpi-label">Registro</p>
            <h3 className="mt-1 text-xl font-black tracking-tight text-white">Movimenti provvigionali</h3>
          </div>
          <p className="text-[11px] text-surface-400">Clic su una riga per vedere il perché dell&apos;importo.</p>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr>
                <th className="w-8 px-4 py-3" />
                <th className="px-4 py-3">Beneficiario</th>
                <th className="px-4 py-3">Origine</th>
                <th className="px-4 py-3">Regola applicata</th>
                <th className="px-4 py-3">Natura</th>
                <th className="px-4 py-3">Maturata</th>
                <th className="px-4 py-3 text-right">Valore</th>
                <th className="px-4 py-3">Situazione</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {isLoading && (
                <tr><td colSpan={9} className="px-4 py-10 text-center text-surface-400">Caricamento...</td></tr>
              )}
              {!isLoading && filtered.length === 0 && (
                <tr>
                  <td colSpan={9} className="px-4 py-12">
                    <div className="flex flex-col items-center gap-2 text-center text-surface-400">
                      <Orb name="vuoto" icon={<span className="text-sm">€</span>} />
                      <span className="text-sm">Nessun movimento corrisponde ai filtri.</span>
                    </div>
                  </td>
                </tr>
              )}
              {pagination.pageItems.map((m) => {
                const nextAction = ACTIONS.find((a) => a.from.includes(m.status) && m.beneficiary_kind === "AGENT");
                const levelText = m.depth_from_producer === 0 ? "Venditore" : m.depth_from_producer != null ? `Livello ${m.depth_from_producer}` : "";
                const margin = m.reference_margin_cents;
                const ratio = margin != null && margin > 0 ? Math.abs(m.amount_cents) / margin : null;
                return (
                  <Fragment key={m.id}>
                    <tr className="cursor-pointer" onClick={() => setExpandedId(expandedId === m.id ? null : m.id)}>
                      <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
                        {m.beneficiary_kind === "AGENT" && (
                          <input type="checkbox" checked={selected.has(m.id)} onChange={() => toggle(m.id)} aria-label="Seleziona movimento" />
                        )}
                      </td>
                      <td className="px-4 py-3">
                        <Identity
                          name={m.agent_name}
                          detail={[levelText, m.role_at_calculation].filter(Boolean).join(" · ") || undefined}
                        />
                      </td>
                      <td className="px-4 py-3">
                        <Stack title={m.customer_name} detail={m.product_name} />
                        <div className="mt-1"><IdTag id={m.contract_id} /></div>
                      </td>
                      <td className="px-4 py-3">
                        <Stack
                          title={m.rule_label ?? BENEFICIARY_LABELS[m.beneficiary_type ?? ""] ?? "—"}
                          detail={m.plan_name ? `${m.plan_name} v${m.plan_version}` : undefined}
                        />
                      </td>
                      <td className="px-4 py-3">
                        <Chip tone={typeTone(m.movement_type)}>{MOVEMENT_TYPE_LABELS[m.movement_type] ?? m.movement_type}</Chip>
                      </td>
                      <td className="px-4 py-3">
                        <Stack title={shortDate(m.effective_date)} detail={m.paid_date ? `pagata ${shortDate(m.paid_date)}` : undefined} />
                      </td>
                      <td className="px-4 py-3">
                        <div className={`ml-auto w-fit ${m.amount_cents < 0 ? "[&_.text-white]:text-danger-300" : ""}`}>
                          <Figure
                            value={euro(m.amount_cents)}
                            detail={margin != null ? `su margine ${euro(margin)}` : undefined}
                            ratio={ratio != null ? Math.min(1, ratio) : null}
                          />
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <Chip tone={statusTone(m.status)} live={m.status === "PENDING" || m.status === "ACCRUED"}>
                          {MOVEMENT_STATUS_LABELS[m.status] ?? m.status}
                        </Chip>
                      </td>
                      <td className="px-4 py-3">
                        <RowActions>
                          {nextAction && (
                            <button
                              onClick={(e) => { e.stopPropagation(); runAction(nextAction.to, [m.id]); }}
                              disabled={busy !== null}
                              className="act act-primary"
                            >
                              {nextAction.label}
                            </button>
                          )}
                        </RowActions>
                      </td>
                    </tr>
                    {expandedId === m.id && (
                      <tr>
                        <td colSpan={9} className="px-5 py-4">
                          <div className="rise grid grid-cols-1 gap-4 text-xs text-surface-300 md:grid-cols-2">
                            <div className="space-y-1.5">
                              <p><span className="text-surface-400">Contratto:</span> <span className="font-mono">{m.contract_id}</span></p>
                              <p><span className="text-surface-400">Importo vendita:</span> <span className="font-bold text-white">{euro(m.value_cents)}</span></p>
                              <p><span className="text-surface-400">Margine di riferimento:</span> <span className="font-bold text-white">{m.reference_margin_cents != null ? euro(m.reference_margin_cents) : "—"}</span></p>
                              <p><span className="text-surface-400">Venditore:</span> {m.producer_name}</p>
                              <p><span className="text-surface-400">Ruolo alla data della vendita:</span> <span className="font-semibold text-brand-300">{m.role_at_calculation ?? "—"}</span> · <span className="text-surface-400">oggi:</span> {m.agent_current_role_code ?? "—"}</p>
                            </div>
                            <div className="space-y-1.5">
                              <p><span className="text-surface-400">Piano:</span> {m.plan_name ?? "—"}{m.plan_version ? ` (versione ${m.plan_version})` : ""}</p>
                              <p><span className="text-surface-400">Calcolo:</span> {CALCULATION_LABELS[m.calculation_type ?? ""] ?? m.calculation_type ?? "—"}</p>
                              {m.fallback_applied && (
                                <p><span className="text-surface-400">Livello mancante:</span> <span className="text-warn-300">{FALLBACK_LABELS[m.fallback_applied] ?? m.fallback_applied}</span></p>
                              )}
                              <p><span className="text-surface-400">Maturazione:</span> {shortDate(m.effective_date)}</p>
                              {m.approved_at && <p><span className="text-surface-400">Approvata:</span> {shortDate(m.approved_at)}</p>}
                              {m.paid_date && <p><span className="text-surface-400">Pagata:</span> <span className="text-success-300">{shortDate(m.paid_date)}</span></p>}
                            </div>
                          </div>
                          {m.explanation && (
                            <div className="mt-3 rounded-2xl border border-white/15 bg-white/5 p-4 text-surface-200">
                              <span className="kpi-label mb-1 block">Perché questo importo</span>
                              {m.explanation}
                            </div>
                          )}
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
        <div className="pt-3">
          <Pagination {...pagination} label="movimenti" />
        </div>
      </section>
    </div>
  );
}
