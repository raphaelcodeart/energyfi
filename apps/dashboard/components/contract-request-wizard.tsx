"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ContractDocumentsPanel, useRequestDocuments } from "@/components/contract-documents-panel";
import { ContractRequestPaymentPanel } from "@/components/contract-request-payment-panel";
import { FullScreenPanel } from "@/components/full-screen-panel";
import { ProductDetailModal } from "@/components/product-detail-modal";
import { friendlyApiError } from "@/lib/api-error";
import { ENERGY_POINT_LABELS, pointCode } from "@/lib/contract-status";
import { computePrice, formatEuroCents as euro, productAllowsCustomerKind } from "@/lib/product-audience";
import { PROVINCES } from "@/lib/provinces";
import type { ContractRequestDetailRead, ContractRequestPointRead, ProductCatalogRead } from "@/lib/types";

type Step = "data" | "documents" | "contracts" | "summary";

const STEPS: { key: Step; label: string }[] = [
  { key: "data", label: "Dati" },
  { key: "documents", label: "Documenti" },
  { key: "contracts", label: "Contratti" },
  { key: "summary", label: "Riepilogo" },
];

const MAX_POD = 50;
const BILLING_LABELS: Record<string, string> = { MONTHLY: "/mese", QUARTERLY: "/trimestre", ANNUAL: "/anno" };

const inputClass = "w-full rounded-xl field px-3 py-2.5 text-sm focus:border-brand-500";
const labelClass = "text-[10px] font-semibold text-surface-300 light:text-surface-600 uppercase block";
const primaryButton =
  "rounded-xl bg-gradient-to-r from-brand-600 to-accent-500 hover:from-brand-500 hover:to-accent-400 px-5 py-3 text-sm font-bold text-white shadow-lg shadow-brand-500/20 transition cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed";
const secondaryButton =
  "rounded-xl bg-white/10 light:bg-surface-900/5 hover:bg-white/20 light:hover:bg-surface-900/10 px-4 py-2.5 text-xs font-semibold text-white light:text-surface-700 transition cursor-pointer disabled:opacity-50";

async function fetchRequest(id: string): Promise<ContractRequestDetailRead> {
  const res = await fetch(`/api/proxy/contract-requests/${id}`);
  if (!res.ok) throw new Error(await friendlyApiError(res));
  return res.json();
}

async function fetchProducts(): Promise<ProductCatalogRead[]> {
  const res = await fetch("/api/proxy/products");
  if (!res.ok) throw new Error("Impossibile caricare il catalogo prodotti.");
  return res.json();
}

/** Where a reopened pratica resumes: the first step still to do. */
function resumeStepFor(request: ContractRequestDetailRead): Step {
  if (request.status !== "DRAFT") return "summary";
  if (!request.street || request.points.length === 0) return "data";
  if (request.points_without_package > 0) return "contracts";
  return "summary";
}

type AddressValue = { street: string; city: string; province: string; postal_code: string };

/**
 * "Attiva nuovo contratto": the activation pratica.
 * Holder, PEC, IBAN, address and the number of PODs are asked once up front,
 * and the pratica is created with that many PODs. After the identity
 * documents, each POD only needs its contract chosen. Each POD becomes its
 * own contract (own review, own commissions) while documents and payment are
 * handled once. No POD code is asked.
 * Progress is saved as it is filled in, so "Riprendi" resumes exactly here.
 * Used by customers for themselves and by promoters for a customer
 * (`customer` set); the promoter does everything except pay.
 */
