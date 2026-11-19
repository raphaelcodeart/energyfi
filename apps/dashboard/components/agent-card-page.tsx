"use client";

import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { useQuery } from "@tanstack/react-query";
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Chip, Figure, Identity, KpiTile, Orb } from "@/components/ui/data-cells";
import { ProductNetworkView } from "@/components/product-network-view";
import type { AgentCardRead, BranchContractRead, CompanyRead, ProductCatalogRead } from "@/lib/types";

/*
 * The collaborator card, opened from the network tree (admin and promoter
 * areas). A page, not a modal: identity and sponsors on top, then tabs for
 * the overview, earnings per Split Plan with the people behind them, the
 * network below, sales and contracts, and roles and delegations.
 */

const STATUS_LABELS: Record<string, string> = {
  DRAFT: "Bozza", SUBMITTED: "Inviata", DOCUMENTS_PENDING: "Documenti mancanti", UNDER_REVIEW: "In revisione",
  APPROVED: "Approvata", PAYMENT_PENDING: "In attesa di pagamento", PAID: "Pagata", ACTIVATION_PENDING: "In attivazione",
  ACTIVE: "Attiva", SUSPENDED: "Sospesa", CANCELLED: "Cessata", EXPIRED: "Scaduta", RENEWED: "Rinnovata",
  REJECTED: "Respinta",
};

const AGENT_STATUS: Record<string, { label: string; tone: "ok" | "warn" | "bad" | "muted" }> = {
  ACTIVE: { label: "Attivo", tone: "ok" },
  PENDING_APPROVAL: { label: "Da approvare", tone: "warn" },
  SUSPENDED: { label: "Sospeso", tone: "warn" },
  TERMINATED: { label: "Cessato", tone: "bad" },
};

const MOVEMENT_TYPES: Record<string, string> = {
  DIRECT: "Vendite proprie",
  INDIRECT: "Dalla rete",
  PROMOTER_FEE: "Fee segnalazioni",
  REVERSAL: "Storni",
  PERSONAL_TOKEN: "Gettoni (storico)",
};

const PLAN_STATUS: Record<string, { label: string; tone: "ok" | "muted" | "info" }> = {
  ACTIVE: { label: "In vigore", tone: "ok" },
  RETIRED: { label: "Ritirato", tone: "info" },
  LEGACY: { label: "Storico", tone: "muted" },
  DRAFT: { label: "Bozza", tone: "muted" },
};

function euro(cents: number): string {
  return (cents / 100).toLocaleString("it-IT", { style: "currency", currency: "EUR" });
}

function day(value: string | null | undefined): string {
  if (!value) return "—";
  return new Date(value).toLocaleDateString("it-IT", { day: "2-digit", month: "short", year: "numeric" });
}

function monthLabel(key: string): string {
  const [y, m] = key.split("-").map(Number);
  return new Date(y ?? 2000, (m ?? 1) - 1, 1).toLocaleDateString("it-IT", { month: "short" });
}

async function getJson<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (res.status === 403) throw new Error("Questa scheda non fa parte della tua rete.");
  if (!res.ok) throw new Error("Impossibile caricare la scheda.");
  return res.json();
}

function Section({ eyebrow, title, children, aside }: { eyebrow: string; title: string; children: ReactNode; aside?: ReactNode }) {
  return (
    <section className="panel rounded-3xl p-6">
      <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="kpi-label">{eyebrow}</p>
          <h3 className="mt-1 text-xl font-black tracking-tight text-white">{title}</h3>
        </div>
        {aside}
      </div>
      {children}
    </section>
  );
}

function Empty({ children }: { children: ReactNode }) {
  return <p className="rounded-2xl bg-white/5 px-4 py-6 text-center text-sm text-surface-300">{children}</p>;
}

type Tab = "overview" | "plans" | "products" | "network" | "sales" | "roles";

const TABS: { key: Tab; label: string }[] = [
  { key: "overview", label: "Panoramica" },
  { key: "plans", label: "Piani e guadagni" },
  { key: "products", label: "Rete per prodotto" },
  { key: "network", label: "La sua rete" },
  { key: "sales", label: "Vendite e contratti" },
  { key: "roles", label: "Ruoli e deleghe" },
];

/** Tabs built on the inherited energy contracts (pratiche luce e gas): kept
 * in the code but not shown. Remove a key to show the tab again. */
const HIDDEN_TABS = new Set<Tab>(["plans", "products", "sales"]);

