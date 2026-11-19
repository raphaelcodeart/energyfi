"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { friendlyApiError } from "@/lib/api-error";
import { Chip } from "@/components/ui/data-cells";

export type GoogleDriveStatus = {
  configured: boolean;
  connected: boolean;
  account_email: string | null;
  connected_at: string | null;
  parent_folder_id: string | null;
  redirect_uri: string;
  client_id: string | null;
  client_secret_configured: boolean;
};

export async function fetchGoogleDriveStatus(): Promise<GoogleDriveStatus> {
  const res = await fetch("/api/proxy/integrations/google-drive");
  if (!res.ok) throw new Error("Impossibile leggere lo stato di Google Drive.");
  return res.json();
}

function CopyableValue({ value }: { value: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="flex items-center gap-2">
      <code className="flex-1 min-w-0 break-all px-2.5 py-1.5 rounded-lg bg-white/5 border border-white/10 text-[11px] text-surface-300">
        {value}
      </code>
      <button
        type="button"
        onClick={async () => {
          await navigator.clipboard.writeText(value);
          setCopied(true);
          setTimeout(() => setCopied(false), 2000);
        }}
        className="act shrink-0"
      >
        {copied ? "Copiato" : "Copia"}
      </button>
    </div>
  );
}

/**
 * Google Drive connection, for the "Invia su Drive" button on a contract dossier.
 * Fields are uncontrolled (defaultValue + key): the initial value comes from
 * the server, with no effect copying state into the form (a lint error here).
 */
