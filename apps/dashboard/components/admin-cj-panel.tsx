"use client";

import { useState } from "react";
import type { CSSProperties } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { friendlyApiError } from "@/lib/api-error";
import { vatLineLabel } from "@/lib/product-audience";
import { Pagination, usePagination } from "@/components/pagination";
import { ProductThumbnail } from "@/components/product-thumbnail";
import { Chip, Figure, IdTag, Identity, KpiTile, RowActions, Stack } from "@/components/ui/data-cells";
import type { ChipTone } from "@/components/ui/data-cells";
import { ProductCategoriesField, saveProductCategories, sameCategorySelection, ManageCategoriesButton } from "@/components/shop-categories-card";
import type {
  CjCashSummary,
  CjCatalogPage,
  CjOrderRead,
  CjProductAdminRead,
  CjProductPreview,
  CjSettingsRead,
} from "@/lib/types";

type Tab = "orders" | "products" | "catalog" | "settings";

function euro(cents: number): string {
  return (cents / 100).toLocaleString("it-IT", { style: "currency", currency: "EUR" });
}

function usd(value: number | string | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  return `$${value}`;
}

/**
 * Mirrors the server formula (cj_dropshipping/pricing.py) for a live preview;
 * the server's figure is authoritative.
 */
function salePriceCents(
  costUsd: number, rules: Pick<CjSettingsRead, "usd_eur_rate" | "markup_fixed_cents" | "price_rounding" | "shipping_mode">,
  markupPct: number, shippingUsd?: number | null,
): number {
  const rate = Number(rules.usd_eur_rate);
  let base = costUsd * rate * 100 * (1 + markupPct / 100) + Number(rules.markup_fixed_cents);
  if (rules.shipping_mode === "INCLUDED" && shippingUsd) base += shippingUsd * rate * 100;
  const cents = Math.ceil(Math.round(base * 1e6) / 1e6);
  if (rules.price_rounding === "NONE") return cents;
  const target = Number(rules.price_rounding);
  const euros = Math.floor(cents / 100);
  return cents % 100 <= target ? euros * 100 + target : (euros + 1) * 100 + target;
}

function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("it-IT", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

function shortDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("it-IT", { day: "2-digit", month: "short", year: "numeric" });
}

