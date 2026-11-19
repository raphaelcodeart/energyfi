/** Who can buy which product, and what it really costs.
 *
 * Mirrors `apps/api/app/modules/catalog/pricing.py` so the catalog does not
 * offer a contract the server would refuse. Keep them in sync; the server
 * is authoritative.
 */

const PRIVATE = "PRIVATE";
const BUSINESS = "BUSINESS";
const BOTH = "BOTH";

/** Legacy `products.customer_type` values (PMI, ENERGY_INTENSIVE, ...)
    collapse onto BUSINESS. Unknown values fail open (visible to everyone):
    wrongly hiding a product is worse than showing one too many. */
export function normalizeProductCustomerType(value: string | null | undefined): string {
  if (!value) return BOTH;
  const upper = value.trim().toUpperCase();
  if (upper === PRIVATE || upper === BUSINESS || upper === BOTH) return upper;
  if (["SOLE_PROPRIETOR", "PMI", "CONDOMINIUM", "ENERGY_INTENSIVE"].includes(upper)) return BUSINESS;
  return BOTH;
}

/** Not the same grouping as the one deciding between a person's name and a
    company name: a sole proprietor has a person's name but also a VAT
    number, so here it counts as a business. */
export function isBusinessCustomer(customerKind: string | null | undefined): boolean {
  return ["SOLE_PROPRIETOR", "COMPANY", "CONDOMINIUM"].includes((customerKind ?? "").trim().toUpperCase());
}

export function productAllowsCustomerKind(
  productCustomerType: string | null | undefined,
  customerKind: string | null | undefined
): boolean {
  const normalized = normalizeProductCustomerType(productCustomerType);
  if (normalized === BOTH) return true;
  // Unknown customer kind (e.g. not loaded yet): fail open.
  if (!customerKind) return true;
  if (normalized === BUSINESS) return isBusinessCustomer(customerKind);
  return !isBusinessCustomer(customerKind);
}

export type PriceBreakdown = {
  netCents: number;
  /** Percentage points (22), not a fraction. 0 for a private customer. */
  vatRate: number;
  vatCents: number;
  grossCents: number;
};

/** A contract for a private individual carries no VAT; for a business it is
 * net + VAT. The customer decides whether VAT applies, the product decides
 * the rate.
 *
 * A null `customerKind` (viewer unknown, e.g. the shop grid) shows the
 * product's own rate.
 */
export function computePrice(
  netCents: number,
  productVatPercentage: number | null | undefined,
  customerKind: string | null | undefined,
  { assumeBusinessWhenUnknown = true }: { assumeBusinessWhenUnknown?: boolean } = {}
): PriceBreakdown {
  const rateApplies = customerKind == null ? assumeBusinessWhenUnknown : isBusinessCustomer(customerKind);
  const rate = rateApplies && productVatPercentage ? productVatPercentage : 0;
  // Round half-up on the cent, matching catalog/pricing.py::_vat_cents.
  const vatCents = rate > 0 && netCents > 0 ? Math.round((netCents * rate) / 100) : 0;
  return { netCents, vatRate: rate, vatCents, grossCents: netCents + vatCents };
}

/** Mirrors catalog/pricing.py::RECURRING_PRODUCT_TYPES: only these are sold
    as a periodic fee. PHYSICAL/DIGITAL products are one-off prices whatever
    billing period their version carries. */
export function isRecurringProductType(productType: string | null | undefined): boolean {
  return ["ENERGY_CONTRACT", "SUBSCRIPTION"].includes((productType ?? "").toUpperCase());
}

export function formatEuroCents(cents: number): string {
  return (cents / 100).toLocaleString("it-IT", { style: "currency", currency: "EUR" });
}

// --- Marketplace: VAT is included in the price -------------------
//
// Contracts are quoted net with VAT added on top (computePrice). Marketplace
// prices are final consumer prices, so VAT is extracted, not added.
//
// As on the server, which freezes `vat_amount_cents` on the order, the taxable
// base is the amount minus the bank-transfer discount. SosnetCash does not
// lower it: it is a means of payment, not a discount.

/** VAT contained in a gross amount, half-cent rounded up.
 *
 *  `taxableGrossCents` is amount minus bank-transfer discount. Preview only:
 *  once the order exists, its frozen `vat_amount_cents` is authoritative. */
export function includedVatCents(taxableGrossCents: number, vatPercentage: number | null | undefined): number {
  const rate = vatPercentage ?? 0;
  if (taxableGrossCents <= 0 || rate <= 0) return 0;
  // gross × rate / (100 + rate), half-cent up. Integer arithmetic identical to
  // marketplaces/rules.py::vat_included_cents (floor((2n + d) / 2d)) so the
  // preview and the order agree to the cent.
  const denominator = 100 + rate;
  return Math.floor((2 * taxableGrossCents * rate + denominator) / (2 * denominator));
}

/** VAT to add on top of a net amount, as rules.vat_added_cents (half-cent
 *  up). Preview only: quotes carry the server's figure, orders a frozen one. */
export function addedVatCents(netCents: number, vatPercentage: number | null | undefined): number {
  const rate = vatPercentage ?? 0;
  if (netCents <= 0 || rate <= 0) return 0;
  return Math.floor((2 * netCents * rate + 100) / 200);
}

export function vatLineLabel(vatPercentage: number): string {
  // Kept terse ("IVA 22%"): it sits among the summary lines, and whether VAT
  // is included is stated next to the price itself.
  return `IVA ${vatPercentage.toLocaleString("it-IT", { maximumFractionDigits: 2 })}%`;
}
