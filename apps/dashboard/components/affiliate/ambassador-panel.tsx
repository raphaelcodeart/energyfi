"use client";

import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Chip, KpiTile } from "@/components/ui/data-cells";
import { AmbassadorLicenses } from "@/components/affiliate/license-register";
import { MamifyOrders } from "@/components/affiliate/mamify-orders";
import { NetworkTree } from "@/components/affiliate/network-tree";
import { VirtualNetworkButton } from "@/components/affiliate/virtual-network-button";
import { Empty, ErrorNote, Field, Loading, Modal, OkNote, Progress, Rainbow, SectionTitle } from "@/components/affiliate/shared";
import {
  affiliateGet,
  affiliateSend,
  bc,
  COMMISSION_LABELS,
  COMMISSION_STATUS,
  eur,
  LICENSE_STATUS,
  mamicash,
  num,
  OPERATION_LABELS,
  OPERATION_STATUS,
  periodLabel,
  productName,
  shortDate,
  type AffiliateSummary,
  type Catalog,
  type ClientRow,
  type CommissionRow,
  type LicenseRow,
  type OperationRow,
  type TreeRow,
} from "@/lib/affiliate";

/*
 * Digital Ambassador area (spec §10.2, UI-01..UI-10). The views are sections
 * of the promoter console; `view` is the console's active key.
 */

export type AmbassadorView = "sos-plan" | "sos-orders" | "sos-shop" | "sos-licenses" | "sos-clients" | "sos-earnings" | "sos-network" | "sos-history";

const KEYS = {
  me: ["affiliate", "me"],
  catalog: ["affiliate", "catalog"],
  operations: ["affiliate", "me", "operations"],
  licenses: ["affiliate", "me", "licenses"],
  clients: ["affiliate", "me", "clients"],
  commissions: ["affiliate", "me", "commissions"],
  network: ["affiliate", "me", "network"],
};

function useMe() {
  return useQuery({ queryKey: KEYS.me, queryFn: () => affiliateGet<AffiliateSummary>("/me") });
}

function useCatalog() {
  return useQuery({ queryKey: KEYS.catalog, queryFn: () => affiliateGet<Catalog>("/catalog"), staleTime: 300_000 });
}

function useInvalidateAll() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: ["affiliate"] });
}

/** Opening the page makes the server re-read one's own Mamify orders in the
 * background: a purchase just made shows up with one more look, ~20 s later. */
