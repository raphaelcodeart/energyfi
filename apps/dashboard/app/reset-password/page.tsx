"use client";

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { AuthStage, StageAlert, StageLabel, StageLink, StageOutcome, StageSubmit } from "@/components/auth-stage";
import { PasswordInput } from "@/components/password-input";
import { translateErrorDetail } from "@/lib/api-error";

function ResetPasswordForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = searchParams.get("token") ?? "";

  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const mismatch = confirmPassword.length > 0 && newPassword !== confirmPassword;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (newPassword !== confirmPassword) {
      setError("Le due password non coincidono.");
      return;
    }
    setSubmitting(true);
    try {
      const res = await fetch("/api/public/reset-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token, new_password: newPassword }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail ? translateErrorDetail(body.detail) : "Impossibile reimpostare la password.");
      }
      setSuccess(true);
      setTimeout(() => router.push("/login"), 2500);
    } catch (err: any) {
      setError(err.message || "Impossibile reimpostare la password.");
    } finally {
      setSubmitting(false);
    }
  }

  if (!token) {
    return (
      <AuthStage
        title="Collegamento scaduto"
        intro="Questo indirizzo non porta più da nessuna parte."
        footer={<StageLink href="/forgot-password">Chiedine uno nuovo</StageLink>}
      >
        <StageOutcome
          tone="problema"
          title="Manca il codice del collegamento"
          icon={
            <svg className="h-8 w-8" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.828 10.172a4 4 0 010 5.656l-3 3a4 4 0 01-5.656-5.656l1.5-1.5m4.5-4.5l1.5-1.5a4 4 0 115.656 5.656l-3 3" />
            </svg>
          }
        >
          I collegamenti per rifare la password valgono una volta sola e durano poco. Chiedine uno nuovo: ci vogliono
          dieci secondi.
        </StageOutcome>
      </AuthStage>
    );
  }

  if (success) {
    return (
      <AuthStage badge="Fatto" title="Password aggiornata" intro="La vecchia password non funziona più.">
        <StageOutcome
          tone="fatto"
          title="Ti riportiamo all'accesso"
          icon={
            <svg className="h-8 w-8" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
            </svg>
          }
        >
          Fra un istante sei sulla schermata di accesso: entra con la password appena scelta.
        </StageOutcome>
      </AuthStage>
    );
  }

  return (
    <AuthStage
      badge="Nuova chiave"
      title="Scegli la password"
      intro="Almeno 8 caratteri, e possibilmente una che non usi da nessun'altra parte."
      footer={<StageLink href="/login">Torna all&apos;accesso</StageLink>}
    >
      <form onSubmit={handleSubmit} className="space-y-5">
        <div className="space-y-2">
          <StageLabel htmlFor="new-password">Nuova password</StageLabel>
          <PasswordInput
            id="new-password"
            required
            minLength={8}
            autoComplete="new-password"
            placeholder="Almeno 8 caratteri"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            className="field-xl"
          />
        </div>

        <div className="space-y-2">
          <StageLabel htmlFor="confirm-password">Riscrivila per conferma</StageLabel>
          <PasswordInput
            id="confirm-password"
            required
            minLength={8}
            autoComplete="new-password"
            placeholder="La stessa di sopra"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            className="field-xl"
            style={mismatch ? { borderColor: "rgba(255, 255, 255, 0.8)" } : undefined}
          />
          {mismatch && <p className="text-xs font-semibold text-white">Le due password non coincidono.</p>}
        </div>

        {error && <StageAlert>{error}</StageAlert>}

        <StageSubmit pending={submitting} pendingLabel="Salvataggio…" disabled={mismatch}>
          Salva ed entra
        </StageSubmit>
      </form>
    </AuthStage>
  );
}

export default function ResetPasswordPage() {
  return (
    <Suspense fallback={null}>
      <ResetPasswordForm />
    </Suspense>
  );
}
