"use client";

import { sectionEnabled, useFeatures } from "@/lib/features";
import { Fragment, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ContractRequestWizard } from "@/components/contract-request-wizard";
import { NewCustomerForm } from "@/components/new-customer-form";
import { Pagination, usePagination } from "@/components/pagination";
import { PhotoUpload } from "@/components/photo-upload";
import { friendlyApiError } from "@/lib/api-error";
import { downloadCsv } from "@/lib/csv-export";
import { AgentPicker } from "@/components/agent-picker";
import type { ContractRead, CustomerDetailRead, CustomerRead, WalletRead } from "@/lib/types";
import { Chip, IdTag, Identity, KpiTile, RowActions, Stack, type ChipTone } from "@/components/ui/data-cells";

const CONTRACT_STATUS_LABELS: Record<string, string> = {
  DRAFT: "Bozza",
  SUBMITTED: "Inviata",
  DOCUMENTS_PENDING: "Documenti mancanti",
  UNDER_REVIEW: "In revisione",
  APPROVED: "Approvata",
  PAYMENT_PENDING: "In attesa di pagamento",
  PAID: "Pagata",
  ACTIVATION_PENDING: "In attivazione",
  ACTIVE: "Attiva",
  SUSPENDED: "Sospesa",
  CANCELLED: "Cessata",
  EXPIRED: "Scaduta",
  RENEWED: "Rinnovata",
  REJECTED: "Respinta",
};

function contractStatusTone(status: string): ChipTone {
  if (status === "ACTIVE" || status === "RENEWED") return "ok";
  if (status === "REJECTED" || status === "CANCELLED") return "bad";
  if (status === "DRAFT") return "muted";
  return "warn";
}

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString("it-IT", { day: "2-digit", month: "short", year: "numeric" });
}

async function fetchAllContracts(): Promise<ContractRead[]> {
  const res = await fetch("/api/proxy/contracts");
  if (!res.ok) throw new Error("Impossibile caricare i contratti.");
  return res.json();
}

async function fetchCustomers(): Promise<CustomerRead[]> {
  const res = await fetch("/api/proxy/customers");
  if (!res.ok) throw new Error("Impossibile caricare i clienti.");
  return res.json();
}

async function fetchCustomerDetail(id: string): Promise<CustomerDetailRead> {
  const res = await fetch(`/api/proxy/customers/${id}`);
  if (!res.ok) throw new Error("Impossibile caricare i dettagli del cliente.");
  return res.json();
}

// null means the user has never transacted; the admin view does not create a
// wallet just by looking.
async function fetchCustomerWallet(userId: string): Promise<WalletRead | null> {
  const res = await fetch(`/api/proxy/wallets/admin/${userId}`);
  if (res.status === 404) return null;
  if (!res.ok) throw new Error("Impossibile caricare il wallet.");
  return res.json();
}

function euro(cents: number): string {
  return (cents / 100).toLocaleString("it-IT", { style: "currency", currency: "EUR" });
}

/** Uploaded photo rendered inside the identity orb; initials are the fallback. */
function customerPhoto(url: string | null) {
  if (!url) return undefined;
  // eslint-disable-next-line @next/next/no-img-element -- externally-hosted, variable-source uploaded photo
  return <img src={url} alt="" className="h-full w-full rounded-[14px] object-cover" />;
}

function CloseIcon() {
  return (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M6 18L18 6M6 6l12 12" />
    </svg>
  );
}

const KIND_LABELS: Record<string, string> = {
  PRIVATE: "Privato",
  SOLE_PROPRIETOR: "Partita IVA",
  COMPANY: "Azienda",
  CONDOMINIUM: "Condominio",
};

const PRIVATE_LIKE = new Set(["PRIVATE", "SOLE_PROPRIETOR"]);

