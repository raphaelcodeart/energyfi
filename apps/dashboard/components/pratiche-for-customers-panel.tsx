"use client";

import { useState, type CSSProperties } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ContractRequestsList, type WizardTarget } from "@/components/contract-requests-list";
import { ContractRequestWizard } from "@/components/contract-request-wizard";
import { CUSTOMER_KIND_LABELS, NewCustomerForm } from "@/components/new-customer-form";
import { Pagination, usePagination } from "@/components/pagination";
import { Chip, Identity, RowActions } from "@/components/ui/data-cells";
import { AgentPicker } from "@/components/agent-picker";
import { friendlyApiError } from "@/lib/api-error";
import type { CustomerRead } from "@/lib/types";

type WizardCustomer = {
  id: string;
  kind: string | null;
  email: string | null;
  firstName?: string | null;
  lastName?: string | null;
  pec?: string | null;
};

type Mode = "promoter" | "admin";
type Action = "new" | "existing" | null;

async function fetchJson<T>(path: string): Promise<T> {
  const res = await fetch(path);
  if (!res.ok) throw new Error(await friendlyApiError(res));
  return res.json();
}

function toWizardCustomer(c: CustomerRead): WizardCustomer {
  return { id: c.id, kind: c.kind, email: c.email, firstName: c.first_name, lastName: c.last_name, pec: c.pec };
}

const FLOW = ["Cliente", "Dati e contratti", "Documenti", "Offerta per ogni contratto", "Il cliente paga"];

/** Activating contracts on a customer's behalf: the promoter's "Miei
 *  Clienti" and the admin "Nuovo Contratto". Start from a new customer
 *  (registered with a login) or an existing one, then run the customer's own
 *  pratica wizard without the payment step: once sent, the customer is
 *  emailed and pays from their area.
 *
 *  Admins also choose the attributed promoter and can give a login to a
 *  customer without one, who could not pay otherwise.
 */
