"use client";

import { useFeatures } from "@/lib/features";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import type {
  AliexpressProductRead,
  CjProductRead,
  CustomerRead,
  ImportedProductRead,
  SosnetMarketProductRead,
  ProductCatalogRead,
  ShopifyProductRead,
  ShopKey,
} from "@/lib/types";
import { AliexpressProductModal } from "@/components/aliexpress-product-modal";
import { SosnetMarketProductModal } from "@/components/sosnet-market-product-modal";
import { CjProductModal } from "@/components/cj-product-modal";
import { useMarketplaceConfig } from "@/components/marketplace-rules-card";
import { ShopifyProductModal } from "@/components/shopify-product-modal";
import { ContractRequestWizard } from "@/components/contract-request-wizard";
import { ImportedProductCheckoutModal } from "@/components/imported-product-checkout-modal";
import { ProductCheckoutModal } from "@/components/product-checkout-modal";
import { ProductDetailModal } from "@/components/product-detail-modal";
import { ProductThumbnail } from "@/components/product-thumbnail";
import { computePrice, productAllowsCustomerKind, isRecurringProductType } from "@/lib/product-audience";
import { ShareMenu } from "@/components/share-buttons";
import { useShopCategories } from "@/components/shop-categories-card";

const ENERGY_LABELS: Record<string, string> = {
  ELECTRICITY: "Luce",
  GAS: "Gas",
  DUAL_FUEL: "Dual Fuel",
};

const PRODUCT_TYPE_LABELS: Record<string, string> = {
  DIGITAL: "Digitale",
  PHYSICAL: "Fisico",
  SUBSCRIPTION: "Abbonamento",
};

const BILLING_LABELS: Record<string, string> = {
  MONTHLY: "/mese",
  QUARTERLY: "/trimestre",
  ANNUAL: "/anno",
};

type ProductCategory = "INTERNAL" | "DROPSHIPPING" | "PARTNER";
// Not a real Product.category: the "Acquisti SOSNET" tab is backed by the
// separate imported_products tables (see its models.py) but looks like any
// other tab. Added only when showImportedTab is passed.
// The imported-product shops appear as "Marketplace 1/2/3" (names are
// settings, see marketplace-rules-card.tsx): "IMPORTED" is AliExpress, "CJ"
// is CJ Dropshipping, "SHOPIFY" is Shopify. Customers never see the source.
// The AliExpress tab shows both API-imported products (same card and
// checkout as CJ and Shopify) and the legacy hand-entered list.
type ShopTab = ProductCategory | "IMPORTED" | "CJ" | "SHOPIFY" | "SOSNET_MARKET";
type MarketplaceProduct = {
  source: "CJ" | "SHOPIFY" | "ALIEXPRESS" | "SOSNET_MARKET";
  product: CjProductRead | SosnetMarketProductRead;
};

const CATEGORY_TABS: { key: ProductCategory; label: string }[] = [
  { key: "INTERNAL", label: "SOSNET" },
  { key: "PARTNER", label: "Prodotti Partner" },
  // UI label only; the DROPSHIPPING key is unchanged in the DB/API (see
  // catalog/models.py::Product.category).
  { key: "DROPSHIPPING", label: "Offerte Sosnet" },
];

const ALL_CATEGORIES: ProductCategory[] = ["INTERNAL", "PARTNER", "DROPSHIPPING"];

// Each Shop tab has its own categories, and a customer never sees another
// shop's. This map is where the two naming schemes meet: legacy hand-entered
// products count as AliExpress, since they share its tab.
const SHOP_KEY_BY_TAB: Record<ShopTab, ShopKey> = {
  INTERNAL: "internal",
  PARTNER: "partner",
  DROPSHIPPING: "dropshipping",
  CJ: "cj",
  SHOPIFY: "shopify",
  IMPORTED: "aliexpress",
  SOSNET_MARKET: "sosnet_market",
};

/**
 * The logged-in customer's own record: decides which contracts they may
 * activate and whether prices carry VAT. A 404 for staff/promoter accounts
 * without a customer record is normal.
 */
async function fetchMyCustomerRecord(): Promise<CustomerRead | null> {
  const res = await fetch("/api/proxy/customers/me");
  if (res.status === 404) return null;
  if (!res.ok) throw new Error("Impossibile caricare la tua anagrafica.");
  return res.json();
}

async function fetchImportedProducts(): Promise<ImportedProductRead[]> {
  const res = await fetch("/api/proxy/imported-products/products/active");
  if (!res.ok) throw new Error("Impossibile caricare gli Acquisti SOSNET.");
  return res.json();
}

async function fetchShopifyProducts(): Promise<ShopifyProductRead[]> {
  const res = await fetch("/api/proxy/shopify/products/active");
  if (!res.ok) return [];
  return res.json();
}

async function fetchAliexpressProducts(): Promise<AliexpressProductRead[]> {
  const res = await fetch("/api/proxy/aliexpress/products/active");
  if (!res.ok) return [];
  return res.json();
}

async function fetchPartnerShopProducts(): Promise<CjProductRead[]> {
  const res = await fetch("/api/proxy/cj/products/active");
  if (!res.ok) return [];
  return res.json();
}

