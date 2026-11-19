"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Chip, KpiTile } from "@/components/ui/data-cells";
import { Empty, ErrorNote, Field, Loading, Modal, OkNote, Progress, Rainbow, SectionTitle } from "@/components/affiliate/shared";
import {
  affiliateGet,
  affiliateSend,
  bc,
  COMMISSION_LABELS,
  COMMISSION_STATUS,
  eur,
  LICENSE_STATUS,
  mamicash,
  num,
  OPERATION_LABELS,
  OPERATION_STATUS,
  PAYMENT_METHODS,
  periodLabel,
  productName,
  shortDate,
  type AffiliateSummary,
  type AgentBrief,
  type Catalog,
  type ClientRow,
  type CommissionRow,
  type LicenseRow,
  type OperationRow,
  type PlanConfig,
  type TreeRow,
} from "@/lib/affiliate";
import { AdminLicenseMargins, AdminLicenseRegister } from "@/components/affiliate/license-register";
import { MamifyPanel } from "@/components/affiliate/mamify-panel";
import { BranchSyncButton } from "@/components/branch-sync-button";
import { NetworkTree } from "@/components/affiliate/network-tree";

/*
 * SOS Affiliate administration (spec §10.1, ADM-01..ADM-08): network and
 * volumes, operations to confirm, commissions to pay, monthly closes,
 * versioned plan and exports.
 */

export type AdminAffiliateView = "sos-overview" | "sos-tree" | "sos-operations" | "sos-affiliates" | "sos-commissions" | "sos-periods" | "sos-registry" | "sos-plan" | "sos-mamify";

type Overview = {
  period: string;
  plan_version: { id: string; label: string };
  affiliates: number;
  active_this_month: number;
  total_points: number;
  qualified_this_month: number;
  career_bonus_estimate: string;
  levels_distribution: Record<string, number>;
  pending: { kind: string; count: number; amount: string }[];
  payable_now: Record<string, string>;
  month_operations: { kind: string; count: number; amount: string }[];
  rome_event: { period: string; target_bc: number; qualified: { agent: AgentBrief; bct: number }[] } | null;
};

type AffiliateRow = {
  agent: AgentBrief;
  sponsor: AgentBrief | null;
  subscription_status: string;
  bcp: number;
  bct: number;
  legs_count: number;
  level: number | null;
  bonus: string;
  joined_at: string;
};

type Periods = {
  current_period: string;
  open_periods: string[];
  closed: { period: string; closed_at: string; affiliates_count: number; qualified_count: number; total_points: number; total_bonus: string; automatic: boolean }[];
};

type PeriodResult = { agent: AgentBrief | null; bcp: number; bct: number; legs: { leg_agent_id: string; points: number; name: string | null }[]; level: number | null; bonus: string; closed: boolean };

type PlanVersion = { id: string; label: string; valid_from: string; notes: string | null; config: PlanConfig; is_current: boolean };

function useInvalidate() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: ["affiliate"] });
}

function useCatalog() {
  return useQuery({ queryKey: ["affiliate", "catalog"], queryFn: () => affiliateGet<Catalog>("/catalog"), staleTime: 300_000 });
}

export function AdminAffiliatePanel({ view, onNavigate }: { view: AdminAffiliateView; onNavigate: (key: AdminAffiliateView) => void }) {
  switch (view) {
    case "sos-overview":
      return <OverviewView onNavigate={onNavigate} />;
    case "sos-operations":
      return <OperationsView />;
    case "sos-affiliates":
      return <AffiliatesView />;
    case "sos-commissions":
      return <CommissionsView />;
    case "sos-periods":
      return <PeriodsView />;
    case "sos-registry":
      return <RegistryView />;
    case "sos-plan":
      return <PlanView />;
    case "sos-tree":
      return <TreeView />;
    case "sos-mamify":
      return <MamifyPanel />;
  }
}

// --- Albero della rete ----------------------------------------------------------

function TreeView() {
  const [open, setOpen] = useState<string | null>(null);
  const { data: catalog } = useCatalog();
  return (
    <div className="space-y-5">
      <SectionTitle eyebrow="Albero della rete" title="Tutta la rete, ramo per ramo" />
      <p className="text-xs text-surface-300">
        L&apos;albero è quello di Mamify, letto dal collegamento Mamify: i nuovi iscritti ogni 5 minuti, tutta la rete ogni notte. Volumi e livelli sono quelli del mese in corso.
      </p>
      <NetworkTree base="admin" levels={catalog?.config.career_levels} onOpenDetail={setOpen}
        emptyText="La rete è vuota: collega Mamify e copia la rete dalla sezione «Collegamento Mamify»." />
      {open && <AffiliateDetail agentId={open} onClose={() => setOpen(null)} />}
    </div>
  );
}

function download(dataset: string) {
  window.location.href = `/api/proxy/affiliate/admin/export/${dataset}`;
}

// --- Panoramica ---------------------------------------------------------------