export function ContractRequestWizard({
  requestId: initialRequestId,
  initialStep,
  initialProduct,
  customer,
  producerAgentId,
  customerKind,
  accountEmail,
  holder,
  onClose,
}: {
  requestId?: string;
  initialStep?: "documents" | "packages" | "summary";
  /** Contract chosen from the catalog: preselected for every POD, changeable per POD. */
  initialProduct?: ProductCatalogRead | null;
  /** Promoter mode: the customer this pratica is for. */
  customer?: { id: string; kind: string | null; email: string | null; firstName?: string | null; lastName?: string | null; pec?: string | null };
  /** Staff only: the promoter this pratica is attributed to. */
  producerAgentId?: string | null;
  customerKind?: string | null;
  accountEmail?: string;
  holder?: { firstName?: string | null; lastName?: string | null; pec?: string | null };
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const promoterMode = Boolean(customer);
  const [requestId, setRequestId] = useState<string | null>(initialRequestId ?? null);
  const [chosenStep, setChosenStep] = useState<Step | null>(
    initialStep === "packages" ? "contracts" : initialStep ?? (initialRequestId ? null : "data")
  );
  const [preview, setPreview] = useState<{ product: ProductCatalogRead; pointId: string | null } | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const { data: request, error: loadError } = useQuery({
    queryKey: ["contract-request", requestId],
    queryFn: () => fetchRequest(requestId!),
    enabled: Boolean(requestId),
  });
  const { data: products } = useQuery({ queryKey: ["customer", "products"], queryFn: fetchProducts });

  const kind = request?.customer_kind ?? customer?.kind ?? customerKind ?? null;
  const packages = (products ?? []).filter(
    (p) =>
      p.category === "INTERNAL" &&
      p.status === "ACTIVE" &&
      p.current_version?.status === "ACTIVE" &&
      productAllowsCustomerKind(p.customer_type, kind)
  );
  const step: Step | null = chosenStep ?? (request ? resumeStepFor(request) : null);

  function goTo(next: Step) {
    setActionError(null);
    setChosenStep(next);
  }

  /**
   * Every mutation returns the whole pratica, which replaces the cached copy so
   * the screen never mixes old and new state.
   */
  async function mutate(label: string, path: string, init: RequestInit): Promise<ContractRequestDetailRead | null> {
    setBusy(label);
    setActionError(null);
    try {
      const res = await fetch(`/api/proxy/contract-requests${path}`, {
        ...init,
        headers: init.body ? { "Content-Type": "application/json" } : undefined,
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      const detail = (await res.json()) as ContractRequestDetailRead;
      queryClient.setQueryData(["contract-request", detail.id], detail);
      queryClient.invalidateQueries({ queryKey: ["contract-requests"] });
      queryClient.invalidateQueries({ queryKey: ["customer", "contracts"] });
      return detail;
    } catch (err: any) {
      setActionError(err.message || "Operazione non riuscita.");
      return null;
    } finally {
      setBusy(null);
    }
  }

  const customerName = [customer?.firstName, customer?.lastName].filter(Boolean).join(" ") || "il cliente";
  const title = promoterMode
    ? requestId
      ? `Pratica per ${request?.holder_name || customerName}`
      : `Nuova pratica per ${customerName}`
    : request
      ? `Pratica ${request.code}`
      : "Attiva nuovo contratto";
  const liveTotal = (request?.points ?? []).reduce((sum, p) => sum + (p.gross_amount_cents ?? 0), 0);
  const isDraft = !request || request.status === "DRAFT";

  return (
    <FullScreenPanel
      eyebrow={request ? `Pratica ${request.code}` : "Attiva nuovo contratto"}
      title={title}
      onClose={onClose}
      subtitle={
        <div className="space-y-2">
          <div className="flex items-center gap-1 overflow-x-auto pb-0.5">
            {STEPS.map((s, i) => {
              const current = s.key === step;
              const reachable = Boolean(requestId) || s.key === "data";
              return (
                <button
                  key={s.key}
                  onClick={() => reachable && goTo(s.key)}
                  disabled={!reachable}
                  className={`flex items-center gap-1.5 px-2 py-1 rounded-lg shrink-0 transition ${
                    current ? "bg-brand-600/15" : reachable ? "hover:bg-white/5 cursor-pointer" : "opacity-50"
                  }`}
                >
                  <span
                    className={`w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold ${
                      current ? "bg-brand-600 text-white" : "bg-white/10 light:bg-surface-900/10 text-surface-400"
                    }`}
                  >
                    {i + 1}
                  </span>
                  <span className={`text-[11px] font-semibold ${current ? "text-white light:text-surface-900" : "text-surface-500"}`}>
                    {s.label}
                  </span>
                </button>
              );
            })}
          </div>
          {request && request.points.length > 0 && (
            <p className="text-[11px] text-surface-400 light:text-surface-500">
              {request.points.length} {request.points.length === 1 ? "contratto" : "contratti"}
              {liveTotal > 0 && <> · totale <strong className="text-brand-400 tabular-nums">{euro(liveTotal)}</strong></>}
            </p>
          )}
        </div>
      }
    >
      {loadError && <p className="text-sm text-danger-400">{(loadError as Error).message}</p>}
      {actionError && (
        <div className="mb-4 p-3 rounded-xl bg-danger-500/10 border border-danger-500/20 text-danger-400 text-xs">{actionError}</div>
      )}
      {step === null && !loadError && <div className="h-40 rounded-2xl bg-white/5 light:bg-surface-900/5 animate-pulse" />}

      {step === "data" && (
        <DataStep
          key={request?.id ?? "new"}
          request={request}
          defaults={{
            firstName: customer?.firstName ?? holder?.firstName ?? "",
            lastName: customer?.lastName ?? holder?.lastName ?? "",
            email: customer?.email ?? accountEmail ?? "",
            pec: customer?.pec ?? holder?.pec ?? "",
          }}
          promoterMode={promoterMode}
          busy={busy === "data"}
          onSubmit={async (body, count) => {
            if (request && request.status !== "DRAFT") {
              goTo("documents");
              return;
            }
            let detail: ContractRequestDetailRead | null;
            if (!request) {
              detail = await mutate("data", "", {
                method: "POST",
                body: JSON.stringify({
                  ...body,
                  points_count: count,
                  customer_id: customer?.id ?? null,
                  producer_agent_id: producerAgentId ?? null,
                  product_version_id: initialProduct?.current_version?.id ?? null,
                }),
              });
            } else {
              detail = await mutate("data", `/${request.id}`, { method: "PATCH", body: JSON.stringify(body) });
              if (detail && detail.points.length !== count) {
                detail = await mutate("data", `/${request.id}/points-count`, {
                  method: "PUT",
                  body: JSON.stringify({ count }),
                });
              }
            }
            if (detail) {
              setRequestId(detail.id);
              goTo("documents");
            }
          }}
        />
      )}

      {step === "documents" && request && (
        <div className="space-y-5">
          <div>
            <h3 className="text-sm font-bold text-white light:text-surface-900">Documenti d&apos;identità</h3>
            <p className="text-xs text-surface-400 light:text-surface-500 mt-1">
              Si caricano una volta sola e valgono per tutti i {request.points.length} contratti della pratica. Se hai
              un&apos;unica bolletta con tutti i punti, caricala qui. Puoi anche andare avanti e caricarli più tardi.
            </p>
          </div>
          <ContractDocumentsPanel requestId={request.id} />
          <div className="flex gap-2">
            <button onClick={() => goTo("data")} className={secondaryButton}>← Dati</button>
            <button onClick={() => goTo("contracts")} className={`flex-1 ${primaryButton}`}>
              Continua: scegli l'offerta per ogni contratto
            </button>
          </div>
        </div>
      )}

      {step === "contracts" && request && (
        <ContractsStep
          request={request}
          packages={packages}
          kind={kind}
          busy={busy}
          onPreview={(product, pointId) => setPreview({ product, pointId })}
          onChoose={(pointId, versionId) =>
            mutate(`package-${pointId}`, `/${request.id}/points/${pointId}/product`, {
              method: "PUT",
              body: JSON.stringify({ product_version_id: versionId }),
            })
          }
          onChooseForAll={(versionId) =>
            mutate("package-all", `/${request.id}/product`, {
              method: "PUT",
              body: JSON.stringify({ product_version_id: versionId }),
            })
          }
          onMoveAddress={(pointId, address) =>
            mutate(`address-${pointId}`, `/${request.id}/points/${pointId}/address`, {
              method: "PATCH",
              body: JSON.stringify(address),
            })
          }
          onBack={() => goTo("documents")}
          onNext={() => goTo("summary")}
        />
      )}

      {step === "summary" && request && (
        <SummaryStep
          request={request}
          promoterMode={promoterMode}
          busy={busy}
          onChooseContracts={() => goTo("contracts")}
          onSubmit={() => mutate("submit", `/${request.id}/submit`, { method: "POST" })}
          onCancelDraft={async () => {
            if (!window.confirm("Eliminare questa pratica in bozza?")) return;
            const detail = await mutate("cancel", `/${request.id}/cancel`, { method: "POST" });
            if (detail) onClose();
          }}
          onClose={onClose}
        />
      )}

      {preview && (
        <ProductDetailModal
          product={preview.product}
          customerKind={kind}
          ctaLabel={preview.pointId ? "Scegli per questo contratto" : "Chiudi"}
          onClose={() => setPreview(null)}
          onBuy={async (versionId) => {
            const target = preview.pointId;
            setPreview(null);
            if (target && request && isDraft) {
              await mutate(`package-${target}`, `/${request.id}/points/${target}/product`, {
                method: "PUT",
                body: JSON.stringify({ product_version_id: versionId }),
              });
            }
          }}
        />
      )}
    </FullScreenPanel>
  );
}

// --- 1. Details: holder, address, number of PODs ---

function AddressFields({ value, onChange }: { value: AddressValue; onChange: (value: AddressValue) => void }) {
  return (
    <>
      <div className="space-y-1">
        <label className={labelClass}>Indirizzo di fornitura</label>
        <input
          required
          value={value.street}
          onChange={(e) => onChange({ ...value, street: e.target.value })}
          placeholder="Via/Piazza e numero civico"
          className={inputClass}
        />
      </div>
      <div className="grid grid-cols-6 gap-2">
        <div className="col-span-3 space-y-1">
          <label className={labelClass}>Città</label>
          <input required value={value.city} onChange={(e) => onChange({ ...value, city: e.target.value })} className={inputClass} />
        </div>
        <div className="col-span-1 space-y-1">
          <label className={labelClass}>Prov.</label>
          <select
            required
            value={value.province}
            onChange={(e) => onChange({ ...value, province: e.target.value })}
            className="w-full rounded-xl field px-1.5 py-2.5 text-sm bg-surface-900 light:bg-white focus:border-brand-500"
          >
            <option value="" disabled>--</option>
            {PROVINCES.map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
        </div>
        <div className="col-span-2 space-y-1">
          <label className={labelClass}>CAP</label>
          <input
            required
            minLength={5}
            maxLength={5}
            value={value.postal_code}
            onChange={(e) => onChange({ ...value, postal_code: e.target.value.replace(/\D/g, "") })}
            className={inputClass}
          />
        </div>
      </div>
    </>
  );
}

function DataStep({
  request,
  defaults,
  promoterMode,
  busy,
  onSubmit,
}: {
  request: ContractRequestDetailRead | undefined;
  defaults: { firstName: string; lastName: string; email: string; pec: string };
  promoterMode: boolean;
  busy: boolean;
  onSubmit: (
    body: { holder_first_name: string; holder_last_name: string; email: string; pec: string | null; iban: string | null } & AddressValue,
    count: number
  ) => void;
}) {
  const readOnly = Boolean(request && request.status !== "DRAFT");
  const [firstName, setFirstName] = useState(request?.holder_first_name ?? defaults.firstName);
  const [lastName, setLastName] = useState(request?.holder_last_name ?? defaults.lastName);
  const [email, setEmail] = useState(request?.email ?? defaults.email);
  const [pec, setPec] = useState(request?.pec ?? defaults.pec);
  const [iban, setIban] = useState(request?.iban ?? "");
  const [address, setAddress] = useState<AddressValue>({
    street: request?.street ?? "",
    city: request?.city ?? "",
    province: request?.province ?? "",
    postal_code: request?.postal_code ?? "",
  });
  const [count, setCount] = useState(request?.points.length || 1);

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit(
          {
            holder_first_name: firstName.trim(),
            holder_last_name: lastName.trim(),
            email: email.trim(),
            pec: pec.trim() || null,
            iban: iban.replace(/\s+/g, "").toUpperCase() || null,
            ...address,
            province: address.province.toUpperCase(),
          },
          count
        );
      }}
      className="space-y-4"
    >
      <fieldset disabled={readOnly} className="space-y-4">
        <h3 className="text-sm font-bold text-white light:text-surface-900">Intestatario del contratto</h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div className="space-y-1">
            <label className={labelClass}>Nome</label>
            <input required value={firstName} onChange={(e) => setFirstName(e.target.value)} autoComplete="given-name" className={inputClass} />
          </div>
          <div className="space-y-1">
            <label className={labelClass}>Cognome</label>
            <input required value={lastName} onChange={(e) => setLastName(e.target.value)} autoComplete="family-name" className={inputClass} />
          </div>
        </div>
        <div className="space-y-1">
          <label className={labelClass}>Email</label>
          <input required type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="nome@esempio.it" className={inputClass} />
          <p className="text-[10px] text-surface-500">Email di riferimento per questi contratti, anche diversa da quella dell&apos;account.</p>
        </div>
        <div className="space-y-1">
          <label className={labelClass}>
            PEC <span className="normal-case font-normal text-surface-500">(facoltativa)</span>
          </label>
          <input type="email" value={pec} onChange={(e) => setPec(e.target.value)} placeholder="nome@pec.it" className={inputClass} />
        </div>
        <div className="space-y-1">
          <label className={labelClass}>
            IBAN per addebito{promoterMode && <span className="normal-case font-normal text-surface-500"> (facoltativo)</span>}
          </label>
          <input
            required={!promoterMode}
            value={iban}
            onChange={(e) => setIban(e.target.value.toUpperCase())}
            placeholder="IT60 X054 2811 1010 0000 0123 456"
            minLength={15}
            maxLength={42}
            className={`${inputClass} font-mono tracking-wide`}
          />
          <p className="text-[10px] text-surface-500">Potrai modificarlo in qualsiasi momento da “I miei Contratti”.</p>
        </div>

        <h3 className="text-sm font-bold text-white light:text-surface-900 pt-3">Punto di fornitura</h3>
        <AddressFields value={address} onChange={setAddress} />

        <div className="space-y-2 pt-3 border-t border-white/5 light:border-surface-200">
          <label className={labelClass}>Quanti contratti vuoi attivare?</label>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setCount((n) => Math.max(1, n - 1))}
              disabled={count <= 1}
              className="w-10 h-10 rounded-xl bg-white/5 light:bg-surface-900/5 border border-white/10 light:border-surface-300 text-lg font-bold text-white light:text-surface-900 hover:bg-white/10 cursor-pointer disabled:opacity-40"
            >
              −
            </button>
            <input
              type="number"
              min={1}
              max={MAX_POD}
              value={count}
              onChange={(e) => setCount(Math.min(MAX_POD, Math.max(1, Number(e.target.value) || 1)))}
              className="w-20 text-center rounded-xl field px-2 py-2.5 text-base font-bold tabular-nums focus:border-brand-500"
            />
            <button
              type="button"
              onClick={() => setCount((n) => Math.min(MAX_POD, n + 1))}
              disabled={count >= MAX_POD}
              className="w-10 h-10 rounded-xl bg-white/5 light:bg-surface-900/5 border border-white/10 light:border-surface-300 text-lg font-bold text-white light:text-surface-900 hover:bg-white/10 cursor-pointer disabled:opacity-40"
            >
              +
            </button>
          </div>
          <p className="text-[10px] text-surface-500">
            Ogni contratto è a sé: tra poco sceglierai quale offerta attivare su ciascuno.
          </p>
        </div>
      </fieldset>
      <button type="submit" disabled={busy} className={`w-full ${primaryButton}`}>
        {busy ? "Salvataggio..." : readOnly ? "Continua" : `Continua con ${count} ${count === 1 ? "contratto" : "contratti"}: documenti`}
      </button>
    </form>
  );
}