export function AdminGoogleDriveSettingsCard() {
  const queryClient = useQueryClient();
  const { data: status, error: loadError } = useQuery({
    queryKey: ["admin", "google-drive"],
    queryFn: fetchGoogleDriveStatus,
  });

  const [saving, setSaving] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  async function handleSave(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    setSaving(true);
    setError(null);
    try {
      // Send the secret only if typed now: an empty field must not clear a saved
      // secret (same rule as the Stripe keys).
      const body: Record<string, string> = {
        client_id: String(form.get("client_id") ?? "").trim(),
        parent_folder_id: String(form.get("parent_folder_id") ?? "").trim(),
      };
      const secret = String(form.get("client_secret") ?? "").trim();
      if (secret) body.client_secret = secret;

      const res = await fetch("/api/proxy/integrations/google-drive/credentials", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      await queryClient.invalidateQueries({ queryKey: ["admin", "google-drive"] });
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch (err: any) {
      setError(err?.message || "Impossibile salvare le credenziali Google.");
    } finally {
      setSaving(false);
    }
  }

  async function handleConnect() {
    setConnecting(true);
    setError(null);
    try {
      const res = await fetch("/api/proxy/integrations/google-drive/authorize-url", { method: "POST" });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      const { url } = await res.json();
      // Same tab, not a popup: Google redirects back to the callback page, and a
      // blocked popup would make the button appear to do nothing.
      window.location.href = url;
    } catch (err: any) {
      setError(err?.message || "Impossibile avviare il collegamento con Google.");
      setConnecting(false);
    }
  }

  async function handleDisconnect() {
    setError(null);
    try {
      const res = await fetch("/api/proxy/integrations/google-drive", { method: "DELETE" });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      await queryClient.invalidateQueries({ queryKey: ["admin", "google-drive"] });
    } catch (err: any) {
      setError(err?.message || "Impossibile scollegare Google Drive.");
    }
  }

  return (
    <div className="panel rounded-3xl p-7 sm:p-8">
      <div className="kpi-label">Archivio documenti</div>
      <div className="mt-1 flex items-center gap-3 flex-wrap">
        <h3 className="text-xl font-black tracking-tight text-white">Google Drive</h3>
        {status && (
          <Chip tone={status.connected ? "ok" : status.configured ? "warn" : "muted"} live={!status.connected && status.configured}>
            {status.connected ? "Collegato" : status.configured ? "Da autorizzare" : "Non configurato"}
          </Chip>
        )}
      </div>
      <p className="text-xs text-surface-400 mt-2 mb-5 max-w-2xl">
        Serve al pulsante <strong>&ldquo;Invia su Drive&rdquo;</strong> sul fascicolo di un contratto:
        crea una cartella <em>nome cliente-id contratto</em> con dentro tutti i documenti allegati e
        il PDF riassuntivo. I file finiscono sul Drive dell&apos;account che collega qui sotto.
      </p>

      {loadError && (
        <div className="p-3 rounded-lg bg-danger-500/10 border border-danger-500/20 text-danger-400 text-xs mb-4">
          Impossibile leggere lo stato del collegamento.
        </div>
      )}

      {status && (
        <>
          <div
            className={`flex items-center justify-between gap-3 flex-wrap p-4 rounded-2xl border text-xs mb-5 ${
              status.connected
                ? "bg-success-500/10 border-success-500/20 text-success-400"
                : "bg-warn-500/10 border-warn-500/20 text-warn-400"
            }`}
          >
            <span className="font-semibold">
              {status.connected
                ? `Collegato a ${status.account_email ?? "un account Google"}`
                : status.configured
                  ? "Credenziali inserite. Manca solo l'autorizzazione."
                  : "Non configurato: inserisci Client ID e Client Secret qui sotto."}
            </span>
            <div className="flex gap-2 shrink-0">
              {status.configured && (
                <button
                  type="button"
                  onClick={handleConnect}
                  disabled={connecting}
                  className="act act-primary"
                >
                  {connecting ? "Apertura..." : status.connected ? "Ricollega" : "Collega Google Drive"}
                </button>
              )}
              {status.connected && (
                <button
                  type="button"
                  onClick={handleDisconnect}
                  className="act"
                >
                  Scollega
                </button>
              )}
            </div>
          </div>

          <form key={status.client_id ?? "empty"} onSubmit={handleSave} className="space-y-4">
            <div className="space-y-1">
              <label className="kpi-label block">
                Client ID
              </label>
              <input
                name="client_id"
                defaultValue={status.client_id ?? ""}
                placeholder="1234567890-abcdefg.apps.googleusercontent.com"
                className="w-full rounded-xl field px-3 py-2.5 text-sm focus:border-brand-500"
              />
            </div>

            <div className="space-y-1">
              <label className="kpi-label block">
                Client Secret
              </label>
              <input
                name="client_secret"
                type="password"
                autoComplete="new-password"
                placeholder={status.client_secret_configured ? "•••••••• (già salvato)" : "GOCSPX-..."}
                className="w-full rounded-xl field px-3 py-2.5 text-sm focus:border-brand-500"
              />
              <p className="text-[10px] text-surface-500">
                Lascia vuoto per non cambiarlo. Una volta salvato non viene più mostrato.
              </p>
            </div>

            <div className="space-y-1">
              <label className="kpi-label block">
                ID cartella di destinazione (facoltativo)
              </label>
              <input
                name="parent_folder_id"
                defaultValue={status.parent_folder_id ?? ""}
                placeholder="Vuoto = radice del Drive"
                className="w-full rounded-xl field px-3 py-2.5 text-sm focus:border-brand-500"
              />
              <p className="text-[10px] text-surface-500">
                Apri la cartella su Drive e copia la parte finale dell&apos;indirizzo, dopo
                <code className="mx-1">/folders/</code>. Le cartelle dei contratti nasceranno lì dentro.
              </p>
            </div>

            <div className="space-y-1">
              <label className="kpi-label block">
                URI di reindirizzamento da registrare su Google
              </label>
              <CopyableValue value={status.redirect_uri} />
              <p className="text-[10px] text-surface-500">
                Incollalo tale e quale fra gli <em>Authorized redirect URIs</em> del client OAuth,
                sulla console Google Cloud. Se non combacia carattere per carattere, Google rifiuta
                il collegamento.
              </p>
            </div>

            <button
              type="submit"
              disabled={saving}
              className="px-5 py-2.5 rounded-full bg-gradient-to-r from-brand-600 to-accent-500 text-xs font-black text-white shadow-lg shadow-brand-500/30 hover:brightness-110 transition cursor-pointer disabled:opacity-50"
            >
              {saving ? "Salvataggio..." : "Salva"}
            </button>
            {saved && (
              <div className="p-3 rounded-lg bg-success-500/10 border border-success-500/20 text-success-400 text-xs">
                Credenziali salvate.
              </div>
            )}
          </form>
        </>
      )}

      {error && (
        <div className="mt-4 p-3 rounded-lg bg-danger-500/10 border border-danger-500/20 text-danger-400 text-xs">
          {error}
        </div>
      )}
    </div>
  );
}
