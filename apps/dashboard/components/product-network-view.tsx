"use client";

import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { NetworkChart, type TreeNode } from "@/components/network-chart";
import { Chip, Figure, Identity, KpiTile } from "@/components/ui/data-cells";

/*
 * "La mia rete per questo prodotto": the collaborator's network filtered to
 * the people who actually bought one product, down to the depth its company
 * reaches. The full network stays as it is elsewhere; this is a lens on it.
 */

type ProductNetworkRead = {
  product: { id: string; name: string; image_url: string | null };
  company: { id: string; name: string; max_network_depth: number | null } | null;
  depth_limit: number;
  tree: TreeNode | null;
  levels: { depth: number; buyers: number; contracts: number; value_cents: number }[];
  buyers: { key: string; depth: number; is_agent: boolean; name: string; contracts: number; value_cents: number; since: string | null }[];
  totals: { buyers: number; contracts: number; value_cents: number; in_progress: number; network_people_in_reach: number };
  earned_cents: number;
};

function euro(cents: number): string {
  return (cents / 100).toLocaleString("it-IT", { style: "currency", currency: "EUR" });
}

function day(value: string | null): string {
  return value ? new Date(value).toLocaleDateString("it-IT", { day: "2-digit", month: "short", year: "numeric" }) : "—";
}

