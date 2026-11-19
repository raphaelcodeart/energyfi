"use client";

import { Fragment, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Pagination, usePagination } from "@/components/pagination";
import { ProductThumbnail } from "@/components/product-thumbnail";
import { Chip, Figure, RowActions, Stack, type ChipTone } from "@/components/ui/data-cells";
import { friendlyApiError } from "@/lib/api-error";
import { vatLineLabel } from "@/lib/product-audience";
import type { AliexpressOrderItemRead, AliexpressOrderRead, SosnetMarketOrderRead, CjOrderRead, ImportedOrderRead, OrderRead, ShopifyOrderRead } from "@/lib/types";

const STATUS_LABELS: Record<string, string> = {
  AWAITING_PAYMENT: "In attesa di pagamento",
  PAID: "Pagato",
  CANCELLED: "Annullato",
};
const STATUS_TONES: Record<UnifiedOrder["status"], ChipTone> = {
  AWAITING_PAYMENT: "warn",
  PAID: "ok",
  CANCELLED: "bad",
};
const PAYMENT_METHOD_LABELS: Record<string, string> = {
  BANK_TRANSFER: "Bonifico",
  CARD: "Carta (Stripe)",
};

type OrderFilter = "ALL" | "PAID" | "AWAITING_PAYMENT" | "CANCELLED" | "BANK_TRANSFER" | "CARD";

const FILTER_TABS: { key: OrderFilter; label: string }[] = [
  { key: "ALL", label: "Tutti" },
  { key: "PAID", label: "Pagati" },
  { key: "AWAITING_PAYMENT", label: "In attesa" },
  { key: "CANCELLED", label: "Annullati" },
  { key: "BANK_TRANSFER", label: "Bonifico" },
  { key: "CARD", label: "Carta" },
];

/**
 * A purchase, whichever order table backs it: orders.id for catalog products,
 * imported_product_orders.id for the imported-products catalog (see
 * imported_products/models.py). The split only keeps the catalogs apart;
 * everywhere else the two form one history. `source` just routes actions to
 * the right endpoint and is never shown. Cashback fields, absent on imported
 * orders, are normalized to "not applicable" here.
 */
type UnifiedOrder = {
  id: string;
  source: "standard" | "imported" | "partner" | "shopify" | "aliexpress" | "sosnet_market";
  product_name: string;
  /** Order lines, when the order has several (cart). Absent for shops without a cart. */
  items?: AliexpressOrderItemRead[];
  /** Shop Sosnet Partner only: delivery tracking state. */
  shipping?: Pick<
    CjOrderRead,
    | "quantity" | "variant_label" | "shipping_cents" | "delivery_status" | "tracking_number" | "tracking_url"
    | "shipping_days" | "shipped_at" | "delivered_at" | "recipient_name" | "address_line1" | "address_line2"
    | "postal_code" | "city" | "province"
  >;
  product_image_url: string | null;
  amount_cents: number;
  credit_applied_cents: number;
  residual_amount_cents: number;
  /**
   * Marketplace orders: bank-transfer discount, already deducted from
   * residual_amount_cents; `bank_transfer_discount_percentage` is the current
   * setting shown on "Paga con bonifico". 0 elsewhere.
   */
  bank_transfer_discount_cents: number;
  bank_transfer_discount_percentage: number;
  /**
   * Marketplace orders: VAT included in the total, frozen on the order. 0 for
   * catalog orders and orders without a recorded VAT, in which case nothing is shown.
   */
  vat_amount_cents: number;
  vat_percentage: number;
  cashback_requested: boolean;
  cashback_surcharge_cents: number;
  cashback_credited_at: string | null;
  status: "AWAITING_PAYMENT" | "PAID" | "CANCELLED";
  payment_method: "BANK_TRANSFER" | "CARD";
  stripe_checkout_session_id: string | null;
  payment_proof_uploaded_at: string | null;
  note: string | null;
  paid_at: string | null;
  cancelled_at: string | null;
  cancellation_reason: string | null;
  created_at: string;
};

/**
 * Backend that this order's actions (pay, switch method, upload proof,
 * cancel...) route to; the only place `source` matters.
 */
function ordersBasePath(source: UnifiedOrder["source"]): string {
  if (source === "partner") return "/api/proxy/cj/orders";
  if (source === "shopify") return "/api/proxy/shopify/orders";
  if (source === "aliexpress") return "/api/proxy/aliexpress/orders";
  if (source === "sosnet_market") return "/api/proxy/sosnet-market/orders";
  return source === "imported" ? "/api/proxy/imported-products/orders" : "/api/proxy/orders";
}

