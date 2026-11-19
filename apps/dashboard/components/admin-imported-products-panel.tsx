"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { friendlyApiError } from "@/lib/api-error";
import { ProductCategoriesField, saveProductCategories, sameCategorySelection } from "@/components/shop-categories-card";
import type { ImportedProductAdminRead, ImportProviderRead } from "@/lib/types";
import { ProductThumbnail } from "@/components/product-thumbnail";
import { Chip, Figure, Identity, KpiTile, RowActions, Stack } from "@/components/ui/data-cells";

function euro(cents: number): string {
  return (cents / 100).toLocaleString("it-IT", { style: "currency", currency: "EUR" });
}

function when(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("it-IT", { day: "2-digit", month: "short", year: "numeric" });
}

const fieldLabel = "kpi-label block";
const fieldInput = "w-full rounded-xl field px-3 py-2 text-sm focus:border-brand-500";

function EmptyRow({ colSpan, text }: { colSpan: number; text: string }) {
  return (
    <tr>
      <td colSpan={colSpan} className="px-4 py-10">
        <div className="flex flex-col items-center gap-2 text-center">
          <span className="orb float-soft" aria-hidden="true">
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.6} d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />
            </svg>
          </span>
          <p className="text-sm text-surface-300">{text}</p>
        </div>
      </td>
    </tr>
  );
}

async function fetchProviders(): Promise<ImportProviderRead[]> {
  const res = await fetch("/api/proxy/imported-products/providers");
  if (!res.ok) throw new Error("Impossibile caricare i provider.");
  return res.json();
}

async function fetchProviderTypes(): Promise<string[]> {
  const res = await fetch("/api/proxy/imported-products/provider-types");
  if (!res.ok) throw new Error("Impossibile caricare i tipi di provider.");
  return res.json();
}

async function fetchProducts(): Promise<ImportedProductAdminRead[]> {
  const res = await fetch("/api/proxy/imported-products/products");
  if (!res.ok) throw new Error("Impossibile caricare i prodotti importati.");
  return res.json();
}

/**
 * Admin for the legacy hand-entered "Acquisti SOSNET" list: import providers
 * (type/url/key) and the hand-added catalog, kept separate from
 * admin-products-panel.tsx like the backend tables. Shown as a tab of
 * admin-aliexpress-panel.tsx; new products come from the API catalog search.
 */
