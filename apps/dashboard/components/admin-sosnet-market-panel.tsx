"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { friendlyApiError } from "@/lib/api-error";
import { ProductThumbnail } from "@/components/product-thumbnail";
import { Chip, Figure, Identity, KpiTile, RowActions, Stack } from "@/components/ui/data-cells";
import type {
  SosnetMarketAdminProductRead,
  SosnetMarketOrderRead,
  SosnetMarketProducerRead,
  SosnetMarketSettingsRead,
} from "@/lib/types";

/**
 * Marketplace 4 ("Fai la Spesa con Sosnet"): where the administrator builds the shop.
 * Sections in order of use: settings (on/off, shipping), producer companies,
 * products. Companies come first so a product can pick one from a list.
 * No supplier integration here (no OAuth, sync or markup): the price entered
 * is the selling price.
 */

const input =
  "w-full rounded-lg field px-3 py-2 text-sm focus:border-brand-500";
const label = "block text-[10px] font-semibold text-surface-400 uppercase tracking-wide mb-1";

function euro(cents: number): string {
  return (cents / 100).toLocaleString("it-IT", { style: "currency", currency: "EUR" });
}

function centsFrom(value: string): number {
  return Math.round((parseFloat(value.replace(",", ".")) || 0) * 100);
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`/api/proxy${path}`);
  if (!res.ok) throw new Error(await friendlyApiError(res));
  return res.json();
}

async function send<T>(path: string, method: string, body: unknown): Promise<T> {
  const res = await fetch(`/api/proxy${path}`, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await friendlyApiError(res));
  return res.json();
}

function Card({ title, subtitle, eyebrow, children }: { title: string; subtitle?: string; eyebrow?: string; children: React.ReactNode }) {
  return (
    <div className="panel rise rounded-3xl p-6 sm:p-7 space-y-5">
      <div>
        {eyebrow && <div className="kpi-label mb-1.5">{eyebrow}</div>}
        <h3 className="text-xl font-black tracking-tight text-white">{title}</h3>
        {subtitle && <p className="text-xs text-surface-300 mt-1">{subtitle}</p>}
      </div>
      {children}
    </div>
  );
}

function when(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("it-IT", { day: "2-digit", month: "short", year: "numeric" });
}

function EmptyBlock({ text }: { text: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-2xl border border-dashed border-white/15 px-6 py-10 text-center">
      <span className="orb float-soft" aria-hidden="true">
        <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.6} d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />
        </svg>
      </span>
      <p className="text-sm text-surface-300">{text}</p>
    </div>
  );
}

function Esito({ message }: { message: { ok: boolean; text: string } | null }) {
  if (!message) return null;
  return (
    <p className={`text-xs ${message.ok ? "text-success-400" : "text-danger-400"}`}>{message.text}</p>
  );
}

// --- Settings ---

