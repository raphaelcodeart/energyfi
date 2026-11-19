"use client";

import { useMemo, useState, type CSSProperties, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { BranchContractRead, BranchSummaryRead } from "@/lib/types";
import { axisProps, tooltipStyles, useChartTheme } from "@/lib/chart-theme";
import { Chip, Figure, IdTag, Identity, KpiTile, RowActions, Stack } from "@/components/ui/data-cells";

const STATUS_LABELS: Record<string, string> = {
  DRAFT: "Bozza",
  SUBMITTED: "Inviata",
  DOCUMENTS_PENDING: "Documenti mancanti",
  UNDER_REVIEW: "In revisione",
  APPROVED: "Approvata",
  PAYMENT_PENDING: "In attesa di pagamento",
  PAID: "Pagata",
  ACTIVATION_PENDING: "In attivazione",
  ACTIVE: "Attiva",
  SUSPENDED: "Sospesa",
  CANCELLED: "Cessata",
  EXPIRED: "Scaduta",
  RENEWED: "Rinnovata",
  REJECTED: "Respinta",
};

function euro(cents: number): string {
  return (cents / 100).toLocaleString("it-IT", { style: "currency", currency: "EUR" });
}

async function fetchBranchSummary(agentId: string): Promise<BranchSummaryRead> {
  const res = await fetch(`/api/proxy/network/agents/${agentId}/branch-summary`);
  if (!res.ok) throw new Error("Impossibile caricare il riepilogo della rete.");
  return res.json();
}

async function fetchBranchContracts(agentId: string): Promise<BranchContractRead[]> {
  const res = await fetch(`/api/proxy/network/agents/${agentId}/branch-contracts`);
  if (!res.ok) throw new Error("Impossibile caricare i contratti della rete.");
  return res.json();
}


export function PromoterAziendaPanel({ agentId }: { agentId: string }) {
  const chart = useChartTheme();
  const { data: summary, error: summaryError, isLoading: summaryLoading } = useQuery({
    queryKey: ["promoter", "branch-summary", agentId],
    queryFn: () => fetchBranchSummary(agentId),
  });
  const { data: contracts, error: contractsError } = useQuery({
    queryKey: ["promoter", "branch-contracts", agentId],
    queryFn: () => fetchBranchContracts(agentId),
  });
  const [onlyProblems, setOnlyProblems] = useState(false);
  const [selectedLevel, setSelectedLevel] = useState<number | null>(null);

  const perLevel = useMemo(() => {
    if (!summary) return [];
    const map = new Map<number, { depth: number; agentCount: number; contracts: number; commission: number }>();
    for (const a of summary.agents) {
      const entry = map.get(a.depth) ?? { depth: a.depth, agentCount: 0, contracts: 0, commission: 0 };
      entry.agentCount += 1;
      entry.contracts += a.contracts_total;
      entry.commission += a.commission_cents;
      map.set(a.depth, entry);
    }
    return Array.from(map.values()).sort((a, b) => a.depth - b.depth);
  }, [summary]);

  const chartData = useMemo(
    () =>
      perLevel
        .filter((row) => row.depth > 0) // Depth 0 ("Tu") is not downline and would skew the scale.
        .map((row) => ({
          name: `Liv. ${row.depth}`,
          Persone: row.agentCount,
          Contratti: row.contracts,
        })),
    [perLevel]
  );

  const directCount = summary?.agents.filter((a) => a.depth === 1).length ?? 0;
  const totalProblems = summary?.agents.reduce((sum, a) => sum + a.contracts_problem, 0) ?? 0;
  const totals = summary?.totals;

  const levelDetail = useMemo(() => {
    if (selectedLevel === null || !summary) return null;
    const agents = summary.agents.filter((a) => a.depth === selectedLevel);
    return {
      depth: selectedLevel,
      agents,
      contracts: agents.reduce((sum, a) => sum + a.contracts_total, 0),
      closed: agents.reduce((sum, a) => sum + a.contracts_processed, 0),
      problem: agents.reduce((sum, a) => sum + a.contracts_problem, 0),
      inProgress: agents.reduce((sum, a) => sum + a.contracts_in_progress, 0),
      commission: agents.reduce((sum, a) => sum + a.commission_cents, 0),
    };
  }, [selectedLevel, summary]);

  const filteredContracts = (contracts ?? []).filter((c) => !onlyProblems || c.is_problem);
  const agentsForTable = selectedLevel === null ? (summary?.agents ?? []) : (levelDetail?.agents ?? []);

  const levelRows = perLevel.filter((row) => row.depth > 0);
  const maxLevelContracts = Math.max(1, ...levelRows.map((row) => row.contracts));
  const levelCommissionTotal = levelRows.reduce((sum, row) => sum + row.commission, 0);
  const tableCommissionTotal = agentsForTable.reduce((sum, a) => sum + a.commission_cents, 0);
  const loadingValue = (value: ReactNode) => (summaryLoading ? "…" : value);

  return (
    <div className="space-y-6">
      {(summaryError || contractsError) && (
        <p className="text-sm text-danger-400">Impossibile caricare i dati della rete.</p>
      )}

      {/* Downline totals; the API scopes data to the promoter's branch. */}
      <div className="stagger grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[
          { label: "Persone in rete", value: loadingValue(totals?.people_total ?? 0), hint: `${directCount} diretti` },
          { label: "Livelli sotto di te", value: loadingValue(totals?.levels_below ?? 0) },
          { label: "Contratti chiusi", value: <span className="text-success-400">{loadingValue(totals?.contracts_closed ?? 0)}</span> },
          { label: "Provvigioni totali", value: <span className="text-gradient">{loadingValue(euro(totals?.commission_cents ?? 0))}</span> },
          { label: "Rifiutati", value: <span className="text-danger-400">{loadingValue(totals?.contracts_rejected ?? 0)}</span> },
          { label: "In attesa", value: <span className="text-warn-400">{loadingValue(totals?.contracts_pending ?? 0)}</span> },
          { label: "In lavorazione", value: <span className="text-info-400">{loadingValue(totals?.contracts_in_progress ?? 0)}</span> },
          { label: "Contratti totali", value: loadingValue(totals?.contracts ?? 0) },
        ].map((tile, i) => (
          <div key={tile.label} style={{ "--i": i } as CSSProperties}>
            <KpiTile label={tile.label} value={tile.value} hint={tile.hint} />
          </div>
        ))}
      </div>

      {totalProblems > 0 && (
        <div className="pop flex items-center gap-3 rounded-3xl border border-warn-500/25 bg-warn-500/10 px-5 py-4 text-sm font-semibold text-warn-300">
          <span className="pulse-ring flex h-9 w-9 shrink-0 items-center justify-center rounded-2xl bg-warn-500/20">
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </span>
          {totalProblems} {totalProblems === 1 ? "contratto ha" : "contratti hanno"} bisogno di attenzione nella tua rete.
        </div>
      )}

      {/* Per-level breakdown, chart and drill-down */}
      <div className="panel rounded-3xl overflow-hidden">
        <div className="flex flex-wrap items-end justify-between gap-2 px-6 pt-6 sm:px-8">
          <div>
            <p className="kpi-label">La tua rete</p>
            <h3 className="mt-1 text-xl font-black tracking-tight text-white">Riepilogo per livello</h3>
          </div>
          <p className="text-[11px] text-surface-400">Clicca un livello per il dettaglio</p>
        </div>
        {chartData.length > 0 && (
          <div className="h-56 px-6 pt-5 sm:px-8">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke={chart.grid} vertical={false} />
                <XAxis dataKey="name" {...axisProps(chart)} />
                <YAxis allowDecimals={false} {...axisProps(chart)} />
                <Tooltip cursor={{ fill: chart.grid }} {...tooltipStyles(chart)} />
                <Bar dataKey="Persone" fill={chart.series[1]} radius={[6, 6, 0, 0]} />
                <Bar dataKey="Contratti" fill={chart.series[0]} radius={[6, 6, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
        {levelRows.length === 0 && !summaryLoading ? (
          <EmptyBlock text="Nessun dato disponibile: la tua rete è ancora da costruire." />
        ) : (
          <div className="overflow-x-auto px-2 pb-4 pt-2 sm:px-4">
            <table className="w-full border-collapse text-left text-sm">
              <thead>
                <tr>
                  <th className="px-4 py-3">Profondità</th>
                  <th className="px-4 py-3">Pratiche generate</th>
                  <th className="px-4 py-3 text-right">Compensi maturati</th>
                  <th className="px-4 py-3"></th>
                </tr>
              </thead>
              <tbody>
                {levelRows.map((row) => {
                  const selected = selectedLevel === row.depth;
                  return (
                    <tr
                      key={row.depth}
                      onClick={() => setSelectedLevel(selectedLevel === row.depth ? null : row.depth)}
                      className={`cursor-pointer ${selected ? "outline outline-2 outline-white/40" : ""}`}
                    >
                      <td className="px-4 py-3">
                        <Identity
                          name={`Livello ${row.depth}`}
                          icon={<span className="text-[13px] font-black">{row.depth}</span>}
                          detail={`${row.agentCount} ${row.agentCount === 1 ? "persona" : "persone"}`}
                        />
                      </td>
                      <td className="px-4 py-3">
                        <div className="min-w-[120px] max-w-[220px]">
                          <div className="text-[13px] font-bold tabular-nums text-white">{row.contracts} contratti</div>
                          <div className="meter mt-1.5">
                            <i style={{ width: `${Math.max(3, (row.contracts / maxLevelContracts) * 100)}%` }} />
                          </div>
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex justify-end">
                          <Figure
                            value={euro(row.commission)}
                            ratio={levelCommissionTotal > 0 ? row.commission / levelCommissionTotal : null}
                          />
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <RowActions>
                          <span className={selected ? "act act-primary" : "act"}>{selected ? "Chiudi" : "Dettaglio"}</span>
                        </RowActions>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Per-agent breakdown, filtered by the selected level */}
      <div className="panel rounded-3xl overflow-hidden">
        <div className="flex flex-wrap items-end justify-between gap-2 px-6 pt-6 sm:px-8">
          <div>
            <p className="kpi-label">{selectedLevel === null ? "Tutta la rete" : "Dettaglio livello"}</p>
            <h3 className="mt-1 text-xl font-black tracking-tight text-white">
              {selectedLevel === null ? "Contratti per persona" : `Livello ${selectedLevel} -- dettaglio`}
            </h3>
          </div>
          {selectedLevel !== null && (
            <button onClick={() => setSelectedLevel(null)} className="act">
              Torna alla vista generale
            </button>
          )}
        </div>
        {levelDetail && (
          <div className="stagger grid grid-cols-2 sm:grid-cols-4 gap-3 px-6 pt-5 sm:px-8">
            {[
              { label: "Persone", value: levelDetail.agents.length, tone: "text-white" },
              { label: "Chiusi", value: levelDetail.closed, tone: "text-success-400" },
              { label: "In lavorazione", value: levelDetail.inProgress, tone: "text-info-400" },
              { label: "Problemi", value: levelDetail.problem, tone: "text-danger-400" },
            ].map((tile, i) => (
              <div
                key={tile.label}
                data-tilt
                style={{ "--i": i } as CSSProperties}
                className="rounded-2xl border border-white/10 bg-white/5 p-4 text-center"
              >
                <p className="kpi-label">{tile.label}</p>
                <p className={`mt-1 text-2xl font-black tabular-nums ${tile.tone}`}>{tile.value}</p>
              </div>
            ))}
          </div>
        )}
        <div className="overflow-x-auto px-2 pb-4 pt-2 sm:px-4">
          <table className="w-full border-collapse text-left text-sm">
            <thead>
              <tr>
                <th className="px-4 py-3">Collaboratore</th>
                <th className="px-4 py-3">Avanzamento pratiche</th>
                <th className="px-4 py-3">Criticità</th>
                <th className="px-4 py-3 text-right">Compensi</th>
              </tr>
            </thead>
            <tbody>
              {agentsForTable.map((a) => (
                <tr key={a.agent_id}>
                  <td className="px-4 py-3">
                    <Identity name={a.display_name} detail={a.depth === 0 ? "Tu" : `Livello ${a.depth}`} />
                  </td>
                  <td className="px-4 py-3">
                    <div className="min-w-[150px] max-w-[240px]">
                      <div className="text-[13px] font-bold tabular-nums text-white">
                        <span className="text-success-400">{a.contracts_processed}</span>
                        <span className="text-surface-400"> / {a.contracts_total} processati</span>
                      </div>
                      <div className="text-[11px] text-warn-400">{a.contracts_in_progress} in lavorazione</div>
                      {a.contracts_total > 0 && (
                        <div className="meter mt-1.5">
                          <i style={{ width: `${Math.max(3, (a.contracts_processed / a.contracts_total) * 100)}%` }} />
                        </div>
                      )}
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    {a.contracts_problem > 0 ? (
                      <Chip tone="bad" live>
                        {a.contracts_problem} {a.contracts_problem === 1 ? "problema" : "problemi"}
                      </Chip>
                    ) : (
                      <Chip tone="muted">Nessuna</Chip>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex justify-end">
                      <Figure
                        value={euro(a.commission_cents)}
                        ratio={tableCommissionTotal > 0 ? a.commission_cents / tableCommissionTotal : null}
                      />
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {agentsForTable.length === 0 && !summaryLoading && <EmptyBlock text="Nessuna persona in questa vista." />}
        </div>
      </div>

      {/* Contracts, with contact action */}
      <div className="panel rounded-3xl overflow-hidden">
        <div className="flex flex-wrap items-end justify-between gap-3 px-6 pt-6 sm:px-8">
          <div>
            <p className="kpi-label">Pratiche</p>
            <h3 className="mt-1 text-xl font-black tracking-tight text-white">Contratti della rete</h3>
          </div>
          <div className="subnav">
            <button type="button" className="subnav-pill" data-active={!onlyProblems} onClick={() => setOnlyProblems(false)}>
              Tutti
            </button>
            <button type="button" className="subnav-pill" data-active={onlyProblems} onClick={() => setOnlyProblems(true)}>
              Solo con problemi
            </button>
          </div>
        </div>
        {filteredContracts.length === 0 ? (
          <EmptyBlock text="Nessun contratto trovato." />
        ) : (
          <div className="overflow-x-auto px-2 pb-4 pt-2 sm:px-4">
            <table className="w-full border-collapse text-left text-sm">
              <thead>
                <tr>
                  <th className="px-4 py-3">Intestatario</th>
                  <th className="px-4 py-3">Fornitura</th>
                  <th className="px-4 py-3">Situazione</th>
                  <th className="px-4 py-3 text-right">Compenso</th>
                  <th className="px-4 py-3"></th>
                </tr>
              </thead>
              <tbody>
                {filteredContracts.map((c) => (
                  <tr key={c.contract_id}>
                    <td className="px-4 py-3">
                      <Identity name={c.customer_name} detail={<IdTag id={c.customer_id} />} />
                    </td>
                    <td className="px-4 py-3">
                      <Stack
                        title={c.product_name}
                        detail={[c.supply_point_label, c.producer_name ? `Venditore: ${c.producer_name}` : null].filter(Boolean).join(" · ")}
                      />
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex max-w-[280px] flex-col items-start gap-1.5">
                        <Chip
                          tone={c.is_problem ? "bad" : c.status === "ACTIVE" || c.status === "RENEWED" ? "ok" : "warn"}
                          live={!c.is_problem && c.status !== "ACTIVE" && c.status !== "RENEWED"}
                        >
                          {STATUS_LABELS[c.status] ?? c.status}
                        </Chip>
                        {c.is_problem && c.admin_note && (
                          <p className="whitespace-normal text-[11px] leading-snug text-danger-300">
                            <span className="font-bold uppercase tracking-wider">Nota amministrazione:</span> {c.admin_note}
                          </p>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex justify-end">
                        <Figure value={euro(c.commission_cents)} />
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <RowActions>
                        {c.customer_email && (
                          <a
                            href={`mailto:${c.customer_email}${c.is_problem ? `?subject=${encodeURIComponent("La tua fornitura SOSNET")}&body=${encodeURIComponent(c.admin_note ? `Ciao, per completare la tua fornitura serve: ${c.admin_note}` : "Ciao, ho notato che il tuo contratto è in attesa di documenti. Posso aiutarti a completarli?")}` : ""}`}
                            className={c.is_problem ? "act act-primary" : "act"}
                          >
                            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                            </svg>
                            Contatta
                          </a>
                        )}
                      </RowActions>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

/** Centred, friendly empty state. */
function EmptyBlock({ text }: { text: string }) {
  return (
    <div className="flex flex-col items-center gap-3 px-6 py-12 text-center">
      <span className="float-soft flex h-12 w-12 items-center justify-center rounded-2xl bg-brand-500/15 text-brand-300">
        <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 20h5v-2a4 4 0 00-3-3.87M9 20H4v-2a4 4 0 013-3.87m6-1.13a4 4 0 10-4-4 4 4 0 004 4zm6 0a4 4 0 10-4-4" />
        </svg>
      </span>
      <p className="text-sm text-surface-300">{text}</p>
    </div>
  );
}
