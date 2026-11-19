"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Pagination, usePagination } from "@/components/pagination";
import { friendlyApiError } from "@/lib/api-error";
import type { TicketDetailRead, TicketRead } from "@/lib/types";
import { Chip, Figure, Identity, KpiTile, RowActions, Stack, type ChipTone } from "@/components/ui/data-cells";

const CATEGORY_LABELS: Record<string, string> = {
  ASSISTENZA_TECNICA: "Assistenza tecnica",
  FATTURAZIONE: "Fatturazione",
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

const OPENER_LABELS: Record<string, string> = {
  CUSTOMER: "Cliente",
  PROMOTER: "Promoter",
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

const OPENER_FILTERS: { key: string; label: string }[] = [
  { key: "ALL", label: "Cliente e Promoter" },
  { key: "CUSTOMER", label: "Solo Clienti" },
  { key: "PROMOTER", label: "Solo Promoter" },
];

async function fetchAllTickets(): Promise<TicketRead[]> {
  const res = await fetch("/api/proxy/support/tickets");
  if (!res.ok) throw new Error("Impossibile caricare i ticket.");
  return res.json();
}

async function fetchTicketDetailAsStaff(id: string): Promise<TicketDetailRead> {
  const res = await fetch(`/api/proxy/support/tickets/${id}/staff`);
  if (!res.ok) throw new Error("Impossibile caricare il ticket.");
  return res.json();
}

function TrashIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
    </svg>
  );
}

