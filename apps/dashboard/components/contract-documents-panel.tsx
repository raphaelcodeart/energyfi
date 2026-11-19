"use client";

import { useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { DocumentPreviewModal } from "@/components/document-preview-modal";
import { friendlyApiError } from "@/lib/api-error";

type DocumentRead = {
  id: string;
  /**
   * Exactly one is set: a document of one contract, or of its whole pratica
   * (which then counts for every point in it).
   */
  contract_id: string | null;
  contract_request_id: string | null;
  document_type: string;
  /** Extra attachments only: the uploader's label. */
  description: string | null;
  original_filename: string;
  content_type: string;
  size_bytes: number;
  uploaded_by_user_id: string;
  uploaded_by_role: string;
  uploaded_by_name: string | null;
  status: string;
  reviewed_by_user_id: string | null;
  reviewed_by_name: string | null;
  reviewed_at: string | null;
  review_note: string | null;
  created_at: string;
};

type RequiredDocumentStatus = {
  document_type: string;
  /**
   * False for an optional slot (e.g. the visura of a sole proprietorship).
   * Defaults to true when absent, as on the server.
   */
  required?: boolean;
  document: DocumentRead | null;
};

type ContractDocumentsRead = {
  contract_id?: string | null;
  contract_request_id?: string | null;
  required: RequiredDocumentStatus[];
  extra?: DocumentRead[];
};

const DOCUMENT_TYPE_LABELS: Record<string, string> = {
  IDENTITY: "Documento d'identità",
  FISCAL_CODE: "Codice fiscale",
  UTILITY_BILL: "Fattura luce/gas",
  CHAMBER_OF_COMMERCE: "Visura camerale",
  OTHER: "Documento aggiuntivo",
};

/** Plain-language description of each slot, shown under its title. */
const DOCUMENT_TYPE_HINTS: Record<string, string> = {
  IDENTITY: "Carta d'identità, patente o passaporto dell'intestatario, in corso di validità.",
  FISCAL_CODE: "Tessera sanitaria o codice fiscale dell'intestatario.",
  UTILITY_BILL: "Una bolletta recente della fornitura da attivare o cambiare.",
  CHAMBER_OF_COMMERCE: "Visura camerale dell'azienda, possibilmente non più vecchia di sei mesi.",
};

const STATUS_LABELS: Record<string, string> = {
  PENDING_REVIEW: "In attesa di verifica",
  APPROVED: "Approvato",
  REJECTED: "Respinto",
};

const ACCEPTED_CONTENT_TYPES = "application/pdf,image/jpeg,image/png";
const MIN_DESCRIPTION_LENGTH = 3;
const MAX_DESCRIPTION_LENGTH = 120;

function statusColor(status: string): string {
  if (status === "APPROVED") return "bg-success-500/10 text-success-400 border-success-500/20";
  if (status === "REJECTED") return "bg-danger-500/10 text-danger-400 border-danger-500/20";
  if (status === "MISSING") return "bg-white/5 light:bg-surface-900/5 text-surface-400 border-white/10 light:border-surface-300";
  return "bg-warn-500/10 text-warn-400 border-warn-500/20";
}

async function fetchDocuments(path: string): Promise<ContractDocumentsRead> {
  const res = await fetch(path);
  if (!res.ok) throw new Error("Impossibile caricare i documenti.");
  return res.json();
}

function documentsPath({ contractId, requestId }: { contractId?: string; requestId?: string }): string {
  return contractId
    ? `/api/proxy/contracts/${contractId}/documents`
    : `/api/proxy/contract-requests/${requestId}/documents`;
}

async function fetchDocumentUrl(documentId: string): Promise<string> {
  const res = await fetch(`/api/proxy/documents/${documentId}/url`);
  if (!res.ok) throw new Error("Impossibile aprire il documento.");
  const data = await res.json();
  return data.url;
}

/**
 * Count of the blocking documents present. Exported so the contract card
 * ("mancano 2 documenti") always agrees with this panel.
 */
export function missingRequiredCount(data: ContractDocumentsRead | undefined): number {
  if (!data) return 0;
  return data.required.filter((row) => row.required !== false && row.document === null).length;
}

export function useContractDocuments(contractId: string) {
  return useQuery({
    queryKey: ["documents", "contract", contractId],
    queryFn: () => fetchDocuments(documentsPath({ contractId })),
  });
}

/** Documents uploaded once for a whole pratica. */
export function useRequestDocuments(requestId: string) {
  return useQuery({
    queryKey: ["documents", "request", requestId],
    queryFn: () => fetchDocuments(documentsPath({ requestId })),
  });
}

/**
 * One contract's documents (`contractId`) or a pratica's shared ones
 * (`requestId`): same slots, upload and review.
 * `onlyTypes` narrows the slots for a single supply point screen, where
 * identity documents already live on the pratica.
 */
export function ContractDocumentsPanel({
  contractId,
  requestId,
  isStaff = false,
  onlyTypes,
}: {
  contractId?: string;
  requestId?: string;
  isStaff?: boolean;
  onlyTypes?: string[];
}) {
  const queryClient = useQueryClient();
  const contractQuery = useQuery({
    queryKey: ["documents", "contract", contractId],
    queryFn: () => fetchDocuments(documentsPath({ contractId })),
    enabled: Boolean(contractId),
  });
  const requestQuery = useQuery({
    queryKey: ["documents", "request", requestId],
    queryFn: () => fetchDocuments(documentsPath({ requestId })),
    enabled: !contractId && Boolean(requestId),
  });
  const { data: rawData, error, isLoading } = contractId ? contractQuery : requestQuery;
  const ownerKey = contractId ?? requestId ?? "";
  const data = rawData && onlyTypes
    ? { ...rawData, required: rawData.required.filter((row) => onlyTypes.includes(row.document_type)) }
    : rawData;

  const [uploadingType, setUploadingType] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [reviewingId, setReviewingId] = useState<string | null>(null);
  const [reviewNote, setReviewNote] = useState("");
  const [extraLabel, setExtraLabel] = useState("");
  const [addingExtra, setAddingExtra] = useState(false);
  const extraFileInput = useRef<HTMLInputElement>(null);
  const extraCameraInput = useRef<HTMLInputElement>(null);

  const trimmedExtraLabel = extraLabel.trim();
  const canPickExtraFile = trimmedExtraLabel.length >= MIN_DESCRIPTION_LENGTH;

  async function refresh() {
    // Contracts show their pratica's documents and pratica screens count what is
    // missing, so all of it is now stale.
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["documents"] }),
      queryClient.invalidateQueries({ queryKey: ["contract-request"] }),
      queryClient.invalidateQueries({ queryKey: ["contract-requests"] }),
    ]);
  }

  async function handleUpload(documentType: string, file: File, description?: string) {
    setUploadingType(documentType);
    setUploadError(null);
    try {
      const formData = new FormData();
      formData.append("document_type", documentType);
      if (description) formData.append("description", description);
      formData.append("file", file);
      const res = await fetch(documentsPath({ contractId, requestId }), { method: "POST", body: formData });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      await refresh();
      return true;
    } catch (err: any) {
      // Prefer the server's specific message (file too large, label too short).
      setUploadError(err?.message || `${DOCUMENT_TYPE_LABELS[documentType] ?? documentType}: caricamento fallito.`);
      return false;
    } finally {
      setUploadingType(null);
    }
  }

  async function handleExtraUpload(file: File) {
    const ok = await handleUpload("OTHER", file, trimmedExtraLabel);
    if (ok) {
      setExtraLabel("");
      setAddingExtra(false);
    }
  }

  // "Visualizza" opens a popup on this page, never a new tab, so the reviewer keeps their place.
  const [previewDoc, setPreviewDoc] = useState<DocumentRead | null>(null);

  async function handleReview(documentId: string, newStatus: "APPROVED" | "REJECTED") {
    try {
      const res = await fetch(`/api/proxy/documents/${documentId}/review`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: newStatus, review_note: reviewNote || null }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      setReviewingId(null);
      setReviewNote("");
      await refresh();
    } catch {
      setUploadError("Impossibile aggiornare lo stato del documento.");
    }
  }

  /** Staff-only approve/reject strip, shared by slot documents and extra attachments. */
  function reviewControls(doc: DocumentRead) {
    if (!isStaff || doc.status !== "PENDING_REVIEW") return null;
    return (
      <div className="mt-3 pt-3 border-t border-white/5 light:border-surface-200 space-y-2">
        {reviewingId === doc.id ? (
          <>
            <input
              value={reviewNote}
              onChange={(e) => setReviewNote(e.target.value)}
              placeholder="Nota (opzionale)..."
              className="w-full rounded-lg field px-3 py-1.5 text-xs focus:border-brand-500"
            />
            <div className="flex gap-2">
              <button
                onClick={() => handleReview(doc.id, "APPROVED")}
                className="px-3 py-1 rounded-lg bg-success-600/10 hover:bg-success-600/20 border border-success-500/20 text-success-400 text-xs font-semibold transition cursor-pointer"
              >
                Approva
              </button>
              <button
                onClick={() => handleReview(doc.id, "REJECTED")}
                className="px-3 py-1 rounded-lg bg-danger-600/10 hover:bg-danger-600/20 border border-danger-500/20 text-danger-400 text-xs font-semibold transition cursor-pointer"
              >
                Respingi
              </button>
              <button
                onClick={() => { setReviewingId(null); setReviewNote(""); }}
                className="px-3 py-1 rounded-lg bg-white/5 hover:bg-white/10 text-surface-400 text-xs font-semibold transition cursor-pointer"
              >
                Annulla
              </button>
            </div>
          </>
        ) : (
          <button
            onClick={() => setReviewingId(doc.id)}
            className="px-3 py-1 rounded-lg bg-white/5 light:bg-surface-900/5 hover:bg-white/10 border border-white/10 light:border-surface-300 text-surface-300 light:text-surface-600 text-xs font-semibold transition cursor-pointer"
          >
            Verifica documento
          </button>
        )}
      </div>
    );
  }

  if (isLoading) return <p className="text-sm text-surface-500">Caricamento documenti...</p>;
  if (error) return <p className="text-sm text-danger-400">Impossibile caricare i documenti.</p>;
  if (!data) return null;

  const extra = data.extra ?? [];
  const requiredRows = data.required.filter((row) => row.required !== false);
  const uploadedRequired = requiredRows.filter((row) => row.document !== null).length;
  const missing = requiredRows.length - uploadedRequired;

  return (
    <div className="space-y-3">
      {/* Summary of what is still missing */}
      <div
        className={`flex items-center justify-between gap-3 px-3.5 py-2.5 rounded-xl border text-xs ${
          missing === 0
            ? "bg-success-500/10 border-success-500/20 text-success-400"
            : "bg-warn-500/10 border-warn-500/20 text-warn-400"
        }`}
      >
        <span className="font-semibold">
          {missing === 0
            ? "Tutti i documenti obbligatori sono stati caricati."
            : missing === 1
              ? "Manca 1 documento obbligatorio."
              : `Mancano ${missing} documenti obbligatori.`}
        </span>
        <span className="font-bold tabular-nums shrink-0">
          {uploadedRequired}/{requiredRows.length}
        </span>
      </div>

      {uploadError && (
        <div className="p-3 rounded-lg bg-danger-500/10 border border-danger-500/20 text-danger-400 text-xs">{uploadError}</div>
      )}

      {data.required.map((row) => {
        const doc = row.document;
        const isRequired = row.required !== false;
        const inputId = `doc-upload-${ownerKey}-${row.document_type}`;
        // On a contract: a slot filled by its pratica's document.
        const inherited = Boolean(contractId && doc?.contract_request_id);
        return (
          <div
            key={row.document_type}
            className="p-3 rounded-xl bg-white/5 light:bg-surface-900/5 border border-white/5 light:border-surface-200"
          >
            <div className="flex items-center justify-between gap-3 flex-wrap">
              <div className="min-w-0">
                <p className="text-sm font-semibold text-white light:text-surface-900">
                  {DOCUMENT_TYPE_LABELS[row.document_type] ?? row.document_type}
                  {!isRequired && (
                    <span className="ml-2 text-[10px] font-semibold text-surface-500 uppercase tracking-wide">
                      Facoltativo
                    </span>
                  )}
                </p>
                {!doc && DOCUMENT_TYPE_HINTS[row.document_type] && (
                  <p className="text-[11px] text-surface-400 light:text-surface-500 mt-0.5">
                    {DOCUMENT_TYPE_HINTS[row.document_type]}
                  </p>
                )}
                {doc && (
                  <p className="text-[11px] text-surface-500 mt-0.5">
                    {doc.original_filename} · caricato da {doc.uploaded_by_name ?? "—"} il{" "}
                    {new Date(doc.created_at).toLocaleDateString("it-IT")}
                    {inherited && " · vale per tutti i punti della pratica"}
                  </p>
                )}
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${statusColor(doc?.status ?? "MISSING")}`}>
                  {doc ? STATUS_LABELS[doc.status] ?? doc.status : "Non caricato"}
                </span>
                {doc && (
                  <button
                    onClick={() => setPreviewDoc(doc)}
                    className="px-2.5 py-1 rounded-lg bg-white/5 light:bg-surface-900/5 hover:bg-white/10 border border-white/10 light:border-surface-300 text-surface-300 light:text-surface-600 text-xs font-semibold transition cursor-pointer"
                  >
                    Visualizza
                  </button>
                )}
                <input
                  type="file"
                  accept={ACCEPTED_CONTENT_TYPES}
                  id={inputId}
                  className="hidden"
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) handleUpload(row.document_type, file);
                    e.target.value = "";
                  }}
                />
                {/* A second picker that opens the camera directly, for photographing the ID or
                   bill; on a computer the browser opens the file picker. */}
                <input
                  type="file"
                  accept="image/jpeg,image/png"
                  capture="environment"
                  id={`${inputId}-camera`}
                  className="hidden"
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) handleUpload(row.document_type, file);
                    e.target.value = "";
                  }}
                />
                <label
                  htmlFor={`${inputId}-camera`}
                  title="Scatta una foto"
                  className="px-2.5 py-1 rounded-lg bg-white/5 light:bg-surface-900/5 hover:bg-white/10 border border-white/10 light:border-surface-300 text-surface-300 light:text-surface-600 text-xs font-semibold cursor-pointer transition inline-flex items-center gap-1"
                >
                  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 9a2 2 0 012-2h.93a2 2 0 001.664-.89l.812-1.22A2 2 0 0110.07 4h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0018.07 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9z" />
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 13a3 3 0 11-6 0 3 3 0 016 0z" />
                  </svg>
                  Foto
                </label>
                <label
                  htmlFor={inputId}
                  className="px-2.5 py-1 rounded-lg bg-brand-600/10 hover:bg-brand-600/20 border border-brand-500/20 text-brand-400 text-xs font-semibold cursor-pointer transition"
                >
                  {uploadingType === row.document_type
                    ? "Caricamento..."
                    : inherited
                      ? "Carica per questo punto"
                      : doc
                        ? "Sostituisci"
                        : "Carica"}
                </label>
              </div>
            </div>

            {doc && doc.review_note && (
              <p className="text-[11px] text-surface-400 light:text-surface-500 mt-2">
                <span className="font-semibold">Nota amministrazione:</span> {doc.review_note}
              </p>
            )}

            {doc && reviewControls(doc)}
          </div>
        );
      })}

      {/* --- Extra attachments ---
         Anything the fixed slots do not cover. Each is labelled by its uploader, so
         the label is asked for before the file picker opens. */}
      <div className="pt-1">
        <p className="text-xs font-semibold text-surface-400 light:text-surface-500 uppercase tracking-wider mb-2">
          Altri documenti allegati
        </p>

        {extra.length === 0 && !addingExtra && (
          <p className="text-[11px] text-surface-500 mb-2">
            Nessun allegato aggiuntivo. Puoi aggiungerne quanti ne servono.
          </p>
        )}

        <div className="space-y-2">
          {extra.map((doc) => (
            <div
              key={doc.id}
              className="p-3 rounded-xl bg-white/5 light:bg-surface-900/5 border border-white/5 light:border-surface-200"
            >
              <div className="flex items-center justify-between gap-3 flex-wrap">
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-white light:text-surface-900">
                    {doc.description || DOCUMENT_TYPE_LABELS[doc.document_type] || doc.document_type}
                  </p>
                  <p className="text-[11px] text-surface-500 mt-0.5">
                    {doc.original_filename} · caricato da {doc.uploaded_by_name ?? "—"} il{" "}
                    {new Date(doc.created_at).toLocaleDateString("it-IT")}
                  </p>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${statusColor(doc.status)}`}>
                    {STATUS_LABELS[doc.status] ?? doc.status}
                  </span>
                  <button
                    onClick={() => setPreviewDoc(doc)}
                    className="px-2.5 py-1 rounded-lg bg-white/5 light:bg-surface-900/5 hover:bg-white/10 border border-white/10 light:border-surface-300 text-surface-300 light:text-surface-600 text-xs font-semibold transition cursor-pointer"
                  >
                    Visualizza
                  </button>
                </div>
              </div>
              {doc.review_note && (
                <p className="text-[11px] text-surface-400 light:text-surface-500 mt-2">
                  <span className="font-semibold">Nota amministrazione:</span> {doc.review_note}
                </p>
              )}
              {reviewControls(doc)}
            </div>
          ))}
        </div>

        {addingExtra ? (
          <div className="mt-2 p-3 rounded-xl bg-white/5 light:bg-surface-900/5 border border-brand-500/20 space-y-2">
            <label className="text-[10px] font-semibold text-surface-300 light:text-surface-600 uppercase block">
              Che documento stai allegando?
            </label>
            <input
              autoFocus
              value={extraLabel}
              maxLength={MAX_DESCRIPTION_LENGTH}
              onChange={(e) => setExtraLabel(e.target.value)}
              placeholder="Es. Carta d'identità retro, Delega firmata, Contratto di locazione"
              className="w-full rounded-xl field px-3 py-2.5 text-sm focus:border-brand-500"
            />
            <p className="text-[10px] text-surface-500">
              Scrivi cos&apos;è, così l&apos;amministrazione sa cosa sta verificando. PDF, JPG o PNG, massimo 15 MB, oppure scatta una foto.
            </p>
            <input
              ref={extraFileInput}
              type="file"
              accept={ACCEPTED_CONTENT_TYPES}
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) handleExtraUpload(file);
                e.target.value = "";
              }}
            />
            <input
              ref={extraCameraInput}
              type="file"
              accept="image/jpeg,image/png"
              capture="environment"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) handleExtraUpload(file);
                e.target.value = "";
              }}
            />
            <div className="flex gap-2">
              <button
                onClick={() => extraFileInput.current?.click()}
                disabled={!canPickExtraFile || uploadingType === "OTHER"}
                className="px-3 py-1.5 rounded-lg bg-brand-600/10 hover:bg-brand-600/20 border border-brand-500/20 text-brand-400 text-xs font-semibold transition cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {uploadingType === "OTHER" ? "Caricamento..." : "Scegli il file e carica"}
              </button>
              <button
                onClick={() => extraCameraInput.current?.click()}
                disabled={!canPickExtraFile || uploadingType === "OTHER"}
                className="px-3 py-1.5 rounded-lg bg-white/5 light:bg-surface-900/5 hover:bg-white/10 border border-white/10 light:border-surface-300 text-surface-300 light:text-surface-600 text-xs font-semibold transition cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
              >
                Scatta una foto
              </button>
              <button
                onClick={() => { setAddingExtra(false); setExtraLabel(""); }}
                className="px-3 py-1.5 rounded-lg bg-white/5 light:bg-surface-900/5 hover:bg-white/10 text-surface-400 text-xs font-semibold transition cursor-pointer"
              >
                Annulla
              </button>
            </div>
          </div>
        ) : (
          <button
            onClick={() => setAddingExtra(true)}
            className="mt-2 w-full px-3 py-2.5 rounded-xl border border-dashed border-white/15 light:border-surface-300 text-surface-300 light:text-surface-600 hover:border-brand-500/40 hover:text-brand-400 text-xs font-semibold transition cursor-pointer"
          >
            + Aggiungi un altro documento
          </button>
        )}
      </div>
      {previewDoc && (
        <DocumentPreviewModal
          key={previewDoc.id}
          title={previewDoc.description || DOCUMENT_TYPE_LABELS[previewDoc.document_type] || "Documento"}
          filename={previewDoc.original_filename}
          contentType={previewDoc.content_type}
          loadUrl={() => fetchDocumentUrl(previewDoc.id)}
          onClose={() => setPreviewDoc(null)}
        />
      )}
    </div>
  );
}
