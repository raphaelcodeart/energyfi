"use client";

import { useEffect, useState } from "react";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Chip, KpiTile } from "@/components/ui/data-cells";
import { AgentPicker } from "@/components/agent-picker";
import { Pagination, serverPagination } from "@/components/pagination";
import { Empty, ErrorNote, Field, Modal, OkNote, SectionTitle } from "@/components/affiliate/shared";
import {
  affiliateGet,
  affiliateSend,
  eur,
  LICENSE_STATUS,
  mamicash,
  num,
  productName,
  shortDate,
  type AgentMarginRow,
  type AgentMargins,
  type Catalog,
  type ClientRow,
  type LicenseRegisterRow,
  type LicensesPage,
} from "@/lib/affiliate";

/*
 * Licence register (piano compensi: licences, resale at 500 €, commercial
 * margin). Mamify sells the packages; which company each licence is given to
 * is remembered only here. Lists are paged and searched on the server.
 *
 *  - AmbassadorLicenses: «Le mie licenze» of a Digital Ambassador.
 *  - AdminLicenseRegister / AdminLicenseMargins: the office registers.
 */

type Scope = "me" | "admin";

function useDebounced(value: string, ms = 300) {
  const [v, setV] = useState(value);
  useEffect(() => { const t = setTimeout(() => setV(value.trim()), ms); return () => clearTimeout(t); }, [value, ms]);
  return v;
}

function SkeletonRows({ cols, rows = 5 }: { cols: number; rows?: number }) {
  return <>{Array.from({ length: rows }, (_, i) => (
    <tr key={i}><td colSpan={cols} className="px-4 py-3"><div className="h-8 animate-pulse rounded-xl bg-white/5" /></td></tr>
  ))}</>;
}

function useCatalog() {
  return useQuery({ queryKey: ["affiliate", "catalog"], queryFn: () => affiliateGet<Catalog>("/catalog") });
}

function useInvalidate() {
  const qc = useQueryClient();
  return () => void qc.invalidateQueries({ queryKey: ["affiliate"] });
}

function originLabel(row: LicenseRegisterRow, catalog: Catalog | undefined): string {
  if (row.origin === "GIFT") return "Omaggio (6 mensilità)";
  const code = row.purchase.product_code;
  if (!code) return "Acquisto";
  return code === "LICENSE_1" ? "Licenza singola" : `Pacchetto ${productName(catalog?.config, code)}`;
}

const STATUS_TABS: [string, string][] = [
  ["ALL", "Tutte"], ["AVAILABLE", "Da assegnare"], ["RESERVED", "Assegnate · da pagare"], ["RESOLD", "Rivendute"], ["VOID", "Annullate"],
];

// --- Register (shared by the two areas) ----------------------------------------

function useRegister(scope: Scope, agentId?: string) {
  const [status, setStatusRaw] = useState("ALL");
  const [search, setSearchRaw] = useState("");
  const q = useDebounced(search);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const query = useQuery({
    queryKey: ["affiliate", scope, "licenses-page", { page, pageSize, status, q, agentId }],
    queryFn: () => {
      const p = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
      if (status !== "ALL") p.set("status_filter", status);
      if (q) p.set("search", q);
      if (agentId) p.set("agent_id", agentId);
      return affiliateGet<LicensesPage>(`/${scope}/licenses/page?${p}`);
    },
    placeholderData: keepPreviousData,
  });
  return {
    ...query, status, q, search,
    setStatus: (v: string) => { setStatusRaw(v); setPage(1); },
    setSearch: (v: string) => { setSearchRaw(v); setPage(1); },
    pagination: serverPagination(query.data?.total ?? 0, page, pageSize, setPage, setPageSize),
  };
}

