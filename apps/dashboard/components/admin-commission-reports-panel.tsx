"use client";

import { type CSSProperties, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { friendlyApiError } from "@/lib/api-error";
import { downloadCsv } from "@/lib/csv-export";
import { formatEuroCents as euro } from "@/lib/product-audience";
import { MOVEMENT_STATUS_LABELS } from "@/lib/commission-labels";
import { Chip, Figure, Identity, KpiTile, Orb } from "@/components/ui/data-cells";
import type { CommercialRoleRead, CommissionReportRead, ProductCatalogRead, ProductCategoryRead, ReportBucket, SplitPlanRead } from "@/lib/types";

async function getJson<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(await friendlyApiError(res));
  return res.json();
}

const COLUMN_ORDER: (keyof ReportBucket)[] = ["commission_cents", "margin_cents", "revenue_cents", "company_cents", "sales"];

const COLUMN_LABELS: Partial<Record<keyof ReportBucket, string>> = {
  sales: "Vendite", revenue_cents: "Giro d'affari", margin_cents: "Margine", commission_cents: "Alla rete", company_cents: "All'azienda",
};

function Table({ title, rows, columns }: { title: string; rows: ReportBucket[]; columns: (keyof ReportBucket)[] }) {
  const ordered = COLUMN_ORDER.filter((c) => columns.includes(c));
  const commissionTotal = rows.reduce((a, r) => a + (r.commission_cents ?? 0), 0);
  const hasMargin = columns.includes("margin_cents");
  return (
    <section className="panel rounded-3xl p-5">
      <p className="kpi-label">Spaccato</p>
      <h4 className="mt-1 text-lg font-black tracking-tight text-white">{title}</h4>
      <div className="mt-3 overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead>
            <tr>
              <th className="px-4 py-3">Voce</th>
              {ordered.map((c) => <th key={c} className="px-4 py-3 text-right">{COLUMN_LABELS[c]}</th>)}
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr>
                <td colSpan={ordered.length + 1} className="px-4 py-8">
                  <div className="flex flex-col items-center gap-2 text-center text-surface-400">
                    <Orb name="vuoto" icon={<span className="text-sm">∅</span>} />
                    <span className="text-sm">Nessun dato nel periodo scelto.</span>
                  </div>
                </td>
              </tr>
            )}
            {rows.map((r) => {
              const label = MOVEMENT_STATUS_LABELS[r.key] ?? r.key;
              const commission = r.commission_cents ?? 0;
              const margin = r.margin_cents ?? 0;
              const ratio = hasMargin
                ? (margin > 0 ? commission / margin : null)
                : (commissionTotal > 0 ? commission / commissionTotal : null);
              return (
                <tr key={r.key}>
                  <td className="px-4 py-3"><Identity name={label} detail={label !== r.key ? r.key : undefined} /></td>
                  {ordered.map((c) => (
                    <td key={c} className="px-4 py-3 text-right tabular-nums">
                      {c === "commission_cents" ? (
                        <div className="ml-auto w-fit">
                          <Figure
                            value={euro(commission)}
                            detail={ratio != null ? `${Math.round(ratio * 100)}% ${hasMargin ? "del margine" : "del totale"}` : undefined}
                            ratio={ratio != null ? Math.min(1, ratio) : null}
                          />
                        </div>
                      ) : c === "sales" ? (
                        <span className="font-bold text-white">{r.sales ?? 0}</span>
                      ) : (
                        <span className="text-surface-300">{euro(Number(r[c] ?? 0))}</span>
                      )}
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

/**
 * Management reports built from already-computed movements, filterable by
 * period (sale date), product, category, role, plan, level and status. No
 * figure is recomputed here.
 */
export function AdminCommissionReportsPanel() {
  const today = new Date();
  const [filters, setFilters] = useState({
    date_from: new Date(today.getFullYear(), today.getMonth() - 2, 1).toISOString().slice(0, 10),
    date_to: "",
    product_id: "", category_id: "", role_code: "", plan_id: "", level: "", status_filter: "",
  });
  const qs = new URLSearchParams();
  Object.entries(filters).forEach(([k, v]) => {
    if (!v) return;
    qs.set(k, k.startsWith("date_") ? new Date(`${v}T00:00:00`).toISOString() : v);
  });
  const { data: report, isLoading, error } = useQuery({
    queryKey: ["admin", "commission-report", qs.toString()],
    queryFn: () => getJson<CommissionReportRead>(`/api/proxy/commissions/reports?${qs.toString()}`),
  });
  const { data: products } = useQuery({ queryKey: ["admin", "products"], queryFn: () => getJson<ProductCatalogRead[]>("/api/proxy/products") });
  const { data: categories } = useQuery({ queryKey: ["commercial", "categories"], queryFn: () => getJson<ProductCategoryRead[]>("/api/proxy/commercial/categories") });
  const { data: roles } = useQuery({ queryKey: ["commercial", "roles"], queryFn: () => getJson<CommercialRoleRead[]>("/api/proxy/commercial/roles") });
  const { data: plans } = useQuery({ queryKey: ["admin", "split-plans"], queryFn: () => getJson<SplitPlanRead[]>("/api/proxy/commissions/plans") });

  const field = "field rounded-xl px-3 py-2 text-xs";
  const t = report?.totals;

  function exportCsv() {
    if (!report) return;
    const rows: (string | number)[][] = [];
    for (const [section, list] of Object.entries({
      "Ruolo venditore": report.by_seller_role, Prodotto: report.by_product, Categoria: report.by_category,
      Livello: report.by_level, Piano: report.by_plan, Stato: report.by_status,
    })) {
      for (const r of list) {
        rows.push([section, r.key, r.sales ?? "", ((r.revenue_cents ?? 0) / 100).toFixed(2), ((r.margin_cents ?? 0) / 100).toFixed(2),
          ((r.commission_cents ?? 0) / 100).toFixed(2), ((r.company_cents ?? 0) / 100).toFixed(2)]);
      }
    }
    downloadCsv(`report_provvigioni_${new Date().toISOString().slice(0, 10)}`,
      ["Sezione", "Voce", "Vendite", "Fatturato", "Margine", "Provvigioni", "Quota azienda"], rows);
  }

  return (
    <div className="space-y-5">
      <div className="panel flex flex-wrap items-end gap-2 rounded-3xl p-5 text-xs text-surface-300">
        <label className="space-y-1"><span className="block">Vendite dal</span><input type="date" className={field} value={filters.date_from} onChange={(e) => setFilters({ ...filters, date_from: e.target.value })} /></label>
        <label className="space-y-1"><span className="block">al (escluso)</span><input type="date" className={field} value={filters.date_to} onChange={(e) => setFilters({ ...filters, date_to: e.target.value })} /></label>
        <select className={field} value={filters.product_id} onChange={(e) => setFilters({ ...filters, product_id: e.target.value })}>
          <option value="">Tutti i prodotti</option>
          {(products ?? []).map((p) => <option key={p.id} value={p.id}>{p.code}</option>)}
        </select>
        <select className={field} value={filters.category_id} onChange={(e) => setFilters({ ...filters, category_id: e.target.value })}>
          <option value="">Tutte le categorie</option>
          {(categories ?? []).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
        <select className={field} value={filters.role_code} onChange={(e) => setFilters({ ...filters, role_code: e.target.value })}>
          <option value="">Tutti i ruoli</option>
          {(roles ?? []).map((r) => <option key={r.id} value={r.code}>{r.name}</option>)}
        </select>
        <select className={field} value={filters.plan_id} onChange={(e) => setFilters({ ...filters, plan_id: e.target.value })}>
          <option value="">Tutti i piani</option>
          {(plans ?? []).filter((p) => p.status !== "DRAFT").map((p) => <option key={p.id} value={p.id}>{p.name} v{p.version}</option>)}
        </select>
        <input className={`${field} w-24`} placeholder="Livello" inputMode="numeric" value={filters.level} onChange={(e) => setFilters({ ...filters, level: e.target.value.replace(/\D/g, "") })} />
        <select className={field} value={filters.status_filter} onChange={(e) => setFilters({ ...filters, status_filter: e.target.value })}>
          <option value="">Tutti gli stati</option>
          {["PENDING", "APPROVED", "PAYABLE", "PAID", "RETAINED"].map((s) => <option key={s} value={s}>{MOVEMENT_STATUS_LABELS[s]}</option>)}
        </select>
        <button onClick={exportCsv} className="act ml-auto">Esporta CSV</button>
      </div>

      {error && <p className="text-sm text-danger-300">Impossibile caricare il report.</p>}
      {isLoading && <p className="text-sm text-surface-400">Caricamento…</p>}

      {t && (
        <div className="stagger grid grid-cols-2 gap-4 md:grid-cols-5">
          {[
            ["Vendite", String(t.sales)],
            ["Giro d'affari", euro(t.revenue_cents)],
            ["Margine", euro(t.margin_cents)],
            ["Alla rete", euro(t.commissions_cents)],
            ["All'azienda", euro(t.company_cents)],
          ].map(([label, value], i) => (
            <div key={label} style={{ "--i": i } as CSSProperties}>
              <KpiTile label={label ?? ""} value={value} hint={label === "Alla rete" ? "provvigioni alla rete" : label === "All'azienda" ? "quota azienda" : label === "Giro d'affari" ? "fatturato" : undefined} />
            </div>
          ))}
        </div>
      )}
      {t && (
        <div className="flex flex-wrap gap-2">
          <Chip tone="accent">Dirette {euro(t.direct_cents)}</Chip>
          <Chip tone="info">Indirette {euro(t.indirect_cents)}</Chip>
          <Chip tone="info">Fee segnalazioni {euro(t.promoter_fee_cents)}</Chip>
          {t.reversal_cents !== 0 && <Chip tone="bad">Storni {euro(t.reversal_cents)}</Chip>}
        </div>
      )}

      {report && (
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
          <Table title="Per ruolo del venditore" rows={report.by_seller_role} columns={["sales", "revenue_cents", "margin_cents", "commission_cents", "company_cents"]} />
          <Table title="Per prodotto" rows={report.by_product} columns={["sales", "revenue_cents", "margin_cents", "commission_cents", "company_cents"]} />
          <Table title="Per categoria" rows={report.by_category} columns={["sales", "revenue_cents", "margin_cents"]} />
          <Table title="Per piano" rows={report.by_plan} columns={["commission_cents", "company_cents"]} />
          <Table title="Per livello di rete" rows={report.by_level} columns={["commission_cents"]} />
          <Table title="Per ruolo di chi riceve" rows={report.by_beneficiary_role} columns={["commission_cents"]} />
          <Table title="Per stato" rows={report.by_status} columns={["commission_cents"]} />
        </div>
      )}
    </div>
  );
}
