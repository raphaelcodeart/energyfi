"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Chip, KpiTile } from "@/components/ui/data-cells";
import { MamifyOrdersPanel } from "@/components/sales/mamify-sales";
import { Empty, ErrorNote, Field, Loading, OkNote, SectionTitle } from "@/components/affiliate/shared";
import {
  affiliateGet,
  COMMISSION_LABELS,
  eur,
  mamifyGet,
  mamifySend,
  num,
  periodLabel,
  shortDate,
  type Catalog,
} from "@/lib/affiliate";

/*
 * The Mamify connection (apps/api/app/modules/mamify). Mamify is only READ:
 * people, tree, orders and products come from it; nothing is ever written
 * there (no webhook registration, no wallet credit). The key is never
 * shown: only whether it is set.
 */

type SyncResult = {
  members?: number; created?: number; moved?: number; updated?: number; missing?: number;
  errors?: string[]; error_count?: number; calls?: number; full?: boolean;
};

type ConfigView = {
  enabled: boolean;
  base_url: string;
  api_key_set: boolean;
  api_key_last4: string | null;
  functionality: string | null;
  root_customer: string | null;
  paid_statuses: string[];
  cancelled_statuses: string[];
  order_apps: string[];
  orders_calls_per_minute: number;
  webhook_url: string;
  webhook_urls: Record<string, string>;
  last_network_sync_at: string | null;
  last_network_sync_result: SyncResult;
  last_new_members_at: string | null;
  network_sync_running: boolean;
  network_sync_progress: { phase?: "read" | "apply"; pages?: number; people?: number; total?: number; done?: number };
  last_orders_sync_at: string | null;
  catalog_refreshed_at: string | null;
  last_error: string | null;
  last_error_at: string | null;
};

type Status = {
  config: ConfigView;
  members: { present: number; missing: number; tree_nodes: number };
  orders: Record<string, number>;
  orders_coverage: { people: number; checked_once: number; oldest_check: string | null };
  failed_webhooks: number;
  last_webhook_at: string | null;
  unmapped_products: { id: string; orders: number }[];
};

type OrderRow = {
  id: string; mamify_order_id: string; state: string; message: string | null; status: string | null; total: string | null;
  ordered_at: string | null; buyer: { mamify_id: string | null; name: string | null }; operations: number; source: string;
  received_at: string; raw: unknown;
};

type RemoteProduct = {
  id: string; name: string | null; app: string | null; app_name: string | null; price: number | string | null;
  promo_price: number | string | null; categories: string[]; available: boolean | null; url: string | null;
};

type DueRow = {
  commission_id: string; kind: string; period: string; amount: string; payable_on: string; beneficiary: string | null;
  mamify_customer_id: string | null; mamify_email: string | null; problem: string | null;
};

const ORDER_STATES: Record<string, { label: string; tone: "ok" | "warn" | "bad" | "muted" | "info" }> = {
  APPLIED: { label: "Applicato", tone: "ok" },
  RECEIVED: { label: "In attesa di pagamento", tone: "info" },
  IGNORED: { label: "Prodotto non abbinato", tone: "muted" },
  UNMATCHED: { label: "Acquirente non in rete", tone: "warn" },
  CANCELLED: { label: "Annullato", tone: "muted" },
  ERROR: { label: "Da verificare", tone: "bad" },
};

type Tab = "setup" | "products" | "orders" | "due";

function useStatus() {
  return useQuery({
    queryKey: ["mamify", "status"],
    queryFn: () => mamifyGet<Status>("/status"),
    // While a copy runs, its progress is worth watching.
    refetchInterval: (q) => (q.state.data?.config.network_sync_running ? 5000 : 60000),
  });
}

function useInvalidate() {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: ["mamify"] });
    qc.invalidateQueries({ queryKey: ["affiliate"] });
  };
}