function RegisterTable({ scope, reg, onAssign, showOwner }: {
  scope: Scope;
  reg: ReturnType<typeof useRegister>;
  onAssign: (row: LicenseRegisterRow) => void;
  showOwner: boolean;
}) {
  const { data: catalog } = useCatalog();
  const invalidate = useInvalidate();
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);
  const act = useMutation({
    mutationFn: ({ opId, action }: { opId: string; action: "cancel" | "confirm" }) =>
      affiliateSend(`/${scope}/operations/${opId}/${action}`, scope === "admin" ? { reason: action === "cancel" ? "Assegnazione ritirata" : null } : undefined),
    onSuccess: (_, v) => {
      setError(null);
      setOk(v.action === "confirm" ? "Pagamento registrato: la licenza è rivenduta e i 450 € sono tra i compensi da pagare." : "Assegnazione ritirata: la licenza è di nuovo libera.");
      invalidate();
    },
    onError: (e: Error) => { setOk(null); setError(e.message); },
  });
  const counts = reg.data?.counts;
  const all = counts ? counts.AVAILABLE + counts.RESERVED + counts.RESOLD + counts.VOID : 0;
  const cols = showOwner ? 6 : 5;
  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <input type="search" value={reg.search} onChange={(e) => reg.setSearch(e.target.value)}
          placeholder={showOwner ? "Cerca licenza, impresa, P.IVA o Digital Ambassador" : "Cerca licenza, impresa o P.IVA"}
          aria-label="Cerca nel registro licenze" className="field w-full rounded-xl px-3 py-2 text-sm lg:w-96" />
        <div className="subnav flex-wrap">
          {STATUS_TABS.map(([k, l]) => {
            const n = k === "ALL" ? all : counts?.[k as keyof typeof counts] ?? 0;
            if (k === "VOID" && !n) return null;
            return (
              <button key={k} type="button" onClick={() => reg.setStatus(k)} className="subnav-pill" data-active={reg.status === k || undefined}>
                {l}{counts ? ` · ${num(n)}` : ""}
              </button>
            );
          })}
        </div>
      </div>
      <ErrorNote message={error} />
      <OkNote message={ok} />
      {reg.error ? <ErrorNote message={(reg.error as Error).message} /> : (
        <div className="panel rounded-3xl p-2 md:p-4">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead><tr>
                <th className="px-4 py-3">Licenza</th>
                {showOwner && <th className="px-4 py-3">Digital Ambassador</th>}
                <th className="px-4 py-3">Stato</th>
                <th className="px-4 py-3">Impresa</th>
                <th className="px-4 py-3 text-right">Costo · margine</th>
                <th className="px-4 py-3"><span className="sr-only">Azioni</span></th>
              </tr></thead>
              <tbody className={reg.isFetching && reg.data ? "opacity-60 transition-opacity" : ""}>
                {!reg.data ? <SkeletonRows cols={cols} /> : reg.data.items.length === 0 ? (
                  <tr><td colSpan={cols} className="px-4 py-10"><Empty>
                    {reg.q || reg.status !== "ALL" ? "Nessuna licenza con questi filtri." : "Nessuna licenza. Le licenze arrivano dagli acquisti di licenze singole o dei pacchetti SMALL, MEDIUM e LARGE."}
                  </Empty></td></tr>
                ) : reg.data.items.map((l) => (
                  <tr key={l.id} className="align-top">
                    <td className="px-4 py-3">
                      <p className="font-mono text-xs font-bold text-white">{l.code}</p>
                      <p className="text-xs text-surface-400">{originLabel(l, catalog)} · {shortDate(l.purchase.at)}{l.purchase.via_mamify ? " · Mamify" : ""}</p>
                    </td>
                    {showOwner && (
                      <td className="px-4 py-3">
                        <p className="text-white">{l.owner?.name ?? "—"}</p>
                        <p className="text-xs text-surface-400">{l.owner?.code}</p>
                      </td>
                    )}
                    <td className="px-4 py-3"><Chip tone={LICENSE_STATUS[l.status]?.tone ?? "muted"}>{LICENSE_STATUS[l.status]?.label ?? l.status}</Chip></td>
                    <td className="px-4 py-3">
                      {l.client_detail ? (
                        <>
                          <p className="text-white">{l.client_detail.name}</p>
                          <p className="text-xs text-surface-400">
                            {[l.client_detail.vat_number, l.client_detail.email].filter(Boolean).join(" · ") || "—"}
                          </p>
                          {l.assignment && (
                            <p className="text-xs text-surface-400">
                              Assegnata il {shortDate(l.assignment.assigned_at)}
                              {l.assignment.paid_at ? ` · pagata il ${shortDate(l.assignment.paid_at)}${l.assignment.via_mamify ? " su Mamify" : ""}` : " · in attesa dei 500 €"}
                            </p>
                          )}
                          {l.status === "RESOLD" && (
                            <p className="text-xs text-surface-400">
                              {mamicash(catalog?.config.license_resale.client_mamicash ?? 500)} all&apos;impresa{l.assignment?.via_mamify ? " (accreditati da Mamify con l'ordine)" : " (da accreditare su Mamify)"}
                            </p>
                          )}
                          {l.assignment?.note && <p className="text-xs italic text-surface-300">{l.assignment.note}</p>}
                        </>
                      ) : <span className="text-surface-400">—</span>}
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums">
                      <p>{eur(l.unit_cost)}</p>
                      {l.margin != null && <p className="text-xs font-bold text-success-300">+{eur(l.margin)}</p>}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <div className="flex flex-wrap justify-end gap-2">
                        {l.status === "AVAILABLE" && (
                          <button type="button" className="act act-primary" onClick={() => onAssign(l)}>Assegna a un&apos;impresa</button>
                        )}
                        {l.status === "RESERVED" && l.assignment?.status === "PENDING" && scope === "admin" && (
                          <button type="button" className="act act-primary" disabled={act.isPending}
                            onClick={() => act.mutate({ opId: l.assignment!.operation_id, action: "confirm" })}>Pagata</button>
                        )}
                        {l.status === "RESERVED" && l.assignment?.status === "PENDING" && (
                          <button type="button" className="act" disabled={act.isPending}
                            onClick={() => { if (window.confirm(`Ritirare l'assegnazione di ${l.code} a ${l.client_detail?.name ?? "questa impresa"}?`)) act.mutate({ opId: l.assignment!.operation_id, action: "cancel" }); }}>
                            Ritira
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="px-2 pt-3"><Pagination {...reg.pagination} label="licenze" /></div>
        </div>
      )}
    </div>
  );
}

// --- Assignment ------------------------------------------------------------------

function AssignModal({ scope, license, onClose }: { scope: Scope; license: LicenseRegisterRow; onClose: () => void }) {
  const invalidate = useInvalidate();
  const ownerId = license.owner?.id;
  const { data: clients } = useQuery({
    queryKey: ["affiliate", scope, "clients", scope === "admin" ? ownerId : "me"],
    queryFn: () => affiliateGet<ClientRow[]>(scope === "admin" ? `/admin/clients?agent_id=${ownerId}` : "/me/clients"),
  });
  const list = clients ?? [];
  const [mode, setMode] = useState<"existing" | "new">("existing");
  const [clientId, setClientId] = useState("");
  const [form, setForm] = useState({ company_name: "", vat_number: "", contact_name: "", email: "", phone: "" });
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  // No company yet: only a new one can be chosen. No choice made: the first.
  const effectiveMode = clients && list.length === 0 ? "new" : mode;
  const chosenId = clientId || list[0]?.id || "";
  const assign = useMutation({
    mutationFn: () => {
      const trimmed = Object.fromEntries(Object.entries(form).map(([k, v]) => [k, v.trim() || null]));
      return affiliateSend(`/${scope}/licenses/assign`, {
        license_id: license.id,
        client_id: effectiveMode === "existing" ? chosenId : null,
        new_client: effectiveMode === "new" ? trimmed : null,
        note: note.trim() || null,
        payment_method: "BANK_TRANSFER",
      });
    },
    onSuccess: () => { invalidate(); onClose(); },
    onError: (e: Error) => setError(e.message),
  });
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, [k]: e.target.value });
  const ready = effectiveMode === "existing" ? !!chosenId : form.company_name.trim().length >= 2;
  return (
    <Modal title={`Assegna la licenza ${license.code}`} onClose={onClose}>
      <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); if (ready) assign.mutate(); }}>
        {scope === "admin" && license.owner && (
          <p className="text-xs text-surface-300">Per conto di <b className="text-white">{license.owner.name}</b>, titolare della licenza.</p>
        )}
        <div className="subnav">
          <button type="button" className="subnav-pill" data-active={effectiveMode === "existing" || undefined} disabled={list.length === 0}
            onClick={() => setMode("existing")}>Impresa già registrata{list.length ? ` · ${list.length}` : ""}</button>
          <button type="button" className="subnav-pill" data-active={effectiveMode === "new" || undefined} onClick={() => setMode("new")}>Nuova impresa</button>
        </div>
        {effectiveMode === "existing" ? (
          <Field label="Impresa cliente">
            <select className="field w-full rounded-xl px-3 py-2.5 text-sm" value={chosenId} onChange={(e) => setClientId(e.target.value)}>
              {list.map((c) => <option key={c.id} value={c.id}>{c.company_name}{c.vat_number ? ` · ${c.vat_number}` : ""}</option>)}
            </select>
          </Field>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="sm:col-span-2"><Field label="Ragione sociale"><input required minLength={2} className="field w-full rounded-xl px-3 py-2.5 text-sm" value={form.company_name} onChange={set("company_name")} /></Field></div>
            <Field label="Partita IVA"><input className="field w-full rounded-xl px-3 py-2.5 text-sm" value={form.vat_number} onChange={set("vat_number")} /></Field>
            <Field label="Referente"><input className="field w-full rounded-xl px-3 py-2.5 text-sm" value={form.contact_name} onChange={set("contact_name")} /></Field>
            <Field label="Email" hint="La stessa con cui l'impresa è su Mamify: così il suo ordine si collega da solo.">
              <input type="email" className="field w-full rounded-xl px-3 py-2.5 text-sm" value={form.email} onChange={set("email")} />
            </Field>
            <Field label="Telefono"><input className="field w-full rounded-xl px-3 py-2.5 text-sm" value={form.phone} onChange={set("phone")} /></Field>
          </div>
        )}
        <Field label="Nota (facoltativa)">
          <input maxLength={1000} className="field w-full rounded-xl px-3 py-2.5 text-sm" value={note} onChange={(e) => setNote(e.target.value)} placeholder="Es. consegnata in negozio, attivazione il 20/11" />
        </Field>
        <p className="text-xs text-surface-300">
          La licenza resta assegnata a questa impresa finché non arriva il pagamento di 500 €: allora risulta rivenduta, al Digital Ambassador spettano 450 € e l&apos;impresa riceve 500 MamiCash su Mamify. La rivendita non genera BC.
        </p>
        <ErrorNote message={error} />
        <button type="submit" disabled={assign.isPending || !ready} className="act act-primary w-full justify-center disabled:opacity-50">Assegna la licenza</button>
      </form>
    </Modal>
  );
}