function Impostazioni() {
  const queryClient = useQueryClient();
  const { data } = useQuery({
    queryKey: ["admin", "sosnet-market", "settings"],
    queryFn: () => get<SosnetMarketSettingsRead>("/sosnet-market/settings"),
  });
  const [form, setForm] = useState<SosnetMarketSettingsRead | null>(null);
  const corrente = form ?? data ?? null;
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  const salva = useMutation({
    mutationFn: (payload: Partial<SosnetMarketSettingsRead>) =>
      send<SosnetMarketSettingsRead>("/sosnet-market/settings", "PATCH", payload),
    onSuccess: (row) => {
      setForm(row);
      setMessage({ ok: true, text: "Impostazioni salvate." });
      queryClient.invalidateQueries({ queryKey: ["admin", "sosnet-market"] });
    },
    onError: (err: unknown) => setMessage({ ok: false, text: (err as Error).message }),
  });

  if (!corrente) return <Card title="Impostazioni">Caricamento…</Card>;

  return (
    <Card
      eyebrow="Negozio"
      title="Impostazioni del negozio"
      subtitle="Finché è spento, il cliente non vede la scheda nello Shop: sparisce da sola."
    >
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        <div>
          <span className={label}>Stato</span>
          <select
            className={input}
            value={corrente.enabled ? "on" : "off"}
            onChange={(e) => setForm({ ...corrente, enabled: e.target.value === "on" })}
          >
            <option value="off">Spento</option>
            <option value="on">Acceso</option>
          </select>
        </div>
        <div>
          <span className={label}>Spedizione</span>
          <select
            className={input}
            value={corrente.shipping_mode}
            onChange={(e) =>
              setForm({ ...corrente, shipping_mode: e.target.value as SosnetMarketSettingsRead["shipping_mode"] })
            }
          >
            <option value="CUSTOMER_PAYS">la paga il cliente</option>
            <option value="INCLUDED">inclusa nel prezzo</option>
          </select>
        </div>
        <div>
          <span className={label}>Spese di spedizione (€)</span>
          <input
            className={input}
            inputMode="decimal"
            value={(corrente.shipping_flat_cents / 100).toString()}
            onChange={(e) => setForm({ ...corrente, shipping_flat_cents: centsFrom(e.target.value) })}
          />
          <span className="block text-[10px] text-surface-500 mt-1">
            {corrente.shipping_mode === "INCLUDED"
              ? "Inclusa nel prezzo: al checkout non si addebita nulla."
              : "Addebitate una volta per ordine, non per articolo."}
          </span>
        </div>
        <div>
          <span className={label}>Invio alle aziende</span>
          <select
            className={input}
            value={corrente.auto_forward ? "auto" : "manuale"}
            onChange={(e) => setForm({ ...corrente, auto_forward: e.target.value === "auto" })}
          >
            <option value="manuale">a mano, con il pulsante</option>
            <option value="auto">automatico al pagamento</option>
          </select>
          <span className="block text-[10px] text-surface-500 mt-1">
            {corrente.auto_forward
              ? "Appena il cliente paga, l'ordine parte da solo verso le aziende."
              : "L'ordine pagato aspetta che tu prema «Invia alle aziende»: una verifica umana prima di mandare una email a un'azienda vera."}
          </span>
        </div>
        <div>
          <span className={label}>Tempi di consegna</span>
          <input
            className={input}
            value={corrente.shipping_days ?? ""}
            placeholder="es. 3-5"
            onChange={(e) => setForm({ ...corrente, shipping_days: e.target.value })}
          />
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Chip tone={corrente.enabled ? "ok" : "muted"} live={corrente.enabled}>
          {corrente.enabled ? "Negozio acceso" : "Negozio spento"}
        </Chip>
        <Chip tone="info">{corrente.shipping_mode === "INCLUDED" ? "Spedizione inclusa" : `Spedizione ${euro(corrente.shipping_flat_cents)}`}</Chip>
        <Chip tone={corrente.auto_forward ? "accent" : "warn"}>{corrente.auto_forward ? "Invio automatico" : "Invio a mano"}</Chip>
      </div>
      <div className="flex items-center gap-3">
        <button
          onClick={() => salva.mutate(corrente)}
          disabled={salva.isPending}
          className="px-4 py-2 rounded-xl bg-brand-600 hover:bg-brand-500 text-xs font-semibold text-white transition cursor-pointer disabled:opacity-40"
        >
          {salva.isPending ? "Salvo…" : "Salva impostazioni"}
        </button>
        <Esito message={message} />
      </div>
    </Card>
  );
}

// --- Producer companies ---

const PRODUTTORE_VUOTO = {
  name: "", description: "", website_url: "", vat_number: "", email: "", phone: "", address: "",
};