export function AdminImportedProductsPanel() {
  const queryClient = useQueryClient();
  const { data: providers, error: providersError } = useQuery({
    queryKey: ["admin", "import-providers"],
    queryFn: fetchProviders,
  });
  const { data: providerTypes } = useQuery({
    queryKey: ["admin", "import-provider-types"],
    queryFn: fetchProviderTypes,
  });
  const { data: products, error: productsError } = useQuery({
    queryKey: ["admin", "imported-products"],
    queryFn: fetchProducts,
  });

  const [providerType, setProviderType] = useState("ALIEXPRESS");
  const [providerName, setProviderName] = useState("");
  const [providerUrl, setProviderUrl] = useState("");
  const [providerKey, setProviderKey] = useState("");
  const [providerCreateLoading, setProviderCreateLoading] = useState(false);
  const [providerCreateError, setProviderCreateError] = useState<string | null>(null);
  const [providerToggleId, setProviderToggleId] = useState<string | null>(null);

  const [showProductForm, setShowProductForm] = useState(false);
  const [pProviderId, setPProviderId] = useState("");
  const [pName, setPName] = useState("");
  const [pDescription, setPDescription] = useState("");
  const [pImageUrl, setPImageUrl] = useState("");
  const [pExternalUrl, setPExternalUrl] = useState("");
  const [pPrice, setPPrice] = useState("");
  const [pCreditPct, setPCreditPct] = useState("30");
  // To customers these are the same Marketplace as the API-imported AliExpress
  // products, so they share the "aliexpress" categories.
  const [pCategoryIds, setPCategoryIds] = useState<string[]>([]);
  const [categoriesTarget, setCategoriesTarget] = useState<ImportedProductAdminRead | null>(null);
  const [productCreateLoading, setProductCreateLoading] = useState(false);
  const [productCreateError, setProductCreateError] = useState<string | null>(null);
  const [productToggleId, setProductToggleId] = useState<string | null>(null);

  async function handleCreateProvider(e: React.FormEvent) {
    e.preventDefault();
    if (!providerName.trim()) return;
    setProviderCreateLoading(true);
    setProviderCreateError(null);
    try {
      const res = await fetch("/api/proxy/imported-products/providers", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          provider_type: providerType, name: providerName.trim(),
          base_url: providerUrl.trim() || null, api_key: providerKey.trim() || null, enabled: true,
        }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      setProviderName(""); setProviderUrl(""); setProviderKey("");
      await queryClient.invalidateQueries({ queryKey: ["admin", "import-providers"] });
    } catch (err: any) {
      setProviderCreateError(err.message || "Impossibile creare il provider.");
    } finally {
      setProviderCreateLoading(false);
    }
  }

  async function handleToggleProvider(provider: ImportProviderRead) {
    setProviderToggleId(provider.id);
    try {
      const res = await fetch(`/api/proxy/imported-products/providers/${provider.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: !provider.enabled }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      await queryClient.invalidateQueries({ queryKey: ["admin", "import-providers"] });
    } finally {
      setProviderToggleId(null);
    }
  }

  async function handleCreateProduct(e: React.FormEvent) {
    e.preventDefault();
    const priceCents = Math.round((parseFloat(pPrice.replace(",", ".")) || 0) * 100);
    if (!pProviderId || !pName.trim() || priceCents <= 0) return;
    setProductCreateLoading(true);
    setProductCreateError(null);
    try {
      const res = await fetch("/api/proxy/imported-products/products", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          provider_id: pProviderId, name: pName.trim(), description: pDescription.trim(),
          image_url: pImageUrl.trim() || null, external_url: pExternalUrl.trim() || null,
          price_cents: priceCents, credit_discount_percentage: Math.max(0, Math.min(99, parseInt(pCreditPct, 10) || 0)),
          status: "ACTIVE",
        }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      const created: ImportedProductAdminRead = await res.json();
      if (pCategoryIds.length > 0 && created?.id) {
        await saveProductCategories("aliexpress", created.id, pCategoryIds);
        await queryClient.invalidateQueries({ queryKey: ["shop-categories", "aliexpress"] });
      }
      setPName(""); setPDescription(""); setPImageUrl(""); setPExternalUrl(""); setPPrice(""); setPCreditPct("0");
      setPCategoryIds([]);
      setShowProductForm(false);
      await queryClient.invalidateQueries({ queryKey: ["admin", "imported-products"] });
    } catch (err: any) {
      setProductCreateError(err.message || "Impossibile creare il prodotto.");
    } finally {
      setProductCreateLoading(false);
    }
  }

  async function handleToggleProduct(product: ImportedProductAdminRead) {
    setProductToggleId(product.id);
    try {
      const res = await fetch(`/api/proxy/imported-products/products/${product.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: product.status === "ACTIVE" ? "INACTIVE" : "ACTIVE" }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      await queryClient.invalidateQueries({ queryKey: ["admin", "imported-products"] });
    } finally {
      setProductToggleId(null);
    }
  }

  const enabledProviders = (providers ?? []).filter((p) => p.enabled);

  const activeProducts = (products ?? []).filter((p) => p.status === "ACTIVE").length;

  return (
    <div className="space-y-8">
      <div className="rise">
        <div className="kpi-label">Catalogo manuale</div>
        <h3 className="mt-1 text-2xl font-black tracking-tight text-white">Prodotti inseriti a mano</h3>
        <p className="text-xs text-surface-300 mt-2 max-w-3xl">
          Prodotti scritti a mano uno per uno -- compaiono nello Shop del cliente nello stesso Marketplace dei prodotti
          importati dall&apos;API, senza mai rivelare la fonte. Il cliente può pagarne una parte con i suoi SosnetCash (30%
          quando il prodotto entra, mai il 100%); questi prodotti non generano mai cashback. Chi paga con bonifico ha
          lo sconto previsto dalle Regole dei Marketplace; con carta si paga il prezzo mostrato.
          Gli ordini su questi prodotti si gestiscono insieme a tutti gli altri nella scheda &ldquo;Ordini&rdquo;.
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <KpiTile label="Provider attivi" value={enabledProviders.length} hint={`su ${(providers ?? []).length} configurati`} />
        <KpiTile label="Prodotti" value={(products ?? []).length} hint="inseriti a mano" />
        <KpiTile label="In vendita" value={activeProducts} hint="visibili nello Shop" />
      </div>

      {/* Providers */}
      <div className="panel rounded-3xl p-6 sm:p-7">
        <div className="kpi-label">Fonte</div>
        <h4 className="text-xl font-black tracking-tight text-white mb-1">Nuovo provider di dropshipping</h4>
        <p className="text-xs text-surface-300 mb-5">
          La chiave API non viene mai mostrata di nuovo dopo il salvataggio (solo le ultime 4 cifre) -- stesso trattamento delle chiavi Stripe.
        </p>
        <form onSubmit={handleCreateProvider} className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3 items-end">
          <div className="space-y-1">
            <label className={fieldLabel}>Tipo di servizio</label>
            <select
              value={providerType}
              onChange={(e) => setProviderType(e.target.value)}
              className={fieldInput}
            >
              {(providerTypes ?? ["ALIEXPRESS"]).map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
          </div>
          <div className="space-y-1">
            <label className={fieldLabel}>Nome</label>
            <input
              required value={providerName} onChange={(e) => setProviderName(e.target.value)}
              placeholder="Es. AliExpress IT" className={fieldInput}
            />
          </div>
          <div className="space-y-1">
            <label className={fieldLabel}>URL API</label>
            <input
              value={providerUrl} onChange={(e) => setProviderUrl(e.target.value)}
              placeholder="https://api...." className={fieldInput}
            />
          </div>
          <div className="space-y-1">
            <label className={fieldLabel}>API KEY</label>
            <input
              type="password" value={providerKey} onChange={(e) => setProviderKey(e.target.value)}
              placeholder="••••••••" className={fieldInput}
            />
          </div>
          <button
            type="submit" disabled={providerCreateLoading}
            className="px-4 py-2.5 rounded-xl bg-brand-600 hover:bg-brand-500 text-xs font-semibold text-white transition cursor-pointer disabled:opacity-50"
          >
            {providerCreateLoading ? "..." : "Aggiungi provider"}
          </button>
        </form>
        {providerCreateError && (
          <div className="mt-3 p-3 rounded-lg bg-danger-500/10 border border-danger-500/20 text-danger-400 text-xs">{providerCreateError}</div>
        )}
      </div>

      <div className="panel rounded-3xl p-6 sm:p-7">
        <div className="mb-4">
          <div className="kpi-label">Collegamenti</div>
          <h4 className="text-xl font-black tracking-tight text-white">Provider configurati</h4>
        </div>
        {providersError && <p className="pb-3 text-sm text-danger-400">Impossibile caricare i provider.</p>}
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr>
                <th className="px-4 py-3">Fornitore</th>
                <th className="px-4 py-3">Accesso API</th>
                <th className="px-4 py-3">Situazione</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {providers === undefined ? (
                <EmptyRow colSpan={4} text="Caricamento..." />
              ) : providers.length === 0 ? (
                <EmptyRow colSpan={4} text="Nessun provider ancora." />
              ) : (
                providers.map((p) => (
                  <tr key={p.id}>
                    <td className="px-4 py-3">
                      <Identity name={p.name} detail={`${p.provider_type} · dal ${when(p.created_at)}`} />
                    </td>
                    <td className="px-4 py-3 max-w-[260px]">
                      <Stack
                        title={
                          p.api_key_configured ? (
                            <span className="font-mono">•••• {p.api_key_last4}</span>
                          ) : (
                            <span className="text-surface-400">chiave non configurata</span>
                          )
                        }
                        detail={<span title={p.base_url ?? undefined}>{p.base_url ?? "—"}</span>}
                      />
                    </td>
                    <td className="px-4 py-3">
                      <Chip tone={p.enabled ? "ok" : "muted"}>{p.enabled ? "Attivo" : "Disattivato"}</Chip>
                    </td>
                    <td className="px-4 py-3">
                      <RowActions>
                        <button
                          onClick={() => handleToggleProvider(p)}
                          disabled={providerToggleId === p.id}
                          className="act"
                        >
                          {providerToggleId === p.id ? "..." : p.enabled ? "Disattiva" : "Riattiva"}
                        </button>
                      </RowActions>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Products */}
      <div className="flex items-end justify-between gap-3 flex-wrap">
        <div>
          <div className="kpi-label">Vetrina</div>
          <h4 className="text-xl font-black tracking-tight text-white">Catalogo prodotti importati</h4>
        </div>
        <button
          onClick={() => setShowProductForm((v) => !v)}
          disabled={enabledProviders.length === 0}
          className="px-4 py-2 rounded-xl bg-brand-600 hover:bg-brand-500 text-xs font-semibold text-white transition cursor-pointer disabled:opacity-40"
          title={enabledProviders.length === 0 ? "Configura prima almeno un provider" : undefined}
        >
          {showProductForm ? "Annulla" : "Aggiungi prodotto"}
        </button>
      </div>

      {showProductForm && (
        <div className="panel pop rounded-3xl p-6 sm:p-7">
          <form onSubmit={handleCreateProduct} className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div className="space-y-1">
              <label className={fieldLabel}>Provider</label>
              <select
                required value={pProviderId} onChange={(e) => setPProviderId(e.target.value)}
                className={fieldInput}
              >
                <option value="">Seleziona...</option>
                {enabledProviders.map((p) => (
                  <option key={p.id} value={p.id}>{p.name}</option>
                ))}
              </select>
            </div>
            <div className="space-y-1">
              <label className={fieldLabel}>Nome prodotto</label>
              <input
                required value={pName} onChange={(e) => setPName(e.target.value)}
                className={fieldInput}
              />
            </div>
            <div className="space-y-1 sm:col-span-2">
              <label className={fieldLabel}>Descrizione</label>
              <textarea
                value={pDescription} onChange={(e) => setPDescription(e.target.value)} rows={2}
                className={fieldInput}
              />
            </div>
            <div className="space-y-1">
              <label className={fieldLabel}>URL immagine</label>
              <input
                value={pImageUrl} onChange={(e) => setPImageUrl(e.target.value)}
                className={fieldInput}
              />
            </div>
            <div className="space-y-1">
              <label className={fieldLabel}>
                Link originale (solo admin, mai mostrato al cliente)
              </label>
              <input
                value={pExternalUrl} onChange={(e) => setPExternalUrl(e.target.value)}
                className={fieldInput}
              />
            </div>
            <div className="space-y-1">
              <label className={fieldLabel}>Prezzo di vendita (&euro;)</label>
              <input
                required inputMode="decimal" value={pPrice} onChange={(e) => setPPrice(e.target.value)}
                className={fieldInput}
              />
            </div>
            <div className="space-y-1">
              <label className={fieldLabel}>
                % massima pagabile in SosnetCash
              </label>
              <input
                type="number" min={0} max={99} value={pCreditPct} onChange={(e) => setPCreditPct(e.target.value)}
                className={fieldInput}
              />
            </div>
            <div className="sm:col-span-2">
              <ProductCategoriesField shop="aliexpress" value={pCategoryIds} onChange={setPCategoryIds} />
            </div>
            <div className="sm:col-span-2">
              <button
                type="submit" disabled={productCreateLoading}
                className="px-4 py-2 rounded-xl bg-brand-600 hover:bg-brand-500 text-xs font-semibold text-white transition cursor-pointer disabled:opacity-50"
              >
                {productCreateLoading ? "..." : "Salva prodotto"}
              </button>
            </div>
          </form>
          {productCreateError && (
            <div className="mt-3 p-3 rounded-lg bg-danger-500/10 border border-danger-500/20 text-danger-400 text-xs">{productCreateError}</div>
          )}
        </div>
      )}

      <div className="panel rounded-3xl p-6 sm:p-7">
        {productsError && <p className="pb-3 text-sm text-danger-400">Impossibile caricare i prodotti.</p>}
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr>
                <th className="px-4 py-3">Articolo</th>
                <th className="px-4 py-3 text-right">Prezzo al cliente</th>
                <th className="px-4 py-3">Vetrina</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {products === undefined ? (
                <EmptyRow colSpan={4} text="Caricamento..." />
              ) : products.length === 0 ? (
                <EmptyRow colSpan={4} text="Nessun prodotto ancora." />
              ) : (
                products.map((p) => (
                  <tr key={p.id}>
                    <td className="px-4 py-3 max-w-[380px]">
                      <div className="flex items-center gap-3 min-w-0">
                        <div className="h-12 w-12 shrink-0 overflow-hidden rounded-2xl ring-1 ring-white/15">
                          <ProductThumbnail imageUrl={p.image_url} alt={p.name} className="h-full w-full object-cover" iconClassName="w-6 h-6 text-brand-300/60" />
                        </div>
                        <Stack
                          title={p.name}
                          detail={
                            <>
                              {p.provider_name} · {when(p.created_at)}
                              {(p.category_ids ?? []).length > 0 && ` · ${(p.category_ids ?? []).length} categorie`}
                            </>
                          }
                        />
                      </div>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <Figure
                        value={euro(p.price_cents)}
                        detail={`fino al ${p.credit_discount_percentage}% in SosnetCash`}
                        ratio={p.credit_discount_percentage / 100}
                      />
                    </td>
                    <td className="px-4 py-3">
                      <Chip tone={p.status === "ACTIVE" ? "ok" : "muted"}>
                        {p.status === "ACTIVE" ? "Attivo" : "Disattivato"}
                      </Chip>
                    </td>
                    <td className="px-4 py-3">
                      <RowActions>
                        <button onClick={() => setCategoriesTarget(p)} className="act">
                          Categorie
                        </button>
                        <button
                          onClick={() => handleToggleProduct(p)}
                          disabled={productToggleId === p.id}
                          className="act"
                        >
                          {productToggleId === p.id ? "..." : p.status === "ACTIVE" ? "Disattiva" : "Riattiva"}
                        </button>
                      </RowActions>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {categoriesTarget && (
        <CategoriesModal product={categoriesTarget} onClose={() => setCategoriesTarget(null)} />
      )}
    </div>
  );
}

/**
 * Categories of a hand-entered product: the AliExpress Marketplace ones,
 * since customers do not distinguish the two lists.
 */
function CategoriesModal({ product, onClose }: { product: ImportedProductAdminRead; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [categoryIds, setCategoryIds] = useState<string[]>(product.category_ids ?? []);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    setSaving(true);
    setError(null);
    try {
      if (!sameCategorySelection(categoryIds, product.category_ids ?? [])) {
        await saveProductCategories("aliexpress", product.id, categoryIds);
        await queryClient.invalidateQueries({ queryKey: ["shop-categories", "aliexpress"] });
        await queryClient.invalidateQueries({ queryKey: ["admin", "imported-products"] });
      }
      onClose();
    } catch (err: any) {
      setError(err.message || "Impossibile salvare le categorie.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-fade-in">
      <div className="w-full max-w-md panel rounded-3xl p-7 bg-surface-950 pop space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-xl font-black tracking-tight text-white">Categorie di &ldquo;{product.name}&rdquo;</h3>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-white/10 text-surface-400 cursor-pointer" aria-label="Chiudi">✕</button>
        </div>
        <ProductCategoriesField shop="aliexpress" value={categoryIds} onChange={setCategoryIds} />
        {error && <div className="p-3 rounded-lg bg-danger-500/10 border border-danger-500/20 text-danger-400 text-xs">{error}</div>}
        <div className="flex justify-end gap-2">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-xl bg-white/5 hover:bg-white/10 text-xs font-semibold text-surface-300 border border-white/10 transition cursor-pointer"
          >
            Annulla
          </button>
          <button
            onClick={save}
            disabled={saving}
            className="px-4 py-2 rounded-xl bg-brand-600 hover:bg-brand-500 text-xs font-semibold text-white transition cursor-pointer disabled:opacity-50"
          >
            {saving ? "Salvataggio..." : "Salva"}
          </button>
        </div>
      </div>
    </div>
  );
}
