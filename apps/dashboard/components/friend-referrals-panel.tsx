"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Pagination, usePagination } from "@/components/pagination";
import { friendlyApiError } from "@/lib/api-error";
import { ShareButtons } from "@/components/share-buttons";
import { Chip, Identity, type ChipTone } from "@/components/ui/data-cells";
import type { FriendReferralSummaryRead } from "@/lib/types";

const STATE_LABELS: Record<string, string> = {
  INVITED: "Iscritto",
  IN_PROGRESS: "Contratto in corso",
  ACTIVE: "Attivo",
};

const STATE_TONES: Record<string, ChipTone> = {
  INVITED: "muted",
  IN_PROGRESS: "warn",
  ACTIVE: "ok",
};

const CLAIM_STATUS_LABELS: Record<string, string> = {
  REQUESTED: "In attesa di risposta",
  FULFILLED: "Consegnato",
  REJECTED: "Non accolto",
};

async function fetchSummary(): Promise<FriendReferralSummaryRead> {
  const res = await fetch("/api/proxy/friend-referrals/me");
  if (!res.ok) throw new Error("Impossibile caricare i tuoi inviti.");
  return res.json();
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("it-IT", { day: "2-digit", month: "short", year: "numeric" });
}

/** "oggi", "ieri", "12 giorni fa"... */
function relativeDays(iso: string): string {
  const days = Math.floor((Date.now() - new Date(iso).getTime()) / 86_400_000);
  if (days <= 0) return "oggi";
  if (days === 1) return "ieri";
  if (days < 30) return `${days} giorni fa`;
  const months = Math.floor(days / 30);
  return months === 1 ? "1 mese fa" : months < 12 ? `${months} mesi fa` : `${Math.floor(months / 12)} anni fa`;
}

/**
 * "Invita un amico": each account's one-level invite list.
 * Not the commercial network: no commissions, no hierarchy. It lets
 * non-promoters see who they invited and tracks the cashback bonus earned
 * every `reward_every` activated friends. Placement of invitees in the commercial tree is decided by
 * the backend and never shown here.
 */
