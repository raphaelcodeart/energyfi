"use client";

import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { friendlyApiError } from "@/lib/api-error";
import { addedVatCents } from "@/lib/product-audience";
import type { MarketplaceConfigRead, ShopSectionKey } from "@/lib/types";
import { Chip } from "@/components/ui/data-cells";

export const MARKETPLACE_SOURCES: { key: "aliexpress" | "cj" | "shopify" | "sosnet_market"; source: string }[] = [
  { key: "aliexpress", source: "AliExpress" },
  { key: "cj", source: "CJ Dropshipping" },
  { key: "shopify", source: "Shopify" },
  // The only one without a supplier: we maintain its catalog.
  { key: "sosnet_market", source: "catalogo nostro" },
];

async function fetchConfig(): Promise<MarketplaceConfigRead> {
  const res = await fetch("/api/proxy/marketplaces/config");
  if (!res.ok) throw new Error(await friendlyApiError(res));
  return res.json();
}

/**
 * Marketplace tab names and bank-transfer discount, used by the customer Shop
 * and every imported-product checkout.
 */
export function useMarketplaceConfig() {
  return useQuery({ queryKey: ["marketplaces", "config"], queryFn: fetchConfig, staleTime: 60_000 });
}

/**
 * "Regole dei Marketplace": settings shared by the imported-product shops
 * (AliExpress, CJ Dropshipping, Shopify): each one's name in the customer
 * Shop, the bank-transfer discount (a discount, never a card surcharge,
 * which Italian law forbids) and the VAT rate already included in shown
 * prices (Italian consumer prices must be final). SosnetCash rules are shown
 * read-only: 30% on a new product, never 100%.
 */