function useOwnOrdersRefresh() {
  const { data } = useMe();
  const invalidate = useInvalidateAll();
  const queued = data?.orders_check === "queued";
  useEffect(() => {
    if (!queued) return;
    const timer = setTimeout(() => invalidate(), 20_000);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [queued]);
}

export function AmbassadorPanel({ view, onNavigate }: { view: AmbassadorView; onNavigate: (key: AmbassadorView) => void }) {
  useOwnOrdersRefresh();
  switch (view) {
    case "sos-plan":
      return <PlanView onNavigate={onNavigate} />;
    case "sos-orders":
      return <MamifyOrders />;
    case "sos-shop":
      return <ShopView />;
    case "sos-licenses":
      return <AmbassadorLicenses />;
    case "sos-clients":
      return <ClientsView />;
    case "sos-earnings":
      return <EarningsView />;
    case "sos-network":
      return <NetworkView />;
    case "sos-history":
      return <HistoryView />;
  }
}

// --- Il mio piano -------------------------------------------------------------

function PlanView({ onNavigate }: { onNavigate: (key: AmbassadorView) => void }) {
  const { data: me, error, isLoading } = useMe();
  if (isLoading) return <Loading />;
  if (error || !me) return <ErrorNote message={(error as Error)?.message ?? "Profilo non disponibile."} />;
  const c = me.career;
  const totals = (kind: string) => Number(me.commissions[kind]?.payable ?? 0) + Number(me.commissions[kind]?.paid ?? 0);
  const legsAtNext = c.next_leg_min_bc ?? 0;
  return (
    <div className="space-y-6">
      <div className="panel sheen rise relative overflow-hidden rounded-3xl p-6 sm:p-7">
        <div className="flex flex-wrap items-start justify-between gap-6">
          <div className="min-w-0">
            <p className="kpi-label">Bonus Carriera · {periodLabel(me.period)}</p>
            <h2 className="mt-1 text-3xl font-black tracking-tight text-white sm:text-4xl">
              {c.level ? `Livello ${c.level}` : "Nessun livello"}
            </h2>
            <p className="mt-1 text-sm text-surface-200">
              {c.level
                ? <>Bonus maturato questo mese: <strong className="text-white">{eur(c.bonus)}</strong>, pagato il {shortDate(c.pay_on)}.</>
                : "Raggiungi il volume del livello 1 con almeno tre gambe al minimo per maturare il primo bonus."}
            </p>
            <Rainbow className="mt-4 w-40" />
          </div>
          <div className="grid grid-cols-3 gap-3 text-center">
            <Figure label="BC personali" value={num(c.bcp)} hint="BCP" />
            <Figure label="BC delle gambe" value={num(c.bct - c.bcp)} hint="somma BCG" />
            <Figure label="BC totali" value={num(c.bct)} hint="BCT" strong />
          </div>
        </div>
        {c.next_level && (
          <div className="mt-6 grid gap-4 border-t border-white/10 pt-5 md:grid-cols-2">
            <Progress
              label={`Volume per il livello ${c.next_level}`}
              value={c.bct}
              target={c.next_total_bc ?? 0}
              detail={`${num(c.bct)} / ${num(c.next_total_bc)} BC`}
            />
            <Progress
              label={`Gambe con almeno ${num(legsAtNext)} BC`}
              value={c.next_qualifying_legs}
              target={c.required_legs}
              detail={`${c.next_qualifying_legs} / ${c.required_legs}`}
            />
          </div>
        )}
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <KpiTile label="Bonus Carriera" value={eur(totals("BC"))} hint="Pagato il 15 del mese successivo" onClick={() => onNavigate("sos-earnings")} />
        <KpiTile label="Bonus Vendita Diretta" value={eur(totals("BD"))} hint="Pack START · BUSINESS · PREMIUM · INTERNATIONAL" onClick={() => onNavigate("sos-earnings")} />
        <KpiTile label="Bonus MamiCash" value={eur(totals("BM"))} hint="Ricariche dei clienti, 13 posizioni" onClick={() => onNavigate("sos-earnings")} />
        <KpiTile label="Rivendita licenze" value={eur(totals("RESALE"))} hint={`${me.licenses.available} licenze disponibili`} onClick={() => onNavigate("sos-licenses")} />
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="panel rounded-3xl p-5 lg:col-span-2">
          <SectionTitle eyebrow="Gambe della rete" title={`${me.legs.length} gambe · ${num(me.network_size)} persone`} />
          <p className="mt-1 text-xs text-surface-300">
            Una gamba parte da una persona collegata direttamente a te e comprende tutta la sua organizzazione, senza limiti di profondità.
          </p>
          {me.legs.length === 0 ? (
            <p className="mt-4 text-sm text-surface-300">Non hai ancora persone collegate direttamente a te.</p>
          ) : (
            <div className="mt-4 space-y-3">
              {me.legs.map((leg, i) => (
                <Progress
                  key={leg.agent?.id ?? i}
                  label={<>{leg.agent?.name ?? "—"} <span className="text-surface-400">· {num(leg.descendants + 1)} persone</span></>}
                  value={leg.points}
                  target={legsAtNext || 1}
                  detail={bc(leg.points)}
                />
              ))}
            </div>
          )}
        </div>

        <div className="space-y-4">
          <SubscriptionCard me={me} onBuy={() => onNavigate("sos-shop")} />
          {me.rome_event && (me.rome_event.open || me.rome_event.qualified) && (
            <div className="panel rounded-3xl p-5">
              <p className="kpi-label">Promo · Evento di lancio a Roma</p>
              <p className="mt-1 text-sm text-white">
                {num(me.rome_event.target_bc)} punti a {periodLabel(me.rome_event.period)} e sei ospite all&apos;evento.
              </p>
              <div className="mt-3">
                <Progress label="I tuoi BC totali" value={me.rome_event.bct} target={me.rome_event.target_bc}
                  detail={`${num(me.rome_event.bct)} / ${num(me.rome_event.target_bc)}`} />
              </div>
              {me.rome_event.qualified && <div className="mt-3"><Chip tone="ok">Obiettivo raggiunto</Chip></div>}
            </div>
          )}
          <div className="panel rounded-3xl p-5 text-sm">
            <p className="kpi-label">Il tuo sponsor</p>
            <p className="mt-1 font-bold text-white">{me.sponsor?.name ?? "Nessuno (vertice della rete)"}</p>
            {me.sponsor && <p className="tag-id mt-1 text-xs">{me.sponsor.code}</p>}
            <p className="mt-3 text-xs text-surface-300">Codice Digital Ambassador: <span className="tag-id">{me.agent.code}</span></p>
          </div>
        </div>
      </div>

      {me.history.length > 0 && (
        <div className="panel rounded-3xl p-5">
          <SectionTitle eyebrow="Mesi chiusi" title="Storico del Bonus Carriera" />
          <div className="mt-4 overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead><tr><th className="px-4 py-3">Mese</th><th className="px-4 py-3 text-right">BCP</th><th className="px-4 py-3 text-right">BCT</th><th className="px-4 py-3">Livello</th><th className="px-4 py-3 text-right">Bonus</th></tr></thead>
              <tbody>
                {me.history.map((h) => (
                  <tr key={h.period}>
                    <td className="px-4 py-3 capitalize">{periodLabel(h.period)}</td>
                    <td className="px-4 py-3 text-right tabular-nums">{num(h.bcp)}</td>
                    <td className="px-4 py-3 text-right tabular-nums">{num(h.bct)}</td>
                    <td className="px-4 py-3">{h.level ? `Livello ${h.level}` : "—"}</td>
                    <td className="px-4 py-3 text-right tabular-nums">{eur(h.bonus)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

function Figure({ label, value, hint, strong = false }: { label: string; value: string; hint: string; strong?: boolean }) {
  return (
    <div className="rounded-2xl bg-white/5 px-4 py-3">
      <p className="kpi-label">{label}</p>
      <p className={`mt-1 tabular-nums font-black tracking-tight ${strong ? "text-gradient text-3xl" : "text-white text-2xl"}`}>{value}</p>
      <p className="text-[10px] uppercase tracking-wider text-surface-400">{hint}</p>
    </div>
  );
}

function SubscriptionCard({ me, onBuy }: { me: AffiliateSummary; onBuy: () => void }) {
  const s = me.subscription;
  const tone = s.status === "ACTIVE" ? "ok" : s.status === "NONE" ? "muted" : "bad";
  const label = { ACTIVE: "Attivo", SUSPENDED: "Sospeso", CANCELLED: "Cessato", NONE: "Da attivare" }[s.status];
  return (
    <div className="panel rounded-3xl p-5">
      <div className="flex items-center justify-between gap-3">
        <p className="kpi-label">Abbonamento Digital Ambassador</p>
        <Chip tone={tone}>{label}</Chip>
      </div>
      <p className="mt-2 text-sm text-white">
        {eur(s.monthly_fee)} al mese · {s.paid_months} mensilità pagate
      </p>
      <p className="mt-1 text-xs text-surface-300">
        {s.current_period_paid
          ? `La mensilità di ${periodLabel(me.period)} è pagata: 40 BC personali.`
          : `La mensilità di ${periodLabel(me.period)} non è ancora pagata: senza pagamento non genera i 40 BC.`}
      </p>
      {s.months_to_gift_license !== null && (
        <p className="mt-2 text-xs text-accent-300">
          Ancora {s.months_to_gift_license} {s.months_to_gift_license === 1 ? "mensilità" : "mensilità"} per la prossima licenza in omaggio.
        </p>
      )}
      {!s.current_period_paid && (
        <button type="button" onClick={onBuy} className="act act-primary mt-4 w-full justify-center">Paga la mensilità</button>
      )}
    </div>
  );
}

// --- Acquista -----------------------------------------------------------------

function currentPeriod(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}

function ShopView() {
  const { data: catalog } = useCatalog();
  const { data: me } = useMe();
  const invalidate = useInvalidateAll();
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const buy = useMutation({
    mutationFn: (body: { product_code: string; period?: string }) => affiliateSend<OperationRow>("/me/purchases", { ...body, payment_method: "BANK_TRANSFER" }),
    onSuccess: (op) => {
      setError(null);
      setMessage(`Ordine registrato (${eur(op.paid_amount)}). I punti e le licenze arrivano appena l'amministrazione conferma il pagamento.`);
      invalidate();
    },
    onError: (e: Error) => { setMessage(null); setError(e.message); },
  });
  if (!catalog) return <Loading />;
  const cfg = catalog.config;
  const period = currentPeriod();
  if (catalog.external_shop) {
    // Purchases happen on Mamify; points arrive with the paid order.
    return (
      <div className="space-y-6">
        <SectionTitle eyebrow="Acquista" title="Gli acquisti si fanno su Mamify" />
        <div className="panel space-y-3 rounded-3xl p-6">
          <p className="text-sm text-surface-100">
            Mensilità, licenze e biglietti si comprano nell&apos;app Mamify, con il tuo account. Appena Mamify registra il pagamento, i punti e le licenze compaiono qui da soli: non serve fare altro.
          </p>
          <a href="https://www.mamify.app" target="_blank" rel="noopener noreferrer" className="act act-primary inline-flex">Apri Mamify</a>
        </div>
        <div className="panel rounded-3xl p-5">
          <p className="kpi-label mb-3">Quanto vale ogni acquisto</p>
          <ul className="grid gap-2 text-sm sm:grid-cols-2">
            <li className="flex justify-between rounded-2xl bg-white/5 px-4 py-2"><span className="text-surface-200">{cfg.subscription.name} · {eur(cfg.subscription.price)}/mese</span><span className="font-bold text-white">{bc(cfg.subscription.bc)}</span></li>
            {[...cfg.license_products, ...cfg.event_ticket_products].map((p) => (
              <li key={p.code} className="flex justify-between rounded-2xl bg-white/5 px-4 py-2"><span className="text-surface-200">{p.name} · {eur(p.price)}</span><span className="font-bold text-white">{bc(p.bc)}</span></li>
            ))}
          </ul>
        </div>
      </div>
    );
  }
  return (
    <div className="space-y-6">
      <SectionTitle eyebrow="Acquista" title="Abbonamento, licenze e biglietti" />
      <OkNote message={message} />
      <ErrorNote message={error} />

      <div className="panel rounded-3xl p-5">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <p className="kpi-label">{cfg.subscription.name}</p>
            <p className="mt-1 text-2xl font-black text-white">{eur(cfg.subscription.price)} <span className="text-sm font-semibold text-surface-300">al mese</span></p>
            <p className="mt-1 text-xs text-surface-300">Ogni mensilità pagata genera {bc(cfg.subscription.bc)} personali. Ogni {cfg.promotions.gift_license_every_paid_months ?? 6} mensilità pagate, una licenza in omaggio.</p>
          </div>
          <button
            type="button"
            disabled={buy.isPending || me?.subscription.current_period_paid}
            onClick={() => buy.mutate({ product_code: cfg.subscription.code, period })}
            className="act act-primary disabled:opacity-50"
          >
            {me?.subscription.current_period_paid ? `${periodLabel(period)} già pagata` : `Paga ${periodLabel(period)}`}
          </button>
        </div>
      </div>

      <div>
        <p className="kpi-label mb-3">Pacchetti licenze · licenze da rivendere alle imprese</p>
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {cfg.license_products.map((p) => (
            <div key={p.code} className="panel panel-hover flex flex-col rounded-3xl p-5">
              <p className="text-lg font-black text-white">{p.name}</p>
              <p className="text-xs text-surface-300">{p.licenses} {p.licenses === 1 ? "licenza" : "licenze"}</p>
              <div className="mt-4 flex items-baseline gap-2">
                <span className="text-2xl font-black text-white">{eur(p.price)}</span>
                {Number(p.nominal) > Number(p.price) && <span className="text-sm text-surface-400 line-through">{eur(p.nominal)}</span>}
              </div>
              <p className="mt-1 text-sm font-semibold text-accent-300">{bc(p.bc)}</p>
              <button type="button" disabled={buy.isPending} onClick={() => buy.mutate({ product_code: p.code })} className="act act-primary mt-auto w-full justify-center pt-2 disabled:opacity-50">
                Acquista
              </button>
            </div>
          ))}
        </div>
        <p className="mt-2 text-[11px] text-surface-400">I BC sono il totale del pacchetto: non si moltiplicano per il numero di licenze. La rivendita non genera nuovi BC.</p>
      </div>

      <div>
        <p className="kpi-label mb-3">Evento Roma · anche i biglietti generano BC</p>
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {cfg.event_ticket_products.map((p) => (
            <div key={p.code} className="panel panel-hover flex flex-col rounded-3xl p-5">
              <p className="text-lg font-black text-white">{p.tickets} {p.tickets === 1 ? "biglietto" : "biglietti"}</p>
              <p className="mt-3 text-2xl font-black text-white">{eur(p.price)}</p>
              <p className="mt-1 text-sm font-semibold text-accent-300">{bc(p.bc)}</p>
              <button type="button" disabled={buy.isPending} onClick={() => buy.mutate({ product_code: p.code })} className="act act-primary mt-4 w-full justify-center disabled:opacity-50">
                Acquista
              </button>
            </div>
          ))}
        </div>
      </div>

      <PendingOrders />
    </div>
  );
}

function PendingOrders() {
  const { data: ops } = useQuery({ queryKey: KEYS.operations, queryFn: () => affiliateGet<OperationRow[]>("/me/operations") });
  const { data: catalog } = useCatalog();
  const invalidate = useInvalidateAll();
  const [error, setError] = useState<string | null>(null);
  const cancel = useMutation({
    mutationFn: (id: string) => affiliateSend(`/me/operations/${id}/cancel`),
    onSuccess: () => { setError(null); invalidate(); },
    onError: (e: Error) => setError(e.message),
  });
  const pending = (ops ?? []).filter((o) => o.status === "PENDING");
  if (pending.length === 0) return null;
  return (
    <div className="panel rounded-3xl p-5">
      <SectionTitle eyebrow="In attesa di pagamento" title={`${pending.length} ${pending.length === 1 ? "ordine" : "ordini"}`} />
      <p className="mt-1 text-xs text-surface-300">Paga con bonifico indicando il codice dell&apos;ordine: l&apos;amministrazione conferma il pagamento e i punti vengono accreditati.</p>
      <ErrorNote message={error} />
      <div className="mt-3 overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead><tr><th className="px-4 py-3">Ordine</th><th className="px-4 py-3">Codice</th><th className="px-4 py-3 text-right">Importo</th><th className="px-4 py-3"><span className="sr-only">Azioni</span></th></tr></thead>
          <tbody>
            {pending.map((o) => (
              <tr key={o.id}>
                <td className="px-4 py-3">{OPERATION_LABELS[o.kind] ?? o.kind} · {productName(catalog?.config, o.product_code)}{o.client ? ` · ${o.client.name}` : ""}</td>
                <td className="px-4 py-3"><span className="tag-id">{o.id.slice(0, 8).toUpperCase()}</span></td>
                <td className="px-4 py-3 text-right tabular-nums">{eur(o.paid_amount)}</td>
                <td className="px-4 py-3 text-right">
                  <button type="button" disabled={cancel.isPending} onClick={() => cancel.mutate(o.id)} className="act disabled:opacity-50">Annulla</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// --- Imprese clienti ----------------------------------------------------------

function ClientsView() {
  const { data: clients, isLoading } = useQuery({ queryKey: KEYS.clients, queryFn: () => affiliateGet<ClientRow[]>("/me/clients") });
  const [adding, setAdding] = useState(false);
  const [packFor, setPackFor] = useState<ClientRow | null>(null);
  const [topupFor, setTopupFor] = useState<ClientRow | null>(null);
  if (isLoading) return <Loading />;
  const list = clients ?? [];
  return (
    <div className="space-y-6">
      <SectionTitle eyebrow="Imprese clienti" title={`${list.length} ${list.length === 1 ? "impresa" : "imprese"}`}>
        <button type="button" onClick={() => setAdding(true)} className="act act-primary">Nuova impresa</button>
      </SectionTitle>
      <p className="text-xs text-surface-300">
        Ai tuoi clienti vendi i Pack (Bonus Vendita Diretta, 18% a te) e segui le ricariche MamiCash (Bonus MamiCash, 1% a te). Il resto si distribuisce sulla tua rete fino alla tredicesima posizione.
      </p>
      {list.length === 0 ? (
        <Empty>Nessuna impresa cliente. Aggiungi la prima per vendere un Pack, rivendere una licenza o registrare una ricarica MamiCash.</Empty>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead><tr><th className="px-4 py-3">Impresa</th><th className="px-4 py-3">Contatto</th><th className="px-4 py-3 text-right">MamiCash</th><th className="px-4 py-3"><span className="sr-only">Azioni</span></th></tr></thead>
            <tbody>
              {list.map((c) => (
                <tr key={c.id}>
                  <td className="px-4 py-3"><p className="font-bold text-white">{c.company_name}</p>{c.vat_number && <p className="text-xs text-surface-400">P.IVA {c.vat_number}</p>}</td>
                  <td className="px-4 py-3 text-xs text-surface-300">{[c.contact_name, c.email, c.phone].filter(Boolean).join(" · ") || "—"}</td>
                  <td className="px-4 py-3 text-right tabular-nums">{mamicash(c.mamicash_balance)}</td>
                  <td className="px-4 py-3 text-right">
                    <div className="flex justify-end gap-2">
                      <button type="button" onClick={() => setPackFor(c)} className="act act-primary">Vendi Pack</button>
                      <button type="button" onClick={() => setTopupFor(c)} className="act">Ricarica</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {adding && <NewClientModal onClose={() => setAdding(false)} />}
      {packFor && <PackSaleModal client={packFor} onClose={() => setPackFor(null)} />}
      {topupFor && <TopupModal client={topupFor} onClose={() => setTopupFor(null)} />}
    </div>
  );
}

function NewClientModal({ onClose }: { onClose: () => void }) {
  const invalidate = useInvalidateAll();
  const [form, setForm] = useState({ company_name: "", vat_number: "", contact_name: "", email: "", phone: "" });
  const save = useMutation({
    mutationFn: () => affiliateSend("/me/clients", Object.fromEntries(Object.entries(form).map(([k, v]) => [k, v.trim() || null]))),
    onSuccess: () => { invalidate(); onClose(); },
  });
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, [k]: e.target.value });
  return (
    <Modal title="Nuova impresa cliente" onClose={onClose}>
      <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
        <Field label="Ragione sociale"><input required minLength={2} className="field w-full rounded-xl px-3 py-2.5 text-sm" value={form.company_name} onChange={set("company_name")} /></Field>
        <Field label="Partita IVA"><input className="field w-full rounded-xl px-3 py-2.5 text-sm" value={form.vat_number} onChange={set("vat_number")} /></Field>
        <Field label="Referente"><input className="field w-full rounded-xl px-3 py-2.5 text-sm" value={form.contact_name} onChange={set("contact_name")} /></Field>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Email"><input type="email" className="field w-full rounded-xl px-3 py-2.5 text-sm" value={form.email} onChange={set("email")} /></Field>
          <Field label="Telefono"><input className="field w-full rounded-xl px-3 py-2.5 text-sm" value={form.phone} onChange={set("phone")} /></Field>
        </div>
        <ErrorNote message={(save.error as Error | null)?.message} />
        <button type="submit" disabled={save.isPending} className="act act-primary w-full justify-center disabled:opacity-50">Salva</button>
      </form>
    </Modal>
  );
}

function PackSaleModal({ client, onClose }: { client: ClientRow; onClose: () => void }) {
  const { data: catalog } = useCatalog();
  const invalidate = useInvalidateAll();
  const packs = catalog?.config.packs ?? [];
  const direct = catalog ? Number(catalog.config.bd_rates[0]) : 0;
  const [code, setCode] = useState("START");
  const sell = useMutation({
    mutationFn: () => affiliateSend("/me/pack-sales", { client_id: client.id, pack_code: code, payment_method: "BANK_TRANSFER" }),
    onSuccess: () => { invalidate(); onClose(); },
  });
  return (
    <Modal title={`Vendi un Pack a ${client.company_name}`} onClose={onClose}>
      <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); sell.mutate(); }}>
        <div className="grid grid-cols-2 gap-3">
          {packs.map((p) => (
            <button type="button" key={p.code} onClick={() => setCode(p.code)}
              className={`panel rounded-2xl p-4 text-left ${code === p.code ? "ring-2 ring-white/70" : ""}`}>
              <p className="font-black text-white">{p.name}</p>
              <p className="text-lg font-black text-white">{eur(p.price)}</p>
              <p className="text-xs text-accent-300">A te {eur((Number(p.price) * direct) / 100)}</p>
            </button>
          ))}
        </div>
        <p className="text-xs text-surface-300">Il bonus viene calcolato appena l&apos;amministrazione conferma il pagamento del cliente, ed è pagato subito.</p>
        <ErrorNote message={(sell.error as Error | null)?.message} />
        <button type="submit" disabled={sell.isPending} className="act act-primary w-full justify-center disabled:opacity-50">Registra la vendita</button>
      </form>
    </Modal>
  );
}

function TopupModal({ client, onClose }: { client: ClientRow; onClose: () => void }) {
  const invalidate = useInvalidateAll();
  const [amount, setAmount] = useState("100");
  const topup = useMutation({
    mutationFn: () => affiliateSend("/me/topups", { client_id: client.id, amount: amount.replace(",", "."), payment_method: "BANK_TRANSFER" }),
    onSuccess: () => { invalidate(); onClose(); },
  });
  return (
    <Modal title={`Ricarica MamiCash · ${client.company_name}`} onClose={onClose}>
      <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); topup.mutate(); }}>
        <div className="flex flex-wrap gap-2">
          {["50", "100", "250", "500", "1000", "10000"].map((v) => (
            <button type="button" key={v} onClick={() => setAmount(v)} className="subnav-pill" data-active={amount === v || undefined}>{num(Number(v))}</button>
          ))}
        </div>
        <Field label="Valore della ricarica" hint="Le provvigioni si calcolano sul valore nominale dei MamiCash ricaricati: 1% a te, 4% in totale sulla rete.">
          <input inputMode="decimal" className="field w-full rounded-xl px-3 py-2.5 text-sm" value={amount} onChange={(e) => setAmount(e.target.value)} />
        </Field>
        <ErrorNote message={(topup.error as Error | null)?.message} />
        <button type="submit" disabled={topup.isPending} className="act act-primary w-full justify-center disabled:opacity-50">Registra la ricarica</button>
      </form>
    </Modal>
  );
}

// --- I miei bonus -------------------------------------------------------------

function EarningsView() {
  const [kind, setKind] = useState<"BC" | "BD" | "BM" | "RESALE">("BD");
  const { data: me } = useMe();
  const { data: rows, isLoading } = useQuery({
    queryKey: [...KEYS.commissions, kind],
    queryFn: () => affiliateGet<CommissionRow[]>(`/me/commissions?kind=${kind}`),
  });
  return (
    <div className="space-y-6">
      <SectionTitle eyebrow="I miei bonus" title="Tre bonus, tre conteggi distinti" />
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {(["BC", "BD", "BM", "RESALE"] as const).map((k) => (
          <KpiTile key={k} label={COMMISSION_LABELS[k] ?? k} active={kind === k} onClick={() => setKind(k)}
            value={eur(Number(me?.commissions[k]?.payable ?? 0) + Number(me?.commissions[k]?.paid ?? 0))}
            hint={`${eur(me?.commissions[k]?.paid ?? 0)} pagati · ${eur(me?.commissions[k]?.payable ?? 0)} da pagare`} />
        ))}
      </div>
      {isLoading ? <Loading /> : (rows ?? []).length === 0 ? (
        <Empty>Nessun {COMMISSION_LABELS[kind]} ancora maturato.</Empty>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead><tr>
              <th className="px-4 py-3">Origine</th><th className="px-4 py-3">Mese</th>
              <th className="px-4 py-3">{kind === "BC" ? "Livello" : "Posizione"}</th>
              <th className="px-4 py-3 text-right">Base</th><th className="px-4 py-3 text-right">Importo</th><th className="px-4 py-3">Stato</th>
            </tr></thead>
            <tbody>
              {(rows ?? []).map((r) => (
                <tr key={r.id}>
                  <td className="px-4 py-3">
                    {r.kind === "BC" ? "Bonus mensile" : `${OPERATION_LABELS[r.operation?.kind ?? ""] ?? "Operazione"}${r.operation?.product_code && r.kind !== "RESALE" ? ` ${r.operation.product_code}` : ""}`}
                    {r.operation?.seller && r.position > 1 && <span className="text-surface-400"> · venditore {r.operation.seller.name}</span>}
                  </td>
                  <td className="px-4 py-3 capitalize">{periodLabel(r.period)}</td>
                  <td className="px-4 py-3">{r.kind === "BC" ? `Livello ${r.career_level}` : r.kind === "RESALE" ? "—" : `${r.position}ª · ${Number(r.rate)}%`}</td>
                  <td className="px-4 py-3 text-right tabular-nums">{r.kind === "BC" ? bc(Number(r.base_amount)) : eur(r.base_amount)}</td>
                  <td className="px-4 py-3 text-right font-bold tabular-nums">{eur(r.amount)}</td>
                  <td className="px-4 py-3">
                    <Chip tone={COMMISSION_STATUS[r.status]?.tone ?? "muted"}>{COMMISSION_STATUS[r.status]?.label ?? r.status}</Chip>
                    {r.status === "PAYABLE" && r.kind === "BC" && <span className="ml-2 text-[11px] text-surface-400">dal {shortDate(r.payable_on)}</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// --- La mia rete -------------------------------------------------------------

function NetworkView() {
  const { data: catalog } = useCatalog();
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <SectionTitle eyebrow="La mia rete" title="Il tuo albero, ramo per ramo" />
        <VirtualNetworkButton levels={catalog?.config.career_levels} />
      </div>
      <p className="text-xs text-surface-300">
        È la tua rete Mamify. I punti di chi acquista sono personali per lui e contano, una sola volta, nella gamba di ogni sponsor sopra di lui.
      </p>
      <NetworkTree base="me" levels={catalog?.config.career_levels}
        emptyText="La tua rete è ancora vuota: chi si iscrive su Mamify con il tuo invito compare qui." />
    </div>
  );
}

// --- Storico ------------------------------------------------------------------

function HistoryView() {
  const { data: ops, isLoading } = useQuery({ queryKey: KEYS.operations, queryFn: () => affiliateGet<OperationRow[]>("/me/operations") });
  const { data: catalog } = useCatalog();
  if (isLoading) return <Loading />;
  const list = ops ?? [];
  return (
    <div className="space-y-6">
      <SectionTitle eyebrow="Storico" title="Tutte le tue operazioni" />
      {list.length === 0 ? <Empty>Nessuna operazione registrata.</Empty> : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead><tr><th className="px-4 py-3">Operazione</th><th className="px-4 py-3">Data</th><th className="px-4 py-3">Mese</th><th className="px-4 py-3 text-right">Importo</th><th className="px-4 py-3 text-right">BC</th><th className="px-4 py-3">Stato</th></tr></thead>
            <tbody>
              {list.map((o) => (
                <tr key={o.id}>
                  <td className="px-4 py-3">
                    <p className="font-semibold text-white">{OPERATION_LABELS[o.kind] ?? o.kind}</p>
                    <p className="text-xs text-surface-400">{productName(catalog?.config, o.product_code)}{o.client ? ` · ${o.client.name}` : ""}{o.license_code ? ` · ${o.license_code}` : ""}</p>
                  </td>
                  <td className="px-4 py-3">{shortDate(o.created_at)}</td>
                  <td className="px-4 py-3 capitalize">{periodLabel(o.period)}</td>
                  <td className="px-4 py-3 text-right tabular-nums">{eur(o.paid_amount)}</td>
                  <td className="px-4 py-3 text-right tabular-nums">{o.bc_points ? num(o.bc_points) : "—"}</td>
                  <td className="px-4 py-3"><Chip tone={OPERATION_STATUS[o.status]?.tone ?? "muted"}>{OPERATION_STATUS[o.status]?.label ?? o.status}</Chip></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