/** Status of a paid Shop Sosnet Partner order, in customer-facing words. */
function shippingState(order: UnifiedOrder): { label: string; tone: ChipTone } | null {
  if (!order.shipping || order.status !== "PAID") return null;
  switch (order.shipping.delivery_status) {
    case "SHIPPED":
      return { label: "Spedito", tone: "info" };
    case "DELIVERED":
      return { label: "Consegnato", tone: "ok" };
    case "PROBLEM":
      return { label: "Problema con la spedizione: ti contattiamo", tone: "bad" };
    case "PREPARING":
      return { label: "In preparazione", tone: "warn" };
    default:
      return { label: "Ordine ricevuto", tone: "muted" };
  }
}

function euro(cents: number): string {
  return (cents / 100).toLocaleString("it-IT", { style: "currency", currency: "EUR" });
}

// Wallet credit is SosnetCash, never EUR (same helper as wallet-panel.tsx).
// Bank transfer and card amounts stay in euro().
function sosnetCash(cents: number): string {
  return `${(cents / 100).toLocaleString("it-IT", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} SosnetCash`;
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString("it-IT", { day: "numeric", month: "long", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

function shortDate(iso: string): string {
  return new Date(iso).toLocaleDateString("it-IT", { day: "2-digit", month: "short", year: "numeric" });
}

function timeOf(iso: string): string {
  return new Date(iso).toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" });
}

function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString("it-IT", { day: "numeric", month: "long", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

/**
 * Short reference derived from the UUID, identical here, in
 * admin-orders-panel.tsx and in the "Pagamento confermato" email, regardless
 * of source.
 */
/**
 * Display name of an order: the sequential `order_code`, falling back to the
 * leading UUID digits for orders that predate the sequence, so their
 * existing references stay traceable.
 */
function orderCode(order: { id: string; order_code?: string }): string {
  return order.order_code ?? order.id.slice(0, 8).toUpperCase();
}

async function fetchMyOrders(): Promise<UnifiedOrder[]> {
  const [standardRes, importedRes, partnerRes, shopifyRes, aliexpressRes, sosnetMarketRes] = await Promise.all([
    fetch("/api/proxy/orders/mine"),
    fetch("/api/proxy/imported-products/orders/mine"),
    fetch("/api/proxy/cj/orders/mine"),
    fetch("/api/proxy/shopify/orders/mine"),
    fetch("/api/proxy/aliexpress/orders/mine"),
    // Marketplace 4. A 404 (shop never opened) is read as an empty list.
    fetch("/api/proxy/sosnet-market/orders/mine"),
  ]);
  if (!standardRes.ok || !importedRes.ok) throw new Error("Impossibile caricare i tuoi ordini.");
  const standard: OrderRead[] = await standardRes.json();
  const imported: ImportedOrderRead[] = await importedRes.json();
  const partner: CjOrderRead[] = partnerRes.ok ? await partnerRes.json() : [];
  // Shopify: same shape and behaviour as CJ.
  const shopify: ShopifyOrderRead[] = shopifyRes.ok ? await shopifyRes.json() : [];
  // AliExpress API: same shape; a 404 means the shop was never switched on.
  const aliexpress: AliexpressOrderRead[] = aliexpressRes.ok ? await aliexpressRes.json() : [];
  const sosnetMarket: SosnetMarketOrderRead[] = sosnetMarketRes.ok ? await sosnetMarketRes.json() : [];
  const merged: UnifiedOrder[] = [
    ...standard.map((o) => ({
      ...o,
      source: "standard" as const,
      bank_transfer_discount_cents: 0,
      bank_transfer_discount_percentage: 0,
      // Contracts and catalog packages carry VAT in the product price; this row is
      // for Marketplaces only.
      vat_amount_cents: 0,
      vat_percentage: 0,
    })),
    ...imported.map((o) => ({
      ...o,
      source: "imported" as const,
      // AliExpress is also discounted for bank transfer.
      residual_amount_cents: o.amount_due_cents ?? o.residual_amount_cents,
      bank_transfer_discount_cents: o.bank_transfer_discount_cents ?? 0,
      bank_transfer_discount_percentage: o.bank_transfer_discount_percentage ?? 0,
      vat_amount_cents: o.vat_amount_cents ?? 0,
      vat_percentage: o.vat_percentage ?? 0,
      cashback_requested: false,
      cashback_surcharge_cents: 0,
      cashback_credited_at: null,
    })),
    ...partner.map((o) => ({
      ...o,
      source: "partner" as const,
      product_name: o.quantity > 1 ? `${o.product_name} × ${o.quantity}` : o.product_name,
      // Actual amount due: no discount when paying by card.
      residual_amount_cents: o.amount_due_cents,
      vat_amount_cents: o.vat_amount_cents ?? 0,
      vat_percentage: o.vat_percentage ?? 0,
      cashback_requested: false,
      cashback_surcharge_cents: 0,
      cashback_credited_at: null,
      shipping: o,
    })),
    ...shopify.map((o) => ({
      ...o,
      source: "shopify" as const,
      product_name: o.quantity > 1 ? `${o.product_name} × ${o.quantity}` : o.product_name,
      residual_amount_cents: o.amount_due_cents,
      vat_amount_cents: o.vat_amount_cents ?? 0,
      vat_percentage: o.vat_percentage ?? 0,
      cashback_requested: false,
      cashback_surcharge_cents: 0,
      cashback_credited_at: null,
      shipping: o,
    })),
    ...sosnetMarket.map((o) => ({
      ...o,
      source: "sosnet_market" as const,
      product_name: orderTitle(o),
      residual_amount_cents: o.amount_due_cents,
      vat_amount_cents: o.vat_amount_cents ?? 0,
      vat_percentage: o.vat_percentage ?? 0,
      cashback_requested: false,
      cashback_surcharge_cents: 0,
      cashback_credited_at: null,
      shipping: o,
    })),
    ...aliexpress.map((o) => ({
      ...o,
      source: "aliexpress" as const,
      product_name: orderTitle(o),
      residual_amount_cents: o.amount_due_cents,
      vat_amount_cents: o.vat_amount_cents ?? 0,
      vat_percentage: o.vat_percentage ?? 0,
      cashback_requested: false,
      cashback_surcharge_cents: 0,
      cashback_credited_at: null,
      shipping: o,
    })),
  ];
  merged.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
  return merged;
}

/**
 * List title of an order. Cart orders are summarised ("Cuffie BT + altri 2")
 * so the other items do not look missing.
 */
function orderTitle(o: {
  id: string;
  order_code?: string;
  product_name: string;
  quantity?: number;
  items?: { product_name: string }[];
}): string {
  const items = o.items ?? [];
  const first = items[0];
  if (items.length > 1 && first) return `${first.product_name} + altri ${items.length - 1}`;
  return (o.quantity ?? 1) > 1 ? `${o.product_name} × ${o.quantity}` : o.product_name;
}

async function fetchPaymentInfo(): Promise<{ iban: string | null; holder: string; instructions: string | null }> {
  const res = await fetch("/api/proxy/invoice-redemptions/payment-info");
  if (!res.ok) throw new Error("Impossibile caricare le coordinate di pagamento.");
  return res.json();
}

function OrderDetailModal({ order, onClose, onViewProof, viewProofLoading }: {
  order: UnifiedOrder;
  onClose: () => void;
  onViewProof: () => void;
  viewProofLoading: boolean;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-fade-in">
      <div className="w-full max-w-lg max-h-[85vh] overflow-y-auto panel rounded-3xl p-7 bg-surface-950 pop">
        <div className="flex items-start justify-between gap-4 mb-4">
          <div className="flex items-center gap-3 min-w-0">
            <div className="w-14 h-14 rounded-2xl overflow-hidden shrink-0 border border-white/15 shadow-lg shadow-brand-500/20">
              <ProductThumbnail imageUrl={order.product_image_url} alt={order.product_name} iconClassName="w-6 h-6 text-brand-400/40" />
            </div>
            <div className="min-w-0">
              <h3 className="text-xl font-black tracking-tight text-white truncate">{order.product_name}</h3>
              <p className="mt-0.5 text-xs text-surface-300">Ordine <span className="tag-id" title={order.id}>#{orderCode(order)}</span></p>
            </div>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-white/10 text-surface-400 hover:text-white transition cursor-pointer shrink-0">
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {(order.items ?? []).length > 1 && (
          <div className="mb-5 rounded-2xl border border-white/10 divide-y divide-white/5">
            {(order.items ?? []).map((line) => (
              <div key={line.id} className="flex items-center justify-between gap-3 px-3 py-2">
                <div className="min-w-0">
                  <p className="text-xs font-semibold text-white truncate">{line.product_name}</p>
                  {line.variant_label && <p className="text-[11px] text-surface-400 truncate">{line.variant_label}</p>}
                </div>
                <div className="text-right shrink-0">
                  <p className="text-[11px] text-surface-400">× {line.quantity}</p>
                  <p className="text-xs font-bold text-white tabular-nums">{euro(line.line_total_cents)}</p>
                </div>
              </div>
            ))}
          </div>
        )}

        <div className="flex items-center gap-2 mb-5 flex-wrap">
          <Chip tone={STATUS_TONES[order.status]} live={order.status === "AWAITING_PAYMENT"}>{STATUS_LABELS[order.status]}</Chip>
          <Chip tone="muted">{PAYMENT_METHOD_LABELS[order.payment_method] ?? order.payment_method}</Chip>
        </div>

        <div className="space-y-3 text-sm">
          <div className="grid grid-cols-2 gap-4 p-5 rounded-2xl bg-white/5 border border-white/10">
            <div>
              <p className="kpi-label">Totale</p>
              <p className="mt-1 text-lg font-black text-white tabular-nums">{euro(order.amount_cents)}</p>
            </div>
            {order.vat_amount_cents > 0 && (
              <div>
                <p className="kpi-label">{vatLineLabel(order.vat_percentage)}</p>
                <p className="mt-1 font-bold text-surface-200 tabular-nums">{euro(order.vat_amount_cents)}</p>
              </div>
            )}
            {order.credit_applied_cents > 0 && (
              <div>
                <p className="kpi-label">SosnetCash usati</p>
                <p className="mt-1 font-bold text-success-300 tabular-nums">-{sosnetCash(order.credit_applied_cents)}</p>
              </div>
            )}
            {order.cashback_surcharge_cents > 0 && (
              <div>
                <p className="kpi-label">Cashback richiesto</p>
                <p className="mt-1 font-bold text-brand-200 tabular-nums">+{euro(order.cashback_surcharge_cents)}</p>
              </div>
            )}
            {order.bank_transfer_discount_cents > 0 && (
              <div>
                <p className="kpi-label">Sconto pagamento con bonifico</p>
                <p className="mt-1 font-bold text-success-300 tabular-nums">-{euro(order.bank_transfer_discount_cents)}</p>
              </div>
            )}
            {order.status === "AWAITING_PAYMENT" && (
              <div>
                <p className="kpi-label">Residuo da pagare</p>
                <p className="mt-1 font-bold text-warn-300 tabular-nums">{euro(order.residual_amount_cents)}</p>
              </div>
            )}
          </div>

          <div className="space-y-1.5 text-xs text-surface-300">
            <p>Ordinato il <span className="text-white">{formatDateTime(order.created_at)}</span></p>
            {order.paid_at && <p>Pagato il <span className="text-success-400">{formatDateTime(order.paid_at)}</span></p>}
            {order.cancelled_at && (
              <p>Annullato il <span className="text-danger-400">{formatDateTime(order.cancelled_at)}</span>{order.cancellation_reason && ` -- ${order.cancellation_reason}`}</p>
            )}
            {order.payment_method === "CARD" && order.stripe_checkout_session_id && (
              <p className="break-all">ID sessione Stripe: <span className="font-mono text-surface-200">{order.stripe_checkout_session_id}</span></p>
            )}
            {order.payment_method === "BANK_TRANSFER" && (
              <p>Causale bonifico: <span className="font-mono text-brand-200">Ordine {orderCode(order)}</span></p>
            )}
            {order.cashback_requested && (
              <p>
                Cashback:{" "}
                {order.cashback_credited_at ? (
                  <span className="text-success-400">
                    accreditato il {formatDateTime(order.cashback_credited_at)} ({sosnetCash(order.amount_cents - order.credit_applied_cents + order.cashback_surcharge_cents)})
                  </span>
                ) : (
                  <span className="text-warn-400">richiesto, verrà accreditato a pagamento confermato</span>
                )}
              </p>
            )}
          </div>

          {order.shipping && (
            <div className="p-5 rounded-2xl bg-white/5 border border-white/10 space-y-2 text-xs">
              <div className="flex items-center justify-between gap-2">
                <p className="kpi-label">Spedizione</p>
                {shippingState(order) && (
                  <Chip tone={shippingState(order)!.tone} live={shippingState(order)!.tone === "warn"}>
                    {shippingState(order)!.label}
                  </Chip>
                )}
              </div>
              {order.shipping.variant_label && (
                <p className="text-surface-300">
                  {order.shipping.variant_label} · {order.shipping.quantity} {order.shipping.quantity === 1 ? "pezzo" : "pezzi"}
                  {" "}· spedizione {order.shipping.shipping_cents > 0 ? euro(order.shipping.shipping_cents) : "inclusa"}
                </p>
              )}
              <p className="text-surface-200">
                {order.shipping.recipient_name}, {order.shipping.address_line1}
                {order.shipping.address_line2 ? `, ${order.shipping.address_line2}` : ""}, {order.shipping.postal_code} {order.shipping.city} ({order.shipping.province})
              </p>
              {order.shipping.shipped_at && <p className="text-surface-300">Spedito il <span className="text-info-400">{formatDateTime(order.shipping.shipped_at)}</span></p>}
              {order.shipping.delivered_at && <p className="text-surface-300">Consegnato il <span className="text-success-400">{formatDateTime(order.shipping.delivered_at)}</span></p>}
              {!order.shipping.shipped_at && order.status === "PAID" && order.shipping.shipping_days && (
                <p className="text-surface-300">Consegna stimata in {order.shipping.shipping_days} giorni lavorativi dalla spedizione.</p>
              )}
              {order.shipping.tracking_number && (
                <p className="text-surface-300">
                  Tracking <span className="font-mono text-white">{order.shipping.tracking_number}</span>
                  {order.shipping.tracking_url && (
                    <a href={order.shipping.tracking_url} target="_blank" rel="noopener noreferrer" className="ml-2 font-semibold text-brand-200 hover:text-white">
                      Segui la spedizione →
                    </a>
                  )}
                </p>
              )}
            </div>
          )}

          {order.payment_proof_uploaded_at && (
            <button
              onClick={onViewProof}
              disabled={viewProofLoading}
              className="act w-full justify-center disabled:opacity-50"
            >
              {viewProofLoading ? "..." : `Vedi la prova di pagamento caricata il ${formatDate(order.payment_proof_uploaded_at)}`}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

/**
 * "I miei ordini": every product purchase, catalog and imported, as one
 * indistinguishable list (see UnifiedOrder). SOSNET contracts are Contract
 * rows, not orders, and live in "I miei Contratti".
 */
export function CustomerOrdersPanel() {
  const queryClient = useQueryClient();
  const { data: orders, isLoading, error } = useQuery({
    queryKey: ["customer", "orders", "mine"],
    queryFn: fetchMyOrders,
  });
  const [filter, setFilter] = useState<OrderFilter>("ALL");
  const [search, setSearch] = useState("");
  const [payingId, setPayingId] = useState<string | null>(null);
  const [payError, setPayError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [bankDetailsFor, setBankDetailsFor] = useState<string | null>(null);
  const [switchingId, setSwitchingId] = useState<string | null>(null);
  const [uploadingId, setUploadingId] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [proofTarget, setProofTarget] = useState<UnifiedOrder | null>(null);
  const [detailOrderId, setDetailOrderId] = useState<string | null>(null);
  const [viewProofLoading, setViewProofLoading] = useState(false);
  const { data: paymentInfo } = useQuery({
    queryKey: ["customer", "payment-info"],
    queryFn: fetchPaymentInfo,
    enabled: bankDetailsFor !== null,
  });

  async function invalidate() {
    await queryClient.invalidateQueries({ queryKey: ["customer", "orders"] });
  }

  async function startCardCheckout(order: UnifiedOrder) {
    setPayingId(order.id);
    try {
      // Opens Stripe in a new tab so a failed or abandoned payment never loses the
      // dashboard. success_url returns to "I miei Ordini" with a banner (see
      // customer-client-page.tsx).
      const returnUrl = new URL("/customer", window.location.origin);
      returnUrl.searchParams.set("tab", "orders");
      const successUrl = new URL(returnUrl);
      successUrl.searchParams.set("payment", "success");
      successUrl.searchParams.set("order_id", order.id);
      const cancelUrl = new URL(returnUrl);
      cancelUrl.searchParams.set("payment", "cancelled");

      const res = await fetch(
        `${ordersBasePath(order.source)}/mine/${order.id}/checkout-session?success_url=${encodeURIComponent(successUrl.toString())}&cancel_url=${encodeURIComponent(cancelUrl.toString())}`,
        { method: "POST" }
      );
      if (!res.ok) throw new Error(await friendlyApiError(res));
      const { checkout_url } = await res.json();
      window.open(checkout_url, "_blank", "noopener,noreferrer");
    } catch (err: any) {
      setPayError(err.message || "Impossibile avviare il pagamento.");
    } finally {
      setPayingId(null);
    }
  }

  function handlePay(order: UnifiedOrder) {
    setPayError(null);
    if (order.payment_method === "BANK_TRANSFER") {
      setBankDetailsFor(bankDetailsFor === order.id ? null : order.id);
      return;
    }
    startCardCheckout(order);
  }

  async function handleSwitchMethod(order: UnifiedOrder, newMethod: "CARD" | "BANK_TRANSFER") {
    setActionError(null);
    setSwitchingId(order.id);
    try {
      const res = await fetch(`${ordersBasePath(order.source)}/mine/${order.id}/payment-method`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ payment_method: newMethod }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      const updated = { ...(await res.json()), source: order.source } as UnifiedOrder;
      await invalidate();
      if (newMethod === "CARD") {
        // Go straight to checkout once the method is switched.
        await startCardCheckout(updated);
      } else {
        setBankDetailsFor(order.id);
      }
    } catch (err: any) {
      setActionError(err.message || "Impossibile cambiare il metodo di pagamento.");
    } finally {
      setSwitchingId(null);
    }
  }

  function openProofPicker(order: UnifiedOrder) {
    setActionError(null);
    setProofTarget(order);
    fileInputRef.current?.click();
  }

  async function handleProofSelected(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = ""; // allow re-selecting the same file later
    if (!file || !proofTarget) return;
    setUploadingId(proofTarget.id);
    setActionError(null);
    try {
      const body = new FormData();
      body.append("file", file);
      const res = await fetch(`${ordersBasePath(proofTarget.source)}/mine/${proofTarget.id}/payment-proof`, { method: "POST", body });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      await invalidate();
    } catch (err: any) {
      setActionError(err.message || "Impossibile caricare la prova di pagamento.");
    } finally {
      setUploadingId(null);
      setProofTarget(null);
    }
  }

  async function handleViewProof(order: UnifiedOrder) {
    setViewProofLoading(true);
    setActionError(null);
    try {
      const res = await fetch(`${ordersBasePath(order.source)}/mine/${order.id}/payment-proof-url`);
      if (!res.ok) throw new Error(await friendlyApiError(res));
      const { url } = await res.json();
      window.open(url, "_blank", "noopener,noreferrer");
    } catch (err: any) {
      setActionError(err.message || "Impossibile aprire la prova di pagamento.");
    } finally {
      setViewProofLoading(false);
    }
  }

  // Before the early returns: usePagination is a hook and must run on every render.
  const list = orders ?? [];
  const normalizedSearch = search.trim().toLowerCase();
  const filteredList = list.filter((o) => {
    if (filter !== "ALL") {
      if (filter === "BANK_TRANSFER" || filter === "CARD") {
        if (o.payment_method !== filter) return false;
      } else if (o.status !== filter) {
        return false;
      }
    }
    if (!normalizedSearch) return true;
    return (
      o.product_name.toLowerCase().includes(normalizedSearch) ||
      orderCode(o).toLowerCase().includes(normalizedSearch)
    );
  });
  const pagination = usePagination(filteredList);

  if (isLoading) {
    return <div className="panel rounded-3xl p-6 animate-pulse h-40" />;
  }

  if (error) {
    return (
      <div className="p-4 rounded-2xl bg-danger-500/10 border border-danger-500/30 text-danger-300 text-sm">
        Impossibile caricare i tuoi ordini.
      </div>
    );
  }

  if (list.length === 0) {
    return (
      <div className="panel rise rounded-3xl p-12 text-center">
        <svg className="float-soft w-14 h-14 text-surface-400 mx-auto mb-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />
        </svg>
        <h3 className="text-xl font-black tracking-tight text-white">Nessun ordine ancora</h3>
        <p className="text-sm text-surface-300 mt-1.5">
          I prodotti che acquisti dallo Shop compaiono qui, con lo stato del pagamento.
        </p>
      </div>
    );
  }

  const detailOrder = detailOrderId ? list.find((o) => o.id === detailOrderId) ?? null : null;

  return (
    <div className="space-y-5">
      <input ref={fileInputRef} type="file" accept="application/pdf,image/jpeg,image/png" className="hidden" onChange={handleProofSelected} />

      <div className="relative">
        <svg className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-surface-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-4.35-4.35M17 11a6 6 0 11-12 0 6 6 0 0112 0z" />
        </svg>
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Cerca per ID ordine o nome prodotto..."
          className="field w-full pl-11 pr-10 py-3.5 rounded-2xl text-sm"
        />
        {search && (
          <button
            type="button"
            onClick={() => setSearch("")}
            className="absolute right-3 top-1/2 -translate-y-1/2 p-1 rounded-full text-surface-400 hover:text-white hover:bg-white/10 transition cursor-pointer"
            title="Cancella ricerca"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        )}
      </div>

      <div className="subnav">
        {FILTER_TABS.map((tab) => {
          const count = tab.key === "ALL"
            ? list.length
            : list.filter((o) => (tab.key === "BANK_TRANSFER" || tab.key === "CARD" ? o.payment_method === tab.key : o.status === tab.key)).length;
          return (
            <button
              key={tab.key}
              onClick={() => setFilter(tab.key)}
              className="subnav-pill"
              data-active={filter === tab.key || undefined}
            >
              {tab.label}
              <span className="ml-1 opacity-70 tabular-nums">{count}</span>
            </button>
          );
        })}
      </div>

      {payError && (
        <div className="p-3.5 rounded-2xl bg-danger-500/10 border border-danger-500/30 text-danger-300 text-xs">{payError}</div>
      )}
      {actionError && (
        <div className="p-3.5 rounded-2xl bg-danger-500/10 border border-danger-500/30 text-danger-300 text-xs">{actionError}</div>
      )}

      {filteredList.length === 0 ? (
        <div className="panel rounded-3xl flex flex-col items-center gap-3 py-12 px-6 text-center">
          <svg className="float-soft w-10 h-10 text-surface-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M21 21l-4.35-4.35M17 11a6 6 0 11-12 0 6 6 0 0112 0z" />
          </svg>
          <p className="text-sm text-surface-300">Nessun ordine in questa categoria.</p>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr>
                <th className="px-4 py-3">Acquisto</th>
                <th className="px-4 py-3">Quando</th>
                <th className="px-4 py-3">Situazione</th>
                <th className="px-4 py-3 text-right">Valore</th>
                <th className="px-4 py-3"><span className="sr-only">Azioni</span></th>
              </tr>
            </thead>
            <tbody>
              {pagination.pageItems.map((o) => {
                const awaiting = o.status === "AWAITING_PAYMENT";
                const busy = payingId === o.id || switchingId === o.id || uploadingId === o.id;
                const ship = shippingState(o);
                return (
                  <Fragment key={o.id}>
                    <tr>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-3 min-w-[220px]">
                          <button
                            type="button"
                            onClick={() => setDetailOrderId(o.id)}
                            className="w-12 h-12 rounded-2xl overflow-hidden shrink-0 border border-white/15 shadow-lg shadow-brand-500/10 cursor-pointer transition-transform hover:scale-105 hover:-rotate-3"
                            title="Vedi dettagli ordine"
                          >
                            <ProductThumbnail imageUrl={o.product_image_url} alt={o.product_name} iconClassName="w-6 h-6 text-brand-400/40" />
                          </button>
                          <div className="min-w-0">
                            <button
                              type="button"
                              onClick={() => setDetailOrderId(o.id)}
                              className="block max-w-[260px] truncate text-[13.5px] font-bold text-white hover:text-brand-200 transition cursor-pointer text-left"
                            >
                              {o.product_name}
                            </button>
                            <div className="mt-0.5 flex items-center gap-2 text-[11px] text-surface-400">
                              <span className="tag-id" title={o.id}>#{orderCode(o)}</span>
                              <span>{PAYMENT_METHOD_LABELS[o.payment_method] ?? o.payment_method}</span>
                            </div>
                          </div>
                        </div>
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap">
                        <Stack title={shortDate(o.created_at)} detail={`ore ${timeOf(o.created_at)}`} />
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex flex-wrap items-center gap-1.5 max-w-[260px]">
                          <Chip tone={STATUS_TONES[o.status]} live={awaiting}>{STATUS_LABELS[o.status]}</Chip>
                          {ship && <Chip tone={ship.tone} live={ship.tone === "warn"}>{ship.label}</Chip>}
                          {o.cashback_requested && (
                            <Chip tone={o.cashback_credited_at ? "ok" : "accent"}>
                              {o.cashback_credited_at ? "✓ Cashback accreditato" : "Cashback richiesto"}
                            </Chip>
                          )}
                        </div>
                        {o.shipping?.tracking_url && (
                          <a href={o.shipping.tracking_url} target="_blank" rel="noopener noreferrer" className="mt-1.5 inline-block text-[11px] font-semibold text-info-300 hover:text-white">
                            Traccia pacco →
                          </a>
                        )}
                        {o.cancellation_reason && (
                          <p className="text-[11px] text-danger-300 mt-1 max-w-[260px]">Motivo annullamento: {o.cancellation_reason}</p>
                        )}
                        {awaiting && o.payment_proof_uploaded_at && (
                          <p className="text-[10.5px] text-success-300 mt-1">✓ Prova caricata il {formatDate(o.payment_proof_uploaded_at)}</p>
                        )}
                      </td>
                      <td className="px-4 py-3 text-right">
                        <Figure
                          value={euro(o.amount_cents)}
                          ratio={awaiting && o.amount_cents > 0 ? 1 - o.residual_amount_cents / o.amount_cents : null}
                          detail={
                            <span className="flex flex-col items-end gap-0.5">
                              {o.vat_amount_cents > 0 && <span>{vatLineLabel(o.vat_percentage)} {euro(o.vat_amount_cents)}</span>}
                              {o.credit_applied_cents > 0 && <span className="text-success-300">-{sosnetCash(o.credit_applied_cents)}</span>}
                              {awaiting && (
                                <span className="text-warn-300">
                                  Residuo {euro(o.residual_amount_cents)}
                                  {o.bank_transfer_discount_cents > 0 && ` (sconto bonifico -${euro(o.bank_transfer_discount_cents)})`}
                                </span>
                              )}
                              {!awaiting && o.bank_transfer_discount_cents > 0 && (
                                <span>-{euro(o.bank_transfer_discount_cents)} sconto bonifico</span>
                              )}
                            </span>
                          }
                        />
                      </td>
                      <td className="px-4 py-3">
                        <RowActions>
                          {awaiting && (
                            <button onClick={() => handlePay(o)} disabled={busy} className="act act-primary disabled:opacity-50">
                              {payingId === o.id ? "Apertura Stripe..." : o.payment_method === "CARD" ? "Paga con carta" : "Vedi coordinate bonifico"}
                            </button>
                          )}
                          {awaiting && o.payment_method === "BANK_TRANSFER" && (
                            <>
                              <button
                                onClick={() => handleSwitchMethod(o, "CARD")}
                                disabled={busy}
                                className="act disabled:opacity-50"
                                title={o.bank_transfer_discount_cents > 0 ? "Con carta paghi il prezzo pieno, senza lo sconto bonifico." : undefined}
                              >
                                {switchingId === o.id ? "..." : "Paga subito con carta"}
                              </button>
                              <button onClick={() => openProofPicker(o)} disabled={busy} className="act disabled:opacity-50">
                                {uploadingId === o.id
                                  ? "Caricamento..."
                                  : o.payment_proof_uploaded_at
                                    ? "Sostituisci prova di pagamento"
                                    : "Aggiungi prova di pagamento"}
                              </button>
                            </>
                          )}
                          {awaiting && o.payment_method !== "BANK_TRANSFER" && (
                            <button onClick={() => handleSwitchMethod(o, "BANK_TRANSFER")} disabled={busy} className="act disabled:opacity-50">
                              {switchingId === o.id
                                ? "..."
                                : o.bank_transfer_discount_percentage > 0
                                  ? `Paga con bonifico (-${o.bank_transfer_discount_percentage}%)`
                                  : "Paga con bonifico"}
                            </button>
                          )}
                          <button type="button" onClick={() => setDetailOrderId(o.id)} className="act">
                            Dettagli →
                          </button>
                        </RowActions>
                        {awaiting && o.payment_method === "BANK_TRANSFER" && o.bank_transfer_discount_cents > 0 && (
                          <p className="mt-1.5 text-[10px] text-surface-400">
                            Con carta paghi il prezzo pieno, senza lo sconto bonifico.
                          </p>
                        )}
                      </td>
                    </tr>
                    {bankDetailsFor === o.id && (
                      <tr>
                        <td colSpan={5} className="px-5 py-4">
                          <div className="pop grid gap-3 sm:grid-cols-3 text-xs">
                            {paymentInfo?.iban ? (
                              <>
                                <div>
                                  <p className="kpi-label">IBAN</p>
                                  <p className="mt-1 font-mono text-white break-all">{paymentInfo.iban}</p>
                                </div>
                                <div>
                                  <p className="kpi-label">Intestatario</p>
                                  <p className="mt-1 text-white">{paymentInfo.holder}</p>
                                </div>
                              </>
                            ) : (
                              <p className="sm:col-span-2 text-surface-300">Contatta l&apos;amministrazione per le coordinate bancarie.</p>
                            )}
                            <div>
                              <p className="kpi-label">Causale consigliata</p>
                              <p className="mt-1 font-mono text-brand-200">Ordine {orderCode(o)}</p>
                            </div>
                            {paymentInfo?.iban && paymentInfo.instructions && (
                              <p className="sm:col-span-3 text-surface-300">{paymentInfo.instructions}</p>
                            )}
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

      <Pagination {...pagination} label="ordini" />

      {detailOrder && (
        <OrderDetailModal
          order={detailOrder}
          onClose={() => setDetailOrderId(null)}
          onViewProof={() => handleViewProof(detailOrder)}
          viewProofLoading={viewProofLoading}
        />
      )}
    </div>
  );
}
