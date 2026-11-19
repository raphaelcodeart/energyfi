"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { friendlyApiError } from "@/lib/api-error";
import { formatEuroCents as euro } from "@/lib/product-audience";
import { CALCULATION_LABELS, FALLBACK_LABELS, pctLabel } from "@/lib/commission-labels";
import { Chip, type ChipTone, Figure, Identity, KpiTile } from "@/components/ui/data-cells";
import { AgentPicker } from "@/components/agent-picker";
import type { ProductCatalogRead, SimulationRead } from "@/lib/types";

async function fetchProducts(): Promise<ProductCatalogRead[]> {
  const res = await fetch("/api/proxy/products");
  if (!res.ok) throw new Error("Impossibile caricare i prodotti.");
  return res.json();
}

function calcTone(type: string): ChipTone {
  if (type === "PERCENTAGE" || type === "MINIMUM_GUARANTEE") return "accent";
  if (type === "FIXED_AMOUNT") return "info";
  return "muted";
}

/**
 * Commission simulator: "if this product were sold today, who would earn
 * what?". The server computes it with the same engine as real sales; nothing
 * is written or calculated here.
 * A collaborator simulates their own sales (`agentId`); administrators pick
 * seller, date, amount, an optional referrer and even a draft plan to test
 * before activation (`adminMode`).
 */
