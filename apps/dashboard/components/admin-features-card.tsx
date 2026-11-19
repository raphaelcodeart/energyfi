"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { friendlyApiError } from "@/lib/api-error";
import { Chip } from "@/components/ui/data-cells";

/*
 * Impostazioni → Funzioni: switch optional parts of the platform on or off
 * for everyone (admin, promoters, customers). Off hides their pages, menu
 * entries and balances; nothing is deleted, so turning back on restores
 * them. The same switches exist on the command line: python -m app.seed.features.
 */

type SwitchesRead = { switches: Record<string, boolean>; defaults: Record<string, boolean>; requires: Record<string, string> };

const ROWS: { key: string; title: string; description: string }[] = [
  {
    key: "external_wallet",
    title: "Saldi MAMIX e MamiCash (da Mamify)",
    description: "I riquadri Saldo MAMIX, MamiCash personale e MamiCash aziendale nella home, letti da Mamify in sola lettura per chi è nella rete.",
  },
  {
    key: "profile_gate",
    title: "Profilo obbligatorio al primo accesso",
    description: "Acceso, chi entra deve compilare codice fiscale e residenza prima di usare la dashboard. Spento, li compila quando vuole da «Il mio profilo».",
  },
  {
    key: "friend_referrals",
    title: "Porta un amico",
    description: "La lista a un livello degli amici invitati, il loro conteggio e il premio (voci Porta un amico e Premi invito).",
  },
  {
    key: "wallet",
    title: "Portafoglio SosnetCash",
    description: "Saldi, ricariche, trasferimenti, pagamento con SosnetCash e accredito automatico del cashback. Spento, i movimenti mostrano solo i pagamenti con bonifico e carta.",
  },
  {
    key: "invoice_cashback",
    title: "Incassa il cashback (riscatto fatture)",
    description: "I clienti caricano una fattura di un partner e ricevono cashback in SosnetCash; sezioni Riscatti fatture e Partner.",
  },
  {
    key: "welcome_bonus",
    title: "Omaggio di benvenuto",
    description: "Il riquadro «Riscatta il tuo omaggio» in home, con SosnetCash di benvenuto.",
  },
  {
    key: "dropshipping",
    title: "Shop dropshipping",
    description: "I negozi dei fornitori esterni (CJ, Shopify, AliExpress). «Fai la Spesa con Sosnet» e il catalogo restano sempre visibili.",
  },
];

const LABELS: Record<string, string> = Object.fromEntries(ROWS.map((r) => [r.key, r.title]));

export function AdminFeaturesCard() {
  const queryClient = useQueryClient();
  const { data } = useQuery({
    queryKey: ["organization", "features", "switches"],
    queryFn: async (): Promise<SwitchesRead> => {
      const res = await fetch("/api/proxy/organizations/me/features/switches");
      if (!res.ok) throw new Error(await friendlyApiError(res));
      return res.json();
    },
  });
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function change(body: Record<string, boolean>, key: string) {
    setBusy(key);
    setError(null);
    try {
      const res = await fetch("/api/proxy/organizations/me/features", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      await queryClient.invalidateQueries({ queryKey: ["organization", "features"] });
    } catch (err: any) {
      setError(err.message || "Modifica non riuscita.");
    } finally {
      setBusy(null);
    }
  }

  const switches = data?.switches ?? {};

  return (
    <section className="panel rounded-3xl p-6 sm:p-7">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="kpi-label">Funzioni</p>
          <h3 className="mt-1 text-xl font-black tracking-tight text-white">Parti della piattaforma da accendere o spegnere</h3>
          <p className="mt-1 text-sm text-surface-300">
            Valgono per tutti: amministrazione, promoter e clienti. Spegnere nasconde, non cancella: riaccendendo torna tutto com&apos;era.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            className="act"
            disabled={!data || busy !== null}
            onClick={() => data && change({ ...data.defaults }, "defaults")}
            title="Riporta ogni funzione alla configurazione iniziale"
          >
            Configurazione iniziale
          </button>
          <button
            className="act act-primary"
            disabled={!data || busy !== null}
            onClick={() => data && change(Object.fromEntries(Object.keys(data.switches).map((k) => [k, true])), "all")}
          >
            Accendi tutto
          </button>
        </div>
      </div>
      <div className="mt-5 space-y-3">
        {ROWS.map((row) => {
          const on = !!switches[row.key];
          const needs = data?.requires[row.key];
          const blocked = on && needs && !switches[needs];
          return (
            <div key={row.key} className="flex flex-wrap items-center justify-between gap-4 rounded-2xl bg-white/5 p-4">
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-bold text-white">{row.title}</span>
                  <Chip tone={on ? (blocked ? "warn" : "ok") : "muted"}>{on ? (blocked ? "In attesa" : "Attivo") : "Spento"}</Chip>
                </div>
                <p className="mt-1 text-xs text-surface-300">{row.description}</p>
                {needs && (
                  <p className={`mt-1 text-[11px] ${blocked ? "text-warn-300" : "text-surface-400"}`}>
                    Funziona solo con «{LABELS[needs] ?? needs}» acceso.
                  </p>
                )}
              </div>
              <button
                role="switch"
                aria-checked={on}
                aria-label={`${on ? "Spegni" : "Accendi"} ${row.title}`}
                disabled={!data || busy !== null}
                onClick={() => change({ [row.key]: !on }, row.key)}
                className={`relative h-8 w-14 shrink-0 cursor-pointer rounded-full transition ${on ? "bg-gradient-to-r from-brand-600 to-accent-500" : "bg-white/15"} disabled:opacity-50`}
              >
                <span className={`absolute top-1 h-6 w-6 rounded-full bg-white shadow transition-all ${on ? "left-7" : "left-1"}`} />
              </button>
            </div>
          );
        })}
      </div>
      {error && <p className="mt-3 text-sm text-danger-300">{error}</p>}
      <p className="mt-4 text-[11px] text-surface-400">
        Anche da terminale: <code className="font-mono">python -m app.seed.features --organization-name SOSNET --enable all</code> ·
        istruzioni complete in <code className="font-mono">docs/funzioni-attivabili.md</code>.
      </p>
    </section>
  );
}