export function PraticheForCustomersPanel({ mode }: { mode: Mode }) {
  const queryClient = useQueryClient();
  const customersKey = mode === "promoter" ? ["network", "customers", "mine"] : ["admin", "customers"];
  const { data: customers, error: customersError } = useQuery({
    queryKey: customersKey,
    queryFn: () => fetchJson<CustomerRead[]>(mode === "promoter" ? "/api/proxy/network/customers/mine" : "/api/proxy/customers"),
  });

  const [action, setAction] = useState<Action>(null);
  const [producerAgentId, setProducerAgentId] = useState("");
  const [wizard, setWizard] = useState<{ customer: WizardCustomer; target: WizardTarget | "new"; producer: string | null } | null>(null);
  const [listTab, setListTab] = useState<"customers" | "pratiche">("customers");
  const [expandedCustomerId, setExpandedCustomerId] = useState<string | null>(null);

  function openFor(customer: CustomerRead, producer: string | null) {
    setAction(null);
    setWizard({ customer: toWizardCustomer(customer), target: "new", producer });
  }

  return (
    <div className="space-y-6">
      {/* New or existing customer. */}
      <div className="panel rounded-3xl p-6 sm:p-8 space-y-5">
        <div>
          <div className="kpi-label">{mode === "promoter" ? "I tuoi clienti" : "Nuova pratica"}</div>
          <h3 className="mt-1 text-3xl font-black tracking-tight text-white">
            Attiva contratti <span className="text-gradient">per un cliente</span>
          </h3>
          <p className="text-xs text-surface-300 mt-2 max-w-3xl">
            Gli stessi passaggi che fa il cliente quando attiva da solo, senza il pagamento: quando invii la pratica il
            cliente riceve un&apos;email e paga dalla sua area.
            {mode === "promoter"
              ? " Resta scritto che l'hai compilata tu e le provvigioni sono tue."
              : " Scegli tu a quale promoter attribuirla."}
          </p>
          <ol className="mt-4 flex flex-wrap items-center gap-2 stagger">
            {FLOW.map((label, i) => (
              <li key={label} className="flex items-center gap-2" style={{ "--i": i } as CSSProperties}>
                <span
                  className={`flex items-center gap-2 pl-1 pr-3 py-1 rounded-full text-[11.5px] font-bold border ${
                    i === FLOW.length - 1
                      ? "bg-success-500/15 text-success-300 border-success-500/30"
                      : "bg-white/5 text-surface-200 border-white/10"
                  }`}
                >
                  <span className="w-6 h-6 rounded-full bg-gradient-to-br from-brand-500 to-accent-500 text-white text-[10px] font-black flex items-center justify-center shadow-md shadow-brand-500/30">
                    {i + 1}
                  </span>
                  {label}
                </span>
                {i < FLOW.length - 1 && <span className="text-surface-400 text-xs">→</span>}
              </li>
            ))}
          </ol>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <ActionCard
            active={action === "new"}
            title="Nuovo cliente"
            text="Registralo adesso e attiva subito i suoi contratti. Riceve l'invito a impostare la password."
            icon="M18 9v3m0 0v3m0-3h3m-3 0h-3m-2-5a4 4 0 11-8 0 4 4 0 018 0zM3 20a6 6 0 0112 0v1H3v-1z"
            onClick={() => setAction(action === "new" ? null : "new")}
          />
          <ActionCard
            active={action === "existing"}
            title="Cliente già registrato"
            text="Aggiungi uno o più contratti a un cliente che hai già: cercalo per nome, email o codice fiscale."
            icon="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
            onClick={() => setAction(action === "existing" ? null : "existing")}
          />
        </div>

        {action === "new" && (
          <div className="p-5 sm:p-6 rounded-3xl border border-white/15 bg-white/[0.04] pop">
            <p className="text-lg font-black tracking-tight text-white mb-4">1 · Dati del nuovo cliente</p>
            <NewCustomerForm
              mode={mode}
              onCancel={() => setAction(null)}
              onCreated={async (customer, promoterAgentId) => {
                await queryClient.invalidateQueries({ queryKey: customersKey });
                openFor(customer, promoterAgentId);
              }}
            />
          </div>
        )}

        {action === "existing" && (
          <div className="p-5 sm:p-6 rounded-3xl border border-white/15 bg-white/[0.04] space-y-4 pop">
            <p className="text-lg font-black tracking-tight text-white">1 · Per quale cliente?</p>
            {mode === "admin" && <ProducerSelect value={producerAgentId} onChange={setProducerAgentId} />}
            <CustomerPicker
              mode={mode}
              customers={customers}
              error={customersError as Error | null}
              onPick={(c) => openFor(c, producerAgentId || null)}
              onLoginCreated={() => queryClient.invalidateQueries({ queryKey: customersKey })}
            />
          </div>
        )}
      </div>

      {mode === "promoter" ? (
        <div className="space-y-4">
          <div className="subnav">
            {(
              [
                ["customers", `I miei clienti${customers ? ` (${customers.length})` : ""}`],
                ["pratiche", "Tutte le pratiche"],
              ] as const
            ).map(([key, label]) => (
              <button
                key={key}
                onClick={() => setListTab(key)}
                data-active={listTab === key}
                className="subnav-pill cursor-pointer"
              >
                {label}
              </button>
            ))}
          </div>
          {listTab === "customers" ? (
            <MyCustomersList
              customers={customers}
              error={customersError as Error | null}
              expandedCustomerId={expandedCustomerId}
              onToggle={(id) => setExpandedCustomerId(expandedCustomerId === id ? null : id)}
              onActivate={(c) => openFor(c, null)}
              onOpenWizard={(c, target) => setWizard({ customer: toWizardCustomer(c), target, producer: null })}
            />
          ) : (
            <ContractRequestsList
              mode="promoter"
              onOpenWizard={(target) => {
                if (!target.customer) return;
                setWizard({ customer: target.customer, target, producer: null });
              }}
            />
          )}
        </div>
      ) : (
        <div className="space-y-3">
          <div>
            <div className="kpi-label">Bozze e pratiche</div>
            <h3 className="mt-1 text-xl font-black tracking-tight text-white">Pratiche aperte dall&apos;amministrazione</h3>
            <p className="text-xs text-surface-300 mt-1">
              Riprendi le bozze da qui. Verifiche, approvazioni e bonifici da confermare di tutte le pratiche sono in{" "}
              <strong>Pratiche</strong>.
            </p>
          </div>
          <ContractRequestsList
            mode="admin"
            onOpenWizard={(target) => {
              if (!target.customer) return;
              setWizard({ customer: target.customer, target, producer: null });
            }}
          />
        </div>
      )}

      {wizard && (
        <ContractRequestWizard
          requestId={wizard.target === "new" ? undefined : wizard.target.requestId}
          initialStep={wizard.target === "new" ? undefined : wizard.target.step}
          customer={wizard.customer}
          producerAgentId={mode === "admin" ? wizard.producer : null}
          onClose={() => {
            if (mode === "promoter") setExpandedCustomerId(wizard.customer.id);
            setWizard(null);
          }}
        />
      )}
    </div>
  );
}

