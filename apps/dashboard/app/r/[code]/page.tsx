"use client";

import { use, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import {
  AuthStage,
  StageAlert,
  StageLabel,
  StageLink,
  StageOutcome,
  StageSpinner,
  StageSubmit,
} from "@/components/auth-stage";
import { PasswordInput } from "@/components/password-input";
import { translateErrorDetail } from "@/lib/api-error";
import type { PromoterCodeRead } from "@/lib/types";

const KIND_LABELS: Record<string, string> = {
  PRIVATE: "Privato",
  SOLE_PROPRIETOR: "Partita IVA",
  COMPANY: "Azienda",
  CONDOMINIUM: "Condominio",
};

const PRIVATE_LIKE = new Set(["PRIVATE", "SOLE_PROPRIETOR"]);

async function resolveReferralCode(code: string, organizationId: string): Promise<PromoterCodeRead> {
  const res = await fetch(`/api/public/referral/${encodeURIComponent(code)}?org=${encodeURIComponent(organizationId)}`);
  if (!res.ok) throw new Error("Link di invito non valido o scaduto.");
  return res.json();
}

export default function ReferralLandingPage({ params }: { params: Promise<{ code: string }> }) {
  const { code } = use(params);
  const searchParams = useSearchParams();
  const organizationId = searchParams.get("org") ?? "";
  const productId = searchParams.get("product");
  const productName = searchParams.get("product_name");
  const router = useRouter();

  const { data: promoterCode, error: resolveErrorObj, isLoading: resolving } = useQuery({
    queryKey: ["referral", "resolve", code, organizationId],
    queryFn: () => resolveReferralCode(code, organizationId),
    enabled: !!organizationId,
    retry: false,
  });
  const resolveError = !organizationId
    ? "Link non valido: manca il riferimento all'organizzazione."
    : resolveErrorObj instanceof Error ? resolveErrorObj.message : null;

  const [kind, setKind] = useState("PRIVATE");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [passwordConfirm, setPasswordConfirm] = useState("");
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [companyName, setCompanyName] = useState("");
  const [phone, setPhone] = useState("");
  const [acceptPrivacy, setAcceptPrivacy] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const mismatch = passwordConfirm.length > 0 && password !== passwordConfirm;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitError(null);
    if (password !== passwordConfirm) {
      setSubmitError("Le due password non coincidono.");
      return;
    }
    if (!acceptPrivacy) {
      setSubmitError("Devi accettare l'informativa sulla privacy per registrarti.");
      return;
    }
    setSubmitting(true);
    try {
      const res = await fetch("/api/public/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          organization_id: organizationId,
          referral_code: code,
          email,
          password,
          kind,
          first_name: PRIVATE_LIKE.has(kind) ? firstName : null,
          last_name: PRIVATE_LIKE.has(kind) ? lastName : null,
          company_name: PRIVATE_LIKE.has(kind) ? null : companyName,
          phone: phone || null,
          accept_privacy: acceptPrivacy,
        }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail ? translateErrorDetail(body.detail) : "Registrazione non riuscita.");
      }
      setSuccess(true);
      setTimeout(() => router.push("/login"), 2500);
    } catch (err: any) {
      setSubmitError(err.message || "Registrazione non riuscita.");
    } finally {
      setSubmitting(false);
    }
  }

  if (success) {
    return (
      <AuthStage badge="Benvenuto" title="Ci sei" intro="Il tuo profilo SOSNET è stato creato.">
        <StageOutcome
          tone="fatto"
          title="Manca solo la conferma"
          icon={
            <svg className="h-8 w-8" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
            </svg>
          }
        >
          Ti abbiamo scritto a <strong className="text-white">{email}</strong>: apri il collegamento nel messaggio per
          attivare il profilo. Fra un istante ti portiamo alla schermata di accesso.
        </StageOutcome>
      </AuthStage>
    );
  }

  if (resolving) {
    return (
      <AuthStage badge="Invito" title="Un attimo solo" intro="Stiamo controllando l'invito che hai aperto.">
        <StageOutcome tone="attesa" title="Verifica dell'invito…" icon={<StageSpinner size="h-8 w-8" />} />
      </AuthStage>
    );
  }

  if (resolveError) {
    return (
      <AuthStage
        title="Invito non valido"
        intro="Questo collegamento non apre nessuna iscrizione."
        footer={<StageLink href="/login">Vai all&apos;accesso</StageLink>}
      >
        <StageOutcome
          tone="problema"
          title="Non riusciamo a riconoscerlo"
          icon={
            <svg className="h-8 w-8" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          }
        >
          {resolveError} In SOSNET ci si iscrive solo con l&apos;invito di un promoter: chiedi il collegamento
          aggiornato a chi te lo ha mandato.
        </StageOutcome>
      </AuthStage>
    );
  }

  return (
    <AuthStage
      width="larga"
      badge={
        promoterCode?.promoter_display_name
          ? `Invito di ${promoterCode.promoter_display_name}`
          : "Invito di un promoter"
      }
      title="Entra nella rete"
      intro="Pochi dati e il profilo è tuo: da qui segui contratti, compensi e ordini in un posto solo."
      footer={<StageLink href="/login">Hai già un profilo? Accedi</StageLink>}
    >
      {productName && (
        <div className="mb-6 rounded-2xl border border-white/15 bg-black/25 p-4">
          <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-[#c6daff]">Offerta consigliata</p>
          <p className="mt-1 text-base font-bold text-white">{productName}</p>
          {productId && <p className="font-mono text-[10px] text-[#8dabd9]">{productId}</p>}
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="space-y-2">
          <StageLabel htmlFor="kind">Come ti registri</StageLabel>
          <select id="kind" value={kind} onChange={(e) => setKind(e.target.value)} className="field-xl field-lg">
            {Object.entries(KIND_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </div>

        {PRIVATE_LIKE.has(kind) ? (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <StageLabel htmlFor="first-name">Nome</StageLabel>
              <input
                id="first-name"
                required
                value={firstName}
                onChange={(e) => setFirstName(e.target.value)}
                className="field-xl field-lg"
              />
            </div>
            <div className="space-y-2">
              <StageLabel htmlFor="last-name">Cognome</StageLabel>
              <input
                id="last-name"
                required
                value={lastName}
                onChange={(e) => setLastName(e.target.value)}
                className="field-xl field-lg"
              />
            </div>
          </div>
        ) : (
          <div className="space-y-2">
            <StageLabel htmlFor="company">Ragione sociale</StageLabel>
            <input
              id="company"
              required
              value={companyName}
              onChange={(e) => setCompanyName(e.target.value)}
              className="field-xl field-lg"
            />
          </div>
        )}

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div className="space-y-2">
            <StageLabel htmlFor="phone">Telefono</StageLabel>
            <input
              id="phone"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              className="field-xl field-lg"
              placeholder="facoltativo"
            />
          </div>
          <div className="space-y-2">
            <StageLabel htmlFor="email">Email</StageLabel>
            <input
              id="email"
              required
              type="email"
              autoComplete="username"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="field-xl field-lg"
              placeholder="nome@azienda.it"
            />
          </div>
        </div>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div className="space-y-2">
            <StageLabel htmlFor="password">Password</StageLabel>
            <PasswordInput
              id="password"
              required
              minLength={8}
              autoComplete="new-password"
              placeholder="Almeno 8 caratteri"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="field-xl field-lg"
            />
          </div>
          <div className="space-y-2">
            <StageLabel htmlFor="password-confirm">Riscrivila</StageLabel>
            <PasswordInput
              id="password-confirm"
              required
              minLength={8}
              autoComplete="new-password"
              placeholder="La stessa di sopra"
              value={passwordConfirm}
              onChange={(e) => setPasswordConfirm(e.target.value)}
              className="field-xl field-lg"
              style={mismatch ? { borderColor: "rgba(255, 255, 255, 0.8)" } : undefined}
            />
          </div>
        </div>

        {mismatch && <p className="text-xs font-semibold text-white">Le due password non coincidono.</p>}

        <label className="flex cursor-pointer items-start gap-3 pt-2 text-xs leading-relaxed text-[#b9cdf0]">
          <input
            type="checkbox"
            checked={acceptPrivacy}
            onChange={(e) => setAcceptPrivacy(e.target.checked)}
            className="stage-check mt-0.5"
          />
          <span>
            Ho letto e accetto l&apos;informativa sulla privacy e il trattamento dei miei dati personali da parte di
            SOSNET, secondo il Regolamento (UE) 2016/679.
          </span>
        </label>

        {submitError && <StageAlert>{submitError}</StageAlert>}

        <StageSubmit pending={submitting} pendingLabel="Creazione profilo…" disabled={!acceptPrivacy || mismatch}>
          Crea il mio profilo
        </StageSubmit>
      </form>
    </AuthStage>
  );
}