export function FriendReferralsPanel({ organizationId }: { organizationId?: string }) {
  const queryClient = useQueryClient();
  const { data, error } = useQuery({ queryKey: ["friend-referrals", "me"], queryFn: fetchSummary });
  const [claimLoading, setClaimLoading] = useState(false);
  const [claimError, setClaimError] = useState<string | null>(null);

  const pagination = usePagination(data?.referrals ?? []);

  function personalLink(): string {
    if (typeof window === "undefined" || !data) return "";
    const url = new URL(`/r/${data.code}`, window.location.origin);
    if (organizationId) url.searchParams.set("org", organizationId);
    return url.toString();
  }

  async function handleClaim() {
    setClaimLoading(true);
    setClaimError(null);
    try {
      const res = await fetch("/api/proxy/friend-referrals/me/reward-claims", { method: "POST" });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      await queryClient.invalidateQueries({ queryKey: ["friend-referrals", "me"] });
    } catch (err: any) {
      setClaimError(err.message || "Impossibile inviare la richiesta.");
    } finally {
      setClaimLoading(false);
    }
  }

  if (error) {
    return <p className="text-sm text-danger-400">Impossibile caricare i tuoi inviti.</p>;
  }
  if (!data) {
    return <div className="panel rounded-3xl p-6 animate-pulse h-40" />;
  }

  const towardsNext = data.active_total % data.reward_every;
  const progress = data.claimable_milestone ? 100 : (towardsNext / data.reward_every) * 100;

  return (
    <div className="space-y-6">
      {/* Personal link */}
      <div className="panel rise rounded-3xl p-6 sm:p-7">
        <p className="kpi-label">Il tuo link personale</p>
        <h3 className="mt-1 text-xl font-black tracking-tight text-white">Invita un amico</h3>
        <p className="text-sm text-surface-300 mt-2 mb-5 max-w-3xl">
          Condividi il tuo link: chi si iscrive da qui compare nella tua lista. <strong className="text-white">Ogni{" "}
          {data.reward_every} amici</strong> che attivano un contratto SOSNET puoi richiedere{" "}
          <strong className="text-white">{data.reward_description}</strong> &mdash; non solo per i primi {data.reward_every}:
          il premio si ripete a {data.reward_every * 2}, {data.reward_every * 3} e cosi via.
        </p>
        <code className="sheen block w-full truncate rounded-2xl bg-black/30 border border-white/10 px-4 py-3 text-xs font-mono text-surface-200 mb-4">
          {personalLink() || `…/r/${data.code}`}
        </code>
        {/* Direct share to common apps; "Copia link" covers the rest. */}
        <ShareButtons
          url={personalLink()}
          text="Ti invito in SOSNET, iscriviti con il mio link:"
        />
      </div>

      {/* Progress toward the gift */}
      <div className="panel rise rounded-3xl p-6 sm:p-7">
        <div className="flex flex-wrap items-end justify-between gap-4 mb-5">
          <div>
            <p className="kpi-label">Amici invitati con contratto attivo</p>
            <p className="kpi-value mt-2 tabular-nums">
              {data.active_total}
              <span className="text-base font-semibold text-surface-300"> / {data.invited_total} iscritti</span>
            </p>
          </div>
          {data.claimable_milestone ? (
            <button
              onClick={handleClaim}
              disabled={claimLoading}
              className="act act-primary pulse-ring !px-5 !py-2.5 disabled:opacity-50"
            >
              {claimLoading ? "Invio..." : `Richiedi ${data.reward_description}`}
            </button>
          ) : (
            <p className="text-sm text-surface-300">
              Ne mancano <strong className="text-gradient text-lg font-black">{data.missing_for_next_reward}</strong> per{" "}
              {data.reward_description}
            </p>
          )}
        </div>

        <div className="meter !h-2.5">
          <i style={{ width: `${Math.max(3, Math.min(100, progress))}%` }} />
        </div>
        <p className="mt-2 text-[11px] text-surface-400 tabular-nums">
          {data.claimable_milestone ? "Traguardo raggiunto" : `${towardsNext} / ${data.reward_every} verso il prossimo omaggio`}
        </p>

        {claimError && (
          <div className="mt-3 p-3 rounded-xl bg-danger-500/10 border border-danger-500/20 text-danger-400 text-xs">
            {claimError}
          </div>
        )}

        {data.claims.length > 0 && (
          <div className="mt-6 pt-5 border-t border-white/10 space-y-2.5">
            <p className="kpi-label">Le tue richieste</p>
            {data.claims.map((c) => (
              <div key={c.id} className="flex flex-wrap items-center justify-between gap-2 rounded-2xl bg-white/5 px-4 py-2.5 text-xs">
                <span className="font-semibold text-white">
                  Omaggio per {c.milestone} amici attivi
                </span>
                <div className="flex items-center gap-2">
                  {c.note && <span className="text-surface-300">{c.note}</span>}
                  <Chip
                    tone={c.status === "FULFILLED" ? "ok" : c.status === "REJECTED" ? "bad" : "warn"}
                    live={c.status !== "FULFILLED" && c.status !== "REJECTED"}
                  >
                    {CLAIM_STATUS_LABELS[c.status] ?? c.status}
                  </Chip>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Invite list */}
      <div className="panel rise rounded-3xl p-6 sm:p-7">
        <p className="kpi-label">La tua cerchia</p>
        <h4 className="mt-1 mb-4 text-xl font-black tracking-tight text-white">Gli amici che hai invitato</h4>
        {data.referrals.length === 0 ? (
          <div className="flex flex-col items-center gap-3 py-12 text-center">
            <span className="float-soft grid h-14 w-14 place-items-center rounded-2xl bg-brand-500/15 text-brand-300">
              <svg className="w-7 h-7" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M18 9v3m0 0v3m0-3h3m-3 0h-3m-2-5a4 4 0 11-8 0 4 4 0 018 0zM3 20a6 6 0 0112 0v1H3v-1z" />
              </svg>
            </span>
            <p className="text-sm text-surface-300">Non hai ancora invitato nessuno. Condividi il tuo link qui sopra.</p>
          </div>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr>
                    <th className="px-4 py-3">Amico</th>
                    <th className="px-4 py-3">Entrato</th>
                    <th className="px-4 py-3 text-right">A che punto è</th>
                  </tr>
                </thead>
                <tbody>
                  {pagination.pageItems.map((r) => (
                    <tr key={r.id}>
                      <td className="px-4 py-3">
                        <Identity name={r.display_name} detail="Invitato con il tuo link" />
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap">
                        <div className="text-[13px] font-semibold text-white">{formatDate(r.invited_at)}</div>
                        <div className="text-[11px] text-surface-400">{relativeDays(r.invited_at)}</div>
                      </td>
                      <td className="px-4 py-3 text-right">
                        <Chip tone={STATE_TONES[r.state] ?? "muted"} live={r.state === "IN_PROGRESS"}>
                          {STATE_LABELS[r.state] ?? r.state}
                        </Chip>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="pt-2">
              <Pagination {...pagination} label="amici invitati" />
            </div>
          </>
        )}
      </div>
    </div>
  );
}
