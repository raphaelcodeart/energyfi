"use client";

import { useState, type CSSProperties } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { PhotoUpload } from "@/components/photo-upload";
import { ProductThumbnail } from "@/components/product-thumbnail";
import { Chip, Figure, KpiTile, RowActions } from "@/components/ui/data-cells";
import { friendlyApiError } from "@/lib/api-error";
import { useMarketplaceConfig } from "@/components/marketplace-rules-card";
import { ProductCategoriesField, saveProductCategories, sameCategorySelection, ManageCategoriesButton } from "@/components/shop-categories-card";
import type { ProductCatalogRead, ProductCategoryRead, ProductRead, ProductVersionRead, ShopKey } from "@/lib/types";

const ENERGY_LABELS: Record<string, string> = {
  ELECTRICITY: "Luce",
  GAS: "Gas",
  DUAL_FUEL: "Dual Fuel",
};

const PRODUCT_TYPE_LABELS: Record<string, string> = {
  ENERGY_CONTRACT: "Contratto Energia",
  DIGITAL: "Digitale",
  PHYSICAL: "Fisico",
  SUBSCRIPTION: "Abbonamento",
};

// Who a product may be sold to. Legacy values (PMI, ENERGY_INTENSIVE,
// SOLE_PROPRIETOR) still parse server-side and map to BUSINESS; see
// catalog/pricing.py.
const CUSTOMER_TYPE_LABELS: Record<string, string> = {
  BOTH: "Privati e aziende",
  PRIVATE: "Solo privati",
  BUSINESS: "Solo aziende / P.IVA",
};

const LEGACY_CUSTOMER_TYPE_LABELS: Record<string, string> = {
  SOLE_PROPRIETOR: "Solo aziende / P.IVA",
  PMI: "Solo aziende / P.IVA",
  CONDOMINIUM: "Solo aziende / P.IVA",
  ENERGY_INTENSIVE: "Solo aziende / P.IVA",
};

function customerTypeLabel(value: string): string {
  return CUSTOMER_TYPE_LABELS[value] ?? LEGACY_CUSTOMER_TYPE_LABELS[value] ?? value;
}

const CATEGORY_LABELS: Record<string, string> = {
  INTERNAL: "Interno SOSNET",
  DROPSHIPPING: "Fai la spesa con Sosnet",
  PARTNER: "Partner / collaboratore",
};

// Each own-catalog section is a separate shop for categories: "Casa" under
// Offerte Sosnet and "Casa" under Partner are different categories.
const SHOP_KEY_BY_CATEGORY: Record<string, ShopKey> = {
  INTERNAL: "internal",
  PARTNER: "partner",
  DROPSHIPPING: "dropshipping",
};

function euro(cents: number): string {
  return (cents / 100).toLocaleString("it-IT", { style: "currency", currency: "EUR" });
}

function euroToCents(value: string): number {
  const parsed = parseFloat(value.replace(",", "."));
  return Number.isFinite(parsed) ? Math.round(parsed * 100) : 0;
}

function centsToEuroInput(cents: number): string {
  return (cents / 100).toFixed(2);
}

/** Network margin as a figure; the meter shows its share of the net price. */
function marginFigure(v: ProductVersionRead | null): { value: string; detail: string; ratio: number | null } | null {
  if (!v?.margin_type) return null;
  if (v.margin_type === "PERCENTAGE") {
    const pct = Number(v.margin_percentage ?? 0);
    return { value: `${pct.toLocaleString("it-IT")}%`, detail: "dell'importo netto", ratio: pct / 100 };
  }
  const amount = v.margin_amount_cents ?? 0;
  const base = v.contract_net_amount_cents || v.base_price_cents;
  return { value: euro(amount), detail: "importo fisso", ratio: base > 0 ? amount / base : null };
}

async function fetchProducts(): Promise<ProductCatalogRead[]> {
  const res = await fetch("/api/proxy/products");
  if (!res.ok) throw new Error("Impossibile caricare i prodotti.");
  return res.json();
}

async function fetchCommercialCategories(): Promise<ProductCategoryRead[]> {
  const res = await fetch("/api/proxy/commercial/categories");
  if (!res.ok) throw new Error("Impossibile caricare le categorie commerciali.");
  return res.json();
}

interface ProductFormState {
  name: string;
  description: string;
  imageUrl: string;
  basePriceEuro: string;
  initialFeeEuro: string;
  recurringFeeEuro: string;
  billingPeriod: string;
  vatPercentage: string;
  contractDurationMonths: string;
  // Margin a sale makes available to the network: "" = not configured (the
  // contract cannot activate until it is), FIXED = amount, PERCENTAGE = % of
  // the net amount. The Split Plan decides how it is divided.
  marginType: "" | "FIXED" | "PERCENTAGE";
  marginEuro: string;
  marginPercentage: string;
  // COMMERCIAL category (Energy, TLC, ...) for plans and reports; lives on the
  // product, not the version.
  commercialCategoryId: string;
  // 0-100, kept as a string so the input can be empty while typing. Only
  // meaningful for non-INTERNAL products (catalog/service.py::_clamp_credit_discount).
  creditDiscountPercentage: string;
  // Whether "riscuoti subito cashback" is offered at checkout; forced off for
  // INTERNAL products (catalog/service.py::_clamp_cashback_enabled).
  cashbackEnabled: boolean;
  // INTERNAL-only counterparts of the two above. 0-100: share of a paid
  // contract's gross (VAT included) returned as SosnetCash, automatically and
  // with no surcharge (catalog/service.py::_clamp_contract_cashback).
  contractCashbackPercentage: string;
  // Shop categories within the product's section. Not on the ProductVersion:
  // saved by their own call (PUT /shop-categories/assignments), only if changed.
  categoryIds: string[];
}