export function AdminCustomersPanel({
  initialActiveOnly = false,
  isSuperAdmin = false,
}: { initialActiveOnly?: boolean; isSuperAdmin?: boolean } = {}) {
  const features = useFeatures();
  const queryClient = useQueryClient();
  const { data: customers, error: loadError } = useQuery({
    queryKey: ["admin", "customers"],
    queryFn: fetchCustomers,
  });
  const [showCreate, setShowCreate] = useState(false);
  const [search, setSearch] = useState("");
  const [activeOnly, setActiveOnly] = useState(initialActiveOnly);

  const [viewingId, setViewingId] = useState<string | null>(null);
  const { data: viewingDetail, error: viewError } = useQuery({
    queryKey: ["admin", "customers", "detail", viewingId],
    queryFn: () => fetchCustomerDetail(viewingId!),
    enabled: viewingId !== null,
  });
  const { data: allContracts } = useQuery({
    queryKey: ["admin", "contracts", "all"],
    queryFn: fetchAllContracts,
  });
  const customerIdsWithActiveContract = new Set(
    (allContracts ?? []).filter((c) => c.status === "ACTIVE" || c.status === "RENEWED").map((c) => c.customer_id)
  );
  const [expandedContractId, setExpandedContractId] = useState<string | null>(null);
  const customerContracts = (allContracts ?? []).filter((c) => c.customer_id === viewingId);

  // Top-up, shown only when the customer has a login to attach a wallet to.
  const { data: viewingWallet } = useQuery({
    queryKey: ["admin", "wallets", "by-user", viewingDetail?.user_id],
    queryFn: () => fetchCustomerWallet(viewingDetail!.user_id!),
    enabled: !!viewingDetail?.user_id,
  });
  const [topUpAmount, setTopUpAmount] = useState("");
  const [topUpNote, setTopUpNote] = useState("");
  const [topUpLoading, setTopUpLoading] = useState(false);
  const [topUpError, setTopUpError] = useState<string | null>(null);
  const [topUpSuccess, setTopUpSuccess] = useState(false);
  // Idempotency key: stable across retries of the same top-up, rotated only
  // after success. The credit is committed before the confirmation email, so an
  // error may follow a top-up that went through; reusing the key prevents a
  // double credit (see core/email.py::send_html_email_best_effort).
  const topUpKeyRef = useRef<string>("");

  async function handleTopUp(e: React.FormEvent) {
    e.preventDefault();
    if (!viewingDetail?.user_id) return;
    const amountCents = Math.round(parseFloat(topUpAmount.replace(",", ".")) * 100);
    if (!Number.isFinite(amountCents) || amountCents <= 0) {
      setTopUpError("Inserisci un importo valido.");
      return;
    }
    setTopUpLoading(true);
    setTopUpError(null);
    try {
      const res = await fetch("/api/proxy/wallets/admin/topup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_id: viewingDetail.user_id,
          amount_cents: amountCents,
          note: topUpNote || null,
          idempotency_key: topUpKeyRef.current,
        }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      setTopUpSuccess(true);
      setTopUpAmount("");
      setTopUpNote("");
      // The form stays open after success, so the next top-up needs a new key.
      topUpKeyRef.current = crypto.randomUUID();
      await queryClient.invalidateQueries({ queryKey: ["admin", "wallets", "by-user", viewingDetail.user_id] });
      setTimeout(() => setTopUpSuccess(false), 3000);
    } catch (err: any) {
      setTopUpError(err.message || "Impossibile ricaricare il wallet.");
    } finally {
      setTopUpLoading(false);
    }
  }

  // Freeze/unfreeze login (SUPER_ADMIN only, see users/router.py)
  const [freezeLoadingId, setFreezeLoadingId] = useState<string | null>(null);
  const [freezeError, setFreezeError] = useState<string | null>(null);

  async function handleToggleFreeze(userId: string, currentlyFrozen: boolean) {
    setFreezeLoadingId(userId);
    setFreezeError(null);
    try {
      const res = await fetch(`/api/proxy/users/${userId}/${currentlyFrozen ? "unfreeze" : "freeze"}`, { method: "PATCH" });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      await queryClient.invalidateQueries({ queryKey: ["admin", "customers"] });
    } catch (err: any) {
      setFreezeError(err.message || "Impossibile aggiornare lo stato dell'account.");
    } finally {
      setFreezeLoadingId(null);
    }
  }

  const [editingCustomer, setEditingCustomer] = useState<CustomerRead | null>(null);
  const [editEmail, setEditEmail] = useState("");
  const [editPhone, setEditPhone] = useState("");
  const [editPec, setEditPec] = useState("");
  const [editFirstName, setEditFirstName] = useState("");
  const [editLastName, setEditLastName] = useState("");
  const [editCompanyName, setEditCompanyName] = useState("");
  const [editFiscalCode, setEditFiscalCode] = useState("");
  const [editVatNumber, setEditVatNumber] = useState("");
  const [editLoading, setEditLoading] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);
  const [editPhotoUrl, setEditPhotoUrl] = useState<string | null>(null);

  const { data: editingDetail } = useQuery({
    queryKey: ["admin", "customers", "detail", editingCustomer?.id],
    queryFn: () => fetchCustomerDetail(editingCustomer!.id),
    enabled: !!editingCustomer,
  });
  const [reassignAgentId, setReassignAgentId] = useState("");
  const [reassignReason, setReassignReason] = useState("");
  const [reassignLoading, setReassignLoading] = useState(false);
  const [reassignError, setReassignError] = useState<string | null>(null);
  const [reassignSuccess, setReassignSuccess] = useState(false);

  async function handleReassign(e: React.FormEvent) {
    e.preventDefault();
    if (!editingCustomer || !reassignAgentId) return;
    setReassignLoading(true);
    setReassignError(null);
    try {
      const res = await fetch(`/api/proxy/customers/${editingCustomer.id}/reassign-promoter`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ new_agent_id: reassignAgentId, reason: reassignReason }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      setReassignSuccess(true);
      setReassignAgentId("");
      setReassignReason("");
      await queryClient.invalidateQueries({ queryKey: ["admin", "customers", "detail", editingCustomer.id] });
      setTimeout(() => setReassignSuccess(false), 3000);
    } catch (err: any) {
      setReassignError(err.message || "Impossibile riassegnare il promoter.");
    } finally {
      setReassignLoading(false);
    }
  }

  function openView(id: string) {
    setTopUpAmount("");
    setTopUpNote("");
    setTopUpError(null);
    setTopUpSuccess(false);
    topUpKeyRef.current = crypto.randomUUID();
    setViewingId(id);
  }

  function openEdit(c: CustomerRead) {
    setEditEmail(c.email);
    setEditPhone(c.phone ?? "");
    setEditPec(c.pec ?? "");
    setEditFiscalCode(c.fiscal_code ?? "");
    setEditVatNumber(c.vat_number ?? "");
    const parts = c.display_name.trim().split(/\s+/);
    if (PRIVATE_LIKE.has(c.kind)) {
      setEditFirstName(parts.slice(0, -1).join(" ") || parts[0] || "");
      setEditLastName(parts.length > 1 ? parts[parts.length - 1]! : "");
      setEditCompanyName("");
    } else {
      setEditFirstName("");
      setEditLastName("");
      setEditCompanyName(c.display_name);
    }
    setEditError(null);
    setEditPhotoUrl(c.photo_url);
    setReassignAgentId("");
    setReassignReason("");
    setReassignError(null);
    setEditingCustomer(c);
  }

  async function handleEditSave(e: React.FormEvent) {
    e.preventDefault();
    if (!editingCustomer) return;
    setEditLoading(true);
    setEditError(null);
    try {
      const res = await fetch(`/api/proxy/customers/${editingCustomer.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: editEmail,
          phone: editPhone || null,
          pec: editPec || null,
          fiscal_code: editFiscalCode || null,
          vat_number: editVatNumber || null,
          first_name: PRIVATE_LIKE.has(editingCustomer.kind) ? editFirstName : null,
          last_name: PRIVATE_LIKE.has(editingCustomer.kind) ? editLastName : null,
          company_name: PRIVATE_LIKE.has(editingCustomer.kind) ? null : editCompanyName,
        }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      setEditingCustomer(null);
      await queryClient.invalidateQueries({ queryKey: ["admin", "customers"] });
    } catch (err: any) {
      setEditError(err.message || "Impossibile salvare le modifiche.");
    } finally {
      setEditLoading(false);
    }
  }

  // Pratica opened right after registering a customer, or from "Attiva contratti".
  const [wizardFor, setWizardFor] = useState<{ customer: CustomerRead; producer: string | null } | null>(null);
  const [loginLoadingId, setLoginLoadingId] = useState<string | null>(null);
  const [loginError, setLoginError] = useState<string | null>(null);

  async function handleCreateLogin(c: CustomerRead) {
    if (!window.confirm(`Creare l'accesso per ${c.display_name} e inviare a ${c.email} l'email per impostare la password?`)) return;
    setLoginLoadingId(c.id);
    setLoginError(null);
    try {
      const res = await fetch(`/api/proxy/customers/${c.id}/account`, { method: "POST" });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      await queryClient.invalidateQueries({ queryKey: ["admin", "customers"] });
    } catch (err: any) {
      setLoginError(err.message || "Impossibile creare l'accesso.");
    } finally {
      setLoginLoadingId(null);
    }
  }

  const filtered = (customers ?? []).filter(
    (c) =>
      (!activeOnly || customerIdsWithActiveContract.has(c.id)) &&
      (c.display_name.toLowerCase().includes(search.toLowerCase()) ||
        c.email.toLowerCase().includes(search.toLowerCase()))
  );

  // Pages the filtered list. The CSV export uses the full filtered set, not
  // just the visible page.
  const pagination = usePagination(filtered);

  const handleExportCsv = () => {
    downloadCsv(
      `clienti_${new Date().toISOString().slice(0, 10)}`,
      ["ID", "Nome", "Tipologia", "Email", "Telefono", "Codice Fiscale", "Partita IVA", "Ha un contratto attivo"],
      filtered.map((c) => [
        c.id, c.display_name, c.kind, c.email, c.phone ?? "", c.fiscal_code ?? "", c.vat_number ?? "",
        customerIdsWithActiveContract.has(c.id) ? "Sì" : "No",
      ])
    );
  };

  const allCustomers = customers ?? [];
  const withActive = allCustomers.filter((c) => customerIdsWithActiveContract.has(c.id)).length;
  const withoutLogin = allCustomers.filter((c) => !c.user_id).length;
  const frozen = allCustomers.filter((c) => c.user_status === "FROZEN").length;

  return (
    <div className="space-y-6">
      {customers !== undefined && (
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4 stagger">
          <div style={{ "--i": 0 } as React.CSSProperties}>
            <KpiTile label="Clienti" value={allCustomers.length} hint="in anagrafica" active={!activeOnly} onClick={() => setActiveOnly(false)} />
          </div>
          <div style={{ "--i": 1 } as React.CSSProperties}>
            <KpiTile label="Con contratto attivo" value={withActive} hint={allCustomers.length ? `${Math.round((withActive / allCustomers.length) * 100)}% del totale` : "—"} active={activeOnly} onClick={() => setActiveOnly(true)} />
          </div>
          <div style={{ "--i": 2 } as React.CSSProperties}>
            <KpiTile label="Senza accesso" value={withoutLogin} hint="non possono pagare" />
          </div>
          <div style={{ "--i": 3 } as React.CSSProperties}>
            <KpiTile label="Congelati" value={frozen} hint="accesso bloccato" />
          </div>
        </div>
      )}

      <div className="flex flex-col lg:flex-row gap-4 lg:items-center justify-between">
        <div className="flex flex-col sm:flex-row gap-3 sm:items-center">
          <div className="w-full sm:w-72 relative">
            <input
              type="text"
              placeholder="Cerca cliente..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full rounded-xl field pl-10 pr-4 py-2 text-xs focus:border-brand-500"
            />
            <svg className="w-4 h-4 text-surface-400 absolute left-3 top-2.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
          </div>
          <div className="subnav">
            <button onClick={() => setActiveOnly(false)} data-active={!activeOnly} className="subnav-pill">Tutti</button>
            <button onClick={() => setActiveOnly(true)} data-active={activeOnly} className="subnav-pill">Solo con contratto attivo</button>
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <button onClick={handleExportCsv} className="act !h-10 !px-4">
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
            </svg>
            CSV
          </button>
          <button onClick={() => setShowCreate(true)} className="act act-primary !h-10 !px-5">
            + Nuovo Cliente
          </button>
        </div>
      </div>

      {loadError && <p className="text-sm text-danger-400">Impossibile caricare i clienti.</p>}
      {freezeError && <p className="text-sm text-danger-400">{freezeError}</p>}
      {loginError && <p className="text-sm text-danger-400">{loginError}</p>}

      <div className="panel rounded-3xl p-4 md:p-6">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr>
                <th className="px-4 py-3">Intestatario</th>
                <th className="px-4 py-3">Recapiti</th>
                <th className="px-4 py-3">Profilo</th>
                <th className="px-4 py-3">Account</th>
                <th className="px-4 py-3"><span className="sr-only">Azioni</span></th>
              </tr>
            </thead>
            <tbody className="text-surface-300">
              {customers === undefined ? (
                <tr>
                  <td colSpan={5} className="px-4 py-8 text-center text-surface-400">Caricamento...</td>
                </tr>
              ) : filtered.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-4 py-12">
                    <div className="flex flex-col items-center gap-2 text-center">
                      <svg viewBox="0 0 24 24" className="h-8 w-8 text-accent-300 float-soft" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
                        <path d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" strokeLinejoin="round" />
                      </svg>
                      <span className="text-sm font-semibold text-surface-200">Nessun cliente trovato.</span>
                    </div>
                  </td>
                </tr>
              ) : (
                pagination.pageItems.map((c) => (
                  <tr key={c.id}>
                    <td className="px-4 py-3">
                      <Identity name={c.display_name} icon={customerPhoto(c.photo_url)} detail={`iscritto il ${fmtDate(c.created_at)}`} />
                    </td>
                    <td className="px-4 py-3">
                      <Stack title={c.email} detail={c.phone ?? "nessun telefono"} className="max-w-[240px]" />
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex flex-col items-start gap-1.5">
                        <Chip tone="accent">{KIND_LABELS[c.kind] ?? c.kind}</Chip>
                        {customerIdsWithActiveContract.has(c.id) && <Chip tone="ok">contratto attivo</Chip>}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      {!c.user_id ? (
                        <Chip tone="warn" live>Senza accesso</Chip>
                      ) : (
                        <div className="flex flex-wrap items-center gap-1.5">
                          <span title={c.email_verified ? "Email verificata" : "Email non verificata"}>
                            <Chip tone={c.email_verified ? "ok" : "bad"}>Email {c.email_verified ? "✓" : "✗"}</Chip>
                          </span>
                          <span title={c.privacy_accepted ? "Privacy accettata" : "Privacy non accettata"}>
                            <Chip tone={c.privacy_accepted ? "ok" : "bad"}>Privacy {c.privacy_accepted ? "✓" : "✗"}</Chip>
                          </span>
                          {c.user_status === "FROZEN" && <Chip tone="info">Congelato</Chip>}
                        </div>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <RowActions>
                        {c.user_id ? (
                          <button
                            onClick={() => setWizardFor({ customer: c, producer: null })}
                            title="Attiva contratti per questo cliente"
                            className="act act-primary whitespace-nowrap"
                          >
                            + Contratti
                          </button>
                        ) : (
                          <button
                            onClick={() => handleCreateLogin(c)}
                            disabled={loginLoadingId === c.id}
                            title="Il cliente non ha un accesso: senza, non può pagare i contratti"
                            className="act !text-warn-400 whitespace-nowrap"
                          >
                            {loginLoadingId === c.id ? "Creazione..." : "Crea accesso"}
                          </button>
                        )}
                        <button onClick={() => openView(c.id)} title="Mostra dettagli" aria-label="Mostra dettagli" className="act !px-2">
                          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                          </svg>
                        </button>
                        <button onClick={() => openEdit(c)} title="Modifica cliente" aria-label="Modifica cliente" className="act !px-2">
                          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                          </svg>
                        </button>
                        {isSuperAdmin && c.user_id && (
                          <button
                            onClick={() => handleToggleFreeze(c.user_id!, c.user_status === "FROZEN")}
                            disabled={freezeLoadingId === c.user_id}
                            title={c.user_status === "FROZEN" ? "Riattiva account" : "Congela account (blocca l'accesso)"}
                            aria-label={c.user_status === "FROZEN" ? "Riattiva account" : "Congela account"}
                            className={`act !px-2 ${c.user_status === "FROZEN" ? "!text-success-400" : "!text-info-400"}`}
                          >
                            {c.user_status === "FROZEN" ? (
                              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 11V7a4 4 0 118 0m-4 8v2m-6 2h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2z" />
                              </svg>
                            ) : (
                              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                              </svg>
                            )}
                          </button>
                        )}
                      </RowActions>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
        <div className="px-2 pt-3">
          <Pagination {...pagination} label="clienti" />
        </div>
      </div>

      {wizardFor && (
        <ContractRequestWizard
          customer={{
            id: wizardFor.customer.id,
            kind: wizardFor.customer.kind,
            email: wizardFor.customer.email,
            firstName: wizardFor.customer.first_name,
            lastName: wizardFor.customer.last_name,
            pec: wizardFor.customer.pec,
          }}
          producerAgentId={wizardFor.producer}
          onClose={() => setWizardFor(null)}
        />
      )}

      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-fade-in">
          <div className="w-full max-w-lg panel rounded-3xl p-6 md:p-7 border-white/10 bg-surface-950 pop max-h-[90vh] overflow-y-auto">
            <div className="flex items-start justify-between mb-5">
              <div>
                <div className="kpi-label">Anagrafica</div>
                <h3 className="mt-0.5 text-xl font-black tracking-tight text-white">Nuovo Cliente</h3>
              </div>
              <button onClick={() => setShowCreate(false)} aria-label="Chiudi" className="act !h-9 !w-9 !p-0 justify-center">
                <CloseIcon />
              </button>
            </div>

            <p className="text-xs text-surface-400 mb-4">
              Il cliente riceve l&apos;email per impostare la password: così potrà pagare i contratti che attivi per lui.
            </p>
            <NewCustomerForm
              mode="admin"
              submitLabel="Registra e attiva i contratti"
              onCancel={() => setShowCreate(false)}
              onCreated={async (customer, promoterAgentId) => {
                setShowCreate(false);
                await queryClient.invalidateQueries({ queryKey: ["admin", "customers"] });
                setWizardFor({ customer, producer: promoterAgentId });
              }}
            />
          </div>
        </div>
      )}

      {viewingId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-fade-in">
          <div className="w-full max-w-lg panel rounded-3xl p-6 md:p-7 border-white/10 bg-surface-950 pop max-h-[90vh] overflow-y-auto">
            <div className="flex items-start justify-between mb-5">
              <div>
                <div className="kpi-label">Scheda cliente</div>
                <h3 className="mt-0.5 text-xl font-black tracking-tight text-white">Dettagli Cliente</h3>
              </div>
              <button onClick={() => setViewingId(null)} aria-label="Chiudi" className="act !h-9 !w-9 !p-0 justify-center">
                <CloseIcon />
              </button>
            </div>

            {viewError && <p className="text-sm text-danger-400">Impossibile caricare i dettagli.</p>}
            {!viewingDetail && !viewError && <p className="text-sm text-surface-400 text-center py-8">Caricamento...</p>}

            {viewingDetail && (
              <div className="space-y-5 text-sm">
                <div className="flex flex-wrap items-center gap-3">
                  <Identity name={viewingDetail.display_name} detail={<IdTag id={viewingDetail.id} />} />
                  <Chip tone="accent">{KIND_LABELS[viewingDetail.kind] ?? viewingDetail.kind}</Chip>
                </div>

                <div className="grid grid-cols-2 gap-4 p-4 rounded-2xl bg-white/5 border border-white/10">
                  <div>
                    <span className="kpi-label">Email</span>
                    <p className="text-surface-100 break-all">{viewingDetail.email}</p>
                  </div>
                  <div>
                    <span className="kpi-label">Telefono</span>
                    <p className="text-surface-100">{viewingDetail.phone ?? "—"}</p>
                  </div>
                  <div>
                    <span className="kpi-label">PEC</span>
                    <p className="text-surface-100 break-all">{viewingDetail.pec ?? "—"}</p>
                  </div>
                  <div>
                    <span className="kpi-label">Codice Fiscale</span>
                    <p className="font-mono text-xs text-surface-100">{viewingDetail.fiscal_code ?? "—"}</p>
                  </div>
                  <div>
                    <span className="kpi-label">Partita IVA</span>
                    <p className="font-mono text-xs text-surface-100">{viewingDetail.vat_number ?? "—"}</p>
                  </div>
                </div>

                <div>
                  <p className="kpi-label mb-1">Contratti</p>
                  {customerContracts.length === 0 ? (
                    <p className="text-xs text-surface-400">Nessun contratto per questo cliente.</p>
                  ) : (
                    <div className="overflow-x-auto">
                      <table className="w-full text-left text-xs">
                        <thead>
                          <tr>
                            <th className="px-3 py-2">Offerta</th>
                            <th className="px-3 py-2">Situazione</th>
                            <th className="px-3 py-2">Scade</th>
                          </tr>
                        </thead>
                        <tbody className="text-surface-300">
                          {customerContracts.map((c) => (
                            <Fragment key={c.id}>
                              <tr onClick={() => setExpandedContractId(expandedContractId === c.id ? null : c.id)} className="cursor-pointer">
                                <td className="px-3 py-2.5">
                                  <Stack title={c.product_name ?? "Prodotto"} detail={c.supply_point_label ?? undefined} className="max-w-[180px]" />
                                </td>
                                <td className="px-3 py-2.5">
                                  <Chip tone={contractStatusTone(c.status)} live={contractStatusTone(c.status) === "warn"}>
                                    {CONTRACT_STATUS_LABELS[c.status] ?? c.status}
                                  </Chip>
                                </td>
                                <td className="px-3 py-2.5 whitespace-nowrap">
                                  {c.expires_at ? fmtDate(c.expires_at) : "—"}
                                </td>
                              </tr>
                              {expandedContractId === c.id && (
                                <tr>
                                  <td colSpan={3} className="px-4 py-3 text-surface-300 space-y-1">
                                    <div><span className="text-surface-400">Creato:</span> {fmtDate(c.created_at)}</div>
                                    {c.activated_at && (
                                      <div><span className="text-surface-400">Attivato:</span> {fmtDate(c.activated_at)}</div>
                                    )}
                                    {c.notes && <div><span className="text-surface-400">Note:</span> {c.notes}</div>}
                                    <div><IdTag id={c.id} /></div>
                                  </td>
                                </tr>
                              )}
                            </Fragment>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>

                {viewingDetail.addresses.length > 0 && (
                  <div>
                    <p className="kpi-label mb-2">Indirizzi</p>
                    <div className="space-y-2">
                      {viewingDetail.addresses.map((a) => (
                        <div key={a.id} className="p-3 rounded-2xl bg-white/5 border border-white/10 text-xs text-surface-300">
                          {a.street}, {a.postal_code} {a.city} ({a.province}) — {a.country}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {viewingDetail.supply_points.length > 0 && (
                  <div>
                    <p className="kpi-label mb-2">Punti di Fornitura</p>
                    <div className="space-y-2">
                      {viewingDetail.supply_points.map((sp) => (
                        <div key={sp.id} className="p-3 rounded-2xl bg-white/5 border border-white/10 text-xs text-surface-300">
                          <div className="flex items-center justify-between">
                            <span className="font-semibold text-white">{sp.label ?? sp.energy_type}</span>
                            <span className="font-mono text-[10px] text-surface-400">{sp.pod_code ?? sp.pdr_code ?? "—"}</span>
                          </div>
                          <div className="text-[10px] text-surface-400 mt-0.5">{sp.energy_type}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {viewingDetail.user_id && features.wallet && (
                  <div>
                    <p className="kpi-label mb-2">Wallet</p>
                    <div className="p-4 rounded-2xl bg-white/5 border border-white/10 space-y-3">
                      {viewingWallet === undefined ? (
                        <p className="text-xs text-surface-400">Caricamento...</p>
                      ) : viewingWallet === null ? (
                        <p className="text-xs text-surface-400">Nessun wallet ancora -- verrà creato alla prima ricarica.</p>
                      ) : (
                        <div className="flex items-center justify-between">
                          <div>
                            <span className="kpi-label">Saldo</span>
                            <p className="kpi-value !text-3xl mt-1">{euro(viewingWallet.balance_cents)}</p>
                          </div>
                          <span className="tag-id">{viewingWallet.address}</span>
                        </div>
                      )}

                      <form onSubmit={handleTopUp} className="flex items-end gap-2 pt-2 border-t border-white/5">
                        <div className="space-y-1 flex-1">
                          <label className="kpi-label block">Importo (EUR)</label>
                          <input
                            required
                            inputMode="decimal"
                            value={topUpAmount}
                            onChange={(e) => setTopUpAmount(e.target.value)}
                            placeholder="0,00"
                            className="w-full rounded-lg field px-3 py-1.5 text-sm focus:border-brand-500"
                          />
                        </div>
                        <div className="space-y-1 flex-1">
                          <label className="kpi-label block">Nota (opzionale)</label>
                          <input
                            value={topUpNote}
                            onChange={(e) => setTopUpNote(e.target.value)}
                            placeholder="Cashback ordine..."
                            className="w-full rounded-lg field px-3 py-1.5 text-sm focus:border-brand-500"
                          />
                        </div>
                        <button type="submit" disabled={topUpLoading} className="act act-primary !h-[34px] shrink-0">
                          {topUpLoading ? "..." : "Ricarica"}
                        </button>
                      </form>
                      {topUpError && (
                        <div className="p-2 rounded-lg bg-danger-500/10 border border-danger-500/20 text-danger-400 text-xs">{topUpError}</div>
                      )}
                      {topUpSuccess && (
                        <div className="p-2 rounded-lg bg-success-500/10 border border-success-500/20 text-success-400 text-xs">Wallet ricaricato con successo.</div>
                      )}
                    </div>
                  </div>
                )}

                <p className="font-mono text-[10px] text-surface-400 pt-2 border-t border-white/10">{viewingDetail.id}</p>
              </div>
            )}
          </div>
        </div>
      )}

      {editingCustomer && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-fade-in">
          <div className="w-full max-w-lg panel rounded-3xl p-6 md:p-7 border-white/10 bg-surface-950 pop max-h-[90vh] overflow-y-auto">
            <div className="flex items-start justify-between mb-5">
              <div>
                <div className="kpi-label">Anagrafica</div>
                <h3 className="mt-0.5 text-xl font-black tracking-tight text-white">Modifica Cliente</h3>
              </div>
              <button onClick={() => setEditingCustomer(null)} aria-label="Chiudi" className="act !h-9 !w-9 !p-0 justify-center">
                <CloseIcon />
              </button>
            </div>

            <div className="mb-5 pb-5 border-b border-white/5">
              <label className="kpi-label block mb-2">Foto profilo</label>
              <PhotoUpload
                currentUrl={editPhotoUrl}
                uploadPath={`customers/${editingCustomer.id}/photo`}
                onUploaded={(url) => {
                  setEditPhotoUrl(url);
                  queryClient.invalidateQueries({ queryKey: ["admin", "customers"] });
                }}
                alt={editingCustomer.display_name}
              />
            </div>

            <form onSubmit={handleEditSave} className="space-y-4">
              {PRIVATE_LIKE.has(editingCustomer.kind) ? (
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-1">
                    <label className="kpi-label block">Nome</label>
                    <input required value={editFirstName} onChange={(e) => setEditFirstName(e.target.value)}
                      className="w-full rounded-xl field px-3 py-2 text-sm focus:border-brand-500" />
                  </div>
                  <div className="space-y-1">
                    <label className="kpi-label block">Cognome</label>
                    <input required value={editLastName} onChange={(e) => setEditLastName(e.target.value)}
                      className="w-full rounded-xl field px-3 py-2 text-sm focus:border-brand-500" />
                  </div>
                </div>
              ) : (
                <div className="space-y-1">
                  <label className="kpi-label block">Ragione sociale</label>
                  <input required value={editCompanyName} onChange={(e) => setEditCompanyName(e.target.value)}
                    className="w-full rounded-xl field px-3 py-2 text-sm focus:border-brand-500" />
                </div>
              )}

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1">
                  <label className="kpi-label block">Email</label>
                  <input required type="email" value={editEmail} onChange={(e) => setEditEmail(e.target.value)}
                    className="w-full rounded-xl field px-3 py-2 text-sm focus:border-brand-500" />
                </div>
                <div className="space-y-1">
                  <label className="kpi-label block">Telefono</label>
                  <input value={editPhone} onChange={(e) => setEditPhone(e.target.value)}
                    className="w-full rounded-xl field px-3 py-2 text-sm focus:border-brand-500" />
                </div>
              </div>

              <div className="space-y-1">
                <label className="kpi-label block">PEC</label>
                <input type="email" value={editPec} onChange={(e) => setEditPec(e.target.value)}
                  placeholder="nome@pec.it"
                  className="w-full rounded-xl field px-3 py-2 text-sm focus:border-brand-500" />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1">
                  <label className="kpi-label block">Codice Fiscale</label>
                  <input value={editFiscalCode} onChange={(e) => setEditFiscalCode(e.target.value)}
                    className="w-full rounded-xl field px-3 py-2 text-sm focus:border-brand-500" />
                </div>
                <div className="space-y-1">
                  <label className="kpi-label block">Partita IVA</label>
                  <input value={editVatNumber} onChange={(e) => setEditVatNumber(e.target.value)}
                    className="w-full rounded-xl field px-3 py-2 text-sm focus:border-brand-500" />
                </div>
              </div>

              {editError && (
                <div className="p-3 rounded-lg bg-danger-500/10 border border-danger-500/20 text-danger-400 text-xs">{editError}</div>
              )}

              <div className="flex justify-end gap-3 mt-4">
                <button type="button" onClick={() => setEditingCustomer(null)} className="act !h-10 !px-4">
                  Annulla
                </button>
                <button type="submit" disabled={editLoading} className="act act-primary !h-10 !px-4">
                  {editLoading ? "Salvataggio..." : "Salva Modifiche"}
                </button>
              </div>
            </form>

            <div className="mt-6 pt-5 border-t border-white/5">
              <label className="kpi-label block mb-2">Promoter di riferimento</label>
              <p className="text-xs text-surface-400 mb-3">
                Attualmente attribuito a: <span className="font-semibold text-white">{editingDetail?.current_promoter_name ?? "—"}</span>
              </p>
              <form onSubmit={handleReassign} className="space-y-3">
                <AgentPicker
                  required
                  allowEmpty={false}
                  value={reassignAgentId}
                  onChange={(id) => setReassignAgentId(id)}
                  excludeId={editingDetail?.current_promoter_agent_id ?? undefined}
                  placeholder="— Seleziona nuovo promoter —"
                  ariaLabel="Nuovo promoter"
                />
                <input
                  required
                  value={reassignReason}
                  onChange={(e) => setReassignReason(e.target.value)}
                  placeholder="Motivo della riassegnazione..."
                  className="w-full rounded-xl field px-3 py-2 text-sm focus:border-brand-500"
                />
                {reassignError && (
                  <div className="p-3 rounded-lg bg-danger-500/10 border border-danger-500/20 text-danger-400 text-xs">{reassignError}</div>
                )}
                {reassignSuccess && (
                  <div className="p-3 rounded-lg bg-success-500/10 border border-success-500/20 text-success-400 text-xs">Promoter riassegnato con successo.</div>
                )}
                <button type="submit" disabled={reassignLoading} className="act w-full justify-center !h-10">
                  {reassignLoading ? "Riassegnazione..." : "Riassegna Promoter"}
                </button>
              </form>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