// --- Margin ------------------------------------------------------------------------

function MarginTiles({ m }: { m: AgentMargins | undefined }) {
  const t = m?.totals;
  return (
    <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
      <KpiTile label="Licenze da assegnare" value={t ? num(t.available) : "—"} hint={t ? `${num(t.reserved)} assegnate in attesa di pagamento` : ""} />
      <KpiTile label="Licenze rivendute" value={t ? num(t.resold) : "—"} hint={t ? `su ${num(t.licenses)} · incassati ${eur(t.collected)}` : ""} />
      <KpiTile label="Margine realizzato" value={t ? eur(t.margin) : "—"} hint="Quanto ti spetta dalle rivendite meno il costo di quelle licenze" />
      <KpiTile label="Margine possibile" value={t ? eur(t.potential_margin) : "—"} hint={m ? `Se rivendi tutte le licenze a ${eur(m.resale_price)} (${eur(m.seller_amount)} a te)` : ""} />
    </div>
  );
}

function MarginGroups({ m }: { m: AgentMargins | undefined }) {
  const { data: catalog } = useCatalog();
  if (!m || m.groups.length === 0) return null;
  return (
    <div className="panel rounded-3xl p-2 md:p-4">
      <p className="kpi-label px-2 pb-2">Margine per acquisto</p>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead><tr>
            <th className="px-4 py-3">Acquisto</th><th className="px-4 py-3 text-right">Licenze</th>
            <th className="px-4 py-3 text-right">Costo</th><th className="px-4 py-3 text-right">Incassato</th>
            <th className="px-4 py-3 text-right">Margine</th><th className="px-4 py-3 text-right">Se rivendi tutto</th>
          </tr></thead>
          <tbody>
            {m.groups.map((g) => (
              <tr key={g.purchase_operation_id}>
                <td className="px-4 py-3">
                  <p className="text-white">{g.origin === "GIFT" ? "Licenza in omaggio" : g.product_code === "LICENSE_1" ? "Licenza singola" : `Pacchetto ${productName(catalog?.config, g.product_code)}`}</p>
                  <p className="text-xs text-surface-400">{shortDate(g.purchased_at)}{g.via_mamify ? " · Mamify" : ""}</p>
                </td>
                <td className="px-4 py-3 text-right tabular-nums">
                  {num(g.resold)}/{num(g.licenses)} rivendute
                  <p className="text-xs text-surface-400">{num(g.available)} libere{g.reserved ? ` · ${num(g.reserved)} assegnate` : ""}</p>
                </td>
                <td className="px-4 py-3 text-right tabular-nums">{eur(g.cost)}</td>
                <td className="px-4 py-3 text-right tabular-nums">{eur(g.collected)}</td>
                <td className="px-4 py-3 text-right font-bold tabular-nums">{eur(g.margin)}</td>
                <td className="px-4 py-3 text-right tabular-nums text-surface-200">{eur(g.potential_margin)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="px-2 pt-2 text-[11px] text-surface-400">Margini prima di altri costi e imposte. Il costo di ogni licenza è il prezzo del pacchetto diviso per le sue licenze; quelle in omaggio costano zero.</p>
    </div>
  );
}

// --- Digital Ambassador ---------------------------------------------------------------

export function AmbassadorLicenses() {
  const { data: margins } = useQuery({ queryKey: ["affiliate", "me", "license-margins"], queryFn: () => affiliateGet<AgentMargins>("/me/licenses/margins") });
  const reg = useRegister("me");
  const [assigning, setAssigning] = useState<LicenseRegisterRow | null>(null);
  return (
    <div className="space-y-5">
      <SectionTitle eyebrow="Le mie licenze" title="Licenze e margine commerciale" />
      <p className="text-xs text-surface-300">
        Le licenze che compri su Mamify (singole o pacchetti SMALL, MEDIUM, LARGE) arrivano qui. Quando ne dai una a un&apos;impresa, assegnala qui: Mamify non sa a chi va, lo ricordiamo noi.
      </p>
      <MarginTiles m={margins} />
      <MarginGroups m={margins} />
      <RegisterTable scope="me" reg={reg} onAssign={setAssigning} showOwner={false} />
      {assigning && <AssignModal scope="me" license={assigning} onClose={() => setAssigning(null)} />}
    </div>
  );
}

// --- Office ------------------------------------------------------------------------------

export function AdminLicenseRegister() {
  const [agentId, setAgentId] = useState("");
  const { data: margins } = useQuery({
    queryKey: ["affiliate", "admin", "license-margins", agentId],
    queryFn: () => affiliateGet<AgentMargins>(`/admin/licenses/margins/${agentId}`),
    enabled: !!agentId,
  });
  const [assigning, setAssigning] = useState<LicenseRegisterRow | null>(null);
  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
        <span className="kpi-label">Digital Ambassador</span>
        <AgentPicker value={agentId} onChange={(id) => setAgentId(id)} emptyLabel="Tutti" placeholder="Tutti · cerca per nome o codice…" className="sm:w-96" ariaLabel="Filtra per Digital Ambassador" />
      </div>
      {agentId && <><MarginTiles m={margins} /><MarginGroups m={margins} /></>}
      {/* Keyed: another ambassador starts again from page 1. */}
      <AdminRegisterBody key={agentId} agentId={agentId} onAssign={setAssigning} />
      {assigning && <AssignModal scope="admin" license={assigning} onClose={() => setAssigning(null)} />}
    </div>
  );
}

function AdminRegisterBody({ agentId, onAssign }: { agentId: string; onAssign: (row: LicenseRegisterRow) => void }) {
  const reg = useRegister("admin", agentId || undefined);
  return <RegisterTable scope="admin" reg={reg} onAssign={onAssign} showOwner={!agentId} />;
}

export function AdminLicenseMargins({ onOpen }: { onOpen?: (agentId: string) => void }) {
  const [search, setSearchRaw] = useState("");
  const q = useDebounced(search);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const { data, error, isFetching } = useQuery({
    queryKey: ["affiliate", "admin", "license-margins-page", { page, pageSize, q }],
    queryFn: () => {
      const p = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
      if (q) p.set("search", q);
      return affiliateGet<{ total: number; items: AgentMarginRow[] }>(`/admin/licenses/margins?${p}`);
    },
    placeholderData: keepPreviousData,
  });
  const pagination = serverPagination(data?.total ?? 0, page, pageSize, setPage, setPageSize);
  return (
    <div className="space-y-4">
      <input type="search" value={search} onChange={(e) => { setSearchRaw(e.target.value); setPage(1); }}
        placeholder="Cerca Digital Ambassador per nome o codice" aria-label="Cerca Digital Ambassador"
        className="field w-full rounded-xl px-3 py-2 text-sm sm:w-96" />
      {error ? <ErrorNote message={(error as Error).message} /> : (
        <div className="panel rounded-3xl p-2 md:p-4">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead><tr>
                <th className="px-4 py-3">Digital Ambassador</th><th className="px-4 py-3 text-right">Licenze</th>
                <th className="px-4 py-3 text-right">Costo</th><th className="px-4 py-3 text-right">Incassato</th>
                <th className="px-4 py-3 text-right">Margine</th><th className="px-4 py-3 text-right">Se rivende tutto</th>
              </tr></thead>
              <tbody className={isFetching && data ? "opacity-60 transition-opacity" : ""}>
                {!data ? <SkeletonRows cols={6} /> : data.items.length === 0 ? (
                  <tr><td colSpan={6} className="px-4 py-10"><Empty>{q ? "Nessun Digital Ambassador con licenze trovato." : "Nessuna licenza emessa finora."}</Empty></td></tr>
                ) : data.items.map((r) => (
                  <tr key={r.agent?.id}>
                    <td className="px-4 py-3">
                      {onOpen && r.agent ? (
                        <button type="button" className="text-left font-semibold text-white hover:underline" onClick={() => onOpen(r.agent!.id)}>{r.agent.name}</button>
                      ) : <p className="font-semibold text-white">{r.agent?.name ?? "—"}</p>}
                      <p className="text-xs text-surface-400">{r.agent?.code}</p>
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums">
                      {num(r.resold)}/{num(r.licenses)} rivendute
                      <p className="text-xs text-surface-400">{num(r.available)} libere{r.reserved ? ` · ${num(r.reserved)} assegnate` : ""}</p>
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums">{eur(r.cost)}</td>
                    <td className="px-4 py-3 text-right tabular-nums">{eur(r.collected)}</td>
                    <td className="px-4 py-3 text-right font-bold tabular-nums">{eur(r.margin)}</td>
                    <td className="px-4 py-3 text-right tabular-nums text-surface-200">{eur(r.potential_margin)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="px-2 pt-3"><Pagination {...pagination} label="Digital Ambassador" /></div>
        </div>
      )}
    </div>
  );
}
