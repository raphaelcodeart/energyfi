"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { friendlyApiError } from "@/lib/api-error";
import { LEAD_STATUS_LABELS } from "@/lib/commission-labels";
import type { LeadRead, ProductCatalogRead } from "@/lib/types";
import { Chip, IdTag, Identity, RowActions, Stack, type ChipTone } from "@/components/ui/data-cells";
import { AgentPicker } from "@/components/agent-picker";

async function getJson<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(await friendlyApiError(res));
  return res.json();
}

function statusTone(status: string): ChipTone {
  if (status === "CONVERTED") return "ok";
  if (status === "LOST") return "bad";
  if (status === "EXPIRED") return "muted";
  if (status === "QUALIFIED") return "warn";
  return "info";
}

function fmtDate(iso: string): string {
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

/**
 * Leads: a Promoter brings an opportunity, someone else closes it. The fee
 * accrues only when the lead becomes an active contract, and the sale's
 * Split Plan sets it.
 * `mode="mine"`: collaborators see and record their own.
 * `mode="admin"`: administrators see all, assign and close them.
 */
export function LeadsPanel({ mode }: { mode: "mine" | "admin" }) {
  const queryClient = useQueryClient();
  const url = mode === "mine" ? "/api/proxy/leads/mine" : "/api/proxy/leads";
  const { data: leads, isLoading } = useQuery({ queryKey: ["leads", mode], queryFn: () => getJson<LeadRead[]>(url) });
  const { data: products } = useQuery({ queryKey: ["leads", "products"], queryFn: () => getJson<ProductCatalogRead[]>("/api/proxy/products") });
  const [form, setForm] = useState({ contact_name: "", contact_email: "", contact_phone: "", product_id: "", notes: "", promoter_agent_id: "" });
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);

  async function send(path: string, method: string, body: unknown, done: string) {
    setError(null);
    setOk(null);
    try {
      const res = await fetch(path, { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      await queryClient.invalidateQueries({ queryKey: ["leads"] });
      setOk(done);
      return true;
    } catch (err: any) {
      setError(err.message || "Operazione non riuscita.");
      return false;
    }
  }

  async function create() {
    const saved = await send("/api/proxy/leads", "POST", {
      contact_name: form.contact_name,
      contact_email: form.contact_email || null,
      contact_phone: form.contact_phone || null,
      product_id: form.product_id || null,
      notes: form.notes,
      promoter_agent_id: mode === "admin" ? form.promoter_agent_id || null : null,
    }, "Segnalazione registrata.");
    if (saved) setForm({ contact_name: "", contact_email: "", contact_phone: "", product_id: "", notes: "", promoter_agent_id: "" });
  }

  const productName = (id: string | null) => (products ?? []).find((p) => p.id === id)?.current_version?.name ?? "—";
  const field = "w-full rounded-xl field px-3 py-2 text-sm bg-surface-900 focus:border-brand-500";
  const colCount = mode === "admin" ? 6 : 4;

  return (
    <div className="space-y-6">
      <div className="panel rounded-3xl p-6 md:p-7 space-y-4 rise">
        <div>
          <div className="kpi-label">Opportunità</div>
          <h3 className="mt-1 text-xl font-black tracking-tight text-white">Nuova segnalazione</h3>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs text-surface-300">
          <label className="space-y-1"><span>Nome e cognome (o azienda)</span><input className={field} value={form.contact_name} onChange={(e) => setForm({ ...form, contact_name: e.target.value })} /></label>
          <label className="space-y-1"><span>Email</span><input className={field} type="email" value={form.contact_email} onChange={(e) => setForm({ ...form, contact_email: e.target.value })} /></label>
          <label className="space-y-1"><span>Telefono</span><input className={field} value={form.contact_phone} onChange={(e) => setForm({ ...form, contact_phone: e.target.value })} /></label>
          <label className="space-y-1"><span>Prodotto di interesse</span>
            <select className={field} value={form.product_id} onChange={(e) => setForm({ ...form, product_id: e.target.value })}>
              <option value="">Non specificato</option>
              {(products ?? []).map((p) => <option key={p.id} value={p.id}>{p.current_version?.name ?? p.code}</option>)}
            </select>
          </label>
          {mode === "admin" && (
            <label className="space-y-1"><span>A nome del promoter</span>
              <AgentPicker value={form.promoter_agent_id} onChange={(id) => setForm({ ...form, promoter_agent_id: id })}
                status="ACTIVE" allowEmpty={false} required placeholder="Scegli…" ariaLabel="A nome del promoter" />
            </label>
          )}
          <label className="space-y-1 md:col-span-3"><span>Note</span><input className={field} value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} /></label>
        </div>
        <button
          onClick={create}
          disabled={!form.contact_name.trim() || (mode === "admin" && !form.promoter_agent_id)}
          className="act act-primary !h-10 !px-5 !text-[13px]"
        >
          Registra segnalazione
        </button>
        {mode === "mine" && (
          <p className="text-[11px] text-surface-400">
            La tua fee matura solo se la segnalazione diventa un contratto attivo. Se il cliente si registra dal tuo link, la
            segnalazione nasce da sola.
          </p>
        )}
      </div>

      {error && <div className="p-3 rounded-2xl bg-danger-500/10 border border-danger-500/20 text-danger-400 text-xs pop">{error}</div>}
      {ok && <div className="p-3 rounded-2xl bg-success-500/10 border border-success-500/20 text-success-400 text-xs pop">{ok}</div>}

      <div className="panel rounded-3xl p-4 md:p-6">
        <div className="flex items-end justify-between gap-3 px-2">
          <div>
            <div className="kpi-label">{mode === "admin" ? "Tutte le segnalazioni" : "Le tue segnalazioni"}</div>
            <h3 className="mt-1 text-xl font-black tracking-tight text-white">Pipeline</h3>
          </div>
          {!isLoading && <Chip tone="accent">{(leads ?? []).length} in elenco</Chip>}
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-xs text-left">
            <thead>
              <tr>
                <th className="px-4 py-3">Contatto</th>
                <th className="px-4 py-3">Interesse</th>
                {mode === "admin" && <th className="px-4 py-3">Portata da</th>}
                <th className="px-4 py-3">Quando</th>
                <th className="px-4 py-3">Situazione</th>
                {mode === "admin" && <th className="px-4 py-3"><span className="sr-only">Azioni</span></th>}
              </tr>
            </thead>
            <tbody className="text-surface-300">
              {isLoading && <tr><td colSpan={colCount} className="px-4 py-8 text-center text-surface-400">Caricamento…</td></tr>}
              {!isLoading && (leads ?? []).length === 0 && (
                <tr>
                  <td colSpan={colCount} className="px-4 py-10">
                    <div className="flex flex-col items-center gap-2 text-center">
                      <svg viewBox="0 0 24 24" className="h-8 w-8 text-accent-300 float-soft" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
                        <path d="M3 11l18-7-7 18-2-8-9-3z" strokeLinejoin="round" />
                      </svg>
                      <span className="text-sm font-semibold text-surface-200">Nessuna segnalazione per ora.</span>
                    </div>
                  </td>
                </tr>
              )}
              {(leads ?? []).map((l) => (
                <tr key={l.id}>
                  <td className="px-4 py-3">
                    <Identity name={l.contact_name} detail={[l.contact_email, l.contact_phone].filter(Boolean).join(" · ") || "Nessun recapito"} />
                  </td>
                  <td className="px-4 py-3">
                    <Stack title={productName(l.product_id)} detail={l.notes ? <span title={l.notes}>{l.notes}</span> : undefined} className="max-w-[220px]" />
                  </td>
                  {mode === "admin" && (
                    <td className="px-4 py-3">
                      <Stack title={l.promoter_name} detail={l.assigned_agent_name ? `segue: ${l.assigned_agent_name}` : "da assegnare"} />
                    </td>
                  )}
                  <td className="px-4 py-3 whitespace-nowrap">
                    <Stack title={fmtDate(l.created_at)} detail={relative(l.created_at)} />
                  </td>
                  <td className="px-4 py-3">
                    <Chip tone={statusTone(l.status)} live={l.status === "QUALIFIED" || l.status === "NEW"}>{LEAD_STATUS_LABELS[l.status] ?? l.status}</Chip>
                  </td>
                  {mode === "admin" && (
                    <td className="px-4 py-3">
                      {(l.status === "NEW" || l.status === "QUALIFIED") && (
                        <RowActions>
                          {l.status === "NEW" && <button onClick={() => send(`/api/proxy/leads/${l.id}`, "PATCH", { status: "QUALIFIED" }, "Segnalazione in lavorazione.")} className="act act-primary">In lavorazione</button>}
                          <button onClick={() => send(`/api/proxy/leads/${l.id}`, "PATCH", { status: "LOST" }, "Segnalazione chiusa.")} className="act">Persa</button>
                          <AgentPicker
                            className="w-52"
                            value={l.assigned_agent_id ?? ""}
                            onChange={(id) => send(`/api/proxy/leads/${l.id}`, "PATCH", { assigned_agent_id: id || null }, "Segnalazione assegnata.")}
                            status="ACTIVE"
                            placeholder="Assegna a…"
                            emptyLabel="Nessuno (togli l'assegnazione)"
                            ariaLabel="Assegna a"
                          />
                        </RowActions>
                      )}
                      {l.status === "CONVERTED" && (
                        <div className="flex items-center justify-end gap-2 text-[10.5px] text-success-400">
                          contratto <IdTag id={l.converted_contract_id} />
                        </div>
                      )}
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
