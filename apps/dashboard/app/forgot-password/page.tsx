"use client";

import { useEffect, useState } from "react";
import { AuthStage, StageAlert, StageLabel, StageLink, StageOutcome, StageSubmit } from "@/components/auth-stage";
import { translateErrorDetail } from "@/lib/api-error";
import { DEFAULT_ORGANIZATION_ID } from "@/lib/config";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // "Cambia password" in the user menu passes the signed-in email along.
  useEffect(() => {
    const preset = new URLSearchParams(window.location.search).get("email");
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (preset) setEmail(preset);
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const res = await fetch("/api/public/forgot-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ organization_id: DEFAULT_ORGANIZATION_ID, email }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail ? translateErrorDetail(body.detail) : "Richiesta non riuscita.");
      }
      setSubmitted(true);
    } catch (err: any) {
      setError(err.message || "Richiesta non riuscita.");
    } finally {
      setSubmitting(false);
    }
  }

  if (submitted) {
    return (
      <AuthStage
        badge="Richiesta inviata"
        title="Guarda nella posta"
        intro="Abbiamo fatto partire il collegamento per rifare la password."
        footer={<StageLink href="/login">Torna all&apos;accesso</StageLink>}
      >
        <StageOutcome
          tone="fatto"
          title="Collegamento in viaggio"
          icon={
            <svg className="h-8 w-8" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
            </svg>
          }
        >
          Se <strong className="text-white">{email}</strong> corrisponde a un profilo SOSNET, entro qualche minuto
          arriva il collegamento per impostare la nuova password. Vale una volta sola e scade in fretta: aprilo appena
          lo ricevi. Se non lo trovi, controlla la posta indesiderata.
        </StageOutcome>
      </AuthStage>
    );
  }

  return (
    <AuthStage
      badge="Recupero accesso"
      title="Rimettiamoti dentro"
      intro="Scrivi l'email con cui sei registrato in SOSNET: ti mandiamo un collegamento per impostare una password nuova."
      footer={<StageLink href="/login">Torna all&apos;accesso</StageLink>}
    >
      <form onSubmit={handleSubmit} className="space-y-5">
        <div className="space-y-2">
          <StageLabel htmlFor="email">Email del profilo</StageLabel>
          <input
            id="email"
            required
            type="email"
            autoComplete="username"
            placeholder="nome@azienda.it"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="field-xl"
          />
        </div>

        {error && <StageAlert>{error}</StageAlert>}

        <StageSubmit pending={submitting} pendingLabel="Invio in corso…">
          Mandami il collegamento
        </StageSubmit>
      </form>
    </AuthStage>
  );
}
