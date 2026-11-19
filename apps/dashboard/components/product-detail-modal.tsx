"use client";

import type { ProductCatalogRead } from "@/lib/types";
import { ProductThumbnail } from "@/components/product-thumbnail";
import { computePrice, isRecurringProductType } from "@/lib/product-audience";

const BILLING_LABELS: Record<string, string> = {
  MONTHLY: "/mese",
  QUARTERLY: "/trimestre",
  ANNUAL: "/anno",
};

function euro(cents: number): string {
  return (cents / 100).toLocaleString("it-IT", { style: "currency", currency: "EUR" });
}

// Wallet credit is SosnetCash, never plain EUR.
function sosnetCash(cents: number): string {
  return `${(cents / 100).toLocaleString("it-IT", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} SosnetCash`;
}

/** Product page shown before checkout.

    Also the package "Anteprima" while configuring a pratica point: there
    `customerKind` is known, the price is the periodic fee times the contract
    months (VAT only for businesses), and the button selects the package
    instead of buying it. */
export function ProductDetailModal({
  product,
  onClose,
  onBuy,
  ctaLabel = "Acquista ora",
  customerKind,
}: {
  product: ProductCatalogRead;
  onClose: () => void;
  onBuy: (versionId: string, name: string) => void;
  ctaLabel?: string;
  customerKind?: string | null;
}) {
  const v = product.current_version!;
  const isContract = product.category === "INTERNAL";
  const contractPrice = computePrice(v.contract_net_amount_cents, v.vat_percentage, customerKind ?? null, {
    assumeBusinessWhenUnknown: false,
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 light:bg-surface-900/40 backdrop-blur-sm animate-fade-in">
      <div className="w-full max-w-2xl panel panel-hover rounded-2xl border-white/10 light:border-surface-300 bg-surface-950 light:bg-white pop max-h-[90vh] overflow-y-auto">
        <div className="relative h-64 sm:h-72">
          <ProductThumbnail imageUrl={v.image_url} alt={v.name} iconClassName="w-16 h-16 text-brand-400/40" />
          <button
            onClick={onClose}
            className="absolute top-3 right-3 p-1.5 rounded-lg bg-surface-950/60 hover:bg-surface-950/80 text-white transition cursor-pointer"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
          {product.category !== "INTERNAL" && v.credit_discount_percentage > 0 && (
            <span className="absolute bottom-3 left-3 px-2.5 py-1 rounded-full text-[11px] font-bold border bg-success-500/90 text-white border-success-400/50 shadow-lg">
              Fino al {v.credit_discount_percentage}% pagabile in SosnetCash
            </span>
          )}
        </div>

        <div className="p-6 space-y-5">
          <div>
            <h2 className="text-xl font-bold text-white light:text-surface-900">{v.name}</h2>
            {v.description && (
              <p className="text-sm text-surface-400 light:text-surface-500 mt-2 whitespace-pre-wrap">{v.description}</p>
            )}
          </div>

          {isContract ? (
            <div className="flex flex-wrap items-end gap-6 p-5 rounded-xl bg-white/5 light:bg-surface-900/5 border border-white/10 light:border-surface-200">
              <div>
                <p className="text-[10px] font-semibold text-surface-500 uppercase tracking-wide">Canone</p>
                <div className="flex items-baseline gap-1.5">
                  <span className="text-3xl font-extrabold text-white light:text-surface-900 tabular-nums">{euro(v.base_price_cents)}</span>
                  <span className="text-xs text-surface-500">{BILLING_LABELS[v.billing_period] ?? ""}</span>
                </div>
                {v.contract_billing_periods > 1 && (
                  <p className="text-[11px] text-surface-400 light:text-surface-500 mt-0.5">
                    × {v.contract_billing_periods} = {euro(contractPrice.netCents)}
                    {v.contract_duration_months ? ` per ${v.contract_duration_months} mesi` : ""}
                  </p>
                )}
                <p className="text-[10px] text-surface-500 mt-0.5">
                  {contractPrice.vatCents > 0
                    ? `+ IVA ${contractPrice.vatRate}% = ${euro(contractPrice.grossCents)} totale`
                    : "IVA non applicata"}
                </p>
              </div>
              {v.contract_cashback_percentage > 0 && (
                <div className="pl-6 border-l border-white/10 light:border-surface-300">
                  <p className="text-[10px] font-semibold text-success-500 uppercase tracking-wide">Cashback</p>
                  <p className="text-3xl font-extrabold text-success-400 tabular-nums">{v.contract_cashback_percentage}%</p>
                  <p className="text-[10px] text-surface-500 mt-0.5">in SosnetCash, a ogni pagamento</p>
                </div>
              )}
            </div>
          ) : (
          <div className="flex flex-wrap items-end gap-6 p-5 rounded-xl bg-white/5 light:bg-surface-900/5 border border-white/10 light:border-surface-200">
            <div>
              <p className="text-[10px] font-semibold text-surface-500 uppercase tracking-wide">Prezzo</p>
              <div className="flex items-baseline gap-1.5">
                <span className="text-3xl font-extrabold text-white light:text-surface-900 tabular-nums">{euro(v.base_price_cents)}</span>
                <span className="text-xs text-surface-500">{isRecurringProductType(product.product_type) ? BILLING_LABELS[v.billing_period] ?? "" : ""}</span>
              </div>
              {v.vat_percentage != null && (
                <p className="text-[10px] text-surface-500 mt-0.5">
                  + IVA {v.vat_percentage}% ({euro(Math.round(v.base_price_cents * (1 + v.vat_percentage / 100)))} tot.)
                </p>
              )}
              {v.initial_fee_cents > 0 && (
                <p className="text-[10px] text-surface-500 mt-0.5">
                  + {euro(v.initial_fee_cents)} contributo di attivazione
                </p>
              )}
            </div>
            {product.category !== "INTERNAL" && v.credit_discount_percentage > 0 && (
              <div className="pl-6 border-l border-white/10 light:border-surface-300">
                <p className="text-[10px] font-semibold text-success-500 uppercase tracking-wide">SosnetCash usabili</p>
                <p className="text-3xl font-extrabold text-success-400 tabular-nums">
                  {sosnetCash(Math.round((v.base_price_cents * v.credit_discount_percentage) / 100))}
                </p>
                <p className="text-[10px] text-surface-500 mt-0.5">dal tuo wallet SOSNET</p>
              </div>
            )}
          </div>
          )}

          <button
            onClick={() => onBuy(v.id, v.name)}
            className="w-full flex items-center justify-center gap-2 px-6 py-3.5 rounded-xl bg-gradient-to-r from-brand-600 to-accent-500 hover:from-brand-500 hover:to-accent-400 text-white text-sm font-bold shadow-lg shadow-brand-500/20 transition-all duration-200 cursor-pointer active:scale-[0.98]"
          >
            <svg className="w-4.5 h-4.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 11V7a4 4 0 00-8 0v4M5 9h14l1 11H4L5 9z" />
            </svg>
            {ctaLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