function euro(cents: number): string {
  return (cents / 100).toLocaleString("it-IT", { style: "currency", currency: "EUR" });
}

// Wallet credit is SosnetCash, never EUR (same helper as wallet-panel.tsx).
function sosnetCash(cents: number): string {
  return `${(cents / 100).toLocaleString("it-IT", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} SosnetCash`;
}

async function fetchProducts(): Promise<ProductCatalogRead[]> {
  const res = await fetch("/api/proxy/products");
  if (!res.ok) throw new Error("Impossibile caricare il catalogo prodotti.");
  return res.json();
}

interface CustomerProductsPanelProps {
  /**
   * When set, each card gets a "Condividi" button copying a product referral
   * link (promoters only).
   */
  referralCode?: string;
  organizationId?: string;
  /**
   * Category tabs this instance shows, so one component serves both the
   * contracts catalog (INTERNAL) and the Shop (PARTNER + DROPSHIPPING).
   * Defaults to all three (used by the promoter's "Condividi" view).
   */
  visibleCategories?: ProductCategory[];
  /** The account's email, used only to pre-fill (never lock) the wizard's Email field. */
  accountEmail?: string;
  /** Opt-in: appends the "Acquisti SOSNET" tab to the Shop's tab bar. */
  showImportedTab?: boolean;
}

