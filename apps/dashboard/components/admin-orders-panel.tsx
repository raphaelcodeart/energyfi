"use client";

import { Fragment, useEffect, useState, type CSSProperties } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Pagination, usePagination } from "@/components/pagination";
import { ProductThumbnail } from "@/components/product-thumbnail";
import { Chip, Figure, Identity, KpiTile, RowActions, Stack, type ChipTone } from "@/components/ui/data-cells";
import { friendlyApiError } from "@/lib/api-error";
import { vatLineLabel } from "@/lib/product-audience";
import type {
  AliexpressOrderItemRead,
  AliexpressOrderRead,
  CustomerRead,
  CjOrderRead,
  ShopifyOrderRead,
  ImportedOrderRead,
  ImportedProductAdminRead,
  OrderRead,
  ProductCatalogRead,
} from "@/lib/types";

const STATUS_LABELS: Record<string, string> = {
  AWAITING_PAYMENT: "Attesa pagamento residuo",
  PAID: "Pagato",
  CANCELLED: "Annullato",
};
const STATUS_TONES: Record<string, ChipTone> = {
  AWAITING_PAYMENT: "warn",
  PAID: "ok",
  CANCELLED: "bad",
};
const PAYMENT_METHOD_LABELS: Record<string, string> = {
  BANK_TRANSFER: "Bonifico",
  CARD: "Carta (Stripe)",
};

/**
 * Same unification as customer-orders-panel.tsx::UnifiedOrder: orders for
 * catalog products (orders) and imported products (imported_product_orders)
 * live in separate tables only to keep the import mechanism isolated (see
 * imported_products/models.py). Here they form one list managed identically;
 * `source` only selects which endpoint an action calls.
 */
type UnifiedOrder = {
  id: string;
  source: "standard" | "imported" | "partner" | "shopify" | "aliexpress";
  /**
   * Shop Sosnet Partner supplier-side state, shown as a hint; sending and
   * tracking happen in "Shop Sosnet Partner → Ordini".
   */
  fulfillment_status?: string;
  cj_payment_status?: string;
  customer_display_name: string;
  product_name: string;
  /** Lines of a cart order and, for AliExpress, the supplier order number each landed on. */
  items?: AliexpressOrderItemRead[];
  item_supplier_orders?: { item_id: string; product_name: string; aliexpress_order_id: string | null }[];
  product_image_url: string | null;
  amount_cents: number;
  credit_applied_cents: number;
  residual_amount_cents: number;
  /** Marketplace orders: bank-transfer discount, already deducted from residual_amount_cents. */
  bank_transfer_discount_cents?: number;
  /**
   * Marketplace orders: VAT included in the total, frozen on the order. Absent
   * on some orders, in which case nothing is shown.
   */
  vat_amount_cents?: number;
  vat_percentage?: number;
  status: "AWAITING_PAYMENT" | "PAID" | "CANCELLED";
  payment_method: "BANK_TRANSFER" | "CARD";
  payment_proof_uploaded_at: string | null;
  cancellation_reason: string | null;
  created_at: string;
};

type UnifiedQuote = {
  product_name: string;
  amount_cents: number;
  credit_discount_percentage: number;
  max_creditable_cents: number;
  customer_wallet_balance_cents: number;
  bank_transfer_available: boolean;
  card_available: boolean;
};

function ordersBasePath(source: UnifiedOrder["source"]): string {
  if (source === "partner") return "/api/proxy/cj/orders";
  if (source === "shopify") return "/api/proxy/shopify/orders";
  if (source === "aliexpress") return "/api/proxy/aliexpress/orders";
  return source === "imported" ? "/api/proxy/imported-products/orders" : "/api/proxy/orders";
}

function euro(cents: number): string {
  return (cents / 100).toLocaleString("it-IT", { style: "currency", currency: "EUR" });
}

// Wallet credit is SosnetCash, never EUR (same helper as wallet-panel.tsx).
// Bank transfer and card amounts stay in euro().
function sosnetCash(cents: number): string {
  return `${(cents / 100).toLocaleString("it-IT", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} SosnetCash`;
}

function shortDate(iso: string): string {
  return new Date(iso).toLocaleDateString("it-IT", { day: "2-digit", month: "short", year: "numeric" });
}

function timeOf(iso: string): string {
  return `ore ${new Date(iso).toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" })}`;
}