export function MamifyPanel() {
  const [tab, setTab] = useState<Tab>("setup");
  const { data, isLoading, error } = useStatus();
  if (isLoading) return <Loading />;
  if (error || !data) return <ErrorNote message={(error as Error)?.message} />;
  const c = data.config;
  const toCheck = (data.orders.ERROR ?? 0) + (data.orders.UNMATCHED ?? 0);
  const cov = data.orders_coverage;
  return (
    <div className="space-y-6">
      <SectionTitle eyebrow="Collegamento Mamify" title="Rete e ordini letti da Mamify">
        <Chip tone={c.enabled ? "ok" : "muted"}>{c.enabled ? "Collegamento attivo" : "Collegamento spento"}</Chip>
        <Chip tone="info">Solo lettura</Chip>
      </SectionTitle>
      <p className="text-sm text-surface-300">
        SOS Affiliate <b className="text-white">legge soltanto</b> da Mamify: persone, albero, ordini e prodotti. Non crea, non modifica e non cancella nulla su Mamify, e non accredita portafogli: i compensi calcolati qui si pagano su Mamify.
      </p>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <KpiTile label="Persone dalla rete Mamify" value={num(data.members.present)}
          hint={c.last_network_sync_at ? `copia completa ${shortDate(c.last_network_sync_at)}` : "rete non ancora copiata"} />
        <KpiTile label="Ordini applicati" value={num(data.orders.APPLIED ?? 0)} hint={`${num(data.orders.RECEIVED ?? 0)} in attesa di pagamento`} onClick={() => setTab("orders")} />
        <KpiTile label="Ordini da verificare" value={num(toCheck)} hint={`${data.unmapped_products.length} prodotti visti non abbinati`} onClick={() => setTab(toCheck ? "orders" : "products")} />
        <KpiTile label="Ordini controllati" value={cov.people ? `${Math.floor((cov.checked_once / cov.people) * 100)}%` : "—"}
          hint={`${num(cov.checked_once)} persone su ${num(cov.people)} lette almeno una volta`} />
      </div>
      {c.network_sync_running && <SyncProgress config={c} />}
      {c.last_error && (
        <ErrorNote message={`Ultimo errore (${shortDate(c.last_error_at)}): ${c.last_error}`} />
      )}
      <div className="flex flex-wrap gap-2" role="tablist">
        {([["setup", "Stato e impostazioni"], ["products", "Prodotti"], ["orders", "Ordini ricevuti"], ["due", "Compensi da pagare"]] as const).map(([k, l]) => (
          <button key={k} type="button" role="tab" aria-selected={tab === k} onClick={() => setTab(k)} className={`act ${tab === k ? "act-primary" : ""}`}>{l}</button>
        ))}
      </div>
      {tab === "setup" && <SetupTab status={data} />}
      {tab === "products" && <ProductsTab unmapped={data.unmapped_products} />}
      {tab === "orders" && <OrdersTab />}
      {tab === "due" && <DueTab />}
    </div>
  );
}

function SyncProgress({ config }: { config: ConfigView }) {
  const p = config.network_sync_progress ?? {};
  const totalPages = p.total ? Math.ceil(p.total / 50) : null;
  const pct = p.phase === "read" && totalPages ? Math.min(100, Math.round(((p.pages ?? 0) / totalPages) * 100))
    : p.phase === "apply" && p.people ? Math.min(100, Math.round(((p.done ?? 0) / p.people) * 100)) : null;
  return (
    <div className="panel space-y-2 rounded-3xl p-5" role="status">
      <p className="kpi-label">Copia della rete in corso</p>
      <p className="text-sm text-surface-200">
        {p.phase === "apply"
          ? `Aggiornamento dell'albero: ${num(p.done ?? 0)} di ${num(p.people ?? 0)} persone.`
          : `Lettura da Mamify: ${num(p.people ?? 0)} persone${p.total ? ` di ${num(p.total)}` : ""} (50 per chiamata, entro il limite di 60 chiamate al minuto).`}
      </p>
      {pct !== null && (
        <div className="h-2 overflow-hidden rounded-full bg-white/10"><div className="h-full rounded-full bg-brand-400" style={{ width: `${pct}%` }} /></div>
      )}
    </div>
  );
}

// --- Stato e impostazioni -------------------------------------------------------

type ActionKind = "test" | "sync" | "new" | "recheck" | "retry";

