"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { friendlyApiError } from "@/lib/api-error";

/** Google OAuth consent redirect target. This path is the redirect URI
    registered on the OAuth client (built server-side in
    `integrations/google_drive.py::CALLBACK_PATH`). The page only hands the
    `code` to the backend, which holds the client secret. */
function GoogleDriveCallback() {
  const params = useSearchParams();
  const [state, setState] = useState<"working" | "done" | "failed">("working");
  const [message, setMessage] = useState<string | null>(null);
  // StrictMode runs effects twice in development, but an authorization code is
  // single-use: a second exchange would fail with "invalid_grant".
  const sent = useRef(false);

  useEffect(() => {
    if (sent.current) return;
    sent.current = true;

    const code = params.get("code");
    const oauthState = params.get("state");
    const denied = params.get("error");

    async function run() {
      if (denied) {
        setState("failed");
        setMessage("Autorizzazione annullata su Google.");
        return;
      }
      if (!code || !oauthState) {
        setState("failed");
        setMessage("Google non ha restituito i dati necessari. Riprova dalle impostazioni.");
        return;
      }
      try {
        const res = await fetch("/api/proxy/integrations/google-drive/callback", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ code, state: oauthState }),
        });
        if (!res.ok) throw new Error(await friendlyApiError(res));
        const status = await res.json();
        setMessage(status.account_email ? `Collegato a ${status.account_email}.` : "Collegamento completato.");
        setState("done");
      } catch (err: any) {
        setMessage(err?.message || "Collegamento non riuscito.");
        setState("failed");
      }
    }
    run();
  }, [params]);

  return (
    <main className="min-h-screen flex items-center justify-center p-6 bg-surface-950 light:bg-surface-50">
      <div className="w-full max-w-md panel panel-hover rounded-2xl p-8 border-white/10 light:border-surface-300 bg-surface-950 light:bg-white text-center">
        <h1 className="text-lg font-bold text-white light:text-surface-900">
          {state === "working"
            ? "Collegamento a Google Drive…"
            : state === "done"
              ? "Google Drive collegato"
              : "Collegamento non riuscito"}
        </h1>
        {message && (
          <p
            className={`text-sm mt-2 ${
              state === "failed" ? "text-danger-400" : "text-surface-400 light:text-surface-500"
            }`}
          >
            {message}
          </p>
        )}
        {state !== "working" && (
          <>
            <Link
              href="/admin"
              className="inline-block mt-6 px-5 py-2.5 rounded-xl bg-gradient-to-r from-brand-600 to-accent-500 hover:from-brand-500 hover:to-accent-400 text-sm font-bold text-white shadow-lg shadow-brand-500/20 transition"
            >
              Torna alla dashboard
            </Link>
            <p className="text-[11px] text-surface-500 mt-3">
              Lo stato del collegamento si vede in <strong>Impostazioni</strong>.
            </p>
          </>
        )}
      </div>
    </main>
  );
}

export default function GoogleDriveCallbackPage() {
  return (
    <Suspense fallback={null}>
      <GoogleDriveCallback />
    </Suspense>
  );
}