/**
 * Must match customer-orders-panel.tsx::orderCode so customer and admin see
 * the same code regardless of source.
 */
/**
 * Display name of an order: the sequential `order_code`, falling back to the
 * leading UUID digits for orders that predate the sequence, so their
 * existing references stay traceable.
 */
function orderCode(order: { id: string; order_code?: string }): string {
  return order.order_code ?? order.id.slice(0, 8).toUpperCase();
}

function shippingText(status: string | undefined): string {
  return `Spedizione: ${status === "SHIPPED" ? "spedito" : status === "DELIVERED" ? "consegnato" : "in lavorazione"}`;
}

/** Supplier-side hint for paid marketplace orders; handled on each shop's own page. */
function fulfillmentHint(o: UnifiedOrder): { text: string; warn: boolean } | null {
  if (o.status !== "PAID") return null;
  const f = o.fulfillment_status;
  if (o.source === "shopify") {
    return {
      warn: f === "ERROR" || f === "NOT_SENT" || f === "CANCELLED",
      text: f === "NOT_SENT"
        ? "Da inviare al negozio Shopify: Prodotti Shopify → Ordini"
        : f === "ERROR"
          ? "Invio al negozio Shopify non riuscito: Prodotti Shopify → Ordini"
          : f === "CANCELLED"
            ? "Annullato nel negozio Shopify: Prodotti Shopify → Ordini"
            : shippingText(f),
    };
  }
  if (o.source === "aliexpress") {
    return {
      warn: f === "ERROR" || f === "NOT_SENT" || f === "CANCELLED",
      text: f === "NOT_SENT"
        ? "Da inviare ad AliExpress: Shop AliExpress → Ordini"
        : f === "ERROR"
          ? "Invio ad AliExpress non riuscito: Shop AliExpress → Ordini"
          : f === "CANCELLED"
            ? "Annullato su AliExpress: Shop AliExpress → Ordini"
            : shippingText(f),
    };
  }
  if (o.source === "partner") {
    return {
      warn: f === "ERROR" || f === "NOT_SENT" || o.cj_payment_status === "PAYMENT_REQUIRED",
      text: o.cj_payment_status === "PAYMENT_REQUIRED"
        ? "Pagamento CJ richiesto: Shop Sosnet Partner → Ordini"
        : f === "NOT_SENT"
          ? "Da inviare al fornitore: Shop Sosnet Partner → Ordini"
          : f === "ERROR"
            ? "Invio al fornitore non riuscito: Shop Sosnet Partner → Ordini"
            : shippingText(f),
    };
  }
  return null;
}

async function fetchCustomers(): Promise<CustomerRead[]> {
  const res = await fetch("/api/proxy/customers");
  if (!res.ok) throw new Error("Impossibile caricare i clienti.");
  return res.json();
}

async function fetchProducts(): Promise<ProductCatalogRead[]> {
  const res = await fetch("/api/proxy/products");
  if (!res.ok) throw new Error("Impossibile caricare i prodotti.");
  return res.json();
}

async function fetchImportedProducts(): Promise<ImportedProductAdminRead[]> {
  const res = await fetch("/api/proxy/imported-products/products");
  if (!res.ok) throw new Error("Impossibile caricare i prodotti importati.");
  return res.json();
}