export function MarketplaceRulesCard({ highlight }: { highlight?: "aliexpress" | "cj" | "shopify" | "sosnet_market" }) {
  const queryClient = useQueryClient();
  const { data: config, error } = useMarketplaceConfig();
  const [open, setOpen] = useState(false);
  const [labels, setLabels] = useState<Record<string, string>>({});
  const [discount, setDiscount] = useState("");
  const [vat, setVat] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  useEffect(() => {
    if (!config) return;
    // Sync the form with the server copy once it arrives.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLabels(config.labels);
    setDiscount(String(config.bank_transfer_discount_percentage));
    setVat(config.vat_percentage === undefined ? "" : String(config.vat_percentage));
  }, [config]);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setMessage(null);
    try {
      const res = await fetch("/api/proxy/marketplaces/config", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          labels,
          bank_transfer_discount_percentage: Number(discount) || 0,
          // Empty means not yet received from the server; sending 0 would reset the real rate.
          ...(vat === "" ? {} : { vat_percentage: Number(vat) || 0 }),
        }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      queryClient.setQueryData(["marketplaces", "config"], await res.json());
      setMessage({ ok: true, text: "Salvato." });
    } catch (err: any) {
      setMessage({ ok: false, text: err.message || "Salvataggio non riuscito." });
    } finally {
      setBusy(false);
    }
  }

  const pct = Number(discount) || 0;
  const vatPct = Number(vat) || 0;
  const label = highlight && config ? config.labels[highlight] : null;

  return (
    <div className="panel rounded-3xl">
      <button onClick={() => setOpen((v) => !v)} className="w-full flex flex-wrap items-center justify-between gap-3 px-6 py-5 text-left cursor-pointer">
        <span className="min-w-0">
          <span className="kpi-label block">Regole condivise</span>
          <span className="block text-xl font-black tracking-tight text-white mt-1">
            Regole dei Marketplace{label ? ` · per i clienti si chiama “${label}”` : ""}
          </span>
          {config ? (
            <span className="mt-2 flex flex-wrap gap-1.5">
              {config.vat_percentage ? <Chip tone="info">Prezzi IVA {config.vat_percentage}% inclusa</Chip> : null}
              <Chip tone="ok">Bonifico -{config.bank_transfer_discount_percentage}%</Chip>
              <Chip tone="accent">
                SosnetCash {config.default_credit_percentage}% sui nuovi prodotti, mai 100% (max {config.max_credit_percentage}%)
              </Chip>
              <Chip tone="muted">nessun cashback</Chip>
            </span>
          ) : (
            <span className="block text-xs text-surface-300 mt-1">Caricamento...</span>
          )}
        </span>
        <span className={open ? "act act-primary" : "act"}>{open ? "Chiudi" : "Modifica"}</span>
      </button>
      {error && <p className="px-6 pb-4 text-xs text-danger-400">{(error as Error).message}</p>}
      {open && config && (
        <form onSubmit={save} className="pop px-6 pb-6 space-y-4 border-t border-white/10 pt-5">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            {MARKETPLACE_SOURCES.map((m) => (
              <label key={m.key} className="block">
                <span className="kpi-label block mb-1">
                  Nome nello Shop · {m.source}
                </span>
                <input
                  value={labels[m.key] ?? ""}
                  maxLength={40}
                  onChange={(e) => setLabels({ ...labels, [m.key]: e.target.value })}
                  className="w-full rounded-xl field px-3 py-2 text-sm focus:border-brand-500"
                />
              </label>
            ))}
          </div>
          <label className="block max-w-xs">
            <span className="kpi-label block mb-1">
              Sconto se si paga con bonifico (%)
            </span>
            <input
              inputMode="numeric"
              value={discount}
              onChange={(e) => setDiscount(e.target.value.replace(/\D/g, ""))}
              className="w-full rounded-xl field px-3 py-2 text-sm focus:border-brand-500"
            />
            <span className="block text-[10px] text-surface-500 mt-1">
              {pct > 0
                ? `Esempio: 20,00 € con carta = ${((2000 - Math.floor((2000 * pct + 50) / 100)) / 100).toFixed(2).replace(".", ",")} € con bonifico istantaneo. Il prezzo mostrato è quello pieno; con carta non si paga mai di più. Vale per tutti e tre i Marketplace.`
                : "0 = nessuno sconto, stesso prezzo con carta e bonifico."}
            </span>
          </label>
          <label className="block max-w-xs">
            <span className="kpi-label block mb-1">
              Aliquota IVA dei prodotti (%)
            </span>
            <input
              inputMode="numeric"
              value={vat}
              onChange={(e) => setVat(e.target.value.replace(/\D/g, ""))}
              className="w-full rounded-xl field px-3 py-2 text-sm focus:border-brand-500"
            />
            <span className="block text-[10px] text-surface-500 mt-1">
              {vatPct > 0
                ? `I prezzi dei prodotti dei Marketplace sono imponibili: questa è l'aliquota che si aggiunge al checkout. Esempio: 100,00 € diventano ${((10000 + addedVatCents(10000, vatPct)) / 100).toFixed(2).replace(".", ",")} € per il cliente.`
                : "0 = nessuna IVA mostrata al cliente. Di norma 22%: il prezzo resta quello, l'IVA è dentro."}
            </span>
          </label>
          <p className="text-[11px] text-surface-500">
            Il cliente non vede mai la fonte (AliExpress, CJ, Shopify): solo il nome scelto qui. I prodotti dei
            Marketplace non danno cashback: permettono solo di spendere il SosnetCash, al massimo per la percentuale di
            ogni prodotto (30% quando entra, modificabile fino al {config.max_credit_percentage}%).
          </p>
          <div className="flex items-center gap-3">
            <button
              type="submit"
              disabled={busy}
              className="px-4 py-2 rounded-xl bg-brand-600 hover:bg-brand-500 text-xs font-bold text-white cursor-pointer disabled:opacity-50"
            >
              {busy ? "Salvataggio..." : "Salva"}
            </button>
            {message && <span className={`text-xs ${message.ok ? "text-success-400" : "text-danger-400"}`}>{message.text}</span>}
          </div>
        </form>
      )}
    </div>
  );
}


export const SHOP_SECTIONS: { key: ShopSectionKey; what: string }[] = [
  { key: "internal", what: "I contratti e i pacchetti SOSNET" },
  { key: "partner", what: "I prodotti dei fornitori partner" },
  { key: "dropshipping", what: "Le offerte del catalogo Sosnet" },
];

/**
 * "Sezioni dello Shop": customer Shop tabs not backed by an imported
 * marketplace. Each can be switched on/off and renamed. Marketplace tabs have
 * their switch in each shop's settings.
 */
