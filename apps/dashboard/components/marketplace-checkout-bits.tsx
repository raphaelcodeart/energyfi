"use client";

/**
 * Pieces shared by the Marketplace checkouts: labelled field, numbered step,
 * money formatting and bank-transfer discount. Presentation and pure
 * arithmetic only, no state or API calls.
 */

export type DeliveryAddress = {
  recipient_name: string;
  recipient_phone: string;
  address_line1: string;
  address_line2: string;
  city: string;
  province: string;
  postal_code: string;
};

export const inputClass = "w-full rounded-lg field px-3 py-2 text-sm focus:border-brand-500";

export function euro(cents: number): string {
  return (cents / 100).toLocaleString("it-IT", { style: "currency", currency: "EUR" });
}

export function sosnetCash(cents: number): string {
  return `${(cents / 100).toLocaleString("it-IT", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} SosnetCash`;
}

/**
 * Mirrors rules.bank_transfer_discount_cents: % of the residual, rounded half
 * up to the cent. A preview only; the server recomputes and freezes it on the order.
 */
export function bankTransferDiscount(residualCents: number, percentage: number): number {
  if (residualCents <= 0 || percentage <= 0) return 0;
  return Math.floor((residualCents * percentage + 50) / 100);
}

/**
 * Address complete enough to ship to, using the server's minimums so the
 * button never enables for an order that would be refused.
 */
export function addressComplete(address: DeliveryAddress): boolean {
  return (
    address.recipient_name.trim().length >= 2 &&
    address.recipient_phone.trim().length >= 6 &&
    address.address_line1.trim().length >= 3 &&
    !!address.city.trim() &&
    !!address.province.trim() &&
    address.postal_code.trim().length >= 3
  );
}

export function Field({
  label, children, className = "",
}: { label: string; children: React.ReactNode; className?: string }) {
  return (
    <label className={`block ${className}`}>
      <span className="block text-[10px] font-semibold text-surface-400 light:text-surface-500 uppercase tracking-wide mb-1">
        {label}
      </span>
      {children}
    </label>
  );
}

export function Section({
  n, title, done, children,
}: { n: number; title: string; done?: boolean; children: React.ReactNode }) {
  return (
    <div className="p-4 rounded-xl border border-white/10 light:border-surface-200 space-y-3">
      <div className="flex items-center gap-2.5">
        <span
          className={`flex items-center justify-center w-6 h-6 rounded-full text-[11px] font-bold shrink-0 text-white ${
            done ? "bg-success-500" : "bg-brand-600"
          }`}
        >
          {done ? "✓" : n}
        </span>
        <p className="text-sm font-semibold text-white light:text-surface-900">{title}</p>
      </div>
      {children}
    </div>
  );
}

/** Delivery address form, shared by every Marketplace checkout so labels stay consistent. */
export function AddressFields({
  address, onChange,
}: { address: DeliveryAddress; onChange: (next: DeliveryAddress) => void }) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-6 gap-3">
      <Field label="Nome e cognome" className="sm:col-span-3">
        <input className={inputClass} value={address.recipient_name} maxLength={50} autoComplete="name"
          onChange={(e) => onChange({ ...address, recipient_name: e.target.value })} />
      </Field>
      <Field label="Telefono (per il corriere)" className="sm:col-span-3">
        <input className={inputClass} value={address.recipient_phone} maxLength={20} inputMode="tel" autoComplete="tel"
          onChange={(e) => onChange({ ...address, recipient_phone: e.target.value })} />
      </Field>
      <Field label="Indirizzo e numero civico" className="sm:col-span-4">
        <input className={inputClass} value={address.address_line1} maxLength={255} autoComplete="address-line1"
          onChange={(e) => onChange({ ...address, address_line1: e.target.value })} />
      </Field>
      <Field label="Scala, interno (facoltativo)" className="sm:col-span-2">
        <input className={inputClass} value={address.address_line2} maxLength={255} autoComplete="address-line2"
          onChange={(e) => onChange({ ...address, address_line2: e.target.value })} />
      </Field>
      <Field label="CAP" className="sm:col-span-2">
        <input className={inputClass} value={address.postal_code} maxLength={12} inputMode="numeric" autoComplete="postal-code"
          onChange={(e) => onChange({ ...address, postal_code: e.target.value })} />
      </Field>
      <Field label="Città" className="sm:col-span-3">
        <input className={inputClass} value={address.city} maxLength={50} autoComplete="address-level2"
          onChange={(e) => onChange({ ...address, city: e.target.value })} />
      </Field>
      <Field label="Provincia" className="sm:col-span-1">
        <input className={inputClass} value={address.province} maxLength={50} placeholder="MI"
          onChange={(e) => onChange({ ...address, province: e.target.value.toUpperCase() })} />
      </Field>
    </div>
  );
}
