"use client";

import { Fragment, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Pagination, usePagination } from "@/components/pagination";
import { friendlyApiError } from "@/lib/api-error";
import type { FriendReferralAdminClaimRead } from "@/lib/types";
import { Chip, Figure, Identity, RowActions, Stack, type ChipTone } from "@/components/ui/data-cells";

const STATUS_TABS: { key: string; label: string }[] = [
  { key: "REQUESTED", label: "Da gestire" },
  { key: "FULFILLED", label: "Consegnati" },
  { key: "REJECTED", label: "Non accolti" },
  { key: "ALL", label: "Tutti" },
];

const STATUS_TONES: Record<string, ChipTone> = {
  REQUESTED: "warn",
  FULFILLED: "ok",
  REJECTED: "bad",
};

const STATUS_LABELS: Record<string, string> = {
  REQUESTED: "Da gestire",
  FULFILLED: "Consegnato",
  REJECTED: "Non accolto",
};

async function fetchClaims(status: string): Promise<FriendReferralAdminClaimRead[]> {
  const res = await fetch(`/api/proxy/friend-referrals/admin/reward-claims?status_filter=${status}`);
  if (!res.ok) throw new Error("Impossibile caricare le richieste omaggio.");
  return res.json();
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("it-IT", { day: "2-digit", month: "short", year: "numeric" });
}

function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" });
}

function relative(iso: string): string {
  const days = Math.floor((Date.now() - new Date(iso).getTime()) / 86_400_000);
  if (days <= 0) return "oggi";
  if (days === 1) return "ieri";
  if (days < 30) return `${days} giorni fa`;
  const months = Math.floor(days / 30);
  return months === 1 ? "un mese fa" : `${months} mesi fa`;
}

/**
 * "Omaggi Inviti": requests customers send at every multiple of 10 activated
 * referrals. Marking one delivered credits the 10 EUR cashback bonus to the
 * customer's wallet (friend_referrals/service.py::handle_claim). The note
 * entered here is shown to the customer.
 */