function SetupTab({ status }: { status: Status }) {
  const c = status.config;
  const invalidate = useInvalidate();
  const [note, setNote] = useState<string | null>(null);
  const action = useMutation({
    mutationFn: async (kind: ActionKind) => {
      const path = { test: "/test", sync: "/sync-network", new: "/sync-new-members", recheck: "/import-orders", retry: "/retry-orders" }[kind];
      const result = await mamifySend<Record<string, unknown>>(path);
      // Mamify's own refusals come back inside a 200: show them as errors.
      if (kind === "test" && typeof result.error === "string") throw new Error(result.error);
      return { kind, result };
    },
    onMutate: () => setNote(null),
    onSuccess: ({ kind, result }) => {
      invalidate();
      if (kind === "test") {
        const r = result as { root: { id: string | null; name: string | null; network?: { direct?: number; total?: number } | null } | null };
        setNote(`Chiave valida. ${r.root ? `In cima alla rete: ${r.root.name || "—"} (cliente ${r.root.id})${r.root.network?.total ? `, ${num(r.root.network.total)} persone nella sua rete` : ""}.` : "Cliente in cima alla rete non indicato."}`);
      } else if (kind === "sync") {
        setNote("Copia completa avviata: qui sopra si vede l'avanzamento. Con 50.000 persone richiede circa 20 minuti.");
      } else if (kind === "new") {
        setNote("Controllo dei nuovi iscritti avviato: compaiono nell'albero entro un minuto.");
      } else if (kind === "recheck") {
        setNote(`Gli ordini di ${num((result as { people: number }).people)} persone verranno riletti, a turno, entro il limite di chiamate.`);
      } else {
        setNote(`Riapplicati ${num((result as { retried: number }).retried)} ordini in sospeso.`);
      }
    },
  });
  const sync = c.last_network_sync_result ?? {};
  const busy = action.isPending;
  const ready = c.enabled && c.api_key_set && !!c.root_customer;
  const cov = status.orders_coverage;
  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_380px]">
      <ConfigForm key={JSON.stringify(c)} initial={c} />
      <div className="space-y-4">
        <div className="panel space-y-3 rounded-3xl p-5">
          <p className="kpi-label">Azioni</p>
          <div className="grid gap-2">
            <button type="button" className="act justify-center" disabled={busy || !c.api_key_set} onClick={() => action.mutate("test")}>Prova il collegamento</button>
            <button type="button" className="act act-primary justify-center" disabled={busy || !ready || c.network_sync_running} onClick={() => action.mutate("sync")}>Copia tutta la rete adesso</button>
            <button type="button" className="act justify-center" disabled={busy || !ready || c.network_sync_running} onClick={() => action.mutate("new")}>Cerca i nuovi iscritti adesso</button>
            <button type="button" className="act justify-center" disabled={busy || !ready} onClick={() => action.mutate("recheck")}>Rileggi gli ordini di tutti</button>
            <button type="button" className="act justify-center" disabled={busy} onClick={() => action.mutate("retry")}>Riapplica gli ordini in sospeso</button>
          </div>
          <OkNote message={note} />
          <ErrorNote message={(action.error as Error | null)?.message} />
        </div>
        <div className="panel space-y-2 rounded-3xl p-5 text-xs">
          <p className="kpi-label">Come si aggiorna</p>
          <ul className="list-disc space-y-1 pl-4 text-surface-300">
            <li><b className="text-surface-100">Nuovi iscritti</b>: ogni 5 minuti, e subito quando Mamify manda l&apos;avviso «nuovo cliente». Ultimo controllo: {c.last_new_members_at ? shortDate(c.last_new_members_at) : "mai"}.</li>
            <li><b className="text-surface-100">Tutta la rete</b> (sponsor cambiati, persone uscite): ogni notte alle 3:15 circa.</li>
            <li><b className="text-surface-100">Ordini</b>: Mamify li fornisce una persona alla volta, quindi si leggono a turno ({num(c.orders_calls_per_minute)} persone al minuto). Prima chi ha una rete o ordini aperti, almeno ogni ora. {cov.oldest_check ? `Il controllo più vecchio è del ${shortDate(cov.oldest_check)}.` : "Primo giro in corso."}</li>
          </ul>
        </div>
        <div className="panel space-y-2 rounded-3xl p-5 text-xs">
          <p className="kpi-label">Ultima copia completa</p>
          {c.last_network_sync_at ? (
            <>
              <p className="text-surface-200">{shortDate(c.last_network_sync_at)} · {num(sync.members)} persone · {num(sync.created)} nuove · {num(sync.moved)} spostate · {num(sync.missing)} uscite{sync.calls ? ` · ${num(sync.calls)} chiamate` : ""}</p>
              {(sync.errors ?? []).length > 0 && (
                <ul className="mt-1 list-disc space-y-0.5 pl-4 text-danger-300">{(sync.errors ?? []).map((e, i) => <li key={i}>{e}</li>)}</ul>
              )}
            </>
          ) : <p className="text-surface-300">Non ancora eseguita.</p>}
          <p className="pt-2 text-surface-400">Nodi nell&apos;albero SOS: {num(status.members.tree_nodes)} · usciti da Mamify: {num(status.members.missing)}</p>
        </div>
        <div className="panel space-y-2 rounded-3xl p-5 text-xs">
          <p className="kpi-label">Avvisi da Mamify (facoltativi)</p>
          <p className="text-surface-300">
            Con gli avvisi, ordini e nuovi iscritti arrivano in pochi secondi invece che a turno. SOS non li registra da solo, perché sarebbe una scrittura su Mamify: se volete, li registra lo staff di Mamify dal CRM con questi indirizzi.
          </p>
          {Object.entries(c.webhook_urls ?? {}).map(([type, url]) => (
            <div key={type}>
              <p className="text-surface-200">{type}</p>
              <code className="block break-all rounded-xl bg-black/30 p-2 text-[11px] text-surface-100">{url}</code>
            </div>
          ))}
          <p className="text-surface-400">
            Ultimo avviso ricevuto: {status.last_webhook_at ? shortDate(status.last_webhook_at) : "mai"}
            {status.failed_webhooks ? ` · ${status.failed_webhooks} con errore` : ""}
          </p>
        </div>
      </div>
    </div>
  );
}