/**
 * Margin columns as the server expects them: all three together, so
 * switching between fixed and percentage leaves no stale value.
 */
function marginPayload(form: ProductFormState) {
  if (!form.marginType) return {};
  return {
    margin_type: form.marginType,
    margin_amount_cents: form.marginType === "FIXED" ? euroToCents(form.marginEuro) : null,
    margin_percentage: form.marginType === "PERCENTAGE" ? form.marginPercentage.replace(",", ".") || "0" : null,
  };
}

const EMPTY_FORM: ProductFormState = {
  name: "",
  description: "",
  imageUrl: "",
  basePriceEuro: "",
  initialFeeEuro: "0",
  recurringFeeEuro: "0",
  billingPeriod: "MONTHLY",
  vatPercentage: "10",
  contractDurationMonths: "12",
  marginType: "",
  marginEuro: "",
  marginPercentage: "",
  commercialCategoryId: "",
  creditDiscountPercentage: "0",
  cashbackEnabled: false,
  contractCashbackPercentage: "0",
  categoryIds: [],
};

function ProductFormFields({
  form,
  onChange,
  commercialCategories,
  category,
}: {
  form: ProductFormState;
  onChange: (patch: Partial<ProductFormState>) => void;
  commercialCategories: ProductCategoryRead[];
  /**
   * Whether the "sconto in crediti" field is usable: INTERNAL products are
   * never discountable in wallet credit.
   */
  category: string;
}) {
  return (
    <>
      <div className="space-y-1">
        <label className="text-xs font-semibold text-surface-300 uppercase block">Nome</label>
        <input required value={form.name} onChange={(e) => onChange({ name: e.target.value })}
          className="w-full rounded-xl field px-3 py-2 text-sm focus:border-brand-500" />
      </div>

      <div className="space-y-1">
        <label className="text-xs font-semibold text-surface-300 uppercase block">Descrizione</label>
        <textarea rows={2} value={form.description} onChange={(e) => onChange({ description: e.target.value })}
          placeholder="Descrizione visibile ai clienti nel marketplace..."
          className="w-full rounded-xl field px-3 py-2 text-sm focus:border-brand-500 resize-none" />
      </div>

      <div className="space-y-1">
        <label className="text-xs font-semibold text-surface-300 uppercase block">Foto prodotto (URL immagine)</label>
        <div className="flex items-center gap-3">
          {form.imageUrl && (
            // eslint-disable-next-line @next/next/no-img-element -- externally-hosted, variable-source image (URL or uploaded)
            <img src={form.imageUrl} alt="" className="w-12 h-12 rounded-lg object-cover border border-white/10 shrink-0" />
          )}
          <input value={form.imageUrl} onChange={(e) => onChange({ imageUrl: e.target.value })}
            placeholder="https://..."
            className="w-full rounded-xl field px-3 py-2 text-sm focus:border-brand-500" />
        </div>
      </div>

      <ProductCategoriesField
        shop={SHOP_KEY_BY_CATEGORY[category] ?? "internal"}
        value={form.categoryIds}
        onChange={(categoryIds) => onChange({ categoryIds })}
      />

      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-1">
          <label className="text-xs font-semibold text-surface-300 uppercase block">Prezzo base (EUR)</label>
          <input required inputMode="decimal" value={form.basePriceEuro} onChange={(e) => onChange({ basePriceEuro: e.target.value })}
            placeholder="18.00"
            className="w-full rounded-xl field px-3 py-2 text-sm focus:border-brand-500" />
        </div>
        <div className="space-y-1">
          <label className="text-xs font-semibold text-surface-300 uppercase block">Aliquota IVA (%)</label>
          <input inputMode="decimal" value={form.vatPercentage} onChange={(e) => onChange({ vatPercentage: e.target.value })}
            placeholder="10"
            className="w-full rounded-xl field px-3 py-2 text-sm focus:border-brand-500" />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-1">
          <label className="text-xs font-semibold text-surface-300 uppercase block">Fee iniziale (EUR)</label>
          <input inputMode="decimal" value={form.initialFeeEuro} onChange={(e) => onChange({ initialFeeEuro: e.target.value })}
            className="w-full rounded-xl field px-3 py-2 text-sm focus:border-brand-500" />
        </div>
        <div className="space-y-1">
          <label className="text-xs font-semibold text-surface-300 uppercase block">Fee ricorrente (EUR)</label>
          <input inputMode="decimal" value={form.recurringFeeEuro} onChange={(e) => onChange({ recurringFeeEuro: e.target.value })}
            className="w-full rounded-xl field px-3 py-2 text-sm focus:border-brand-500" />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-1">
          <label className="text-xs font-semibold text-surface-300 uppercase block">Periodicità fatturazione</label>
          <select value={form.billingPeriod} onChange={(e) => onChange({ billingPeriod: e.target.value })}
            className="w-full rounded-xl field px-3 py-2.5 text-sm bg-surface-900 focus:border-brand-500">
            <option value="MONTHLY">Mensile</option>
            <option value="QUARTERLY">Trimestrale</option>
            <option value="ANNUAL">Annuale</option>
          </select>
        </div>
        <div className="space-y-1">
          <label className="text-xs font-semibold text-surface-300 uppercase block">Durata contratto (mesi)</label>
          <input inputMode="numeric" value={form.contractDurationMonths}
            onChange={(e) => onChange({ contractDurationMonths: e.target.value })}
            placeholder="Vuoto = nessun rinnovo"
            className="w-full rounded-xl field px-3 py-2 text-sm focus:border-brand-500" />
          <p className="text-[10px] text-surface-500">Lascia vuoto per prodotti senza rinnovo (digitali, fisici, acquisti una tantum).</p>
        </div>
      </div>

      <div className="space-y-1">
        <label className="text-xs font-semibold text-surface-300 uppercase block">
          Sconto pagabile in crediti (%)
        </label>
        {category === "INTERNAL" ? (
          <p className="text-[10px] text-surface-500">
            Non disponibile per i prodotti Interno SOSNET -- pagabili solo in bonifico.
          </p>
        ) : (
          <>
            <input
              inputMode="numeric"
              value={form.creditDiscountPercentage}
              onChange={(e) => onChange({ creditDiscountPercentage: e.target.value })}
              placeholder="0"
              className="w-full max-w-[140px] rounded-xl field px-3 py-2 text-sm focus:border-brand-500"
            />
            <p className="text-[10px] text-surface-500">
              Quanta parte del prezzo un cliente può pagare con i crediti wallet nel checkout -- il resto resta bonifico.
            </p>
          </>
        )}
      </div>

      <div className="space-y-1">
        <label className="text-xs font-semibold text-surface-300 uppercase block">
          Cashback al checkout
        </label>
        {category === "INTERNAL" ? (
          <p className="text-[10px] text-surface-500">
            Non disponibile per i prodotti Interno SOSNET.
          </p>
        ) : (
          <>
            <label className="flex items-center gap-2.5 text-xs text-surface-300 cursor-pointer">
              <input
                type="checkbox"
                checked={form.cashbackEnabled}
                onChange={(e) => onChange({ cashbackEnabled: e.target.checked })}
                className="w-4 h-4 rounded border-white/20 accent-brand-500"
              />
              Abilita &ldquo;riscuoti subito cashback&rdquo; per questo prodotto
            </label>
            <p className="text-[10px] text-surface-500">
              Se attivo, il cliente può scegliere in fase di acquisto di pagare il {" "}
              <span className="font-mono">5%</span> in più per ricevere l&apos;intero importo pagato (100% + 5%)
              accreditato subito come SosnetCash sul suo wallet, una volta confermato il pagamento.
            </p>
          </>
        )}
      </div>

      {category === "INTERNAL" && (
        <>
          <div className="space-y-1">
            <label className="text-xs font-semibold text-surface-300 uppercase block">
              Cashback automatico sul contratto (%)
            </label>
            <input
              inputMode="numeric"
              value={form.contractCashbackPercentage}
              onChange={(e) => onChange({ contractCashbackPercentage: e.target.value })}
              placeholder="0"
              className="w-full max-w-[140px] rounded-xl field px-3 py-2 text-sm focus:border-brand-500"
            />
            <p className="text-[10px] text-surface-500">
              Percentuale dell&apos;importo totale pagato (IVA inclusa) che torna al cliente come SosnetCash
              quando il contratto risulta pagato. <strong>Automatico e senza il 5% aggiuntivo</strong>: sui
              servizi SOSNET e sulla formazione il cliente non paga nulla in più per ottenere il credito,
              a differenza del riscatto fatture dei partner esterni. <span className="font-mono">0</span> = nessun
              cashback.
            </p>
          </div>

        </>
      )}

      <div className="space-y-2 pt-2 border-t border-white/5">
        <label className="text-xs font-semibold text-surface-300 uppercase block">
          Margine per la rete
        </label>
        <p className="text-[10px] text-surface-500">
          Quanto una vendita di questo prodotto mette a disposizione di chi vende e della sua rete. Come si divide lo decidono
          gli <strong>Split Plan</strong>. Senza margine, un contratto di questo prodotto non può essere approvato.
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
          <select
            value={form.marginType}
            onChange={(e) => onChange({ marginType: e.target.value as ProductFormState["marginType"] })}
            className="w-full rounded-xl field px-3 py-2 text-sm focus:border-brand-500"
          >
            <option value="">Non configurato</option>
            <option value="FIXED">Importo fisso</option>
            <option value="PERCENTAGE">% dell&apos;importo netto</option>
          </select>
          {form.marginType === "FIXED" && (
            <input inputMode="decimal" value={form.marginEuro} onChange={(e) => onChange({ marginEuro: e.target.value })} placeholder="150.00 EUR" className="w-full rounded-xl field px-3 py-2 text-sm focus:border-brand-500" />
          )}
          {form.marginType === "PERCENTAGE" && (
            <input inputMode="decimal" value={form.marginPercentage} onChange={(e) => onChange({ marginPercentage: e.target.value })} placeholder="30 %" className="w-full rounded-xl field px-3 py-2 text-sm focus:border-brand-500" />
          )}
        </div>
        <label className="text-xs font-semibold text-surface-300 uppercase block pt-2">
          Categoria commerciale
        </label>
        <select
          value={form.commercialCategoryId}
          onChange={(e) => onChange({ commercialCategoryId: e.target.value })}
          className="w-full rounded-xl field px-3 py-2 text-sm focus:border-brand-500"
        >
          <option value="">Nessuna</option>
          {commercialCategories.map((c) => (
            <option key={c.id} value={c.id}>{c.name}{c.requires_supply_point ? " (con punto di fornitura)" : ""}</option>
          ))}
        </select>
        <p className="text-[10px] text-surface-500">
          Un piano per categoria vale per tutti i suoi prodotti che non hanno un piano proprio.
        </p>
      </div>
    </>
  );
}

