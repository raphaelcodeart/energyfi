"use client";

import { sectionEnabled, useFeatures } from "@/lib/features";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type {
  AttentionItem,
  DashboardSummary,
  OrganizationNetworkLevelsRead,
  RecentActivityItem,
  TimeseriesPoint,
} from "@/lib/types";
import { axisProps, tooltipStyles, useChartTheme } from "@/lib/chart-theme";
import { Chip, IdTag, KpiTile } from "@/components/ui/data-cells";

type PeriodKey = "today" | "7d" | "month" | "quarter" | "year";

const PERIODS: { key: PeriodKey; label: string; days: number }[] = [
  { key: "today", label: "Oggi", days: 1 },
  { key: "7d", label: "7 giorni", days: 7 },
  { key: "month", label: "Mese", days: 30 },
  { key: "quarter", label: "Trimestre", days: 90 },
  { key: "year", label: "Anno", days: 365 },
];

const STATUS_LABELS: Record<string, string> = {
  SUBMITTED: "Inviata",
  DOCUMENTS_PENDING: "Documenti mancanti",
  UNDER_REVIEW: "In revisione",
};

const ACTION_LABELS: Record<string, string> = {
  "login.success": "Accesso effettuato",
  "contract.transition": "Cambio stato contratto",
  "contract.create": "Contratto creato",
};

function euro(cents: number): string {
  return (cents / 100).toLocaleString("it-IT", { style: "currency", currency: "EUR" });
}

function periodBounds(days: number): { period_from: string; period_to: string } {
  const to = new Date();
  const from = new Date(to.getTime() - days * 24 * 60 * 60 * 1000);
  return { period_from: from.toISOString().slice(0, 10), period_to: to.toISOString().slice(0, 10) };
}

async function fetchSummary(days: number): Promise<DashboardSummary> {
  const { period_from, period_to } = periodBounds(days);
  const res = await fetch(`/api/proxy/reports/dashboard-summary?period_from=${period_from}&period_to=${period_to}`);
  if (!res.ok) throw new Error("Impossibile caricare il riepilogo.");
  return res.json();
}

async function fetchContractsTimeseries(): Promise<TimeseriesPoint[]> {
  const res = await fetch("/api/proxy/reports/contracts-timeseries?months=12");
  if (!res.ok) throw new Error("Impossibile caricare l'andamento contratti.");
  return res.json();
}

async function fetchCommissionsTimeseries(): Promise<TimeseriesPoint[]> {
  const res = await fetch("/api/proxy/reports/commissions-timeseries?months=12");
  if (!res.ok) throw new Error("Impossibile caricare l'andamento provvigioni.");
  return res.json();
}

async function fetchAttentionItems(): Promise<AttentionItem[]> {
  const res = await fetch("/api/proxy/reports/attention-items");
  if (!res.ok) throw new Error("Impossibile caricare le segnalazioni.");
  return res.json();
}

async function fetchRecentActivity(): Promise<RecentActivityItem[]> {
  const res = await fetch("/api/proxy/reports/recent-activity?limit=10");
  if (!res.ok) throw new Error("Impossibile caricare l'attività recente.");
  return res.json();
}

async function fetchNetworkLevels(): Promise<OrganizationNetworkLevelsRead> {
  const res = await fetch("/api/proxy/network/organization/levels");
  if (!res.ok) throw new Error("Impossibile caricare i livelli della rete.");
  return res.json();
}

function monthLabel(period: string): string {
  const [y, m] = period.split("-");
  return new Date(Number(y), Number(m) - 1, 1).toLocaleDateString("it-IT", { month: "short" });
}

function Icon({ d, className = "h-5 w-5" }: { d: string; className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.9} d={d} />
    </svg>
  );
}

