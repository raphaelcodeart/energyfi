"use client";

import { useEffect } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Chip, KpiTile } from "@/components/ui/data-cells";
import { Empty, Loading, SectionTitle } from "@/components/affiliate/shared";
import {
  affiliateGet, eur, num, OPERATION_LABELS, periodLabel, type AffiliateSummary, type LicenseRow, type Money,
} from "@/lib/affiliate";

/*
 * The purchases a Digital Ambassador made on Mamify, as last read from Mamify
 * (GET /affiliate/me/mamify-orders, local data, read only), with what each
 * one gave: points, licences, the month paid. Opening the console re-reads
 * one's own orders in the background (ambassador-panel useOwnOrdersRefresh).
 */

type MamifyOrderRow = {
  mamify_order_id: string;
  ordered_at: string | null;
  total: Money | null;
  status: string | null;
  paid: boolean | null;
  state: "RECEIVED" | "APPLIED" | "IGNORED" | "UNMATCHED" | "ERROR" | "CANCELLED";
  products: { name: string; quantity: number; price: number | null }[];
  bc_points: number;
  operations: { id: string; kind: string; status: string }[];
};

const STATE: Record<MamifyOrderRow["state"], { label: string; tone: "ok" | "warn" | "bad" | "muted" | "info" }> = {
  APPLIED: { label: "Registrato", tone: "ok" },
  RECEIVED: { label: "In lavorazione", tone: "info" },
  IGNORED: { label: "Non riguarda SOS", tone: "muted" },
  UNMATCHED: { label: "In verifica", tone: "warn" },
  ERROR: { label: "In verifica", tone: "warn" },
  CANCELLED: { label: "Annullato", tone: "bad" },
};

function when(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("it-IT", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

function useOwnMamifyOrders() {
  return useQuery({
    queryKey: ["affiliate", "me", "mamify-orders"],
    queryFn: () => affiliateGet<MamifyOrderRow[]>("/me/mamify-orders"),
    retry: false,
  });
}

/** Points and licences, no money: this month's points (opening it also
 * re-reads one's own Mamify orders in the background), the points the Mamify
 * orders gave, the licences bought and those still to assign. Renders nothing
 * for someone without a Digital Ambassador profile. */
export function PointsCounters() {
  const { data: orders } = useOwnMamifyOrders();
  const { data: me, error } = useQuery({
    queryKey: ["affiliate", "me"], queryFn: () => affiliateGet<AffiliateSummary>("/me"), retry: false,
  });
  const { data: licenses } = useQuery({
    queryKey: ["affiliate", "me", "licenses"], queryFn: () => affiliateGet<LicenseRow[]>("/me/licenses"), retry: false,
  });
  const qc = useQueryClient();
  const queued = me?.orders_check === "queued";
  useEffect(() => {
    if (!queued) return;
    const timer = setTimeout(() => void qc.invalidateQueries({ queryKey: ["affiliate"] }), 20_000);
    return () => clearTimeout(timer);
  }, [queued, qc]);
  if (error) return null;
  const orderPoints = (orders ?? []).reduce((sum, o) => sum + (o.bc_points || 0), 0);
  const owned = (licenses ?? []).filter((l) => l.status !== "VOID");
  const toAssign = owned.filter((l) => l.status === "AVAILABLE").length;
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <KpiTile label="Punti personali del mese" value={me ? num(me.career.bcp) : "—"} hint={me ? `BC · ${periodLabel(me.period)}` : "BC"} />
      <KpiTile label="Punti dai tuoi ordini" value={orders ? num(orderPoints) : "—"} hint="BC accreditati dagli ordini Mamify" />
      <KpiTile label="Licenze acquistate" value={licenses ? num(owned.length) : "—"} hint="Totale delle tue licenze" />
      <KpiTile label="Licenze da assegnare" value={licenses ? num(toAssign) : "—"} hint="Disponibili da rivendere a un'impresa" />
    </div>
  );
}

/** `quiet`: renders nothing for someone without a Digital Ambassador profile
 * (the customer "I tuoi ordini" page). */
export function MamifyOrders({ quiet = false }: { quiet?: boolean }) {
  const { data, isLoading, error } = useOwnMamifyOrders();
  if (isLoading) return quiet ? null : <Loading />;
  const list = data ?? [];
  if (quiet && error) return null;
  return (
    <div className="space-y-4">
    <PointsCounters />
    <div className="panel space-y-4 rounded-3xl p-5">
      <SectionTitle eyebrow="Acquisti su Mamify" title="I miei ordini Mamify" />
      <p className="text-xs text-surface-300">
        Gli ordini SOS Affiliate fatti su Mamify con il tuo account. Si aggiornano da soli quando apri la console: un acquisto appena fatto compare entro un minuto.
      </p>
      {error ? (
        <Empty>Ordini non disponibili: {(error as Error).message}</Empty>
      ) : list.length === 0 ? (
        <Empty>Nessun ordine SOS Affiliate trovato su Mamify per il tuo account.</Empty>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr>
                <th className="px-4 py-3">Ordine</th>
                <th className="px-4 py-3">Data</th>
                <th className="px-4 py-3">Prodotti</th>
                <th className="px-4 py-3 text-right">Totale</th>
                <th className="px-4 py-3 text-right">BC</th>
                <th className="px-4 py-3">Stato</th>
              </tr>
            </thead>
            <tbody>
              {list.map((o) => (
                <tr key={o.mamify_order_id}>
                  <td className="px-4 py-3"><span className="tag-id">#{o.mamify_order_id}</span></td>
                  <td className="px-4 py-3 whitespace-nowrap">{when(o.ordered_at)}</td>
                  <td className="px-4 py-3">
                    <p className="font-semibold text-white">
                      {o.products.map((p) => (p.quantity > 1 ? `${p.quantity} × ${p.name}` : p.name)).join(", ") || "—"}
                    </p>
                    <p className="text-xs text-surface-400">
                      {o.operations.map((op) => OPERATION_LABELS[op.kind] ?? op.kind).join(" · ") || (o.status ?? "")}
                    </p>
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums">{o.total != null ? eur(o.total) : "—"}</td>
                  <td className="px-4 py-3 text-right tabular-nums">{o.bc_points ? `+${num(o.bc_points)}` : "—"}</td>
                  <td className="px-4 py-3"><Chip tone={STATE[o.state]?.tone ?? "muted"}>{STATE[o.state]?.label ?? o.state}</Chip></td>
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
