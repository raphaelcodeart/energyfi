"use client";

import { useState } from "react";
import type { CSSProperties } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { friendlyApiError } from "@/lib/api-error";
import { vatLineLabel } from "@/lib/product-audience";
import { AdminImportedProductsPanel } from "@/components/admin-imported-products-panel";
import { Pagination, usePagination } from "@/components/pagination";
import { ProductThumbnail } from "@/components/product-thumbnail";
import { Chip, Figure, IdTag, Identity, KpiTile, RowActions, Stack } from "@/components/ui/data-cells";
import type { ChipTone } from "@/components/ui/data-cells";
import { ProductCategoriesField, saveProductCategories, sameCategorySelection, ManageCategoriesButton } from "@/components/shop-categories-card";
import type {
  AliexpressCatalogPage,
  AliexpressCatalogProduct,
  AliexpressOrderRead,
  AliexpressProductAdminRead,
  AliexpressSettingsRead,
} from "@/lib/types";

type Tab = "orders" | "products" | "catalog" | "manual" | "settings";

function euro(cents: number): string {
  return (cents / 100).toLocaleString("it-IT", { style: "currency", currency: "EUR" });
}

function money(amount: number | null | undefined, currency: string | null | undefined): string {
  if (amount === null || amount === undefined) return "—";
  return `${amount.toFixed(2)} ${currency ?? ""}`.trim();
}

/**
 * Mirrors the server formula (aliexpress_dropshipping/pricing.py) for a live
 * preview; the server's figure is authoritative.
 */
