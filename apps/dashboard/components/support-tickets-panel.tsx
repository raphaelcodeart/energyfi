"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Pagination, usePagination } from "@/components/pagination";
import { friendlyApiError } from "@/lib/api-error";
import type { TicketDetailRead, TicketRead } from "@/lib/types";
import { Chip, Figure, Identity, RowActions, type ChipTone } from "@/components/ui/data-cells";

const CATEGORY_LABELS: Record<string, string> = {
  ASSISTENZA_TECNICA: "Assistenza tecnica",
  FATTURAZIONE: "Fatturazione",
  // Old tickets only: no longer offered as a choice.
  CONTRATTO: "Contratto",
  COMMISSIONI: "Commissioni",
  ALTRO: "Altro",
};

const STATUS_LABELS: Record<string, string> = {
  OPEN: "Aperto",
  IN_PROGRESS: "In lavorazione",
  RESOLVED: "Risolto",
  CLOSED: "Chiuso",
};

function statusTone(status: string): ChipTone {
  switch (status) {
    case "OPEN":
      return "warn";
    case "IN_PROGRESS":
      return "info";
    case "RESOLVED":
      return "ok";
    default:
      return "muted";
  }
}

function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString("it-IT", { dateStyle: "short", timeStyle: "short" });
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("it-IT", { day: "2-digit", month: "short", year: "numeric" });
}

function relative(iso: string): string {
  const days = Math.floor((Date.now() - new Date(iso).getTime()) / 86_400_000);
  if (days <= 0) return "oggi";
  if (days === 1) return "ieri";
  if (days < 30) return `${days} giorni fa`;
  const months = Math.floor(days / 30);
  return months === 1 ? "un mese fa" : `${months} mesi fa`;
}

async function fetchMyTickets(): Promise<TicketRead[]> {
  const res = await fetch("/api/proxy/support/tickets/mine");
  if (!res.ok) throw new Error("Impossibile caricare i ticket.");
  return res.json();
}

async function fetchTicketDetail(id: string): Promise<TicketDetailRead> {
  const res = await fetch(`/api/proxy/support/tickets/${id}`);
  if (!res.ok) throw new Error("Impossibile caricare il ticket.");
  return res.json();
}

