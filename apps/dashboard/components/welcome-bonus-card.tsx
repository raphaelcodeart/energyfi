"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { friendlyApiError } from "@/lib/api-error";

type WelcomeBonusStatus = { available: boolean; amount_cents: number };

function sosnetCash(cents: number): string {
  return `${(cents / 100).toLocaleString("it-IT", { minimumFractionDigits: 0, maximumFractionDigits: 2 })} SosnetCash`;
}

async function fetchWelcomeBonus(): Promise<WelcomeBonusStatus> {
  const res = await fetch("/api/proxy/wallets/me/welcome-bonus");
  if (!res.ok) throw new Error("Impossibile verificare l'omaggio di benvenuto.");
  return res.json();
}

/** One-off welcome bonus card on the dashboard home. Renders nothing when
    `available` is false (wallets/schemas.py::WelcomeBonusStatusRead).
    Claiming is idempotent server-side, keyed on the user id. */
export function WelcomeBonusCard() {
  const queryClient = useQueryClient();
  const { data: bonus } = useQuery({
    queryKey: ["wallet", "welcome-bonus"],
    queryFn: fetchWelcomeBonus,
  });

  const [claiming, setClaiming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [justClaimed, setJustClaimed] = useState(false);

  async function handleClaim() {
    setClaiming(true);
    setError(null);
    try {
      const res = await fetch("/api/proxy/wallets/me/welcome-bonus/claim", { method: "POST" });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      setJustClaimed(true);
      // Refresh bonus status, wallet balance and the home stat cards.
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["wallet"] }),
        queryClient.invalidateQueries({ queryKey: ["accounting"] }),
      ]);
    } catch (err: any) {
      setError(err.message || "Impossibile riscattare l'omaggio.");
      setClaiming(false);
    }
  }

  // Brief success message before the card disappears.
  if (justClaimed) {
    return (
      <div className="panel pop relative overflow-hidden rounded-3xl p-6 flex items-center gap-4 ring-1 ring-success-500/30">
        <span className="pulse-ring grid h-12 w-12 shrink-0 place-items-center rounded-2xl bg-success-500/20 text-success-400">
          <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
          </svg>
        </span>
        <div>
          <p className="kpi-label">Fatto</p>
          <p className="mt-1 text-xl font-black tracking-tight text-white">Omaggio riscattato!</p>
          <p className="mt-0.5 text-xs text-surface-300">
            {sosnetCash(bonus?.amount_cents ?? 0)} sono già disponibili sul tuo wallet.
          </p>
        </div>
      </div>
    );
  }

  if (!bonus?.available) return null;

  return (
    <div className="panel rise sheen relative overflow-hidden rounded-3xl p-6 sm:p-7">
      {/* Decorative glow; pointer-events-none keeps it click-through. */}
      <div className="pointer-events-none absolute -top-16 -right-16 w-56 h-56 rounded-full bg-gradient-to-br from-brand-500/40 to-accent-500/20 blur-3xl" />
      <div className="relative flex flex-col sm:flex-row sm:items-center gap-5">
        <span className="float-soft grid h-16 w-16 shrink-0 place-items-center rounded-2xl bg-gradient-to-br from-brand-500 to-accent-500 text-white shadow-lg shadow-brand-500/30">
          <svg className="w-8 h-8" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M12 8v13m0-13V6a2 2 0 112 2h-2zm0 0V5.5A2.5 2.5 0 109.5 8H12zM5 12h14M5 12a2 2 0 110-4h14a2 2 0 110 4M5 12v7a2 2 0 002 2h10a2 2 0 002-2v-7" />
          </svg>
        </span>
        <div className="flex-1 min-w-0">
          <p className="kpi-label">Omaggio di benvenuto</p>
          <p className="mt-1 text-xl font-black tracking-tight text-white">
            Il tuo omaggio di benvenuto ti aspetta
          </p>
          <p className="text-sm text-surface-300 mt-1">
            Ricevi <strong className="text-gradient font-black">{sosnetCash(bonus.amount_cents)}</strong> sul tuo
            wallet, da usare subito per i tuoi acquisti. Puoi riscattarlo una sola volta.
          </p>
          {error && <p className="text-xs text-danger-400 mt-2">{error}</p>}
        </div>
        <button
          onClick={handleClaim}
          disabled={claiming}
          className="act act-primary shrink-0 !px-6 !py-3 !text-sm disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {claiming ? "Riscatto in corso..." : "Riscatta il tuo omaggio"}
        </button>
      </div>
    </div>
  );
}
