"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { friendlyApiError } from "@/lib/api-error";
import { COMMISSION_MODE_LABELS } from "@/lib/commission-labels";
import type { CommercialRoleRead, DelegationRead, ProductCategoryRead } from "@/lib/types";
import { Chip, Figure, Identity, KpiTile, RowActions, Stack } from "@/components/ui/data-cells";
import { AgentPicker } from "@/components/agent-picker";

async function getJson<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(await friendlyApiError(res));
  return res.json();
}

async function send(url: string, method: string, body?: unknown) {
  const res = await fetch(url, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error(await friendlyApiError(res));
  return res.status === 204 ? null : res.json();
}

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString("it-IT", { day: "2-digit", month: "short", year: "numeric" });
}

function EmptyRow({ colSpan, text }: { colSpan: number; text: string }) {
  return (
    <tr>
      <td colSpan={colSpan} className="px-4 py-10">
        <div className="flex flex-col items-center gap-2 text-center">
          <svg viewBox="0 0 24 24" className="h-8 w-8 text-accent-300 float-soft" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
            <circle cx="12" cy="12" r="9" />
            <path d="M8 12h8" strokeLinecap="round" />
          </svg>
          <span className="text-sm font-semibold text-surface-200">{text}</span>
        </div>
      </td>
    </tr>
  );
}

type RoleDraft = Omit<CommercialRoleRead, "id"> & { id?: string };

const EMPTY_ROLE: RoleDraft = {
  code: "", name: "", description: "", commission_mode: "PERCENTAGE", network_depth: null,
  allows_delegation: false, allows_downline: true, can_close_sales: true, is_default: false, is_active: true, sort_order: 100,
};

/**
 * Commercial roles (how money is earned), product categories (for plans) and
 * influencer delegations. Distinct from software ACCESS roles, which decide
 * screens rather than money.
 */
