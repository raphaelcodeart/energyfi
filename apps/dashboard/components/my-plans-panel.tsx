"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Chip, Figure, Identity, KpiTile, Orb } from "@/components/ui/data-cells";
import { ProductNetworkView } from "@/components/product-network-view";
import { AgentCardModal } from "@/components/agent-card-page";
import { changeMembership } from "@/components/my-companies-card";

/*
 * "I miei piani" (promoter area): the Split Plans the collaborator works
 * with. For each plan, what every product would pay them if sold today (the
 * same engine as real sales), who else in the chain is paid and how, and what
 * the plan has already paid them and thanks to whom.
 */

type Company = { id: string; name: string; description: string; logo_url: string | null; max_network_depth: number | null; joined_at: string | null };

type MyPlansRead = {
  agent_id: string;
  companies: Company[];
  role_name: string | null;
  refers_only: boolean;
  agent_name: string | null;
  plans: {
    plan: { id: string; name: string; version: number; status: string; valid_from: string | null };
    products: {
      product_id: string;
      name: string;
      category: string | null;
      company_id: string | null;
      image_url: string | null;
      price_cents: number | null;
      margin_cents: number | null;
      mine_cents: number;
      network_cents: number;
      company_cents: number;
    }[];
    distribution: { who: string; name: string; is_me: boolean; cents: number; calculation: string; value: string | null }[];
    earned_cents: number;
    contracts: number;
    people: { agent_id: string | null; name: string; level: number | null; earned_cents: number; contracts: number }[];
  }[];
  past_plans: { plan_id: string | null; name: string; version: number | null; earned_cents: number; contracts: number }[];
  unavailable: { product: string; reason: string }[];
  earnings: { total_cents: number; paid_cents: number; last_30_days_cents: number } | null;
};

async function fetchMyPlans(): Promise<MyPlansRead> {
  const res = await fetch("/api/proxy/network/agents/me/plans");
  if (!res.ok) throw new Error("Impossibile caricare i tuoi piani.");
  return res.json();
}

function euro(cents: number | null | undefined): string {
  return ((cents ?? 0) / 100).toLocaleString("it-IT", { style: "currency", currency: "EUR" });
}

function share(item: { calculation: string; value: string | null; cents: number }): string {
  if (item.calculation === "PERCENTAGE" && item.value) return `${Number(item.value).toLocaleString("it-IT")}% del margine`;
  if (item.calculation === "FIXED_AMOUNT") return "importo fisso";
  if (item.calculation === "REMAINDER") return "quello che resta";
  if (item.calculation === "MINIMUM_GUARANTEE") return "minimo garantito";
  return "";
}