/** "3 giorni fa" style hint next to a date. */
function relative(iso: string | null | undefined): string {
  if (!iso) return "";
  const minutes = Math.round((Date.now() - new Date(iso).getTime()) / 60_000);
  if (minutes < 1) return "adesso";
  if (minutes < 60) return `${minutes} min fa`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} h fa`;
  const days = Math.round(hours / 24);
  return days === 1 ? "ieri" : `${days} giorni fa`;
}

async function getJson<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) throw new Error(await friendlyApiError(res));
  return res.json();
}

function postJson<T>(url: string, body?: unknown, method = "POST"): Promise<T> {
  return getJson<T>(url, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

const card = "panel rounded-3xl";
const input = "w-full rounded-lg field px-3 py-2 text-sm focus:border-brand-500";
const label = "block text-[10px] font-extrabold text-surface-300 uppercase tracking-[0.16em] mb-1.5";
const btnPrimary = "inline-flex items-center justify-center px-5 py-2.5 rounded-2xl bg-gradient-to-r from-brand-600 to-accent-500 hover:brightness-110 text-xs font-extrabold text-white shadow-lg shadow-brand-900/40 transition cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed";
const btnGhost = "act";

function Empty({ icon, text }: { icon: string; text: string }) {
  return (
    <div className={`${card} flex flex-col items-center justify-center gap-3 px-6 py-12 text-center`}>
      <span className="float-soft text-4xl" aria-hidden="true">{icon}</span>
      <p className="max-w-md text-sm font-semibold text-surface-300">{text}</p>
    </div>
  );
}

/** Small product photo on a white tile, for table rows. */
function Thumb({ url, alt }: { url: string | null | undefined; alt: string }) {
  return (
    <span className="block h-12 w-12 shrink-0 overflow-hidden rounded-xl bg-white shadow-lg shadow-black/30 ring-1 ring-white/20">
      <ProductThumbnail imageUrl={url} alt={alt} className="h-full w-full object-cover" iconClassName="w-5 h-5 text-brand-400/50" />
    </span>
  );
}

function ErrorBox({ message }: { message: string | null }) {
  if (!message) return null;
  return <div className="p-3.5 rounded-2xl bg-danger-500/15 border border-danger-400/30 text-danger-300 text-xs font-semibold">{message}</div>;
}

/**
 * Shop Sosnet Partner (CJ Dropshipping).
 * Products come from CJ's catalog via API, are re-priced in euro with the
 * organization's markup and sold through the common Shop checkout. Paid
 * orders are sent to CJ (manually or automatically), paid from the CJ
 * balance and tracked until delivery.
 */
export function AdminCjPanel() {
  const { data: settings } = useQuery({
    queryKey: ["admin", "cj", "settings"],
    queryFn: () => getJson<CjSettingsRead>("/api/proxy/cj/settings"),
  });
  const [tab, setTab] = useState<Tab | null>(null);
  const activeTab: Tab = tab ?? (settings && !settings.api_key_configured ? "settings" : "orders");

  const tabs: { key: Tab; label: string }[] = [
    { key: "orders", label: "Ordini" },
    { key: "products", label: "Prodotti in vendita" },
    { key: "catalog", label: "Catalogo CJ" },
    { key: "settings", label: "Impostazioni" },
  ];

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="rise">
          <div className="kpi-label">Marketplace · fornitore CJ</div>
          <h2 className="mt-1 text-3xl font-black tracking-tight text-white">
            Prodotti <span className="text-gradient">CJ Dropshipping</span>
          </h2>
          <p className="text-sm text-surface-300 mt-1 max-w-2xl">
            Prodotti CJ Dropshipping venduti nello Shop: importa, prezza, spedisci e segui gli ordini.
          </p>
        </div>
        {settings && (
          <div className="flex flex-wrap gap-2">
            <Chip tone={settings.enabled ? "ok" : "muted"} live={settings.enabled}>{settings.enabled ? "Shop attivo" : "Shop spento"}</Chip>
            {settings.sandbox && <Chip tone="warn" live>Modalità test (sandbox)</Chip>}
            {settings.last_balance_usd !== null && (
              <Chip tone="info">Saldo CJ {usd(settings.last_balance_usd.toFixed(2))}</Chip>
            )}
          </div>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <div className="subnav flex-1 min-w-0">
        {tabs.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className="subnav-pill"
            data-active={activeTab === t.key}
          >
            {t.label}
          </button>
        ))}
        </div>
        <span className="ml-auto">
          <ManageCategoriesButton shops={[{ key: "cj", label: "CJ Dropshipping" }]} />
        </span>
      </div>

      {activeTab === "settings" && <SettingsTab settings={settings} />}
      {activeTab === "catalog" && <CatalogTab settings={settings} onImported={() => setTab("products")} />}
      {activeTab === "products" && (
        <>
          <ProductsTab />
        </>
      )}
      {activeTab === "orders" && <OrdersTab />}
    </div>
  );
}

// --- Settings ---

function SettingsTab({ settings }: { settings: CjSettingsRead | undefined }) {
  if (!settings) return <div className={`${card} h-40 animate-pulse`} />;
  return <SettingsForm settings={settings} />;
}

function SettingsForm({ settings }: { settings: CjSettingsRead }) {
  const queryClient = useQueryClient();
  const [apiKey, setApiKey] = useState("");
  const [form, setForm] = useState<CjSettingsRead>(settings);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function save(extra: Partial<CjSettingsRead> & { api_key?: string } = {}) {
    setSaving(true);
    setError(null);
    setNotice(null);
    try {
      const body = {
        enabled: form.enabled,
        sandbox: form.sandbox,
        usd_eur_rate: Number(form.usd_eur_rate),
        markup_percentage: Number(form.markup_percentage),
        markup_fixed_cents: Number(form.markup_fixed_cents),
        price_rounding: form.price_rounding,
        shipping_mode: form.shipping_mode,
        default_credit_percentage: Number(form.default_credit_percentage),
        auto_forward: form.auto_forward,
        ...(apiKey.trim() ? { api_key: apiKey.trim() } : {}),
        ...extra,
      };
      const saved = await postJson<CjSettingsRead>("/api/proxy/cj/settings", body, "PATCH");
      setForm(saved);
      setApiKey("");
      queryClient.setQueryData(["admin", "cj", "settings"], saved);
      queryClient.invalidateQueries({ queryKey: ["admin", "cj", "products"] });
      setNotice("Impostazioni salvate. Se hai cambiato i prezzi, tutti i prodotti sono già stati ricalcolati.");
    } catch (err: any) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }


  /**
   * The visibility switch is saved immediately, not on "Salva", so the
   * administrator never believes the shop is live when customers cannot see it.
   */
  async function toggleEnabled(value: boolean) {
    setForm({ ...form, enabled: value });
    setError(null);
    setNotice(null);
    try {
      const saved = await postJson<CjSettingsRead>("/api/proxy/cj/settings", { enabled: value }, "PATCH");
      setForm(saved);
      queryClient.setQueryData(["admin", "cj", "settings"], saved);
      setNotice(value ? "Shop acceso: i clienti lo vedono appena c'è almeno un prodotto in vendita." : "Shop spento: la scheda sparisce dallo Shop del cliente.");
    } catch (err: any) {
      setForm({ ...form, enabled: !value });
      setError(err.message);
    }
  }

  async function test() {
    setTesting(true);
    setError(null);
    setNotice(null);
    try {
      const saved = await postJson<CjSettingsRead>("/api/proxy/cj/settings/test");
      setForm({ ...form, connected: saved.connected, last_balance_usd: saved.last_balance_usd, last_balance_at: saved.last_balance_at });
      queryClient.setQueryData(["admin", "cj", "settings"], saved);
      setNotice(`Connessione a CJ riuscita. Saldo disponibile: $${saved.last_balance_usd?.toFixed(2) ?? "0.00"}.`);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setTesting(false);
    }
  }

  const sample = 10; // USD
  const sampleCents = salePriceCents(sample, { ...form, shipping_mode: "CUSTOMER_PAYS" }, Number(form.markup_percentage));

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
      <div className={`${card} p-6 md:p-7 space-y-5`}>
        <h3 className="text-xl font-black tracking-tight text-white">Collegamento a CJ Dropshipping</h3>
        <div>
          <span className={label}>Chiave API</span>
          <input
            className={input}
            type="password"
            autoComplete="off"
            value={apiKey}
            placeholder={settings.api_key_configured ? `Salvata (${settings.api_key_hint}) — scrivi qui solo per cambiarla` : "CJxxxxxxx@api@xxxxxxxx"}
            onChange={(e) => setApiKey(e.target.value)}
          />
          <p className="text-[11px] text-surface-500 mt-1">
            La trovi su cjdropshipping.com → My CJ → Authorization → API. Resta salvata sul server e non viene mai mostrata.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button className={btnPrimary} disabled={saving || !apiKey.trim()} onClick={() => save()}>Salva chiave</button>
          <button className={btnGhost} disabled={testing || !settings.api_key_configured} onClick={test}>
            {testing ? "Verifica..." : "Verifica connessione e saldo"}
          </button>
        </div>
        <div className="text-xs text-surface-400 space-y-1">
          <p>Stato: {settings.connected ? <span className="text-success-400">collegato</span> : <span className="text-warn-400">non ancora verificato</span>}</p>
          {settings.last_balance_at && <p>Saldo CJ: <strong className="text-white">${settings.last_balance_usd?.toFixed(2)}</strong> (letto il {formatDate(settings.last_balance_at)})</p>}
          <p className="text-[11px]">Gli ordini inviati a CJ vengono pagati dal saldo del tuo account CJ: ricaricalo dal sito CJ quando serve.</p>
        </div>

        <div className="pt-4 border-t border-white/5 space-y-3">
          <Switch checked={form.enabled} onChange={(v) => void toggleEnabled(v)}
            title="Shop visibile ai clienti" hint="Aggiunge la scheda del Marketplace nello Shop del cliente. La scheda compare solo quando c'è almeno un prodotto in vendita: se è accesa ma il catalogo è vuoto, il cliente non vede nulla. Il nome della scheda si cambia nella card “Regole dei Marketplace” qui sopra." />
          <Switch checked={form.sandbox} onChange={(v) => setForm({ ...form, sandbox: v })}
            title="Modalità test (sandbox)" hint="Gli ordini inviati a CJ sono di prova: nessuna spedizione reale, nessun addebito. Spegnila quando sei pronto a vendere." />
          <Switch checked={form.auto_forward} onChange={(v) => setForm({ ...form, auto_forward: v })}
            title="Evasione automatica (consigliata)" hint="Appena il cliente ha pagato, l'ordine viene creato su CJ e pagato dal saldo CJ se basta. Se il saldo non basta resta “Pagamento CJ richiesto”: lo paghi dalla pagina CJ dell'ordine o ricaricando il saldo, e riparte da solo." />
          {form.enabled && form.sandbox && (
            <p className="p-3.5 rounded-2xl bg-warn-500/10 border border-warn-500/30 text-[11px] text-warn-300">
              Attenzione: shop visibile ma in modalità test. I clienti possono comprare e pagare davvero, ma CJ non
              spedisce gli ordini di prova. Usalo così solo per una prova con un tuo account, poi spegni la sandbox.
            </p>
          )}
        </div>
      </div>

      <div className={`${card} p-6 md:p-7 space-y-5`}>
        <h3 className="text-xl font-black tracking-tight text-white">Prezzi e spedizione</h3>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <span className={label}>Cambio 1 USD = EUR</span>
            <input className={input} inputMode="decimal" value={form.usd_eur_rate}
              onChange={(e) => setForm({ ...form, usd_eur_rate: e.target.value as unknown as number })} />
          </div>
          <div>
            <span className={label}>Ricarico %</span>
            <input className={input} inputMode="numeric" value={form.markup_percentage}
              onChange={(e) => setForm({ ...form, markup_percentage: e.target.value as unknown as number })} />
          </div>
          <div>
            <span className={label}>Ricarico fisso (€)</span>
            <input className={input} inputMode="decimal" value={(Number(form.markup_fixed_cents) / 100).toString()}
              onChange={(e) => setForm({ ...form, markup_fixed_cents: Math.round((parseFloat(e.target.value.replace(",", ".")) || 0) * 100) })} />
          </div>
          <div>
            <span className={label}>Arrotondamento</span>
            <select className={input} value={form.price_rounding}
              onChange={(e) => setForm({ ...form, price_rounding: e.target.value as CjSettingsRead["price_rounding"] })}>
              <option value="90">a ,90 (es. 12,90)</option>
              <option value="99">a ,99 (es. 12,99)</option>
              <option value="NONE">al centesimo</option>
            </select>
          </div>
          <div>
            <span className={label}>Spedizione</span>
            <select className={input} value={form.shipping_mode}
              onChange={(e) => setForm({ ...form, shipping_mode: e.target.value as CjSettingsRead["shipping_mode"] })}>
              <option value="CUSTOMER_PAYS">la paga il cliente (costo reale)</option>
              <option value="INCLUDED">inclusa nel prezzo</option>
            </select>
          </div>
          <div>
            <span className={label}>SosnetCash usabili sui nuovi prodotti (%)</span>
            <input className={input} inputMode="numeric" value={form.default_credit_percentage}
              onChange={(e) => setForm({ ...form, default_credit_percentage: e.target.value as unknown as number })} />
            <span className="block text-[10px] text-surface-500 mt-1">30% consigliato, massimo 99%: mai tutto in SosnetCash.</span>
          </div>
        </div>
        <div className="p-4 rounded-2xl bg-gradient-to-br from-brand-500/15 to-accent-500/10 border border-brand-400/25 text-xs text-surface-300">
          Esempio: un prodotto che su CJ costa <strong>$10</strong> sarà in vendita a <strong className="text-brand-400">{euro(sampleCents)}</strong>
          {form.shipping_mode === "CUSTOMER_PAYS" ? " + spedizione." : " (più la stima di spedizione, inclusa)."}
          {" "}È il prezzo pieno IVA inclusa, lo stesso con carta; con bonifico istantaneo il cliente ha lo sconto delle Regole dei Marketplace, che riduce il margine.
          <p className="text-[11px] text-surface-500 mt-1">L&apos;arrotondamento è sempre per eccesso: il margine non scende mai sotto il ricarico impostato.</p>
        </div>
        <ErrorBox message={error} />
        {notice && <div className="p-3.5 rounded-2xl bg-success-500/15 border border-success-400/30 text-success-300 text-xs font-semibold">{notice}</div>}
        <button className={btnPrimary} disabled={saving} onClick={() => save()}>
          {saving ? "Salvataggio..." : "Salva impostazioni"}
        </button>
      </div>
    </div>
  );
}

function Switch({ checked, onChange, title, hint }: { checked: boolean; onChange: (v: boolean) => void; title: string; hint: string }) {
  return (
    <button type="button" role="switch" aria-checked={checked} onClick={() => onChange(!checked)} className="flex items-start gap-3 text-left cursor-pointer w-full">
      <span className={`relative mt-0.5 inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors ${checked ? "bg-brand-600" : "bg-white/15"}`}>
        <span className={`inline-block rounded-full bg-white shadow transition-transform ${checked ? "translate-x-6" : "translate-x-1"}`} style={{ height: 18, width: 18 }} />
      </span>
      <span>
        <span className="block text-sm font-semibold text-white">{title}</span>
        <span className="block text-[11px] text-surface-500">{hint}</span>
      </span>
    </button>
  );
}

// --- CJ catalog ---

function CatalogTab({ settings, onImported }: { settings: CjSettingsRead | undefined; onImported: () => void }) {
  const [keyword, setKeyword] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [minPrice, setMinPrice] = useState("");
  const [maxPrice, setMaxPrice] = useState("");
  const [freeShipping, setFreeShipping] = useState(false);
  const [query, setQuery] = useState<{ keyword: string; categoryId: string; min: string; max: string; free: boolean; page: number } | null>(null);
  const [previewPid, setPreviewPid] = useState<string | null>(null);

  const { data: categories } = useQuery({
    queryKey: ["admin", "cj", "categories"],
    queryFn: () => getJson<{ id: string; name: string }[]>("/api/proxy/cj/catalog/categories"),
    enabled: !!settings?.api_key_configured,
    staleTime: 3600_000,
  });

  const { data: results, error, isFetching } = useQuery({
    queryKey: ["admin", "cj", "search", query],
    queryFn: () => {
      const q = query!;
      const params = new URLSearchParams({ page: String(q.page) });
      if (q.keyword) params.set("keyword", q.keyword);
      if (q.categoryId) params.set("category_id", q.categoryId);
      if (q.min) params.set("min_price", q.min);
      if (q.max) params.set("max_price", q.max);
      if (q.free) params.set("free_shipping", "true");
      return getJson<CjCatalogPage>(`/api/proxy/cj/catalog/search?${params}`);
    },
    enabled: !!query,
    staleTime: 300_000,
  });

  if (settings && !settings.api_key_configured) {
    return <Empty icon="🔑" text="Prima inserisci la chiave API di CJ in Impostazioni." />;
  }

  function search(page = 1) {
    setQuery({ keyword: keyword.trim(), categoryId, min: minPrice, max: maxPrice, free: freeShipping, page });
  }

  return (
    <div className="space-y-4">
      <form onSubmit={(e) => { e.preventDefault(); search(1); }} className={`${card} p-5 md:p-6 grid grid-cols-1 md:grid-cols-12 gap-3 items-end`}>
        <div className="md:col-span-4">
          <span className={label}>Cerca (in inglese)</span>
          <input className={input} value={keyword} onChange={(e) => setKeyword(e.target.value)} placeholder="es. wireless earbuds, led lamp, yoga mat" />
        </div>
        <div className="md:col-span-3">
          <span className={label}>Categoria</span>
          <select className={input} value={categoryId} onChange={(e) => setCategoryId(e.target.value)}>
            <option value="">Tutte</option>
            {(categories ?? []).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </div>
        <div className="md:col-span-1">
          <span className={label}>Da $</span>
          <input className={input} inputMode="decimal" value={minPrice} onChange={(e) => setMinPrice(e.target.value)} />
        </div>
        <div className="md:col-span-1">
          <span className={label}>A $</span>
          <input className={input} inputMode="decimal" value={maxPrice} onChange={(e) => setMaxPrice(e.target.value)} />
        </div>
        <label className="md:col-span-2 flex items-center gap-2 text-xs text-surface-300 pb-2 cursor-pointer">
          <input type="checkbox" checked={freeShipping} onChange={(e) => setFreeShipping(e.target.checked)} />
          Spedizione gratuita
        </label>
        <button type="submit" className={`${btnPrimary} md:col-span-1`} disabled={isFetching}>{isFetching ? "..." : "Cerca"}</button>
      </form>

      <ErrorBox message={error ? (error as Error).message : null} />

      {!query && (
        <Empty icon="🔎" text="Cerca nel catalogo CJ: vedi subito il prezzo a cui lo venderesti, poi apri un prodotto per importarlo." />
      )}

      {results && (
        <>
          <div className="flex flex-wrap items-baseline gap-2">
            <span className="kpi-label">Risultati</span>
            <span className="text-sm font-bold text-white tabular-nums">{results.total_records.toLocaleString("it-IT")} prodotti</span>
            <span className="text-xs text-surface-400">· pagina {results.page} di {results.total_pages}</span>
          </div>
          <div className="stagger grid grid-cols-2 md:grid-cols-4 xl:grid-cols-6 gap-4">
            {results.items.map((item, i) => (
              <button key={item.pid} type="button" onClick={() => setPreviewPid(item.pid)} data-tilt style={{ "--i": i } as CSSProperties}
                className={`${card} group overflow-hidden p-2 text-left transition cursor-pointer`}>
                <div className="relative aspect-square overflow-hidden rounded-2xl bg-white">
                  <ProductThumbnail imageUrl={item.image_url} alt={item.name_en} className="w-full h-full object-cover transition-transform duration-500 group-hover:scale-105" />
                  <div className="absolute inset-x-1.5 top-1.5 flex flex-wrap justify-between gap-1">
                    {item.already_imported && <Chip tone="ok">Già importato</Chip>}
                    {item.free_shipping && <Chip tone="info">Sped. gratis</Chip>}
                  </div>
                </div>
                <div className="px-1.5 pb-1.5 pt-2.5">
                  <p className="text-[11.5px] font-semibold text-surface-200 line-clamp-2 min-h-[2rem]">{item.name_en}</p>
                  <div className="flex items-end justify-between mt-2">
                    <span className="text-[10px] text-surface-400">CJ {usd(item.sell_price_usd)}</span>
                    {item.estimated_price_cents !== null && (
                      <span className="text-base font-black tabular-nums text-white">{euro(item.estimated_price_cents)}</span>
                    )}
                  </div>
                  {item.inventory !== null && <p className="text-[10px] text-surface-400">Disponibili {item.inventory}</p>}
                </div>
              </button>
            ))}
          </div>
          <div className="flex items-center justify-center gap-2">
            <button className={btnGhost} disabled={results.page <= 1 || isFetching} onClick={() => search(results.page - 1)}>← Precedente</button>
            <button className={btnGhost} disabled={results.page >= results.total_pages || isFetching} onClick={() => search(results.page + 1)}>Successiva →</button>
          </div>
        </>
      )}

      {previewPid && (
        <ImportModal pid={previewPid} settings={settings} onClose={() => setPreviewPid(null)} onImported={() => { setPreviewPid(null); onImported(); }} />
      )}
    </div>
  );
}

function ImportModal({ pid, settings, onClose, onImported }: {
  pid: string; settings: CjSettingsRead | undefined; onClose: () => void; onImported: () => void;
}) {
  const queryClient = useQueryClient();
  const { data: preview, error } = useQuery({
    queryKey: ["admin", "cj", "preview", pid],
    queryFn: () => getJson<CjProductPreview>(`/api/proxy/cj/catalog/products/${pid}`),
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-fade-in">
      <div className="w-full max-w-4xl max-h-[92vh] overflow-y-auto panel rounded-3xl p-7 border-white/10 bg-surface-950 pop">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-xl font-black tracking-tight text-white">Importa da CJ Dropshipping</h3>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-white/10 text-surface-400 cursor-pointer" aria-label="Chiudi">✕</button>
        </div>
        <ErrorBox message={error ? (error as Error).message : null} />
        {!preview && !error && <p className="py-12 text-center text-sm text-surface-500">Lettura del prodotto e della spedizione da CJ...</p>}
        {preview && (
          <ImportForm
            pid={pid}
            preview={preview}
            settings={settings}
            onImported={async () => {
              await queryClient.invalidateQueries({ queryKey: ["admin", "cj"] });
              onImported();
            }}
          />
        )}
      </div>
    </div>
  );
}

function ImportForm({ pid, preview, settings, onImported }: {
  pid: string; preview: CjProductPreview; settings: CjSettingsRead | undefined; onImported: () => void;
}) {
  const [name, setName] = useState(preview.name_en.slice(0, 255));
  const [description, setDescription] = useState(preview.description_text);
  const [creditPct, setCreditPct] = useState(String(settings?.default_credit_percentage ?? 30));
  const generalMarkup = settings?.markup_percentage ?? 100;
  const [markup, setMarkup] = useState(String(generalMarkup));
  const markupValue = markup.trim() === "" || Number.isNaN(Number(markup)) ? generalMarkup : Number(markup);
  const priceOf = (costUsd: number, serverPrice: number) =>
    settings ? salePriceCents(costUsd, settings, markupValue, preview.shipping_estimate_usd) : serverPrice;
  const [selected, setSelected] = useState<Set<string>>(
    () => new Set(preview.variants.filter((v) => v.inventory > 0).map((v) => v.vid))
  );
  const [categoryIds, setCategoryIds] = useState<string[]>([]);
  const [activate, setActivate] = useState(true);
  const [loading, setLoading] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  async function handleImport() {
    setLoading(true);
    setSubmitError(null);
    try {
      const created = await postJson<{ id: string }>("/api/proxy/cj/products", {
        pid,
        name: name.trim(),
        description,
        credit_discount_percentage: Number(creditPct),
        // Equal to the general markup: store nothing, so the product keeps following
        // the general setting.
        markup_percentage: markupValue === generalMarkup ? null : markupValue,
        vids: Array.from(selected),
        activate,
      });
      // Choosing categories at import time means a bulk import arrives already sorted.
      if (categoryIds.length > 0) await saveProductCategories("cj", created.id, categoryIds);
      onImported();
    } catch (err: any) {
      setSubmitError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
          <div className="grid grid-cols-1 md:grid-cols-5 gap-5">
            <div className="md:col-span-2 space-y-3">
              <div className="aspect-square rounded-xl overflow-hidden bg-white border border-white/10">
                <ProductThumbnail imageUrl={preview.images[0]} alt={preview.name_en} className="w-full h-full object-contain" />
              </div>
              <div className="flex gap-1.5 overflow-x-auto">
                {preview.images.slice(1, 8).map((src) => (
                  <div key={src} className="w-12 h-12 shrink-0 rounded-md overflow-hidden bg-white">
                    <ProductThumbnail imageUrl={src} alt="" className="w-full h-full object-cover" />
                  </div>
                ))}
              </div>
              <div className="text-xs space-y-1 text-surface-400">
                <p>SKU CJ <span className="font-mono">{preview.sku}</span> · {preview.category_name}</p>
                <p>Parte da: <strong className="text-white">{preview.origin_country}</strong></p>
                {preview.ships_to_destination ? (
                  <p>Spedizione più economica: <strong className="text-white">{preview.shipping_carrier}</strong>,
                    {" "}{usd(preview.shipping_estimate_usd)} ≈ {euro(preview.shipping_estimate_cents ?? 0)}, {preview.shipping_days} giorni</p>
                ) : (
                  <p className="text-danger-400">CJ non spedisce questo prodotto in {settings?.destination_country ?? "Italia"}: non è importabile.</p>
                )}
              </div>
            </div>
            <div className="md:col-span-3 space-y-3">
              <div>
                <span className={label}>Nome in vendita (traducilo in italiano)</span>
                <input className={input} value={name} maxLength={255} onChange={(e) => setName(e.target.value)} />
                <p className="text-[10px] text-surface-500 mt-0.5">Originale: {preview.name_en}</p>
              </div>
              <div>
                <span className={label}>Descrizione</span>
                <textarea className={`${input} min-h-[110px]`} value={description} maxLength={8000} onChange={(e) => setDescription(e.target.value)} />
              </div>
              <div>
                <span className={label}>Varianti da vendere</span>
                <div className="max-h-56 overflow-y-auto rounded-2xl border border-white/15 bg-white/[0.04] divide-y divide-white/10">
                  {preview.variants.map((v) => (
                    <label key={v.vid} className={`flex items-center gap-3 px-3 py-2 text-xs cursor-pointer ${v.inventory === 0 ? "opacity-50" : ""}`}>
                      <input type="checkbox" checked={selected.has(v.vid)}
                        onChange={(e) => {
                          const next = new Set(selected);
                          if (e.target.checked) next.add(v.vid); else next.delete(v.vid);
                          setSelected(next);
                        }} />
                      <span className="w-8 h-8 rounded overflow-hidden bg-white shrink-0">
                        <ProductThumbnail imageUrl={v.image_url} alt="" className="w-full h-full object-cover" iconClassName="w-4 h-4 text-brand-400/40" />
                      </span>
                      <span className="flex-1 min-w-0 truncate text-surface-200">{v.label}</span>
                      <span className="text-surface-500 shrink-0">{usd(v.cost_usd.toFixed(2))}</span>
                      <span className="font-bold text-brand-400 shrink-0 w-16 text-right">{euro(priceOf(v.cost_usd, v.price_cents))}</span>
                      <span className="text-surface-500 shrink-0 w-16 text-right">{v.inventory} pz</span>
                    </label>
                  ))}
                </div>
              </div>
              <div className="grid grid-cols-3 gap-3 items-end">
                <div>
                  <span className={label}>Ricarico %</span>
                  <input className={input} inputMode="numeric" value={markup} onChange={(e) => setMarkup(e.target.value)} />
                </div>
                <div>
                  <span className={label}>SosnetCash usabili (%)</span>
                  <input className={input} inputMode="numeric" value={creditPct} onChange={(e) => setCreditPct(e.target.value)} />
                </div>
                <label className="flex items-center gap-2 text-xs text-surface-300 pb-2 cursor-pointer">
                  <input type="checkbox" checked={activate} onChange={(e) => setActivate(e.target.checked)} />
                  Metti subito in vendita
                </label>
              </div>
              <ProductCategoriesField shop="cj" value={categoryIds} onChange={setCategoryIds} />
              <p className="text-[11px] text-surface-500 -mt-1">
                {markupValue === generalMarkup
                  ? `Ricarico generale (${generalMarkup}%): se lo cambi in Impostazioni, questo prodotto si aggiorna.`
                  : `Ricarico solo per questo prodotto (${markupValue}%). Lo cambi quando vuoi da Prodotti in vendita → Modifica.`}
              </p>
              <ErrorBox message={submitError} />
              <button
                className={`${btnPrimary} w-full py-2.5`}
                disabled={loading || !preview.ships_to_destination || selected.size === 0 || !name.trim()}
                onClick={handleImport}
              >
                {loading ? "Importazione..." : `Importa ${selected.size} ${selected.size === 1 ? "variante" : "varianti"}`}
              </button>
            </div>
          </div>
  );
}

// --- Products on sale ---

function ProductsTab() {
  const queryClient = useQueryClient();
  const { data: products, error } = useQuery({
    queryKey: ["admin", "cj", "products"],
    queryFn: () => getJson<CjProductAdminRead[]>("/api/proxy/cj/products"),
  });
  const [search, setSearch] = useState("");
  const [editing, setEditing] = useState<CjProductAdminRead | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const filtered = (products ?? []).filter((p) =>
    !search.trim() || p.name.toLowerCase().includes(search.toLowerCase()) || (p.cj_sku ?? "").toLowerCase().includes(search.toLowerCase())
  );
  const pagination = usePagination(filtered);

  async function act(product: CjProductAdminRead, action: "sync" | "toggle") {
    setBusyId(product.id);
    setActionError(null);
    try {
      if (action === "sync") await postJson(`/api/proxy/cj/products/${product.id}/sync`);
      else await postJson(`/api/proxy/cj/products/${product.id}`, { status: product.status === "ACTIVE" ? "INACTIVE" : "ACTIVE" }, "PATCH");
      await queryClient.invalidateQueries({ queryKey: ["admin", "cj", "products"] });
    } catch (err: any) {
      setActionError(err.message);
    } finally {
      setBusyId(null);
    }
  }

  if (error) return <ErrorBox message={(error as Error).message} />;
  if (!products) return <div className={`${card} h-40 animate-pulse`} />;
  if (products.length === 0) {
    return <Empty icon="📦" text="Nessun prodotto ancora: importali da “Catalogo CJ”." />;
  }

  const topSeller = Math.max(1, ...products.map((p) => p.paid_orders));

  return (
    <div className="space-y-4">
      <input className={input} value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Cerca per nome o SKU..." />
      <ErrorBox message={actionError} />
      <div className="overflow-x-auto">
        <table className="w-full min-w-[860px] text-sm">
          <thead>
            <tr className="text-left">
              <th className="px-4 py-3">Articolo</th>
              <th className="px-4 py-3">Situazione</th>
              <th className="px-4 py-3">Magazzino</th>
              <th className="px-4 py-3 text-right">Prezzo al pubblico</th>
              <th className="px-4 py-3 text-right">Venduti</th>
              <th className="px-4 py-3"><span className="sr-only">Comandi</span></th>
            </tr>
          </thead>
          <tbody>
            {pagination.pageItems.map((p) => {
              const prices = p.variants.filter((v) => v.active && v.available_on_cj).map((v) => v.effective_price_cents);
              const stock = p.variants.reduce((sum, v) => sum + (v.active ? v.inventory : 0), 0);
              return (
                <tr key={p.id}>
                  <td className="px-4 py-3">
                    <div className="flex min-w-0 items-center gap-3">
                      <Thumb url={p.image_url} alt={p.name} />
                      <div className="min-w-0 max-w-[320px]">
                        <Stack title={p.name} detail={<>SKU <span className="font-mono">{p.cj_sku ?? "—"}</span> · aggiornato da CJ {formatDate(p.last_synced_at)}</>} />
                        {p.sync_error && <p className="mt-0.5 text-[11px] text-warn-300">{p.sync_error}</p>}
                      </div>
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap gap-1.5">
                      <Chip tone={p.status === "ACTIVE" ? "ok" : "muted"}>{p.status === "ACTIVE" ? "In vendita" : "Nascosto"}</Chip>
                      {stock === 0 && <Chip tone="bad">Esaurito</Chip>}
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <Stack title={<span className="tabular-nums">{stock} pz</span>} detail={`${p.variants.length} varianti`} />
                  </td>
                  <td className="px-4 py-3">
                    <Figure
                      value={prices.length ? (Math.min(...prices) === Math.max(...prices) ? euro(prices[0] ?? 0) : `${euro(Math.min(...prices))} – ${euro(Math.max(...prices))}`) : "—"}
                      detail={`${p.markup_percentage !== null ? `ricarico ${p.markup_percentage}%` : "ricarico generale"} · SosnetCash ${p.credit_discount_percentage}%`}
                    />
                  </td>
                  <td className="px-4 py-3">
                    <Figure value={p.paid_orders} detail="ordini pagati" ratio={p.paid_orders / topSeller} />
                  </td>
                  <td className="px-4 py-3">
                    <RowActions>
                      <button className="act act-primary" onClick={() => setEditing(p)}>Modifica</button>
                      <button className="act" disabled={busyId === p.id} onClick={() => act(p, "sync")}>{busyId === p.id ? "..." : "Aggiorna da CJ"}</button>
                      <button className="act" disabled={busyId === p.id} onClick={() => act(p, "toggle")}>{p.status === "ACTIVE" ? "Nascondi" : "Metti in vendita"}</button>
                    </RowActions>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <Pagination {...pagination} label="prodotti" />
      {editing && <EditProductModal product={editing} onClose={() => setEditing(null)} />}
    </div>
  );
}

function EditProductModal({ product, onClose }: { product: CjProductAdminRead; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [name, setName] = useState(product.name);
  const [description, setDescription] = useState(product.description);
  const [creditPct, setCreditPct] = useState(String(product.credit_discount_percentage));
  const [markup, setMarkup] = useState(product.markup_percentage === null ? "" : String(product.markup_percentage));
  const [image, setImage] = useState(product.image_url);
  const [variants, setVariants] = useState(product.variants);
  const [categoryIds, setCategoryIds] = useState<string[]>(product.category_ids ?? []);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    setLoading(true);
    setError(null);
    try {
      await postJson(`/api/proxy/cj/products/${product.id}`, {
        name: name.trim(),
        description,
        image_url: image,
        credit_discount_percentage: Number(creditPct),
        markup_percentage: markup.trim() === "" ? null : Number(markup),
      }, "PATCH");
      for (const v of variants) {
        const original = product.variants.find((o) => o.id === v.id);
        if (!original) continue;
        if (original.active !== v.active || original.price_override_cents !== v.price_override_cents || original.label !== v.label) {
          await postJson(`/api/proxy/cj/variants/${v.id}`, {
            active: v.active, label: v.label, price_override_cents: v.price_override_cents,
          }, "PATCH");
        }
      }
      // Only when the checkboxes were touched: unrelated saves must not hit this endpoint.
      if (!sameCategorySelection(categoryIds, product.category_ids ?? [])) {
        await saveProductCategories("cj", product.id, categoryIds);
        await queryClient.invalidateQueries({ queryKey: ["shop-categories", "cj"] });
      }
      await queryClient.invalidateQueries({ queryKey: ["admin", "cj", "products"] });
      onClose();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-fade-in">
      <div className="w-full max-w-3xl max-h-[92vh] overflow-y-auto panel rounded-3xl p-7 border-white/10 bg-surface-950 pop space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-xl font-black tracking-tight text-white">Modifica prodotto</h3>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-white/10 text-surface-400 cursor-pointer" aria-label="Chiudi">✕</button>
        </div>
        <div>
          <span className={label}>Nome</span>
          <input className={input} value={name} maxLength={255} onChange={(e) => setName(e.target.value)} />
          {product.name_en && <p className="text-[10px] text-surface-500 mt-0.5">Originale CJ: {product.name_en}</p>}
        </div>
        <div>
          <span className={label}>Descrizione</span>
          <textarea className={`${input} min-h-[120px]`} value={description} maxLength={8000} onChange={(e) => setDescription(e.target.value)} />
        </div>
        {product.images.length > 1 && (
          <div>
            <span className={label}>Foto principale</span>
            <div className="flex gap-2 overflow-x-auto pb-1">
              {product.images.map((src) => (
                <button key={src} type="button" onClick={() => setImage(src)}
                  className={`w-14 h-14 shrink-0 rounded-lg overflow-hidden bg-white border-2 cursor-pointer ${image === src ? "border-brand-500" : "border-transparent"}`}>
                  <ProductThumbnail imageUrl={src} alt="" className="w-full h-full object-cover" />
                </button>
              ))}
            </div>
          </div>
        )}
        <div className="grid grid-cols-2 gap-3">
          <div>
            <span className={label}>SosnetCash usabili (%)</span>
            <input className={input} inputMode="numeric" value={creditPct} onChange={(e) => setCreditPct(e.target.value)} />
          </div>
          <div>
            <span className={label}>Ricarico % solo per questo prodotto</span>
            <input className={input} inputMode="numeric" value={markup} placeholder="vuoto = quello generale" onChange={(e) => setMarkup(e.target.value)} />
          </div>
        </div>
        <ProductCategoriesField shop="cj" value={categoryIds} onChange={setCategoryIds} />
        <div>
          <span className={label}>Varianti</span>
          <div className="rounded-2xl border border-white/15 bg-white/[0.04] divide-y divide-white/10">
            {variants.map((v, i) => (
              <div key={v.id} className={`flex flex-wrap items-center gap-3 px-3 py-2 text-xs ${!v.available_on_cj ? "opacity-50" : ""}`}>
                <input type="checkbox" checked={v.active} title="In vendita"
                  onChange={(e) => setVariants(variants.map((x, j) => (j === i ? { ...x, active: e.target.checked } : x)))} />
                <input className="flex-1 min-w-[120px] rounded-md field px-2 py-1 text-xs" value={v.label}
                  onChange={(e) => setVariants(variants.map((x, j) => (j === i ? { ...x, label: e.target.value } : x)))} />
                <span className="text-surface-500">CJ {usd(v.cost_usd.toFixed(2))}</span>
                <span className="text-surface-400">auto {euro(v.price_cents)}</span>
                <input className="w-24 rounded-md field px-2 py-1 text-xs" inputMode="decimal"
                  placeholder="prezzo fisso €"
                  value={v.price_override_cents === null ? "" : (v.price_override_cents / 100).toFixed(2)}
                  onChange={(e) => {
                    const cents = e.target.value.trim() === "" ? null : Math.round((parseFloat(e.target.value.replace(",", ".")) || 0) * 100) || null;
                    setVariants(variants.map((x, j) => (j === i ? { ...x, price_override_cents: cents } : x)));
                  }} />
                <span className="text-surface-500 w-14 text-right">{v.inventory} pz</span>
                {!v.available_on_cj && <span className="text-danger-400">non più su CJ</span>}
              </div>
            ))}
          </div>
          <p className="text-[10px] text-surface-500 mt-1">Il prezzo fisso, se c&apos;è, sostituisce quello calcolato: non segue più il costo CJ.</p>
        </div>
        <ErrorBox message={error} />
        <div className="flex justify-end gap-2">
          <button className={btnGhost} onClick={onClose}>Annulla</button>
          <button className={btnPrimary} disabled={loading || !name.trim()} onClick={save}>{loading ? "Salvataggio..." : "Salva"}</button>
        </div>
      </div>
    </div>
  );
}

// --- Orders ---
// 
// Three independent facts per order (customer paid, placed on CJ, CJ paid),
// plus the CJ balance needed to release every order customers already paid.

type Badge = { label: string; tone: ChipTone; live?: boolean };

const CUSTOMER_PAYMENT: Record<string, Badge> = {
  AWAITING_PAYMENT: { label: "Cliente: da pagare", tone: "warn", live: true },
  PAID: { label: "Cliente: pagato", tone: "ok" },
  CANCELLED: { label: "Annullato", tone: "bad" },
};

const CJ_ORDER: Record<string, Badge> = {
  NOT_SENT: { label: "CJ: non creato", tone: "muted" },
  SENDING: { label: "CJ: in corso", tone: "info", live: true },
  SENT: { label: "CJ: creato", tone: "info" },
  PROCESSING: { label: "CJ: in preparazione", tone: "info" },
  SHIPPED: { label: "Spedito", tone: "info" },
  DELIVERED: { label: "Consegnato", tone: "ok" },
  ERROR: { label: "CJ: errore", tone: "bad" },
  CJ_CANCELLED: { label: "Annullato da CJ", tone: "bad" },
};

const CJ_PAYMENT: Record<string, Badge> = {
  PENDING: { label: "Pagamento CJ: in attesa", tone: "muted" },
  PAYMENT_REQUIRED: { label: "Pagamento CJ richiesto", tone: "warn", live: true },
  PAID: { label: "CJ pagato", tone: "ok" },
  FAILED: { label: "Pagamento CJ non riuscito", tone: "bad" },
};

const ERROR_KIND: Record<string, string> = {
  TEMPORARY: "temporaneo, si riprova da solo",
  AUTHENTICATION: "chiave API / accesso",
  VALIDATION: "dati rifiutati da CJ",
  INSUFFICIENT_BALANCE: "saldo CJ insufficiente",
  FATAL: "da verificare",
};

const ORDER_FILTERS: { key: string; label: string; match: (o: CjOrderRead) => boolean }[] = [
  { key: "pay", label: "Da pagare su CJ", match: (o) => o.status === "PAID" && o.cj_payment_status !== "PAID" && o.fulfillment_status !== "CJ_CANCELLED" },
  { key: "problems", label: "Problemi", match: (o) => o.status === "PAID" && ["ERROR", "CJ_CANCELLED"].includes(o.fulfillment_status ?? "") },
  { key: "unpaid", label: "Cliente non ha pagato", match: (o) => o.status === "AWAITING_PAYMENT" },
  { key: "moving", label: "In preparazione / in viaggio", match: (o) => o.cj_payment_status === "PAID" && ["PROCESSING", "SHIPPED"].includes(o.fulfillment_status ?? "") },
  { key: "delivered", label: "Consegnati", match: (o) => o.fulfillment_status === "DELIVERED" },
  { key: "all", label: "Tutti", match: () => true },
];

function Pill({ badge }: { badge?: Badge }) {
  if (!badge) return null;
  return <Chip tone={badge.tone} live={badge.live}>{badge.label}</Chip>;
}

function CashSummary() {
  const queryClient = useQueryClient();
  const { data, isFetching } = useQuery({
    queryKey: ["admin", "cj", "orders", "summary"],
    queryFn: () => getJson<CjCashSummary>("/api/proxy/cj/orders/summary"),
    refetchInterval: 60_000,
  });
  async function refresh() {
    const fresh = await getJson<CjCashSummary>("/api/proxy/cj/orders/summary?refresh=true");
    queryClient.setQueryData(["admin", "cj", "orders", "summary"], fresh);
  }
  if (!data) return <div className={`${card} h-32 animate-pulse`} />;
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiTile
          label="Ordini CJ da pagare"
          value={<span className={data.orders_to_pay ? "text-warn-300" : undefined}>{data.orders_to_pay}</span>}
          hint={data.orders_payment_required ? `${data.orders_payment_required} con pagamento richiesto` : "pagati dai clienti, non ancora a CJ"}
        />
        <KpiTile label="Totale da pagare a CJ" value={`$${data.required_usd.toFixed(2)}`} hint={`≈ ${euro(data.required_cents)}`} />
        <KpiTile
          label="Saldo CJ"
          value={data.balance_usd === null ? "—" : `$${data.balance_usd.toFixed(2)}`}
          hint={data.balance_at ? `letto ${formatDate(data.balance_at)}` : "non ancora letto"}
        />
        <KpiTile
          label="Da ricaricare / pagare"
          value={<span className={data.shortfall_usd > 0 ? "text-danger-300" : "text-success-300"}>${data.shortfall_usd.toFixed(2)}</span>}
          hint={`≈ ${euro(data.shortfall_cents)}`}
        />
      </div>
      <div className="flex flex-wrap items-center justify-between gap-3 text-[11.5px] text-surface-300">
        <span className="max-w-3xl">
          Nessuna ricarica automatica: paghi tu ogni ordine dalla pagina CJ, oppure ricarichi il saldo e gli ordini in attesa
          {data.auto_forward ? " si pagano da soli (dal più vecchio) entro 10 minuti." : " si pagano con “Paga con saldo CJ”."}
          {data.sandbox && " Modalità test: CJ considera pagati gli ordini sandbox appena creati."}
        </span>
        <button className="act" disabled={isFetching} onClick={refresh}>Aggiorna saldo CJ</button>
      </div>
    </div>
  );
}

function OrdersTab() {
  const queryClient = useQueryClient();
  const { data: orders, error } = useQuery({
    queryKey: ["admin", "cj", "orders"],
    queryFn: () => getJson<CjOrderRead[]>("/api/proxy/cj/orders"),
    refetchInterval: 60_000,
  });
  const [filter, setFilter] = useState("pay");
  const [search, setSearch] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionNotice, setActionNotice] = useState<string | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);

  const active = ORDER_FILTERS.find((f) => f.key === filter) ?? ORDER_FILTERS[0]!;
  const needle = search.trim().toLowerCase();
  const filtered = (orders ?? []).filter(active.match).filter((o) =>
    !needle
    || o.id.slice(0, 8).toLowerCase().includes(needle)
    || o.product_name.toLowerCase().includes(needle)
    || o.customer_display_name.toLowerCase().includes(needle)
    || (o.cj_order_code ?? "").toLowerCase().includes(needle)
    || (o.tracking_number ?? "").toLowerCase().includes(needle)
  );
  const pagination = usePagination(filtered);

  async function act(order: CjOrderRead, action: "forward" | "sync") {
    setBusyId(order.id);
    setActionError(null);
    setActionNotice(null);
    try {
      const updated = await postJson<CjOrderRead>(`/api/proxy/cj/orders/${order.id}/${action}`);
      if (updated.cj_payment_status === "PAID") setActionNotice(`Ordine #${order.id.slice(0, 8).toUpperCase()}: CJ pagato, in preparazione.`);
      else if (updated.cj_payment_status === "PAYMENT_REQUIRED") setActionNotice("CJ non risulta ancora pagato: pagalo dalla pagina CJ o ricarica il saldo, poi premi “Verifica pagamento CJ”.");
      else if (updated.forward_error) setActionError(updated.forward_error);
      await queryClient.invalidateQueries({ queryKey: ["admin", "cj", "orders"] });
      await queryClient.invalidateQueries({ queryKey: ["admin", "orders"] });
    } catch (err: any) {
      setActionError(err.message);
    } finally {
      setBusyId(null);
    }
  }

  if (error) return <ErrorBox message={(error as Error).message} />;
  if (!orders) return <div className={`${card} h-40 animate-pulse`} />;

  return (
    <div className="space-y-4">
      <CashSummary />
      <div className="subnav">
        {ORDER_FILTERS.map((f) => {
          const count = orders.filter(f.match).length;
          return (
            <button key={f.key} onClick={() => setFilter(f.key)} className="subnav-pill" data-active={filter === f.key}>
              {f.label} <span className="rounded-full bg-black/15 px-1.5 text-[10.5px] tabular-nums">{count}</span>
            </button>
          );
        })}
      </div>
      <input className={input} value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Cerca per ordine, cliente, prodotto, codice CJ o tracking..." />
      <ErrorBox message={actionError} />
      {actionNotice && <div className="p-3.5 rounded-2xl bg-info-500/15 border border-info-400/30 text-info-300 text-xs font-semibold">{actionNotice}</div>}

      {filtered.length === 0 ? (
        <Empty icon="🛰️" text="Nessun ordine qui." />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[1040px] text-sm">
            <thead>
              <tr className="text-left">
                <th className="px-4 py-3">Articolo</th>
                <th className="px-4 py-3">Destinatario</th>
                <th className="px-4 py-3">Avanzamento</th>
                <th className="px-4 py-3 text-right">Incasso</th>
                <th className="px-4 py-3 text-right">Margine stimato</th>
                <th className="px-4 py-3">Quando</th>
                <th className="px-4 py-3"><span className="sr-only">Comandi</span></th>
              </tr>
            </thead>
            <tbody>
              {pagination.pageItems.flatMap((o) => {
                const customerPaid = o.status === "PAID";
                const cjPaid = o.cj_payment_status === "PAID";
                const needsPayment = customerPaid && !cjPaid && o.fulfillment_status !== "CJ_CANCELLED";
                const canCreate = customerPaid && ["NOT_SENT", "ERROR"].includes(o.fulfillment_status ?? "") && !o.cj_order_id;
                const canPay = needsPayment && !!o.cj_order_id && o.fulfillment_status !== "SENDING";
                const open = openId === o.id;
                const charged = o.amount_cents - o.bank_transfer_discount_cents;
                const rows = [
                  <tr key={o.id}>
                    <td className="px-4 py-3">
                      <div className="flex min-w-0 items-center gap-3">
                        <Thumb url={o.product_image_url} alt="" />
                        <div className="min-w-0 max-w-[260px]">
                          <Stack title={o.product_name} detail={`${o.variant_label} × ${o.quantity}`} />
                          <div className="mt-1 flex flex-wrap items-center gap-1.5">
                            <IdTag id={o.id} />
                            {o.sandbox && <Chip tone="muted">sandbox</Chip>}
                          </div>
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <Identity name={o.customer_display_name} detail={`${o.city} (${o.province})`} />
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex max-w-[280px] flex-wrap gap-1.5">
                        <Pill badge={CUSTOMER_PAYMENT[o.status]} />
                        {customerPaid && <Pill badge={CJ_ORDER[o.fulfillment_status ?? ""]} />}
                        {customerPaid && <Pill badge={CJ_PAYMENT[o.cj_payment_status ?? ""]} />}
                      </div>
                      {o.forward_error && o.cj_payment_status !== "PAYMENT_REQUIRED" && (
                        <p className="mt-1 max-w-[280px] text-[11px] text-danger-300">
                          {o.forward_error}{o.last_error_kind ? ` (${ERROR_KIND[o.last_error_kind] ?? o.last_error_kind})` : ""}
                        </p>
                      )}
                      {o.next_retry_at && !cjPaid && (
                        <p className="mt-0.5 text-[10.5px] text-surface-400">Prossimo controllo automatico {formatDate(o.next_retry_at)} · tentativi {o.attempt_count}</p>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <Figure
                        value={euro(charged)}
                        detail={(o.vat_amount_cents ?? 0) > 0 ? `${vatLineLabel(o.vat_percentage ?? 0)} ${euro(o.vat_amount_cents!)}` : "pagato dal cliente"}
                      />
                    </td>
                    <td className="px-4 py-3">
                      {o.estimated_margin_cents !== undefined ? (
                        <Figure
                          value={<span className={o.estimated_margin_cents >= 0 ? "text-success-300" : "text-danger-300"}>{euro(o.estimated_margin_cents)}</span>}
                          detail={o.cj_cost_usd !== undefined ? `CJ $${o.cj_cost_usd.toFixed(2)}${o.cj_cost_is_actual ? "" : " (stima)"} · netto IVA e sconto` : "netto IVA e sconto"}
                          ratio={charged > 0 && o.estimated_margin_cents > 0 ? o.estimated_margin_cents / charged : null}
                        />
                      ) : (
                        <Figure value="—" detail={o.cj_cost_usd !== undefined ? `CJ $${o.cj_cost_usd.toFixed(2)}${o.cj_cost_is_actual ? "" : " (stima)"}` : undefined} />
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <Stack title={shortDate(o.paid_at ?? o.created_at)} detail={relative(o.paid_at ?? o.created_at)} />
                      {o.cj_order_code && <p className="text-[10.5px] text-surface-400">CJ <span className="font-mono">{o.cj_order_code}</span></p>}
                      {o.tracking_number && <p className="text-[10.5px] text-surface-400">tracking <span className="font-mono">{o.tracking_number}</span></p>}
                    </td>
                    <td className="px-4 py-3">
                      <RowActions>
                        <div className="flex flex-wrap justify-end gap-1.5">
                          {canCreate && (
                            <button className="act act-primary" disabled={busyId === o.id} onClick={() => act(o, "forward")}>
                              {busyId === o.id ? "Invio..." : o.fulfillment_status === "ERROR" ? "Riprova su CJ" : "Crea su CJ"}
                            </button>
                          )}
                          {canPay && o.cj_pay_url && (
                            <a className="act act-primary" href={o.cj_pay_url} target="_blank" rel="noopener noreferrer">Apri pagamento CJ</a>
                          )}
                          {canPay && (
                            <button className={o.cj_pay_url ? "act" : "act act-primary"} disabled={busyId === o.id} onClick={() => act(o, "forward")}>
                              {busyId === o.id ? "..." : "Paga con saldo CJ"}
                            </button>
                          )}
                          {o.cj_order_id && o.fulfillment_status !== "DELIVERED" && (
                            <button className="act" disabled={busyId === o.id} onClick={() => act(o, "sync")}>
                              {needsPayment ? "Verifica pagamento CJ" : "Aggiorna stato"}
                            </button>
                          )}
                          {o.tracking_url && <a className="act" href={o.tracking_url} target="_blank" rel="noopener noreferrer">Traccia</a>}
                          <button className="act" onClick={() => setOpenId(open ? null : o.id)}>{open ? "Chiudi" : "Dettagli"}</button>
                        </div>
                      </RowActions>
                    </td>
                  </tr>,
                ];
                if (open) {
                  rows.push(
                    <tr key={`${o.id}-details`}>
                      <td colSpan={7} className="px-5 py-4">
                        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs text-surface-300">
                          <div className="space-y-0.5">
                            <p className="kpi-label mb-1">Consegna</p>
                            <p>{o.recipient_name} · {o.recipient_phone}</p>
                            <p>{o.address_line1}{o.address_line2 ? `, ${o.address_line2}` : ""}</p>
                            <p>{o.postal_code} {o.city} ({o.province}) {o.country_code}</p>
                            <p>{o.logistic_name} · parte da {o.origin_country} · {o.shipping_days ?? "?"} giorni</p>
                          </div>
                          <div className="space-y-0.5">
                            <p className="kpi-label mb-1">Cliente</p>
                            <p>{o.quantity} × {euro(o.unit_price_cents)} + spedizione {euro(o.shipping_cents)} = {euro(o.amount_cents)}</p>
                            <p>
                              SosnetCash {euro(o.credit_applied_cents)} · in euro {euro(o.amount_due_cents)} ({o.payment_method === "CARD" ? "carta" : "bonifico"})
                              {o.bank_transfer_discount_cents > 0 && <> · sconto bonifico -{euro(o.bank_transfer_discount_cents)}</>}
                            </p>
                            <p>Pagato {formatDate(o.paid_at)}</p>
                            <p className="kpi-label mb-1 pt-2">Costo CJ</p>
                            {o.cj_cost_is_actual ? (
                              <p>Prodotti {usd(o.cj_product_amount_usd?.toFixed(2))} · spedizione {usd(o.cj_postage_amount_usd?.toFixed(2))}
                                {o.cj_ioss_amount_usd ? ` · IVA IOSS ${usd(o.cj_ioss_amount_usd.toFixed(2))}` : ""} · totale {usd(o.cj_amount_usd?.toFixed(2))}</p>
                            ) : (
                              <p>Stima: prodotti {usd(((o.unit_cost_usd ?? 0) * o.quantity).toFixed(2))} + spedizione {usd((o.shipping_cost_usd ?? 0).toFixed(2))} + IVA IOSS stimata = {usd(o.cj_cost_usd?.toFixed(2))}</p>
                            )}
                            <p>≈ {euro(o.cj_cost_cents ?? 0)} al cambio {o.usd_eur_rate}</p>
                          </div>
                          <div className="space-y-0.5">
                            <p className="kpi-label mb-1">CJ</p>
                            <p>Codice <span className="font-mono">{o.cj_order_code ?? "—"}</span> · id <span className="font-mono">{o.cj_order_id ?? "—"}</span></p>
                            <p>Stato CJ {o.cj_order_status ?? "—"} · pagamento {o.cj_payment_status}</p>
                            <p>Creato {formatDate(o.forwarded_at)} · pagato {formatDate(o.cj_paid_at)}</p>
                            <p>Tentativi {o.attempt_count ?? 0} · ultimo {formatDate(o.last_attempt_at)}</p>
                            {o.last_error_kind && <p>Ultimo errore: {ERROR_KIND[o.last_error_kind] ?? o.last_error_kind}</p>}
                            <p>Ultimo controllo {formatDate(o.last_cj_sync_at)}</p>
                            {o.shipped_at && <p>Spedito {formatDate(o.shipped_at)}</p>}
                            {o.delivered_at && <p>Consegnato {formatDate(o.delivered_at)}</p>}
                          </div>
                        </div>
                      </td>
                    </tr>
                  );
                }
                return rows;
              })}
            </tbody>
          </table>
        </div>
      )}
      <Pagination {...pagination} label="ordini" />
    </div>
  );
}