// --- 3. One contract per POD ---

function PackageOption({
  product,
  kind,
  selected,
  disabled,
  onChoose,
  onPreview,
}: {
  product: ProductCatalogRead;
  kind: string | null;
  selected: boolean;
  disabled: boolean;
  onChoose: () => void;
  onPreview: () => void;
}) {
  const v = product.current_version!;
  const price = computePrice(v.contract_net_amount_cents, v.vat_percentage, kind, { assumeBusinessWhenUnknown: false });
  return (
    <div
      className={`flex items-center gap-3 p-3 rounded-xl border transition ${
        selected ? "bg-brand-500/10 border-brand-500/50" : "bg-white/5 light:bg-white border-white/10 light:border-surface-200"
      }`}
    >
      <button onClick={onChoose} disabled={disabled} className="flex items-center gap-3 flex-1 min-w-0 text-left cursor-pointer disabled:cursor-default">
        <span className={`w-4 h-4 rounded-full border-2 shrink-0 ${selected ? "border-brand-500 bg-brand-500" : "border-surface-500"}`} />
        <span className="min-w-0">
          <span className="block text-sm font-semibold text-white light:text-surface-900 truncate">
            {v.name}
            {product.energy_type && ENERGY_POINT_LABELS[product.energy_type] && (
              <span className="ml-2 text-[10px] font-semibold text-surface-500 uppercase">{ENERGY_POINT_LABELS[product.energy_type]}</span>
            )}
          </span>
          <span className="block text-[11px] text-surface-400 light:text-surface-500">
            {euro(v.base_price_cents)}
            {BILLING_LABELS[v.billing_period] ?? ""}
            {v.contract_billing_periods > 1 ? ` × ${v.contract_billing_periods}` : ""} ={" "}
            <strong className="text-surface-300 light:text-surface-700">{euro(price.grossCents)}</strong>
            {price.vatCents > 0 ? " IVA incl." : ""}
            {v.contract_cashback_percentage > 0 ? ` · cashback ${v.contract_cashback_percentage}%` : ""}
          </span>
        </span>
      </button>
      <button onClick={onPreview} className="px-2.5 py-1 rounded-lg text-[11px] font-semibold text-brand-400 hover:bg-brand-500/10 cursor-pointer shrink-0">
        Anteprima
      </button>
    </div>
  );
}