function ActionCard({
  active,
  title,
  text,
  icon,
  onClick,
}: {
  active: boolean;
  title: string;
  text: string;
  icon: string;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`group flex items-start gap-4 p-5 rounded-3xl border text-left transition duration-300 cursor-pointer hover:-translate-y-0.5 ${
        active
          ? "border-white/50 bg-gradient-to-br from-brand-500/25 to-accent-500/10 shadow-xl shadow-brand-500/25"
          : "border-white/10 bg-white/5 hover:border-white/30"
      }`}
    >
      <span
        className={`p-3 rounded-2xl shrink-0 transition-colors ${
          active
            ? "bg-gradient-to-br from-brand-500 to-accent-500 text-white shadow-lg shadow-brand-500/40"
            : "bg-white/10 text-brand-300 group-hover:bg-gradient-to-br group-hover:from-brand-500 group-hover:to-accent-500 group-hover:text-white"
        }`}
      >
        <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d={icon} />
        </svg>
      </span>
      <span className="min-w-0">
        <span className="block text-base font-black tracking-tight text-white">{title}</span>
        <span className="block text-xs text-surface-300 mt-1">{text}</span>
      </span>
    </button>
  );
}

function ProducerSelect({
  value,
  onChange,
}: {
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className="block">
      <span className="block kpi-label mb-1">
        Promoter a cui attribuire la pratica
      </span>
      <AgentPicker
        value={value}
        onChange={(id) => onChange(id)}
        status="ACTIVE"
        className="w-full max-w-md"
        placeholder="Il promoter del cliente (predefinito)"
        emptyLabel="Il promoter del cliente (predefinito)"
        ariaLabel="Promoter a cui attribuire la pratica"
      />
      <span className="block text-[10px] text-surface-500 mt-1">Decide chi guadagna le provvigioni di questa pratica.</span>
    </label>
  );
}