function salePriceCents(
  cost: number | null, price: number,
  rules: Pick<AliexpressSettingsRead, "currency_rate" | "price_basis" | "markup_fixed_cents" | "price_rounding" | "shipping_mode" | "shipping_minimum_cents">,
  markupPct: number,
): number {
  const base = rules.price_basis === "COST" && cost !== null && cost > 0 ? cost : price;
  let cents = base * Number(rules.currency_rate) * 100 * (1 + markupPct / 100) + Number(rules.markup_fixed_cents);
  if (rules.shipping_mode === "INCLUDED") cents += Number(rules.shipping_minimum_cents);
  const rounded = Math.ceil(Math.round(cents * 1e6) / 1e6);
  if (rules.price_rounding === "NONE") return rounded;
  const target = Number(rules.price_rounding);
  const euros = Math.floor(rounded / 100);
  return rounded % 100 <= target ? euros * 100 + target : (euros + 1) * 100 + target;
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

/**
 * AliExpress has no admin page per order, only the public item page. The
 * server sends the real link when known; this builds the fallback.
 */
function aliexpressItemUrl(url: string | null | undefined, productId: string | null | undefined): string | null {
  return url || (productId ? `https://www.aliexpress.com/item/${productId}.html` : null);
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

/** Small product photo on a white tile, for table rows. */
function Thumb({ url, alt }: { url: string | null | undefined; alt: string }) {
  return (
    <span className="block h-12 w-12 shrink-0 overflow-hidden rounded-xl bg-white shadow-lg shadow-black/30 ring-1 ring-white/20">
      <ProductThumbnail imageUrl={url} alt={alt} className="h-full w-full object-cover" iconClassName="w-5 h-5 text-brand-400/50" />
    </span>
  );
}

function Empty({ icon, text }: { icon: string; text: string }) {
  return (
    <div className={`${card} flex flex-col items-center justify-center gap-3 px-6 py-12 text-center`}>
      <span className="float-soft text-4xl" aria-hidden="true">{icon}</span>
      <p className="max-w-md text-sm font-semibold text-surface-300">{text}</p>
    </div>
  );
}

function ErrorBox({ message }: { message: string | null }) {
  if (!message) return null;
  return <div className="p-3.5 rounded-2xl bg-danger-500/15 border border-danger-400/30 text-danger-300 text-xs font-semibold">{message}</div>;
}

/**
 * Marketplace 3: AliExpress Dropshipping API.
 * Products are searched in the AliExpress catalog, re-priced in euro with our
 * markup, sold through the common Shop checkout, then paid orders are placed
 * at AliExpress and tracked until delivery. The hand-made imported-products
 * list remains as its own tab so existing sales keep working. Bank transfer
 * confirmation lives in the unified "Ordini".
 */
const APP_URL = (process.env.NEXT_PUBLIC_APP_URL || (typeof window !== "undefined" ? window.location.origin : "")).replace(/\/$/, "");

export function AdminAliexpressPanel() {
  const { data: settings } = useQuery({
    queryKey: ["admin", "aliexpress", "settings"],
    queryFn: () => getJson<AliexpressSettingsRead>("/api/proxy/aliexpress/settings"),
  });
  const [tab, setTab] = useState<Tab | null>(null);
  const configured = !!settings?.connected;
  const activeTab: Tab = tab ?? (settings && !configured ? "settings" : "orders");

  const tabs: { key: Tab; label: string }[] = [
    { key: "orders", label: "Ordini" },
    { key: "products", label: "Prodotti in vendita" },
    { key: "catalog", label: "Catalogo AliExpress" },
    { key: "manual", label: "Prodotti inseriti a mano" },
    { key: "settings", label: "Impostazioni" },
  ];

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="rise">
          <div className="kpi-label">Marketplace · API AliExpress</div>
          <h2 className="mt-1 text-3xl font-black tracking-tight text-white">
            Prodotti <span className="text-gradient">AliExpress Dropshipping</span>
          </h2>
          <p className="text-sm text-surface-300 mt-1 max-w-2xl">
            Prodotti presi dal catalogo AliExpress e venduti nello Shop: cerca, importa, prezza, invia gli ordini ad AliExpress e seguili fino alla consegna.
          </p>
        </div>
        {settings && (
          <div className="flex flex-wrap gap-2">
            <Chip tone={settings.enabled ? "ok" : "muted"} live={settings.enabled}>{settings.enabled ? "Shop attivo" : "Shop spento"}</Chip>
            {settings.connected && <Chip tone="info">{settings.account_label ?? "Account collegato"}</Chip>}
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
          <ManageCategoriesButton shops={[{ key: "aliexpress", label: "AliExpress" }]} />
        </span>
      </div>

      {activeTab === "settings" && (settings ? <SettingsForm settings={settings} /> : <div className={`${card} h-40 animate-pulse`} />)}
      {activeTab === "catalog" && <CatalogTab settings={settings} configured={configured} onImported={() => setTab("products")} />}
      {activeTab === "products" && (
        <>
          <ProductsTab settings={settings} />
        </>
      )}
      {activeTab === "orders" && <OrdersTab settings={settings} />}
      {activeTab === "manual" && <ManualTab />}
    </div>
  );
}

// --- Settings ---

function SettingsForm({ settings }: { settings: AliexpressSettingsRead }) {
  const queryClient = useQueryClient();
  const [appSecret, setAppSecret] = useState("");
  const [form, setForm] = useState<AliexpressSettingsRead>(settings);
  const [saving, setSaving] = useState(false);
  const [busy, setBusy] = useState<"connect" | "test" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function save() {
    setSaving(true);
    setError(null);
    setNotice(null);
    try {
      const body = {
        app_key: form.app_key ?? "",
        enabled: form.enabled,
        currency_rate: Number(form.currency_rate),
        price_basis: form.price_basis,
        markup_percentage: Number(form.markup_percentage),
        markup_fixed_cents: Number(form.markup_fixed_cents),
        price_rounding: form.price_rounding,
        shipping_mode: form.shipping_mode,
        shipping_minimum_cents: Number(form.shipping_minimum_cents),
        shipping_days: form.shipping_days || null,
        ship_to_country: form.ship_to_country,
        target_currency: form.target_currency,
        target_language: form.target_language,
        default_credit_percentage: Number(form.default_credit_percentage),
        auto_forward: form.auto_forward,
        ...(appSecret.trim() ? { app_secret: appSecret.trim() } : {}),
      };
      const saved = await postJson<AliexpressSettingsRead>("/api/proxy/aliexpress/settings", body, "PATCH");
      setForm(saved);
      setAppSecret("");
      queryClient.setQueryData(["admin", "aliexpress", "settings"], saved);
      queryClient.invalidateQueries({ queryKey: ["admin", "aliexpress", "products"] });
      setNotice("Impostazioni salvate. Se hai cambiato i prezzi, tutti i prodotti sono già stati ricalcolati.");
    } catch (err: any) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  /**
   * Seller account consent page: AliExpress returns the code to the callback
   * URL, where only the server (holding the App Secret) exchanges it.
   */
  async function connect() {
    setBusy("connect");
    setError(null);
    setNotice(null);
    try {
      const data = await getJson<{ url: string; callback_url: string }>("/api/proxy/aliexpress/oauth/authorize-url");
      window.open(data.url, "_blank", "noopener,noreferrer");
      setNotice("Autorizza l'account nella scheda che si è aperta, poi torna qui e premi “Verifica connessione”.");
    } catch (err: any) {
      setError(err.message);
    } finally {
      setBusy(null);
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
      const saved = await postJson<AliexpressSettingsRead>("/api/proxy/aliexpress/settings", { enabled: value }, "PATCH");
      setForm(saved);
      queryClient.setQueryData(["admin", "aliexpress", "settings"], saved);
      setNotice(value ? "Shop acceso: i clienti lo vedono appena c'è almeno un prodotto in vendita." : "Shop spento: la scheda sparisce dallo Shop del cliente.");
    } catch (err: any) {
      setForm({ ...form, enabled: !value });
      setError(err.message);
    }
  }

  async function test() {
    setBusy("test");
    setError(null);
    setNotice(null);
    try {
      const saved = await postJson<AliexpressSettingsRead & { sample_categories?: string[] }>("/api/proxy/aliexpress/settings/test");
      setForm({ ...form, connected: saved.connected, account_label: saved.account_label, token_expires_at: saved.token_expires_at, last_connected_at: saved.last_connected_at });
      queryClient.setQueryData(["admin", "aliexpress", "settings"], saved);
      const categories = saved.sample_categories ?? [];
      setNotice(
        categories.length > 0
          ? `Connessione riuscita. Categorie lette da AliExpress: ${categories.join(", ")}.`
          : `Connessione riuscita: AliExpress ha risposto${saved.account_label ? ` per l'account "${saved.account_label}"` : ""}.`
      );
    } catch (err: any) {
      setError(err.message);
    } finally {
      setBusy(null);
    }
  }

  const sampleCents = salePriceCents(10, 10, form, Number(form.markup_percentage));
  const setNum = (key: keyof AliexpressSettingsRead) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm({ ...form, [key]: e.target.value as unknown as number });

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
      <div className={`${card} p-6 md:p-7 space-y-5`}>
        <h3 className="text-xl font-black tracking-tight text-white">Collegamento all&apos;API Dropshipping di AliExpress</h3>
        <details className="rounded-xl border border-brand-500/20 bg-brand-500/5 p-3 text-xs text-surface-300" open={!settings.connected}>
          <summary className="font-semibold cursor-pointer text-brand-400">Come collegare AliExpress (una volta sola)</summary>
          <ol className="list-decimal pl-5 mt-2 space-y-1">
            <li>Crea l&apos;app sul portale <span className="font-mono">openservice.aliexpress.com</span>, categoria <strong>Drop Shipping</strong>.</li>
            <li>Registra come <strong>Callback URL</strong>: <span className="font-mono break-all">{APP_URL}/api/aliexpress/oauth/callback</span> (esattamente così, senza barra finale).</li>
            <li>Nella pagina della console dell&apos;app copia <strong>App Key</strong> e <strong>App Secret</strong> qui sotto e premi <strong>Salva collegamento</strong>.</li>
            <li>Fai attivare all&apos;app il permesso <strong>DS (dropshipping)</strong>: finché non è concesso, il catalogo non risponde.</li>
            <li>Premi <strong>Collega AliExpress</strong>: si apre la pagina di consenso, autorizzi l&apos;account venditore e AliExpress ti riporta qui.</li>
            <li>Chiudi con <strong>Verifica connessione</strong>. Il token ha una scadenza: il server lo rinnova da solo finché l&apos;autorizzazione resta valida.</li>
          </ol>
        </details>
        <div>
          <span className={label}>App Key</span>
          <input className={input} autoComplete="off" value={form.app_key ?? ""} placeholder="es. 547960"
            onChange={(e) => setForm({ ...form, app_key: e.target.value })} />
        </div>
        <div>
          <span className={label}>App Secret</span>
          <input className={input} type="password" autoComplete="off" value={appSecret}
            placeholder={settings.app_secret_configured ? `Salvato (${settings.app_secret_hint}) — scrivi qui solo per cambiarlo` : "••••••••"}
            onChange={(e) => setAppSecret(e.target.value)} />
          <p className="text-[11px] text-surface-500 mt-1">Resta salvato sul server e non viene mai mostrato.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button className={btnPrimary} disabled={saving} onClick={save}>Salva collegamento</button>
          <button className={btnGhost} disabled={busy !== null || !settings.app_secret_configured} onClick={connect}>
            {busy === "connect" ? "..." : settings.connected ? "Ricollega AliExpress" : "Collega AliExpress"}
          </button>
          <button className={btnGhost} disabled={busy !== null || !settings.connected} onClick={test}>
            {busy === "test" ? "Verifica..." : "Verifica connessione"}
          </button>
        </div>
        <p className="text-xs text-surface-400">
          Stato: {settings.connected
            ? (
              <span className="text-success-400">
                account collegato{settings.account_label ? ` (${settings.account_label})` : ""}
                {settings.last_connected_at ? ` · ultima verifica ${formatDate(settings.last_connected_at)}` : ""}
                {settings.token_expires_at ? ` · token valido fino al ${formatDate(settings.token_expires_at)}` : ""}
              </span>
            )
            : <span className="text-warn-400">non ancora autorizzato</span>}
        </p>

        <div className="pt-4 border-t border-white/5 space-y-3">
          <Switch checked={form.enabled} onChange={(v) => void toggleEnabled(v)}
            title="Shop visibile ai clienti" hint="Aggiunge la scheda del Marketplace nello Shop del cliente. La scheda compare solo quando c'è almeno un prodotto in vendita: se è accesa ma il catalogo è vuoto, il cliente non vede nulla. Il nome della scheda si cambia nella card “Regole dei Marketplace” qui sopra." />
          <Switch checked={form.auto_forward} onChange={(v) => setForm({ ...form, auto_forward: v })}
            title="Invio automatico ad AliExpress (consigliato)" hint="Appena il cliente ha pagato, l'ordine viene creato su AliExpress con l'indirizzo di consegna. Se qualcosa va storto si riprova da solo; se AliExpress lo rifiuta ricevi un avviso." />
        </div>
      </div>

      <div className={`${card} p-6 md:p-7 space-y-5`}>
        <h3 className="text-xl font-black tracking-tight text-white">Prezzi e spedizione</h3>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <span className={label}>Il prezzo parte da</span>
            <select className={input} value={form.price_basis}
              onChange={(e) => setForm({ ...form, price_basis: e.target.value as AliexpressSettingsRead["price_basis"] })}>
              <option value="COST">prezzo riservato al dropshipping</option>
              <option value="PRICE">prezzo di listino AliExpress</option>
            </select>
          </div>
          <div>
            <span className={label}>Cambio 1 {form.target_currency || "USD"} = EUR</span>
            <input className={input} inputMode="decimal" value={form.currency_rate} onChange={setNum("currency_rate")} />
          </div>
          <div>
            <span className={label}>Ricarico %</span>
            <input className={input} inputMode="numeric" value={form.markup_percentage} onChange={setNum("markup_percentage")} />
          </div>
          <div>
            <span className={label}>Ricarico fisso (€)</span>
            <input className={input} inputMode="decimal" value={(Number(form.markup_fixed_cents) / 100).toString()}
              onChange={(e) => setForm({ ...form, markup_fixed_cents: Math.round((parseFloat(e.target.value.replace(",", ".")) || 0) * 100) })} />
          </div>
          <div>
            <span className={label}>Arrotondamento</span>
            <select className={input} value={form.price_rounding}
              onChange={(e) => setForm({ ...form, price_rounding: e.target.value as AliexpressSettingsRead["price_rounding"] })}>
              <option value="90">a ,90 (es. 12,90)</option>
              <option value="99">a ,99 (es. 12,99)</option>
              <option value="NONE">al centesimo</option>
            </select>
          </div>
          <div>
            <span className={label}>Spedizione</span>
            <select className={input} value={form.shipping_mode}
              onChange={(e) => setForm({ ...form, shipping_mode: e.target.value as AliexpressSettingsRead["shipping_mode"] })}>
              <option value="CUSTOMER_PAYS">la paga il cliente (costo reale, con un minimo)</option>
              <option value="INCLUDED">inclusa nel prezzo</option>
            </select>
          </div>
          <div>
            <span className={label}>Spesa di spedizione minima (€)</span>
            <input className={input} inputMode="decimal" value={(Number(form.shipping_minimum_cents) / 100).toString()}
              onChange={(e) => setForm({ ...form, shipping_minimum_cents: Math.round((parseFloat(e.target.value.replace(",", ".")) || 0) * 100) })} />
            <span className="block text-[10px] text-surface-500 mt-1">
              {form.shipping_mode === "INCLUDED"
                ? "Con la spedizione inclusa questo importo entra nel prezzo di listino e al checkout non si addebita nulla."
                : Number(form.shipping_minimum_cents) === 0
                  ? "Nessun minimo: il cliente paga esattamente la spedizione che AliExpress chiede per quei prodotti, calcolata al checkout. Metti un importo qui sopra se vuoi che non scenda mai sotto una certa soglia."
                  : "Il cliente paga almeno questo importo. Se la spedizione reale di AliExpress costa di più, si addebita quella. Il minimo vale una volta per ordine, non per articolo; a zero non c'è minimo e si paga solo il costo reale."}
            </span>
          </div>
          <div>
            <span className={label}>Tempi di consegna (giorni)</span>
            <input className={input} value={form.shipping_days ?? ""} placeholder="es. 10-20" onChange={(e) => setForm({ ...form, shipping_days: e.target.value })} />
          </div>
          <div>
            <span className={label}>Paese di consegna</span>
            <input className={input} maxLength={2} value={form.ship_to_country}
              onChange={(e) => setForm({ ...form, ship_to_country: e.target.value.toUpperCase() })} />
            <span className="block text-[10px] text-surface-500 mt-1">Sigla a due lettere: IT.</span>
          </div>
          <div>
            <span className={label}>Valuta e lingua delle risposte</span>
            <div className="flex gap-2">
              <input className={input} maxLength={3} value={form.target_currency}
                onChange={(e) => setForm({ ...form, target_currency: e.target.value.toUpperCase() })} />
              <input className={input} maxLength={8} value={form.target_language}
                onChange={(e) => setForm({ ...form, target_language: e.target.value })} />
            </div>
            <span className="block text-[10px] text-surface-500 mt-1">Es. USD e IT: AliExpress traduce i titoli.</span>
          </div>
          <div className="col-span-2">
            <span className={label}>SosnetCash usabili sui nuovi prodotti (%)</span>
            <input className={input} inputMode="numeric" value={form.default_credit_percentage} onChange={setNum("default_credit_percentage")} />
            <span className="block text-[10px] text-surface-500 mt-1">
              30% consigliato, massimo {settings.max_credit_percentage}%: un prodotto dei Marketplace non si compra mai tutto in SosnetCash.
            </span>
          </div>
        </div>
        <div className="p-4 rounded-2xl bg-gradient-to-br from-brand-500/15 to-accent-500/10 border border-brand-400/25 text-xs text-surface-300">
          Esempio: un articolo che costa <strong>10 {form.target_currency || "USD"}</strong> sarà in vendita a{" "}
          <strong className="text-brand-400">{euro(sampleCents)}</strong>
          {form.shipping_mode === "CUSTOMER_PAYS" ? (Number(form.shipping_minimum_cents) === 0
              ? " + la spedizione reale di AliExpress, calcolata al checkout."
              : ` + spedizione reale AliExpress, minimo ${euro(Number(form.shipping_minimum_cents))}.`) : " (spedizione inclusa)."}{" "}
          È il prezzo pieno IVA inclusa, lo stesso con carta; con bonifico istantaneo il cliente ha lo sconto delle Regole dei Marketplace, che riduce il margine.
          <p className="text-[11px] text-surface-500 mt-1">
            Se un articolo non ha il prezzo riservato al dropshipping si parte dal suo listino. L&apos;arrotondamento è sempre per eccesso.
          </p>
        </div>
        <ErrorBox message={error} />
        {notice && <div className="p-3.5 rounded-2xl bg-success-500/15 border border-success-400/30 text-success-300 text-xs font-semibold">{notice}</div>}
        <button className={btnPrimary} disabled={saving} onClick={save}>{saving ? "Salvataggio..." : "Salva impostazioni"}</button>
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

// --- AliExpress catalog ---

function CatalogTab({ settings, configured, onImported }: {
  settings: AliexpressSettingsRead | undefined; configured: boolean; onImported: () => void;
}) {
  const [keyword, setKeyword] = useState("");
  const [query, setQuery] = useState<{ keyword: string; cursor: string | null; page: number } | null>(null);
  const [cursors, setCursors] = useState<(string | null)[]>([null]);
  // Search hits carry no SKU; variants and real prices only come with the
  // detail call, so the import window opens on an id and waits for it.
  const [previewOf, setPreviewOf] = useState<AliexpressCatalogProduct | null>(null);

  const { data: results, error, isFetching } = useQuery({
    queryKey: ["admin", "aliexpress", "search", query],
    queryFn: () => {
      const q = query!;
      const params = new URLSearchParams();
      if (q.keyword) params.set("keyword", q.keyword);
      if (q.cursor) params.set("cursor", q.cursor);
      return getJson<AliexpressCatalogPage>(`/api/proxy/aliexpress/catalog/search?${params}`);
    },
    enabled: !!query,
    staleTime: 120_000,
  });

  const { data: preview, error: previewError } = useQuery({
    queryKey: ["admin", "aliexpress", "catalog-product", previewOf?.product_id],
    queryFn: () => getJson<AliexpressCatalogProduct>(
      `/api/proxy/aliexpress/catalog/product?product_id=${encodeURIComponent(previewOf!.product_id)}`
    ),
    enabled: !!previewOf,
    staleTime: 120_000,
    retry: false,
  });

  if (!configured) {
    return <Empty icon="🔌" text="Prima collega l'account AliExpress in Impostazioni." />;
  }

  function goTo(page: number, list = cursors) {
    setQuery({ keyword: keyword.trim(), cursor: list[page] ?? null, page });
  }

  return (
    <div className="space-y-4">
      <form onSubmit={(e) => { e.preventDefault(); if (!keyword.trim()) return; setCursors([null]); goTo(0, [null]); }} className={`${card} p-5 md:p-6 flex flex-col md:flex-row gap-3 md:items-end`}>
        <div className="flex-1">
          <span className={label}>Cerca su AliExpress (parola chiave, in inglese funziona meglio)</span>
          <input className={input} value={keyword} onChange={(e) => setKeyword(e.target.value)} placeholder="es. cuffie, lampada, yoga" />
        </div>
        <button type="submit" className={btnPrimary} disabled={isFetching || !keyword.trim()}>{isFetching ? "..." : "Cerca"}</button>
      </form>

      <ErrorBox message={error ? (error as Error).message : null} />

      {!query && (
        <Empty icon="🔎" text="Scrivi che cosa cercare tra gli articoli disponibili per il dropshipping: vedi subito il prezzo a cui li venderesti, poi aprine uno per importarlo." />
      )}

      {results && (
        <>
          {results.items.length === 0 && <Empty icon="🫥" text="Nessun prodotto trovato." />}
          <div className="stagger grid grid-cols-2 md:grid-cols-4 xl:grid-cols-6 gap-4">
            {results.items.map((item, i) => (
              <button key={item.product_id} type="button" onClick={() => setPreviewOf(item)} data-tilt style={{ "--i": i } as CSSProperties}
                className={`${card} group overflow-hidden p-2 text-left transition cursor-pointer`}>
                <div className="relative aspect-square overflow-hidden rounded-2xl bg-white">
                  <ProductThumbnail imageUrl={item.image_url} alt={item.title} className="w-full h-full object-cover transition-transform duration-500 group-hover:scale-105" />
                  {item.already_imported && (
                    <span className="absolute left-1.5 top-1.5"><Chip tone="ok">Già importato</Chip></span>
                  )}
                </div>
                <div className="px-1.5 pb-1.5 pt-2.5">
                  <p className="text-[11.5px] font-semibold text-surface-200 line-clamp-2 min-h-[2rem]">{item.title}</p>
                  <div className="flex items-end justify-between mt-2">
                    <span className="text-[10px] text-surface-400">{item.evaluate_rate ?? item.vendor ?? ""}</span>
                    {item.min_price_cents !== null && <span className="text-base font-black tabular-nums text-white">{euro(item.min_price_cents)}</span>}
                  </div>
                </div>
              </button>
            ))}
          </div>
          <div className="flex items-center justify-center gap-2">
            <button className={btnGhost} disabled={!query || query.page === 0 || isFetching} onClick={() => goTo((query?.page ?? 1) - 1)}>← Precedente</button>
            <button className={btnGhost} disabled={!results.next_cursor || isFetching}
              onClick={() => {
                const page = (query?.page ?? 0) + 1;
                const next = [...cursors.slice(0, page), results.next_cursor];
                setCursors(next);
                goTo(page, next);
              }}>Successiva →</button>
          </div>
        </>
      )}

      {previewOf && (
        preview ? (
          <ImportModal
            product={preview}
            alreadyImported={!!previewOf.already_imported}
            settings={settings}
            onClose={() => setPreviewOf(null)}
            onImported={() => { setPreviewOf(null); onImported(); }}
          />
        ) : (
          <LoadingModal
            title={previewOf.title}
            error={previewError ? (previewError as Error).message : null}
            onClose={() => setPreviewOf(null)}
          />
        )
      )}
    </div>
  );
}

/** While AliExpress is asked for the item's SKUs (slow, and possibly none sellable). */
function LoadingModal({ title, error, onClose }: { title: string; error: string | null; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-fade-in">
      <div className="w-full max-w-md panel rounded-3xl p-7 border-white/10 bg-surface-950 pop space-y-4">
        <div className="flex items-start justify-between gap-3">
          <p className="text-base font-black tracking-tight text-white line-clamp-2">{title}</p>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-white/10 text-surface-400 cursor-pointer shrink-0" aria-label="Chiudi">✕</button>
        </div>
        {error ? <ErrorBox message={error} /> : <p className="text-sm text-surface-400">Lettura delle varianti da AliExpress...</p>}
      </div>
    </div>
  );
}

function ImportModal({ product, alreadyImported, settings, onClose, onImported }: {
  product: AliexpressCatalogProduct; alreadyImported: boolean;
  settings: AliexpressSettingsRead | undefined; onClose: () => void; onImported: () => void;
}) {
  const queryClient = useQueryClient();
  const [name, setName] = useState(product.title.slice(0, 255));
  const [description, setDescription] = useState(product.description_text);
  const [creditPct, setCreditPct] = useState(String(settings?.default_credit_percentage ?? 30));
  const generalMarkup = settings?.markup_percentage ?? 100;
  const [markup, setMarkup] = useState(String(generalMarkup));
  const markupValue = markup.trim() === "" || Number.isNaN(Number(markup)) ? generalMarkup : Number(markup);
  const [selected, setSelected] = useState<Set<string>>(
    () => new Set(product.variants.filter((v) => v.inventory === null || v.inventory > 0).map((v) => v.variant_id))
  );
  const [categoryIds, setCategoryIds] = useState<string[]>([]);
  const [activate, setActivate] = useState(true);
  const [loading, setLoading] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const priceOf = (v: AliexpressCatalogProduct["variants"][number]) =>
    settings ? salePriceCents(v.cost_amount, v.source_price_amount, settings, markupValue) : v.price_cents;

  async function handleImport() {
    setLoading(true);
    setSubmitError(null);
    try {
      const created = await postJson<{ id: string }>("/api/proxy/aliexpress/products", {
        product_id: product.product_id,
        name: name.trim(),
        description,
        credit_discount_percentage: Number(creditPct),
        markup_percentage: markupValue === generalMarkup ? null : markupValue,
        variant_ids: Array.from(selected),
        activate,
      });
      await queryClient.invalidateQueries({ queryKey: ["admin", "aliexpress"] });
      // Choosing categories at import time means a bulk import arrives already sorted.
      if (categoryIds.length > 0) await saveProductCategories("aliexpress", created.id, categoryIds);
      onImported();
    } catch (err: any) {
      setSubmitError(err.message);
    } finally {
      setLoading(false);
    }
  }

  const itemUrl = aliexpressItemUrl(product.product_url, product.product_id);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-fade-in">
      <div className="w-full max-w-4xl max-h-[92vh] overflow-y-auto panel rounded-3xl p-7 border-white/10 bg-surface-950 pop">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-xl font-black tracking-tight text-white">Importa da AliExpress</h3>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-white/10 text-surface-400 cursor-pointer" aria-label="Chiudi">✕</button>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-5 gap-5">
          <div className="md:col-span-2 space-y-3">
            <div className="aspect-square rounded-xl overflow-hidden bg-white border border-white/10">
              <ProductThumbnail imageUrl={product.images[0] ?? product.image_url} alt={product.title} className="w-full h-full object-contain" />
            </div>
            <div className="flex gap-1.5 overflow-x-auto">
              {product.images.slice(1, 8).map((src) => (
                <div key={src} className="w-12 h-12 shrink-0 rounded-md overflow-hidden bg-white">
                  <ProductThumbnail imageUrl={src} alt="" className="w-full h-full object-cover" />
                </div>
              ))}
            </div>
            <p className="text-xs text-surface-400">
              {product.vendor ? `Venditore ${product.vendor} · ` : ""}
              {alreadyImported && <span className="text-success-400">già importato</span>}
            </p>
            {itemUrl && (
              <a className={btnGhost} href={itemUrl} target="_blank" rel="noopener noreferrer">Apri su AliExpress</a>
            )}
          </div>
          <div className="md:col-span-3 space-y-3">
            <div>
              <span className={label}>Nome in vendita (in italiano)</span>
              <input className={input} value={name} maxLength={255} onChange={(e) => setName(e.target.value)} />
              <p className="text-[10px] text-surface-500 mt-0.5">Originale: {product.title}</p>
            </div>
            <div>
              <span className={label}>Descrizione</span>
              <textarea className={`${input} min-h-[110px]`} value={description} maxLength={8000} onChange={(e) => setDescription(e.target.value)} />
            </div>
            <div>
              <span className={label}>Varianti da vendere</span>
              <div className="max-h-56 overflow-y-auto rounded-2xl border border-white/15 bg-white/[0.04] divide-y divide-white/10">
                {product.variants.map((v) => (
                  <label key={v.variant_id} className={`flex items-center gap-3 px-3 py-2 text-xs cursor-pointer ${v.inventory === 0 ? "opacity-50" : ""}`}>
                    <input type="checkbox" checked={selected.has(v.variant_id)}
                      onChange={(e) => {
                        const next = new Set(selected);
                        if (e.target.checked) next.add(v.variant_id); else next.delete(v.variant_id);
                        setSelected(next);
                      }} />
                    <span className="flex-1 min-w-0 truncate text-surface-200">{v.label}{v.sku ? ` · ${v.sku}` : ""}</span>
                    <span className="text-surface-500 shrink-0" title="prezzo dropshipping / listino">
                      {v.cost_amount !== null ? `ds ${money(v.cost_amount, product.currency)}` : `listino ${money(v.source_price_amount, product.currency)}`}
                    </span>
                    <span className="font-bold text-brand-400 shrink-0 w-16 text-right">{euro(priceOf(v))}</span>
                    <span className="text-surface-500 shrink-0 w-14 text-right">{v.inventory === null ? "∞" : `${v.inventory} pz`}</span>
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
            <ProductCategoriesField shop="aliexpress" value={categoryIds} onChange={setCategoryIds} />
            <p className="text-[11px] text-surface-500 -mt-1">
              {markupValue === generalMarkup
                ? `Ricarico generale (${generalMarkup}%): se lo cambi in Impostazioni, questo prodotto si aggiorna.`
                : `Ricarico solo per questo prodotto (${markupValue}%).`}
              {" "}SosnetCash: massimo {settings?.max_credit_percentage ?? 99}%.
            </p>
            <ErrorBox message={submitError} />
            <button className={`${btnPrimary} w-full py-2.5`} disabled={loading || selected.size === 0 || !name.trim() || alreadyImported}
              onClick={handleImport}>
              {loading ? "Importazione..." : alreadyImported ? "Già importato" : `Importa ${selected.size} ${selected.size === 1 ? "variante" : "varianti"}`}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// --- Products on sale ---

function ProductsTab({ settings }: { settings: AliexpressSettingsRead | undefined }) {
  const queryClient = useQueryClient();
  const { data: products, error } = useQuery({
    queryKey: ["admin", "aliexpress", "products"],
    queryFn: () => getJson<AliexpressProductAdminRead[]>("/api/proxy/aliexpress/products"),
  });
  const [search, setSearch] = useState("");
  const [editing, setEditing] = useState<AliexpressProductAdminRead | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const needle = search.trim().toLowerCase();
  const filtered = (products ?? []).filter((p) =>
    !needle || p.name.toLowerCase().includes(needle) || p.variants.some((v) => (v.sku ?? "").toLowerCase().includes(needle))
  );
  const pagination = usePagination(filtered);

  async function act(product: AliexpressProductAdminRead, action: "sync" | "toggle") {
    setBusyId(product.id);
    setActionError(null);
    try {
      if (action === "sync") await postJson(`/api/proxy/aliexpress/products/${product.id}/sync`);
      else await postJson(`/api/proxy/aliexpress/products/${product.id}`, { status: product.status === "ACTIVE" ? "INACTIVE" : "ACTIVE" }, "PATCH");
      await queryClient.invalidateQueries({ queryKey: ["admin", "aliexpress", "products"] });
    } catch (err: any) {
      setActionError(err.message);
    } finally {
      setBusyId(null);
    }
  }

  if (error) return <ErrorBox message={(error as Error).message} />;
  if (!products) return <div className={`${card} h-40 animate-pulse`} />;
  if (products.length === 0) {
    return <Empty icon="📦" text="Nessun prodotto ancora: importali da “Catalogo AliExpress”." />;
  }

  const topSeller = Math.max(1, ...products.map((p) => p.paid_orders));

  return (
    <div className="space-y-4">
      <input className={input} value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Cerca per nome o SKU..." />
      <ErrorBox message={actionError} />
      <div className="overflow-x-auto">
        <table className="w-full min-w-[880px] text-sm">
          <thead>
            <tr className="text-left">
              <th className="px-4 py-3">Articolo</th>
              <th className="px-4 py-3">Situazione</th>
              <th className="px-4 py-3">Assortimento</th>
              <th className="px-4 py-3 text-right">Prezzo al pubblico</th>
              <th className="px-4 py-3 text-right">Venduti</th>
              <th className="px-4 py-3"><span className="sr-only">Comandi</span></th>
            </tr>
          </thead>
          <tbody>
            {pagination.pageItems.map((p) => {
              const live = p.variants.filter((v) => v.active && v.available_in_store);
              const prices = live.map((v) => v.effective_price_cents);
              const soldOut = live.length > 0 && live.every((v) => v.inventory !== null && v.inventory <= 0);
              const itemUrl = aliexpressItemUrl(p.product_url, p.aliexpress_product_id);
              return (
                <tr key={p.id}>
                  <td className="px-4 py-3">
                    <div className="flex min-w-0 items-center gap-3">
                      <Thumb url={p.image_url} alt={p.name} />
                      <div className="min-w-0 max-w-[320px]">
                        <Stack title={p.name} detail={`${p.vendor ? `${p.vendor} · ` : ""}aggiornato da AliExpress ${formatDate(p.last_synced_at)}`} />
                        {p.sync_error && <p className="mt-0.5 text-[11px] text-warn-300">{p.sync_error}</p>}
                      </div>
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap gap-1.5">
                      <Chip tone={p.status === "ACTIVE" ? "ok" : "muted"}>{p.status === "ACTIVE" ? "In vendita" : "Nascosto"}</Chip>
                      {soldOut && <Chip tone="bad">Esaurito</Chip>}
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <Stack title={`${p.variants.length} varianti`} detail={`${live.length} attive e disponibili`} />
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
                      <div className="flex flex-wrap justify-end gap-1.5">
                        <button className="act act-primary" onClick={() => setEditing(p)}>Modifica</button>
                        <button className="act" disabled={busyId === p.id} onClick={() => act(p, "sync")}>{busyId === p.id ? "..." : "Aggiorna da AliExpress"}</button>
                        <button className="act" disabled={busyId === p.id} onClick={() => act(p, "toggle")}>{p.status === "ACTIVE" ? "Nascondi" : "Metti in vendita"}</button>
                        {itemUrl && <a className="act" href={itemUrl} target="_blank" rel="noopener noreferrer">Apri su AliExpress</a>}
                      </div>
                    </RowActions>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <Pagination {...pagination} label="prodotti" />
      {editing && <EditProductModal product={editing} maxCredit={settings?.max_credit_percentage ?? 99} onClose={() => setEditing(null)} />}
    </div>
  );
}

function EditProductModal({ product, maxCredit, onClose }: { product: AliexpressProductAdminRead; maxCredit: number; onClose: () => void }) {
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
      await postJson(`/api/proxy/aliexpress/products/${product.id}`, {
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
          await postJson(`/api/proxy/aliexpress/variants/${v.id}`, {
            active: v.active, label: v.label, price_override_cents: v.price_override_cents,
          }, "PATCH");
        }
      }
      // Only when the checkboxes were touched: unrelated saves must not hit this endpoint.
      if (!sameCategorySelection(categoryIds, product.category_ids ?? [])) {
        await saveProductCategories("aliexpress", product.id, categoryIds);
        await queryClient.invalidateQueries({ queryKey: ["shop-categories", "aliexpress"] });
      }
      await queryClient.invalidateQueries({ queryKey: ["admin", "aliexpress", "products"] });
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
          {product.source_title && <p className="text-[10px] text-surface-500 mt-0.5">Su AliExpress: {product.source_title}</p>}
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
            <span className={label}>SosnetCash usabili (%, max {maxCredit})</span>
            <input className={input} inputMode="numeric" value={creditPct} onChange={(e) => setCreditPct(e.target.value)} />
          </div>
          <div>
            <span className={label}>Ricarico % solo per questo prodotto</span>
            <input className={input} inputMode="numeric" value={markup} placeholder="vuoto = quello generale" onChange={(e) => setMarkup(e.target.value)} />
          </div>
        </div>
        <ProductCategoriesField shop="aliexpress" value={categoryIds} onChange={setCategoryIds} />
        <div>
          <span className={label}>Varianti</span>
          <div className="rounded-2xl border border-white/15 bg-white/[0.04] divide-y divide-white/10">
            {variants.map((v, i) => (
              <div key={v.id} className={`flex flex-wrap items-center gap-3 px-3 py-2 text-xs ${!v.available_in_store ? "opacity-50" : ""}`}>
                <input type="checkbox" checked={v.active} title="In vendita"
                  onChange={(e) => setVariants(variants.map((x, j) => (j === i ? { ...x, active: e.target.checked } : x)))} />
                <input className="flex-1 min-w-[120px] rounded-md field px-2 py-1 text-xs" value={v.label}
                  onChange={(e) => setVariants(variants.map((x, j) => (j === i ? { ...x, label: e.target.value } : x)))} />
                <span className="text-surface-500">{v.cost_amount !== null ? `ds ${v.cost_amount.toFixed(2)}` : `listino ${v.source_price_amount.toFixed(2)}`}</span>
                <span className="text-surface-400">auto {euro(v.price_cents)}</span>
                <input className="w-24 rounded-md field px-2 py-1 text-xs" inputMode="decimal" placeholder="prezzo fisso €"
                  value={v.price_override_cents === null ? "" : (v.price_override_cents / 100).toFixed(2)}
                  onChange={(e) => {
                    const cents = e.target.value.trim() === "" ? null : Math.round((parseFloat(e.target.value.replace(",", ".")) || 0) * 100) || null;
                    setVariants(variants.map((x, j) => (j === i ? { ...x, price_override_cents: cents } : x)));
                  }} />
                <span className="text-surface-500 w-14 text-right">{v.inventory === null ? "∞" : `${v.inventory} pz`}</span>
                {!v.available_in_store && <span className="text-danger-400">non più su AliExpress</span>}
              </div>
            ))}
          </div>
          <p className="text-[10px] text-surface-500 mt-1">Il prezzo fisso, se c&apos;è, sostituisce quello calcolato: non segue più il costo del fornitore.</p>
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

type Badge = { label: string; tone: ChipTone; live?: boolean };

const CUSTOMER_PAYMENT: Record<string, Badge> = {
  AWAITING_PAYMENT: { label: "Cliente: da pagare", tone: "warn", live: true },
  PAID: { label: "Cliente: pagato", tone: "ok" },
  CANCELLED: { label: "Annullato", tone: "bad" },
};

const SUPPLIER_ORDER: Record<string, Badge> = {
  NOT_SENT: { label: "AliExpress: non creato", tone: "muted" },
  SENDING: { label: "AliExpress: invio in corso", tone: "info", live: true },
  SENT: { label: "AliExpress: creato, in preparazione", tone: "info" },
  SHIPPED: { label: "Spedito", tone: "info" },
  DELIVERED: { label: "Consegnato", tone: "ok" },
  ERROR: { label: "AliExpress: errore", tone: "bad" },
  CANCELLED: { label: "Annullato su AliExpress", tone: "bad" },
};

const ERROR_KIND: Record<string, string> = {
  TEMPORARY: "temporaneo, si riprova da solo",
  AUTHENTICATION: "token / permessi dell'app",
  VALIDATION: "dati rifiutati da AliExpress",
  FATAL: "da verificare",
};

const ORDER_FILTERS: { key: string; label: string; match: (o: AliexpressOrderRead) => boolean }[] = [
  { key: "send", label: "Da inviare ad AliExpress", match: (o) => o.status === "PAID" && ["NOT_SENT", "SENDING", "ERROR"].includes(o.fulfillment_status ?? "") },
  { key: "problems", label: "Problemi", match: (o) => o.status === "PAID" && ["ERROR", "CANCELLED"].includes(o.fulfillment_status ?? "") },
  { key: "unpaid", label: "Cliente non ha pagato", match: (o) => o.status === "AWAITING_PAYMENT" },
  { key: "moving", label: "In preparazione / in viaggio", match: (o) => ["SENT", "SHIPPED"].includes(o.fulfillment_status ?? "") },
  { key: "delivered", label: "Consegnati", match: (o) => o.fulfillment_status === "DELIVERED" },
  { key: "all", label: "Tutti", match: () => true },
];

function Pill({ badge }: { badge?: Badge }) {
  if (!badge) return null;
  return <Chip tone={badge.tone} live={badge.live}>{badge.label}</Chip>;
}

function OrdersTab({ settings }: { settings: AliexpressSettingsRead | undefined }) {
  const queryClient = useQueryClient();
  const { data: orders, error } = useQuery({
    queryKey: ["admin", "aliexpress", "orders"],
    queryFn: () => getJson<AliexpressOrderRead[]>("/api/proxy/aliexpress/orders"),
    refetchInterval: 60_000,
  });
  const [filter, setFilter] = useState("send");
  const [search, setSearch] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);

  const active = ORDER_FILTERS.find((f) => f.key === filter) ?? ORDER_FILTERS[0]!;
  const needle = search.trim().toLowerCase();
  const filtered = (orders ?? []).filter(active.match).filter((o) =>
    !needle
    || o.id.slice(0, 8).toLowerCase().includes(needle)
    || o.product_name.toLowerCase().includes(needle)
    || o.customer_display_name.toLowerCase().includes(needle)
    || (o.aliexpress_order_id ?? "").toLowerCase().includes(needle)
    || (o.out_order_id ?? "").toLowerCase().includes(needle)
    || (o.tracking_number ?? "").toLowerCase().includes(needle)
  );
  const pagination = usePagination(filtered);

  async function act(order: AliexpressOrderRead, action: "forward" | "sync") {
    setBusyId(order.id);
    setActionError(null);
    try {
      const updated = await postJson<AliexpressOrderRead>(`/api/proxy/aliexpress/orders/${order.id}/${action}`);
      if (updated.forward_error && updated.fulfillment_status === "ERROR") setActionError(updated.forward_error);
      await queryClient.invalidateQueries({ queryKey: ["admin", "aliexpress", "orders"] });
      await queryClient.invalidateQueries({ queryKey: ["admin", "orders"] });
    } catch (err: any) {
      setActionError(err.message);
    } finally {
      setBusyId(null);
    }
  }

  if (error) return <ErrorBox message={(error as Error).message} />;
  if (!orders) return <div className={`${card} h-40 animate-pulse`} />;

  const toSend = orders.filter(ORDER_FILTERS[0]!.match).length;
  const moving = orders.filter((o) => ["SENT", "SHIPPED"].includes(o.fulfillment_status ?? "")).length;
  const delivered = orders.filter((o) => o.fulfillment_status === "DELIVERED").length;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiTile label="Da inviare ad AliExpress" value={<span className={toSend ? "text-warn-300" : undefined}>{toSend}</span>} hint="pagati, non ancora su AliExpress" onClick={() => setFilter("send")} active={filter === "send"} />
        <KpiTile label="In viaggio" value={moving} hint="creati su AliExpress o spediti" onClick={() => setFilter("moving")} active={filter === "moving"} />
        <KpiTile label="Consegnati" value={delivered} onClick={() => setFilter("delivered")} active={filter === "delivered"} />
        <KpiTile label="Invio automatico" value={settings?.auto_forward ? "Attivo" : "Spento"} hint={settings?.auto_forward ? "gli ordini pagati partono da soli" : "usa “Crea su AliExpress”"} />
      </div>
      <p className="text-[11.5px] text-surface-300">
        I bonifici si confermano da <strong>Ordini</strong>, come per tutti gli acquisti. Qui: invio ad AliExpress e spedizione.
        {settings?.auto_forward ? " Invio automatico attivo: gli ordini pagati partono da soli." : " Invio automatico spento: usa “Crea su AliExpress”."}
      </p>
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
      <input className={input} value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Cerca per ordine, cliente, prodotto, numero AliExpress o tracking..." />
      <ErrorBox message={actionError} />

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
                const canCreate = customerPaid && ["NOT_SENT", "ERROR"].includes(o.fulfillment_status ?? "") && !o.aliexpress_order_id;
                const itemUrl = aliexpressItemUrl(null, o.aliexpress_product_id);
                const open = openId === o.id;
                const charged = o.amount_cents - o.bank_transfer_discount_cents;
                const rows = [
                  <tr key={o.id}>
                    <td className="px-4 py-3">
                      <div className="flex min-w-0 items-center gap-3">
                        <Thumb url={o.product_image_url} alt="" />
                        <div className="min-w-0 max-w-[260px]">
                          <Stack title={o.product_name} detail={`${o.variant_label} × ${o.quantity}`} />
                          <div className="mt-1"><IdTag id={o.id} /></div>
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <Identity name={o.customer_display_name} detail={`${o.city} (${o.province})`} />
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex max-w-[280px] flex-wrap gap-1.5">
                        <Pill badge={CUSTOMER_PAYMENT[o.status]} />
                        {customerPaid && <Pill badge={SUPPLIER_ORDER[o.fulfillment_status ?? ""]} />}
                      </div>
                      {o.forward_error && o.fulfillment_status === "ERROR" && (
                        <p className="mt-1 max-w-[280px] text-[11px] text-danger-300">
                          {o.forward_error}{o.last_error_kind ? ` (${ERROR_KIND[o.last_error_kind] ?? o.last_error_kind})` : ""}
                        </p>
                      )}
                      {o.next_retry_at && o.fulfillment_status === "ERROR" && (
                        <p className="mt-0.5 text-[10.5px] text-surface-400">Nuovo tentativo automatico {formatDate(o.next_retry_at)} · tentativi {o.attempt_count}</p>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <Figure
                        value={euro(charged)}
                        detail={(o.vat_amount_cents ?? 0) > 0 ? `${vatLineLabel(o.vat_percentage ?? 0)} ${euro(o.vat_amount_cents!)}` : "pagato dal cliente"}
                      />
                    </td>
                    <td className="px-4 py-3">
                      {o.estimated_margin_cents != null ? (
                        <Figure
                          value={<span className={o.estimated_margin_cents >= 0 ? "text-success-300" : "text-danger-300"}>{euro(o.estimated_margin_cents)}</span>}
                          detail={o.supplier_cost_cents != null ? `costo ≈ ${euro(o.supplier_cost_cents)} · netto IVA, sconto e spedizione` : "netto IVA, sconto e spedizione"}
                          ratio={charged > 0 && o.estimated_margin_cents > 0 ? o.estimated_margin_cents / charged : null}
                        />
                      ) : (
                        <Figure value="—" detail={o.supplier_cost_cents != null ? `costo ≈ ${euro(o.supplier_cost_cents)}` : undefined} />
                      )}
                      {/* Shipping has its own margin (charged max(actual, minimum)); its cost is
                         subtracted from the overall margin rather than counted as profit. */}
                      {o.supplier_shipping_cents != null && (
                        <p className="mt-1 text-right text-[10.5px] text-surface-400">
                          sped. {euro(o.shipping_cents)} su {euro(o.supplier_shipping_cents)} reali
                          {o.shipping_margin_cents != null && (
                            <span className={o.shipping_margin_cents >= 0 ? "text-success-300" : "text-danger-300"}>
                              {" "}({o.shipping_margin_cents >= 0 ? "+" : ""}{euro(o.shipping_margin_cents)})
                            </span>
                          )}
                        </p>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <Stack title={shortDate(o.paid_at ?? o.created_at)} detail={relative(o.paid_at ?? o.created_at)} />
                      {o.aliexpress_order_id && <p className="text-[10.5px] text-surface-400">AliExpress <span className="font-mono">{o.aliexpress_order_id}</span></p>}
                      {o.tracking_number && <p className="text-[10.5px] text-surface-400">tracking <span className="font-mono">{o.tracking_number}</span></p>}
                    </td>
                    <td className="px-4 py-3">
                      <RowActions>
                        <div className="flex flex-wrap justify-end gap-1.5">
                          {canCreate && (
                            <button className="act act-primary" disabled={busyId === o.id} onClick={() => act(o, "forward")}>
                              {busyId === o.id ? "Invio..." : o.fulfillment_status === "ERROR" ? "Riprova su AliExpress" : "Crea su AliExpress"}
                            </button>
                          )}
                          {o.aliexpress_order_id && o.fulfillment_status !== "DELIVERED" && (
                            <button className="act" disabled={busyId === o.id} onClick={() => act(o, "sync")}>Aggiorna stato</button>
                          )}
                          {itemUrl && <a className="act" href={itemUrl} target="_blank" rel="noopener noreferrer">Apri su AliExpress</a>}
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
                            <p>{o.shipping_days ?? "?"} giorni stimati</p>
                          </div>
                          <div className="space-y-0.5">
                            <p className="kpi-label mb-1">Cliente</p>
                            <p>{o.quantity} × {euro(o.unit_price_cents)} + spedizione {euro(o.shipping_cents)} = {euro(o.amount_cents)}</p>
                            <p>
                              SosnetCash {euro(o.credit_applied_cents)} · in euro {euro(o.amount_due_cents)} ({o.payment_method === "CARD" ? "carta" : "bonifico"})
                              {o.bank_transfer_discount_cents > 0 && <> · sconto bonifico -{euro(o.bank_transfer_discount_cents)}</>}
                            </p>
                            <p>Pagato {formatDate(o.paid_at)}</p>
                          </div>
                          <div className="space-y-0.5">
                            <p className="kpi-label mb-1">AliExpress</p>
                            <p>Ordine <span className="font-mono">{o.aliexpress_order_id ?? "—"}</span> · stato {o.aliexpress_order_status ?? "—"}</p>
                            <p>Nostro riferimento <span className="font-mono">{o.out_order_id ?? "—"}</span></p>
                            <p>Creato {formatDate(o.forwarded_at)} · tentativi {o.attempt_count ?? 0}</p>
                            {o.tracking_company && <p>Corriere {o.tracking_company}</p>}
                            <p>Ultimo controllo {formatDate(o.last_sync_at)}</p>
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

// --- Hand-entered products ---

/**
 * The legacy hand-entered "Acquisti SOSNET" list, kept so existing orders,
 * SosnetCash and history keep working. New products go through "Catalogo AliExpress".
 */
function ManualTab() {
  return (
    <div className="space-y-4">
      <div className={`${card} p-5 md:p-6 text-sm text-surface-300`}>
        <div className="kpi-label mb-2">Lista storica</div>
        Questa è la vecchia lista compilata a mano, prima del collegamento all&apos;API. Resta qui perché i prodotti già
        venduti così non devono sparire: si possono ancora nascondere o riattivare, e i loro ordini restano in
        &ldquo;Ordini&rdquo;. Per i prodotti nuovi usa <strong>Catalogo AliExpress</strong>: prezzi, disponibilità e
        spedizione si aggiornano da soli.
      </div>
      <AdminImportedProductsPanel />
    </div>
  );
}