async function fetchOrders(statusFilter: string): Promise<UnifiedOrder[]> {
  const qs = statusFilter !== "ALL" ? `?status_filter=${statusFilter}` : "";
  const [standardRes, importedRes, partnerRes, shopifyRes, aliexpressRes] = await Promise.all([
    fetch(`/api/proxy/orders${qs}`),
    fetch(`/api/proxy/imported-products/orders${qs}`),
    fetch(`/api/proxy/cj/orders${qs}`),
    fetch(`/api/proxy/shopify/orders${qs}`),
    fetch(`/api/proxy/aliexpress/orders${qs}`),
  ]);
  if (!standardRes.ok || !importedRes.ok) throw new Error("Impossibile caricare gli ordini.");
  const standard: OrderRead[] = await standardRes.json();
  const imported: ImportedOrderRead[] = await importedRes.json();
  const merged: UnifiedOrder[] = [
    ...standard.map((o) => ({ ...o, source: "standard" as const })),
    ...imported.map((o) => ({
      ...o,
      source: "imported" as const,
      residual_amount_cents: o.amount_due_cents ?? o.residual_amount_cents,
    })),
    ...(partnerRes.ok ? ((await partnerRes.json()) as CjOrderRead[]) : []).map((o) => ({
      ...o,
      product_name: `${o.product_name}${o.quantity > 1 ? ` × ${o.quantity}` : ""} (Shop Sosnet Partner)`,
      source: "partner" as const,
      residual_amount_cents: o.amount_due_cents,
    })),
    // Shopify: confirmed here like every order; sending to the store and tracking
    // live on its own admin page.
    ...(shopifyRes.ok ? ((await shopifyRes.json()) as ShopifyOrderRead[]) : []).map((o) => ({
      ...o,
      product_name: `${o.product_name}${o.quantity > 1 ? ` × ${o.quantity}` : ""} (Shopify)`,
      source: "shopify" as const,
      residual_amount_cents: o.amount_due_cents,
    })),
    // AliExpress API: confirmed here, placed at AliExpress and tracked on its own
    // admin page.
    ...(aliexpressRes.ok ? ((await aliexpressRes.json()) as AliexpressOrderRead[]) : []).map((o) => ({
      ...o,
      // Multi-line cart orders show the item count, not the first item's name.
      product_name: ((o.items ?? []).length > 1
        ? `${(o.items ?? []).length} articoli`
        : `${o.product_name}${o.quantity > 1 ? ` × ${o.quantity}` : ""}`) + " (AliExpress)",
      source: "aliexpress" as const,
      residual_amount_cents: o.amount_due_cents,
    })),
  ];
  merged.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
  return merged;
}

async function fetchQuote(
  customerUserId: string, productRef: { id: string; source: "standard" | "imported" }
): Promise<UnifiedQuote> {
  const url = productRef.source === "imported"
    ? `/api/proxy/imported-products/orders/quote?customer_user_id=${customerUserId}&imported_product_id=${productRef.id}`
    : `/api/proxy/orders/quote?customer_user_id=${customerUserId}&product_version_id=${productRef.id}`;
  const res = await fetch(url);
  if (!res.ok) throw new Error("Impossibile calcolare il preventivo.");
  return res.json();
}

/**
 * Admin checkout for dropshipping/partner and imported products, handled as
 * one list with one creation form. Never for internal SOSNET products, which
 * are contracts ("Nuovo Contratto"). The imported catalog also has customer
 * self-checkout (customer-products-panel.tsx).
 */
