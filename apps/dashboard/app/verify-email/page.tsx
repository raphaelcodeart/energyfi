"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { AuthStage, StageLink, StageOutcome, StageSpinner } from "@/components/auth-stage";
import { translateErrorDetail } from "@/lib/api-error";

function VerifyEmailContent() {
  const searchParams = useSearchParams();
  const token = searchParams.get("token") ?? "";

  const [status, setStatus] = useState<"checking" | "success" | "error">(token ? "checking" : "error");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch("/api/public/verify-email", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ token }),
        });
        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          throw new Error(body.detail ? translateErrorDetail(body.detail) : "Link di conferma non valido.");
        }
        if (!cancelled) setStatus("success");
      } catch (err: any) {
        if (!cancelled) {
          setError(err.message || "Link di conferma non valido.");
          setStatus("error");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token]);

  if (status === "checking") {
    return (
      <AuthStage badge="Verifica" title="Un attimo solo" intro="Stiamo controllando il collegamento che hai aperto.">
        <StageOutcome tone="attesa" title="Controllo in corso…" icon={<StageSpinner size="h-8 w-8" />} />
      </AuthStage>
    );
  }

  if (status === "success") {
    return (
      <AuthStage
        badge="Indirizzo confermato"
        title="Email verificata"
        intro="Il tuo indirizzo è collegato al profilo SOSNET."
        footer={<StageLink href="/login">Vai all&apos;accesso</StageLink>}
      >
        <StageOutcome
          tone="fatto"
          title="Tutto a posto"
          icon={
            <svg className="h-8 w-8" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
            </svg>
          }
        >
          Da adesso ricevi a questo indirizzo gli avvisi su contratti, compensi e ordini. Puoi entrare nella tua
          console.
        </StageOutcome>
      </AuthStage>
    );
  }

  return (
    <AuthStage
      title="Collegamento non valido"
      intro="Questo indirizzo di conferma non funziona più."
      footer={<StageLink href="/login">Torna all&apos;accesso</StageLink>}
    >
      <StageOutcome
        tone="problema"
        title="Non siamo riusciti a confermare"
        icon={
          <svg className="h-8 w-8" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        }
      >
        {error || "Il collegamento è già stato usato oppure è scaduto."}{" "}
        Puoi far ripartire la conferma dalla tua console, oppure scrivere all&apos;assistenza.
      </StageOutcome>
    </AuthStage>
  );
}

export default function VerifyEmailPage() {
  return (
    <Suspense fallback={null}>
      <VerifyEmailContent />
    </Suspense>
  );
}