function ContractsStep({
  request,
  packages,
  kind,
  busy,
  onPreview,
  onChoose,
  onChooseForAll,
  onMoveAddress,
  onBack,
  onNext,
}: {
  request: ContractRequestDetailRead;
  packages: ProductCatalogRead[];
  kind: string | null;
  busy: string | null;
  onPreview: (product: ProductCatalogRead, pointId: string | null) => void;
  onChoose: (pointId: string, versionId: string) => void;
  onChooseForAll: (versionId: string) => void;
  onMoveAddress: (pointId: string, address: AddressValue) => Promise<ContractRequestDetailRead | null>;
  onBack: () => void;
  onNext: () => void;
}) {
  const editable = request.status === "DRAFT";
  const [openPoint, setOpenPoint] = useState<string | null>(null);
  const [movingPoint, setMovingPoint] = useState<string | null>(null);
  const [bulkChoice, setBulkChoice] = useState("");
  const missing = request.points.filter((p) => !p.product_version_id).length;

  return (
    <div className="space-y-5">
      <div>
        <h3 className="text-sm font-bold text-white light:text-surface-900">Scegli l'offerta per ogni contratto</h3>
        <p className="text-xs text-surface-400 light:text-surface-500 mt-1">
          Ogni contratto è a sé: puoi scegliere offerte diverse. Apri “Anteprima” per leggerlo prima di
          sceglierlo.
        </p>
      </div>

      {editable && request.points.length > 1 && packages.length > 0 && (
        <div className="flex flex-col sm:flex-row gap-2 p-3 rounded-xl bg-white/5 light:bg-surface-900/5 border border-white/10 light:border-surface-200">
          <select
            value={bulkChoice}
            onChange={(e) => setBulkChoice(e.target.value)}
            className="flex-1 rounded-xl field px-3 py-2 text-xs bg-surface-900 light:bg-white"
          >
            <option value="">Stessa offerta per tutti i contratti…</option>
            {packages.map((p) => (
              <option key={p.id} value={p.current_version!.id}>{p.current_version!.name}</option>
            ))}
          </select>
          <button
            onClick={() => bulkChoice && onChooseForAll(bulkChoice)}
            disabled={!bulkChoice || busy === "package-all"}
            className={secondaryButton}
          >
            {busy === "package-all" ? "Applicazione..." : "Applica a tutti"}
          </button>
        </div>
      )}

      <div className="space-y-4">
        {request.points.map((point) => (
          <div key={point.id} className="p-4 rounded-2xl border border-white/10 light:border-surface-200 bg-surface-950/40 light:bg-white/70 space-y-3">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="text-sm font-bold text-white light:text-surface-900">
                  {pointCode(point)}
                  {point.energy_type && ENERGY_POINT_LABELS[point.energy_type] && (
                    <span className="ml-2 text-[10px] font-semibold text-surface-500 uppercase">{ENERGY_POINT_LABELS[point.energy_type]}</span>
                  )}
                </p>
                <p className="text-[11px] text-surface-400 light:text-surface-500 truncate">
                  {[point.street, point.city].filter(Boolean).join(", ")}
                  {editable && (
                    <button
                      onClick={() => setMovingPoint(movingPoint === point.id ? null : point.id)}
                      className="ml-2 font-semibold text-brand-400 hover:text-brand-300 cursor-pointer"
                    >
                      {movingPoint === point.id ? "Annulla" : "Indirizzo diverso?"}
                    </button>
                  )}
                </p>
              </div>
              {point.gross_amount_cents != null && (
                <span className="text-sm font-bold text-brand-400 tabular-nums shrink-0">{euro(point.gross_amount_cents)}</span>
              )}
            </div>

            {movingPoint === point.id && (
              <MoveAddressForm
                point={point}
                busy={busy === `address-${point.id}`}
                onSubmit={async (address) => {
                  if (await onMoveAddress(point.id, address)) setMovingPoint(null);
                }}
              />
            )}

            {packages.length === 0 ? (
              <p className="text-xs text-warn-400">Nessun contratto disponibile al momento.</p>
            ) : (
              <div className="space-y-2">
                {packages.map((product) => (
                  <PackageOption
                    key={product.id}
                    product={product}
                    kind={kind}
                    selected={point.product_version_id === product.current_version!.id}
                    disabled={!editable || busy === `package-${point.id}`}
                    onChoose={() => editable && onChoose(point.id, product.current_version!.id)}
                    onPreview={() => onPreview(product, editable ? point.id : null)}
                  />
                ))}
                {point.product_version_id && !packages.some((p) => p.current_version!.id === point.product_version_id) && (
                  <p className="text-[11px] text-surface-400">Contratto scelto: {point.product_name}</p>
                )}
              </div>
            )}

            <div className="pt-2 border-t border-white/5 light:border-surface-200">
              <button
                onClick={() => setOpenPoint(openPoint === point.id ? null : point.id)}
                className="text-xs font-semibold text-surface-300 light:text-surface-600 hover:text-brand-400 cursor-pointer"
              >
                {openPoint === point.id ? "▾" : "▸"} Allegati di questo contratto (bolletta, foto del contatore)
              </button>
              {openPoint === point.id && (
                <div className="mt-3">
                  <ContractDocumentsPanel contractId={point.id} onlyTypes={["UTILITY_BILL"]} />
                </div>
              )}
            </div>
          </div>
        ))}
      </div>

      <div className="flex gap-2">
        <button onClick={onBack} className={secondaryButton}>← Documenti</button>
        <button onClick={onNext} className={`flex-1 ${primaryButton}`}>
          {missing > 0 ? `Continua (${missing} ${missing === 1 ? "contratto" : "contratti"} senza offerta)` : "Continua: riepilogo"}
        </button>
      </div>
    </div>
  );
}