export function AdminFriendReferralClaimsPanel() {
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState("REQUESTED");
  const [handlingId, setHandlingId] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);
  const [loadingId, setLoadingId] = useState<string | null>(null);

  const { data: claims, error } = useQuery({
    queryKey: ["admin", "friend-referral-claims", statusFilter],
    queryFn: () => fetchClaims(statusFilter),
  });

  const pagination = usePagination(claims ?? []);

  async function handle(id: string, status: "FULFILLED" | "REJECTED") {
    setLoadingId(id);
    setActionError(null);
    try {
      const res = await fetch(`/api/proxy/friend-referrals/admin/reward-claims/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status, note: note.trim() || null }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      setHandlingId(null);
      setNote("");
      await queryClient.invalidateQueries({ queryKey: ["admin", "friend-referral-claims"] });
    } catch (err: any) {
      setActionError(err.message || "Impossibile aggiornare la richiesta.");
    } finally {
      setLoadingId(null);
    }
  }

  return (
    <div className="space-y-5">
      <div className="px-1">
        <div className="kpi-label">Invita un amico</div>
        <h3 className="mt-1 text-2xl font-black tracking-tight text-white">Omaggi <span className="text-gradient">da consegnare</span></h3>
        <p className="text-xs text-surface-300 mt-2 max-w-3xl">
          Richieste inviate da chi ha raggiunto 10, 20, 30… amici invitati con un contratto
          <strong> attivo</strong>. Il premio è un <strong>bonus di 10 € in cashback omaggio</strong>, e si
          ripete a ogni multiplo di 10. Quando segnate la richiesta come consegnata, i 10 € vengono
          accreditati in automatico sul portafoglio SosnetCash del cliente; la nota che scrivete gli viene
          mostrata.
        </p>
      </div>

      <div className="subnav">
        {STATUS_TABS.map((tab) => (
          <button key={tab.key} onClick={() => setStatusFilter(tab.key)} data-active={statusFilter === tab.key} className="subnav-pill">
            {tab.label}
          </button>
        ))}
      </div>

      {error && <p className="text-sm text-danger-400">Impossibile caricare le richieste.</p>}
      {actionError && (
        <div className="p-3 rounded-2xl bg-danger-500/10 border border-danger-500/20 text-danger-400 text-xs pop">
          {actionError}
        </div>
      )}

      <div className="panel rounded-3xl p-4 md:p-6">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr>
                <th className="px-4 py-3">Chi invita</th>
                <th className="px-4 py-3 text-right">Traguardo</th>
                <th className="px-4 py-3">Richiesto</th>
                <th className="px-4 py-3">Esito</th>
                <th className="px-4 py-3"><span className="sr-only">Azioni</span></th>
              </tr>
            </thead>
            <tbody className="text-surface-300">
              {claims === undefined ? (
                <tr><td colSpan={5} className="px-4 py-8 text-center text-surface-400">Caricamento...</td></tr>
              ) : claims.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-4 py-10">
                    <div className="flex flex-col items-center gap-2 text-center">
                      <svg viewBox="0 0 24 24" className="h-8 w-8 text-accent-300 float-soft" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
                        <path d="M4 11h16v10H4zM2 7h20v4H2zM12 7v14M12 7c-2-4-6-4-6-1s6 1 6 1zm0 0c2-4 6-4 6-1s-6 1-6 1z" strokeLinejoin="round" />
                      </svg>
                      <span className="text-sm font-semibold text-surface-200">Nessuna richiesta in questo stato.</span>
                    </div>
                  </td>
                </tr>
              ) : (
                pagination.pageItems.map((c) => (
                  <Fragment key={c.id}>
                    <tr>
                      <td className="px-4 py-3">
                        <Identity name={c.referrer_name} detail={c.referrer_email} />
                      </td>
                      <td className="px-4 py-3">
                        <Figure value={`${c.milestone} amici`} detail="attivi" ratio={Math.min(1, c.milestone / 50)} />
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap">
                        <Stack title={formatDate(c.requested_at)} detail={`${formatTime(c.requested_at)} · ${relative(c.requested_at)}`} />
                      </td>
                      <td className="px-4 py-3">
                        <div className="space-y-1">
                          <Chip tone={STATUS_TONES[c.status] ?? "muted"} live={c.status === "REQUESTED"}>{STATUS_LABELS[c.status] ?? c.status}</Chip>
                          {c.handled_at && <div className="text-[10.5px] text-surface-400">gestito il {formatDate(c.handled_at)}, {formatTime(c.handled_at)}</div>}
                          {c.note && <div className="max-w-[260px] truncate text-[10.5px] text-surface-300" title={c.note}>Nota: {c.note}</div>}
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        {c.status === "REQUESTED" && handlingId !== c.id && (
                          <RowActions>
                            <button
                              onClick={() => {
                                setHandlingId(c.id);
                                setNote("");
                                setActionError(null);
                              }}
                              className="act act-primary"
                            >
                              Gestisci
                            </button>
                          </RowActions>
                        )}
                      </td>
                    </tr>
                    {handlingId === c.id && (
                      <tr>
                        <td colSpan={5} className="px-5 py-4">
                          <div className="space-y-3 pop">
                            <div className="space-y-1">
                              <label className="kpi-label block">Nota per il cliente (opzionale)</label>
                              <input
                                value={note}
                                onChange={(e) => setNote(e.target.value)}
                                maxLength={500}
                                placeholder="Es. Bonus di 10 € accreditato sul tuo portafoglio"
                                className="w-full rounded-xl field px-3 py-2 text-sm focus:border-brand-500"
                              />
                            </div>
                            <div className="flex flex-wrap gap-2">
                              <button onClick={() => handle(c.id, "FULFILLED")} disabled={loadingId === c.id} className="act act-primary">
                                {loadingId === c.id ? "..." : "Omaggio consegnato"}
                              </button>
                              <button onClick={() => handle(c.id, "REJECTED")} disabled={loadingId === c.id} className="act !text-danger-400">
                                {loadingId === c.id ? "..." : "Non accolgo"}
                              </button>
                              <button onClick={() => setHandlingId(null)} className="act">
                                Annulla
                              </button>
                            </div>
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
      <Pagination {...pagination} label="richieste" />
    </div>
  );
}
