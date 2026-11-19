"use client";

import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { friendlyApiError } from "@/lib/api-error";
import type { BranchSyncView } from "@/lib/types";

function when(iso?: string | null): string {
  if (!iso) return "";
  return new Date(iso).toLocaleString("it-IT", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
}

function outcome(r: BranchSyncView["result"]): string {
  if (!r) return "";
  if (r.skipped) return r.skipped;
  if (r.message) return r.message;
  const parts = [
    r.created ? `${r.created} nuovi` : "",
    r.moved ? `${r.moved} spostati` : "",
    r.missing ? `${r.missing} usciti` : "",
    r.updated ? `${r.updated} nomi aggiornati` : "",
  ].filter(Boolean);
  return parts.length ? parts.join(" · ") : "nessuna differenza con Mamify";
}

/** "Aggiorna rete": re-reads this collaborator's branch from Mamify (read
    only, in the Mamify queue) and shows how it went. Hidden for people who
    do not come from Mamify. `self` is the Digital Ambassador's own branch. */
export function BranchSyncButton({ agentId, self = false, compact = false }: { agentId?: string; self?: boolean; compact?: boolean }) {
  const qc = useQueryClient();
  const url = self ? "/api/proxy/mamify/me/branch-sync" : `/api/proxy/mamify/admin/members/${agentId}/branch-sync`;
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const { data } = useQuery({
    queryKey: ["branch-sync", self ? "me" : agentId],
    queryFn: async () => {
      const res = await fetch(url);
      if (!res.ok) return { available: false } as BranchSyncView;
      const view: BranchSyncView = await res.json();
      return view;
    },
    // While it runs, ask every 3 seconds; when it ends, refresh the screens.
    refetchInterval: (q) => (q.state.data?.running ? 3000 : false),
    staleTime: 0,
  });
  const wasRunning = useRef(false);
  useEffect(() => {
    if (wasRunning.current && data && !data.running) {
      void qc.invalidateQueries({ queryKey: ["affiliate"] });
      void qc.invalidateQueries({ queryKey: ["admin"] });
      void qc.invalidateQueries({ queryKey: ["network"] });
      void qc.invalidateQueries({ queryKey: ["promoter"] });
    }
    wasRunning.current = !!data?.running;
  }, [data, qc]);

  if (!data?.available) return null;
  async function run() {
    setSending(true);
    setError(null);
    try {
      const res = await fetch(url, { method: "POST" });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      qc.setQueryData(["branch-sync", self ? "me" : agentId], await res.json());
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSending(false);
    }
  }
  const running = data.running || sending;
  return (
    <div className={compact ? "inline-flex flex-col items-start gap-1" : "flex flex-wrap items-center gap-3"}>
      <button type="button" onClick={run} disabled={running} className="act disabled:opacity-60"
        title="Rilegge da Mamify la rete sotto questa persona (solo lettura) e la allinea qui">
        <svg className={`h-4 w-4 ${running ? "animate-spin" : ""}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden>
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
        </svg>
        {running ? "Aggiorno la rete…" : "Aggiorna rete"}
      </button>
      <span className="text-[11px] text-surface-400">
        {error ? <span className="text-danger-400">{error}</span>
          : running ? "Lettura da Mamify in corso, pochi secondi per ogni 50 persone."
          : data.synced_at ? `Aggiornata ${when(data.synced_at)}: ${outcome(data.result)}`
          : "Allineata con la copia automatica di Mamify."}
      </span>
    </div>
  );
}
