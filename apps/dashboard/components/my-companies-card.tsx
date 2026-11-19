"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { friendlyApiError } from "@/lib/api-error";
import { AgentCardModal } from "@/components/agent-card-page";
import { ProductNetworkView } from "@/components/product-network-view";
import { Chip, Orb } from "@/components/ui/data-cells";

/*
 * Promoter home: the companies whose products they can sell, whether they
 * take part in each one's plans, their results with it, and a shortcut to
 * the network of every product. Joining tells the company (and staff) that
 * this promoter works with it; commissions follow the plans either way.
 */

export type MyCompanyRead = {
  id: string;
  name: string;
  description: string;
  logo_url: string | null;
  max_network_depth: number | null;
  joined_at: string | null;
  products: { id: string; name: string; image_url: string | null }[];
  earned_cents: number;
  own_sales: number;
  network_buyers: number;
};

function euro(cents: number): string {
  return (cents / 100).toLocaleString("it-IT", { style: "currency", currency: "EUR" });
}

function day(value: string): string {
  return new Date(value).toLocaleDateString("it-IT", { day: "2-digit", month: "short", year: "numeric" });
}

export async function changeMembership(companyId: string, join: boolean): Promise<void> {
  const res = await fetch(`/api/proxy/network/agents/me/companies/${companyId}/${join ? "join" : "leave"}`, { method: "POST" });
  if (!res.ok) throw new Error(await friendlyApiError(res));
}

export function MyCompaniesCard({ agentId, onOpenPlans }: { agentId: string; onOpenPlans?: () => void }) {
  const queryClient = useQueryClient();
  const { data: companies, isLoading } = useQuery({
    queryKey: ["network", "my-companies"],
    queryFn: async (): Promise<MyCompanyRead[]> => {
      const res = await fetch("/api/proxy/network/agents/me/companies");
      if (!res.ok) throw new Error(await friendlyApiError(res));
      return res.json();
    },
  });
  const [networkProduct, setNetworkProduct] = useState<string | null>(null);
  const [openAgentId, setOpenAgentId] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [howOpen, setHowOpen] = useState(false);

  async function toggle(company: MyCompanyRead) {
    setBusy(company.id);
    setError(null);
    try {
      await changeMembership(company.id, !company.joined_at);
      await queryClient.invalidateQueries({ queryKey: ["network", "my-companies"] });
      await queryClient.invalidateQueries({ queryKey: ["network", "my-plans"] });
    } catch (err: any) {
      setError(err.message || "Operazione non riuscita.");
    } finally {
      setBusy(null);
    }
  }

  if (networkProduct) {
    return (
      <>
        <ProductNetworkView
          agentId={agentId}
          productId={networkProduct}
          onBack={() => setNetworkProduct(null)}
          onOpenAgent={setOpenAgentId}
          backLabel="Torna alla home"
        />
        {openAgentId && <AgentCardModal agentId={openAgentId} onClose={() => setOpenAgentId(null)} onOpenAgent={setOpenAgentId} />}
      </>
    );
  }

  const joined = (companies ?? []).filter((c) => c.joined_at).length;

  return (
    <section className="panel rounded-3xl p-6 sm:p-7">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="kpi-label">I tuoi piani</p>
          <h3 className="mt-1 text-2xl font-black tracking-tight text-white">Le aziende con cui lavori</h3>
          <p className="mt-1 text-sm text-surface-300">
            {companies ? `Partecipi a ${joined} ${joined === 1 ? "azienda" : "aziende"} su ${companies.length}.` : "Caricamento…"}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button className="act" onClick={() => setHowOpen((v) => !v)}>
            {howOpen ? "Chiudi" : "Come si partecipa"}
          </button>
          {onOpenPlans && (
            <button className="act act-primary" onClick={onOpenPlans}>
              Tutti i miei piani →
            </button>
          )}
        </div>
      </div>

      {howOpen && (
        <ol className="mt-5 grid gap-3 rounded-3xl bg-white/5 p-5 text-sm text-surface-200 md:grid-cols-3">
          <li>
            <span className="kpi-label">1 · Scegli l&apos;azienda</span>
            <p className="mt-1">Ogni prodotto appartiene a un&apos;azienda, con il suo piano provvigionale e i livelli di rete che paga.</p>
          </li>
          <li>
            <span className="kpi-label">2 · Premi &ldquo;Partecipa&rdquo;</span>
            <p className="mt-1">
              L&apos;azienda e l&apos;amministrazione sanno che lavori con loro. Puoi uscire quando vuoi: i compensi già maturati restano tuoi.
            </p>
          </li>
          <li>
            <span className="kpi-label">3 · Vendi e segui la rete</span>
            <p className="mt-1">Apri un prodotto per vedere chi, nella tua rete, lo ha già acquistato, livello per livello.</p>
          </li>
        </ol>
      )}

      {error && <p className="mt-4 text-sm text-danger-300">{error}</p>}

      <div className="mt-5 grid gap-4 lg:grid-cols-2">
        {isLoading && [0, 1].map((i) => <div key={i} className="h-40 animate-pulse rounded-3xl bg-white/5" />)}
        {(companies ?? []).map((company) => (
          <div key={company.id} className="rounded-3xl bg-white/5 p-5 ring-1 ring-white/10">
            <div className="flex items-start gap-4">
              {company.logo_url ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={company.logo_url} alt="" className="h-12 w-12 rounded-2xl bg-white object-contain p-1" />
              ) : (
                <Orb name={company.name} />
              )}
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <h4 className="text-lg font-black tracking-tight text-white">{company.name}</h4>
                  {company.joined_at ? (
                    <Chip tone="ok">Partecipi dal {day(company.joined_at)}</Chip>
                  ) : (
                    <Chip tone="muted">Non partecipi</Chip>
                  )}
                </div>
                <p className="mt-0.5 text-xs text-surface-400">
                  {company.max_network_depth ? `Paga fino a ${company.max_network_depth} livelli di rete` : "Nessun limite di livelli"}
                </p>
              </div>
              <button
                className={company.joined_at ? "act" : "act act-primary"}
                disabled={busy === company.id}
                onClick={() => toggle(company)}
              >
                {busy === company.id ? "…" : company.joined_at ? "Esci" : "Partecipa"}
              </button>
            </div>

            <dl className="mt-4 grid grid-cols-3 gap-2 text-center">
              <div className="rounded-2xl bg-white/5 p-2.5">
                <dt className="kpi-label !text-[9px]">Guadagnato</dt>
                <dd className="mt-1 text-sm font-black text-white">{euro(company.earned_cents)}</dd>
              </div>
              <div className="rounded-2xl bg-white/5 p-2.5">
                <dt className="kpi-label !text-[9px]">Vendite tue</dt>
                <dd className="mt-1 text-sm font-black text-white">{company.own_sales}</dd>
              </div>
              <div className="rounded-2xl bg-white/5 p-2.5">
                <dt className="kpi-label !text-[9px]">Clienti in rete</dt>
                <dd className="mt-1 text-sm font-black text-white">{company.network_buyers}</dd>
              </div>
            </dl>

            <p className="kpi-label mt-4 !text-[9.5px]">La rete di ogni prodotto</p>
            <div className="mt-2 flex flex-wrap gap-2">
              {company.products.map((product) => (
                <button key={product.id} className="subnav-pill" onClick={() => setNetworkProduct(product.id)}>
                  {product.name} →
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
