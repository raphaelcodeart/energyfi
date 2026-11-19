"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AuthStage } from "@/components/auth-stage";
import { PasswordInput } from "@/components/password-input";
import { DEFAULT_ORGANIZATION_ID } from "@/lib/config";

/** Roles that land in the admin area. */
const ADMIN_ROLES = new Set([
  "SUPER_ADMIN",
  "ORGANIZATION_ADMIN",
  "ADMIN",
  "BACK_OFFICE_OPERATOR",
  "ACCOUNTING_OPERATOR",
  "SALES_MANAGER",
]);

/** Post-login destination, based on the roles the API granted
 *  (/api/auth/login), never on the email address. */
export function landingPathForRoles(roles: string[]): string {
  if (roles.some((role) => ADMIN_ROLES.has(role))) return "/admin";
  // SOS Affiliate: a Digital Ambassador lands in the promoter area even when
  // they are also a customer; only pure customers go to /customer.
  if (roles.includes("PROMOTER")) return "/promoter";
  if (roles.includes("CUSTOMER")) return "/customer";
  return "/promoter";
}

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password, organizationId: DEFAULT_ORGANIZATION_ID }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        setError(body.error ?? "Credenziali non riconosciute. Ricontrolla email e password.");
        return;
      }
      router.push(landingPathForRoles(body.roles ?? []));
      router.refresh();
    } catch {
      setError("Centrale SOSNET non raggiungibile. Riprova fra qualche istante.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthStage
      badge="Rete operativa"
      title="Apri la tua console"
      intro="Da qui entri nella tua rete, nei compensi maturati e nei negozi collegati. Un solo accesso per tutto."
      footer={
        <Link href="/forgot-password" className="btn-ghost-xl">
          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z" />
          </svg>
          Non ricordi la password?
        </Link>
      }
    >
      <form onSubmit={handleSubmit} className="space-y-5">
        <div className="space-y-2">
          <label className="block text-[11px] font-bold uppercase tracking-[0.16em] text-[#c6daff]" htmlFor="email">
            Email di accesso
          </label>
          <input
            id="email"
            type="email"
            autoComplete="username"
            className="field-xl"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="nome@azienda.it"
            required
          />
        </div>

        <div className="space-y-2">
          <label className="block text-[11px] font-bold uppercase tracking-[0.16em] text-[#c6daff]" htmlFor="password">
            Password personale
          </label>
          <PasswordInput
            id="password"
            autoComplete="current-password"
            className="field-xl"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="••••••••"
            required
          />
        </div>

        {error && (
          <div
            role="alert"
            className="pop flex items-start gap-3 rounded-2xl border border-white/25 bg-black/35 p-4 text-sm font-medium text-white"
          >
            <svg className="mt-0.5 h-5 w-5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
            <span>{error}</span>
          </div>
        )}

        <button type="submit" disabled={submitting} className="btn-xl !mt-7">
          <span className="btn-sheen" aria-hidden="true" />
          {submitting ? (
            <>
              <svg className="h-5 w-5 animate-spin" fill="none" viewBox="0 0 24 24" aria-hidden="true">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path
                  className="opacity-75"
                  fill="currentColor"
                  d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                />
              </svg>
              Apertura sessione…
            </>
          ) : (
            <>
              Entra in SOSNET
              <svg
                className="h-5 w-5 transition-transform duration-300 group-hover:translate-x-1"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                aria-hidden="true"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M13 7l5 5m0 0l-5 5m5-5H6" />
              </svg>
            </>
          )}
        </button>
      </form>
    </AuthStage>
  );
}
