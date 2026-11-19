"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { friendlyApiError } from "@/lib/api-error";
import type { PartnerRead } from "@/lib/types";
import { Chip, IdTag, Identity, KpiTile, RowActions } from "@/components/ui/data-cells";

async function fetchPartners(): Promise<PartnerRead[]> {
  const res = await fetch("/api/proxy/partners");
  if (!res.ok) throw new Error("Impossibile caricare i partner.");
  return res.json();
}

/**
 * Registry of external suppliers SOSNET brokers for. Customers pick from this
 * list when uploading an invoice to redeem.
 */
export function AdminPartnersPanel() {
  const queryClient = useQueryClient();
  const { data: partners, error: loadError } = useQuery({
    queryKey: ["admin", "partners"],
    queryFn: fetchPartners,
  });

  const [name, setName] = useState("");
  const [createLoading, setCreateLoading] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [toggleId, setToggleId] = useState<string | null>(null);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    setCreateLoading(true);
    setCreateError(null);
    try {
      const res = await fetch("/api/proxy/partners", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: name.trim() }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      setName("");
      await queryClient.invalidateQueries({ queryKey: ["admin", "partners"] });
    } catch (err: any) {
      setCreateError(err.message || "Impossibile creare il partner.");
    } finally {
      setCreateLoading(false);
    }
  }

  async function handleToggleActive(partner: PartnerRead) {
    setToggleId(partner.id);
    try {
      const res = await fetch(`/api/proxy/partners/${partner.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ is_active: !partner.is_active }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      await queryClient.invalidateQueries({ queryKey: ["admin", "partners"] });
    } finally {
      setToggleId(null);
    }
  }

  const activeCount = (partners ?? []).filter((p) => p.is_active).length;

  return (
    <div className="space-y-6">
      {partners !== undefined && (
        <div className="grid grid-cols-2 gap-4 md:grid-cols-3 stagger">
          <div style={{ "--i": 0 } as React.CSSProperties}><KpiTile label="Fornitori" value={partners.length} hint="in anagrafica" /></div>
          <div style={{ "--i": 1 } as React.CSSProperties}><KpiTile label="Visibili" value={activeCount} hint="scelti dai clienti" /></div>
          <div style={{ "--i": 2 } as React.CSSProperties}><KpiTile label="In pausa" value={partners.length - activeCount} hint="nascosti ai clienti" /></div>
        </div>
      )}

      <div className="panel rounded-3xl p-6 md:p-7 rise">
        <div className="kpi-label">Anagrafica</div>
        <h3 className="mt-1 mb-1 text-xl font-black tracking-tight text-white">Nuovo fornitore partner</h3>
        <p className="text-xs text-surface-400 mb-5">
          Un fornitore esterno di cui SOSNET è broker (es. Eviso). Comparirà nell&apos;elenco che il cliente vede quando carica una fattura da riscattare.
        </p>
        <form onSubmit={handleCreate} className="flex flex-wrap items-end gap-3">
          <div className="space-y-1 flex-1 min-w-[200px] max-w-sm">
            <label className="kpi-label block">Nome</label>
            <input
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Es. Eviso"
              className="w-full rounded-xl field px-3 py-2 text-sm focus:border-brand-500"
            />
          </div>
          <button type="submit" disabled={createLoading} className="act act-primary !h-10 !px-5">
            {createLoading ? "..." : "Aggiungi"}
          </button>
        </form>
        {createError && (
          <div className="mt-3 p-3 rounded-2xl bg-danger-500/10 border border-danger-500/20 text-danger-400 text-xs pop">{createError}</div>
        )}
      </div>

      <div className="panel rounded-3xl p-4 md:p-6">
        <div className="px-2 pb-1">
          <div className="kpi-label">Rete fornitori</div>
          <h3 className="mt-1 text-xl font-black tracking-tight text-white">Fornitori partner</h3>
        </div>
        {loadError && <p className="px-2 pt-2 text-sm text-danger-400">Impossibile caricare i partner.</p>}
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr>
                <th className="px-4 py-3">Fornitore</th>
                <th className="px-4 py-3">Visibilità</th>
                <th className="px-4 py-3"><span className="sr-only">Azioni</span></th>
              </tr>
            </thead>
            <tbody>
              {partners === undefined ? (
                <tr><td colSpan={3} className="px-4 py-8 text-center text-surface-400">Caricamento...</td></tr>
              ) : partners.length === 0 ? (
                <tr>
                  <td colSpan={3} className="px-4 py-10">
                    <div className="flex flex-col items-center gap-2 text-center">
                      <svg viewBox="0 0 24 24" className="h-8 w-8 text-accent-300 float-soft" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
                        <path d="M3 21h18M5 21V8l7-5 7 5v13M9 21v-6h6v6" strokeLinejoin="round" />
                      </svg>
                      <span className="text-sm font-semibold text-surface-200">Nessun partner ancora.</span>
                    </div>
                  </td>
                </tr>
              ) : (
                partners.map((p) => (
                  <tr key={p.id} className="text-surface-300">
                    <td className="px-4 py-3">
                      <Identity
                        name={p.name}
                        // eslint-disable-next-line @next/next/no-img-element -- externally-hosted partner logo
                        icon={p.logo_url ? <img src={p.logo_url} alt="" className="h-full w-full rounded-[14px] object-cover" /> : undefined}
                        detail={<IdTag id={p.id} />}
                      />
                    </td>
                    <td className="px-4 py-3">
                      <Chip tone={p.is_active ? "ok" : "muted"}>{p.is_active ? "Attivo" : "Disattivato"}</Chip>
                    </td>
                    <td className="px-4 py-3">
                      <RowActions>
                        <button onClick={() => handleToggleActive(p)} disabled={toggleId === p.id} className={p.is_active ? "act" : "act act-primary"}>
                          {toggleId === p.id ? "..." : p.is_active ? "Disattiva" : "Riattiva"}
                        </button>
                      </RowActions>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