function MoveAddressForm({
  point,
  busy,
  onSubmit,
}: {
  point: ContractRequestPointRead;
  busy: boolean;
  onSubmit: (address: AddressValue) => void;
}) {
  const [address, setAddress] = useState<AddressValue>({
    street: point.street ?? "",
    city: point.city ?? "",
    province: point.province ?? "",
    postal_code: point.postal_code ?? "",
  });
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit({ ...address, province: address.province.toUpperCase() });
      }}
      className="space-y-2 p-3 rounded-xl border border-brand-500/25 bg-brand-500/5"
    >
      <AddressFields value={address} onChange={setAddress} />
      <button type="submit" disabled={busy} className="w-full rounded-xl bg-brand-600 hover:bg-brand-500 px-4 py-2 text-xs font-bold text-white cursor-pointer disabled:opacity-50">
        {busy ? "Salvataggio..." : "Salva l'indirizzo di questo contratto"}
      </button>
    </form>
  );
}

// --- 4. Summary, submission and payment ---

function SummaryStep({
  request,
  promoterMode,
  busy,
  onChooseContracts,
  onSubmit,
  onCancelDraft,
  onClose,
}: {
  request: ContractRequestDetailRead;
  promoterMode: boolean;
  busy: string | null;
  onChooseContracts: () => void;
  onSubmit: () => void;
  onCancelDraft: () => void;
  onClose: () => void;
}) {
  const { data: sharedDocs } = useRequestDocuments(request.id);
  const sharedMissing = (sharedDocs?.required ?? []).filter((r) => r.required !== false && r.document === null).length;
  const pointsMissingDocs = request.points.filter((p) => p.documents_missing > 0).length;
  const total = request.points.reduce((sum, p) => sum + (p.gross_amount_cents ?? 0), 0);
  const isDraft = request.status === "DRAFT";

  return (
    <div className="space-y-5">
      <div>
        <h3 className="text-sm font-bold text-white light:text-surface-900">{isDraft ? "Riepilogo della pratica" : "Pratica inviata"}</h3>
        <p className="text-xs text-surface-400 light:text-surface-500 mt-1">
          {isDraft
            ? `Controlla i contratti scelti. Inviando la pratica si aprono ${request.points.length} ${
                request.points.length === 1 ? "contratto" : "contratti indipendenti"
              }, ognuno verificato e attivato per conto suo.`
            : "Ogni contratto viene verificato dall'amministrazione per conto suo e si attiva appena i suoi documenti sono approvati."}
        </p>
      </div>

      <div className="p-3 rounded-xl bg-white/5 light:bg-surface-900/5 border border-white/10 light:border-surface-200 text-[11px] text-surface-400 light:text-surface-500">
        Intestatario: <strong className="text-surface-200 light:text-surface-800">{request.holder_name}</strong>
        {request.email ? ` · ${request.email}` : ""}
        {request.street ? ` · ${request.street}, ${request.postal_code} ${request.city} (${request.province})` : ""}
      </div>

      <div className="rounded-2xl border border-white/10 light:border-surface-200 divide-y divide-white/5 light:divide-surface-200 overflow-hidden">
        {request.points.map((point) => (
          <div key={point.id} className="flex items-center justify-between gap-3 px-4 py-3">
            <div className="min-w-0">
              <p className="text-sm font-semibold text-white light:text-surface-900">{pointCode(point)}</p>
              <p className={`text-[11px] ${point.product_name ? "text-surface-400 light:text-surface-500" : "text-warn-400"}`}>
                {point.product_name ?? "Contratto non ancora scelto"}
                {point.street && point.street !== request.street ? ` · ${point.street}, ${point.city}` : ""}
              </p>
            </div>
            <span className="text-sm font-semibold text-white light:text-surface-900 tabular-nums shrink-0">
              {point.gross_amount_cents != null ? euro(point.gross_amount_cents) : "—"}
            </span>
          </div>
        ))}
        <div className="flex items-center justify-between gap-3 px-4 py-3 bg-white/5 light:bg-surface-900/5">
          <span className="text-sm font-bold text-white light:text-surface-900">Totale</span>
          <span className="text-base font-extrabold text-brand-400 tabular-nums">{euro(total)}</span>
        </div>
      </div>

      {(sharedMissing > 0 || pointsMissingDocs > 0) && (
        <div className="p-3 rounded-xl bg-warn-500/10 border border-warn-500/20 text-warn-400 text-xs">
          Mancano ancora dei documenti
          {sharedMissing > 0 ? ` (${sharedMissing} d'identità)` : ""}
          {pointsMissingDocs > 0 ? ` (bolletta di ${pointsMissingDocs} ${pointsMissingDocs === 1 ? "contratto" : "contratti"})` : ""}. Puoi inviare e pagare lo stesso e
          caricarli dopo: ogni contratto si attiva quando i suoi documenti sono approvati.
        </div>
      )}

      {isDraft ? (
        <div className="space-y-2">
          {request.points_without_package > 0 ? (
            <button onClick={onChooseContracts} className={`w-full ${primaryButton}`}>
              Scegli l'offerta per i contratti mancanti
            </button>
          ) : (
            <button onClick={onSubmit} disabled={busy === "submit"} className={`w-full ${primaryButton}`}>
              {busy === "submit"
                ? "Invio in corso..."
                : `Invia la pratica (${request.points.length} ${request.points.length === 1 ? "contratto" : "contratti"})`}
            </button>
          )}
          <button onClick={onCancelDraft} disabled={busy === "cancel"} className="w-full text-xs text-surface-500 hover:text-danger-400 py-2 cursor-pointer">
            Elimina questa bozza
          </button>
        </div>
      ) : promoterMode ? (
        <div className="space-y-3">
          <div className="p-4 rounded-2xl bg-success-500/10 border border-success-500/20 text-success-400 text-sm">
            Pratica inviata. Il cliente può pagarla dal suo account, in “I miei Contratti”, anche prima che i documenti
            siano approvati.
          </div>
          <button onClick={onClose} className={`w-full ${secondaryButton}`}>Chiudi</button>
        </div>
      ) : (
        <ContractRequestPaymentPanel requestId={request.id} />
      )}
    </div>
  );
}