export function ProductNetworkView({
  agentId,
  productId,
  onBack,
  onOpenAgent,
  backLabel = "Torna ai piani",
  ownerName,
}: {
  /** Set when looking at someone else's network (admin, upline): wording in third person. */
  ownerName?: string;
  agentId: string;
  productId: string;
  onBack: () => void;
  backLabel?: string;
  /** Opens a collaborator's card from the tree (customers are not openable). */
  onOpenAgent?: (agentId: string) => void;
}) {
  const topRef = useRef<HTMLButtonElement>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const { data, error, isLoading } = useQuery({
    queryKey: ["network", "product-network", agentId, productId],
    queryFn: async (): Promise<ProductNetworkRead> => {
      const res = await fetch(`/api/proxy/network/agents/${agentId}/product-network/${productId}`);
      if (!res.ok) throw new Error("Impossibile caricare la rete di questo prodotto.");
      return res.json();
    },
  });

  useEffect(() => {
    topRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [productId]);

  const back = (
    <button ref={topRef} onClick={onBack} className="act mb-5 scroll-mt-28">
      ← {backLabel}
    </button>
  );

  if (isLoading) {
    return (
      <div>
        {back}
        <div className="panel h-64 animate-pulse rounded-3xl" />
      </div>
    );
  }
  if (error || !data) {
    return (
      <div>
        {back}
        <div className="panel rounded-3xl p-6 text-sm text-danger-300">{(error as Error | null)?.message ?? "Nessun dato."}</div>
      </div>
    );
  }

  const maxLevel = Math.max(1, ...data.levels.map((l) => l.buyers));
  const reach = data.company?.max_network_depth
    ? `${data.company.name} arriva fino a ${data.company.max_network_depth} ${data.company.max_network_depth === 1 ? "livello" : "livelli"} ${ownerName ? "della sua rete" : "della tua rete"}`
    : "Nessun limite di profondità per questo prodotto";

  return (
    <div className="rise space-y-6">
      {back}

      <section className="panel relative overflow-hidden rounded-3xl p-6 sm:p-8">
        <div className="flex flex-col gap-6 md:flex-row md:items-center">
          {data.product.image_url && (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={data.product.image_url} alt="" className="h-28 w-full rounded-3xl object-cover md:h-32 md:w-48" />
          )}
          <div>
            <p className="kpi-label">Rete per questo prodotto</p>
            <h2 className="mt-1 text-3xl font-black tracking-tight text-white">{data.product.name}</h2>
            <div className="mt-3 flex flex-wrap gap-2">
              {data.company && <Chip tone="accent">{data.company.name}</Chip>}
              <Chip tone="info">{reach}</Chip>
            </div>
            <p className="mt-3 max-w-2xl text-sm text-surface-300">
              {ownerName
                ? `La rete di ${ownerName} ridotta a chi ha davvero acquistato questo prodotto, livello per livello. La rete completa resta nell'albero.`
                : "Qui vedi solo chi ha davvero acquistato questo prodotto, livello per livello. La tua rete completa resta com'è nella sezione «La mia rete»."}
            </p>
          </div>
        </div>
      </section>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <KpiTile label="Hanno acquistato" value={data.totals.buyers} hint={`${data.totals.network_people_in_reach} collaboratori raggiungibili`} />
        <KpiTile label="Contratti attivi" value={data.totals.contracts} hint={data.totals.in_progress ? `${data.totals.in_progress} in corso` : "nessuno in corso"} />
        <KpiTile label="Valore venduto" value={euro(data.totals.value_cents)} />
        <KpiTile label={ownerName ? "Ha guadagnato" : "Hai guadagnato"} value={euro(data.earned_cents)} hint="da questo prodotto" />
      </div>

      <div className="grid gap-6 xl:grid-cols-3">
        <section className="panel rounded-3xl p-6 xl:col-span-2">
          <p className="kpi-label">Albero degli acquisti</p>
          <h3 className="mt-1 mb-4 text-xl font-black tracking-tight text-white">Chi ha comprato, e da che ramo</h3>
          {data.totals.buyers === 0 || !data.tree ? (
            <p className="rounded-2xl bg-white/5 px-4 py-8 text-center text-sm text-surface-300">
              {ownerName ? "Ancora nessun acquisto di questo prodotto nella sua rete." : "Ancora nessun acquisto di questo prodotto nella tua rete."}
            </p>
          ) : (
            <NetworkChart
              roots={[data.tree]}
              expandAll
              onCopy={(id) => {
                navigator.clipboard?.writeText(id);
                setCopiedId(id);
                setTimeout(() => setCopiedId(null), 1500);
              }}
              copiedId={copiedId}
              onNodeSelect={(id) => {
                if (!id.startsWith("c:") && onOpenAgent) onOpenAgent(id);
              }}
            />
          )}
        </section>
        <section className="panel rounded-3xl p-6">
          <p className="kpi-label">Per livello</p>
          <h3 className="mt-1 mb-4 text-xl font-black tracking-tight text-white">Acquirenti</h3>
          {data.levels.length === 0 ? (
            <p className="text-sm text-surface-300">Nessuno, per ora.</p>
          ) : (
            <div className="space-y-4">
              {data.levels.map((l) => (
                <div key={l.depth} className="flex items-center gap-4">
                  <span className="orb !h-9 !w-9 !text-xs">{l.depth}</span>
                  <div className="flex-1">
                    <div className="flex justify-between text-xs text-surface-300">
                      <span>{l.depth === 0 ? (ownerName ?? "Tu") : l.depth === 1 ? "Diretti" : `Livello ${l.depth}`}</span>
                      <span className="font-bold text-white">
                        {l.buyers} · {euro(l.value_cents)}
                      </span>
                    </div>
                    <div className="meter mt-1.5 !h-2">
                      <i style={{ width: `${Math.max(4, (l.buyers / maxLevel) * 100)}%` }} />
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>
      </div>

      {data.buyers.length > 0 && (
        <section className="panel rounded-3xl p-6">
          <p className="kpi-label">Elenco</p>
          <h3 className="mt-1 mb-4 text-xl font-black tracking-tight text-white">Tutti gli acquirenti</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr>
                  <th className="px-4">Chi</th>
                  <th className="px-4">Livello</th>
                  <th className="px-4">Dal</th>
                  <th className="px-4 text-right">Valore</th>
                </tr>
              </thead>
              <tbody>
                {data.buyers.map((b) => (
                  <tr
                    key={b.key}
                    onClick={b.is_agent && onOpenAgent ? () => onOpenAgent(b.key) : undefined}
                    className={b.is_agent && onOpenAgent ? "cursor-pointer" : undefined}
                  >
                    <td className="px-4 py-3">
                      <Identity
                        name={b.name}
                        detail={b.is_agent ? (onOpenAgent ? "collaboratore, per sé · apri la scheda" : "collaboratore, per sé") : "cliente"}
                      />
                    </td>
                    <td className="px-4 py-3">
                      <Chip tone={b.depth <= 1 ? "accent" : "info"}>{b.depth === 0 ? (ownerName ? "per sé" : "tu") : b.depth === 1 ? "diretto" : `livello ${b.depth}`}</Chip>
                    </td>
                    <td className="px-4 py-3 text-surface-200">{day(b.since)}</td>
                    <td className="px-4 py-3">
                      <Figure value={euro(b.value_cents)} detail={`${b.contracts} ${b.contracts === 1 ? "contratto" : "contratti"}`} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}
