"use client";

const MAX_SUPPLY_POINTS = 10;

/** One POD or PDR code plus its meter number. Shared by every screen that
    collects supply-point codes, so wording and behavior stay aligned. */
export type CodeEntry = { code: string; meterNumber: string };

export function emptyEntries(count: number): CodeEntry[] {
  return Array.from({ length: count }, () => ({ code: "", meterNumber: "" }));
}

/** Resizes to a new quantity, keeping values in surviving rows. */
export function resizeEntries(prev: CodeEntry[], count: number): CodeEntry[] {
  if (prev.length === count) return prev;
  const next = [...prev];
  while (next.length < count) next.push({ code: "", meterNumber: "" });
  next.length = count;
  return next;
}

/** Quantity stepper, worded as a question ("Quanti contratti luce?") so it is
    clearly a count, distinct from the code rows below. */
function QuantityStepper({ label, value, onChange }: { label: string; value: number; onChange: (n: number) => void }) {
  return (
    <div className="space-y-1">
      <label className="text-[10px] font-semibold text-surface-300 light:text-surface-600 uppercase block">{label}</label>
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={() => onChange(Math.max(1, value - 1))}
          className="w-8 h-8 rounded-lg bg-white/5 light:bg-surface-900/5 border border-white/10 light:border-surface-300 text-white light:text-surface-900 font-bold hover:bg-white/10 transition cursor-pointer disabled:opacity-40"
          disabled={value <= 1}
        >
          −
        </button>
        <span className="w-8 text-center text-sm font-bold text-white light:text-surface-900 tabular-nums">{value}</span>
        <button
          type="button"
          onClick={() => onChange(Math.min(MAX_SUPPLY_POINTS, value + 1))}
          className="w-8 h-8 rounded-lg bg-white/5 light:bg-surface-900/5 border border-white/10 light:border-surface-300 text-white light:text-surface-900 font-bold hover:bg-white/10 transition cursor-pointer disabled:opacity-40"
          disabled={value >= MAX_SUPPLY_POINTS}
        >
          +
        </button>
      </div>
    </div>
  );
}

/** The quantity question followed by that many code rows (with optional
    meter number). */
export function SupplyPointCodeFields({
  kind,
  entries,
  onChange,
}: {
  kind: "POD" | "PDR";
  entries: CodeEntry[];
  onChange: (entries: CodeEntry[]) => void;
}) {
  const label = kind === "POD" ? "Quanti contratti luce? (uno per codice POD)" : "Quanti contratti gas? (uno per codice PDR)";
  const placeholder = kind === "POD" ? "IT001E..." : "00000000000000";

  function updateEntry(i: number, field: keyof CodeEntry, value: string) {
    onChange(entries.map((entry, idx) => (idx === i ? { ...entry, [field]: value } : entry)));
  }

  return (
    <div className="space-y-3 pt-3 border-t border-white/5 light:border-surface-200">
      <QuantityStepper label={label} value={entries.length} onChange={(n) => onChange(resizeEntries(entries, n))} />
      <div className="space-y-2">
        {entries.map((entry, i) => (
          <div key={i} className="grid grid-cols-2 gap-2">
            <div className="space-y-1">
              <label className="text-[10px] font-semibold text-surface-300 light:text-surface-600 uppercase block">
                Codice {kind} {entries.length > 1 ? `#${i + 1}` : ""}
              </label>
              <input
                required
                value={entry.code}
                onChange={(e) => updateEntry(i, "code", e.target.value)}
                placeholder={placeholder}
                className="w-full rounded-xl field px-3 py-2.5 text-sm uppercase focus:border-brand-500"
              />
            </div>
            <div className="space-y-1">
              <label className="text-[10px] font-semibold text-surface-300 light:text-surface-600 uppercase block">Contatore (opz.)</label>
              <input
                value={entry.meterNumber}
                onChange={(e) => updateEntry(i, "meterNumber", e.target.value)}
                className="w-full rounded-xl field px-3 py-2.5 text-sm focus:border-brand-500"
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
