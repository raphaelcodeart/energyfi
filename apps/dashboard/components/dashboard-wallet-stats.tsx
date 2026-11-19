"use client";

import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import type { WalletRead, WalletTransactionRead } from "@/lib/types";

const CASHBACK_SOURCES = new Set([
  "ORDER_CASHBACK_BASE", "ORDER_CASHBACK_BONUS", "INVOICE_REDEMPTION_BASE", "INVOICE_REDEMPTION_BONUS",
  "CONTRACT_CASHBACK",
]);

/**
 * Eased count-up from the previous value to `value` over `durationMs`,
 * without an animation library. Re-runs whenever `value` changes.
 */
function useCountUp(value: number, durationMs = 900): number {
  const [display, setDisplay] = useState(value);
  const fromRef = useRef(value);
  const frameRef = useRef<number | null>(null);

  useEffect(() => {
    const from = fromRef.current;
    const to = value;
    if (from === to) return;
    const start = performance.now();
    function tick(now: number) {
      const progress = Math.min((now - start) / durationMs, 1);
      const eased = 1 - Math.pow(1 - progress, 3); // ease-out-cubic
      setDisplay(Math.round(from + (to - from) * eased));
      if (progress < 1) {
        frameRef.current = requestAnimationFrame(tick);
      } else {
        fromRef.current = to;
      }
    }
    frameRef.current = requestAnimationFrame(tick);
    return () => {
      if (frameRef.current) cancelAnimationFrame(frameRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);

  return display;
}

function formatSosnetCash(cents: number): string {
  return (cents / 100).toLocaleString("it-IT", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

async function fetchMyWallet(): Promise<WalletRead> {
  const res = await fetch("/api/proxy/wallets/me");
  if (!res.ok) throw new Error("Impossibile caricare il wallet.");
  return res.json();
}

async function fetchMyTransactions(): Promise<WalletTransactionRead[]> {
  const res = await fetch("/api/proxy/wallets/me/transactions");
  if (!res.ok) throw new Error("Impossibile caricare le transazioni.");
  return res.json();
}

/** Animated stat card for the balance/cashback figures on the dashboard home. */
function StatCard({
  label, cents, tone, icon, hint, ratio,
}: {
  label: string;
  cents: number;
  tone: "orange" | "emerald" | "sky";
  icon: React.ReactNode;
  hint?: string;
  /** Share of the largest of the three figures, drawn as a meter. */
  ratio?: number | null;
}) {
  const animated = useCountUp(cents);
  const glow: Record<"orange" | "emerald" | "sky", string> = {
    orange: "from-brand-400/50 to-accent-400/10",
    emerald: "from-success-400/40 to-accent-400/10",
    sky: "from-info-400/40 to-accent-400/10",
  };

  return (
    <div data-tilt className="panel relative overflow-hidden rounded-3xl p-6">
      <div className="mb-5 flex items-start justify-between">
        <span className="orb" style={{ "--orb-h": tone === "orange" ? 350 : tone === "emerald" ? 380 : 330 } as React.CSSProperties}>{icon}</span>
      </div>
      <p className="kpi-label">{label}</p>
      <p className="kpi-value mt-3">
        {formatSosnetCash(animated)} <span className="align-top text-sm font-bold opacity-80">SosnetCash</span>
      </p>
      {ratio != null && (
        <div className="meter mt-4">
          <i style={{ width: `${Math.max(3, Math.min(100, ratio * 100))}%` }} />
        </div>
      )}
      {hint && <p className="mt-2 text-[11px] text-surface-300">{hint}</p>}
      <span className={`pointer-events-none absolute -right-8 -top-8 h-32 w-32 rounded-full bg-gradient-to-br ${glow[tone]} blur-2xl`} />
    </div>
  );
}

/**
 * Wallet balance and cashback earned/spent at a glance, shared by the
 * customer and promoter homes. Full history and CSV export live in the
 * Wallet/Contabilità tabs.
 */
export function DashboardWalletStats() {
  const { data: wallet } = useQuery({ queryKey: ["wallet", "me"], queryFn: fetchMyWallet });
  const { data: transactions } = useQuery({ queryKey: ["wallet", "me", "transactions"], queryFn: fetchMyTransactions });

  const list = transactions ?? [];
  const cashbackEarnedCents = list
    .filter((t) => t.source && CASHBACK_SOURCES.has(t.source))
    .reduce((sum, t) => sum + t.amount_cents, 0);
  const spentCents = wallet
    ? list
        .filter((t) => t.from_wallet_id === wallet.id)
        .reduce((sum, t) => sum + t.amount_cents, 0)
    : 0;

  const balanceCents = wallet?.balance_cents ?? 0;
  const peak = Math.max(balanceCents, cashbackEarnedCents, spentCents);
  const share = (cents: number) => (peak > 0 ? Math.max(0, cents) / peak : null);

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
      <StatCard
        label="Saldo Wallet"
        cents={balanceCents}
        ratio={share(balanceCents)}
        tone="orange"
        hint="Disponibile per i tuoi acquisti"
        icon={
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a2 2 0 00-2-2H7a2 2 0 00-2 2m16 0v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6m16 0V9a2 2 0 00-2-2H5a2 2 0 00-2 2v3m16 0h-4a1 1 0 00-1 1v0a1 1 0 001 1h4" />
          </svg>
        }
      />
      <StatCard
        label="Cashback Accumulato"
        cents={cashbackEarnedCents}
        ratio={share(cashbackEarnedCents)}
        tone="emerald"
        hint="Totale ricevuto da ordini e riscatti"
        icon={
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V6m0 10v2" />
          </svg>
        }
      />
      <StatCard
        label="SosnetCash Consumati"
        cents={spentCents}
        ratio={share(spentCents)}
        tone="sky"
        hint="Totale speso in acquisti e trasferimenti"
        icon={
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 7h6m0 10v-3m-3 3v-6m-3 6v-1m6-13H9a2 2 0 00-2 2v14a2 2 0 002 2h6a2 2 0 002-2V6a2 2 0 00-2-2z" />
          </svg>
        }
      />
    </div>
  );
}