export function MyPlansPanel() {
  const { data, error, isLoading } = useQuery({ queryKey: ["network", "my-plans"], queryFn: fetchMyPlans });
  const [open, setOpen] = useState<string | null>(null);
  const [companyFilter, setCompanyFilter] = useState<string>("ALL");
  const [networkProduct, setNetworkProduct] = useState<string | null>(null);
  // Collaborator card opened from the product tree, as a popup over it.
  const [openAgentId, setOpenAgentId] = useState<string | null>(null);
  const queryClient = useQueryClient();
  const [busyCompany, setBusyCompany] = useState<string | null>(null);

  async function toggleMembership(company: Company) {
    setBusyCompany(company.id);
    try {
      await changeMembership(company.id, !company.joined_at);
      await queryClient.invalidateQueries({ queryKey: ["network", "my-plans"] });
      await queryClient.invalidateQueries({ queryKey: ["network", "my-companies"] });
    } finally {
      setBusyCompany(null);
    }
  }

  if (isLoading) {
    return (
      <div className="grid gap-4 lg:grid-cols-3">
        {[0, 1, 2].map((i) => <div key={i} className="panel h-40 animate-pulse rounded-3xl" />)}
      </div>
    );
  }
  if (error || !data) {
    return <div className="panel rounded-3xl p-6 text-sm text-danger-300">{(error as Error | null)?.message ?? "Nessun dato."}</div>;
  }

  if (networkProduct) {
    return (
      <>
        <ProductNetworkView
          agentId={data.agent_id}
          productId={networkProduct}
          onBack={() => setNetworkProduct(null)}
          onOpenAgent={setOpenAgentId}
        />
        {openAgentId && (
          <AgentCardModal agentId={openAgentId} onClose={() => setOpenAgentId(null)} onOpenAgent={setOpenAgentId} />
        )}
      </>
    );
  }

  const products = data.plans.flatMap((p) => p.products);
  // Companies that have at least one product this collaborator can sell, plus
  // a bucket for products not yet assigned to a company.
  const groups: { company: Company | null; key: string }[] = [
    ...data.companies.filter((c) => products.some((p) => p.company_id === c.id)).map((c) => ({ company: c, key: c.id })),
    ...(products.some((p) => !p.company_id) ? [{ company: null, key: "NONE" }] : []),
  ];
  const shownGroups = groups.filter((g) => companyFilter === "ALL" || g.key === companyFilter);
  const best = products.reduce<(typeof products)[number] | null>((top, p) => (!top || p.mine_cents > top.mine_cents ? p : top), null);

  return (
    <div className="space-y-6">
      <section className="panel rounded-3xl p-6 sm:p-8">
        <p className="kpi-label">Il tuo ruolo · {data.role_name ?? "—"}</p>
        <h2 className="mt-2 text-2xl font-black tracking-tight text-white sm:text-3xl">
          I piani con cui <span className="text-gradient">lavori</span>
        </h2>
        <p className="mt-2 max-w-3xl text-sm text-surface-200">
          {data.refers_only
            ? "Il tuo ruolo segnala i clienti: la vendita la chiude chi sta sopra di te e tu ricevi la tua quota. Qui vedi quanto ti rende ogni prodotto."
            : "Per ogni prodotto vedi quanto guadagni se lo vendi oggi, quanto va alla tua rete e quanto all'azienda. Sotto, cosa ti ha già fruttato ogni piano."}
        </p>
      </section>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <KpiTile label="Piani attivi per te" value={data.plans.length} hint={`${products.length} prodotti vendibili`} />
        <KpiTile label="Il più redditizio" value={best ? euro(best.mine_cents) : "—"} hint={best ? best.name : "nessun prodotto"} />
        <KpiTile label="Guadagnato in tutto" value={euro(data.earnings?.total_cents)} hint={`pagato ${euro(data.earnings?.paid_cents)}`} />
        <KpiTile label="Ultimi 30 giorni" value={euro(data.earnings?.last_30_days_cents)} hint="maturato di recente" />
      </div>

      {groups.length > 1 && (
        <div className="subnav">
          <button className="subnav-pill" data-active={companyFilter === "ALL"} onClick={() => setCompanyFilter("ALL")}>
            Tutte le aziende
          </button>
          {groups.map((g) => (
            <button key={g.key} className="subnav-pill" data-active={companyFilter === g.key} onClick={() => setCompanyFilter(g.key)}>
              {g.company?.name ?? "Senza azienda"}
            </button>
          ))}
        </div>
      )}

      {shownGroups.map((group) => (
        <div key={group.key} className="space-y-5">
          <section className="panel relative overflow-hidden rounded-3xl p-6">
            <span className="pointer-events-none absolute -right-20 -top-20 h-60 w-60 rounded-full bg-gradient-to-br from-brand-400/30 to-accent-400/10 blur-3xl" />
            <div className="relative flex flex-wrap items-center gap-4">
              {group.company?.logo_url ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={group.company.logo_url} alt="" className="h-14 w-14 rounded-2xl bg-white object-contain p-1" />
              ) : (
                <div className="origin-left scale-125">
                  <Orb name={group.company?.name ?? "Altro"} />
                </div>
              )}
              <div className="min-w-0 flex-1 pl-2">
                <p className="kpi-label">Azienda</p>
                <h3 className="text-2xl font-black tracking-tight text-white">{group.company?.name ?? "Prodotti senza azienda"}</h3>
                {group.company?.description && <p className="mt-1 text-sm text-surface-300">{group.company.description}</p>}
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Chip tone="info">
                  {group.company?.max_network_depth
                    ? `Paga fino a ${group.company.max_network_depth} livelli`
                    : "Nessun limite di livelli"}
                </Chip>
                {group.company && (
                  <>
                    {group.company.joined_at ? (
                      <Chip tone="ok">Partecipi dal {new Date(group.company.joined_at).toLocaleDateString("it-IT")}</Chip>
                    ) : (
                      <Chip tone="muted">Non partecipi</Chip>
                    )}
                    <button
                      className={group.company.joined_at ? "act" : "act act-primary"}
                      disabled={busyCompany === group.company.id}
                      onClick={() => group.company && toggleMembership(group.company)}
                    >
                      {group.company.joined_at ? "Esci" : "Partecipa"}
                    </button>
                  </>
                )}
              </div>
            </div>
          </section>

          {data.plans
            .map((plan) => ({ ...plan, products: plan.products.filter((p) => (p.company_id ?? "NONE") === group.key) }))
            .filter((plan) => plan.products.length > 0)
            .map((plan) => {
        const expanded = open === plan.plan.id;
        const maxMine = Math.max(1, ...plan.products.map((p) => p.mine_cents));
        return (
          <section key={plan.plan.id} className="panel rounded-3xl p-6">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <p className="kpi-label">{[...new Set(plan.products.map((p) => p.category).filter(Boolean))].join(" · ") || "Piano"}</p>
                <h3 className="mt-1 text-xl font-black tracking-tight text-white">
                  {plan.plan.name} <span className="text-surface-400">· v{plan.plan.version}</span>
                </h3>
                <div className="mt-2 flex flex-wrap gap-2">
                  <Chip tone="ok">In vigore</Chip>
                  <Chip tone="info">{plan.products.length} prodotti</Chip>
                  {plan.contracts > 0 && <Chip tone="accent">{plan.contracts} contratti con questo piano</Chip>}
                </div>
              </div>
              <Figure value={euro(plan.earned_cents)} detail="già maturato con questo piano" />
            </div>

            <div className="mt-5 overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr>
                    <th className="px-4">Prodotto</th>
                    <th className="px-4 text-right">Prezzo</th>
                    <th className="px-4 text-right">Margine</th>
                    <th className="px-4 text-right">Alla tua rete</th>
                    <th className="px-4 text-right">A te, per vendita</th>
                    <th className="px-4" />
                  </tr>
                </thead>
                <tbody>
                  {plan.products.map((p) => (
                    <tr key={p.product_id}>
                      <td className="px-4 py-3">
                        <div className="font-bold text-white">{p.name}</div>
                        {p.category && <div className="text-[11px] text-surface-400">{p.category}</div>}
                      </td>
                      <td className="px-4 py-3 text-right tabular-nums text-surface-200">{euro(p.price_cents)}</td>
                      <td className="px-4 py-3 text-right tabular-nums text-surface-200">{euro(p.margin_cents)}</td>
                      <td className="px-4 py-3 text-right tabular-nums text-surface-200">{euro(p.network_cents)}</td>
                      <td className="px-4 py-3">
                        <Figure value={euro(p.mine_cents)} ratio={p.mine_cents / maxMine} />
                      </td>
                      <td className="px-4 py-3 text-right">
                        <button className="act act-primary whitespace-nowrap" onClick={() => setNetworkProduct(p.product_id)}>
                          La mia rete
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <button className="act mt-4" onClick={() => setOpen(expanded ? null : plan.plan.id)}>
              {expanded ? "Nascondi i dettagli" : "Come si divide e chi ti ha fatto guadagnare"}
            </button>

            {expanded && (
              <div className="mt-5 grid gap-6 lg:grid-cols-2">
                <div className="rounded-3xl bg-white/5 p-5">
                  <p className="kpi-label">Come si divide · {plan.products[0]?.name}</p>
                  <ul className="mt-3 space-y-3">
                    {plan.distribution.map((d, i) => (
                      <li key={i} className="flex items-center justify-between gap-3">
                        <div>
                          <div className={`text-sm font-bold ${d.is_me ? "text-white" : "text-surface-200"}`}>
                            {d.who} {d.is_me && <Chip tone="accent">tu</Chip>}
                          </div>
                          <div className="text-[11px] text-surface-400">
                            {d.name} · {share(d)}
                          </div>
                        </div>
                        <span className="font-black tabular-nums text-white">{euro(d.cents)}</span>
                      </li>
                    ))}
                  </ul>
                </div>
                <div className="rounded-3xl bg-white/5 p-5">
                  <p className="kpi-label">Chi ti ha fatto guadagnare</p>
                  {plan.people.length === 0 ? (
                    <p className="mt-3 text-sm text-surface-300">Ancora nessun guadagno con questo piano.</p>
                  ) : (
                    <ul className="mt-3 space-y-3">
                      {plan.people.map((p) => (
                        <li key={p.agent_id ?? p.name} className="flex items-center justify-between gap-3">
                          <Identity
                            name={p.name}
                            detail={`${p.contracts} ${p.contracts === 1 ? "contratto" : "contratti"}${p.level ? ` · ${p.level} livelli sotto` : ""}`}
                          />
                          <span className="font-black tabular-nums text-white">{euro(p.earned_cents)}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </div>
            )}
          </section>
        );
      })}
        </div>
      ))}

      {data.past_plans.length > 0 && (
        <section className="panel rounded-3xl p-6">
          <p className="kpi-label">Storico</p>
          <h3 className="mt-1 text-xl font-black tracking-tight text-white">Piani che ti hanno pagato in passato</h3>
          <ul className="mt-4 grid gap-3 sm:grid-cols-2">
            {data.past_plans.map((p) => (
              <li key={p.plan_id ?? p.name} className="flex items-center justify-between rounded-2xl bg-white/5 p-4">
                <div>
                  <div className="font-bold text-white">{p.name}{p.version ? ` · v${p.version}` : ""}</div>
                  <div className="text-[11px] text-surface-400">{p.contracts} contratti</div>
                </div>
                <span className="font-black tabular-nums text-white">{euro(p.earned_cents)}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {data.unavailable.length > 0 && (
        <section className="panel rounded-3xl p-6">
          <p className="kpi-label">Non disponibili per te oggi</p>
          <ul className="mt-3 space-y-2 text-sm text-surface-300">
            {data.unavailable.map((u) => (
              <li key={u.product}>
                <span className="font-semibold text-white">{u.product}</span> — {u.reason}
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