const ICONS = {
  contracts:
    "M9 17V7m0 10a2 2 0 01-2 2H5a2 2 0 01-2-2V7a2 2 0 012-2h2a2 2 0 012 2m0 10a2 2 0 002 2h2a2 2 0 002-2M9 7a2 2 0 012-2h2a2 2 0 012 2m0 10V7m0 10a2 2 0 002 2h2a2 2 0 002-2V7a2 2 0 00-2-2h-2a2 2 0 00-2 2",
  plus: "M12 4v16m8-8H4",
  user: "M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z",
  team: "M17 20h5v-2a4 4 0 00-3-3.87M9 20H4v-2a4 4 0 013-3.87m6-1.13a4 4 0 10-4-4 4 4 0 004 4zm6 0a4 4 0 10-4-4",
  box: "M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4",
  network:
    "M9 3H5a2 2 0 00-2 2v4m6-6h10a2 2 0 012 2v4M9 3v18m0 0H5a2 2 0 01-2-2v-4m6 6h10a2 2 0 002-2v-4m0-6h-6m6 0v6m0-6l-8 8",
  orders: "M16.5 7.5h-9v9h9v-9zM3 6a3 3 0 013-3h12a3 3 0 013 3v12a3 3 0 01-3 3H6a3 3 0 01-3-3V6z",
  check: "M9 14l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z",
  coin: "M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V6m0 10v2M21 12a9 9 0 11-18 0 9 9 0 0118 0z",
  chat: "M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z",
  ledger: "M9 7h6m-6 4h6m-6 4h4M5 3h14a2 2 0 012 2v14a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2z",
  tick: "M5 13l4 4L19 7",
  clock: "M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z",
  cross: "M6 18L18 6M6 6l12 12",
  lock: "M17 9V7a4 4 0 00-8 0v2m-2 0h12a2 2 0 012 2v7a2 2 0 01-2 2H7a2 2 0 01-2-2v-7a2 2 0 012-2z",
  bolt: "M13 10V3L4 14h7v7l9-11h-7z",
} as const;

const QUICK_LINKS: { key: string; label: string; description: string; icon: string }[] = [
  { key: "list", label: "Contratti", description: "Tutti i contratti", icon: ICONS.contracts },
  { key: "create", label: "Nuovo", description: "Nuova proposta di contratto", icon: ICONS.plus },
  { key: "customers", label: "Clienti", description: "Anagrafiche", icon: ICONS.user },
  { key: "promoters", label: "Promoter", description: "Collaboratori", icon: ICONS.team },
  { key: "products", label: "Prodotti", description: "Catalogo", icon: ICONS.box },
  { key: "network", label: "Rete", description: "Rete commerciale: albero promoter", icon: ICONS.network },
  { key: "orders", label: "Ordini", description: "Acquisti Shop", icon: ICONS.orders },
  { key: "invoice-redemptions", label: "Riscatti", description: "Riscatti fatture da confermare", icon: ICONS.check },
  { key: "commissions", label: "Provvigioni", description: "Movimenti provvigionali", icon: ICONS.coin },
  { key: "tickets", label: "Ticket", description: "Ticket di supporto: richieste aperte", icon: ICONS.chat },
  { key: "accounting", label: "Contabilità", description: "Movimenti contabili", icon: ICONS.ledger },
];

function percent(part: number, total: number): string {
  if (!total) return "0%";
  return `${Math.round((part / total) * 100)}%`;
}

/** KPI hint with a small leading icon. */
function Hint({ icon, children }: { icon: string; children: React.ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <Icon d={icon} className="h-3.5 w-3.5 text-white/80" />
      {children}
    </span>
  );
}

/** Clickable signal row inside the money/people consoles. */
function Signal({
  label,
  value,
  detail,
  icon,
  onClick,
}: {
  label: string;
  value: string;
  detail?: React.ReactNode;
  icon: string;
  onClick?: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="group flex w-full cursor-pointer items-center gap-4 rounded-2xl bg-white/[0.04] px-4 py-3.5 text-left ring-1 ring-white/10 transition hover:bg-white/10 hover:ring-white/30"
    >
      <span className="grid h-11 w-11 shrink-0 place-items-center rounded-2xl bg-gradient-to-br from-brand-500 to-accent-500 text-white shadow-lg shadow-brand-900/40 transition group-hover:rotate-6 group-hover:scale-110">
        <Icon d={icon} />
      </span>
      <span className="min-w-0 flex-1">
        <span className="kpi-label block truncate">{label}</span>
        {detail && <span className="mt-0.5 block truncate text-[11px] text-surface-400">{detail}</span>}
      </span>
      <span className="shrink-0 text-2xl font-black tabular-nums tracking-tight text-white">{value}</span>
      <Icon d="M9 5l7 7-7 7" className="h-4 w-4 shrink-0 text-surface-400 transition group-hover:translate-x-1 group-hover:text-white" />
    </button>
  );
}