export function AdminProductsPanel() {
  const queryClient = useQueryClient();
  const { data: products, error: loadError } = useQuery({
    queryKey: ["admin", "products"],
    queryFn: fetchProducts,
  });
  const { data: commercialCategories = [] } = useQuery({
    queryKey: ["commercial", "categories"],
    queryFn: fetchCommercialCategories,
  });

  const [showCreate, setShowCreate] = useState(false);
  const [isDuplicating, setIsDuplicating] = useState(false);
  const [code, setCode] = useState("");
  const [productType, setProductType] = useState("ENERGY_CONTRACT");
  const [energyType, setEnergyType] = useState("ELECTRICITY");
  const [customerType, setCustomerType] = useState("BOTH");
  const [category, setCategory] = useState("INTERNAL");
  const [createForm, setCreateForm] = useState<ProductFormState>(EMPTY_FORM);
  const [createLoading, setCreateLoading] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const [editingProduct, setEditingProduct] = useState<ProductCatalogRead | null>(null);
  // Lives on the Product, not the ProductVersion, so it is saved by its own PATCH below.
  const [editCustomerType, setEditCustomerType] = useState("BOTH");
  const [editForm, setEditForm] = useState<ProductFormState>(EMPTY_FORM);
  const [editLoading, setEditLoading] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);

  // Shop sections can be renamed; use the names customers see.
  const { data: marketplaceConfig } = useMarketplaceConfig();
  const shopsForCategories: { key: ShopKey; label: string }[] = [
    { key: "internal", label: marketplaceConfig?.sections.internal.label ?? "Interno SOSNET" },
    { key: "partner", label: marketplaceConfig?.sections.partner.label ?? "Partner / collaboratore" },
    { key: "dropshipping", label: marketplaceConfig?.sections.dropshipping.label ?? "Fai la spesa con Sosnet" },
  ];

  // Section pill filter (client side only).
  const [sectionFilter, setSectionFilter] = useState<"ALL" | "INTERNAL" | "PARTNER" | "DROPSHIPPING">("ALL");

  const [deletingProduct, setDeletingProduct] = useState<ProductCatalogRead | null>(null);
  const [deleteLoading, setDeleteLoading] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  function openDuplicate(product: ProductCatalogRead) {
    const v = product.current_version;
    setCode(`${product.code}-COPY`);
    setProductType(product.product_type);
    setEnergyType(product.energy_type ?? "ELECTRICITY");
    setCustomerType(product.customer_type);
    setCategory(product.category);
    setCreateForm({
      name: v ? `${v.name} (copia)` : "",
      description: v?.description ?? "",
      imageUrl: v?.image_url ?? "",
      basePriceEuro: v ? centsToEuroInput(v.base_price_cents) : "",
      initialFeeEuro: v ? centsToEuroInput(v.initial_fee_cents) : "0",
      recurringFeeEuro: v ? centsToEuroInput(v.recurring_fee_cents) : "0",
      billingPeriod: v?.billing_period ?? "MONTHLY",
      vatPercentage: v?.vat_percentage != null ? String(v.vat_percentage) : "",
      contractDurationMonths: v?.contract_duration_months != null ? String(v.contract_duration_months) : "",
      marginType: (v?.margin_type ?? "") as ProductFormState["marginType"],
      marginEuro: v?.margin_amount_cents != null ? centsToEuroInput(v.margin_amount_cents) : "",
      marginPercentage: v?.margin_percentage != null ? String(Number(v.margin_percentage)) : "",
      commercialCategoryId: product.commercial_category_id ?? "",
      creditDiscountPercentage: v ? String(v.credit_discount_percentage) : "0",
      cashbackEnabled: v?.cashback_enabled ?? false,
      contractCashbackPercentage: v ? String(v.contract_cashback_percentage) : "0",
      categoryIds: product.category_ids ?? [],
    });
    setCreateError(null);
    setIsDuplicating(true);
    setShowCreate(true);
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setCreateLoading(true);
    setCreateError(null);
    try {
      const res = await fetch("/api/proxy/products", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          code,
          product_type: productType,
          energy_type: productType === "ENERGY_CONTRACT" ? energyType : null,
          customer_type: customerType,
          category,
          name: createForm.name,
          description: createForm.description,
          image_url: createForm.imageUrl.trim() || null,
          base_price_cents: euroToCents(createForm.basePriceEuro),
          initial_fee_cents: euroToCents(createForm.initialFeeEuro),
          recurring_fee_cents: euroToCents(createForm.recurringFeeEuro),
          billing_period: createForm.billingPeriod,
          vat_percentage: createForm.vatPercentage.trim() ? parseFloat(createForm.vatPercentage) : null,
          contract_duration_months: createForm.contractDurationMonths.trim()
            ? parseInt(createForm.contractDurationMonths, 10)
            : null,
          ...marginPayload(createForm),
          commercial_category_id: createForm.commercialCategoryId || null,
          credit_discount_percentage: category === "INTERNAL" ? 0 : (parseInt(createForm.creditDiscountPercentage, 10) || 0),
          cashback_enabled: category === "INTERNAL" ? false : createForm.cashbackEnabled,
          // Mirrors the clamps in catalog/service.py; the server enforces them anyway.
          contract_cashback_percentage: category === "INTERNAL" ? (parseInt(createForm.contractCashbackPercentage, 10) || 0) : 0,
        }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));

      // Categories are assigned afterwards, and only if at least one was chosen.
      const created: ProductRead = await res.json();
      if (createForm.categoryIds.length > 0 && created?.id) {
        const shop = SHOP_KEY_BY_CATEGORY[category] ?? "internal";
        await saveProductCategories(shop, created.id, createForm.categoryIds);
        await queryClient.invalidateQueries({ queryKey: ["shop-categories", shop] });
      }

      setShowCreate(false);
      setIsDuplicating(false);
      setCode("");
      setCreateForm(EMPTY_FORM);
      await queryClient.invalidateQueries({ queryKey: ["admin", "products"] });
    } catch (err: any) {
      setCreateError(err.message || "Impossibile creare il prodotto.");
    } finally {
      setCreateLoading(false);
    }
  }

  function openEdit(product: ProductCatalogRead) {
    const v = product.current_version;
    setEditForm({
      name: v?.name ?? "",
      description: v?.description ?? "",
      imageUrl: v?.image_url ?? "",
      basePriceEuro: v ? centsToEuroInput(v.base_price_cents) : "",
      initialFeeEuro: v ? centsToEuroInput(v.initial_fee_cents) : "0",
      recurringFeeEuro: v ? centsToEuroInput(v.recurring_fee_cents) : "0",
      billingPeriod: v?.billing_period ?? "MONTHLY",
      vatPercentage: v?.vat_percentage != null ? String(v.vat_percentage) : "",
      contractDurationMonths: v?.contract_duration_months != null ? String(v.contract_duration_months) : "",
      marginType: (v?.margin_type ?? "") as ProductFormState["marginType"],
      marginEuro: v?.margin_amount_cents != null ? centsToEuroInput(v.margin_amount_cents) : "",
      marginPercentage: v?.margin_percentage != null ? String(Number(v.margin_percentage)) : "",
      commercialCategoryId: product.commercial_category_id ?? "",
      creditDiscountPercentage: v ? String(v.credit_discount_percentage) : "0",
      cashbackEnabled: v?.cashback_enabled ?? false,
      contractCashbackPercentage: v ? String(v.contract_cashback_percentage) : "0",
      categoryIds: product.category_ids ?? [],
    });
    setEditCustomerType(
      ["PRIVATE", "BUSINESS", "BOTH"].includes(product.customer_type) ? product.customer_type : "BUSINESS"
    );
    setEditError(null);
    setEditingProduct(product);
  }

  async function handleEditSave(e: React.FormEvent) {
    e.preventDefault();
    if (!editingProduct?.current_version) return;
    setEditLoading(true);
    setEditError(null);
    try {
      const res = await fetch(`/api/proxy/products/versions/${editingProduct.current_version.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: editForm.name,
          description: editForm.description,
          image_url: editForm.imageUrl.trim() || null,
          base_price_cents: euroToCents(editForm.basePriceEuro),
          initial_fee_cents: euroToCents(editForm.initialFeeEuro),
          recurring_fee_cents: euroToCents(editForm.recurringFeeEuro),
          vat_percentage: editForm.vatPercentage.trim() ? parseFloat(editForm.vatPercentage) : null,
          contract_duration_months: editForm.contractDurationMonths.trim()
            ? parseInt(editForm.contractDurationMonths, 10)
            : null,
          ...marginPayload(editForm),
          credit_discount_percentage: editingProduct.category === "INTERNAL" ? 0 : (parseInt(editForm.creditDiscountPercentage, 10) || 0),
          cashback_enabled: editingProduct.category === "INTERNAL" ? false : editForm.cashbackEnabled,
          contract_cashback_percentage: editingProduct.category === "INTERNAL" ? (parseInt(editForm.contractCashbackPercentage, 10) || 0) : 0,
        }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));

      // Audience is a Product field: saved by a second call, only when changed.
      const categoryChanged = (editForm.commercialCategoryId || null) !== (editingProduct.commercial_category_id ?? null);
      if (editCustomerType !== editingProduct.customer_type || categoryChanged) {
        const audienceRes = await fetch(`/api/proxy/products/${editingProduct.id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            customer_type: editCustomerType,
            ...(categoryChanged && editForm.commercialCategoryId ? { commercial_category_id: editForm.commercialCategoryId } : {}),
          }),
        });
        if (!audienceRes.ok) throw new Error(await friendlyApiError(audienceRes));
      }

      // As on creation: call the categories endpoint only if the selection changed.
      if (!sameCategorySelection(editForm.categoryIds, editingProduct.category_ids ?? [])) {
        const shop = SHOP_KEY_BY_CATEGORY[editingProduct.category] ?? "internal";
        await saveProductCategories(shop, editingProduct.id, editForm.categoryIds);
        await queryClient.invalidateQueries({ queryKey: ["shop-categories", shop] });
      }

      setEditingProduct(null);
      await queryClient.invalidateQueries({ queryKey: ["admin", "products"] });
    } catch (err: any) {
      setEditError(err.message || "Impossibile salvare le modifiche.");
    } finally {
      setEditLoading(false);
    }
  }

  async function handleDeleteProduct() {
    if (!deletingProduct) return;
    setDeleteLoading(true);
    setDeleteError(null);
    try {
      const res = await fetch(`/api/proxy/products/${deletingProduct.id}`, { method: "DELETE" });
      if (!res.ok) throw new Error(await friendlyApiError(res, "Impossibile eliminare il prodotto."));
      setDeletingProduct(null);
      await queryClient.invalidateQueries({ queryKey: ["admin", "products"] });
    } catch (err: any) {
      setDeleteError(err.message || "Impossibile eliminare il prodotto.");
    } finally {
      setDeleteLoading(false);
    }
  }

  const deleteConfirmModal = deletingProduct && (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-fade-in">
      <div className="w-full max-w-md panel rounded-3xl p-7 border-white/10 bg-surface-950 pop">
        <h3 className="text-xl font-black tracking-tight text-white mb-2">Elimina prodotto</h3>
        <p className="text-xs text-surface-400 mb-4">
          Stai per eliminare definitivamente il prodotto{" "}
          <span className="font-semibold text-surface-300">
            &quot;{deletingProduct.current_version?.name ?? deletingProduct.code}&quot;
          </span>{" "}
          e tutte le sue versioni. L&apos;operazione non può essere annullata. Se il prodotto ha contratti
          associati, l&apos;eliminazione verrà rifiutata: in quel caso puoi solo disattivarlo.
        </p>
        {deleteError && <p className="text-xs text-danger-400 mb-3">{deleteError}</p>}
        <div className="flex justify-end gap-3">
          <button
            onClick={() => { setDeletingProduct(null); setDeleteError(null); }}
            className="px-4 py-2 rounded-xl bg-white/5 hover:bg-white/10 text-xs font-semibold text-surface-300 border border-white/5 transition cursor-pointer"
          >
            Annulla
          </button>
          <button
            onClick={handleDeleteProduct}
            disabled={deleteLoading}
            className="px-4 py-2 rounded-xl bg-danger-600 hover:bg-danger-500 text-xs font-semibold text-white transition cursor-pointer disabled:opacity-50"
          >
            {deleteLoading ? "Eliminazione..." : "Elimina definitivamente"}
          </button>
        </div>
      </div>
    </div>
  );

  const list = products ?? [];
  const visibleProducts = sectionFilter === "ALL" ? list : list.filter((p) => p.category === sectionFilter);
  const activeCount = list.filter((p) => p.status === "ACTIVE").length;
  const withMarginCount = list.filter((p) => p.current_version?.margin_type).length;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="kpi-label">Catalogo</div>
          <h2 className="mt-1 text-xl font-black tracking-tight text-white">Prodotti in vetrina</h2>
          <p className="mt-1 text-sm text-surface-400">
            Cataloghi luce, gas, dual fuel ed Energia Plus venduti in marketplace.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {/* One button for all three sections, with a section picker inside the dialog. */}
          <ManageCategoriesButton shops={shopsForCategories} />
          <button
            onClick={() => {
              setCode("");
              setProductType("ENERGY_CONTRACT");
              setEnergyType("ELECTRICITY");
              setCustomerType("PRIVATE");
              setCategory("INTERNAL");
              setCreateForm(EMPTY_FORM);
              setCreateError(null);
              setIsDuplicating(false);
              setShowCreate(true);
            }}
            className="act act-primary shrink-0"
          >
            + Nuovo prodotto
          </button>
        </div>
      </div>

      {loadError && <p className="text-sm text-danger-400">Impossibile caricare i prodotti.</p>}

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 stagger">
        <div style={{ "--i": 0 } as CSSProperties}>
          <KpiTile label="In catalogo" value={products ? list.length : "—"} hint="Tutte le sezioni" onClick={() => setSectionFilter("ALL")} active={sectionFilter === "ALL"} />
        </div>
        <div style={{ "--i": 1 } as CSSProperties}>
          <KpiTile label="Attivi" value={products ? activeCount : "—"} hint={products && list.length > 0 ? `${Math.round((activeCount / list.length) * 100)}% del catalogo` : undefined} />
        </div>
        <div style={{ "--i": 2 } as CSSProperties}>
          <KpiTile label="Con margine" value={products ? withMarginCount : "—"} hint={products ? `${list.length - withMarginCount} da configurare` : undefined} />
        </div>
        <div style={{ "--i": 3 } as CSSProperties}>
          <KpiTile label="Sezioni" value={Object.keys(CATEGORY_LABELS).length} hint="Interno, partner, spesa" />
        </div>
      </div>

      <div className="subnav">
        {(["ALL", "INTERNAL", "PARTNER", "DROPSHIPPING"] as const).map((key) => {
          const count = key === "ALL" ? list.length : list.filter((p) => p.category === key).length;
          return (
            <button
              key={key}
              type="button"
              className="subnav-pill"
              data-active={sectionFilter === key}
              onClick={() => setSectionFilter(key)}
            >
              {key === "ALL" ? "Tutti" : CATEGORY_LABELS[key]}
              <span className="text-[10px] opacity-70 tabular-nums">{count}</span>
            </button>
          );
        })}
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-5 stagger">
        {products === undefined ? (
          <p className="text-sm text-surface-400 col-span-full text-center py-10">Caricamento...</p>
        ) : visibleProducts.length === 0 ? (
          <div className="panel rounded-3xl col-span-full flex flex-col items-center justify-center gap-3 py-14 text-center">
            <span className="orb float-soft" aria-hidden="true">
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />
              </svg>
            </span>
            <p className="text-sm text-surface-300">
              {list.length === 0 ? "Nessun prodotto nel catalogo." : "Nessun prodotto in questa sezione."}
            </p>
          </div>
        ) : (
          visibleProducts.map((p, index) => {
            const v = p.current_version;
            const typeLabel = p.product_type === "ENERGY_CONTRACT"
              ? (p.energy_type ? ENERGY_LABELS[p.energy_type] ?? p.energy_type : "Energia")
              : PRODUCT_TYPE_LABELS[p.product_type] ?? p.product_type;
            const margin = marginFigure(v);
            return (
              <div
                key={p.id}
                style={{ "--i": index } as CSSProperties}
                className="panel group relative flex flex-col overflow-hidden rounded-3xl"
              >
                <div className="relative h-40 overflow-hidden">
                  <div className="h-full w-full transition duration-500 group-hover:scale-105">
                    <ProductThumbnail
                      imageUrl={v?.image_url}
                      alt={v?.name ?? p.code}
                      iconClassName="w-12 h-12 text-brand-300/50"
                    />
                  </div>
                  <div className="pointer-events-none absolute inset-0 bg-gradient-to-t from-black/70 via-black/10 to-transparent" />
                  <div className="absolute left-3 top-3 flex flex-wrap items-center gap-1.5 rounded-full bg-black/60 p-1 backdrop-blur-md">
                    <Chip tone="info">{typeLabel}</Chip>
                    <Chip tone={p.status === "ACTIVE" ? "ok" : "muted"}>
                      {p.status === "ACTIVE" ? "Attivo" : p.status}
                    </Chip>
                  </div>
                  <div className="absolute bottom-3 left-4 right-4 flex items-end justify-between gap-3">
                    <div className="min-w-0">
                      <h4 className="truncate text-base font-black tracking-tight text-white">{v?.name ?? p.code}</h4>
                      <span className="tag-id" title={p.code}>{p.code}</span>
                    </div>
                  </div>
                </div>

                <div className="flex flex-1 flex-col gap-4 p-5">
                  {v?.description && (
                    <p className="text-xs text-surface-300 line-clamp-2">{v.description}</p>
                  )}

                  <div className="grid grid-cols-2 gap-3">
                    <div className="rounded-2xl bg-white/5 p-3">
                      <div className="kpi-label">Listino</div>
                      {v ? (
                        <Figure
                          value={euro(v.base_price_cents)}
                          detail={v.vat_percentage != null ? `+ IVA ${v.vat_percentage}%` : "IVA non indicata"}
                        />
                      ) : (
                        <div className="mt-1 text-right text-xs text-surface-400">Nessuna versione</div>
                      )}
                    </div>
                    <div className="rounded-2xl bg-white/5 p-3">
                      <div className="kpi-label">Margine rete</div>
                      {margin ? (
                        <Figure value={margin.value} detail={margin.detail} ratio={margin.ratio} />
                      ) : (
                        <div className="mt-2 flex justify-end">
                          <Chip tone="warn" live>Da configurare</Chip>
                        </div>
                      )}
                    </div>
                  </div>

                  <div className="flex flex-wrap items-center gap-1.5">
                    <Chip tone="accent">{CATEGORY_LABELS[p.category] ?? p.category}</Chip>
                    <Chip tone="muted">{customerTypeLabel(p.customer_type)}</Chip>
                    {p.category !== "INTERNAL" && v && v.credit_discount_percentage > 0 && (
                      <Chip tone="ok">{v.credit_discount_percentage}% in SosnetCash</Chip>
                    )}
                    {p.category !== "INTERNAL" && v?.cashback_enabled && (
                      <Chip tone="info">Cashback attivo</Chip>
                    )}
                  </div>

                  <div className="mt-auto flex justify-end">
                    <RowActions>
                      <button
                        type="button"
                        onClick={() => openEdit(p)}
                        className="act act-primary"
                        title="Modifica prodotto"
                        disabled={!v}
                      >
                        Modifica
                      </button>
                      <button
                        type="button"
                        onClick={() => openDuplicate(p)}
                        className="act"
                        title="Duplica prodotto"
                        disabled={!v}
                      >
                        Duplica
                      </button>
                      <button
                        type="button"
                        onClick={() => { setDeletingProduct(p); setDeleteError(null); }}
                        className="act"
                        title="Elimina prodotto"
                      >
                        Elimina
                      </button>
                    </RowActions>
                  </div>
                </div>
              </div>
            );
          })
        )}
      </div>

      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-fade-in">
          <div className="w-full max-w-lg panel rounded-3xl p-7 border-white/10 bg-surface-950 pop max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-xl font-black tracking-tight text-white">
                {isDuplicating ? "Duplica Prodotto" : "Nuovo Prodotto"}
              </h3>
              <button onClick={() => { setShowCreate(false); setIsDuplicating(false); }}
                className="p-1 hover:bg-white/5 rounded-lg text-surface-400 hover:text-white transition cursor-pointer">
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            {isDuplicating && (
              <p className="text-xs text-surface-400 -mt-2 mb-4">
                Tutti i campi sono precompilati dal prodotto originale, incluso il margine. Cambia almeno il codice prima di salvare.
              </p>
            )}

            <form onSubmit={handleCreate} className="space-y-4">
              <div className="space-y-1">
                <label className="text-xs font-semibold text-surface-300 uppercase block">Codice</label>
                <input required value={code} onChange={(e) => setCode(e.target.value)} placeholder="Es: LUCE-PMI-01"
                  className="w-full rounded-xl field px-3 py-2 text-sm font-mono focus:border-brand-500" />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-surface-300 uppercase block">Tipo Prodotto</label>
                  <select value={productType} onChange={(e) => setProductType(e.target.value)}
                    className="w-full rounded-xl field px-3 py-2.5 text-sm bg-surface-900 focus:border-brand-500">
                    {Object.entries(PRODUCT_TYPE_LABELS).map(([code2, label]) => (
                      <option key={code2} value={code2}>{label}</option>
                    ))}
                  </select>
                </div>
                {productType === "ENERGY_CONTRACT" && (
                  <div className="space-y-1">
                    <label className="text-xs font-semibold text-surface-300 uppercase block">Tipo Energia</label>
                    <select value={energyType} onChange={(e) => setEnergyType(e.target.value)}
                      className="w-full rounded-xl field px-3 py-2.5 text-sm bg-surface-900 focus:border-brand-500">
                      {Object.entries(ENERGY_LABELS).map(([code2, label]) => (
                        <option key={code2} value={code2}>{label}</option>
                      ))}
                    </select>
                  </div>
                )}
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-surface-300 uppercase block">Cliente Target</label>
                  <select value={customerType} onChange={(e) => setCustomerType(e.target.value)}
                    className="w-full rounded-xl field px-3 py-2.5 text-sm bg-surface-900 focus:border-brand-500">
                    {Object.entries(CUSTOMER_TYPE_LABELS).map(([code2, label]) => (
                      <option key={code2} value={code2}>{label}</option>
                    ))}
                  </select>
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-surface-300 uppercase block">Categoria</label>
                  <select value={category} onChange={(e) => setCategory(e.target.value)}
                    className="w-full rounded-xl field px-3 py-2.5 text-sm bg-surface-900 focus:border-brand-500">
                    {Object.entries(CATEGORY_LABELS).map(([code2, label]) => (
                      <option key={code2} value={code2}>{label}</option>
                    ))}
                  </select>
                </div>
              </div>

              <ProductFormFields form={createForm} onChange={(patch) => setCreateForm((f) => ({ ...f, ...patch }))} commercialCategories={commercialCategories} category={category} />

              {createError && (
                <div className="p-3 rounded-lg bg-danger-500/10 border border-danger-500/20 text-danger-400 text-xs">{createError}</div>
              )}

              <div className="flex justify-end gap-3 mt-4">
                <button type="button" onClick={() => { setShowCreate(false); setIsDuplicating(false); }}
                  className="px-4 py-2 rounded-xl bg-white/5 hover:bg-white/10 text-xs font-semibold text-surface-300 border border-white/5 transition cursor-pointer">
                  Annulla
                </button>
                <button type="submit" disabled={createLoading}
                  className="px-4 py-2 rounded-xl bg-brand-600 hover:bg-brand-500 text-xs font-semibold text-white transition cursor-pointer disabled:opacity-50">
                  {createLoading ? "Creazione..." : isDuplicating ? "Crea Copia" : "Crea Prodotto"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {editingProduct && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-fade-in">
          <div className="w-full max-w-lg panel rounded-3xl p-7 border-white/10 bg-surface-950 pop max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-xl font-black tracking-tight text-white">Modifica Prodotto</h3>
              <button onClick={() => setEditingProduct(null)}
                className="p-1 hover:bg-white/5 rounded-lg text-surface-400 hover:text-white transition cursor-pointer">
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <p className="font-mono text-[10px] text-surface-500 mb-4">{editingProduct.code}</p>

            {editingProduct.current_version && (
              <div className="mb-5 pb-5 border-b border-white/5">
                <label className="text-xs font-semibold text-surface-300 uppercase block mb-2">Carica foto</label>
                <PhotoUpload
                  currentUrl={editForm.imageUrl || null}
                  uploadPath={`products/versions/${editingProduct.current_version.id}/photo`}
                  onUploaded={(url) => {
                    setEditForm((f) => ({ ...f, imageUrl: url }));
                    queryClient.invalidateQueries({ queryKey: ["admin", "products"] });
                  }}
                  alt={editingProduct.current_version.name}
                  size={72}
                />
              </div>
            )}

            <form onSubmit={handleEditSave} className="space-y-4">
              <div className="space-y-1">
                <label className="text-xs font-semibold text-surface-300 uppercase block">
                  Cliente Target
                </label>
                <select
                  value={editCustomerType}
                  onChange={(e) => setEditCustomerType(e.target.value)}
                  className="w-full rounded-xl field px-3 py-2.5 text-sm bg-surface-900 focus:border-brand-500"
                >
                  {Object.entries(CUSTOMER_TYPE_LABELS).map(([code2, label]) => (
                    <option key={code2} value={code2}>{label}</option>
                  ))}
                </select>
                <p className="text-[10px] text-surface-500">
                  Chi può attivare questo contratto. Un cliente vede in catalogo solo i contratti compatibili
                  con la propria tipologia &mdash; e il controllo è anche lato server, non solo grafico.
                </p>
              </div>

              <ProductFormFields form={editForm} onChange={(patch) => setEditForm((f) => ({ ...f, ...patch }))} commercialCategories={commercialCategories} category={editingProduct?.category ?? "INTERNAL"} />

              {editError && (
                <div className="p-3 rounded-lg bg-danger-500/10 border border-danger-500/20 text-danger-400 text-xs">{editError}</div>
              )}

              <div className="flex justify-end gap-3 mt-4">
                <button type="button" onClick={() => setEditingProduct(null)}
                  className="px-4 py-2 rounded-xl bg-white/5 hover:bg-white/10 text-xs font-semibold text-surface-300 border border-white/5 transition cursor-pointer">
                  Annulla
                </button>
                <button type="submit" disabled={editLoading}
                  className="px-4 py-2 rounded-xl bg-brand-600 hover:bg-brand-500 text-xs font-semibold text-white transition cursor-pointer disabled:opacity-50">
                  {editLoading ? "Salvataggio..." : "Salva Modifiche"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {deleteConfirmModal}
    </div>
  );
}