function ConfigForm({ initial }: { initial: ConfigView }) {
  const invalidate = useInvalidate();
  const [form, setForm] = useState({
    enabled: initial.enabled,
    base_url: initial.base_url,
    api_key: "",
    functionality: initial.functionality ?? "",
    root_customer: initial.root_customer ?? "",
    paid_statuses: initial.paid_statuses.join(", "),
    cancelled_statuses: initial.cancelled_statuses.join(", "),
    order_apps: initial.order_apps.join(", "),
    orders_calls_per_minute: String(initial.orders_calls_per_minute),
  });
  const set = <K extends keyof typeof form>(k: K, v: (typeof form)[K]) => setForm((f) => ({ ...f, [k]: v }));
  const save = useMutation({
    mutationFn: () => mamifySend("/config", {
      ...form,
      api_key: form.api_key || undefined,
      orders_calls_per_minute: Number(form.orders_calls_per_minute),
    }, "PATCH"),
    onSuccess: () => invalidate(),
  });
  return (
    <form className="panel space-y-5 rounded-3xl p-5" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
      <div>
        <p className="kpi-label">Accesso alle API (sola lettura)</p>
        <div className="mt-3 grid gap-4 sm:grid-cols-2">
          <Field label="Chiave API" hint={initial.api_key_set ? `Impostata (…${initial.api_key_last4}). Lascia vuoto per non cambiarla.` : "CRM di Mamify: Sviluppatori → API → Chiavi API, con spuntati solo i percorsi «Mamify > Rag»."}>
            <input className="field w-full rounded-xl px-3 py-2 text-sm" type="password" autoComplete="off" value={form.api_key} onChange={(e) => set("api_key", e.target.value)} placeholder={initial.api_key_set ? "••••••••" : ""} />
          </Field>
          <Field label="Indirizzo delle API">
            <input className="field w-full rounded-xl px-3 py-2 text-sm" value={form.base_url} onChange={(e) => set("base_url", e.target.value)} />
          </Field>
          <Field label="Cliente Mamify in cima alla rete" hint="Id cliente, email o codice invito: si copia tutta la rete sotto di lui. Lui stesso non entra nell'albero.">
            <input className="field w-full rounded-xl px-3 py-2 text-sm" value={form.root_customer} onChange={(e) => set("root_customer", e.target.value)} />
          </Field>
          <Field label="Codice app Mamify" hint="L'app di SOS Affiliate su Mamify (sos-affiliate).">
            <input className="field w-full rounded-xl px-3 py-2 text-sm" value={form.functionality} onChange={(e) => set("functionality", e.target.value)} />
          </Field>
        </div>
      </div>
      <div>
        <p className="kpi-label">Ordini</p>
        <p className="mt-1 text-xs text-surface-300">Un ordine genera punti e bonus quando Mamify lo dà per pagato. Gli stati sono quelli di Mamify, per nome o per numero, separati da virgola.</p>
        <div className="mt-3 grid gap-4 sm:grid-cols-2">
          <Field label="Altri stati «pagato» (facoltativo)" hint="Di norma basta l'indicazione «pagato» che Mamify dà su ogni ordine.">
            <input className="field w-full rounded-xl px-3 py-2 text-sm" value={form.paid_statuses} onChange={(e) => set("paid_statuses", e.target.value)} placeholder="Completato" />
          </Field>
          <Field label="Stati «annullato o rimborsato»">
            <input className="field w-full rounded-xl px-3 py-2 text-sm" value={form.cancelled_statuses} onChange={(e) => set("cancelled_statuses", e.target.value)} placeholder="Annullato, Rimborsato" />
          </Field>
          <Field label="App Mamify i cui prodotti contano" hint="Gli ordini di altre app (gift card, altri negozi) non vengono nemmeno salvati.">
            <input className="field w-full rounded-xl px-3 py-2 text-sm" value={form.order_apps} onChange={(e) => set("order_apps", e.target.value)} placeholder="sos-affiliate, digitalambassador" />
          </Field>
          <Field label="Persone lette al minuto per gli ordini" hint="Parte del limite della chiave (60 chiamate al minuto). Il resto serve alla rete e agli accessi.">
            <input className="field w-full rounded-xl px-3 py-2 text-sm" inputMode="numeric" value={form.orders_calls_per_minute} onChange={(e) => set("orders_calls_per_minute", e.target.value)} />
          </Field>
        </div>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-white/10 pt-4">
        <label className="flex items-center gap-2 text-sm font-semibold text-white">
          <input type="checkbox" checked={form.enabled} onChange={(e) => set("enabled", e.target.checked)} />
          Collegamento attivo
        </label>
        <button type="submit" className="act act-primary" disabled={save.isPending}>{save.isPending ? "Salvataggio…" : "Salva le impostazioni"}</button>
      </div>
      {save.isSuccess && <OkNote message="Impostazioni salvate." />}
      <ErrorNote message={(save.error as Error | null)?.message} />
    </form>
  );
}