export function AdminTicketsPanel() {
  const queryClient = useQueryClient();
  const { data: tickets, error: listError } = useQuery({ queryKey: ["admin", "tickets"], queryFn: fetchAllTickets });

  const [openerFilter, setOpenerFilter] = useState<string>("ALL");
  const [statusFilter, setStatusFilter] = useState<string>("ALL");
  const [categoryFilter, setCategoryFilter] = useState<string>("ALL");
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const [deletingTicket, setDeletingTicket] = useState<TicketRead | null>(null);
  const [deleteLoading, setDeleteLoading] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const { data: detail } = useQuery({
    queryKey: ["admin", "tickets", "detail", selectedId],
    queryFn: () => fetchTicketDetailAsStaff(selectedId as string),
    enabled: !!selectedId,
  });

  const [reply, setReply] = useState("");
  const [replyLoading, setReplyLoading] = useState(false);
  const [replyError, setReplyError] = useState<string | null>(null);
  const [statusLoading, setStatusLoading] = useState(false);

  const filteredTickets = (tickets ?? []).filter((t) => {
    const matchesOpener = openerFilter === "ALL" || t.opened_by_role === openerFilter;
    const matchesStatus = statusFilter === "ALL" || t.status === statusFilter;
    const matchesCategory = categoryFilter === "ALL" || t.category === categoryFilter;
    const q = searchQuery.trim().toLowerCase();
    const matchesSearch =
      q === "" ||
      t.subject.toLowerCase().includes(q) ||
      (t.opened_by_name ?? "").toLowerCase().includes(q);
    return matchesOpener && matchesStatus && matchesCategory && matchesSearch;
  });

  const pagination = usePagination(filteredTickets);

  const openCount = (tickets ?? []).filter((t) => t.status === "OPEN").length;

  async function refreshDetail() {
    await queryClient.invalidateQueries({ queryKey: ["admin", "tickets", "detail", selectedId] });
    await queryClient.invalidateQueries({ queryKey: ["admin", "tickets"] });
  }

  async function handleReply(e: React.FormEvent) {
    e.preventDefault();
    if (!selectedId) return;
    setReplyLoading(true);
    setReplyError(null);
    try {
      const res = await fetch(`/api/proxy/support/tickets/${selectedId}/staff-messages`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ body: reply }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      setReply("");
      await refreshDetail();
    } catch (err: any) {
      setReplyError(err.message || "Impossibile inviare la risposta.");
    } finally {
      setReplyLoading(false);
    }
  }

  async function handleStatusChange(newStatus: string) {
    if (!selectedId) return;
    setStatusLoading(true);
    try {
      const res = await fetch(`/api/proxy/support/tickets/${selectedId}/status`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: newStatus }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      await refreshDetail();
    } finally {
      setStatusLoading(false);
    }
  }

  async function handleDeleteTicket() {
    if (!deletingTicket) return;
    setDeleteLoading(true);
    setDeleteError(null);
    try {
      const res = await fetch(`/api/proxy/support/tickets/${deletingTicket.id}`, { method: "DELETE" });
      if (!res.ok) throw new Error(await friendlyApiError(res, "Impossibile eliminare il ticket."));
      if (selectedId === deletingTicket.id) setSelectedId(null);
      setDeletingTicket(null);
      await queryClient.invalidateQueries({ queryKey: ["admin", "tickets"] });
    } catch (err: any) {
      setDeleteError(err.message || "Impossibile eliminare il ticket.");
    } finally {
      setDeleteLoading(false);
    }
  }

  const deleteConfirmModal = deletingTicket && (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-fade-in">
      <div className="w-full max-w-md panel rounded-3xl p-7 border-white/10 bg-surface-950 pop">
        <div className="kpi-label">Azione irreversibile</div>
        <h3 className="mt-1 text-xl font-black tracking-tight text-white mb-2">Elimina ticket</h3>
        <p className="text-xs text-surface-300 mb-5">
          Stai per eliminare definitivamente il ticket{" "}
          <span className="font-semibold text-white">&quot;{deletingTicket.subject}&quot;</span> e
          tutti i suoi messaggi. L&apos;operazione non può essere annullata.
        </p>
        {deleteError && <p className="text-xs text-danger-400 mb-3">{deleteError}</p>}
        <div className="flex justify-end gap-3">
          <button onClick={() => { setDeletingTicket(null); setDeleteError(null); }} className="act !h-10 !px-4">
            Annulla
          </button>
          <button onClick={handleDeleteTicket} disabled={deleteLoading} className="act act-primary !h-10 !px-4">
            {deleteLoading ? "Eliminazione..." : "Elimina definitivamente"}
          </button>
        </div>
      </div>
    </div>
  );

  if (selectedId && detail) {
    return (
      <div className="space-y-5">
        <button onClick={() => setSelectedId(null)} className="act">
          ← Torna a tutti i ticket
        </button>

        <div className="panel rounded-3xl p-6 md:p-8">
          <div className="flex flex-wrap items-start justify-between gap-4 mb-6">
            <div className="min-w-0">
              <div className="kpi-label">{CATEGORY_LABELS[detail.category] ?? detail.category}</div>
              <h3 className="mt-1 text-2xl font-black tracking-tight text-white">{detail.subject}</h3>
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <Identity name={detail.opened_by_name ?? "—"} detail={OPENER_LABELS[detail.opened_by_role] ?? detail.opened_by_role} />
                <Chip tone={statusTone(detail.status)} live={detail.status === "OPEN"}>{STATUS_LABELS[detail.status] ?? detail.status}</Chip>
              </div>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <select
                value={detail.status}
                onChange={(e) => handleStatusChange(e.target.value)}
                disabled={statusLoading}
                aria-label="Cambia stato"
                className="field rounded-xl px-3 py-2 text-xs font-bold bg-surface-900 cursor-pointer"
              >
                {Object.entries(STATUS_LABELS).map(([code, label]) => (
                  <option key={code} value={code}>{label}</option>
                ))}
              </select>
              <button
                type="button"
                onClick={() => { if (detail.status === "RESOLVED") setDeletingTicket(detail); }}
                disabled={detail.status !== "RESOLVED"}
                title={detail.status === "RESOLVED" ? "Elimina ticket" : "Solo i ticket risolti possono essere eliminati"}
                className="act !h-9 hover:!text-danger-400"
              >
                <TrashIcon className="w-4 h-4" />
              </button>
            </div>
          </div>

          <div className="space-y-3 mb-6 stagger">
            {detail.messages.map((m, i) => {
              const isStaff = m.author_role === "ADMIN";
              return (
                <div key={m.id} style={{ "--i": Math.min(i, 12) } as React.CSSProperties} className={`flex ${isStaff ? "justify-end" : "justify-start"}`}>
                  <div
                    className={`max-w-[80%] rounded-3xl px-5 py-3 text-sm ${
                      isStaff
                        ? "bg-gradient-to-br from-brand-600/35 to-accent-500/20 border border-brand-400/30 text-white rounded-br-md"
                        : "bg-white/6 border border-white/10 text-surface-100 rounded-bl-md"
                    }`}
                  >
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-[10px] font-extrabold uppercase tracking-[0.14em] text-surface-300">
                        {isStaff ? "Tu (Assistenza)" : m.author_name ?? OPENER_LABELS[m.author_role] ?? m.author_role}
                      </span>
                      <span className="text-[10px] text-surface-400">{formatDateTime(m.created_at)}</span>
                    </div>
                    <p className="whitespace-pre-wrap">{m.body}</p>
                  </div>
                </div>
              );
            })}
          </div>

          <form onSubmit={handleReply} className="flex gap-2">
            <input
              required
              value={reply}
              onChange={(e) => setReply(e.target.value)}
              placeholder="Rispondi..."
              className="flex-1 rounded-2xl field px-4 py-3 text-sm focus:border-brand-500"
            />
            <button type="submit" disabled={replyLoading} className="act act-primary !h-auto !px-5">
              {replyLoading ? "Invio..." : "Rispondi"}
            </button>
          </form>
          {replyError && <p className="text-xs text-danger-400 mt-2">{replyError}</p>}
        </div>
        {deleteConfirmModal}
      </div>
    );
  }

  const countBy = (status: string) => (tickets ?? []).filter((t) => t.status === status).length;
  const kpis: { key: string; label: string; value: number; hint: string }[] = [
    { key: "OPEN", label: "Aperti", value: openCount, hint: "in attesa di risposta" },
    { key: "IN_PROGRESS", label: "In lavorazione", value: countBy("IN_PROGRESS"), hint: "presi in carico" },
    { key: "RESOLVED", label: "Risolti", value: countBy("RESOLVED"), hint: "eliminabili" },
    { key: "ALL", label: "Totale", value: (tickets ?? []).length, hint: "tutte le richieste" },
  ];

  return (
    <div className="space-y-6">
      {tickets !== undefined && (
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4 stagger">
          {kpis.map((k, i) => (
            <div key={k.key} style={{ "--i": i } as React.CSSProperties}>
              <KpiTile label={k.label} value={k.value} hint={k.hint} active={statusFilter === k.key} onClick={() => setStatusFilter(k.key)} />
            </div>
          ))}
        </div>
      )}

      <div className="flex flex-col gap-3">
        <div className="flex flex-col sm:flex-row sm:items-center gap-3">
          <p className="text-sm text-surface-300 flex-1">
            Ticket aperti da clienti e promoter. <strong className="text-white">{openCount}</strong> in attesa di risposta.
          </p>
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Cerca per oggetto o nome..."
            className="rounded-xl field px-3 py-2 text-xs bg-surface-900 focus:border-brand-500 w-full sm:w-64"
          />
        </div>
        <div className="flex items-center gap-3 flex-wrap">
          <div className="subnav">
            {OPENER_FILTERS.map((f) => (
              <button key={f.key} onClick={() => setOpenerFilter(f.key)} data-active={openerFilter === f.key} className="subnav-pill">
                {f.label}
              </button>
            ))}
          </div>
          <select
            value={categoryFilter}
            onChange={(e) => setCategoryFilter(e.target.value)}
            className="rounded-xl field px-3 py-2 text-xs bg-surface-900 focus:border-brand-500"
          >
            <option value="ALL">Tutte le categorie</option>
            {Object.entries(CATEGORY_LABELS).map(([code, label]) => (
              <option key={code} value={code}>{label}</option>
            ))}
          </select>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="rounded-xl field px-3 py-2 text-xs bg-surface-900 focus:border-brand-500"
          >
            <option value="ALL">Tutti gli stati</option>
            {Object.entries(STATUS_LABELS).map(([code, label]) => (
              <option key={code} value={code}>{label}</option>
            ))}
          </select>
        </div>
      </div>

      {listError && <p className="text-sm text-danger-400">Impossibile caricare i ticket.</p>}

      <div className="panel rounded-3xl p-4 md:p-6">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr>
                <th className="px-4 py-3">Richiedente</th>
                <th className="px-4 py-3">Argomento</th>
                <th className="px-4 py-3">Situazione</th>
                <th className="px-4 py-3 text-right">Conversazione</th>
                <th className="px-4 py-3"><span className="sr-only">Azioni</span></th>
              </tr>
            </thead>
            <tbody className="text-surface-300">
              {tickets === undefined ? (
                <tr><td colSpan={5} className="px-4 py-8 text-center text-surface-400">Caricamento...</td></tr>
              ) : filteredTickets.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-4 py-12">
                    <div className="flex flex-col items-center gap-2 text-center">
                      <svg viewBox="0 0 24 24" className="h-8 w-8 text-accent-300 float-soft" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
                        <path d="M4 5h16v11H9l-5 4z" strokeLinejoin="round" />
                      </svg>
                      <span className="text-sm font-semibold text-surface-200">Nessun ticket corrisponde ai filtri impostati.</span>
                    </div>
                  </td>
                </tr>
              ) : (
                pagination.pageItems.map((t) => (
                  <tr key={t.id} onClick={() => setSelectedId(t.id)} className="cursor-pointer">
                    <td className="px-4 py-3">
                      <Identity name={t.opened_by_name ?? "—"} detail={OPENER_LABELS[t.opened_by_role] ?? t.opened_by_role} />
                    </td>
                    <td className="px-4 py-3">
                      <Stack title={t.subject} detail={CATEGORY_LABELS[t.category] ?? t.category} className="max-w-[320px]" />
                    </td>
                    <td className="px-4 py-3">
                      <Chip tone={statusTone(t.status)} live={t.status === "OPEN"}>{STATUS_LABELS[t.status] ?? t.status}</Chip>
                    </td>
                    <td className="px-4 py-3">
                      <Figure
                        value={`${t.message_count} msg`}
                        detail={t.last_message_at ? <span title={formatDateTime(t.last_message_at)}>{formatDate(t.last_message_at)} · {relative(t.last_message_at)}</span> : "nessun aggiornamento"}
                      />
                    </td>
                    <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
                      <RowActions>
                        <button onClick={() => setSelectedId(t.id)} className="act act-primary">Apri</button>
                        <button
                          type="button"
                          onClick={() => { if (t.status === "RESOLVED") setDeletingTicket(t); }}
                          disabled={t.status !== "RESOLVED"}
                          title={t.status === "RESOLVED" ? "Elimina ticket" : "Solo i ticket risolti possono essere eliminati"}
                          aria-label="Elimina ticket"
                          className="act hover:!text-danger-400"
                        >
                          <TrashIcon className="w-4 h-4" />
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
      <Pagination {...pagination} label="ticket" />
      {deleteConfirmModal}
    </div>
  );
}