export function CommissionSimulator({
  agentId,
  adminMode = false,
  planId,
}: {
  agentId?: string;
  adminMode?: boolean;
  planId?: string;
}) {
  const { data: products } = useQuery({ queryKey: ["simulator", "products"], queryFn: fetchProducts });

  const [sellerId, setSellerId] = useState(agentId ?? "");
  const [productId, setProductId] = useState("");
  const [soldAt, setSoldAt] = useState(() => new Date().toISOString().slice(0, 10));
  const [amount, setAmount] = useState("");
  const [promoterId, setPromoterId] = useState("");
  const [result, setResult] = useState<SimulationRead | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function simulate() {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await fetch("/api/proxy/commissions/simulate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          seller_agent_id: sellerId,
          product_id: productId,
          sold_at: new Date(`${soldAt}T12:00:00`).toISOString(),
          sale_amount_cents: amount.trim() ? Math.round(Number(amount.replace(",", ".")) * 100) : null,
          promoter_agent_id: promoterId || null,
          plan_id: planId ?? null,
        }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      setResult(await res.json());
    } catch (err: any) {
      setError(err.message || "Simulazione non riuscita.");
    } finally {
      setLoading(false);
    }
  }

  const field = "field w-full rounded-xl px-3 py-2 text-sm";

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {adminMode && (
          <label className="space-y-1 text-xs text-surface-300">
            <span>Venditore</span>
            <AgentPicker value={sellerId} onChange={(id) => setSellerId(id)} status="ACTIVE" ariaLabel="Venditore"
              placeholder="Scegli chi vende…" allowEmpty={false} required />
          </label>
        )}
        <label className="space-y-1 text-xs text-surface-300">
          <span>Prodotto</span>
          <select value={productId} onChange={(e) => setProductId(e.target.value)} className={field}>
            <option value="">Scegli il prodotto…</option>
            {(products ?? []).map((p) => (
              <option key={p.id} value={p.id}>{p.current_version?.name ?? p.code} ({p.code})</option>
            ))}
          </select>
        </label>
        <label className="space-y-1 text-xs text-surface-300">
          <span>Data della vendita</span>
          <input type="date" value={soldAt} onChange={(e) => setSoldAt(e.target.value)} className={field} />
        </label>
        <label className="space-y-1 text-xs text-surface-300">
          <span>Importo vendita, IVA esclusa (facoltativo)</span>
          <input inputMode="decimal" placeholder="prezzo di listino" value={amount} onChange={(e) => setAmount(e.target.value)} className={field} />
        </label>
        {adminMode && (
          <label className="space-y-1 text-xs text-surface-300">
            <span>Da una segnalazione di (facoltativo)</span>
            <AgentPicker value={promoterId} onChange={(id) => setPromoterId(id)} status="ACTIVE" ariaLabel="Da una segnalazione di"
              placeholder="Nessuna segnalazione" emptyLabel="Nessuna segnalazione" />
          </label>
        )}
      </div>
      <button
        onClick={simulate}
        disabled={loading || !sellerId || !productId}
        className="act act-primary !h-10 !px-5 !text-sm"
      >
        {loading ? "Calcolo…" : "Simula commissione"}
      </button>

      {error && <div className="rounded-xl border border-danger-500/30 bg-danger-500/15 p-3 text-xs text-danger-300">{error}</div>}

      {result && (
        <div className="rise space-y-4">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <KpiTile label="Margine disponibile" value={result.reference_margin_cents != null ? euro(result.reference_margin_cents) : "—"} />
            <KpiTile
              label="Piano applicato"
              value={<span className="text-lg">{result.plan ? `${result.plan.name} v${result.plan.version}` : "—"}</span>}
              hint={result.plan ? FALLBACK_LABELS[result.plan.fallback_strategy] : undefined}
            />
            <KpiTile label="Alla rete" value={euro(result.agents_cents)} />
            <KpiTile label="All'azienda" value={euro(result.company_cents)} />
          </div>

          {result.errors.map((e) => (
            <div key={e} className="rounded-xl border border-danger-500/30 bg-danger-500/15 p-3 text-xs text-danger-300">{e}</div>
          ))}
          {result.warnings.map((w) => (
            <div key={w} className="rounded-xl border border-warn-500/30 bg-warn-500/15 p-3 text-xs text-warn-300">{w}</div>
          ))}

          {result.rows.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr>
                    <th className="px-4 py-3">Chi riceve</th>
                    <th className="px-4 py-3">Titolo</th>
                    <th className="px-4 py-3">Metodo</th>
                    <th className="px-4 py-3 text-right">Quota</th>
                  </tr>
                </thead>
                <tbody>
                  {result.rows.map((r) => {
                    const margin = result.reference_margin_cents;
                    const ratio = margin != null && margin > 0 ? r.total_cents / margin : null;
                    return (
                      <tr key={r.key} title={r.explanation}>
                        <td className="px-4 py-3">
                          <Identity
                            name={r.name}
                            detail={r.role_code ? `${r.role_code}${r.depth != null ? ` · livello ${r.depth}` : ""}` : undefined}
                          />
                        </td>
                        <td className="px-4 py-3">
                          <div className="font-semibold text-white">{r.role}</div>
                          {r.fallback_applied && <div className="text-[10.5px] text-warn-300">{FALLBACK_LABELS[r.fallback_applied] ?? r.fallback_applied}</div>}
                        </td>
                        <td className="px-4 py-3">
                          <Chip tone={calcTone(r.calculation_type)}>{CALCULATION_LABELS[r.calculation_type] ?? r.calculation_type}</Chip>
                        </td>
                        <td className="px-4 py-3">
                          <div className="ml-auto w-fit">
                            <Figure
                              value={euro(r.total_cents)}
                              detail={ratio != null ? `${pctLabel((ratio * 100).toFixed(1))} del margine` : undefined}
                              ratio={ratio != null ? Math.max(0, Math.min(1, ratio)) : null}
                            />
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                  <tr>
                    <td className="px-4 py-3" colSpan={3}>
                      <span className="kpi-label">Totale distribuito</span>
                    </td>
                    <td className="px-4 py-3 text-right text-lg font-black tabular-nums text-white">{euro(result.distributed_cents)}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          )}
          {result.chain.length > 0 && (
            <p className="text-[11px] text-surface-400">
              Catena alla data: {result.chain.map((c) => `${c.name}${c.role_code ? ` (${c.role_code})` : ""}${c.status !== "ACTIVE" ? " – non attivo" : ""}`).join(" → ")}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