function Produttori() {
  const queryClient = useQueryClient();
  // Behind a button: companies are edited rarely, products daily.
  const [aperto, setAperto] = useState(false);
  const { data: producers } = useQuery({
    queryKey: ["admin", "sosnet-market", "producers"],
    queryFn: () => get<SosnetMarketProducerRead[]>("/sosnet-market/producers"),
  });
  const [form, setForm] = useState({ ...PRODUTTORE_VUOTO });
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  const crea = useMutation({
    mutationFn: () =>
      send<SosnetMarketProducerRead>("/sosnet-market/producers", "POST", {
        ...form,
        website_url: form.website_url || null,
        vat_number: form.vat_number || null,
        email: form.email || null,
        phone: form.phone || null,
        address: form.address || null,
      }),
    onSuccess: (p) => {
      setForm({ ...PRODUTTORE_VUOTO });
      setMessage({ ok: true, text: `«${p.name}» aggiunta.` });
      queryClient.invalidateQueries({ queryKey: ["admin", "sosnet-market", "producers"] });
    },
    onError: (err: unknown) => setMessage({ ok: false, text: (err as Error).message }),
  });

  if (!aperto) {
    return (
      <div className="panel rise rounded-3xl p-6 flex items-center justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-4 min-w-0">
          <div className="kpi-value">{(producers ?? []).length}</div>
          <div className="min-w-0">
          <div className="kpi-label">Filiera</div>
          <h3 className="text-xl font-black tracking-tight text-white">Aziende produttrici</h3>
          <p className="text-xs text-surface-300 mt-1">
            {(producers ?? []).length === 0
              ? "Nessuna azienda ancora. Servono per dire al cliente chi fa la merce, e per mandare loro l'ordine."
              : `${(producers ?? []).length} in elenco: ${(producers ?? []).slice(0, 3).map((p) => p.name).join(", ")}${(producers ?? []).length > 3 ? "…" : ""}`}
          </p>
          </div>
        </div>
        <button
          onClick={() => setAperto(true)}
          className="act act-primary shrink-0"
        >
          Gestisci aziende
        </button>
      </div>
    );
  }

  return (
    <Card
      eyebrow="Filiera"
      title="Aziende produttrici"
      subtitle="Chi fa la merce. L'email è quella a cui mandiamo l'ordine quando il cliente paga."
    >
      <button
        onClick={() => setAperto(false)}
        className="act"
      >
        ← Chiudi
      </button>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        <div className="sm:col-span-2">
          <span className={label}>Nome dell&apos;azienda *</span>
          <input className={input} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        </div>
        <div>
          <span className={label}>Partita IVA</span>
          <input className={input} value={form.vat_number} onChange={(e) => setForm({ ...form, vat_number: e.target.value })} />
        </div>
        <div className="sm:col-span-3">
          <span className={label}>Descrizione (la legge il cliente)</span>
          <textarea
            className={`${input} min-h-[70px]`}
            value={form.description}
            placeholder="Chi sono, cosa producono, dove."
            onChange={(e) => setForm({ ...form, description: e.target.value })}
          />
        </div>
        <div>
          <span className={label}>Sito</span>
          <input className={input} value={form.website_url} placeholder="https://" onChange={(e) => setForm({ ...form, website_url: e.target.value })} />
        </div>
        <div>
          <span className={label}>Email per gli ordini</span>
          <input className={input} value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
          <span className="block text-[10px] text-surface-500 mt-1">
            È qui che arriva l&apos;ordine quando il cliente paga. Senza, l&apos;ordine non si può inviare.
          </span>
        </div>
        <div>
          <span className={label}>Telefono</span>
          <input className={input} value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
        </div>
        <div className="sm:col-span-3">
          <span className={label}>Sede</span>
          <input className={input} value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} />
        </div>
      </div>
      <div className="flex items-center gap-3">
        <button
          onClick={() => crea.mutate()}
          disabled={crea.isPending || form.name.trim().length === 0}
          className="px-4 py-2 rounded-xl bg-brand-600 hover:bg-brand-500 text-xs font-semibold text-white transition cursor-pointer disabled:opacity-40"
        >
          {crea.isPending ? "Aggiungo…" : "Aggiungi azienda"}
        </button>
        <Esito message={message} />
      </div>

      {(producers ?? []).length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr>
                <th className="px-4 py-3 text-left">Azienda</th>
                <th className="px-4 py-3 text-left">Recapito ordini</th>
                <th className="px-4 py-3 text-right">Pronta?</th>
              </tr>
            </thead>
            <tbody>
              {(producers ?? []).map((p) => (
                <tr key={p.id}>
                  <td className="px-4 py-3 max-w-[340px]">
                    <Identity name={p.name} detail={p.description || undefined} />
                  </td>
                  <td className="px-4 py-3">
                    {p.email ? (
                      <span className="text-xs text-surface-200">{p.email}</span>
                    ) : (
                      <span className="text-xs text-warn-400">manca l&apos;email: gli ordini non partiranno</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <Chip tone={p.email ? "ok" : "warn"} live={!p.email}>{p.email ? "Riceve ordini" : "Senza email"}</Chip>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}

// --- Catalog ---

type VarianteForm = { label: string; price: string; inventory: string };

const PRODOTTO_VUOTO = {
  name: "", description: "", image_url: "", credit_discount_percentage: "30", unit_cost: "",
  producer_id: "",
};

function Catalogo() {
  const queryClient = useQueryClient();
  const { data: products } = useQuery({
    queryKey: ["admin", "sosnet-market", "products"],
    queryFn: () => get<SosnetMarketAdminProductRead[]>("/sosnet-market/products"),
  });
  const { data: producers } = useQuery({
    queryKey: ["admin", "sosnet-market", "producers"],
    queryFn: () => get<SosnetMarketProducerRead[]>("/sosnet-market/producers"),
  });
  const [form, setForm] = useState({ ...PRODOTTO_VUOTO });
  const [variants, setVariants] = useState<VarianteForm[]>([{ label: "Unica", price: "", inventory: "" }]);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  const crea = useMutation({
    mutationFn: () =>
      send<SosnetMarketAdminProductRead>("/sosnet-market/products", "POST", {
        name: form.name,
        description: form.description,
        image_url: form.image_url || null,
        images: [],
        status: "ACTIVE",
        credit_discount_percentage: Number(form.credit_discount_percentage) || 0,
        unit_cost_cents: form.unit_cost ? centsFrom(form.unit_cost) : null,
        producer_id: form.producer_id || null,
        variants: variants.map((v) => ({
          label: v.label || "Unica",
          price_cents: centsFrom(v.price),
          inventory: v.inventory === "" ? null : Number(v.inventory),
        })),
      }),
    onSuccess: (p) => {
      setForm({ ...PRODOTTO_VUOTO });
      setVariants([{ label: "Unica", price: "", inventory: "" }]);
      setMessage({ ok: true, text: `«${p.name}» caricato.` });
      queryClient.invalidateQueries({ queryKey: ["admin", "sosnet-market", "products"] });
    },
    onError: (err: unknown) => setMessage({ ok: false, text: (err as Error).message }),
  });

  // Editing an already uploaded product (price, company, ...).
  const [modifica, setModifica] = useState<SosnetMarketAdminProductRead | null>(null);
  const salvaModifica = useMutation({
    mutationFn: (p: SosnetMarketAdminProductRead) =>
      send<SosnetMarketAdminProductRead>(`/sosnet-market/products/${p.id}`, "PATCH", {
        name: p.name,
        description: p.description,
        credit_discount_percentage: p.credit_discount_percentage,
        producer_id: p.producer_id || null,
      }),
    onSuccess: () => {
      setModifica(null);
      queryClient.invalidateQueries({ queryKey: ["admin", "sosnet-market", "products"] });
    },
    onError: (err: unknown) => setMessage({ ok: false, text: (err as Error).message }),
  });
  const salvaVariante = useMutation({
    mutationFn: ({ id, price_cents, inventory }: { id: string; price_cents: number; inventory: number | null }) =>
      send(`/sosnet-market/variants/${id}`, "PATCH", { price_cents, inventory }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin", "sosnet-market", "products"] }),
  });

  const spegni = useMutation({
    mutationFn: ({ id, status }: { id: string; status: "ACTIVE" | "INACTIVE" }) =>
      send<SosnetMarketAdminProductRead>(`/sosnet-market/products/${id}`, "PATCH", { status }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin", "sosnet-market", "products"] }),
  });

  return (
    <>
      <Card
        eyebrow="Nuovo articolo"
        title="Carica un prodotto"
        subtitle="Serve almeno una variante con il suo prezzo: un prodotto senza varianti non sarebbe comprabile."
      >
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          <div className="sm:col-span-2">
            <span className={label}>Nome *</span>
            <input className={input} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          </div>
          <div>
            <span className={label}>Azienda produttrice</span>
            <select
              className={input}
              value={form.producer_id}
              onChange={(e) => setForm({ ...form, producer_id: e.target.value })}
            >
              <option value="">— nessuna —</option>
              {(producers ?? []).map((p) => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </select>
          </div>
          <div>
            <span className={label}>SosnetCash max (%)</span>
            <input
              className={input}
              inputMode="numeric"
              value={form.credit_discount_percentage}
              onChange={(e) => setForm({ ...form, credit_discount_percentage: e.target.value })}
            />
            <span className="block text-[10px] text-surface-500 mt-1">Mai 100: è la regola dei Marketplace.</span>
          </div>
          <div className="sm:col-span-3">
            <span className={label}>Descrizione</span>
            <textarea
              className={`${input} min-h-[70px]`}
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
            />
          </div>
          <div>
            <span className={label}>Costo per noi (€)</span>
            <input
              className={input}
              inputMode="decimal"
              value={form.unit_cost}
              onChange={(e) => setForm({ ...form, unit_cost: e.target.value })}
            />
            <span className="block text-[10px] text-surface-500 mt-1">Serve solo al margine, mai mostrato.</span>
          </div>
          <div className="sm:col-span-4">
            <span className={label}>Immagine (URL)</span>
            <input className={input} value={form.image_url} onChange={(e) => setForm({ ...form, image_url: e.target.value })} />
          </div>
        </div>

        <div className="space-y-2">
          <p className={label}>Varianti</p>
          {variants.map((v, i) => (
            <div key={i} className="grid grid-cols-1 sm:grid-cols-4 gap-2">
              <input
                className={input}
                placeholder="Etichetta (es. 500 g)"
                value={v.label}
                onChange={(e) => setVariants(variants.map((x, j) => (i === j ? { ...x, label: e.target.value } : x)))}
              />
              <input
                className={input}
                inputMode="decimal"
                placeholder="Prezzo €"
                value={v.price}
                onChange={(e) => setVariants(variants.map((x, j) => (i === j ? { ...x, price: e.target.value } : x)))}
              />
              <input
                className={input}
                inputMode="numeric"
                placeholder="Scorta (vuoto = illimitata)"
                value={v.inventory}
                onChange={(e) => setVariants(variants.map((x, j) => (i === j ? { ...x, inventory: e.target.value } : x)))}
              />
              {variants.length > 1 && (
                <button
                  onClick={() => setVariants(variants.filter((_, j) => j !== i))}
                  className="act"
                >
                  Togli
                </button>
              )}
            </div>
          ))}
          <button
            onClick={() => setVariants([...variants, { label: "", price: "", inventory: "" }])}
            className="act"
          >
            + Aggiungi variante
          </button>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={() => crea.mutate()}
            disabled={crea.isPending || !form.name.trim() || variants.every((v) => !v.price)}
            className="px-4 py-2 rounded-xl bg-brand-600 hover:bg-brand-500 text-xs font-semibold text-white transition cursor-pointer disabled:opacity-40"
          >
            {crea.isPending ? "Carico…" : "Carica prodotto"}
          </button>
          <Esito message={message} />
        </div>
      </Card>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 stagger">
        <div style={{ "--i": 0 } as React.CSSProperties}>
          <KpiTile label="Prodotti" value={(products ?? []).length} hint="in catalogo" />
        </div>
        <div style={{ "--i": 1 } as React.CSSProperties}>
          <KpiTile label="In vendita" value={(products ?? []).filter((p) => p.status === "ACTIVE").length} hint="visibili nello Shop" />
        </div>
        <div style={{ "--i": 2 } as React.CSSProperties}>
          <KpiTile label="Spenti" value={(products ?? []).filter((p) => p.status !== "ACTIVE").length} hint="nascosti al cliente" />
        </div>
      </div>

      <Card eyebrow="Vetrina" title="Prodotti in catalogo" subtitle={`${(products ?? []).length} prodotti.`}>
        {(products ?? []).length === 0 ? (
          <EmptyBlock text="Nessun prodotto ancora. Caricane uno qui sopra." />
        ) : (
          <div className="space-y-4">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr>
                    <th className="px-4 py-3 text-left">Articolo</th>
                    <th className="px-4 py-3 text-left">Formati</th>
                    <th className="px-4 py-3 text-right">Prezzo al cliente</th>
                    <th className="px-4 py-3 text-left">Vetrina</th>
                    <th className="px-4 py-3" />
                  </tr>
                </thead>
                <tbody>
                  {(products ?? []).map((p) => {
                    const prezzi = p.variants.map((v) => v.price_cents);
                    const min = prezzi.length ? Math.min(...prezzi) : 0;
                    const max = prezzi.length ? Math.max(...prezzi) : 0;
                    return (
                      <tr key={p.id}>
                        <td className="px-4 py-3 max-w-[360px]">
                          <div className="flex items-center gap-3 min-w-0">
                            <div className="h-12 w-12 shrink-0 overflow-hidden rounded-2xl ring-1 ring-white/15">
                              <ProductThumbnail imageUrl={p.image_url} alt={p.name} className="h-full w-full object-cover" iconClassName="w-6 h-6 text-brand-300/60" />
                            </div>
                            <Stack title={p.name} detail={p.producer?.name ?? "Nessuna azienda"} />
                          </div>
                        </td>
                        <td className="px-4 py-3">
                          <Stack
                            title={`${p.variants.length} ${p.variants.length === 1 ? "variante" : "varianti"}`}
                            detail={p.variants.map((v) => v.label).join(" · ")}
                          />
                        </td>
                        <td className="px-4 py-3 text-right">
                          <Figure
                            value={p.variants.length > 1 && max !== min ? `${euro(min)} – ${euro(max)}` : euro(min)}
                            detail={`SosnetCash ${p.credit_discount_percentage}%`}
                            ratio={p.credit_discount_percentage / 100}
                          />
                        </td>
                        <td className="px-4 py-3">
                          <Chip tone={p.status === "ACTIVE" ? "ok" : "muted"}>
                            {p.status === "ACTIVE" ? "In vendita" : "Spento"}
                          </Chip>
                        </td>
                        <td className="px-4 py-3">
                          <RowActions>
                            <button
                              onClick={() => setModifica(modifica?.id === p.id ? null : p)}
                              className={modifica?.id === p.id ? "act act-primary" : "act"}
                            >
                              {modifica?.id === p.id ? "Chiudi" : "Modifica"}
                            </button>
                            <button
                              onClick={() => spegni.mutate({ id: p.id, status: p.status === "ACTIVE" ? "INACTIVE" : "ACTIVE" })}
                              className="act"
                            >
                              {p.status === "ACTIVE" ? "Spegni" : "Rimetti in vendita"}
                            </button>
                          </RowActions>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            {modifica && (
              <div className="pop rounded-3xl border border-white/15 bg-white/5 p-5 space-y-4">
                <div>
                  <div className="kpi-label">Modifica</div>
                  <p className="text-lg font-black tracking-tight text-white">«{modifica.name}»</p>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  <div className="sm:col-span-2">
                    <span className={label}>Nome</span>
                    <input
                      className={input}
                      value={modifica.name}
                      onChange={(e) => setModifica({ ...modifica, name: e.target.value })}
                    />
                  </div>
                  <div>
                    <span className={label}>Azienda produttrice</span>
                    <select
                      className={input}
                      value={modifica.producer_id ?? ""}
                      onChange={(e) => setModifica({ ...modifica, producer_id: e.target.value || null })}
                    >
                      <option value="">— nessuna —</option>
                      {(producers ?? []).map((pr) => (
                        <option key={pr.id} value={pr.id}>{pr.name}</option>
                      ))}
                    </select>
                  </div>
                  <div className="sm:col-span-2">
                    <span className={label}>Descrizione</span>
                    <textarea
                      className={`${input} min-h-[60px]`}
                      value={modifica.description}
                      onChange={(e) => setModifica({ ...modifica, description: e.target.value })}
                    />
                  </div>
                  <div>
                    <span className={label}>SosnetCash max (%)</span>
                    <input
                      className={input}
                      inputMode="numeric"
                      value={String(modifica.credit_discount_percentage)}
                      onChange={(e) =>
                        setModifica({ ...modifica, credit_discount_percentage: Number(e.target.value) || 0 })
                      }
                    />
                  </div>
                </div>
                <div className="space-y-2">
                  <p className={label}>Prezzi e scorte</p>
                  {modifica.variants.map((v) => (
                    <div key={v.id} className="grid grid-cols-1 sm:grid-cols-4 gap-2 items-center">
                      <span className="text-xs font-semibold text-surface-200">{v.label}</span>
                      <input
                        className={input}
                        inputMode="decimal"
                        defaultValue={(v.price_cents / 100).toString()}
                        onBlur={(e) =>
                          salvaVariante.mutate({
                            id: v.id, price_cents: centsFrom(e.target.value), inventory: v.inventory,
                          })
                        }
                      />
                      <input
                        className={input}
                        inputMode="numeric"
                        placeholder="Scorta"
                        defaultValue={v.inventory === null ? "" : String(v.inventory)}
                        onBlur={(e) =>
                          salvaVariante.mutate({
                            id: v.id, price_cents: v.price_cents,
                            inventory: e.target.value === "" ? null : Number(e.target.value),
                          })
                        }
                      />
                      <span className="text-[10px] text-surface-500">si salva uscendo dal campo</span>
                    </div>
                  ))}
                </div>
                <button
                  onClick={() => salvaModifica.mutate(modifica)}
                  disabled={salvaModifica.isPending}
                  className="px-4 py-2 rounded-xl bg-brand-600 hover:bg-brand-500 text-xs font-semibold text-white transition cursor-pointer disabled:opacity-40"
                >
                  {salvaModifica.isPending ? "Salvo…" : "Salva modifiche"}
                </button>
              </div>
            )}
          </div>
        )}
      </Card>
    </>
  );
}


// --- Orders ---

function Ordini() {
  const queryClient = useQueryClient();
  const { data: orders } = useQuery({
    queryKey: ["admin", "sosnet-market", "orders"],
    queryFn: () => get<SosnetMarketOrderRead[]>("/sosnet-market/orders"),
  });
  const { data: settings } = useQuery({
    queryKey: ["admin", "sosnet-market", "settings"],
    queryFn: () => get<SosnetMarketSettingsRead>("/sosnet-market/settings"),
  });
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  const invia = useMutation({
    mutationFn: (id: string) => send<SosnetMarketOrderRead>(`/sosnet-market/orders/${id}/forward`, "POST", {}),
    onSuccess: (o) =>
      setMessage(
        o.forward_error
          ? { ok: false, text: `Inviato in parte: ${o.forward_error}` }
          : { ok: true, text: `Ordine #${o.order_code} inviato alle aziende.` },
      ),
    onError: (err: unknown) => setMessage({ ok: false, text: (err as Error).message }),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["admin", "sosnet-market", "orders"] }),
  });
  const conferma = useMutation({
    mutationFn: (id: string) => send(`/sosnet-market/orders/${id}/confirm-payment`, "POST", {}),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["admin", "sosnet-market", "orders"] }),
  });

  const daFare = (orders ?? []).filter((o) => o.status !== "CANCELLED");
  return (
    <Card
      eyebrow="Consegne"
      title="Ordini"
      subtitle={
        settings?.auto_forward
          ? "Invio automatico acceso: un ordine pagato parte da solo verso le aziende."
          : "Invio a mano: un ordine pagato aspetta che tu prema «Invia alle aziende»."
      }
    >
      <Esito message={message} />
      {daFare.length === 0 ? (
        <EmptyBlock text="Nessun ordine." />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr>
                <th className="px-4 py-3 text-left">Acquirente</th>
                <th className="px-4 py-3 text-left">Carrello</th>
                <th className="px-4 py-3 text-right">Valore</th>
                <th className="px-4 py-3 text-left">Situazione</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {daFare.map((o) => {
                const aziende = Array.from(new Set((o.producers ?? []).map((p) => p.name))).join(", ");
                return (
                  <tr key={o.id}>
                    <td className="px-4 py-3 max-w-[260px]">
                      <Identity name={o.customer_display_name} detail={`#${o.order_code}`} />
                    </td>
                    <td className="px-4 py-3 max-w-[320px]">
                      <Stack
                        title={(o.items ?? []).map((i) => `${i.quantity} × ${i.product_name}`).join(" · ") || "—"}
                        detail={aziende || undefined}
                      />
                      {o.forward_error && (
                        <p className="mt-1 text-[11px] text-warn-400">Da sistemare: {o.forward_error}</p>
                      )}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <Figure value={euro(o.amount_cents)} />
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex flex-col items-start gap-1">
                        <Chip
                          tone={o.status === "PAID" ? "ok" : o.status === "AWAITING_PAYMENT" ? "warn" : "info"}
                          live={o.status === "AWAITING_PAYMENT"}
                        >
                          {o.status === "AWAITING_PAYMENT" ? "In attesa di pagamento" : o.status === "PAID" ? "Pagato" : o.status}
                        </Chip>
                        {o.forwarded_at && (
                          <span className="text-[11px] text-surface-400">inviato alle aziende · {when(o.forwarded_at)}</span>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <RowActions>
                        {o.status === "AWAITING_PAYMENT" && o.payment_method === "BANK_TRANSFER" && (
                          <button onClick={() => conferma.mutate(o.id)} className="act">
                            Conferma bonifico
                          </button>
                        )}
                        {o.status === "PAID" && (
                          <button
                            onClick={() => invia.mutate(o.id)}
                            disabled={invia.isPending}
                            className="act act-primary"
                          >
                            {o.forwarded_at ? "Reinvia alle aziende" : "Invia alle aziende"}
                          </button>
                        )}
                      </RowActions>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}

export function AdminSosnetMarketPanel() {
  return (
    <div className="space-y-6">
      <Impostazioni />
      <Produttori />
      <Catalogo />
      <Ordini />
    </div>
  );
}