function OverviewView({ onNavigate }: { onNavigate: (key: AdminAffiliateView) => void }) {
  const { data, isLoading, error } = useQuery({ queryKey: ["affiliate", "admin", "overview"], queryFn: () => affiliateGet<Overview>("/admin/overview") });
  if (isLoading) return <Loading />;
  if (error || !data) return <ErrorNote message={(error as Error)?.message} />;
  const pendingCount = data.pending.reduce((s, p) => s + p.count, 0);
  const pendingAmount = data.pending.reduce((s, p) => s + Number(p.amount), 0);
  const payable = Object.values(data.payable_now).reduce((s, v) => s + Number(v), 0);
  const maxLevel = Math.max(1, ...Object.values(data.levels_distribution));
  return (
    <div className="space-y-6">
      <div className="panel sheen rise rounded-3xl p-6">
        <p className="kpi-label">SOS Affiliate · {periodLabel(data.period)} · piano {data.plan_version.label}</p>
        <h2 className="mt-1 text-3xl font-black tracking-tight text-white">Rete Digital Ambassador</h2>
        <Rainbow className="mt-3 w-40" />
      </div>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <KpiTile label="Digital Ambassador" value={num(data.affiliates)} hint={`${data.active_this_month} con punti questo mese`} onClick={() => onNavigate("sos-affiliates")} />
        <KpiTile label="BC generati nel mese" value={num(data.total_points)} hint="Punti personali, senza doppi conteggi" />
        <KpiTile label="Qualificati al Bonus Carriera" value={num(data.qualified_this_month)} hint={`Stima ${eur(data.career_bonus_estimate)} da pagare il 15`} onClick={() => onNavigate("sos-periods")} />
        <KpiTile label="Da confermare" value={num(pendingCount)} hint={`${eur(pendingAmount)} in attesa di pagamento`} onClick={() => onNavigate("sos-operations")} />
      </div>
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="panel rounded-3xl p-5 lg:col-span-2">
          <SectionTitle eyebrow="Questo mese" title="Livelli raggiunti" />
          <div className="mt-4 grid grid-cols-11 items-end gap-2" style={{ height: 140 }}>
            {Array.from({ length: 11 }, (_, i) => String(i + 1)).map((lv) => {
              const count = data.levels_distribution[lv] ?? 0;
              return (
                <div key={lv} className="flex h-full flex-col items-center justify-end gap-1">
                  <span className="text-[11px] tabular-nums text-white">{count || ""}</span>
                  <div className="w-full rounded-t-lg bg-gradient-to-t from-brand-600 to-accent-400" style={{ height: `${(count / maxLevel) * 100}%`, minHeight: count ? 6 : 2, opacity: count ? 1 : 0.25 }} />
                  <span className="text-[10px] text-surface-400">L{lv}</span>
                </div>
              );
            })}
          </div>
          <div className="mt-6 grid gap-3 sm:grid-cols-2">
            {data.month_operations.length === 0 ? <p className="text-sm text-surface-300">Nessuna operazione confermata nel mese.</p> :
              data.month_operations.map((m) => (
                <div key={m.kind} className="flex items-center justify-between rounded-2xl bg-white/5 px-4 py-3 text-sm">
                  <span className="text-surface-200">{OPERATION_LABELS[m.kind] ?? m.kind} <span className="text-surface-400">· {m.count}</span></span>
                  <span className="font-bold tabular-nums text-white">{eur(m.amount)}</span>
                </div>
              ))}
          </div>
        </div>
        <div className="space-y-4">
          <div className="panel rounded-3xl p-5">
            <p className="kpi-label">Compensi pagabili oggi</p>
            <p className="mt-1 text-2xl font-black text-white">{eur(payable)}</p>
            <div className="mt-3 space-y-1 text-xs">
              {Object.entries(data.payable_now).map(([k, v]) => (
                <div key={k} className="flex justify-between"><span className="text-surface-300">{COMMISSION_LABELS[k] ?? k}</span><span className="tabular-nums text-white">{eur(v)}</span></div>
              ))}
            </div>
            <button type="button" onClick={() => onNavigate("sos-commissions")} className="act act-primary mt-4 w-full justify-center">Vai ai pagamenti</button>
          </div>
          {data.rome_event && (
            <div className="panel rounded-3xl p-5">
              <p className="kpi-label">Promo Evento di lancio a Roma</p>
              <p className="mt-1 text-sm text-white">{num(data.rome_event.target_bc)} BC totali a {periodLabel(data.rome_event.period)}</p>
              <p className="mt-2 text-2xl font-black text-white">{data.rome_event.qualified.length} <span className="text-sm font-semibold text-surface-300">ospiti qualificati</span></p>
              <ul className="mt-2 space-y-1 text-xs">
                {data.rome_event.qualified.slice(0, 8).map((q) => (
                  <li key={q.agent?.id} className="flex justify-between"><span className="text-surface-200">{q.agent?.name}</span><span className="tabular-nums text-white">{bc(q.bct)}</span></li>
                ))}
              </ul>
            </div>
          )}
          <div className="panel rounded-3xl p-5">
            <p className="kpi-label">Esporta (CSV per Excel)</p>
            <div className="mt-3 grid grid-cols-2 gap-2">
              {([["operations", "Operazioni"], ["commissions", "Compensi"], ["licenses", "Licenze"], ["affiliates", "Affiliati"]] as const).map(([k, l]) => (
                <button key={k} type="button" onClick={() => download(k)} className="act justify-center">{l}</button>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// --- Operazioni ---------------------------------------------------------------

const OP_FILTERS = [
  { key: "PENDING", label: "Da confermare" },
  { key: "CONFIRMED", label: "Confermate" },
  { key: "REVERSED", label: "Rettificate" },
  { key: "CANCELLED", label: "Annullate" },
  { key: "", label: "Tutte" },
];

function OperationsView() {
  const [status, setStatus] = useState("PENDING");
  const { data: catalog } = useCatalog();
  const { data: ops, isLoading } = useQuery({
    queryKey: ["affiliate", "admin", "operations", status],
    queryFn: () => affiliateGet<OperationRow[]>(`/admin/operations${status ? `?status_filter=${status}` : ""}`),
  });
  const invalidate = useInvalidate();
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);
  const [reversing, setReversing] = useState<OperationRow | null>(null);
  const [registering, setRegistering] = useState(false);
  const act = useMutation({
    mutationFn: ({ id, action }: { id: string; action: "confirm" | "cancel" }) => affiliateSend(`/admin/operations/${id}/${action}`, {}),
    onSuccess: (_, v) => { setError(null); setOk(v.action === "confirm" ? "Pagamento confermato: punti, licenze e bonus sono stati registrati." : "Operazione annullata."); invalidate(); },
    onError: (e: Error) => { setOk(null); setError(e.message); },
  });
  return (
    <div className="space-y-5">
      <SectionTitle eyebrow="Operazioni" title="Pagamenti da confermare e storico">
        <button type="button" onClick={() => setRegistering(true)} className="act act-primary">Registra un pagamento</button>
      </SectionTitle>
      <div className="subnav">
        {OP_FILTERS.map((f) => (
          <button key={f.key} type="button" onClick={() => setStatus(f.key)} className="subnav-pill" data-active={status === f.key || undefined}>{f.label}</button>
        ))}
      </div>
      <OkNote message={ok} />
      <ErrorNote message={error} />
      {isLoading ? <Loading /> : (ops ?? []).length === 0 ? <Empty>Nessuna operazione in questo elenco.</Empty> : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead><tr>
              <th className="px-4 py-3">Operazione</th><th className="px-4 py-3">Digital Ambassador</th><th className="px-4 py-3">Data</th>
              <th className="px-4 py-3 text-right">Importo</th><th className="px-4 py-3 text-right">BC</th><th className="px-4 py-3">Stato</th><th className="px-4 py-3"><span className="sr-only">Azioni</span></th>
            </tr></thead>
            <tbody>
              {(ops ?? []).map((o) => (
                <tr key={o.id}>
                  <td className="px-4 py-3">
                    <p className="font-semibold text-white">{OPERATION_LABELS[o.kind] ?? o.kind}</p>
                    <p className="text-xs text-surface-400">
                      {productName(catalog?.config, o.product_code)}{o.period && o.kind === "SUBSCRIPTION_PAYMENT" ? ` · ${periodLabel(o.period)}` : ""}
                      {o.client ? ` · ${o.client.name}` : ""}{o.license_code ? ` · ${o.license_code}` : ""}
                    </p>
                    <p className="tag-id mt-0.5 text-[10px]">{o.id.slice(0, 8).toUpperCase()}</p>
                  </td>
                  <td className="px-4 py-3">{o.agent?.name}<p className="text-xs text-surface-400">{o.agent?.code}</p></td>
                  <td className="px-4 py-3">{shortDate(o.created_at)}</td>
                  <td className="px-4 py-3 text-right tabular-nums">{eur(o.paid_amount)}</td>
                  <td className="px-4 py-3 text-right tabular-nums">{o.bc_points ? num(o.bc_points) : "—"}</td>
                  <td className="px-4 py-3"><Chip tone={OPERATION_STATUS[o.status]?.tone ?? "muted"}>{OPERATION_STATUS[o.status]?.label ?? o.status}</Chip></td>
                  <td className="px-4 py-3 text-right">
                    <div className="flex justify-end gap-2">
                      {o.status === "PENDING" && <>
                        <button type="button" disabled={act.isPending} onClick={() => act.mutate({ id: o.id, action: "confirm" })} className="act act-primary disabled:opacity-50">Conferma pagamento</button>
                        <button type="button" disabled={act.isPending} onClick={() => act.mutate({ id: o.id, action: "cancel" })} className="act disabled:opacity-50">Annulla</button>
                      </>}
                      {o.status === "CONFIRMED" && o.kind !== "REVERSAL" && o.kind !== "GIFT_LICENSE" && (
                        <button type="button" onClick={() => setReversing(o)} className="act">Rettifica</button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {reversing && <ReverseModal op={reversing} onClose={() => setReversing(null)} />}
      {registering && <RegisterPaymentModal onClose={() => setRegistering(false)} />}
    </div>
  );
}

function ReverseModal({ op, onClose }: { op: OperationRow; onClose: () => void }) {
  const invalidate = useInvalidate();
  const [reason, setReason] = useState("");
  const reverse = useMutation({
    mutationFn: () => affiliateSend(`/admin/operations/${op.id}/reverse`, { reason }),
    onSuccess: () => { invalidate(); onClose(); },
  });
  return (
    <Modal title="Rettifica operazione" onClose={onClose}>
      <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); reverse.mutate(); }}>
        <p className="text-sm text-surface-200">
          {OPERATION_LABELS[op.kind]} di {op.agent?.name} · {eur(op.paid_amount)}. La rettifica non cancella nulla: registra punti negativi e annulla i bonus non ancora pagati; quelli già pagati diventano un recupero.
        </p>
        <Field label="Motivo (resta nello storico)">
          <textarea required minLength={3} rows={3} className="field w-full rounded-xl px-3 py-2.5 text-sm" value={reason} onChange={(e) => setReason(e.target.value)} />
        </Field>
        <ErrorNote message={(reverse.error as Error | null)?.message} />
        <button type="submit" disabled={reverse.isPending} className="act act-primary w-full justify-center disabled:opacity-50">Conferma la rettifica</button>
      </form>
    </Modal>
  );
}

function RegisterPaymentModal({ onClose }: { onClose: () => void }) {
  const invalidate = useInvalidate();
  const { data: catalog } = useCatalog();
  const [who, setWho] = useState("");
  const { data: affiliates } = useQuery({
    queryKey: ["affiliate", "admin", "affiliates", who],
    queryFn: () => affiliateGet<AffiliateRow[]>(`/admin/affiliates?limit=100${who.trim() ? `&search=${encodeURIComponent(who.trim())}` : ""}`),
  });
  const now = new Date();
  const [form, setForm] = useState({
    agent_id: "", product_code: "DIGITAL_AMBASSADOR",
    period: `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`, payment_method: "BANK_TRANSFER", confirm_now: true,
  });
  const save = useMutation({
    mutationFn: () => affiliateSend("/admin/purchases", { ...form, period: form.product_code === "DIGITAL_AMBASSADOR" ? form.period : null }),
    onSuccess: () => { invalidate(); onClose(); },
  });
  const cfg = catalog?.config;
  const products = cfg ? [cfg.subscription, ...cfg.license_products, ...cfg.event_ticket_products] : [];
  return (
    <Modal title="Registra un pagamento ricevuto" onClose={onClose}>
      <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
        <Field label="Digital Ambassador">
          <input className="field mb-2 w-full rounded-xl px-3 py-2.5 text-sm" placeholder="Cerca per nome o codice" value={who} onChange={(e) => setWho(e.target.value)} aria-label="Cerca il Digital Ambassador" />
          <select required className="field w-full rounded-xl px-3 py-2.5 text-sm" value={form.agent_id} onChange={(e) => setForm({ ...form, agent_id: e.target.value })}>
            <option value="">Scegli…</option>
            {(affiliates ?? []).map((a) => <option key={a.agent.id} value={a.agent.id}>{a.agent.name} · {a.agent.code}</option>)}
          </select>
        </Field>
        <Field label="Prodotto">
          <select className="field w-full rounded-xl px-3 py-2.5 text-sm" value={form.product_code} onChange={(e) => setForm({ ...form, product_code: e.target.value })}>
            {products.map((p) => <option key={p.code} value={p.code}>{p.name} · {eur(p.price)} · {bc(p.bc)}</option>)}
          </select>
        </Field>
        {form.product_code === "DIGITAL_AMBASSADOR" && (
          <Field label="Mese pagato"><input type="month" required className="field w-full rounded-xl px-3 py-2.5 text-sm" value={form.period} onChange={(e) => setForm({ ...form, period: e.target.value })} /></Field>
        )}
        <Field label="Metodo">
          <select className="field w-full rounded-xl px-3 py-2.5 text-sm" value={form.payment_method} onChange={(e) => setForm({ ...form, payment_method: e.target.value })}>
            {PAYMENT_METHODS.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
          </select>
        </Field>
        <label className="flex items-center gap-2 text-sm text-surface-200">
          <input type="checkbox" checked={form.confirm_now} onChange={(e) => setForm({ ...form, confirm_now: e.target.checked })} />
          Il pagamento è già arrivato: conferma subito
        </label>
        <ErrorNote message={(save.error as Error | null)?.message} />
        <button type="submit" disabled={save.isPending || !form.agent_id} className="act act-primary w-full justify-center disabled:opacity-50">Registra</button>
      </form>
    </Modal>
  );
}

// --- Digital Ambassador -------------------------------------------------------

function AffiliatesView() {
  const [search, setSearch] = useState("");
  const [open, setOpen] = useState<string | null>(null);
  const { data, isLoading } = useQuery({
    queryKey: ["affiliate", "admin", "affiliates", search],
    queryFn: () => affiliateGet<AffiliateRow[]>(`/admin/affiliates${search ? `?search=${encodeURIComponent(search)}` : ""}`),
  });
  return (
    <div className="space-y-5">
      <SectionTitle eyebrow="Digital Ambassador" title="Volumi del mese, persona per persona">
        <input placeholder="Cerca per nome o codice" className="field w-64 rounded-xl px-3 py-2 text-sm" value={search} onChange={(e) => setSearch(e.target.value)} />
      </SectionTitle>
      <p className="text-xs text-surface-300">Per aggiungere o approvare un Digital Ambassador usa la sezione della rete: ogni collaboratore è un Digital Ambassador. L&apos;elenco mostra i primi 300 per volume del mese: usa la ricerca per trovare chiunque altro.</p>
      {isLoading ? <Loading /> : (data ?? []).length === 0 ? <Empty>Nessun Digital Ambassador.</Empty> : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead><tr>
              <th className="px-4 py-3">Digital Ambassador</th><th className="px-4 py-3">Sponsor</th><th className="px-4 py-3">Abbonamento</th>
              <th className="px-4 py-3 text-right">BCP</th><th className="px-4 py-3 text-right">BCT</th><th className="px-4 py-3 text-right">Gambe attive</th><th className="px-4 py-3">Livello</th><th className="px-4 py-3 text-right">Bonus</th>
            </tr></thead>
            <tbody>
              {(data ?? []).map((a) => (
                <tr key={a.agent.id} className="cursor-pointer" onClick={() => setOpen(a.agent.id)}>
                  <td className="px-4 py-3"><p className="font-semibold text-white">{a.agent.name}</p><p className="text-xs text-surface-400">{a.agent.code}</p></td>
                  <td className="px-4 py-3">{a.sponsor?.name ?? "—"}</td>
                  <td className="px-4 py-3"><SubscriptionChip status={a.subscription_status} /></td>
                  <td className="px-4 py-3 text-right tabular-nums">{num(a.bcp)}</td>
                  <td className="px-4 py-3 text-right tabular-nums">{num(a.bct)}</td>
                  <td className="px-4 py-3 text-right tabular-nums">{a.legs_count}</td>
                  <td className="px-4 py-3">{a.level ? `Livello ${a.level}` : "—"}</td>
                  <td className="px-4 py-3 text-right tabular-nums">{eur(a.bonus)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {open && <AffiliateDetail agentId={open} onClose={() => setOpen(null)} />}
    </div>
  );
}

function SubscriptionChip({ status }: { status: string }) {
  const map: Record<string, { label: string; tone: "ok" | "warn" | "bad" | "muted" }> = {
    ACTIVE: { label: "Attivo", tone: "ok" }, SUSPENDED: { label: "Sospeso", tone: "warn" },
    CANCELLED: { label: "Cessato", tone: "bad" }, NONE: { label: "Mai pagato", tone: "muted" },
  };
  const s = map[status] ?? { label: status, tone: "muted" as const };
  return <Chip tone={s.tone}>{s.label}</Chip>;
}

function AffiliateDetail({ agentId, onClose }: { agentId: string; onClose: () => void }) {
  const invalidate = useInvalidate();
  const { data: s, isLoading } = useQuery({ queryKey: ["affiliate", "admin", "affiliate", agentId], queryFn: () => affiliateGet<AffiliateSummary>(`/admin/affiliates/${agentId}`) });
  const setStatus = useMutation({
    mutationFn: (status: string) => affiliateSend(`/admin/affiliates/${agentId}/subscription`, { status, reason: "Dal pannello amministrativo" }, "PATCH"),
    onSuccess: () => invalidate(),
  });
  return (
    <Modal title={s ? s.agent.name : "Digital Ambassador"} onClose={onClose} wide>
      {isLoading || !s ? <Loading /> : (
        <div className="space-y-5">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Mini label="BCP" value={num(s.career.bcp)} />
            <Mini label="BCT" value={num(s.career.bct)} />
            <Mini label="Livello" value={s.career.level ? String(s.career.level) : "—"} />
            <Mini label="Bonus del mese" value={eur(s.career.bonus)} />
          </div>
          <BranchSyncButton agentId={agentId} />
          <div className="grid gap-3 text-sm sm:grid-cols-2">
            <p className="text-surface-300">Sponsor: <span className="text-white">{s.sponsor?.name ?? "nessuno"}</span></p>
            <p className="text-surface-300">Rete: <span className="text-white">{s.direct_count} diretti · {num(s.network_size)} persone</span></p>
            <p className="text-surface-300">Mensilità pagate: <span className="text-white">{s.subscription.paid_months}</span> · ultima {periodLabel(s.subscription.last_paid_period)}</p>
            <p className="text-surface-300">Licenze: <span className="text-white">{s.licenses.available} disponibili · {s.licenses.resold} rivendute</span></p>
          </div>
          <div>
            <p className="kpi-label mb-2">Gambe · {periodLabel(s.period)}</p>
            <div className="space-y-2">
              {s.legs.length === 0 ? <p className="text-sm text-surface-300">Nessuna gamba.</p> : s.legs.map((l, i) => (
                <Progress key={l.agent?.id ?? i} label={`${l.agent?.name ?? "—"} · ${num(l.descendants + 1)} persone`} value={l.points}
                  target={s.career.next_leg_min_bc || 1} detail={bc(l.points)} />
              ))}
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {(["BC", "BD", "BM", "RESALE"] as const).map((k) => (
              <Mini key={k} label={COMMISSION_LABELS[k] ?? k} value={eur(Number(s.commissions[k]?.payable ?? 0) + Number(s.commissions[k]?.paid ?? 0))} />
            ))}
          </div>
          <div className="flex flex-wrap items-center gap-2 border-t border-white/10 pt-4">
            <span className="kpi-label mr-2">Abbonamento</span>
            <SubscriptionChip status={s.subscription.status} />
            {(["ACTIVE", "SUSPENDED", "CANCELLED"] as const).filter((st) => st !== s.subscription.status).map((st) => (
              <button key={st} type="button" disabled={setStatus.isPending} onClick={() => setStatus.mutate(st)} className="act disabled:opacity-50">
                {{ ACTIVE: "Riattiva", SUSPENDED: "Sospendi", CANCELLED: "Cessa" }[st]}
              </button>
            ))}
          </div>
          <ErrorNote message={(setStatus.error as Error | null)?.message} />
        </div>
      )}
    </Modal>
  );
}

function Mini({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl bg-white/5 px-4 py-3">
      <p className="kpi-label">{label}</p>
      <p className="mt-1 text-lg font-black tabular-nums text-white">{value}</p>
    </div>
  );
}

// --- Compensi -----------------------------------------------------------------

function CommissionsView() {
  const [kind, setKind] = useState("");
  const [status, setStatus] = useState("PAYABLE");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const invalidate = useInvalidate();
  const { data, isLoading } = useQuery({
    queryKey: ["affiliate", "admin", "commissions", kind, status],
    queryFn: () => affiliateGet<CommissionRow[]>(`/admin/commissions?${new URLSearchParams({ ...(kind && { kind }), ...(status && { status_filter: status }) })}`),
  });
  const [ok, setOk] = useState<string | null>(null);
  const pay = useMutation({
    mutationFn: () => affiliateSend<{ paid: number }>("/admin/commissions/pay", { commission_ids: [...selected] }),
    onSuccess: (r) => { setOk(`${r.paid} compensi segnati come pagati.`); setSelected(new Set()); invalidate(); },
  });
  const today = new Date().toISOString().slice(0, 10);
  const rows = data ?? [];
  const due = rows.filter((r) => r.status === "PAYABLE" && r.payable_on <= today);
  const total = rows.filter((r) => selected.has(r.id)).reduce((s, r) => s + Number(r.amount), 0);
  const toggle = (id: string) => setSelected((prev) => { const n = new Set(prev); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  return (
    <div className="space-y-5">
      <SectionTitle eyebrow="Compensi" title="BC, BD, BM e rivendite, sempre separati">
        <button type="button" onClick={() => download("commissions")} className="act">Esporta CSV</button>
      </SectionTitle>
      <div className="flex flex-wrap gap-4">
        <div className="subnav">
          {([["", "Tutti"], ["BC", "Carriera"], ["BD", "Vendita diretta"], ["BM", "MamiCash"], ["RESALE", "Rivendite"]] as const).map(([k, l]) => (
            <button key={k} type="button" onClick={() => setKind(k)} className="subnav-pill" data-active={kind === k || undefined}>{l}</button>
          ))}
        </div>
        <div className="subnav">
          {([["PAYABLE", "Da pagare"], ["PAID", "Pagati"], ["CANCELLED", "Annullati"]] as const).map(([k, l]) => (
            <button key={k} type="button" onClick={() => { setStatus(k); setSelected(new Set()); }} className="subnav-pill" data-active={status === k || undefined}>{l}</button>
          ))}
        </div>
      </div>
      <OkNote message={ok} />
      <ErrorNote message={(pay.error as Error | null)?.message} />
      {status === "PAYABLE" && due.length > 0 && (
        <div className="panel flex flex-wrap items-center justify-between gap-3 rounded-3xl p-4">
          <p className="text-sm text-surface-200">{selected.size} selezionati · <strong className="text-white">{eur(total)}</strong></p>
          <div className="flex gap-2">
            <button type="button" onClick={() => setSelected(new Set(due.map((r) => r.id)))} className="act">Seleziona i dovuti ({due.length})</button>
            <button type="button" disabled={selected.size === 0 || pay.isPending} onClick={() => pay.mutate()} className="act act-primary disabled:opacity-50">Segna come pagati</button>
          </div>
        </div>
      )}
      {isLoading ? <Loading /> : rows.length === 0 ? <Empty>Nessun compenso in questo elenco.</Empty> : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead><tr>
              {status === "PAYABLE" && <th className="px-4 py-3"><span className="sr-only">Seleziona</span></th>}
              <th className="px-4 py-3">Beneficiario</th><th className="px-4 py-3">Bonus</th><th className="px-4 py-3">Origine</th>
              <th className="px-4 py-3 text-right">Base</th><th className="px-4 py-3 text-right">Importo</th><th className="px-4 py-3">Pagabile</th><th className="px-4 py-3">Stato</th>
            </tr></thead>
            <tbody>
              {rows.map((r) => {
                const isDue = r.status === "PAYABLE" && r.payable_on <= today;
                return (
                  <tr key={r.id}>
                    {status === "PAYABLE" && (
                      <td className="px-4 py-3"><input type="checkbox" disabled={!isDue} checked={selected.has(r.id)} onChange={() => toggle(r.id)} aria-label="Seleziona" /></td>
                    )}
                    <td className="px-4 py-3">{r.beneficiary?.name}<p className="text-xs text-surface-400">{r.beneficiary?.code}</p></td>
                    <td className="px-4 py-3">{COMMISSION_LABELS[r.kind]}<p className="text-xs text-surface-400">{r.kind === "BC" ? `Livello ${r.career_level} · ${periodLabel(r.period)}` : r.kind === "RESALE" ? "450 € per licenza" : `${r.position}ª posizione · ${Number(r.rate)}%`}</p></td>
                    <td className="px-4 py-3 text-xs">{r.operation ? `${OPERATION_LABELS[r.operation.kind] ?? r.operation.kind}${r.operation.product_code ? ` ${r.operation.product_code}` : ""} · ${r.operation.seller?.name ?? ""}` : "Chiusura mensile"}</td>
                    <td className="px-4 py-3 text-right tabular-nums">{r.kind === "BC" ? bc(Number(r.base_amount)) : eur(r.base_amount)}</td>
                    <td className="px-4 py-3 text-right font-bold tabular-nums">{eur(r.amount)}</td>
                    <td className="px-4 py-3">{shortDate(r.payable_on)}</td>
                    <td className="px-4 py-3"><Chip tone={COMMISSION_STATUS[r.status]?.tone ?? "muted"}>{COMMISSION_STATUS[r.status]?.label ?? r.status}</Chip></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// --- Chiusure mensili ---------------------------------------------------------

function PeriodsView() {
  const invalidate = useInvalidate();
  const { data, isLoading } = useQuery({ queryKey: ["affiliate", "admin", "periods"], queryFn: () => affiliateGet<Periods>("/admin/periods") });
  const [selected, setSelected] = useState<string | null>(null);
  const shown = selected ?? data?.current_period ?? null;
  const { data: results, isLoading: loadingResults } = useQuery({
    queryKey: ["affiliate", "admin", "period-results", shown],
    queryFn: () => affiliateGet<PeriodResult[]>(`/admin/periods/${shown}/results`),
    enabled: !!shown,
  });
  const close = useMutation({
    mutationFn: (period: string) => affiliateSend(`/admin/periods/${period}/close`),
    onSuccess: () => invalidate(),
  });
  if (isLoading || !data) return <Loading />;
  const closable = data.open_periods.filter((p) => p < data.current_period);
  const periods = Array.from(new Set([data.current_period, ...data.open_periods, ...data.closed.map((c) => c.period)])).sort().reverse();
  const closedInfo = data.closed.find((c) => c.period === shown);
  return (
    <div className="space-y-5">
      <SectionTitle eyebrow="Chiusure mensili" title="Bonus Carriera mese per mese" />
      <p className="text-xs text-surface-300">
        Ogni mese il conteggio dei BC riparte da zero. La chiusura congela volumi e livelli e genera i Bonus Carriera, pagabili il 15 del mese successivo. Si esegue da sola il primo del mese; qui puoi farla a mano.
      </p>
      <ErrorNote message={(close.error as Error | null)?.message} />
      {closable.length > 0 && (
        <div className="panel flex flex-wrap items-center justify-between gap-3 rounded-3xl p-4">
          <p className="text-sm text-surface-200">Mesi terminati ancora aperti: {closable.map(periodLabel).join(", ")}</p>
          {closable.map((p) => (
            <button key={p} type="button" disabled={close.isPending} onClick={() => close.mutate(p)} className="act act-primary disabled:opacity-50">Chiudi {periodLabel(p)}</button>
          ))}
        </div>
      )}
      <div className="subnav">
        {periods.map((p) => (
          <button key={p} type="button" onClick={() => setSelected(p)} className="subnav-pill capitalize" data-active={shown === p || undefined}>
            {periodLabel(p)}{data.closed.some((c) => c.period === p) ? " ✓" : p === data.current_period ? " · in corso" : ""}
          </button>
        ))}
      </div>
      {closedInfo && (
        <div className="grid gap-4 sm:grid-cols-4">
          <KpiTile label="Chiuso il" value={shortDate(closedInfo.closed_at)} hint={closedInfo.automatic ? "Automaticamente" : "A mano"} />
          <KpiTile label="Con punti" value={num(closedInfo.affiliates_count)} />
          <KpiTile label="Qualificati" value={num(closedInfo.qualified_count)} />
          <KpiTile label="Bonus Carriera" value={eur(closedInfo.total_bonus)} hint={`${num(closedInfo.total_points)} BC generati`} />
        </div>
      )}
      {loadingResults ? <Loading /> : (results ?? []).length === 0 ? <Empty>Nessun punto generato in questo mese.</Empty> : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead><tr><th className="px-4 py-3">Digital Ambassador</th><th className="px-4 py-3 text-right">BCP</th><th className="px-4 py-3">Gambe principali</th><th className="px-4 py-3 text-right">BCT</th><th className="px-4 py-3">Livello</th><th className="px-4 py-3 text-right">Bonus</th></tr></thead>
            <tbody>
              {(results ?? []).map((r, i) => (
                <tr key={r.agent?.id ?? i}>
                  <td className="px-4 py-3 font-semibold text-white">{r.agent?.name}</td>
                  <td className="px-4 py-3 text-right tabular-nums">{num(r.bcp)}</td>
                  <td className="px-4 py-3 text-xs text-surface-300">{r.legs.slice(0, 4).map((l) => `${l.name ?? "—"} ${num(l.points)}`).join(" · ") || "—"}</td>
                  <td className="px-4 py-3 text-right tabular-nums">{num(r.bct)}</td>
                  <td className="px-4 py-3">{r.level ? `Livello ${r.level}` : "—"}</td>
                  <td className="px-4 py-3 text-right tabular-nums">{eur(r.bonus)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// --- Licenze e imprese --------------------------------------------------------

function RegistryView() {
  const [tab, setTab] = useState<"licenses" | "margins" | "clients">("licenses");
  const { data: clients } = useQuery({ queryKey: ["affiliate", "admin", "clients"], queryFn: () => affiliateGet<ClientRow[]>("/admin/clients") });
  return (
    <div className="space-y-5">
      <SectionTitle eyebrow="Registri" title="Licenze e imprese clienti">
        <button type="button" onClick={() => download("licenses")} className="act">Esporta licenze</button>
      </SectionTitle>
      <div className="subnav">
        <button type="button" onClick={() => setTab("licenses")} className="subnav-pill" data-active={tab === "licenses" || undefined}>Registro licenze</button>
        <button type="button" onClick={() => setTab("margins")} className="subnav-pill" data-active={tab === "margins" || undefined}>Margine per Digital Ambassador</button>
        <button type="button" onClick={() => setTab("clients")} className="subnav-pill" data-active={tab === "clients" || undefined}>Imprese <span className="ml-1 opacity-70">{clients?.length ?? 0}</span></button>
      </div>
      {tab === "licenses" ? <AdminLicenseRegister /> : tab === "margins" ? <AdminLicenseMargins /> : (
        (clients ?? []).length === 0 ? <Empty>Nessuna impresa cliente.</Empty> : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead><tr><th className="px-4 py-3">Impresa</th><th className="px-4 py-3">Seguita da</th><th className="px-4 py-3">Email</th><th className="px-4 py-3 text-right">MamiCash</th></tr></thead>
              <tbody>
                {(clients ?? []).map((c) => (
                  <tr key={c.id}>
                    <td className="px-4 py-3 font-semibold text-white">{c.company_name}{c.vat_number && <p className="text-xs font-normal text-surface-400">P.IVA {c.vat_number}</p>}</td>
                    <td className="px-4 py-3">{c.agent?.name ?? "—"}</td>
                    <td className="px-4 py-3">{c.email ?? "—"}</td>
                    <td className="px-4 py-3 text-right tabular-nums">{mamicash(c.mamicash_balance)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      )}
    </div>
  );
}

// --- Piano compensi -----------------------------------------------------------

function PlanView() {
  const { data: versions, isLoading } = useQuery({ queryKey: ["affiliate", "admin", "plan"], queryFn: () => affiliateGet<PlanVersion[]>("/admin/plan") });
  const [editing, setEditing] = useState(false);
  if (isLoading || !versions) return <Loading />;
  const current = versions.find((v) => v.is_current) ?? versions[0];
  if (!current) return <Empty>Nessun piano configurato.</Empty>;
  const cfg = current.config;
  return (
    <div className="space-y-6">
      <SectionTitle eyebrow={`Piano compensi · versione ${current.label} dal ${shortDate(current.valid_from)}`} title="Le regole in vigore">
        <button type="button" onClick={() => setEditing(true)} className="act">Nuova versione</button>
      </SectionTitle>
      {current.notes && <p className="text-xs text-surface-300">{current.notes}</p>}
      <div className="grid gap-6 lg:grid-cols-2">
        <div className="panel rounded-3xl p-5">
          <p className="kpi-label mb-3">Bonus Carriera · 11 livelli, almeno {cfg.required_legs} gambe</p>
          <table className="w-full text-left text-sm">
            <thead><tr><th className="px-3 py-2">Livello</th><th className="px-3 py-2 text-right">BC totali</th><th className="px-3 py-2 text-right">Minimo per gamba</th><th className="px-3 py-2 text-right">Bonus</th></tr></thead>
            <tbody>
              {cfg.career_levels.map((l) => (
                <tr key={l.level}><td className="px-3 py-2">{l.level}</td><td className="px-3 py-2 text-right tabular-nums">{num(l.total_bc)}</td><td className="px-3 py-2 text-right tabular-nums">{num(l.leg_min_bc)}</td><td className="px-3 py-2 text-right tabular-nums">{eur(l.bonus)}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="panel rounded-3xl p-5">
          <p className="kpi-label mb-3">Aliquote per posizione · BD sul prezzo del Pack, BM sulla ricarica</p>
          <table className="w-full text-left text-sm">
            <thead><tr><th className="px-3 py-2">Posizione</th><th className="px-3 py-2 text-right">BD</th><th className="px-3 py-2 text-right">BM</th></tr></thead>
            <tbody>
              {cfg.bd_rates.map((r, i) => (
                <tr key={i}><td className="px-3 py-2">{i + 1}{i === 0 ? " · venditore diretto" : ""}</td><td className="px-3 py-2 text-right tabular-nums">{Number(r).toLocaleString("it-IT")}%</td><td className="px-3 py-2 text-right tabular-nums">{Number(cfg.bm_rates[i]).toLocaleString("it-IT")}%</td></tr>
              ))}
              <tr><td className="px-3 py-2 font-bold">Totale</td><td className="px-3 py-2 text-right font-bold">{cfg.bd_rates.reduce((s, r) => s + Number(r), 0)}%</td><td className="px-3 py-2 text-right font-bold">{cfg.bm_rates.reduce((s, r) => s + Number(r), 0)}%</td></tr>
            </tbody>
          </table>
        </div>
        <div className="panel rounded-3xl p-5">
          <p className="kpi-label mb-3">Prodotti che generano BC</p>
          <table className="w-full text-left text-sm">
            <thead><tr><th className="px-3 py-2">Prodotto</th><th className="px-3 py-2 text-right">Prezzo</th><th className="px-3 py-2 text-right">BC</th></tr></thead>
            <tbody>
              <tr><td className="px-3 py-2">{cfg.subscription.name} (al mese)</td><td className="px-3 py-2 text-right">{eur(cfg.subscription.price)}</td><td className="px-3 py-2 text-right">{num(cfg.subscription.bc)}</td></tr>
              {cfg.license_products.map((p) => <tr key={p.code}><td className="px-3 py-2">{p.name} · {p.licenses} licenze</td><td className="px-3 py-2 text-right">{eur(p.price)}</td><td className="px-3 py-2 text-right">{num(p.bc)}</td></tr>)}
              {cfg.event_ticket_products.map((p) => <tr key={p.code}><td className="px-3 py-2">{p.name}</td><td className="px-3 py-2 text-right">{eur(p.price)}</td><td className="px-3 py-2 text-right">{num(p.bc)}</td></tr>)}
            </tbody>
          </table>
        </div>
        <div className="panel space-y-3 rounded-3xl p-5 text-sm">
          <p className="kpi-label">Pack e rivendite</p>
          <p className="text-surface-200">Pack: {cfg.packs.map((p) => `${p.name} ${eur(p.price)}`).join(" · ")}</p>
          <p className="text-surface-200">Rivendita licenza a {eur(cfg.license_resale.price)}: {eur(cfg.license_resale.seller_amount)} all&apos;affiliato, {eur(cfg.license_resale.company_amount)} alla società per {mamicash(cfg.license_resale.client_mamicash)} all&apos;impresa cliente. Nessun BC.</p>
          <p className="text-surface-200">Promo: una licenza in omaggio ogni {cfg.promotions.gift_license_every_paid_months} mensilità pagate; evento di Roma con {num(cfg.promotions.rome_launch_event?.target_bc)} BC a {periodLabel(cfg.promotions.rome_launch_event?.period)}.</p>
          <p className="text-surface-200">Bonus Carriera pagato il {cfg.career_bonus_pay_day} del mese successivo; BD, BM e rivendite subito.</p>
        </div>
      </div>
      {versions.length > 1 && (
        <div className="panel rounded-3xl p-5">
          <p className="kpi-label mb-3">Versioni</p>
          <ul className="space-y-1 text-sm">
            {versions.map((v) => <li key={v.id} className="text-surface-200">{v.label} · dal {shortDate(v.valid_from)} {v.is_current && <Chip tone="ok">In vigore</Chip>}</li>)}
          </ul>
        </div>
      )}
      {editing && <NewPlanVersionModal base={cfg} onClose={() => setEditing(false)} />}
    </div>
  );
}

function NewPlanVersionModal({ base, onClose }: { base: PlanConfig; onClose: () => void }) {
  const invalidate = useInvalidate();
  const [label, setLabel] = useState("");
  const [validFrom, setValidFrom] = useState("");
  const [json, setJson] = useState(JSON.stringify(base, null, 2));
  const [parseError, setParseError] = useState<string | null>(null);
  const save = useMutation({
    mutationFn: (config: unknown) => affiliateSend("/admin/plan", { label, valid_from: new Date(validFrom).toISOString(), config, notes: null }),
    onSuccess: () => { invalidate(); onClose(); },
  });
  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    try { setParseError(null); save.mutate(JSON.parse(json)); } catch { setParseError("Il testo del piano non è un JSON valido."); }
  };
  return (
    <Modal title="Nuova versione del piano" onClose={onClose} wide>
      <form className="space-y-3" onSubmit={submit}>
        <p className="text-xs text-surface-300">Vale solo da una data futura: le operazioni già calcolate restano con le regole della loro versione. Il sistema rifiuta un piano senza 11 livelli o con aliquote BM diverse dal 4% e BD diverse dal 42%.</p>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Nome versione"><input required className="field w-full rounded-xl px-3 py-2.5 text-sm" value={label} onChange={(e) => setLabel(e.target.value)} placeholder="es. 1.2" /></Field>
          <Field label="In vigore dal"><input required type="datetime-local" className="field w-full rounded-xl px-3 py-2.5 text-sm" value={validFrom} onChange={(e) => setValidFrom(e.target.value)} /></Field>
        </div>
        <Field label="Configurazione">
          <textarea rows={16} spellCheck={false} className="field w-full rounded-xl px-3 py-2.5 font-mono text-xs" value={json} onChange={(e) => setJson(e.target.value)} />
        </Field>
        <ErrorNote message={parseError ?? (save.error as Error | null)?.message} />
        <button type="submit" disabled={save.isPending} className="act act-primary w-full justify-center disabled:opacity-50">Salva la nuova versione</button>
      </form>
    </Modal>
  );
}