export function AdminCommercialPanel() {
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<"roles" | "categories" | "delegations">("roles");
  const { data: roles } = useQuery({ queryKey: ["commercial", "roles"], queryFn: () => getJson<CommercialRoleRead[]>("/api/proxy/commercial/roles") });
  const { data: categories } = useQuery({ queryKey: ["commercial", "categories"], queryFn: () => getJson<ProductCategoryRead[]>("/api/proxy/commercial/categories") });
  const { data: delegations } = useQuery({ queryKey: ["commercial", "delegations"], queryFn: () => getJson<DelegationRead[]>("/api/proxy/commercial/delegations") });

  const [role, setRole] = useState<RoleDraft | null>(null);
  const [category, setCategory] = useState<{ code: string; name: string; requires_supply_point: boolean }>({ code: "", name: "", requires_supply_point: false });
  const [delegation, setDelegation] = useState({ influencer_agent_id: "", delegate_agent_id: "", reason: "" });
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);

  async function act(fn: () => Promise<unknown>, done: string, keys: string[][]) {
    setError(null);
    setOk(null);
    try {
      await fn();
      await Promise.all(keys.map((queryKey) => queryClient.invalidateQueries({ queryKey })));
      setOk(done);
    } catch (err: any) {
      setError(err.message || "Operazione non riuscita.");
    }
  }

  function saveRole() {
    if (!role) return;
    const { id, code, ...rest } = role;
    act(
      () => (id ? send(`/api/proxy/commercial/roles/${id}`, "PATCH", rest) : send("/api/proxy/commercial/roles", "POST", { code, ...rest })),
      id ? "Ruolo aggiornato: vale per le vendite future." : "Ruolo creato.",
      [["commercial", "roles"]],
    ).then(() => setRole(null));
  }

  const field = "w-full rounded-xl field px-3 py-2 text-sm bg-surface-900 focus:border-brand-500";
  const tabBtn = (key: typeof tab, label: string) => (
    <button key={key} onClick={() => setTab(key)} data-active={tab === key} className="subnav-pill">
      {label}
    </button>
  );
  const activeDelegations = (delegations ?? []).filter((d) => !d.valid_to).length;

  return (
    <div className="space-y-6">
      <div className="panel rounded-3xl p-6 md:p-7 text-xs text-surface-300 leading-relaxed">
        <div className="kpi-label mb-2">Come funziona</div>
        La rete è <strong className="text-white">una sola</strong>: chi ha introdotto chi. Il <strong className="text-white">ruolo commerciale</strong> dice come una persona
        vende e fin dove arriva la sua rete nel calcolo; le quote vere le decidono gli <strong className="text-white">Split Plan</strong>. Cambiare un
        ruolo vale per le vendite future: le vendite passate restano calcolate con il ruolo che la persona aveva quel giorno.
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3 stagger">
        <div style={{ "--i": 0 } as React.CSSProperties}>
          <KpiTile label="Ruoli commerciali" value={(roles ?? []).length} hint={`${(roles ?? []).filter((r) => r.is_active).length} attivi`} active={tab === "roles"} onClick={() => setTab("roles")} />
        </div>
        <div style={{ "--i": 1 } as React.CSSProperties}>
          <KpiTile label="Categorie prodotti" value={(categories ?? []).length} hint={`${(categories ?? []).filter((c) => c.requires_supply_point).length} con punto di fornitura`} active={tab === "categories"} onClick={() => setTab("categories")} />
        </div>
        <div style={{ "--i": 2 } as React.CSSProperties}>
          <KpiTile label="Deleghe influencer" value={activeDelegations} hint={`in corso su ${(delegations ?? []).length}`} active={tab === "delegations"} onClick={() => setTab("delegations")} />
        </div>
      </div>

      <div className="subnav">
        {tabBtn("roles", "Ruoli commerciali")}
        {tabBtn("categories", "Categorie prodotti")}
        {tabBtn("delegations", "Deleghe influencer")}
      </div>

      {error && <div className="p-3 rounded-2xl bg-danger-500/10 border border-danger-500/20 text-danger-400 text-xs pop">{error}</div>}
      {ok && <div className="p-3 rounded-2xl bg-success-500/10 border border-success-500/20 text-success-400 text-xs pop">{ok}</div>}

      {tab === "roles" && (
        <div className="space-y-5">
          <div className="panel rounded-3xl p-4 md:p-6">
            <div className="flex flex-wrap items-end justify-between gap-3 px-2">
              <div>
                <div className="kpi-label">Come si guadagna</div>
                <h3 className="mt-1 text-xl font-black tracking-tight text-white">Ruoli commerciali</h3>
              </div>
              {!role && (
                <button onClick={() => setRole({ ...EMPTY_ROLE })} className="act act-primary !h-10 !px-5">+ Nuovo ruolo</button>
              )}
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-xs text-left">
                <thead>
                  <tr>
                    <th className="px-4 py-3">Ruolo</th>
                    <th className="px-4 py-3">Compenso</th>
                    <th className="px-4 py-3">Può fare</th>
                    <th className="px-4 py-3 text-right">Raggio di rete</th>
                    <th className="px-4 py-3">Situazione</th>
                    <th className="px-4 py-3"><span className="sr-only">Azioni</span></th>
                  </tr>
                </thead>
                <tbody className="text-surface-300">
                  {roles !== undefined && roles.length === 0 && <EmptyRow colSpan={6} text="Nessun ruolo commerciale." />}
                  {(roles ?? []).map((r) => (
                    <tr key={r.id} onClick={() => setRole({ ...r })} className="cursor-pointer">
                      <td className="px-4 py-3">
                        <Identity name={r.name} detail={<span className="font-mono">{r.code}</span>}>
                          {r.is_default && <span className="mt-1 inline-block"><Chip tone="accent">predefinito</Chip></span>}
                        </Identity>
                      </td>
                      <td className="px-4 py-3">
                        <Stack title={COMMISSION_MODE_LABELS[r.commission_mode] ?? r.commission_mode} detail={r.description || undefined} className="max-w-[240px]" />
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex flex-wrap gap-1.5">
                          <Chip tone={r.can_close_sales ? "ok" : "muted"}>{r.can_close_sales ? "chiude vendite" : "non chiude vendite"}</Chip>
                          {r.allows_downline && <Chip tone="info">introduce persone</Chip>}
                          {r.allows_delegation && <Chip tone="accent">ha delegati</Chip>}
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <Figure
                          value={r.network_depth == null ? "∞" : r.network_depth}
                          detail={r.network_depth == null ? "senza limite" : "livelli"}
                          ratio={r.network_depth == null ? 1 : Math.min(1, r.network_depth / 10)}
                        />
                      </td>
                      <td className="px-4 py-3">
                        <Chip tone={r.is_active ? "ok" : "muted"}>{r.is_active ? "Attivo" : "Disattivato"}</Chip>
                      </td>
                      <td className="px-4 py-3">
                        <RowActions>
                          <button onClick={(e) => { e.stopPropagation(); setRole({ ...r }); }} className="act">Modifica</button>
                        </RowActions>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
          {role && (
            <div className="panel rounded-3xl p-6 md:p-7 pop">
              <div className="kpi-label">{role.id ? "Modifica ruolo" : "Nuovo ruolo"}</div>
              <h3 className="mt-1 mb-4 text-xl font-black tracking-tight text-white">{role.name || "Senza nome"}</h3>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs text-surface-300">
                <label className="space-y-1"><span>Codice</span>
                  <input className={field} disabled={!!role.id} value={role.code} onChange={(e) => setRole({ ...role, code: e.target.value.toUpperCase() })} placeholder="es. AGENTE_TLC" />
                </label>
                <label className="space-y-1 md:col-span-2"><span>Nome</span>
                  <input className={field} value={role.name} onChange={(e) => setRole({ ...role, name: e.target.value })} />
                </label>
                <label className="space-y-1 md:col-span-3"><span>Descrizione</span>
                  <input className={field} value={role.description} onChange={(e) => setRole({ ...role, description: e.target.value })} />
                </label>
                <label className="space-y-1"><span>Tipo di remunerazione</span>
                  <select className={field} value={role.commission_mode} onChange={(e) => setRole({ ...role, commission_mode: e.target.value })}>
                    {Object.entries(COMMISSION_MODE_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                  </select>
                </label>
                <label className="space-y-1"><span>Profondità della rete nel calcolo (vuoto = senza limite)</span>
                  <input className={field} inputMode="numeric" value={role.network_depth ?? ""} onChange={(e) => setRole({ ...role, network_depth: e.target.value.trim() === "" ? null : Number(e.target.value.replace(/\D/g, "")) })} />
                </label>
                <label className="space-y-1"><span>Ordine</span>
                  <input className={field} inputMode="numeric" value={role.sort_order} onChange={(e) => setRole({ ...role, sort_order: Number(e.target.value.replace(/\D/g, "") || 0) })} />
                </label>
                {([
                  ["can_close_sales", "Può chiudere vendite (essere il venditore)"],
                  ["allows_downline", "Può introdurre persone nella rete"],
                  ["allows_delegation", "Può avere delegati (influencer)"],
                  ["is_default", "Ruolo predefinito per chi entra nella rete"],
                  ["is_active", "Attivo"],
                ] as const).map(([key, label]) => (
                  <label key={key} className="inline-flex items-center gap-2 cursor-pointer rounded-xl bg-white/5 px-3 py-2">
                    <input type="checkbox" className="accent-brand-500" checked={role[key]} onChange={(e) => setRole({ ...role, [key]: e.target.checked })} />
                    {label}
                  </label>
                ))}
                <div className="md:col-span-3 flex gap-2 pt-2">
                  <button onClick={saveRole} className="act act-primary !h-10 !px-5">Salva</button>
                  <button onClick={() => setRole(null)} className="act !h-10 !px-5">Annulla</button>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {tab === "categories" && (
        <div className="space-y-5">
          <div className="panel rounded-3xl p-4 md:p-6">
            <div className="px-2">
              <div className="kpi-label">Catalogo</div>
              <h3 className="mt-1 text-xl font-black tracking-tight text-white">Categorie prodotti</h3>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-xs text-left">
                <thead>
                  <tr>
                    <th className="px-4 py-3">Famiglia</th>
                    <th className="px-4 py-3">Punto di fornitura</th>
                    <th className="px-4 py-3">Situazione</th>
                  </tr>
                </thead>
                <tbody className="text-surface-300">
                  {categories !== undefined && categories.length === 0 && <EmptyRow colSpan={3} text="Nessuna categoria." />}
                  {(categories ?? []).map((c) => (
                    <tr key={c.id}>
                      <td className="px-4 py-3">
                        <Identity name={c.name} detail={<span className="font-mono">{c.code}</span>} />
                      </td>
                      <td className="px-4 py-3">
                        <label className="inline-flex items-center gap-2 cursor-pointer">
                          <input
                            type="checkbox" className="accent-brand-500" checked={c.requires_supply_point}
                            onChange={(e) => act(() => send(`/api/proxy/commercial/categories/${c.id}`, "PATCH", { requires_supply_point: e.target.checked }), "Categoria aggiornata.", [["commercial", "categories"]])}
                          />
                          <Chip tone={c.requires_supply_point ? "info" : "muted"}>{c.requires_supply_point ? "punto di fornitura richiesto" : "non richiesto"}</Chip>
                        </label>
                      </td>
                      <td className="px-4 py-3">
                        <Chip tone={c.is_active ? "ok" : "muted"}>{c.is_active ? "Attiva" : "Disattivata"}</Chip>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
          <div className="panel rounded-3xl p-6 md:p-7">
            <div className="kpi-label mb-3">Nuova categoria</div>
            <div className="grid grid-cols-1 md:grid-cols-4 gap-3 items-end text-xs text-surface-300">
              <label className="space-y-1"><span>Codice</span><input className={field} value={category.code} onChange={(e) => setCategory({ ...category, code: e.target.value.toUpperCase() })} placeholder="es. TLC" /></label>
              <label className="space-y-1"><span>Nome</span><input className={field} value={category.name} onChange={(e) => setCategory({ ...category, name: e.target.value })} /></label>
              <label className="inline-flex items-center gap-2 cursor-pointer pb-2"><input type="checkbox" className="accent-brand-500" checked={category.requires_supply_point} onChange={(e) => setCategory({ ...category, requires_supply_point: e.target.checked })} /> Richiede punto di fornitura</label>
              <button
                onClick={() => act(() => send("/api/proxy/commercial/categories", "POST", category), "Categoria creata.", [["commercial", "categories"]]).then(() => setCategory({ code: "", name: "", requires_supply_point: false }))}
                disabled={!category.code || !category.name}
                className="act act-primary !h-10 !px-5 justify-center"
              >
                Aggiungi categoria
              </button>
            </div>
          </div>
        </div>
      )}

      {tab === "delegations" && (
        <div className="space-y-5">
          <p className="text-xs text-surface-300 px-1">
            Un delegato che è entrato nella rete direttamente sotto il suo influencer non ha bisogno di una delega: il motore
            lo trova da solo. La delega serve quando il delegato è in un altro ramo, e ha la precedenza.
          </p>
          <div className="panel rounded-3xl p-4 md:p-6">
            <div className="px-2">
              <div className="kpi-label">Eccezioni di rete</div>
              <h3 className="mt-1 text-xl font-black tracking-tight text-white">Deleghe influencer</h3>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-xs text-left">
                <thead>
                  <tr>
                    <th className="px-4 py-3">Influencer</th>
                    <th className="px-4 py-3">Delega a</th>
                    <th className="px-4 py-3">Validità</th>
                    <th className="px-4 py-3">Situazione</th>
                    <th className="px-4 py-3"><span className="sr-only">Azioni</span></th>
                  </tr>
                </thead>
                <tbody className="text-surface-300">
                  {(delegations ?? []).length === 0 && <EmptyRow colSpan={5} text="Nessuna delega esplicita." />}
                  {(delegations ?? []).map((d) => (
                    <tr key={d.id}>
                      <td className="px-4 py-3"><Identity name={d.influencer_name} detail="influencer" /></td>
                      <td className="px-4 py-3"><Identity name={d.delegate_name} detail={d.reason ? <span title={d.reason}>{d.reason}</span> : "delegato"} /></td>
                      <td className="px-4 py-3 whitespace-nowrap">
                        <Stack title={`dal ${fmtDate(d.valid_from)}`} detail={d.valid_to ? `al ${fmtDate(d.valid_to)}` : "senza scadenza"} />
                      </td>
                      <td className="px-4 py-3">
                        <Chip tone={d.valid_to ? "muted" : "ok"} live={!d.valid_to}>{d.valid_to ? "Chiusa" : "In corso"}</Chip>
                      </td>
                      <td className="px-4 py-3">
                        {!d.valid_to && (
                          <RowActions>
                            <button onClick={() => act(() => send(`/api/proxy/commercial/delegations/${d.id}/end`, "POST"), "Delega chiusa.", [["commercial", "delegations"]])} className="act !text-danger-400">Chiudi</button>
                          </RowActions>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
          <div className="panel rounded-3xl p-6 md:p-7">
            <div className="kpi-label mb-3">Nuova delega</div>
            <div className="grid grid-cols-1 md:grid-cols-4 gap-3 items-end text-xs text-surface-300">
              <label className="space-y-1"><span>Influencer</span>
                <AgentPicker value={delegation.influencer_agent_id} onChange={(id) => setDelegation({ ...delegation, influencer_agent_id: id })}
                  placeholder="Scegli…" emptyLabel="Nessuno" ariaLabel="Influencer" />
              </label>
              <label className="space-y-1"><span>Delegato</span>
                <AgentPicker value={delegation.delegate_agent_id} onChange={(id) => setDelegation({ ...delegation, delegate_agent_id: id })}
                  status="ACTIVE" placeholder="Scegli…" emptyLabel="Nessuno" ariaLabel="Delegato" />
              </label>
              <label className="space-y-1"><span>Motivo</span><input className={field} value={delegation.reason} onChange={(e) => setDelegation({ ...delegation, reason: e.target.value })} /></label>
              <button
                onClick={() => act(() => send("/api/proxy/commercial/delegations", "POST", { ...delegation, reason: delegation.reason || null }), "Delega creata.", [["commercial", "delegations"]])}
                disabled={!delegation.influencer_agent_id || !delegation.delegate_agent_id}
                className="act act-primary !h-10 !px-5 justify-center"
              >
                Crea delega
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