export function CustomerProductsPanel({
  referralCode,
  organizationId,
  visibleCategories = ALL_CATEGORIES,
  accountEmail,
  showImportedTab = false,
}: CustomerProductsPanelProps = {}) {
  const features = useFeatures();
  const queryClient = useQueryClient();
  const { data: products, isLoading, error } = useQuery({
    queryKey: ["customer", "products"],
    queryFn: fetchProducts,
  });
  const { data: importedProducts } = useQuery({
    queryKey: ["customer", "imported-products"],
    queryFn: fetchImportedProducts,
    enabled: showImportedTab,
  });
  // Shop Sosnet Partner (CJ Dropshipping), shown as "Marketplace 1". The tab
  // appears only while the shop is switched on and has products.
  const { data: partnerShopProducts } = useQuery({
    queryKey: ["customer", "cj-products"],
    queryFn: fetchPartnerShopProducts,
    enabled: showImportedTab,
  });
  const { data: shopifyProducts } = useQuery({
    queryKey: ["customer", "shopify-products"],
    queryFn: fetchShopifyProducts,
    enabled: showImportedTab,
  });
  const { data: aliexpressProducts } = useQuery({
    queryKey: ["customer", "aliexpress-products"],
    queryFn: fetchAliexpressProducts,
    enabled: showImportedTab,
  });
  // Marketplace 4. The grid is empty when the shop is off, so the tab hides itself.
  const { data: sosnetMarketProducts } = useQuery({
    queryKey: ["customer", "sosnet-market", "products"],
    queryFn: async (): Promise<SosnetMarketProductRead[]> => {
      const res = await fetch("/api/proxy/sosnet-market/products/mine");
      if (!res.ok) return [];
      return res.json();
    },
    enabled: showImportedTab,
  });
  const { data: marketplaceConfig } = useMarketplaceConfig();
  // The listed price is net; VAT is added at checkout. The "+ IVA" label avoids
  // a surprise at payment.
  const marketplaceVatPercentage = marketplaceConfig?.vat_percentage ?? 0;
  const marketplaceLabels = marketplaceConfig?.labels ?? {
    cj: "Marketplace 1",
    shopify: "Marketplace 2",
    aliexpress: "Marketplace 3",
    sosnet_market: "Fai la Spesa con Sosnet",
  };
  const [partnerShopTarget, setPartnerShopTarget] = useState<MarketplaceProduct | null>(null);
  // Only the contract catalog depends on the viewer, so this is fetched only
  // when an INTERNAL tab is shown.
  const needsCustomerKind = visibleCategories.includes("INTERNAL");
  const { data: myCustomer } = useQuery({
    queryKey: ["customer", "me", "record"],
    queryFn: fetchMyCustomerRecord,
    enabled: needsCustomerKind,
  });
  const customerKind = myCustomer?.kind ?? null;

  // null until the customer picks a shop: then the first one with products opens.
  const [activeCategory, setActiveCategory] = useState<ShopTab | null>(null);
  // Shop navigation: category and search combine and affect only the grid.
  const [search, setSearch] = useState("");
  const [chosenCategoryId, setChosenCategoryId] = useState<string | null>(null);
  const [checkoutTarget, setCheckoutTarget] = useState<{ versionId: string; name: string } | null>(null);
  const [importedCheckoutTarget, setImportedCheckoutTarget] = useState<{ id: string; name: string } | null>(null);
  const [detailTarget, setDetailTarget] = useState<ProductCatalogRead | null>(null);
  const [activationTarget, setActivationTarget] = useState<ProductCatalogRead | null>(null);

  // "I miei Contratti" and Home only showcase SOSNET packages; activation
  // happens through the pratica.
  const contractsOnly = !referralCode && visibleCategories.length === 1 && visibleCategories[0] === "INTERNAL";

  // Own-catalog sections can be renamed and switched off by the administrator
  // ("Sezioni dello Shop"). This affects the Shop's tab bar only; a page that
  // requests a category explicitly (the Home contracts showcase) still shows it.
  const sectionConfig = marketplaceConfig?.sections;
  const sectionKeyOf: Record<ProductCategory, "internal" | "partner" | "dropshipping"> = {
    INTERNAL: "internal",
    PARTNER: "partner",
    DROPSHIPPING: "dropshipping",
  };
  const onlyOneCategoryAsked = visibleCategories.length === 1;
  const visibleTabs: { key: ShopTab; label: string }[] = [
    ...CATEGORY_TABS.filter((tab) => visibleCategories.includes(tab.key))
      .filter((tab) => onlyOneCategoryAsked || (sectionConfig?.[sectionKeyOf[tab.key]]?.enabled ?? true))
      .map((tab) => ({ key: tab.key, label: sectionConfig?.[sectionKeyOf[tab.key]]?.label ?? tab.label })),
    ...(showImportedTab && (sosnetMarketProducts ?? []).length > 0
      ? [{ key: "SOSNET_MARKET" as ShopTab, label: marketplaceLabels.sosnet_market }]
      : []),
    ...(showImportedTab && features.dropshipping && (partnerShopProducts ?? []).length > 0
      ? [{ key: "CJ" as ShopTab, label: marketplaceLabels.cj }]
      : []),
    ...(showImportedTab && features.dropshipping && (shopifyProducts ?? []).length > 0
      ? [{ key: "SHOPIFY" as ShopTab, label: marketplaceLabels.shopify }]
      : []),
    ...(showImportedTab && features.dropshipping && ((aliexpressProducts ?? []).length > 0 || (importedProducts ?? []).length > 0)
      ? [{ key: "IMPORTED" as ShopTab, label: marketplaceLabels.aliexpress }]
      : []),
  ];

  const activeProducts = (products ?? []).filter(
    (p) => p.status === "ACTIVE" && p.current_version && p.current_version.status === "ACTIVE"
  );
  const countFor = (key: ShopTab): number =>
    key === "IMPORTED"
      ? (aliexpressProducts ?? []).length + (importedProducts ?? []).length
      : key === "CJ"
        ? (partnerShopProducts ?? []).length
        : key === "SHOPIFY"
          ? (shopifyProducts ?? []).length
          : key === "SOSNET_MARKET"
            ? (sosnetMarketProducts ?? []).length
            : activeProducts.filter((p) => p.category === key).length;

  // If the selected tab no longer exists (section off, Marketplace empty), fall
  // back to the first one with products, else the first: derived during
  // render, not synced in an effect.
  const activeTab: ShopTab =
    activeCategory && visibleTabs.some((t) => t.key === activeCategory)
      ? activeCategory
      : (visibleTabs.find((t) => countFor(t.key) > 0) ?? visibleTabs[0])?.key ?? visibleCategories[0] ?? "INTERNAL";

  // CJ, Shopify and AliExpress products share one shape and one card.
  const shopPartnerCards: CjProductRead[] = !showImportedTab
    ? []
    : activeTab === "CJ"
      ? partnerShopProducts ?? []
      : activeTab === "SHOPIFY"
        ? shopifyProducts ?? []
        : activeTab === "IMPORTED"
          ? aliexpressProducts ?? []
          : activeTab === "SOSNET_MARKET"
            ? sosnetMarketProducts ?? []
            : [];
  const partnerSource: MarketplaceProduct["source"] =
    activeTab === "SHOPIFY"
      ? "SHOPIFY"
      : activeTab === "IMPORTED"
        ? "ALIEXPRESS"
        : activeTab === "SOSNET_MARKET"
          ? "SOSNET_MARKET"
          : "CJ";
  // Legacy hand-entered AliExpress list: its own card and checkout, shown below
  // the API products in the same tab.
  const shopHandMadeCards: ImportedProductRead[] =
    showImportedTab && activeTab === "IMPORTED" ? importedProducts ?? [] : [];

  const shopCatalog = activeProducts
    .filter((p) => p.category === activeTab)
    // Only offer contracts the customer's type may activate. Enforced
    // server-side too (contracts/service.py); this avoids showing cards that
    // would be refused. Contracts only, and fails open while the customer record loads.
    .filter((p) => p.category !== "INTERNAL" || productAllowsCustomerKind(p.customer_type, customerKind));

  // Categories of the selected shop only. Failures are tolerated: with no
  // categories the Shop simply shows no category bar.
  const shopKey = SHOP_KEY_BY_TAB[activeTab];
  // The Home package showcase is just a few cards and a button, no navigation tools.
  const navigable = !contractsOnly;
  const { data: shopCategories } = useShopCategories(shopKey, navigable);

  // Every active category of this shop, including empty ones, as an index of
  // what it sells. Empty ones look disabled and explain why when opened.
  const categoryIdsInShop = new Set<string>([
    ...shopCatalog.flatMap((p) => p.category_ids ?? []),
    ...shopPartnerCards.flatMap((p) => p.category_ids ?? []),
    ...shopHandMadeCards.flatMap((p) => p.category_ids ?? []),
  ]);
  const categoryChips = (shopCategories ?? []).filter((c) => c.active);
  // Derived during render: after switching shop the old category no longer
  // exists and the filter simply drops.
  const activeCategoryId = categoryChips.some((c) => c.id === chosenCategoryId) ? chosenCategoryId : null;

  const needle = search.trim().toLowerCase();
  const filtering = needle !== "" || activeCategoryId !== null;
  function matchesSearch(name: string, description?: string | null): boolean {
    return !needle || name.toLowerCase().includes(needle) || (description ?? "").toLowerCase().includes(needle);
  }
  function matchesCategory(categoryIds: string[] | undefined): boolean {
    return activeCategoryId === null || (categoryIds ?? []).includes(activeCategoryId);
  }
  /** Resets to the full catalog: the way out of an empty result. */
  function showEverything() {
    setSearch("");
    setChosenCategoryId(null);
  }

  const catalog = shopCatalog.filter(
    (p) => matchesSearch(p.current_version!.name, p.current_version!.description) && matchesCategory(p.category_ids)
  );
  const partnerCards = shopPartnerCards.filter(
    (p) => matchesSearch(p.name, p.description) && matchesCategory(p.category_ids)
  );
  const handMadeCards = shopHandMadeCards.filter(
    (p) => matchesSearch(p.name, p.description) && matchesCategory(p.category_ids)
  );

  /**
   * Product referral link: registration with this promoter's code and the
   * product preselected.
   */
  function productLink(productId: string, productName: string): string {
    if (!referralCode || typeof window === "undefined") return "";
    const url = new URL(`/r/${referralCode}`, window.location.origin);
    if (organizationId) url.searchParams.set("org", organizationId);
    url.searchParams.set("product", productId);
    url.searchParams.set("product_name", productName);
    return url.toString();
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12 text-surface-300 gap-2">
        <svg className="animate-spin h-5 w-5 text-brand-500" fill="none" viewBox="0 0 24 24">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
        </svg>
        <span>Caricamento catalogo...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-4 rounded-2xl bg-danger-500/10 border border-danger-500/30 text-danger-300 text-sm">
        Impossibile caricare il catalogo prodotti.
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <p className="kpi-label">{contractsOnly ? "Pacchetti" : referralCode ? "Da proporre" : "Shop"}</p>
        <h3 className="mt-1 text-xl sm:text-2xl font-black tracking-tight text-white">
          {contractsOnly ? "I pacchetti SOSNET" : showImportedTab && !referralCode ? "Fai la spesa con SOSNET" : "Prodotti & Servizi"}
        </h3>
        <p className="mt-1 text-xs text-surface-300 max-w-3xl">
          {referralCode
            ? "Condividi un'offerta con un cliente: il link lo porta dritto alla registrazione, già associato a te."
            : contractsOnly
              ? "Apri “Dettagli” per leggere ogni pacchetto. Per attivarli usa “Attiva nuovo contratto”: una pratica può contenere uno o più contratti."
              : showImportedTab
                ? "Usa il tuo SosnetCash con i nostri partner e nei Marketplace, con consegna a casa. Nei Marketplace, pagando con bonifico istantaneo hai uno sconto."
                : "Le offerte luce, gas e dual fuel disponibili per il tuo profilo."}
        </p>
      </div>


      {/* Shop selection comes first: large tappable buttons, two per row on phones. */}
      {visibleTabs.length > 1 && (
      <div className="stagger grid grid-cols-2 sm:grid-cols-3 gap-3">
        {visibleTabs.map((tab, i) => {
          const count = countFor(tab.key);
          const chosen = activeTab === tab.key;
          return (
            <button
              key={tab.key}
              aria-pressed={chosen}
              data-tilt
              style={{ "--i": i } as React.CSSProperties}
              onClick={() => {
                setActiveCategory(tab.key);
                // Switching shop resets search and category, which belonged to the previous shop.
                showEverything();
              }}
              className={`relative overflow-hidden rounded-3xl p-5 text-left transition-all duration-200 cursor-pointer active:scale-[0.98] ${
                chosen
                  ? "bg-gradient-to-br from-brand-600 to-accent-500 text-white shadow-xl shadow-brand-500/30 ring-2 ring-white/60"
                  : "panel"
              }`}
            >
              <span className="block text-base sm:text-lg font-black tracking-tight leading-snug text-white">
                {tab.label}
              </span>
              <span className={`block text-[11px] mt-1 ${chosen ? "text-white/85" : "text-surface-300"}`}>
                {count > 0 ? `${count} ${count === 1 ? "prodotto" : "prodotti"}` : "Nessun prodotto"}
              </span>
            </button>
          );
        })}
      </div>
      )}

      {/* Search and categories of the selected shop, combined to filter the grid below. */}
      {navigable && (
        <div className="space-y-3">
          <div className="relative">
            <svg className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-surface-400 pointer-events-none" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-4.35-4.35M17 11a6 6 0 11-12 0 6 6 0 0112 0z" />
            </svg>
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Cerca un prodotto per nome o descrizione..."
              aria-label="Cerca un prodotto in questo negozio"
              className="w-full rounded-2xl field pl-11 pr-10 py-3.5 text-sm focus:border-brand-500"
            />
            {search && (
              <button
                type="button"
                onClick={() => setSearch("")}
                aria-label="Cancella la ricerca"
                className="absolute right-3 top-1/2 -translate-y-1/2 p-1 rounded-lg text-surface-400 hover:text-white cursor-pointer"
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            )}
          </div>

          {categoryChips.length > 0 && (
            <div className="subnav">
              <button
                type="button"
                aria-pressed={activeCategoryId === null}
                onClick={() => setChosenCategoryId(null)}
                className="subnav-pill"
                data-active={activeCategoryId === null || undefined}
              >
                Tutte
              </button>
              {categoryChips.map((c) => {
                const empty = !categoryIdsInShop.has(c.id);
                return (
                  <button
                    key={c.id}
                    type="button"
                    aria-pressed={activeCategoryId === c.id}
                    onClick={() => setChosenCategoryId(c.id)}
                    title={empty ? "Nessun prodotto in questa categoria, per ora" : undefined}
                    className={`subnav-pill ${empty && activeCategoryId !== c.id ? "opacity-50" : ""}`}
                    data-active={activeCategoryId === c.id || undefined}
                  >
                    {c.name}
                  </button>
                );
              })}
            </div>
          )}
        </div>
      )}

      {catalog.length === 0 && partnerCards.length === 0 && handMadeCards.length === 0 ? (
        filtering ? (
          // Empty because of our filters, not because the shop is empty: say so and offer a way out.
          <div className="panel rounded-3xl flex flex-col items-center text-center py-12 px-6 gap-3">
            <svg className="float-soft w-10 h-10 text-surface-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M21 21l-4.35-4.35M17 11a6 6 0 11-12 0 6 6 0 0112 0z" />
            </svg>
            <p className="text-sm text-surface-300">
              Nessun prodotto corrisponde alla ricerca in questo negozio.
            </p>
            <button
              type="button"
              onClick={showEverything}
              className="act act-primary"
            >
              Mostra tutti
            </button>
          </div>
        ) : (
          <div className="panel rounded-3xl flex flex-col items-center text-center py-12 px-6 gap-3">
            <svg className="float-soft w-10 h-10 text-surface-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />
            </svg>
            <p className="text-sm text-surface-300">
              {activeTab === "INTERNAL"
                ? "Nessun prodotto disponibile al momento. Contatta il tuo promoter di riferimento per maggiori informazioni."
                : "Nessun prodotto in questa categoria al momento."}
            </p>
          </div>
        )
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
          {catalog.map((p, i) => {
            const v = p.current_version!;
            const typeLabel = p.product_type === "ENERGY_CONTRACT"
              ? (p.energy_type ? ENERGY_LABELS[p.energy_type] ?? p.energy_type : "Energia")
              : PRODUCT_TYPE_LABELS[p.product_type] ?? p.product_type;
            const purchasable = !referralCode && p.category !== "INTERNAL";
            // An SOSNET package opens its details; activation goes through "Attiva nuovo contratto".
            const readable = p.category === "INTERNAL";
            const openable = purchasable || readable;
            const maxCreditCents = Math.round((v.base_price_cents * v.credit_discount_percentage) / 100);
            return (
              <div
                key={p.id}
                style={{ animationDelay: `${Math.min(i, 8) * 60}ms` }}
                className="group rise panel sheen relative flex flex-col rounded-3xl overflow-hidden hover:-translate-y-1.5 hover:shadow-2xl hover:shadow-brand-500/25 transition-all duration-300"
              >
                <button
                  type="button"
                  onClick={() => openable && setDetailTarget(p)}
                  disabled={!openable}
                  className={`relative block w-full h-48 overflow-hidden ${openable ? "cursor-pointer" : "cursor-default"}`}
                >
                  <ProductThumbnail
                    imageUrl={v.image_url}
                    alt={v.name}
                    className="w-full h-full object-cover transition-transform duration-700 ease-out group-hover:scale-110 group-hover:rotate-1"
                    iconClassName="w-12 h-12 text-brand-400/40"
                  />
                  <div className="absolute inset-0 bg-gradient-to-t from-surface-950/85 via-surface-950/10 to-transparent" />
                  <div className="absolute top-3 left-3 flex flex-wrap gap-1.5">
                    <span className="chip chip-muted backdrop-blur-sm">
                      {typeLabel}
                    </span>
                  </div>
                  {features.wallet && p.category !== "INTERNAL" && v.credit_discount_percentage > 0 && (
                    <div className="absolute top-3 right-3">
                      <span className="chip chip-ok pop backdrop-blur-sm">
                        -{v.credit_discount_percentage}% in SosnetCash
                      </span>
                    </div>
                  )}
                  {purchasable && (
                    <div className="absolute inset-0 flex items-center justify-center bg-surface-950/0 group-hover:bg-surface-950/30 transition-colors duration-300">
                      <span className="opacity-0 group-hover:opacity-100 translate-y-2 group-hover:translate-y-0 transition-all duration-300 act act-primary">
                        Vedi dettagli
                      </span>
                    </div>
                  )}
                </button>
                <div className="flex flex-1 flex-col p-6">
                  <h4
                    onClick={() => openable && setDetailTarget(p)}
                    className={`text-lg font-black tracking-tight text-white mb-1.5 leading-snug ${openable ? "cursor-pointer hover:text-brand-200 transition" : ""}`}
                  >
                    {v.name}
                  </h4>
                  {v.description && (
                    <p className="text-xs text-surface-300 mb-4 line-clamp-2">{v.description}</p>
                  )}

                  <div className="mt-auto flex items-end justify-between gap-3 pt-4 border-t border-white/10">
                    <div>
                      <p className="kpi-label">Prezzo</p>
                      <div className="flex items-baseline gap-1">
                        <span className="text-2xl font-black text-gradient tabular-nums">{euro(v.base_price_cents)}</span>
                        <span className="text-[11px] text-surface-300">{isRecurringProductType(p.product_type) ? BILLING_LABELS[v.billing_period] ?? "" : ""}</span>
                      </div>
                      {(() => {
                        // Contracts for private customers carry no VAT. On the shop grid (no
                        // customer kind) the product's own rate is shown.
                        const price = computePrice(
                          v.base_price_cents,
                          v.vat_percentage,
                          p.category === "INTERNAL" ? customerKind : null
                        );
                        if (price.vatCents <= 0) {
                          return p.category === "INTERNAL" && customerKind ? (
                            <p className="text-[10.5px] text-surface-300 mt-0.5">IVA non applicata</p>
                          ) : null;
                        }
                        return (
                          <p className="text-[10.5px] text-surface-300 mt-0.5">
                            + IVA {price.vatRate}% ({euro(price.grossCents)} tot.)
                          </p>
                        );
                      })()}
                      {v.initial_fee_cents > 0 && (
                        <p className="text-[10.5px] text-surface-300 mt-0.5">
                          + {euro(v.initial_fee_cents)} attivazione
                        </p>
                      )}
                    </div>
                    {p.category !== "INTERNAL" && maxCreditCents > 0 && (
                      <div className="text-right">
                        <p className="kpi-label !text-success-300">SosnetCash usabili</p>
                        <p className="text-lg font-black text-success-300 tabular-nums">{sosnetCash(maxCreditCents)}</p>
                      </div>
                    )}
                  </div>

                  {referralCode && (
                    // A menu rather than a row of pills, to keep grid cards uncluttered.
                    <ShareMenu
                      url={productLink(p.id, v.name)}
                      text={`Ti consiglio "${v.name}" di SOSNET:`}
                      title={v.name}
                      heading={`Condividi "${v.name}"`}
                      buttonClassName="act mt-5 w-full justify-center"
                    />
                  )}
                  {purchasable && (
                    <button
                      onClick={() => setDetailTarget(p)}
                      className="act act-primary mt-5 w-full justify-center"
                    >
                      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 11V7a4 4 0 00-8 0v4M5 9h14l1 11H4L5 9z" />
                      </svg>
                      Vedi dettagli e acquista
                    </button>
                  )}
                  {readable && (
                    <button
                      onClick={() => setDetailTarget(p)}
                      className="act mt-5 w-full justify-center"
                    >
                      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                      </svg>
                      Dettagli
                    </button>
                  )}
                </div>
              </div>
            );
          })}
          {partnerCards.map((p, i) => {
            const maxCreditCents = Math.round((p.min_price_cents * p.credit_discount_percentage) / 100);
            return (
              <div
                key={`partner-${p.id}`}
                style={{ animationDelay: `${Math.min(catalog.length + i, 8) * 60}ms` }}
                className="group rise panel sheen relative flex flex-col rounded-3xl overflow-hidden hover:-translate-y-1.5 hover:shadow-2xl hover:shadow-brand-500/25 transition-all duration-300"
              >
                <button
                  type="button"
                  onClick={() => {
                    if (!referralCode) setPartnerShopTarget({ source: partnerSource, product: p });
                  }}
                  className="relative block w-full h-48 overflow-hidden cursor-pointer bg-white"
                >
                  <ProductThumbnail
                    imageUrl={p.image_url}
                    alt={p.name}
                    className="w-full h-full object-cover transition-transform duration-700 ease-out group-hover:scale-110 group-hover:rotate-1"
                    iconClassName="w-12 h-12 text-brand-400/40"
                  />
                  <div className="absolute inset-0 bg-gradient-to-t from-surface-950/85 via-surface-950/10 to-transparent" />
                  <div className="absolute top-3 left-3 flex flex-wrap gap-1.5">
                    <span className="chip chip-muted backdrop-blur-sm">
                      {p.shipping_days ? `Consegna ${p.shipping_days} gg` : "Spedito a casa"}
                    </span>
                  </div>
                  {features.wallet && p.credit_discount_percentage > 0 && (
                    <div className="absolute top-3 right-3">
                      <span className="chip chip-ok pop backdrop-blur-sm">
                        -{p.credit_discount_percentage}% in SosnetCash
                      </span>
                    </div>
                  )}
                  {!p.in_stock && (
                    <span className="absolute bottom-3 left-3"><span className="chip chip-bad">Esaurito</span></span>
                  )}
                  <div className="absolute inset-0 flex items-center justify-center bg-surface-950/0 group-hover:bg-surface-950/30 transition-colors duration-300">
                    <span className="opacity-0 group-hover:opacity-100 translate-y-2 group-hover:translate-y-0 transition-all duration-300 act act-primary">
                      Vedi dettagli
                    </span>
                  </div>
                </button>
                <div className="flex flex-1 flex-col p-6">
                  <h4
                    onClick={() => setPartnerShopTarget({ source: partnerSource, product: p })}
                    className="text-lg font-black tracking-tight text-white mb-1.5 leading-snug cursor-pointer hover:text-brand-200 transition line-clamp-2"
                  >
                    {p.name}
                  </h4>
                  {p.description && (
                    <p className="text-xs text-surface-300 mb-4 line-clamp-2">{p.description}</p>
                  )}
                  <div className="mt-auto flex items-end justify-between gap-3 pt-4 border-t border-white/10">
                    <div>
                      <p className="kpi-label">
                        {p.min_price_cents !== p.max_price_cents ? "Prezzo da" : "Prezzo"}
                      </p>
                      <span className="text-2xl font-black text-gradient tabular-nums">{euro(p.min_price_cents)}</span>
                      <p className="text-[10.5px] text-surface-300 mt-0.5">
                        {marketplaceVatPercentage > 0 ? "+ IVA · " : ""}
                        {p.shipping_included ? "Spedizione inclusa" : "+ spedizione"}
                      </p>
                      {/* The price shown is the full one; bank transfer takes a discount off. */}
                      {p.bank_transfer_discount_percentage > 0 && (
                        <p className="text-[10px] font-semibold text-white mt-0.5">
                          Con bonifico istantaneo -{p.bank_transfer_discount_percentage}%:{" "}
                          <span className="tabular-nums">
                            {euro(p.min_price_cents - Math.floor((p.min_price_cents * p.bank_transfer_discount_percentage + 50) / 100))}
                          </span>
                        </p>
                      )}
                    </div>
                    {maxCreditCents > 0 && (
                      <div className="text-right">
                        <p className="kpi-label !text-success-300">SosnetCash usabili</p>
                        <p className="text-lg font-black text-success-300 tabular-nums">{sosnetCash(maxCreditCents)}</p>
                      </div>
                    )}
                  </div>
                  {referralCode ? (
                    // Promoters share rather than buy on someone's behalf: the link leads to
                    // registration with their code.
                    <ShareMenu
                      url={productLink(p.id, p.name)}
                      text={`Ti consiglio "${p.name}" nello shop di SOSNET:`}
                      title={p.name}
                      heading={`Condividi "${p.name}"`}
                      buttonClassName="act mt-5 w-full justify-center"
                    />
                  ) : (
                    <button
                      onClick={() => setPartnerShopTarget({ source: partnerSource, product: p })}
                      className="act act-primary mt-5 w-full justify-center"
                    >
                      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 11V7a4 4 0 00-8 0v4M5 9h14l1 11H4L5 9z" />
                      </svg>
                      Vedi dettagli e acquista
                    </button>
                  )}
                </div>
              </div>
            );
          })}
          {handMadeCards.map((ip, i) => {
            const maxCreditCents = Math.round((ip.price_cents * ip.credit_discount_percentage) / 100);
            return (
              <div
                key={ip.id}
                style={{ animationDelay: `${Math.min(catalog.length + partnerCards.length + i, 8) * 60}ms` }}
                className="group rise panel sheen relative flex flex-col rounded-3xl overflow-hidden hover:-translate-y-1.5 hover:shadow-2xl hover:shadow-brand-500/25 transition-all duration-300"
              >
                <button
                  type="button"
                  onClick={() => {
                    if (!referralCode) setImportedCheckoutTarget({ id: ip.id, name: ip.name });
                  }}
                  className="relative block w-full h-48 overflow-hidden cursor-pointer"
                >
                  <ProductThumbnail
                    imageUrl={ip.image_url}
                    alt={ip.name}
                    className="w-full h-full object-cover transition-transform duration-700 ease-out group-hover:scale-110 group-hover:rotate-1"
                    iconClassName="w-12 h-12 text-brand-400/40"
                  />
                  <div className="absolute inset-0 bg-gradient-to-t from-surface-950/85 via-surface-950/10 to-transparent" />
                  {features.wallet && ip.credit_discount_percentage > 0 && (
                    <div className="absolute top-3 right-3">
                      <span className="chip chip-ok pop backdrop-blur-sm">
                        -{ip.credit_discount_percentage}% in SosnetCash
                      </span>
                    </div>
                  )}
                  <div className="absolute inset-0 flex items-center justify-center bg-surface-950/0 group-hover:bg-surface-950/30 transition-colors duration-300">
                    <span className="opacity-0 group-hover:opacity-100 translate-y-2 group-hover:translate-y-0 transition-all duration-300 act act-primary">
                      Vedi dettagli
                    </span>
                  </div>
                </button>
                <div className="flex flex-1 flex-col p-6">
                  <h4
                    onClick={() => {
                      if (!referralCode) setImportedCheckoutTarget({ id: ip.id, name: ip.name });
                    }}
                    className="text-lg font-black tracking-tight text-white mb-1.5 leading-snug cursor-pointer hover:text-brand-200 transition"
                  >
                    {ip.name}
                  </h4>
                  {ip.description && (
                    <p className="text-xs text-surface-300 mb-4 line-clamp-2">{ip.description}</p>
                  )}
                  <div className="mt-auto flex items-end justify-between gap-3 pt-4 border-t border-white/10">
                    <div>
                      <p className="kpi-label">
                        Prezzo
                      </p>
                      <span className="text-2xl font-black text-gradient tabular-nums">{euro(ip.price_cents)}</span>
                      {marketplaceVatPercentage > 0 && (
                        <p className="text-[10.5px] text-surface-300 mt-0.5">+ IVA {marketplaceVatPercentage}%</p>
                      )}
                      {(ip.bank_transfer_discount_percentage ?? 0) > 0 && (
                        <p className="text-[11px] font-semibold text-white mt-0.5">
                          Con bonifico istantaneo -{ip.bank_transfer_discount_percentage}%:{" "}
                          <strong className="tabular-nums">
                            {euro(ip.price_cents - Math.floor((ip.price_cents * ip.bank_transfer_discount_percentage! + 50) / 100))}
                          </strong>
                        </p>
                      )}
                    </div>
                    {maxCreditCents > 0 && (
                      <div className="text-right">
                        <p className="kpi-label !text-success-300">SosnetCash usabili</p>
                        <p className="text-lg font-black text-success-300 tabular-nums">{sosnetCash(maxCreditCents)}</p>
                      </div>
                    )}
                  </div>
                  {referralCode ? (
                    <ShareMenu
                      url={productLink(ip.id, ip.name)}
                      text={`Ti consiglio "${ip.name}" nello shop di SOSNET:`}
                      title={ip.name}
                      heading={`Condividi "${ip.name}"`}
                      buttonClassName="act mt-5 w-full justify-center"
                    />
                  ) : (
                    <button
                      onClick={() => setImportedCheckoutTarget({ id: ip.id, name: ip.name })}
                      className="act act-primary mt-5 w-full justify-center"
                    >
                      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 11V7a4 4 0 00-8 0v4M5 9h14l1 11H4L5 9z" />
                      </svg>
                      Vedi dettagli e acquista
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {detailTarget && (
        <ProductDetailModal
          product={detailTarget}
          customerKind={detailTarget.category === "INTERNAL" ? customerKind : undefined}
          ctaLabel={
            detailTarget.category !== "INTERNAL"
              ? "Acquista ora"
              : referralCode
                ? "Chiudi"
                : "Attiva nuovo contratto"
          }
          onClose={() => setDetailTarget(null)}
          onBuy={(versionId, name) => {
            const target = detailTarget;
            setDetailTarget(null);
            if (target.category !== "INTERNAL") setCheckoutTarget({ versionId, name });
            // Same pratica as the button atop "I miei Contratti", with this package
            // preselected for every POD.
            else if (!referralCode) setActivationTarget(target);
          }}
        />
      )}

      {checkoutTarget && (
        <ProductCheckoutModal
          productVersionId={checkoutTarget.versionId}
          productName={checkoutTarget.name}
          onClose={() => setCheckoutTarget(null)}
        />
      )}

      {importedCheckoutTarget && (
        <ImportedProductCheckoutModal
          importedProductId={importedCheckoutTarget.id}
          productName={importedCheckoutTarget.name}
          onClose={() => setImportedCheckoutTarget(null)}
        />
      )}

      {partnerShopTarget?.source === "CJ" && (
        <CjProductModal product={partnerShopTarget.product} onClose={() => setPartnerShopTarget(null)} />
      )}
      {partnerShopTarget?.source === "SHOPIFY" && (
        <ShopifyProductModal product={partnerShopTarget.product} onClose={() => setPartnerShopTarget(null)} />
      )}
      {partnerShopTarget?.source === "ALIEXPRESS" && (
        <AliexpressProductModal product={partnerShopTarget.product} onClose={() => setPartnerShopTarget(null)} />
      )}
      {partnerShopTarget?.source === "SOSNET_MARKET" && (
        <SosnetMarketProductModal
          product={partnerShopTarget.product as SosnetMarketProductRead}
          onClose={() => setPartnerShopTarget(null)}
        />
      )}

      {activationTarget && (
        // Opens a new pratica with this package preselected for every compatible
        // point, changeable per point.
        <ContractRequestWizard
          initialProduct={activationTarget}
          customerKind={customerKind}
          accountEmail={accountEmail}
          holder={{ firstName: myCustomer?.first_name, lastName: myCustomer?.last_name, pec: myCustomer?.pec }}
          onClose={() => {
            setActivationTarget(null);
            queryClient.invalidateQueries({ queryKey: ["contract-requests"] });
          }}
        />
      )}
    </div>
  );
}
