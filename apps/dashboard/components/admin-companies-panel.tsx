"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { friendlyApiError } from "@/lib/api-error";
import { Chip, KpiTile, Orb } from "@/components/ui/data-cells";
import type { CompanyRead, ProductCatalogRead } from "@/lib/types";

/*
 * "Aziende": the companies behind the products (energy supplier, telco...).
 * Each product belongs to one company, and the company says how many levels
 * of a collaborator's network its products reach. Editing happens inline,
 * never in a popup; products are assigned with one click.
 */

async function getJson<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(await friendlyApiError(res));
  return res.json();
}

type Draft = {
  id: string | null;
  name: string;
  description: string;
  website_url: string;
  logo_url: string;
  max_network_depth: string;
  is_active: boolean;
};

const EMPTY: Draft = { id: null, name: "", description: "", website_url: "", logo_url: "", max_network_depth: "", is_active: true };

export function AdminCompaniesPanel() {
  const queryClient = useQueryClient();
  const { data: companies } = useQuery({ queryKey: ["admin", "companies"], queryFn: () => getJson<CompanyRead[]>("/api/proxy/products/companies") });
  const { data: products } = useQuery({ queryKey: ["admin", "products", "for-companies"], queryFn: () => getJson<ProductCatalogRead[]>("/api/proxy/products") });
  const [draft, setDraft] = useState<Draft | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [participantsOf, setParticipantsOf] = useState<string | null>(null);

  const contractProducts = (products ?? []).filter((p) => p.category === "INTERNAL");
  const unassigned = contractProducts.filter((p) => !p.company_id).length;

  async function refresh() {
    await queryClient.invalidateQueries({ queryKey: ["admin", "companies"] });
    await queryClient.invalidateQueries({ queryKey: ["admin", "products"] });
  }

  async function save() {
    if (!draft) return;
    setBusy(true);
    setError(null);
    try {
      const body = {
        name: draft.name,
        description: draft.description,
        website_url: draft.website_url || null,
        logo_url: draft.logo_url || null,
        max_network_depth: draft.max_network_depth ? Number(draft.max_network_depth) : null,
        is_active: draft.is_active,
      };
      const res = await fetch(draft.id ? `/api/proxy/products/companies/${draft.id}` : "/api/proxy/products/companies", {
        method: draft.id ? "PUT" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      await refresh();
      setDraft(null);
    } catch (err: any) {
      setError(err.message || "Salvataggio non riuscito.");
    } finally {
      setBusy(false);
    }
  }

  async function assign(product: ProductCatalogRead, companyId: string | null) {
    setError(null);
    const res = await fetch(`/api/proxy/products/${product.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(companyId ? { company_id: companyId } : { clear_company: true }),
    });
    if (!res.ok) {
      setError(await friendlyApiError(res));
      return;
    }
    await refresh();
  }

  const field = "field w-full rounded-2xl px-4 py-2.5 text-sm";

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <KpiTile label="Aziende" value={companies?.length ?? "…"} hint="dietro ai prodotti" />
        <KpiTile label="Attive" value={(companies ?? []).filter((c) => c.is_active).length} />
        <KpiTile label="Prodotti assegnati" value={contractProducts.length - unassigned} hint={`su ${contractProducts.length} contratti`} />
        <KpiTile label="Da assegnare" value={unassigned} hint={unassigned ? "prodotti senza azienda" : "tutto in ordine"} />
      </div>

      {error && <div className="panel rounded-3xl p-4 text-sm text-danger-300">{error}</div>}

      {draft ? (
        <section className="panel rounded-3xl p-6 sm:p-8">
          <p className="kpi-label">{draft.id ? "Modifica azienda" : "Nuova azienda"}</p>
          <h3 className="mt-1 text-xl font-black tracking-tight text-white">{draft.name || "Azienda senza nome"}</h3>
          <div className="mt-5 grid gap-4 md:grid-cols-2">
            <label className="space-y-1.5 text-xs text-surface-300">
              <span>Nome</span>
              <input className={field} value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
            </label>
            <label className="space-y-1.5 text-xs text-surface-300">
              <span>Livelli di rete raggiunti (vuoto = senza limite)</span>
              <input
                className={field}
                inputMode="numeric"
                placeholder="es. 3"
                value={draft.max_network_depth}
                onChange={(e) => setDraft({ ...draft, max_network_depth: e.target.value.replace(/\D/g, "").slice(0, 2) })}
              />
            </label>
            <label className="space-y-1.5 text-xs text-surface-300 md:col-span-2">
              <span>Descrizione</span>
              <textarea className={`${field} min-h-24`} value={draft.description} onChange={(e) => setDraft({ ...draft, description: e.target.value })} />
            </label>
            <label className="space-y-1.5 text-xs text-surface-300">
              <span>Sito web</span>
              <input className={field} value={draft.website_url} onChange={(e) => setDraft({ ...draft, website_url: e.target.value })} />
            </label>
            <label className="space-y-1.5 text-xs text-surface-300">
              <span>Logo (indirizzo dell&apos;immagine)</span>
              <input className={field} value={draft.logo_url} onChange={(e) => setDraft({ ...draft, logo_url: e.target.value })} />
            </label>
            <label className="flex items-center gap-3 text-sm text-surface-200">
              <input type="checkbox" className="h-5 w-5 accent-brand-500" checked={draft.is_active} onChange={(e) => setDraft({ ...draft, is_active: e.target.checked })} />
              Attiva: i suoi prodotti compaiono ai promoter
            </label>
          </div>
          <div className="mt-6 flex flex-wrap gap-3">
            <button className="act act-primary !h-11 !px-6" disabled={busy || !draft.name.trim()} onClick={save}>
              {busy ? "Salvataggio…" : "Salva"}
            </button>
            <button className="act !h-11 !px-6" onClick={() => setDraft(null)}>Annulla</button>
          </div>
          <p className="mt-4 text-xs text-surface-400">
            I livelli limitano la rete per prodotto che vedono i promoter, e uno Split Plan su un prodotto di questa azienda non può
            pagare oltre questo livello.
          </p>
        </section>
      ) : (
        <div className="flex justify-end">
          <button className="act act-primary !h-11 !px-6" onClick={() => setDraft(EMPTY)}>+ Nuova azienda</button>
        </div>
      )}

      <div className="grid gap-5 xl:grid-cols-2">
        {(companies ?? []).map((company) => {
          const mine = contractProducts.filter((p) => p.company_id === company.id);
          const free = contractProducts.filter((p) => !p.company_id);
          return (
            <section key={company.id} className="panel rounded-3xl p-6">
              <div className="flex items-start justify-between gap-4">
                <div className="flex items-center gap-4">
                  {company.logo_url ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={company.logo_url} alt="" className="h-12 w-12 rounded-2xl bg-white object-contain p-1" />
                  ) : (
                    <Orb name={company.name} />
                  )}
                  <div>
                    <h3 className="text-lg font-black tracking-tight text-white">{company.name}</h3>
                    <div className="mt-1 flex flex-wrap gap-2">
                      <Chip tone={company.is_active ? "ok" : "muted"}>{company.is_active ? "Attiva" : "Sospesa"}</Chip>
                      <Chip tone="info">
                        {company.max_network_depth ? `Rete fino a ${company.max_network_depth} livelli` : "Rete senza limite"}
                      </Chip>
                    </div>
                  </div>
                </div>
                <button
                  className="act"
                  onClick={() =>
                    setDraft({
                      id: company.id,
                      name: company.name,
                      description: company.description,
                      website_url: company.website_url ?? "",
                      logo_url: company.logo_url ?? "",
                      max_network_depth: company.max_network_depth ? String(company.max_network_depth) : "",
                      is_active: company.is_active,
                    })
                  }
                >
                  Modifica
                </button>
              </div>
              {company.description && <p className="mt-3 text-sm text-surface-300">{company.description}</p>}

              <button
                className="act mt-4"
                onClick={() => setParticipantsOf(participantsOf === company.id ? null : company.id)}
              >
                {participantsOf === company.id ? "Nascondi partecipanti" : "Partecipanti: promoter e clienti"}
              </button>
              {participantsOf === company.id && <CompanyParticipants companyId={company.id} />}

              <p className="kpi-label mt-5">Prodotti · {mine.length}</p>
              <div className="mt-2 flex flex-wrap gap-2">
                {mine.length === 0 && <span className="text-sm text-surface-400">Nessun prodotto assegnato.</span>}
                {mine.map((p) => (
                  <button key={p.id} className="subnav-pill" data-active onClick={() => assign(p, null)} title="Togli da questa azienda">
                    {p.current_version?.name ?? p.code} ✕
                  </button>
                ))}
              </div>
              {free.length > 0 && (
                <>
                  <p className="kpi-label mt-4">Aggiungi</p>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {free.map((p) => (
                      <button key={p.id} className="subnav-pill" onClick={() => assign(p, company.id)}>
                        + {p.current_version?.name ?? p.code}
                      </button>
                    ))}
                  </div>
                </>
              )}
            </section>
          );
        })}
      </div>
    </div>
  );
}


type Participant = {
  agent_id: string;
  name: string;
  promoter_code: string | null;
  role_name: string | null;
  joined_at: string | null;
  left_at: string | null;
  contracts: number;
  value_cents: number;
};

type ParticipantsRead = {
  members: Participant[];
  former_members: Participant[];
  sellers_not_members: Participant[];
  customers: { customer_id: string; name: string; products: string[]; value_cents: number; since: string | null; seller: string }[];
};

function euro(cents: number): string {
  return (cents / 100).toLocaleString("it-IT", { style: "currency", currency: "EUR" });
}

function day(value: string | null): string {
  return value ? new Date(value).toLocaleDateString("it-IT", { day: "2-digit", month: "short", year: "numeric" }) : "—";
}

/** Who takes part in one company's plans: promoters (joined or just selling) and customers. */
function CompanyParticipants({ companyId }: { companyId: string }) {
  const { data, error } = useQuery({
    queryKey: ["admin", "companies", companyId, "participants"],
    queryFn: () => getJson<ParticipantsRead>(`/api/proxy/network/companies/${companyId}/participants`),
  });
  if (error) return <p className="mt-3 text-sm text-danger-300">{(error as Error).message}</p>;
  if (!data) return <div className="mt-4 h-24 animate-pulse rounded-2xl bg-white/5" />;

  const promoterList = (rows: Participant[], empty: string, extra?: (p: Participant) => string) =>
    rows.length === 0 ? (
      <p className="text-sm text-surface-400">{empty}</p>
    ) : (
      <ul className="space-y-2">
        {rows.map((p) => (
          <li key={p.agent_id} className="flex items-center justify-between gap-3 rounded-2xl bg-white/5 px-3 py-2">
            <span className="flex min-w-0 items-center gap-3">
              <Orb name={p.name} />
              <span className="min-w-0">
                <span className="block truncate text-sm font-bold text-white">{p.name}</span>
                <span className="block truncate text-[11px] text-surface-400">
                  {[p.role_name, extra?.(p)].filter(Boolean).join(" · ")}
                </span>
              </span>
            </span>
            <span className="text-right text-xs text-surface-300">
              <span className="block font-black text-white">{p.contracts} contr.</span>
              {euro(p.value_cents)}
            </span>
          </li>
        ))}
      </ul>
    );

  return (
    <div className="mt-4 space-y-5">
      <div>
        <p className="kpi-label mb-2">Promoter che partecipano · {data.members.length}</p>
        {promoterList(data.members, "Nessun promoter ha ancora aderito.", (p) => `dal ${day(p.joined_at)}`)}
      </div>
      {data.sellers_not_members.length > 0 && (
        <div>
          <p className="kpi-label mb-2">Vendono senza aver aderito · {data.sellers_not_members.length}</p>
          {promoterList(data.sellers_not_members, "")}
        </div>
      )}
      {data.former_members.length > 0 && (
        <div>
          <p className="kpi-label mb-2">Hanno lasciato · {data.former_members.length}</p>
          {promoterList(data.former_members, "", (p) => `uscito il ${day(p.left_at)}`)}
        </div>
      )}
      <div>
        <p className="kpi-label mb-2">Clienti con i suoi prodotti · {data.customers.length}</p>
        {data.customers.length === 0 ? (
          <p className="text-sm text-surface-400">Nessun contratto attivo.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr>
                  <th className="px-3">Cliente</th>
                  <th className="px-3">Prodotti</th>
                  <th className="px-3">Venduto da</th>
                  <th className="px-3 text-right">Valore</th>
                </tr>
              </thead>
              <tbody>
                {data.customers.map((c) => (
                  <tr key={c.customer_id}>
                    <td className="px-3 py-2.5">
                      <div className="font-bold text-white">{c.name}</div>
                      <div className="text-[11px] text-surface-400">dal {day(c.since)}</div>
                    </td>
                    <td className="px-3 py-2.5 text-surface-200">{c.products.join(", ")}</td>
                    <td className="px-3 py-2.5 text-surface-200">{c.seller}</td>
                    <td className="px-3 py-2.5 text-right font-black tabular-nums text-white">{euro(c.value_cents)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