export function ShopSectionsCard() {
  const queryClient = useQueryClient();
  const { data: config, error } = useMarketplaceConfig();
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<Record<string, { label: string; enabled: boolean }>>({});
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  useEffect(() => {
    if (!config) return;
    // Sync the form with the server copy once it arrives.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setDraft(config.sections);
  }, [config]);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setMessage(null);
    try {
      const res = await fetch("/api/proxy/marketplaces/config", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sections: draft }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      queryClient.setQueryData(["marketplaces", "config"], await res.json());
      setMessage({ ok: true, text: "Salvato." });
    } catch (err: any) {
      setMessage({ ok: false, text: err.message || "Salvataggio non riuscito." });
    } finally {
      setBusy(false);
    }
  }

  const summary = config
    ? SHOP_SECTIONS.map((s) => `${config.sections[s.key].label}${config.sections[s.key].enabled ? "" : " (spenta)"}`).join(" · ")
    : "Caricamento...";

  return (
    <div className="panel rounded-3xl">
      <button onClick={() => setOpen((v) => !v)} className="w-full flex flex-wrap items-center justify-between gap-3 px-6 py-5 text-left cursor-pointer">
        <span className="min-w-0">
          <span className="kpi-label block">Vetrina</span>
          <span className="block text-xl font-black tracking-tight text-white mt-1">Sezioni dello Shop del cliente</span>
          {config ? (
            <span className="mt-2 flex flex-wrap gap-1.5" title={summary}>
              {SHOP_SECTIONS.map((s) => (
                <Chip key={s.key} tone={config.sections[s.key].enabled ? "ok" : "muted"}>
                  {config.sections[s.key].label}
                  {config.sections[s.key].enabled ? "" : " (spenta)"}
                </Chip>
              ))}
            </span>
          ) : (
            <span className="block text-xs text-surface-300 mt-1">{summary}</span>
          )}
        </span>
        <span className={open ? "act act-primary" : "act"}>{open ? "Chiudi" : "Modifica"}</span>
      </button>
      {error && <p className="px-6 pb-4 text-xs text-danger-400">{(error as Error).message}</p>}
      {open && config && (
        <form onSubmit={save} className="pop px-6 pb-6 space-y-4 border-t border-white/10 pt-5">
          {SHOP_SECTIONS.map((section) => {
            const value = draft[section.key] ?? config.sections[section.key];
            return (
              <div key={section.key} className="flex flex-wrap items-end gap-3">
                <label className="block flex-1 min-w-[180px]">
                  <span className="kpi-label block mb-1">
                    Nome nello Shop · {section.what}
                  </span>
                  <input
                    value={value.label}
                    maxLength={40}
                    onChange={(e) => setDraft({ ...draft, [section.key]: { ...value, label: e.target.value } })}
                    className="w-full rounded-xl field px-3 py-2 text-sm focus:border-brand-500"
                  />
                </label>
                <button
                  type="button"
                  onClick={() => setDraft({ ...draft, [section.key]: { ...value, enabled: !value.enabled } })}
                  aria-pressed={value.enabled}
                  className="cursor-pointer rounded-full py-1.5"
                >
                  <Chip tone={value.enabled ? "ok" : "muted"} live={value.enabled}>
                    {value.enabled ? "Visibile" : "Spenta"}
                  </Chip>
                </button>
              </div>
            );
          })}
          <p className="text-[11px] text-surface-500">
            Una sezione spenta sparisce dallo Shop del cliente. I tre Marketplace hanno il proprio interruttore
            (&ldquo;Shop visibile ai clienti&rdquo;) nelle impostazioni di ciascuno, e il nome nella card
            &ldquo;Regole dei Marketplace&rdquo;: una scheda Marketplace compare solo se accesa **e** se ha almeno un
            prodotto in vendita.
          </p>
          <div className="flex items-center gap-3">
            <button
              type="submit"
              disabled={busy}
              className="px-4 py-2 rounded-xl bg-brand-600 hover:bg-brand-500 text-xs font-bold text-white cursor-pointer disabled:opacity-50"
            >
              {busy ? "Salvataggio..." : "Salva"}
            </button>
            {message && <span className={`text-xs ${message.ok ? "text-success-400" : "text-danger-400"}`}>{message.text}</span>}
          </div>
        </form>
      )}
    </div>
  );
}
