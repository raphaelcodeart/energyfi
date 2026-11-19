"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

/*
 * Home balances: the signed-in person's MAMIX and MamiCash wallets, read from
 * Mamify (GET /external-wallet/me, a read-only call; the server keeps the
 * answer for 2 minutes). Someone who is not in the Mamify network sees why
 * instead of a misleading zero.
 */

type ExternalWalletRead = {
  connected: boolean;
  provider: string;
  account: string | null;
  mamix_cents: number | null;
  mamicash_cents: number | null;
  mamicash_personal_cents: number | null;
  mamicash_business_cents: number | null;
  updated_at: string | null;
  error: string | null;
};

type Key = "mamix_cents" | "mamicash_personal_cents" | "mamicash_business_cents";

function amount(cents: number | null | undefined): string {
  if (cents == null) return "—";
  return (cents / 100).toLocaleString("it-IT", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

const TILES: { key: Key; label: string; unit: string; hint: string; icon: string; bg: string }[] = [
  { key: "mamix_cents", label: "Saldo MAMIX", unit: "MAMIX", hint: "Nel tuo wallet Mamix", icon: "M", bg: "linear-gradient(135deg,#216eff,#47e2ff)" },
  { key: "mamicash_personal_cents", label: "MamiCash personale", unit: "MAMICASH", hint: "Nel tuo wallet personale", icon: "C", bg: "linear-gradient(135deg,#f59e0b,#446cef)" },
  { key: "mamicash_business_cents", label: "MamiCash aziendale", unit: "MAMICASH", hint: "Nel wallet aziendale", icon: "B", bg: "linear-gradient(135deg,#7c3aed,#47e2ff)" },
];

export function ExternalWalletStats() {
  const qc = useQueryClient();
  const [refreshing, setRefreshing] = useState(false);
  const { data, isLoading } = useQuery({
    queryKey: ["external-wallet", "me"],
    queryFn: async (): Promise<ExternalWalletRead | null> => {
      const res = await fetch("/api/proxy/external-wallet/me");
      if (!res.ok) return null;
      return res.json();
    },
    staleTime: 60_000,
  });
  const connected = data?.connected ?? false;

  const refresh = async () => {
    setRefreshing(true);
    try {
      const res = await fetch("/api/proxy/external-wallet/me?fresh=true");
      if (res.ok) qc.setQueryData(["external-wallet", "me"], await res.json());
    } finally {
      setRefreshing(false);
    }
  };

  const updated = data?.updated_at
    ? new Date(data.updated_at).toLocaleString("it-IT", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })
    : null;

  return (
    <div className="space-y-3">
      <div className="grid gap-4 md:grid-cols-3">
        {TILES.map((tile) => (
          <div key={tile.key} data-tilt className="panel relative overflow-hidden rounded-3xl p-6">
            <span className="grid h-11 w-11 place-items-center rounded-2xl text-lg font-black text-white shadow-lg" style={{ background: tile.bg }}>
              {tile.icon}
            </span>
            <p className="kpi-label mt-5">{tile.label}</p>
            <div className="mt-2 flex items-baseline gap-2">
              {isLoading ? (
                <span className="inline-block h-8 w-28 animate-pulse rounded-lg bg-white/10" aria-label="Caricamento" />
              ) : (
                <span className="kpi-value">{connected ? amount(data?.[tile.key]) : "—"}</span>
              )}
              <span className="text-sm font-bold text-surface-300">{tile.unit}</span>
            </div>
            <p className="mt-2 text-xs text-surface-400">{connected ? tile.hint : "Saldo non disponibile"}</p>
          </div>
        ))}
      </div>
      {!isLoading && (
        <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-surface-300">
          {connected ? (
            <span>
              Totale MamiCash <b className="text-white">{amount(data?.mamicash_cents)}</b> · saldi letti da Mamify
              {updated ? ` alle ${updated}` : ""}
              {data?.error ? <span className="text-warn-300"> · Mamify ora non risponde: sono gli ultimi saldi letti.</span> : null}
            </span>
          ) : (
            <span>
              {data?.error
                ? `Non riesco a leggere i saldi da Mamify: ${data.error}`
                : "I saldi MAMIX e MamiCash si vedono quando il tuo accesso è collegato al tuo account Mamify."}
            </span>
          )}
          {connected && (
            <button type="button" className="act" onClick={() => void refresh()} disabled={refreshing}>
              {refreshing ? "Aggiorno…" : "Aggiorna saldi"}
            </button>
          )}
        </div>
      )}
    </div>
  );
}