export function AdminOrdersPanel() {
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState("AWAITING_PAYMENT");
  const [showCreate, setShowCreate] = useState(false);
  const [customerUserId, setCustomerUserId] = useState("");
  const [productRef, setProductRef] = useState<{ id: string; source: "standard" | "imported" } | null>(null);
  const [creditAmount, setCreditAmount] = useState("0.00");
  const [note, setNote] = useState("");
  const [createLoading, setCreateLoading] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [actionLoadingId, setActionLoadingId] = useState<string | null>(null);
  const [cancellingId, setCancellingId] = useState<string | null>(null);
  const [cancelReason, setCancelReason] = useState("");

  const { data: customers } = useQuery({ queryKey: ["admin", "customers"], queryFn: fetchCustomers });
  const { data: allProducts } = useQuery({ queryKey: ["admin", "products"], queryFn: fetchProducts });
  const { data: allImportedProducts } = useQuery({ queryKey: ["admin", "imported-products"], queryFn: fetchImportedProducts });
  const { data: orders, error: loadError } = useQuery({
    queryKey: ["admin", "orders", statusFilter],
    queryFn: () => fetchOrders(statusFilter),
  });

  const orderableCustomers = (customers ?? []).filter((c) => !!c.user_id);
  const orderableProducts = (allProducts ?? []).filter((p) => p.category !== "INTERNAL" && p.current_version);
  const orderableImportedProducts = (allImportedProducts ?? []).filter((p) => p.status === "ACTIVE");

  const { data: quote } = useQuery({
    queryKey: ["admin", "orders", "quote", customerUserId, productRef?.source, productRef?.id],
    queryFn: () => fetchQuote(customerUserId, productRef!),
    enabled: !!customerUserId && !!productRef,
  });

  // Default the credit field to the maximum usable amount whenever the quote
  // changes; the admin only lowers it to apply less.
  useEffect(() => {
    if (!quote) return;
    const maxUsable = Math.min(quote.max_creditable_cents, quote.customer_wallet_balance_cents);
    setCreditAmount((maxUsable / 100).toFixed(2));
  }, [quote]);

  async function invalidate() {
    await queryClient.invalidateQueries({ queryKey: ["admin", "orders"] });
    await queryClient.invalidateQueries({ queryKey: ["admin", "wallets"] });
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!productRef) return;
    const creditCents = Math.round(parseFloat(creditAmount.replace(",", ".")) * 100);
    if (!Number.isFinite(creditCents) || creditCents < 0) {
      setCreateError("Importo in SosnetCash non valido.");
      return;
    }
    setCreateLoading(true);
    setCreateError(null);
    try {
      const url = productRef.source === "imported" ? "/api/proxy/imported-products/orders" : "/api/proxy/orders";
      const body = productRef.source === "imported"
        ? { customer_user_id: customerUserId, imported_product_id: productRef.id, credit_applied_cents: creditCents, note: note || null }
        : { customer_user_id: customerUserId, product_version_id: productRef.id, credit_applied_cents: creditCents, note: note || null };
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      setShowCreate(false);
      setCustomerUserId("");
      setProductRef(null);
      setCreditAmount("0.00");
      setNote("");
      await invalidate();
    } catch (err: any) {
      setCreateError(err.message || "Impossibile creare l'ordine.");
    } finally {
      setCreateLoading(false);
    }
  }

  async function handleConfirmPayment(order: UnifiedOrder) {
    setActionLoadingId(order.id);
    try {
      const res = await fetch(`${ordersBasePath(order.source)}/${order.id}/confirm-payment`, { method: "POST" });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      await invalidate();
    } finally {
      setActionLoadingId(null);
    }
  }

  async function handleCancel(order: UnifiedOrder) {
    if (!cancelReason.trim()) return;
    setActionLoadingId(order.id);
    try {
      const res = await fetch(`${ordersBasePath(order.source)}/${order.id}/cancel`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reason: cancelReason.trim() }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      setCancellingId(null);
      setCancelReason("");
      await invalidate();
    } finally {
      setActionLoadingId(null);
    }
  }

  async function handleViewPaymentProof(order: UnifiedOrder) {
    setActionLoadingId(order.id);
    try {
      const res = await fetch(`${ordersBasePath(order.source)}/${order.id}/payment-proof-url`);
      if (!res.ok) throw new Error(await friendlyApiError(res));
      const { url } = await res.json();
      window.open(url, "_blank", "noopener,noreferrer");
    } finally {
      setActionLoadingId(null);
    }
  }

  // Pages whatever the status tabs leave.
  const pagination = usePagination(orders ?? []);

  const totalCents = (orders ?? []).reduce((sum, o) => sum + o.amount_cents, 0);
  const awaitingResidualCents = (orders ?? []).filter((o) => o.status === "AWAITING_PAYMENT").reduce((sum, o) => sum + o.residual_amount_cents, 0);
  const creditCents = (orders ?? []).reduce((sum, o) => sum + o.credit_applied_cents, 0);

  const residualPreview = quote
    ? quote.amount_cents - Math.min(
        Math.round((parseFloat(creditAmount.replace(",", ".")) || 0) * 100),
        quote.max_creditable_cents,
        quote.customer_wallet_balance_cents
      )
    : null;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="kpi-label">Vendite</div>
          <h2 className="mt-1 text-xl font-black tracking-tight text-white">Ordini marketplace</h2>
          <p className="mt-1 text-sm text-surface-400">
            Acquisti di prodotti dropshipping/partner e Acquisti SOSNET, con sconto in SosnetCash opzionale -- un unico elenco.
          </p>
        </div>
        <button
          type="button"
          onClick={() => { setShowCreate(!showCreate); setCreateError(null); }}
          className={`act ${showCreate ? "" : "act-primary"} shrink-0`}
        >
          {showCreate ? "Annulla" : "+ Nuovo ordine"}
        </button>
      </div>

      {showCreate && (
        <div className="panel rounded-3xl p-6 sm:p-7 pop">
          <div className="kpi-label">Checkout assistito</div>
          <h3 className="mt-1 mb-5 text-xl font-black tracking-tight text-white">Nuovo ordine per un cliente</h3>
          <form onSubmit={handleCreate} className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="space-y-1">
                <label className="text-xs font-semibold text-surface-300 uppercase block">Cliente</label>
                <select required value={customerUserId} onChange={(e) => setCustomerUserId(e.target.value)}
                  className="w-full rounded-xl field px-3 py-2.5 text-sm bg-surface-900 focus:border-brand-500">
                  <option value="">Seleziona...</option>
                  {orderableCustomers.map((c) => (
                    <option key={c.id} value={c.user_id!}>{c.display_name}</option>
                  ))}
                </select>
                <p className="text-[10px] text-surface-500">Solo clienti con un account collegato compaiono qui.</p>
              </div>
              <div className="space-y-1">
                <label className="text-xs font-semibold text-surface-300 uppercase block">Prodotto</label>
                <select
                  required
                  value={productRef ? `${productRef.source}:${productRef.id}` : ""}
                  onChange={(e) => {
                    const [source, id] = e.target.value.split(":");
                    setProductRef(id ? { id, source: source as "standard" | "imported" } : null);
                  }}
                  className="w-full rounded-xl field px-3 py-2.5 text-sm bg-surface-900 focus:border-brand-500"
                >
                  <option value="">Seleziona...</option>
                  {orderableProducts.length > 0 && (
                    <optgroup label="Catalogo prodotti">
                      {orderableProducts.map((p) => (
                        <option key={p.id} value={`standard:${p.current_version!.id}`}>
                          {p.current_version!.name} ({euro(p.current_version!.base_price_cents)})
                        </option>
                      ))}
                    </optgroup>
                  )}
                  {orderableImportedProducts.length > 0 && (
                    <optgroup label="Acquisti SOSNET">
                      {orderableImportedProducts.map((p) => (
                        <option key={p.id} value={`imported:${p.id}`}>
                          {p.name} ({euro(p.price_cents)})
                        </option>
                      ))}
                    </optgroup>
                  )}
                </select>
                <p className="text-[10px] text-surface-500">Solo prodotti dropshipping/partner/importati -- i prodotti Interno Sosnet si vendono come contratto.</p>
              </div>
            </div>

            {quote && (
              <div className="p-4 rounded-2xl bg-white/5 border border-white/10 space-y-3">
                <div className="grid grid-cols-3 gap-3 text-xs">
                  <div>
                    <p className="text-[10px] text-surface-500 uppercase">Prezzo prodotto</p>
                    <p className="font-semibold text-white">{euro(quote.amount_cents)}</p>
                  </div>
                  <div>
                    <p className="text-[10px] text-surface-500 uppercase">Sconto max in SosnetCash</p>
                    <p className="font-semibold text-brand-400">{quote.credit_discount_percentage}% ({euro(quote.max_creditable_cents)})</p>
                  </div>
                  <div>
                    <p className="text-[10px] text-surface-500 uppercase">Saldo cliente</p>
                    <p className="font-semibold text-white">{euro(quote.customer_wallet_balance_cents)}</p>
                  </div>
                </div>
                <div className="space-y-1 pt-2 border-t border-white/5">
                  <label className="text-[10px] font-semibold text-surface-300 uppercase block">SosnetCash da applicare</label>
                  <input
                    inputMode="decimal"
                    value={creditAmount}
                    onChange={(e) => setCreditAmount(e.target.value)}
                    className="w-full max-w-[160px] rounded-lg field px-3 py-1.5 text-sm focus:border-brand-500"
                  />
                </div>
                {residualPreview != null && (
                  <p className="text-xs text-surface-300">
                    Residuo da bonifico: <strong className="text-brand-400">{euro(Math.max(residualPreview, 0))}</strong>
                    {residualPreview <= 0 && <span className="text-success-400"> -- copre l&apos;intero importo, nessun bonifico necessario</span>}
                  </p>
                )}
              </div>
            )}

            <div className="space-y-1">
              <label className="text-xs font-semibold text-surface-300 uppercase block">Nota (opzionale)</label>
              <input value={note} onChange={(e) => setNote(e.target.value)}
                className="w-full rounded-xl field px-3 py-2 text-sm focus:border-brand-500" />
            </div>

            <button type="submit" disabled={createLoading || !quote}
              className="px-4 py-2 rounded-xl bg-brand-600 hover:bg-brand-500 text-xs font-semibold text-white transition cursor-pointer disabled:opacity-50">
              {createLoading ? "Creazione..." : "Crea Ordine"}
            </button>
            {createError && (
              <div className="p-3 rounded-lg bg-danger-500/10 border border-danger-500/20 text-danger-400 text-xs">{createError}</div>
            )}
          </form>
        </div>
      )}

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 stagger">
        <div style={{ "--i": 0 } as CSSProperties}>
          <KpiTile label="Ordini in vista" value={orders ? orders.length : "—"} hint={statusFilter === "ALL" ? "Tutti gli stati" : STATUS_LABELS[statusFilter]} />
        </div>
        <div style={{ "--i": 1 } as CSSProperties}>
          <KpiTile label="Valore complessivo" value={orders ? euro(totalCents) : "—"} hint="Totale degli ordini elencati" />
        </div>
        <div style={{ "--i": 2 } as CSSProperties}>
          <KpiTile label="Da incassare" value={orders ? euro(awaitingResidualCents) : "—"} hint="Residui in attesa di pagamento" />
        </div>
        <div style={{ "--i": 3 } as CSSProperties}>
          <KpiTile label="SosnetCash usato" value={orders ? sosnetCash(creditCents) : "—"} hint="Sconti applicati dal wallet" />
        </div>
      </div>

      <div className="subnav">
        {["AWAITING_PAYMENT", "PAID", "CANCELLED", "ALL"].map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => setStatusFilter(s)}
            className="subnav-pill"
            data-active={statusFilter === s}
          >
            {s === "ALL" ? "Tutti" : STATUS_LABELS[s]}
          </button>
        ))}
      </div>

      {loadError && <p className="text-sm text-danger-400">Impossibile caricare gli ordini.</p>}

      <div className="panel rounded-3xl p-4 sm:p-6">
        <div className="mb-4 flex items-end justify-between gap-3">
          <div>
            <div className="kpi-label">Registro</div>
            <h3 className="mt-1 text-xl font-black tracking-tight text-white">Ordini e pagamenti</h3>
          </div>
        </div>
        {orders === undefined ? (
          <p className="text-center py-10 text-surface-400 text-sm">Caricamento...</p>
        ) : orders.length === 0 ? (
          <div className="flex flex-col items-center justify-center gap-3 py-14 text-center">
            <span className="orb float-soft" aria-hidden="true">
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M3 3h2l.4 2M7 13h10l4-8H5.4M7 13L5.4 5M7 13l-2.293 2.293c-.63.63-.184 1.707.707 1.707H17m0 0a2 2 0 100 4 2 2 0 000-4zm-8 2a2 2 0 11-4 0 2 2 0 014 0z" />
              </svg>
            </span>
            <p className="text-sm text-surface-300">Nessun ordine in questo stato.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left">
                  <th className="px-4 py-3">Acquisto</th>
                  <th className="px-4 py-3">Acquirente</th>
                  <th className="px-4 py-3">Quando</th>
                  <th className="px-4 py-3">Situazione</th>
                  <th className="px-4 py-3 text-right">Valore</th>
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody>
                {pagination.pageItems.map((o) => {
                  const hint = fulfillmentHint(o);
                  const creditRatio = o.amount_cents > 0 ? o.credit_applied_cents / o.amount_cents : null;
                  return (
                    <Fragment key={o.id}>
                      <tr className="align-top">
                        <td className="px-4 py-3">
                          <div className="flex min-w-[220px] items-start gap-3">
                            <div className="w-11 h-11 rounded-xl overflow-hidden shrink-0 border border-white/10">
                              <ProductThumbnail imageUrl={o.product_image_url} alt={o.product_name} iconClassName="w-5 h-5 text-brand-300/50" />
                            </div>
                            <div className="min-w-0">
                              <div className="text-[13px] font-semibold text-white">{o.product_name}</div>
                              <span className="tag-id" title={o.id}>#{orderCode(o)}</span>
                              {(o.items ?? []).length > 1 && (
                                <ul className="mt-1 space-y-0.5">
                                  {(o.items ?? []).map((line) => {
                                    const supplier = (o.item_supplier_orders ?? []).find((r) => r.item_id === line.id);
                                    return (
                                      <li key={line.id} className="text-[11px] text-surface-400">
                                        · {line.quantity} × {line.product_name}
                                        {line.variant_label ? ` (${line.variant_label})` : ""} — {euro(line.line_total_cents)}
                                        {supplier?.aliexpress_order_id && (
                                          <span className="font-mono text-surface-500">
                                            {" "}· ord. {supplier.aliexpress_order_id}
                                          </span>
                                        )}
                                      </li>
                                    );
                                  })}
                                </ul>
                              )}
                            </div>
                          </div>
                        </td>
                        <td className="px-4 py-3">
                          <Identity
                            name={o.customer_display_name}
                            detail={PAYMENT_METHOD_LABELS[o.payment_method] ?? o.payment_method}
                          />
                        </td>
                        <td className="px-4 py-3 whitespace-nowrap">
                          <Stack title={shortDate(o.created_at)} detail={timeOf(o.created_at)} />
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex max-w-[260px] flex-col items-start gap-1.5">
                            <Chip tone={STATUS_TONES[o.status] ?? "muted"} live={o.status === "AWAITING_PAYMENT"}>
                              {STATUS_LABELS[o.status]}
                            </Chip>
                            {o.payment_proof_uploaded_at && o.status === "AWAITING_PAYMENT" && (
                              <Chip tone="info">Prova caricata</Chip>
                            )}
                            {hint && (
                              <span className={`text-[11px] ${hint.warn ? "text-warn-400" : "text-info-400"}`}>{hint.text}</span>
                            )}
                            {o.cancellation_reason && (
                              <span className="text-[11px] text-danger-400">Motivo annullamento: {o.cancellation_reason}</span>
                            )}
                          </div>
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex justify-end">
                            <Figure
                              value={euro(o.amount_cents)}
                              ratio={o.credit_applied_cents > 0 ? creditRatio : null}
                              detail={
                                <>
                                  {o.status === "AWAITING_PAYMENT" ? "Residuo" : "Pagato in euro"} {euro(o.residual_amount_cents)}
                                  {o.credit_applied_cents > 0 && <><br />{sosnetCash(o.credit_applied_cents)}</>}
                                  {(o.bank_transfer_discount_cents ?? 0) > 0 && <><br />sconto bonifico -{euro(o.bank_transfer_discount_cents!)}</>}
                                  {(o.vat_amount_cents ?? 0) > 0 && <><br />{vatLineLabel(o.vat_percentage ?? 0)} {euro(o.vat_amount_cents!)}</>}
                                </>
                              }
                            />
                          </div>
                        </td>
                        <td className="px-4 py-3">
                          {o.status === "AWAITING_PAYMENT" && (
                            <RowActions>
                              {o.payment_method === "CARD" ? (
                                <span className="text-[11px] text-surface-400 whitespace-nowrap">In attesa di conferma Stripe</span>
                              ) : (
                                <button
                                  type="button"
                                  onClick={() => handleConfirmPayment(o)}
                                  disabled={actionLoadingId === o.id}
                                  className="act act-primary"
                                >
                                  {actionLoadingId === o.id ? "..." : "Conferma bonifico ricevuto"}
                                </button>
                              )}
                              {o.payment_proof_uploaded_at && (
                                <button
                                  type="button"
                                  onClick={() => handleViewPaymentProof(o)}
                                  disabled={actionLoadingId === o.id}
                                  className="act"
                                >
                                  Vedi prova di pagamento
                                </button>
                              )}
                              <button
                                type="button"
                                onClick={() => setCancellingId(cancellingId === o.id ? null : o.id)}
                                className="act"
                              >
                                Annulla
                              </button>
                            </RowActions>
                          )}
                        </td>
                      </tr>
                      {cancellingId === o.id && (
                        <tr>
                          <td colSpan={6} className="px-4 py-3">
                            <div className="flex flex-wrap items-end gap-2">
                              <div className="space-y-1 flex-1 max-w-sm">
                                <label className="kpi-label block">Motivo annullamento</label>
                                <input autoFocus value={cancelReason} onChange={(e) => setCancelReason(e.target.value)}
                                  className="w-full rounded-xl field px-3 py-1.5 text-sm focus:border-brand-500" />
                              </div>
                              <button
                                type="button"
                                onClick={() => handleCancel(o)}
                                disabled={actionLoadingId === o.id}
                                className="px-4 py-2 rounded-xl bg-danger-600 hover:bg-danger-500 text-xs font-semibold text-white transition cursor-pointer disabled:opacity-50"
                              >
                                {actionLoadingId === o.id ? "..." : "Conferma annullamento"}
                              </button>
                            </div>
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
      <Pagination {...pagination} label="ordini" />
    </div>
  );
}