// --- Prodotti -------------------------------------------------------------------

function planOptions(catalog: Catalog | undefined): { code: string; label: string }[] {
  if (!catalog) return [];
  const c = catalog.config;
  return [
    { code: c.subscription.code, label: `${c.subscription.name} (mensilità · ${c.subscription.bc} BC)` },
    ...c.license_products.map((p) => ({ code: p.code, label: `Licenze ${p.name} (${p.licenses} · ${p.bc} BC)` })),
    ...c.event_ticket_products.map((p) => ({ code: p.code, label: `${p.name} (${p.bc} BC)` })),
    ...c.packs.map((p) => ({ code: p.code, label: `Pack ${p.name} (BD su ${eur(p.price)})` })),
    { code: "MAMICASH_TOPUP", label: "Ricarica MamiCash (BM sul valore dell'ordine)" },
    { code: "LICENSE_RESALE", label: `Rivendita licenza a un'impresa (${eur(c.license_resale.price)}: ${eur(c.license_resale.seller_amount)} al suo sponsor)` },
  ];
}

function price(p: RemoteProduct): string {
  const base = p.price !== null && p.price !== undefined ? eur(String(p.price)) : "—";
  return p.promo_price ? `${eur(String(p.promo_price))} (listino ${base})` : base;
}

function ProductsTab({ unmapped }: { unmapped: { id: string; orders: number }[] }) {
  const invalidate = useInvalidate();
  const qc = useQueryClient();
  const { data: catalog } = useQuery({ queryKey: ["affiliate", "catalog"], queryFn: () => affiliateGet<Catalog>("/catalog"), staleTime: 300_000 });
  const { data: mapped, isLoading } = useQuery({
    queryKey: ["mamify", "products"],
    queryFn: () => mamifyGet<{ mamify_product_id: string; title: string | null; plan_code: string }[]>("/products"),
  });
  const remote = useQuery({ queryKey: ["mamify", "remote-products"], queryFn: () => mamifyGet<RemoteProduct[]>("/remote-products") });
  const refresh = useMutation({
    mutationFn: () => mamifyGet<RemoteProduct[]>("/remote-products?refresh=true"),
    onSuccess: (rows) => qc.setQueryData(["mamify", "remote-products"], rows),
  });
  const map = useMutation({
    mutationFn: (v: { mamify_product_id: string; plan_code: string | null; title?: string | null }) => mamifySend("/products", v, "PUT"),
    onSuccess: () => invalidate(),
  });
  const options = planOptions(catalog);
  const codeOf = new Map((mapped ?? []).map((m) => [m.mamify_product_id, m.plan_code]));
  const known = new Set((remote.data ?? []).map((p) => p.id));
  const select = (id: string, title?: string | null) => (
    <select className="field w-full rounded-xl px-3 py-2 text-sm" value={codeOf.get(id) ?? ""} disabled={map.isPending}
      aria-label={`Prodotto del piano per ${title ?? id}`}
      onChange={(e) => map.mutate({ mamify_product_id: id, plan_code: e.target.value || null, title })}>
      <option value="">Non conta per il piano</option>
      {options.map((o) => <option key={o.code} value={o.code}>{o.label}</option>)}
    </select>
  );
  const byApp = new Map<string, RemoteProduct[]>();
  for (const p of remote.data ?? []) byApp.set(p.app_name || p.app || "—", [...(byApp.get(p.app_name || p.app || "—") ?? []), p]);
  return (
    <div className="space-y-6">
      <p className="text-sm text-surface-300">
        Ogni prodotto Mamify che conta per il piano va abbinato al prodotto SOS che rappresenta. Punti e bonus restano quelli del piano: l&apos;abbinamento dice solo «questo prodotto Mamify è il pacchetto LARGE». Negli ordini Mamify indica nome, app e prezzo, non l&apos;id: SOS riconosce il prodotto da questi tre. Gli ordini arrivati prima dell&apos;abbinamento vengono riapplicati subito.
      </p>
      <ErrorNote message={(map.error as Error | null)?.message} />
      <div className="panel space-y-3 rounded-3xl p-5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="kpi-label">Prodotti delle app SOS su Mamify</p>
          <button type="button" className="act" disabled={refresh.isPending} onClick={() => refresh.mutate()}>{refresh.isPending ? "Lettura…" : "Rileggi da Mamify"}</button>
        </div>
        <ErrorNote message={((remote.error || refresh.error) as Error | null)?.message} />
        {remote.isLoading || isLoading ? <Loading /> : (remote.data ?? []).length === 0 ? <p className="text-sm text-surface-300">Nessun prodotto trovato nelle app indicate.</p> : (
          [...byApp.entries()].map(([app, rows]) => (
            <div key={app} className="space-y-2 pt-2">
              <p className="text-xs font-bold uppercase tracking-wide text-surface-400">{app}</p>
              {rows.map((p) => (
                <div key={p.id} className="grid items-center gap-2 sm:grid-cols-[1fr_minmax(0,22rem)]">
                  <p className="text-sm text-white">{p.name || "—"} <span className="text-surface-400">· {price(p)} · {p.categories.join(", ") || "senza categoria"} · id {p.id}</span></p>
                  {select(p.id, p.name)}
                </div>
              ))}
            </div>
          ))
        )}
      </div>
      {unmapped.length > 0 && (
        <div className="panel rounded-3xl p-5">
          <p className="kpi-label mb-3">Visti negli ordini, non ancora abbinati</p>
          <div className="space-y-2">
            {unmapped.map((u) => (
              <div key={u.id} className="grid items-center gap-2 sm:grid-cols-[1fr_minmax(0,22rem)]">
                <p className="text-sm text-white">{known.has(u.id) ? `Prodotto ${u.id}` : u.id} <span className="text-surface-400">· in {u.orders} ordini</span></p>
                {known.has(u.id) ? select(u.id) : <p className="text-xs text-surface-400">Non riconosciuto nel catalogo: rileggi i prodotti da Mamify.</p>}
              </div>
            ))}
          </div>
        </div>
      )}
      {(mapped ?? []).some((m) => !known.has(m.mamify_product_id)) && (
        <div className="panel rounded-3xl p-5">
          <p className="kpi-label mb-3">Abbinati ma non più nel catalogo</p>
          <div className="space-y-2">
            {(mapped ?? []).filter((m) => !known.has(m.mamify_product_id)).map((m) => (
              <div key={m.mamify_product_id} className="grid items-center gap-2 sm:grid-cols-[1fr_minmax(0,22rem)]">
                <p className="text-sm text-white">{m.title || "Prodotto"} <span className="text-surface-400">· id {m.mamify_product_id}</span></p>
                {select(m.mamify_product_id, m.title)}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// --- Ordini ---------------------------------------------------------------------

function OrdersTab() {
  return <MamifyOrdersPanel />;
}

// --- Compensi da pagare su Mamify ----------------------------------------------

function DueTab() {
  const due = useQuery({ queryKey: ["mamify", "payouts-due"], queryFn: () => mamifyGet<DueRow[]>("/payouts/due") });
  const ready = (due.data ?? []).filter((d) => !d.problem);
  const total = ready.reduce((s, d) => s + Number(d.amount), 0);
  const csv = () => {
    const rows = [["cliente_mamify", "email", "beneficiario", "compenso", "periodo", "importo_eur", "dovuto_dal"],
      ...ready.map((d) => [d.mamify_customer_id ?? "", d.mamify_email ?? "", d.beneficiary ?? "", d.kind, d.period, d.amount, d.payable_on])];
    const text = rows.map((r) => r.map((v) => `"${String(v).replaceAll('"', '""')}"`).join(";")).join("\n");
    const url = URL.createObjectURL(new Blob([text], { type: "text/csv;charset=utf-8" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `compensi-da-pagare-su-mamify-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };
  return (
    <div className="space-y-6">
      <p className="text-sm text-surface-300">
        SOS calcola i compensi; li paga lo staff di Mamify sui portafogli MamiCash o Mamix, dal CRM. Questa è la lista dei dovuti con il cliente Mamify di ciascun beneficiario. Una volta pagati, si segnano come pagati in «Compensi BC · BD · BM».
      </p>
      <div className="panel space-y-3 rounded-3xl p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="kpi-label">Dovuti oggi</p>
            <p className="text-2xl font-black text-white">{eur(total)} <span className="text-sm font-semibold text-surface-300">· {ready.length} compensi</span></p>
          </div>
          <button type="button" className="act act-primary" disabled={ready.length === 0} onClick={csv}>Scarica la lista (CSV)</button>
        </div>
        {due.isLoading ? <Loading /> : due.error ? <ErrorNote message={(due.error as Error).message} /> : (due.data ?? []).length === 0 ? <p className="text-sm text-surface-300">Nessun compenso dovuto.</p> : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead><tr><th className="px-4 py-3">Beneficiario</th><th className="px-4 py-3">Cliente Mamify</th><th className="px-4 py-3">Compenso</th><th className="px-4 py-3 text-right">Importo</th></tr></thead>
              <tbody>
                {(due.data ?? []).map((d) => (
                  <tr key={d.commission_id}>
                    <td className="px-4 py-3 text-white">{d.beneficiary ?? "—"}</td>
                    <td className="px-4 py-3">{d.problem ? <span className="text-xs text-warn-300">{d.problem}</span> : <>{d.mamify_customer_id}<p className="text-xs text-surface-400">{d.mamify_email}</p></>}</td>
                    <td className="px-4 py-3">{COMMISSION_LABELS[d.kind] ?? d.kind}<p className="text-xs capitalize text-surface-400">{periodLabel(d.period)}</p></td>
                    <td className="px-4 py-3 text-right tabular-nums">{eur(d.amount)}</td>
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
