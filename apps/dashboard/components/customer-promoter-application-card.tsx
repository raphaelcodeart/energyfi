"use client";

import { useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { CollaborationDocumentViewer } from "@/components/collaboration-document-viewer";
import { Chip } from "@/components/ui/data-cells";
import { friendlyApiError } from "@/lib/api-error";
import type { AgentProfileRead, CollaborationDocumentRead } from "@/lib/types";

async function fetchMyApplication(): Promise<AgentProfileRead | null> {
  const res = await fetch("/api/proxy/network/agents/me");
  if (!res.ok) throw new Error("Impossibile caricare lo stato della richiesta.");
  const text = await res.text();
  return text ? JSON.parse(text) : null;
}

interface CustomerPromoterApplicationCardProps {
  /**
   * When true, renders nothing once the caller is an ACTIVE promoter. Used on
   * the customer home, where the card only invites; afterwards the area
   * switcher (area-switcher.tsx) leads to the promoter dashboard. The "Lavora
   * con noi" tab leaves it unset to keep showing a confirmation.
   */
  hideWhenActive?: boolean;
}

/**
 * The legal text is served by the backend (GET
 * /network/agents/apply/documents): one authoritative copy, versioned and
 * recorded with the acceptance, updatable without a frontend release.
 */
async function fetchCollaborationDocuments(): Promise<CollaborationDocumentRead[]> {
  const res = await fetch("/api/proxy/network/agents/apply/documents");
  if (!res.ok) throw new Error("Impossibile caricare il contratto di collaborazione.");
  return res.json();
}

export function CustomerPromoterApplicationCard({ hideWhenActive = false }: CustomerPromoterApplicationCardProps = {}) {
  const queryClient = useQueryClient();
  const { data: application, isLoading } = useQuery({
    queryKey: ["customer", "promoter-application"],
    queryFn: fetchMyApplication,
  });
  const [formOpen, setFormOpen] = useState(false);
  const formRef = useRef<HTMLElement>(null);
  // One acceptance per document key. Submission requires every returned
  // document to be ticked; the backend refuses incomplete applications too.
  const [accepted, setAccepted] = useState<Record<string, boolean>>({});
  const { data: documents, error: documentsError } = useQuery({
    queryKey: ["promoter-application", "documents"],
    queryFn: fetchCollaborationDocuments,
    enabled: formOpen,
  });
  const [otpRequested, setOtpRequested] = useState(false);
  const [otpCode, setOtpCode] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function openForm() {
    setAccepted({});
    setOtpRequested(false);
    setOtpCode("");
    setError(null);
    setFormOpen(true);
    requestAnimationFrame(() => formRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }));
  }

  async function handleRequestOtp() {
    setSubmitting(true);
    setError(null);
    try {
      const res = await fetch("/api/proxy/network/agents/apply/request-otp", { method: "POST" });
      if (!res.ok) throw new Error(await friendlyApiError(res, "Impossibile inviare il codice. Riprova più tardi."));
      setOtpRequested(true);
    } catch (err: any) {
      setError(err.message || "Impossibile inviare il codice. Riprova più tardi.");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleApply() {
    setSubmitting(true);
    setError(null);
    try {
      const res = await fetch("/api/proxy/network/agents/apply", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          accept_contract: true,
          // Echo back the version of each text shown, so an acceptance refers to a
          // specific wording. The backend refuses a stale version.
          accepted_documents: Object.fromEntries((documents ?? []).map((d) => [d.key, d.version])),
          otp_code: otpCode,
        }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res, "Impossibile inviare la richiesta. Riprova più tardi."));
      await queryClient.invalidateQueries({ queryKey: ["customer", "promoter-application"] });
      // The access token's roles lack PROMOTER until the next silent refresh, so
      // tell the area switcher to re-check live roles now.
      await queryClient.invalidateQueries({ queryKey: ["auth", "me", "roles"] });
      setFormOpen(false);
    } catch (err: any) {
      setError(err.message || "Impossibile inviare la richiesta. Riprova più tardi.");
    } finally {
      setSubmitting(false);
    }
  }

  // Derived, not stored, so a newly added document cannot be skipped via a stale flag.
  const allAccepted = !!documents && documents.length > 0 && documents.every((d) => accepted[d.key]);

  const card = "panel rounded-3xl p-6 sm:p-8";

  if (isLoading) {
    return <div className={`${card} h-40 animate-pulse`} />;
  }

  if (application?.status === "ACTIVE") {
    if (hideWhenActive) return null;
    return (
      <div className={card}>
        <p className="kpi-label">Lavora con noi</p>
        <h3 className="mt-2 text-xl font-black tracking-tight text-white">Sei un Promoter!</h3>
        <p className="mt-2 max-w-2xl text-sm text-surface-300">
          Vai alla dashboard promoter per gestire la tua rete e le tue commissioni, oppure usa il selettore
          &ldquo;Area Cliente / Area Promoter&rdquo; in alto per passare da un&apos;area all&apos;altra in qualsiasi momento.
        </p>
        <Link href="/promoter" className="act act-primary mt-5 !h-11 !px-5">
          Vai alla dashboard Promoter
        </Link>
      </div>
    );
  }

  if (application?.status === "PENDING_APPROVAL") {
    return (
      <div className={card}>
        <p className="kpi-label">Lavora con noi</p>
        <h3 className="mt-2 text-xl font-black tracking-tight text-white">Richiesta inviata</h3>
        <div className="mt-3">
          <Chip tone="warn" live>In attesa di approvazione</Chip>
        </div>
        <p className="mt-3 text-sm text-surface-300">
          Il nostro team sta valutando la tua richiesta. Riceverai una notifica non appena verrà esaminata.
        </p>
      </div>
    );
  }

  // Blacklisted: an existing TERMINATED row with is_blacklisted, set by an
  // admin (network/router.py update_agent). No apply action: the server would
  // put it in PENDING_APPROVAL (network/service.py apply_as_promoter), and
  // showing a normal "in attesa" state would hide the real reason.
  if (application?.is_blacklisted) {
    return (
      <div className={card}>
        <p className="kpi-label">Lavora con noi</p>
        <h3 className="mt-2 text-xl font-black tracking-tight text-white">Il tuo profilo promoter è bloccato</h3>
        <div className="mt-3">
          <Chip tone="bad">Bloccato dall&apos;amministrazione</Chip>
        </div>
        <p className="mt-3 text-sm text-surface-300">
          Non puoi attivarti come promoter in autonomia. Se pensi sia un errore, contatta subito l&apos;assistenza
          nella sezione Supporto.
        </p>
      </div>
    );
  }

  // No application yet, or a TERMINATED one that is not blacklisted: applying
  // activates immediately (network/service.py apply_as_promoter). The
  // application is a page of its own, not a modal.
  if (!formOpen) {
    return (
      <div className={card}>
        <p className="kpi-label">Lavora con noi</p>
        <h3 className="mt-2 text-xl font-black tracking-tight text-white">Diventa promoter SOSNET</h3>
        <p className="mt-2 max-w-2xl text-sm text-surface-300">
          Invita nuovi clienti e guadagna commissioni sulla tua rete.
        </p>
        {application?.status === "TERMINATED" && application.rejection_reason && (
          <p className="mt-2 text-xs text-surface-400">Nota dall&apos;ultima volta: {application.rejection_reason}</p>
        )}
        <button onClick={openForm} className="act act-primary mt-5 !h-11 !px-5">
          Leggi il contratto e candidati
        </button>
      </div>
    );
  }

  const steps = [
    { label: "Leggi e accetta", done: allAccepted },
    { label: "Ricevi il codice", done: otpRequested },
    { label: "Conferma", done: false },
  ];

  return (
    <section ref={formRef} className="rise scroll-mt-28 space-y-6">
      <div className={card}>
        <button onClick={() => setFormOpen(false)} className="act mb-5">
          ← Torna indietro
        </button>
        <p className="kpi-label">Candidatura</p>
        <h2 className="mt-2 text-2xl font-black tracking-tight text-white sm:text-3xl">Diventa Promoter SOSNET</h2>
        <p className="mt-2 max-w-2xl text-sm text-surface-300">
          Leggi e accetta i documenti qui sotto, poi firma con il codice che ricevi via email.
        </p>
        <ol className="mt-5 flex flex-wrap gap-2">
          {steps.map((step, i) => (
            <li key={step.label}>
              <Chip tone={step.done ? "ok" : "muted"}>
                {i + 1}. {step.label}
              </Chip>
            </li>
          ))}
        </ol>
      </div>

      {documentsError && (
        <div className={`${card} text-sm text-danger-300`}>Impossibile caricare il contratto. Riprova più tardi.</div>
      )}
      {!documents && !documentsError && <div className={`${card} h-60 animate-pulse`} />}

      {(documents ?? []).map((doc, index) => (
        <div key={doc.key} className={card}>
          <p className="kpi-label">Documento {index + 1} di {documents?.length}</p>
          <div className="mt-3">
            <CollaborationDocumentViewer document={doc} />
          </div>
          <label className="mt-4 flex cursor-pointer items-start gap-3 rounded-2xl bg-white/5 p-4 text-sm text-surface-200">
            <input
              type="checkbox"
              checked={!!accepted[doc.key]}
              onChange={(e) => setAccepted((prev) => ({ ...prev, [doc.key]: e.target.checked }))}
              className="mt-0.5 h-5 w-5 shrink-0 rounded accent-brand-500"
            />
            <span>{doc.acceptance_label}</span>
          </label>
        </div>
      ))}

      <div className={card}>
        <p className="kpi-label">Firma</p>
        {!otpRequested ? (
          <>
            <p className="mt-2 text-sm text-surface-300">
              {allAccepted
                ? "Ti mandiamo un codice via email: è la tua firma."
                : "Spunta tutte le accettazioni qui sopra per continuare."}
            </p>
            <button
              onClick={handleRequestOtp}
              disabled={!allAccepted || submitting}
              className="act act-primary mt-4 !h-12 w-full justify-center"
            >
              {submitting ? "Invio codice..." : "Invia codice di conferma via email"}
            </button>
          </>
        ) : (
          <div className="mt-2 space-y-3">
            <p className="text-sm text-surface-300">
              Ti abbiamo inviato un codice via email. Inseriscilo qui sotto per confermare la tua richiesta.
            </p>
            <input
              value={otpCode}
              onChange={(e) => setOtpCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
              placeholder="Codice a 6 cifre"
              inputMode="numeric"
              className="field w-full rounded-2xl px-4 py-3 text-center font-mono text-lg tracking-[0.4em]"
            />
            <button
              onClick={handleApply}
              disabled={otpCode.length !== 6 || submitting}
              className="act act-primary !h-12 w-full justify-center"
            >
              {submitting ? "Conferma in corso..." : "Conferma e attiva"}
            </button>
            <button
              onClick={handleRequestOtp}
              disabled={submitting}
              className="w-full cursor-pointer text-xs text-brand-300 transition hover:text-white disabled:opacity-50"
            >
              Non hai ricevuto il codice? Invia di nuovo
            </button>
          </div>
        )}
        {error && <p className="mt-3 text-sm text-danger-300">{error}</p>}
      </div>
    </section>
  );
}