function SectionHead({ eyebrow, title, children }: { eyebrow: string; title: string; children?: React.ReactNode }) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-4">
      <div>
        <p className="kpi-label">{eyebrow}</p>
        <h4 className="mt-1 text-xl font-black tracking-tight text-white">{title}</h4>
      </div>
      {children}
    </div>
  );
}

export function AdminOverviewPanel({ onNavigate }: { onNavigate?: (key: string, filter?: string) => void }) {
  const features = useFeatures();
  const chart = useChartTheme();
  const [period, setPeriod] = useState<PeriodKey>("month");
  const activeDays = PERIODS.find((p) => p.key === period)!.days;

  const { data: summary, error: summaryError, isLoading: summaryLoading } = useQuery({
    queryKey: ["admin", "reports", "summary", activeDays],
    queryFn: () => fetchSummary(activeDays),
  });
  const { data: contractsSeries } = useQuery({
    queryKey: ["admin", "reports", "contracts-timeseries"],
    queryFn: fetchContractsTimeseries,
  });
  const { data: commissionsSeries } = useQuery({
    queryKey: ["admin", "reports", "commissions-timeseries"],
    queryFn: fetchCommissionsTimeseries,
  });
  const { data: attentionItems } = useQuery({
    queryKey: ["admin", "reports", "attention-items"],
    queryFn: fetchAttentionItems,
  });
  const { data: recentActivity } = useQuery({
    queryKey: ["admin", "reports", "recent-activity"],
    queryFn: fetchRecentActivity,
  });
  const { data: networkLevels } = useQuery({
    queryKey: ["admin", "network", "levels"],
    queryFn: fetchNetworkLevels,
  });

  const networkLevelsChartData = Object.entries(networkLevels?.people_by_level ?? {})
    .map(([depth, count]) => ({ depth: Number(depth), Persone: count }))
    .sort((a, b) => a.depth - b.depth)
    .map((row) => ({ name: row.depth === 0 ? "Livello 0 (root)" : `Livello ${row.depth}`, Persone: row.Persone }));

  const contractsChartData = (contractsSeries ?? []).map((p) => ({ ...p, label: monthLabel(p.period) }));
  const commissionsChartData = (commissionsSeries ?? []).map((p) => ({
    ...p,
    label: monthLabel(p.period),
    euro: p.value / 100,
  }));

  const loadingText = "…";
  const total = summary?.contracts.total ?? 0;
  const active = summary?.contracts.active ?? 0;
  const pending = summary?.contracts.pending_approval ?? 0;
  const closed = (summary?.contracts.rejected ?? 0) + (summary?.contracts.cancelled ?? 0);
  const accrued = summary?.commissions.accrued_cents ?? 0;
  const paid = summary?.commissions.paid_cents ?? 0;
  const paidRatio = accrued + paid > 0 ? paid / (accrued + paid) : 0;
  const periodLabel = PERIODS.find((p) => p.key === period)?.label ?? "";

  return (
    <div className="space-y-6">
      {/* Cockpit header: title and period switcher */}
      <div className="rise flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="kpi-label">Cabina di regia</p>
          <h3 className="mt-1 text-3xl font-black tracking-tight text-white sm:text-4xl">
            Il polso della <span className="text-gradient">rete</span>
          </h3>
        </div>
        <div className="subnav" role="tablist" aria-label="Periodo">
          {PERIODS.map((p) => (
            <button
              key={p.key}
              type="button"
              role="tab"
              aria-selected={period === p.key}
              data-active={period === p.key}
              onClick={() => setPeriod(p.key)}
              className="subnav-pill"
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>

      {summaryError && (
        <p className="panel rounded-2xl px-4 py-3 text-sm text-danger-300">
          Impossibile caricare il riepilogo. Riprova più tardi.
        </p>
      )}

      {/* Hero row: contract KPIs as large tilting tiles */}
      <div className="stagger grid grid-cols-2 gap-4 lg:grid-cols-4">
        <div className="grid" style={{ "--i": 0 } as React.CSSProperties}>
          <KpiTile
            label="Contratti totali"
            value={summaryLoading ? loadingText : String(total)}
            hint={<Hint icon={ICONS.contracts}>Archivio completo</Hint>}
            onClick={() => onNavigate?.("list", "ALL")}
          />
        </div>
        <div className="grid" style={{ "--i": 1 } as React.CSSProperties}>
          <KpiTile
            label="Contratti attivi"
            value={summaryLoading ? loadingText : String(active)}
            hint={<Hint icon={ICONS.tick}>{percent(active, total)} del totale</Hint>}
            onClick={() => onNavigate?.("list", "ACTIVE")}
          />
        </div>
        <div className="grid" style={{ "--i": 2 } as React.CSSProperties}>
          <KpiTile
            label="In attesa di approvazione"
            value={summaryLoading ? loadingText : String(pending)}
            hint={<Hint icon={ICONS.clock}>Da valutare</Hint>}
            onClick={() => onNavigate?.("list", "PENDING_APPROVAL")}
          />
        </div>
        <div className="grid" style={{ "--i": 3 } as React.CSSProperties}>
          <KpiTile
            label="Respinti / cessati"
            value={summaryLoading ? loadingText : String(closed)}
            hint={<Hint icon={ICONS.cross}>{percent(closed, total)} del totale</Hint>}
            onClick={() => onNavigate?.("list", "REJECTED_CANCELLED")}
          />
        </div>
      </div>

      {/* Launch strip: compact quick actions */}
      <div className="panel rise rounded-3xl px-4 py-3">
        <div className="flex items-center gap-3">
          <span className="hidden shrink-0 items-center gap-2 pr-2 sm:inline-flex">
            <span className="grid h-8 w-8 place-items-center rounded-xl bg-white text-brand-600">
              <Icon d={ICONS.bolt} className="h-4 w-4" />
            </span>
            <span className="kpi-label">Avvio rapido</span>
          </span>
          <div className="flex flex-1 gap-1.5 overflow-x-auto pb-1 pt-1 [scrollbar-width:none]">
            {QUICK_LINKS.filter((link) => sectionEnabled(link.key, features)).map((link) => (
              <button
                key={link.key}
                type="button"
                title={link.description}
                aria-label={`${link.label}: ${link.description}`}
                onClick={() => onNavigate?.(link.key)}
                className="group flex w-[68px] shrink-0 cursor-pointer flex-col items-center gap-1.5 rounded-2xl px-1 py-2 transition hover:bg-white/10"
              >
                <span
                  className={`grid h-10 w-10 place-items-center rounded-2xl ring-1 transition duration-300 group-hover:-translate-y-1 group-hover:rotate-[-8deg] group-hover:scale-110 ${
                    link.key === "create"
                      ? "bg-gradient-to-br from-brand-500 to-accent-500 text-white ring-white/30 shadow-lg shadow-brand-900/50"
                      : "bg-white/[0.06] text-surface-200 ring-white/15 group-hover:bg-white group-hover:text-brand-600"
                  }`}
                >
                  <Icon d={link.icon} />
                </span>
                <span className="w-full truncate text-center text-[10.5px] font-bold text-surface-300 group-hover:text-white">
                  {link.label}
                </span>
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Money and people consoles */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-5">
        <div className="panel rounded-3xl p-6 lg:col-span-3">
          <SectionHead eyebrow={`Periodo: ${periodLabel}`} title="Flusso provvigioni">
            <div className="text-right">
              <p className="kpi-label">Quota pagata</p>
              <p className="mt-1 text-2xl font-black tabular-nums text-white">
                {summaryLoading ? loadingText : percent(paid, accrued + paid)}
              </p>
            </div>
          </SectionHead>
          <div className="meter mb-5 h-2">
            <i style={{ width: `${Math.max(3, paidRatio * 100)}%` }} />
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Signal
              label="Provvigioni maturate"
              value={summaryLoading ? loadingText : euro(accrued)}
              detail="In attesa di pagamento"
              icon={ICONS.coin}
              onClick={() => onNavigate?.("commissions", "ACCRUED")}
            />
            <Signal
              label="Provvigioni pagate"
              value={summaryLoading ? loadingText : euro(paid)}
              detail="Liquidate"
              icon={ICONS.lock}
              onClick={() => onNavigate?.("commissions", "PAID")}
            />
          </div>
        </div>

        <div className="panel rounded-3xl p-6 lg:col-span-2">
          <SectionHead eyebrow="Persone" title="Chi è in campo" />
          <div className="space-y-3">
            <Signal
              label="Promoter attivi"
              value={summaryLoading ? loadingText : String(summary?.active_promoters ?? 0)}
              icon={ICONS.team}
              onClick={() => onNavigate?.("promoters", "ACTIVE")}
            />
            <Signal
              label="Clienti attivi"
              value={summaryLoading ? loadingText : String(summary?.active_customers ?? 0)}
              icon={ICONS.user}
              onClick={() => onNavigate?.("customers", "ACTIVE")}
            />
          </div>
        </div>
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div className="panel rounded-3xl p-6">
          <SectionHead eyebrow="Ultimi 12 mesi" title="Andamento contratti" />
          <ResponsiveContainer width="100%" height={240}>
            <AreaChart data={contractsChartData} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
              <defs>
                <linearGradient id="ovContractsStroke" x1="0" y1="0" x2="1" y2="0">
                  <stop offset="0%" stopColor="#216eff" />
                  <stop offset="60%" stopColor="#47e2ff" />
                  <stop offset="100%" stopColor="#ffffff" />
                </linearGradient>
                <linearGradient id="ovContractsFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#47e2ff" stopOpacity={0.55} />
                  <stop offset="55%" stopColor="#216eff" stopOpacity={0.18} />
                  <stop offset="100%" stopColor="#216eff" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="2 6" stroke={chart.grid} vertical={false} />
              <XAxis dataKey="label" {...axisProps(chart)} />
              <YAxis allowDecimals={false} {...axisProps(chart)} />
              <Tooltip
                cursor={{ stroke: "rgba(255,255,255,0.35)", strokeDasharray: "3 3" }}
                {...tooltipStyles(chart)}
                formatter={(value) => [String(value), "Contratti"]}
              />
              <Area
                type="monotone"
                dataKey="value"
                stroke="url(#ovContractsStroke)"
                strokeWidth={3}
                fill="url(#ovContractsFill)"
                dot={false}
                activeDot={{ r: 5, fill: "#fff", stroke: "#47e2ff", strokeWidth: 3 }}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        <div className="panel rounded-3xl p-6">
          <SectionHead eyebrow="Ultimi 12 mesi" title="Andamento provvigioni" />
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={commissionsChartData} margin={{ top: 8, right: 8, left: -4, bottom: 0 }}>
              <defs>
                <linearGradient id="ovCommissionsBar" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#ffffff" />
                  <stop offset="35%" stopColor="#47e2ff" />
                  <stop offset="100%" stopColor="#216eff" stopOpacity={0.55} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="2 6" stroke={chart.grid} vertical={false} />
              <XAxis dataKey="label" {...axisProps(chart)} />
              <YAxis {...axisProps(chart)} />
              <Tooltip
                cursor={{ fill: "rgba(255,255,255,0.06)" }}
                {...tooltipStyles(chart)}
                formatter={(value) => [euro(Math.round(Number(value) * 100)), "Provvigioni"]}
              />
              <Bar dataKey="euro" fill="url(#ovCommissionsBar)" radius={[10, 10, 3, 3]} maxBarSize={28} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Network levels across the whole organization (no single root, unlike the
         promoter's branch-scoped "La mia Azienda"). */}
      <div className="panel rounded-3xl p-6">
        <SectionHead eyebrow="Rete commerciale" title="Livelli e persone">
          <div className="flex gap-6">
            <div className="text-right">
              <p className="kpi-label">Persone totali</p>
              <p className="mt-1 text-2xl font-black tabular-nums text-white">{networkLevels?.people_total ?? 0}</p>
            </div>
            <div className="text-right">
              <p className="kpi-label">Livelli totali</p>
              <p className="mt-1 text-2xl font-black tabular-nums text-white">{networkLevels?.levels_total ?? 0}</p>
            </div>
          </div>
        </SectionHead>
        {networkLevelsChartData.length > 0 && (
          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={networkLevelsChartData} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
                <defs>
                  <linearGradient id="ovLevelsBar" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#85eeff" />
                    <stop offset="100%" stopColor="#216eff" stopOpacity={0.6} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="2 6" stroke={chart.grid} vertical={false} />
                <XAxis dataKey="name" {...axisProps(chart)} />
                <YAxis allowDecimals={false} {...axisProps(chart)} />
                <Tooltip cursor={{ fill: "rgba(255,255,255,0.06)" }} {...tooltipStyles(chart)} />
                <Bar dataKey="Persone" fill="url(#ovLevelsBar)" radius={[10, 10, 3, 3]} maxBarSize={48} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>

      {/* Attention items and recent activity */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div className="panel rounded-3xl p-6">
          <SectionHead eyebrow="Radar" title="Richiede attenzione">
            {attentionItems && attentionItems.length > 0 && (
              <Chip tone="warn" live>
                {attentionItems.length} da verificare
              </Chip>
            )}
          </SectionHead>
          <div className="space-y-2">
            {attentionItems === undefined ? (
              <p className="py-6 text-center text-xs text-surface-400">Caricamento...</p>
            ) : attentionItems.length === 0 ? (
              <div className="flex flex-col items-center gap-2 py-8 text-center">
                <span className="grid h-12 w-12 place-items-center rounded-2xl bg-white/10 text-white">
                  <Icon d={ICONS.tick} />
                </span>
                <p className="text-sm text-surface-300">Nessuna anomalia rilevata.</p>
              </div>
            ) : (
              attentionItems.map((item) => (
                <div
                  key={item.contract_id}
                  className="flex items-center gap-3 rounded-2xl bg-white/[0.04] px-4 py-3 ring-1 ring-warn-400/20 transition hover:bg-white/[0.08]"
                >
                  <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-warn-400/15 text-sm font-black tabular-nums text-warn-300">
                    {item.days_in_status}g
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <IdTag id={item.contract_id} />
                      <span className="truncate text-[12px] font-semibold text-white">
                        {STATUS_LABELS[item.status] ?? item.status}
                      </span>
                    </div>
                    <p className="mt-0.5 text-[11px] text-surface-400">Fermo da {item.days_in_status} giorni</p>
                  </div>
                  <Chip tone="warn" live>
                    Verifica
                  </Chip>
                </div>
              ))
            )}
          </div>
        </div>

        <div className="panel rounded-3xl p-6">
          <SectionHead eyebrow="Diario" title="Attività recente" />
          {recentActivity === undefined ? (
            <p className="py-6 text-center text-xs text-surface-400">Caricamento...</p>
          ) : recentActivity.length === 0 ? (
            <div className="flex flex-col items-center gap-2 py-8 text-center">
              <span className="grid h-12 w-12 place-items-center rounded-2xl bg-white/10 text-white">
                <Icon d={ICONS.clock} />
              </span>
              <p className="text-sm text-surface-300">Nessuna attività registrata.</p>
            </div>
          ) : (
            <ol className="relative ml-2 space-y-3 border-l border-white/15 pl-5">
              {recentActivity.map((item) => (
                <li key={item.id} className="relative">
                  <span className="absolute -left-[26px] top-1.5 h-2.5 w-2.5 rounded-full bg-gradient-to-br from-white to-accent-400 shadow-[0_0_10px_rgba(71, 226, 255,0.8)]" />
                  <p className="truncate text-[13px] font-semibold text-white">
                    {ACTION_LABELS[item.action] ?? item.action}
                  </p>
                  <p className="text-[11px] text-surface-400">
                    {item.entity_type} · {new Date(item.created_at).toLocaleString("it-IT")}
                  </p>
                </li>
              ))}
            </ol>
          )}
        </div>
      </div>
    </div>
  );
}