function CustomerPicker({
  mode,
  customers,
  error,
  onPick,
  onLoginCreated,
}: {
  mode: Mode;
  customers: CustomerRead[] | undefined;
  error: Error | null;
  onPick: (customer: CustomerRead) => void;
  onLoginCreated: () => void;
}) {
  const [search, setSearch] = useState("");
  const [needsLogin, setNeedsLogin] = useState<CustomerRead | null>(null);
  const [busy, setBusy] = useState(false);
  const [loginError, setLoginError] = useState<string | null>(null);

  const needle = search.trim().toLowerCase();
  const matches = (customers ?? []).filter(
    (c) =>
      !needle ||
      [c.display_name, c.email, c.phone, c.fiscal_code, c.vat_number]
        .filter(Boolean)
        .some((v) => v!.toLowerCase().includes(needle))
  );

  async function createLoginAndContinue(customer: CustomerRead) {
    setBusy(true);
    setLoginError(null);
    try {
      const res = await fetch(`/api/proxy/customers/${customer.id}/account`, { method: "POST" });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      const updated = (await res.json()) as CustomerRead;
      onLoginCreated();
      setNeedsLogin(null);
      onPick(updated);
    } catch (err: any) {
      setLoginError(err.message || "Impossibile creare l'accesso.");
    } finally {
      setBusy(false);
    }
  }

  if (needsLogin) {
    return (
      <div className="p-5 rounded-2xl border border-warn-500/30 bg-warn-500/10 space-y-3 pop">
        <p className="text-sm font-semibold text-warn-300">
          {needsLogin.display_name} non ha ancora un accesso alla sua area
        </p>
        <p className="text-xs text-surface-300">
          Senza accesso non potrebbe pagare la pratica.
          {mode === "admin" ? (
            <>
              {" "}Creiamo l&apos;account su <strong>{needsLogin.email}</strong> e gli mandiamo l&apos;email per impostare la
              password, poi apri la pratica.
            </>
          ) : (
            " Per creargli l'accesso scrivi al Supporto."
          )}
        </p>
        {loginError && <p className="text-xs text-danger-400">{loginError}</p>}
        <div className="flex flex-wrap gap-2">
          {mode === "admin" && (
            <button
              onClick={() => createLoginAndContinue(needsLogin)}
              disabled={busy}
              className="act act-primary cursor-pointer"
            >
              {busy ? "Creazione..." : "Crea l'accesso e continua"}
            </button>
          )}
          <button
            onClick={() => onPick(needsLogin)}
            className="act cursor-pointer"
          >
            Continua comunque
          </button>
          <button onClick={() => setNeedsLogin(null)} className="px-3 py-2 text-xs text-surface-400 cursor-pointer">
            Indietro
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <input
        autoFocus
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        placeholder="Cerca per nome, email, telefono, codice fiscale, partita IVA..."
        className="w-full rounded-xl field px-3 py-2.5 text-sm focus:border-brand-500"
      />
      {error && <p className="text-xs text-danger-400">{error.message}</p>}
      <div className="max-h-80 overflow-y-auto space-y-1.5 pr-1">
        {matches.length === 0 ? (
          <div className="flex flex-col items-center gap-2 px-4 py-8 text-center">
            <span className="text-2xl" aria-hidden="true">🔎</span>
            <p className="text-xs text-surface-300">
              {customers === undefined ? "Caricamento..." : "Nessun cliente trovato. È nuovo? Usa “Nuovo cliente”."}
            </p>
          </div>
        ) : (
          matches.slice(0, 60).map((c) => (
            <button
              key={c.id}
              onClick={() => (c.user_id ? onPick(c) : setNeedsLogin(c))}
              className="group w-full flex items-center justify-between gap-3 px-4 py-3 rounded-2xl border border-white/5 bg-white/[0.03] text-left hover:bg-white/10 hover:border-white/20 transition cursor-pointer"
            >
              <Identity
                name={c.display_name}
                detail={[CUSTOMER_KIND_LABELS[c.kind] ?? c.kind, c.email, c.fiscal_code].filter(Boolean).join(" · ")}
              />
              <span className="flex items-center gap-2 shrink-0">
                {!c.user_id && <Chip tone="warn">Senza accesso</Chip>}
                <span className="text-[11px] font-black text-white/80 group-hover:text-white">Attiva contratti →</span>
              </span>
            </button>
          ))
        )}
      </div>
    </div>
  );
}

function MyCustomersList({
  customers,
  error,
  expandedCustomerId,
  onToggle,
  onActivate,
  onOpenWizard,
}: {
  customers: CustomerRead[] | undefined;
  error: Error | null;
  expandedCustomerId: string | null;
  onToggle: (id: string) => void;
  onActivate: (customer: CustomerRead) => void;
  onOpenWizard: (customer: CustomerRead, target: WizardTarget) => void;
}) {
  const [search, setSearch] = useState("");
  const needle = search.trim().toLowerCase();
  const filtered = (customers ?? []).filter(
    (c) =>
      !needle ||
      [c.display_name, c.email, c.phone, c.fiscal_code].filter(Boolean).some((v) => v!.toLowerCase().includes(needle))
  );
  const pagination = usePagination(filtered);

  if (error) return <p className="text-sm text-danger-400">{error.message}</p>;

  return (
    <div className="space-y-3">
      {(customers?.length ?? 0) > 5 && (
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Cerca tra i tuoi clienti..."
          className="w-full max-w-md rounded-xl field px-3 py-2.5 text-sm focus:border-brand-500"
        />
      )}
      <div className="space-y-3 stagger">
        {customers === undefined ? (
          <p className="panel rounded-3xl text-center py-8 text-surface-400 text-sm">Caricamento...</p>
        ) : filtered.length === 0 ? (
          <div className="panel rounded-3xl flex flex-col items-center gap-3 py-12 text-center">
            <span className="text-3xl float-soft" aria-hidden="true">👥</span>
            <p className="text-sm text-surface-300">
              {customers.length === 0 ? "Non hai ancora nessun cliente: inizia da “Nuovo cliente”." : "Nessun cliente trovato."}
            </p>
          </div>
        ) : (
          pagination.pageItems.map((c, i) => (
            <div
              key={c.id}
              className={`panel rounded-3xl overflow-hidden transition ${expandedCustomerId === c.id ? "ring-1 ring-white/40" : ""}`}
              style={{ "--i": i } as CSSProperties}
            >
              <div className="p-4 sm:p-5 flex flex-wrap items-center justify-between gap-4">
                <Identity
                  name={c.display_name}
                  detail={`${CUSTOMER_KIND_LABELS[c.kind] ?? c.kind} · ${c.email}${c.phone ? ` · ${c.phone}` : ""}`}
                />
                <div className="flex items-center gap-3 flex-wrap">
                  {c.email_verified ? (
                    <Chip tone="ok">Account attivo</Chip>
                  ) : (
                    <Chip tone="warn" live>In attesa di primo accesso</Chip>
                  )}
                  <RowActions>
                    <button onClick={() => onToggle(c.id)} className="act cursor-pointer">
                      {expandedCustomerId === c.id ? "Nascondi pratiche" : "Pratiche"}
                    </button>
                    <button onClick={() => onActivate(c)} className="act act-primary cursor-pointer">
                      + Attiva contratti
                    </button>
                  </RowActions>
                </div>
              </div>
              {expandedCustomerId === c.id && (
                <div className="px-4 sm:px-5 pb-5 rise">
                  <ContractRequestsList mode="promoter" customerId={c.id} onOpenWizard={(target) => onOpenWizard(c, target)} />
                </div>
              )}
            </div>
          ))
        )}
      </div>
      <Pagination {...pagination} label="clienti" />
    </div>
  );
}