export function AgentCardPage({
  agentId,
  onBack,
  onOpenAgent,
  canOpen = () => true,
  backLabel = "Torna all'albero",
  hideBack = false,
}: {
  /** In the popup the close button replaces the back button. */
  hideBack?: boolean;
  agentId: string;
  onBack: () => void;
  /** Opens another collaborator's card (a sponsor, someone in a plan). */
  onOpenAgent?: (agentId: string) => void;
  /** Which cards the viewer may open; defaults to all. */
  canOpen?: (agentId: string) => boolean;
  backLabel?: string;
}) {
  const [tab, setTab] = useState<Tab>("overview");
  const { data: card, error, isLoading } = useQuery({
    queryKey: ["network", "agent-card", agentId],
    queryFn: () => getJson<AgentCardRead>(`/api/proxy/network/agents/${agentId}/card`),
  });
  const { data: contracts } = useQuery({
    queryKey: ["network", "node-detail", "contracts", agentId],
    queryFn: () => getJson<BranchContractRead[]>(`/api/proxy/network/agents/${agentId}/branch-contracts`),
    enabled: tab === "sales",
  });
  const [onlyProblems, setOnlyProblems] = useState(false);
  const [networkProduct, setNetworkProduct] = useState<string | null>(null);
  const { data: catalog } = useQuery({
    queryKey: ["network", "agent-card", "catalog"],
    queryFn: () => getJson<ProductCatalogRead[]>("/api/proxy/products"),
    enabled: tab === "products",
  });
  const { data: companies } = useQuery({
    queryKey: ["network", "agent-card", "companies"],
    queryFn: () => getJson<CompanyRead[]>("/api/proxy/products/companies"),
    enabled: tab === "products",
  });
  const topRef = useRef<HTMLElement>(null);

  // Opening a card (or another card from this one) starts at its top.
  useEffect(() => {
    topRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [agentId]);

  const back = hideBack ? (
    <span ref={topRef} className="block scroll-mt-28" />
  ) : (
    <button ref={topRef as React.RefObject<HTMLButtonElement | null>} onClick={onBack} className="act mb-5 scroll-mt-28">
      ← {backLabel}
    </button>
  );

  if (isLoading) {
    return (
      <div className="space-y-4">
        {back}
        <div className="panel h-48 animate-pulse rounded-3xl" />
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          {[0, 1, 2, 3].map((i) => <div key={i} className="panel h-32 animate-pulse rounded-3xl" />)}
        </div>
      </div>
    );
  }
  if (error || !card) {
    return (
      <div>
        {back}
        <Empty>{(error as Error | null)?.message ?? "Scheda non disponibile."}</Empty>
      </div>
    );
  }

  const { agent, earnings, network, sales } = card;
  const status = AGENT_STATUS[agent.status] ?? { label: agent.status, tone: "muted" as const };
  const toCollect = earnings.pending_cents + earnings.approved_cents + earnings.payable_cents;
  const maxMonth = Math.max(1, ...earnings.by_month.map((m) => m.cents));
  const maxLevel = Math.max(1, ...network.levels.map((l) => l.people));
  const open = (id: string | null) =>
    id && id !== agent.id && onOpenAgent && canOpen(id) ? () => onOpenAgent(id) : undefined;

  const chartData = earnings.by_month.map((m) => ({ ...m, label: monthLabel(m.month), euro: m.cents / 100 }));
  const filteredContracts = (contracts ?? []).filter((c) => !onlyProblems || c.is_problem);

  return (
    <div className="rise space-y-6">
      {back}

      {/* ---- Identity ---- */}
      <section className="panel relative overflow-hidden rounded-3xl p-6 sm:p-8">
        <span className="pointer-events-none absolute -right-24 -top-24 h-72 w-72 rounded-full bg-gradient-to-br from-brand-400/40 to-accent-400/10 blur-3xl" />
        <div className="relative flex flex-col gap-6 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex items-center gap-5">
            {agent.photo_url ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={agent.photo_url} alt="" className="h-20 w-20 rounded-3xl object-cover shadow-2xl" />
            ) : (
              <div className="origin-left scale-[1.9]">
                <Orb name={agent.display_name} />
              </div>
            )}
            <div className={agent.photo_url ? "" : "pl-8"}>
              <p className="kpi-label">Scheda collaboratore</p>
              <h2 className="mt-1 text-3xl font-black tracking-tight text-white sm:text-4xl">{agent.display_name}</h2>
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <span className="tag-id">{agent.promoter_code}</span>
                {agent.role_name && <Chip tone="accent">{agent.role_name}</Chip>}
                {agent.rank_name && <Chip tone="info">{agent.rank_name}</Chip>}
                <Chip tone={status.tone} live={status.tone === "warn"}>{status.label}</Chip>
                <span className="text-xs text-surface-300">in rete dal {day(agent.joined_at)}</span>
                {agent.email && <span className="text-xs text-surface-300">· {agent.email}</span>}
              </div>
            </div>
          </div>
          <div className="min-w-[220px]">
            <p className="kpi-label">Sponsor</p>
            {card.upline.length === 0 ? (
              <p className="mt-2 text-sm font-semibold text-white">Radice della rete</p>
            ) : (
              <ol className="mt-2 space-y-1.5">
                {card.upline.map((u) => (
                  <li key={u.agent_id} className="flex items-center gap-2 text-sm">
                    <span className="grid h-6 w-6 place-items-center rounded-lg bg-white/10 text-[10px] font-black text-white">
                      {u.depth}
                    </span>
                    {open(u.agent_id) ? (
                      <button onClick={open(u.agent_id)} className="cursor-pointer font-semibold text-white hover:text-brand-200">
                        {u.name}
                      </button>
                    ) : (
                      <span className="font-semibold text-white">{u.name}</span>
                    )}
                    {u.role_name && <span className="text-[11px] text-surface-400">{u.role_name}</span>}
                  </li>
                ))}
              </ol>
            )}
          </div>
        </div>
      </section>

      {/* ---- Headline numbers ---- */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <KpiTile label="Guadagnato" value={euro(earnings.total_cents)} hint={`${earnings.movements} movimenti in tutto`} />
        <KpiTile label="Ultimi 30 giorni" value={euro(earnings.last_30_days_cents)} hint="maturato di recente" />
        <KpiTile label="Già pagato" value={euro(earnings.paid_cents)} hint={`da incassare ${euro(toCollect)}`} />
        <KpiTile
          label="Persone in rete"
          value={network.total}
          hint={`${network.direct} dirette · ${network.levels.length} livelli`}
        />
      </div>

      <div className="subnav">
        {TABS.filter((t) => !HIDDEN_TABS.has(t.key)).map((t) => (
          <button key={t.key} className="subnav-pill" data-active={tab === t.key} onClick={() => setTab(t.key)}>
            {t.label}
          </button>
        ))}
      </div>

      {tab === "overview" && (
        <div className="grid gap-6 xl:grid-cols-3">
          <div className="xl:col-span-2">
            <Section eyebrow="Andamento" title="Guadagni degli ultimi 12 mesi">
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={chartData} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
                    <defs>
                      <linearGradient id="agentCardBar" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#ffffff" />
                        <stop offset="45%" stopColor="#47e2ff" />
                        <stop offset="100%" stopColor="#216eff" />
                      </linearGradient>
                    </defs>
                    <CartesianGrid vertical={false} stroke="rgba(200, 222, 255,0.08)" />
                    <XAxis dataKey="label" tick={{ fill: "#aec6e8", fontSize: 11 }} axisLine={false} tickLine={false} />
                    <YAxis tick={{ fill: "#aec6e8", fontSize: 11 }} axisLine={false} tickLine={false} width={56} />
                    <Tooltip
                      cursor={{ fill: "rgba(255,255,255,0.06)" }}
                      contentStyle={{ background: "#081a2b", border: "1px solid rgba(200, 222, 255,0.25)", borderRadius: 14, color: "#fff" }}
                      formatter={(value) => [euro(Number(value) * 100), "Guadagnato"]}
                    />
                    <Bar dataKey="euro" radius={[8, 8, 2, 2]}>
                      {chartData.map((m) => (
                        <Cell key={m.month} fill="url(#agentCardBar)" fillOpacity={0.35 + 0.65 * (m.cents / maxMonth)} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </Section>
          </div>
          <Section eyebrow="Stato dei compensi" title="Dove sono i soldi">
            <div className="space-y-4">
              {[
                ["Pagati", earnings.paid_cents, "chip-ok"],
                ["Pagabili", earnings.payable_cents, "chip-accent"],
                ["Approvati", earnings.approved_cents, "chip-info"],
                ["Da approvare", earnings.pending_cents, "chip-warn"],
                ["Annullati", earnings.cancelled_cents, "chip-bad"],
              ].map(([label, cents, tone]) => (
                <div key={label as string}>
                  <div className="flex items-baseline justify-between text-sm">
                    <span className={`chip ${tone}`}>{label}</span>
                    <span className="font-black tabular-nums text-white">{euro(cents as number)}</span>
                  </div>
                  <div className="meter mt-2">
                    <i style={{ width: `${Math.max(2, Math.min(100, (Math.abs(cents as number) / Math.max(1, earnings.total_cents)) * 100))}%` }} />
                  </div>
                </div>
              ))}
            </div>
          </Section>
          <Section eyebrow="Composizione" title="Da dove arrivano">
            {earnings.by_type.length === 0 ? (
              <Empty>Nessun compenso ancora.</Empty>
            ) : (
              <div className="space-y-3">
                {earnings.by_type.map((t) => (
                  <Figure
                    key={t.type}
                    value={<span className="flex justify-between gap-3"><span className="text-sm font-semibold text-surface-200">{MOVEMENT_TYPES[t.type] ?? t.type}</span>{euro(t.cents)}</span>}
                    ratio={t.cents / Math.max(1, earnings.total_cents)}
                  />
                ))}
              </div>
            )}
          </Section>
          <Section eyebrow="Attività" title="In sintesi">
            <dl className="grid grid-cols-2 gap-4 text-sm">
              {[
                ["Vendite proprie", sales.own_sold],
                ["In lavorazione", sales.own_open],
                ["Valore venduto", euro(sales.own_value_cents)],
                ["Generato dalla rete", euro(sales.network_value_cents)],
                ["Segnalazioni", `${card.leads.total} (${card.leads.open} aperte)`],
                ["Portafoglio", card.wallet_cents == null ? "senza accesso" : euro(card.wallet_cents)],
              ].map(([label, value]) => (
                <div key={label as string} className="rounded-2xl bg-white/5 p-3">
                  <dt className="kpi-label !text-[9.5px]">{label}</dt>
                  <dd className="mt-1 font-black text-white">{value}</dd>
                </div>
              ))}
            </dl>
          </Section>
          <Section eyebrow="Rete" title="Livelli sotto di lui">
            <LevelBars levels={network.levels} max={maxLevel} />
          </Section>
        </div>
      )}

      {tab === "plans" && (
        <div className="space-y-6">
          {card.plans.length === 0 && <Empty>Nessun compenso maturato con un piano provvigionale.</Empty>}
          {card.plans.map((plan) => {
            const planStatus = PLAN_STATUS[plan.status] ?? { label: plan.status, tone: "muted" as const };
            return (
              <Section
                key={plan.plan_id ?? "legacy"}
                eyebrow={[plan.scope, plan.seller_role_name ? `chi vende: ${plan.seller_role_name}` : null].filter(Boolean).join(" · ") || "Piano"}
                title={`${plan.name}${plan.version ? ` · v${plan.version}` : ""}`}
                aside={
                  <div className="flex items-center gap-4">
                    <Chip tone={planStatus.tone}>{planStatus.label}</Chip>
                    <Figure
                      value={euro(plan.earned_cents)}
                      detail={`${plan.contracts} contratti · ${Math.round((plan.earned_cents / Math.max(1, earnings.total_cents)) * 100)}% del totale`}
                    />
                  </div>
                }
              >
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-sm">
                    <thead>
                      <tr>
                        <th className="px-4">Chi ha venduto</th>
                        <th className="px-4">Distanza</th>
                        <th className="px-4">Contratti</th>
                        <th className="px-4 text-right">Gli ha fruttato</th>
                      </tr>
                    </thead>
                    <tbody>
                      {plan.people.map((p) => (
                        <tr
                          key={p.agent_id ?? p.name}
                          onClick={open(p.agent_id)}
                          className={open(p.agent_id) ? "cursor-pointer" : ""}
                        >
                          <td className="px-4 py-3">
                            <Identity name={p.name} detail={open(p.agent_id) ? "apri la scheda" : undefined} />
                          </td>
                          <td className="px-4 py-3">
                            <Chip tone={p.level ? "info" : "accent"}>{distanceLabel(p, agent.id)}</Chip>
                          </td>
                          <td className="px-4 py-3 font-bold tabular-nums text-white">{p.contracts}</td>
                          <td className="px-4 py-3">
                            <Figure value={euro(p.earned_cents)} ratio={p.earned_cents / Math.max(1, plan.earned_cents)} />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Section>
            );
          })}
        </div>
      )}

      {tab === "products" &&
        (networkProduct ? (
          <ProductNetworkView
            key={networkProduct}
            agentId={agent.id}
            productId={networkProduct}
            onBack={() => setNetworkProduct(null)}
            onOpenAgent={onOpenAgent ? (id) => canOpen(id) && onOpenAgent(id) : undefined}
            backLabel="Torna ai prodotti"
            ownerName={agent.display_name}
          />
        ) : (
          <ProductPicker catalog={catalog} companies={companies} onPick={setNetworkProduct} name={agent.display_name} />
        ))}

      {tab === "network" && (
        <div className="grid gap-6 lg:grid-cols-2">
          <Section eyebrow="Struttura" title="Persone per livello">
            <LevelBars levels={network.levels} max={maxLevel} />
          </Section>
          <Section eyebrow="Crescita" title="Come si muove">
            <div className="grid grid-cols-2 gap-4">
              <KpiTile label="Dirette" value={network.direct} />
              <KpiTile label="Attive" value={`${network.active}/${network.total}`} />
              <KpiTile label="Nuove in 30 giorni" value={network.joined_last_30_days} />
              <KpiTile label="Nuove in 90 giorni" value={network.joined_last_90_days} />
            </div>
          </Section>
        </div>
      )}

      {tab === "sales" && (
        <div className="space-y-6">
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <KpiTile label="Vendite chiuse" value={sales.own_sold} hint={`su ${sales.own_total} aperte in tutto`} />
            <KpiTile label="In lavorazione" value={sales.own_open} />
            <KpiTile label="Perse" value={sales.own_lost} hint="respinte o cessate" />
            <KpiTile label="Dalla sua rete" value={sales.network_sold} hint={euro(sales.network_value_cents)} />
          </div>
          <Section eyebrow="Vendite proprie" title="Per prodotto">
            {sales.by_product.length === 0 ? (
              <Empty>Nessuna vendita propria chiusa.</Empty>
            ) : (
              <div className="grid gap-3 sm:grid-cols-2">
                {sales.by_product.map((p) => (
                  <div key={p.product} className="rounded-2xl bg-white/5 p-4">
                    <Figure
                      value={<span className="flex justify-between gap-3"><span className="text-sm font-semibold text-surface-200">{p.product}</span>{euro(p.value_cents)}</span>}
                      detail={`${p.contracts} contratti`}
                      ratio={p.value_cents / Math.max(1, sales.own_value_cents)}
                    />
                  </div>
                ))}
              </div>
            )}
          </Section>
          <Section
            eyebrow="Contratti"
            title="Tutti i contratti del suo ramo"
            aside={
              <div className="subnav !p-0">
                <button className="subnav-pill" data-active={!onlyProblems} onClick={() => setOnlyProblems(false)}>Tutti</button>
                <button className="subnav-pill" data-active={onlyProblems} onClick={() => setOnlyProblems(true)}>Solo con problemi</button>
              </div>
            }
          >
            {!contracts ? (
              <div className="h-32 animate-pulse rounded-2xl bg-white/5" />
            ) : filteredContracts.length === 0 ? (
              <Empty>Nessun contratto.</Empty>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr>
                      <th className="px-4">Intestatario</th>
                      <th className="px-4">Offerta</th>
                      <th className="px-4">Situazione</th>
                      <th className="px-4 text-right">Valore</th>
                      <th className="px-4 text-right">Compensi</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredContracts.map((c) => (
                      <tr key={c.contract_id}>
                        <td className="px-4 py-3">
                          <Identity name={c.customer_name} detail={`venduto da ${c.producer_name}`} />
                        </td>
                        <td className="px-4 py-3">
                          <div className="font-semibold text-white">{c.product_name}</div>
                          {c.supply_point_label && <div className="text-[11px] text-surface-400">{c.supply_point_label}</div>}
                        </td>
                        <td className="px-4 py-3">
                          <Chip tone={c.is_problem ? "bad" : c.status === "ACTIVE" ? "ok" : "warn"} live={c.is_problem}>
                            {STATUS_LABELS[c.status] ?? c.status}
                          </Chip>
                          {c.admin_note && <div className="mt-1 text-[11px] text-surface-400">{c.admin_note}</div>}
                        </td>
                        <td className="px-4 py-3"><Figure value={euro(c.value_cents)} /></td>
                        <td className="px-4 py-3">
                          <Figure
                            value={euro(c.commission_cents)}
                            detail={c.my_commission_cents != null ? `tua quota ${euro(c.my_commission_cents)}` : undefined}
                          />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Section>
        </div>
      )}

      {tab === "roles" && (
        <div className="grid gap-6 lg:grid-cols-2">
          <Section eyebrow="Storia" title="Ruoli commerciali">
            {card.role_history.length === 0 ? (
              <Empty>Nessun ruolo registrato.</Empty>
            ) : (
              <ol className="relative space-y-4 border-l border-white/15 pl-6">
                {card.role_history.map((r, i) => (
                  <li key={`${r.role_name}-${r.valid_from}`} className="relative" style={{ "--i": i } as CSSProperties}>
                    <span className="absolute -left-[31px] top-1 h-3 w-3 rounded-full bg-gradient-to-br from-white to-accent-400 shadow-[0_0_12px_#47e2ff]" />
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-bold text-white">{r.role_name}</span>
                      {!r.valid_to && <Chip tone="ok">attuale</Chip>}
                    </div>
                    <p className="text-xs text-surface-300">
                      dal {day(r.valid_from)}{r.valid_to ? ` al ${day(r.valid_to)}` : ""}
                    </p>
                    {r.reason && <p className="mt-1 text-xs text-surface-400">{r.reason}</p>}
                  </li>
                ))}
              </ol>
            )}
          </Section>
          <Section eyebrow="Deleghe" title="Per chi vende e chi vende per lui">
            <div className="space-y-5">
              <DelegationList
                title="Vende per conto di"
                empty="Non rappresenta nessun influencer."
                rows={card.delegations.represents}
                onOpen={open}
              />
              <DelegationList
                title="Delegati che vendono per lui"
                empty="Nessun delegato."
                rows={card.delegations.delegates}
                onOpen={open}
              />
            </div>
          </Section>
        </div>
      )}
    </div>
  );
}

/** How the sale reached this collaborator: their own, from N levels below, or by another rule. */
function distanceLabel(p: AgentCardRead["plans"][number]["people"][number], selfId: string): string {
  if (p.agent_id === selfId || p.via === "SELLER") return "vendita propria";
  if (p.level) return `${p.level} ${p.level === 1 ? "livello" : "livelli"} sotto`;
  if (p.via === "INFLUENCER") return "tramite delega";
  if (p.via === "PROMOTER") return "sua segnalazione";
  if (p.via === "ROLE_IN_UPLINE") return "per il suo ruolo";
  return "altra regola";
}

/**
 * The card as a popup over the network tree, so the tree stays where it was.
 * Rendered into <body> through a portal: no ancestor of the tree can trap or
 * move it. Opening another collaborator from inside swaps the card in place.
 */
export function AgentCardModal({
  agentId,
  onClose,
  onOpenAgent,
  canOpen,
}: {
  agentId: string;
  onClose: () => void;
  onOpenAgent?: (agentId: string) => void;
  canOpen?: (agentId: string) => boolean;
}) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = previous;
      document.removeEventListener("keydown", onKey);
    };
  }, [onClose]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: 0 });
  }, [agentId]);

  if (typeof document === "undefined") return null;
  return createPortal(
    <div
      ref={scrollRef}
      className="fixed inset-0 z-[80] overflow-y-auto bg-black/75 backdrop-blur-sm animate-fade-in"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
      role="dialog"
      aria-modal="true"
    >
      <div className="mx-auto my-4 w-full max-w-[1400px] px-3 sm:my-8 sm:px-6" onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}>
        <div className="sheet pop relative rounded-[28px] bg-[#04121d] p-4 shadow-[0_40px_120px_-30px_rgba(0,0,0,0.95)] ring-1 ring-white/10 sm:p-6">
          <div className="sticky top-2 z-10 flex justify-end">
            <button
              onClick={onClose}
              aria-label="Chiudi la scheda"
              className="grid h-11 w-11 cursor-pointer place-items-center rounded-2xl bg-white text-[#041f3a] shadow-xl transition hover:scale-105"
            >
              <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.6} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
          <div className="-mt-11">
            <AgentCardPage
              key={agentId}
              agentId={agentId}
              onBack={onClose}
              onOpenAgent={onOpenAgent}
              canOpen={canOpen}
              hideBack
            />
          </div>
        </div>
      </div>
    </div>,
    document.body,
  );
}

/** Contract products grouped by company; picking one opens its network. */
function ProductPicker({
  catalog,
  companies,
  onPick,
  name,
}: {
  catalog: ProductCatalogRead[] | undefined;
  companies: CompanyRead[] | undefined;
  onPick: (productId: string) => void;
  name: string;
}) {
  if (!catalog || !companies) return <div className="panel h-40 animate-pulse rounded-3xl" />;
  const products = catalog.filter((p) => p.category === "INTERNAL" && p.status === "ACTIVE");
  const groups = [
    ...companies.map((c) => ({ key: c.id, company: c as CompanyRead | null, items: products.filter((p) => p.company_id === c.id) })),
    { key: "NONE", company: null, items: products.filter((p) => !p.company_id) },
  ].filter((g) => g.items.length > 0);
  return (
    <div className="space-y-5">
      <Section eyebrow="Rete per prodotto" title={`Scegli un prodotto per vedere chi, nella rete di ${name}, lo ha acquistato`}>
        <p className="text-sm text-surface-300">
          La vista mostra solo gli acquirenti di quel prodotto, livello per livello, fino alla profondità dell&apos;azienda.
        </p>
      </Section>
      {groups.map((g) => (
        <Section
          key={g.key}
          eyebrow="Azienda"
          title={g.company?.name ?? "Prodotti senza azienda"}
          aside={
            <Chip tone="info">
              {g.company?.max_network_depth ? `Fino a ${g.company.max_network_depth} livelli` : "Nessun limite di livelli"}
            </Chip>
          }
        >
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {g.items.map((p) => (
              <button
                key={p.id}
                onClick={() => onPick(p.id)}
                className="group flex items-center gap-4 rounded-2xl bg-white/5 p-3 text-left transition hover:bg-white/10"
              >
                {p.current_version?.image_url ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={p.current_version.image_url} alt="" className="h-14 w-20 rounded-xl object-cover" />
                ) : (
                  <Orb name={p.current_version?.name ?? p.code} />
                )}
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-bold text-white">{p.current_version?.name ?? p.code}</span>
                  <span className="text-[11px] text-surface-400">Apri la rete di questo prodotto →</span>
                </span>
              </button>
            ))}
          </div>
        </Section>
      ))}
    </div>
  );
}

function LevelBars({ levels, max }: { levels: AgentCardRead["network"]["levels"]; max: number }) {
  if (levels.length === 0) return <Empty>Nessuno sotto di lui, per ora.</Empty>;
  return (
    <div className="space-y-3">
      {levels.map((l) => (
        <div key={l.depth} className="flex items-center gap-4">
          <span className="orb !h-9 !w-9 !text-xs">{l.depth}</span>
          <div className="flex-1">
            <div className="flex justify-between text-xs text-surface-300">
              <span>{l.depth === 1 ? "Dirette" : `Livello ${l.depth}`}</span>
              <span className="font-bold text-white">
                {l.people} {l.people === 1 ? "persona" : "persone"}
                {l.active !== l.people && <span className="font-normal text-surface-400"> · {l.active} attive</span>}
              </span>
            </div>
            <div className="meter mt-1.5 !h-2">
              <i style={{ width: `${Math.max(4, (l.people / max) * 100)}%` }} />
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

function DelegationList({
  title,
  empty,
  rows,
  onOpen,
}: {
  title: string;
  empty: string;
  rows: AgentCardRead["delegations"]["delegates"];
  onOpen: (id: string | null) => (() => void) | undefined;
}) {
  return (
    <div>
      <p className="kpi-label mb-2">{title}</p>
      {rows.length === 0 ? (
        <p className="text-sm text-surface-400">{empty}</p>
      ) : (
        <ul className="space-y-2">
          {rows.map((d) => (
            <li key={`${d.agent_id}-${d.valid_from}`} className="flex items-center justify-between gap-3 rounded-2xl bg-white/5 p-3">
              <button onClick={onOpen(d.agent_id)} disabled={!onOpen(d.agent_id)} className="text-left disabled:cursor-default">
                <Identity name={d.name} detail={`dal ${day(d.valid_from)}${d.valid_to ? ` al ${day(d.valid_to)}` : ""}`} />
              </button>
              <Chip tone={d.active ? "ok" : "muted"}>{d.active ? "In corso" : "Chiusa"}</Chip>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
