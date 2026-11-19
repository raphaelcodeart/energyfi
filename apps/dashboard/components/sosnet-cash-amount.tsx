/**
 * An SosnetCash amount with the currency name stacked underneath, so the
 * number is what the eye scans and the label makes clear it is not euro
 * (docs/business-rules.md: wallet credit must never look like real money).
 * Number colour and size are inherited from the parent cell.
 */

function formatCents(cents: number): string {
  return (cents / 100).toLocaleString("it-IT", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export function SosnetCashAmount({
  cents,
  sign,
  align = "right",
}: {
  cents: number;
  /** "+" / "-" prefix; omit for a balance. */
  sign?: "+" | "-";
  align?: "right" | "left";
}) {
  return (
    <span className={`inline-flex flex-col leading-tight ${align === "right" ? "items-end" : "items-start"}`}>
      <span className="tabular-nums">
        {sign}
        {formatCents(cents)}
      </span>
      {/* Inherits the parent's colour at reduced opacity so the label matches its row. */}
      <span className="text-[9px] font-bold uppercase tracking-wider opacity-70">SosnetCash</span>
    </span>
  );
}