export function SupportTicketsPanel({ title, subtitle }: { title: string; subtitle: string }) {
  const queryClient = useQueryClient();
  const { data: tickets, error: listError } = useQuery({ queryKey: ["support", "tickets", "mine"], queryFn: fetchMyTickets });

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const { data: detail } = useQuery({
    queryKey: ["support", "tickets", "detail", selectedId],
    queryFn: () => fetchTicketDetail(selectedId as string),
    enabled: !!selectedId,
  });

  const [showCreate, setShowCreate] = useState(false);
  const [subject, setSubject] = useState("");
  const [category, setCategory] = useState("ASSISTENZA_TECNICA");
  const [message, setMessage] = useState("");
  const [createLoading, setCreateLoading] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const [reply, setReply] = useState("");
  const [replyLoading, setReplyLoading] = useState(false);
  const [replyError, setReplyError] = useState<string | null>(null);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setCreateLoading(true);
    setCreateError(null);
    try {
      const res = await fetch("/api/proxy/support/tickets", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ subject, category, message }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      const newTicket = (await res.json()) as TicketRead;
      setSubject("");
      setMessage("");
      setShowCreate(false);
      await queryClient.invalidateQueries({ queryKey: ["support", "tickets", "mine"] });
      setSelectedId(newTicket.id);
    } catch (err: any) {
      setCreateError(err.message || "Impossibile aprire il ticket.");
    } finally {
      setCreateLoading(false);
    }
  }

  async function handleReply(e: React.FormEvent) {
    e.preventDefault();
    if (!selectedId) return;
    setReplyLoading(true);
    setReplyError(null);
    try {
      const res = await fetch(`/api/proxy/support/tickets/${selectedId}/messages`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ body: reply }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      setReply("");
      await queryClient.invalidateQueries({ queryKey: ["support", "tickets", "detail", selectedId] });
      await queryClient.invalidateQueries({ queryKey: ["support", "tickets", "mine"] });
    } catch (err: any) {
      setReplyError(err.message || "Impossibile inviare la risposta.");
    } finally {
      setReplyLoading(false);
    }
  }

  // Before the early return below: hooks must run on every render.
  const pagination = usePagination(tickets ?? []);

  if (selectedId && detail) {
    return (
      <div className="space-y-5">
        <button onClick={() => setSelectedId(null)} className="act">
          ← Torna ai ticket
        </button>

        <div className="panel rounded-3xl p-6 md:p-8">
          <div className="flex flex-wrap items-start justify-between gap-4 mb-6">
            <div className="min-w-0">
              <div className="kpi-label">{CATEGORY_LABELS[detail.category] ?? detail.category}</div>
              <h3 className="mt-1 text-2xl font-black tracking-tight text-white">{detail.subject}</h3>
            </div>
            <Chip tone={statusTone(detail.status)} live={detail.status === "OPEN"}>{STATUS_LABELS[detail.status] ?? detail.status}</Chip>
          </div>

          <div className="space-y-3 mb-6 stagger">
            {detail.messages.map((m, i) => {
              const isStaff = m.author_role === "ADMIN";
              return (
                <div key={m.id} style={{ "--i": Math.min(i, 12) } as React.CSSProperties} className={`flex ${isStaff ? "justify-start" : "justify-end"}`}>
                  <div
                    className={`max-w-[80%] rounded-3xl px-5 py-3 text-sm ${
                      isStaff
                        ? "bg-white/6 border border-white/10 text-surface-100 rounded-bl-md"
                        : "bg-gradient-to-br from-brand-600/35 to-accent-500/20 border border-brand-400/30 text-white rounded-br-md"
                    }`}
                  >
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-[10px] font-extrabold uppercase tracking-[0.14em] text-surface-300">
                        {isStaff ? "Assistenza" : m.author_name ?? "Tu"}
                      </span>
                      <span className="text-[10px] text-surface-400">{formatDateTime(m.created_at)}</span>
                    </div>
                    <p className="whitespace-pre-wrap">{m.body}</p>
                  </div>
                </div>
              );
            })}
          </div>

          {detail.status !== "CLOSED" && (
            <form onSubmit={handleReply} className="flex gap-2">
              <input
                required
                value={reply}
                onChange={(e) => setReply(e.target.value)}
                placeholder="Scrivi una risposta..."
                className="flex-1 rounded-2xl field px-4 py-3 text-sm focus:border-brand-500"
              />
              <button type="submit" disabled={replyLoading} className="act act-primary !h-auto !px-5">
                {replyLoading ? "Invio..." : "Invia"}
              </button>
            </form>
          )}
          {replyError && <p className="text-xs text-danger-400 mt-2">{replyError}</p>}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="kpi-label">Assistenza</div>
          <h2 className="mt-1 text-2xl font-black tracking-tight text-white">{title}</h2>
          <p className="text-sm text-surface-300 mt-1">{subtitle}</p>
        </div>
        <button onClick={() => setShowCreate((v) => !v)} className="act act-primary !h-10 !px-5 shrink-0">
          + Nuovo Ticket
        </button>
      </div>

      {showCreate && (
        <form onSubmit={handleCreate} className="panel rounded-3xl p-6 md:p-7 space-y-4 pop">
          <div className="space-y-1">
            <label className="kpi-label block">Oggetto</label>
            <input required value={subject} onChange={(e) => setSubject(e.target.value)}
              className="w-full rounded-xl field px-3 py-2 text-sm focus:border-brand-500" />
          </div>
          <div className="space-y-1">
            <label className="kpi-label block">Categoria</label>
            <select value={category} onChange={(e) => setCategory(e.target.value)}
              className="w-full rounded-xl field px-3 py-2.5 text-sm bg-surface-900 focus:border-brand-500">
              {Object.entries(CATEGORY_LABELS).filter(([code]) => code !== "CONTRATTO").map(([code, label]) => (
                <option key={code} value={code}>{label}</option>
              ))}
            </select>
          </div>
          <div className="space-y-1">
            <label className="kpi-label block">Messaggio</label>
            <textarea required rows={4} value={message} onChange={(e) => setMessage(e.target.value)}
              className="w-full rounded-xl field px-3 py-2 text-sm focus:border-brand-500 resize-none" />
          </div>
          {createError && <p className="text-xs text-danger-400">{createError}</p>}
          <div className="flex justify-end gap-2">
            <button type="button" onClick={() => setShowCreate(false)} className="act !h-10 !px-4">
              Annulla
            </button>
            <button type="submit" disabled={createLoading} className="act act-primary !h-10 !px-4">
              {createLoading ? "Invio..." : "Apri Ticket"}
            </button>
          </div>
        </form>
      )}

      {listError && <p className="text-sm text-danger-400">Impossibile caricare i ticket.</p>}

      <div className="panel rounded-3xl p-4 md:p-6">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr>
                <th className="px-4 py-3">Argomento</th>
                <th className="px-4 py-3">Situazione</th>
                <th className="px-4 py-3 text-right">Conversazione</th>
                <th className="px-4 py-3"><span className="sr-only">Azioni</span></th>
              </tr>
            </thead>
            <tbody className="text-surface-300">
              {tickets === undefined ? (
                <tr><td colSpan={4} className="px-4 py-8 text-center text-surface-400">Caricamento...</td></tr>
              ) : tickets.length === 0 ? (
                <tr>
                  <td colSpan={4} className="px-4 py-12">
                    <div className="flex flex-col items-center gap-2 text-center">
                      <svg viewBox="0 0 24 24" className="h-8 w-8 text-accent-300 float-soft" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
                        <path d="M4 5h16v11H9l-5 4z" strokeLinejoin="round" />
                      </svg>
                      <span className="text-sm font-semibold text-surface-200">Nessun ticket aperto. Usa &quot;+ Nuovo Ticket&quot; se hai bisogno di assistenza.</span>
                    </div>
                  </td>
                </tr>
              ) : (
                pagination.pageItems.map((t) => (
                  <tr key={t.id} onClick={() => setSelectedId(t.id)} className="cursor-pointer">
                    <td className="px-4 py-3">
                      <Identity name={t.subject} detail={CATEGORY_LABELS[t.category] ?? t.category} />
                    </td>
                    <td className="px-4 py-3">
                      <Chip tone={statusTone(t.status)} live={t.status === "OPEN"}>{STATUS_LABELS[t.status] ?? t.status}</Chip>
                    </td>
                    <td className="px-4 py-3">
                      <Figure
                        value={`${t.message_count} messaggi`}
                        detail={t.last_message_at ? <span title={formatDateTime(t.last_message_at)}>{formatDate(t.last_message_at)} · {relative(t.last_message_at)}</span> : "nessun aggiornamento"}
                      />
                    </td>
                    <td className="px-4 py-3">
                      <RowActions>
                        <button onClick={(e) => { e.stopPropagation(); setSelectedId(t.id); }} className="act act-primary">Apri</button>
                      </RowActions>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
      <Pagination {...pagination} label="ticket" />
    </div>
  );
}
