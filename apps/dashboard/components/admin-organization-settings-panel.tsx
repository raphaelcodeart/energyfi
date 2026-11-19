"use client";

import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AdminGoogleDriveSettingsCard } from "@/components/admin-google-drive-settings-card";
import { PasswordInput } from "@/components/password-input";
import { Chip } from "@/components/ui/data-cells";
import { friendlyApiError } from "@/lib/api-error";
import type { OrganizationSettingsRead, PaymentSettingsRead } from "@/lib/types";

async function fetchSettings(): Promise<OrganizationSettingsRead> {
  const res = await fetch("/api/proxy/organizations/me/settings");
  if (!res.ok) throw new Error("Impossibile caricare le impostazioni aziendali.");
  return res.json();
}

async function fetchPaymentSettings(): Promise<PaymentSettingsRead> {
  const res = await fetch("/api/proxy/organizations/me/payment-settings");
  if (!res.ok) throw new Error("Impossibile caricare le impostazioni di pagamento.");
  return res.json();
}

/**
 * Company-wide configuration: the bank account customers wire transfers to
 * (invoice-redemption 5% payments, order residuals) and, SUPER_ADMIN only,
 * Stripe keys. `isSuperAdmin` only hides the section; the
 * organization.manage_payments permission is enforced server-side.
 */
const SHOW_CONTRACT_SETTINGS = false;

export function AdminOrganizationSettingsPanel(
  { isSuperAdmin = false, organizationId }: { isSuperAdmin?: boolean; organizationId?: string } = {}
) {
  const queryClient = useQueryClient();
  const { data: settings, error: loadError } = useQuery({
    queryKey: ["admin", "organization-settings"],
    queryFn: fetchSettings,
  });

  const [iban, setIban] = useState("");
  const [holder, setHolder] = useState("");
  const [instructions, setInstructions] = useState("");
  const [saveLoading, setSaveLoading] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saveSuccess, setSaveSuccess] = useState(false);

  useEffect(() => {
    if (settings) {
      setIban(settings.bank_iban ?? "");
      setHolder(settings.bank_account_holder ?? "");
      setInstructions(settings.bank_transfer_instructions ?? "");
    }
  }, [settings]);

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    setSaveLoading(true);
    setSaveError(null);
    try {
      const res = await fetch("/api/proxy/organizations/me/settings", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          bank_iban: iban.trim() || null,
          bank_account_holder: holder.trim() || null,
          bank_transfer_instructions: instructions.trim() || null,
        }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      await queryClient.invalidateQueries({ queryKey: ["admin", "organization-settings"] });
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 3000);
    } catch (err: any) {
      setSaveError(err.message || "Impossibile salvare le impostazioni.");
    } finally {
      setSaveLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="panel rounded-3xl p-7 sm:p-8">
        <div className="kpi-label">Incassi via bonifico</div>
        <h3 className="mt-1 text-xl font-black tracking-tight text-white mb-1">Coordinate bancarie aziendali</h3>
        <p className="text-xs text-surface-500 mb-4">
          Mostrate al cliente quando deve pagare tramite bonifico (riscatto fatture, ordini). Finché l'IBAN non è
          impostato, il bottone "Paga con bonifico" non compare -- il cliente non può scegliere un metodo non
          configurato.
        </p>
        {loadError && <p className="text-sm text-danger-400 mb-3">Impossibile caricare le impostazioni.</p>}
        <form onSubmit={handleSave} className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="space-y-1">
              <label className="kpi-label block">IBAN</label>
              <input
                value={iban}
                onChange={(e) => setIban(e.target.value)}
                placeholder="IT00 A000 0000 0000 0000 0000 000"
                className="w-full rounded-xl field px-3 py-2 text-sm font-mono focus:border-brand-500"
              />
            </div>
            <div className="space-y-1">
              <label className="kpi-label block">Intestatario</label>
              <input
                value={holder}
                onChange={(e) => setHolder(e.target.value)}
                placeholder="SOSNET Srl"
                className="w-full rounded-xl field px-3 py-2 text-sm focus:border-brand-500"
              />
            </div>
          </div>
          <div className="space-y-1">
            <label className="kpi-label block">
              Istruzioni aggiuntive per il bonifico
            </label>
            <textarea
              rows={3}
              value={instructions}
              onChange={(e) => setInstructions(e.target.value)}
              placeholder="Es. Includi il codice ordine/riscatto nella causale del bonifico."
              className="w-full rounded-xl field px-3 py-2 text-sm focus:border-brand-500 resize-none"
            />
            <p className="text-[10px] text-surface-500">Mostrato insieme a IBAN e intestatario ovunque un cliente veda le istruzioni di pagamento.</p>
          </div>
          <button
            type="submit"
            disabled={saveLoading}
            className="px-5 py-2.5 rounded-full bg-gradient-to-r from-brand-600 to-accent-500 text-xs font-black text-white shadow-lg shadow-brand-500/30 hover:brightness-110 transition cursor-pointer disabled:opacity-50"
          >
            {saveLoading ? "Salvataggio..." : "Salva"}
          </button>
          {saveError && (
            <div className="p-3 rounded-lg bg-danger-500/10 border border-danger-500/20 text-danger-400 text-xs">{saveError}</div>
          )}
          {saveSuccess && (
            <div className="p-3 rounded-lg bg-success-500/10 border border-success-500/20 text-success-400 text-xs">Impostazioni salvate.</div>
          )}
        </form>
      </div>

      {/* Luce e gas contracts are out of this console: their price list,
          cashback and Google Drive dossier cards stay in the code, not shown. */}
      {SHOW_CONTRACT_SETTINGS && (
        <>
          <ContractFullPaymentDiscountCard
            key={String(settings?.contract_full_payment_discount_percentage ?? "default")}
            current={settings?.contract_full_payment_discount_percentage ?? null}
          />
          <ContractCashbackSettingsCard current={settings?.contract_instalment_cashback_mode ?? null} />
          <AdminGoogleDriveSettingsCard />
        </>
      )}

      {isSuperAdmin && <AdminStripeSettingsCard organizationId={organizationId} />}
    </div>
  );
}

/** Discount for paying a contract in one go; 3 and 12 instalments stay at list price. */
function ContractFullPaymentDiscountCard({ current }: { current: number | null }) {
  const queryClient = useQueryClient();
  const [value, setValue] = useState(String(current ?? 32));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const pct = Math.max(0, Math.min(90, parseInt(value, 10) || 0));
  const example = 180 * (1 - pct / 100);

  async function save() {
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      const res = await fetch("/api/proxy/organizations/me/settings", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ contract_full_payment_discount_percentage: pct }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      await queryClient.invalidateQueries({ queryKey: ["admin", "organization-settings"] });
      setSaved(true);
    } catch (err: any) {
      setError(err.message || "Impossibile salvare l'impostazione.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="panel rounded-3xl p-7 sm:p-8">
      <div className="kpi-label">Listino contratti</div>
      <h3 className="mt-1 text-xl font-black tracking-tight text-white mb-1">Sconto per il pagamento in un&apos;unica soluzione</h3>
      <p className="text-xs text-surface-500 mb-4">
        Il cliente che paga il contratto tutto subito con carta ha questo sconto sul prezzo (l&apos;IVA, se dovuta, si
        calcola sul prezzo scontato). Pagamenti in 3 o 12 rate e bonifici confermati a mano restano a prezzo pieno.
        Il cashback segue quanto il cliente paga davvero. Metti 0 per non fare sconto.
      </p>
      <div className="flex flex-wrap items-end gap-3">
        <label className="block">
          <span className="block kpi-label mb-1">Sconto %</span>
          <input
            inputMode="numeric"
            value={value}
            onChange={(e) => { setValue(e.target.value); setSaved(false); }}
            className="w-24 rounded-xl field px-3 py-2 text-sm focus:border-brand-500"
          />
        </label>
        <button
          type="button"
          onClick={save}
          disabled={saving}
          className="px-5 py-2.5 rounded-full bg-gradient-to-r from-brand-600 to-accent-500 text-xs font-black text-white shadow-lg shadow-brand-500/30 hover:brightness-110 transition cursor-pointer disabled:opacity-50"
        >
          {saving ? "Salvataggio..." : "Salva"}
        </button>
        <span className="text-xs text-surface-400 pb-2">
          Esempio: 180 € → <strong className="text-success-400">{example.toLocaleString("it-IT", { style: "currency", currency: "EUR" })}</strong> + IVA se pagato tutto subito
        </span>
      </div>
      {error && <div className="mt-3 p-3 rounded-lg bg-danger-500/10 border border-danger-500/20 text-danger-400 text-xs">{error}</div>}
      {saved && <div className="mt-3 p-3 rounded-lg bg-success-500/10 border border-success-500/20 text-success-400 text-xs">Sconto salvato: vale per i prossimi pagamenti.</div>}
    </div>
  );
}

const CASHBACK_MODES: { key: "PER_INSTALMENT" | "UPFRONT"; title: string; body: string }[] = [
  {
    key: "PER_INSTALMENT",
    title: "Una parte a ogni rata pagata",
    body: "Il cliente riceve il cashback di ogni rata quando Stripe la incassa (o quando la confermi a mano). Se smette di pagare, non ha ricevuto il cashback delle rate mancanti.",
  },
  {
    key: "UPFRONT",
    title: "Tutto subito, alla prima rata",
    body: "Appena il cliente paga la prima rata riceve in un'unica ricarica SosnetCash il cashback dell'intero contratto. Più semplice da capire, ma se poi smette di pagare il cashback è già stato dato.",
  },
];

/**
 * How a contract paid in 3 or 12 instalments earns its SosnetCash cashback.
 * Applied to each contract when its first instalment is paid, so changing it
 * never credits a contract twice.
 */
function ContractCashbackSettingsCard({ current }: { current: "PER_INSTALMENT" | "UPFRONT" | null }) {
  const queryClient = useQueryClient();
  const [saving, setSaving] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const active = current ?? "PER_INSTALMENT";

  async function choose(mode: "PER_INSTALMENT" | "UPFRONT") {
    if (mode === active) return;
    setSaving(mode);
    setError(null);
    try {
      const res = await fetch("/api/proxy/organizations/me/settings", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ contract_instalment_cashback_mode: mode }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      await queryClient.invalidateQueries({ queryKey: ["admin", "organization-settings"] });
    } catch (err: any) {
      setError(err.message || "Impossibile salvare l'impostazione.");
    } finally {
      setSaving(null);
    }
  }

  return (
    <div className="panel rounded-3xl p-7 sm:p-8">
      <div className="kpi-label">SosnetCash</div>
      <h3 className="mt-1 text-xl font-black tracking-tight text-white mb-1">Cashback dei contratti pagati a rate</h3>
      <p className="text-xs text-surface-500 mb-4">
        Per i contratti pagati in 3 o 12 rate. La scelta vale per ogni contratto dal momento in cui il cliente paga la
        prima rata: cambiarla dopo non accredita mai due volte lo stesso contratto. I pagamenti in unica soluzione
        ricevono sempre tutto il cashback subito.
      </p>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {CASHBACK_MODES.map((mode) => {
          const selected = mode.key === active;
          return (
            <button
              key={mode.key}
              type="button"
              onClick={() => choose(mode.key)}
              disabled={saving !== null}
              className={`text-left p-5 rounded-2xl border transition cursor-pointer disabled:cursor-wait ${
                selected
                  ? "bg-gradient-to-br from-brand-500/25 to-accent-500/10 border-white/40 shadow-lg shadow-brand-500/20"
                  : "bg-white/5 border-white/10 hover:bg-white/10"
              }`}
            >
              <span className="flex items-center gap-2">
                <span className={`w-4 h-4 rounded-full border-2 shrink-0 ${selected ? "border-brand-500 bg-brand-500" : "border-surface-500"}`} />
                <span className="text-sm font-semibold text-white">
                  {mode.title}
                  {mode.key === "PER_INSTALMENT" && <span className="ml-1.5 text-[10px] font-normal text-surface-500">(predefinito)</span>}
                </span>
              </span>
              <span className="block text-xs text-surface-400 mt-1.5">{saving === mode.key ? "Salvataggio..." : mode.body}</span>
            </button>
          );
        })}
      </div>
      {error && <div className="mt-3 p-3 rounded-lg bg-danger-500/10 border border-danger-500/20 text-danger-400 text-xs">{error}</div>}
    </div>
  );
}

function AdminStripeSettingsCard({ organizationId }: { organizationId?: string }) {
  const queryClient = useQueryClient();
  const { data: payment, error: loadError } = useQuery({
    queryKey: ["admin", "payment-settings"],
    queryFn: fetchPaymentSettings,
  });

  const [publishableKey, setPublishableKey] = useState("");
  const [secretKey, setSecretKey] = useState("");
  const [webhookSecret, setWebhookSecret] = useState("");
  const [saveLoading, setSaveLoading] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saveSuccess, setSaveSuccess] = useState(false);

  useEffect(() => {
    if (payment) setPublishableKey(payment.stripe_publishable_key ?? "");
  }, [payment]);

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    setSaveLoading(true);
    setSaveError(null);
    try {
      // Secrets are sent only if typed, so an untouched field never overwrites a
      // saved secret (see PaymentSettingsUpdate's exclude_unset).
      const body: Record<string, string> = { stripe_publishable_key: publishableKey.trim() };
      if (secretKey.trim()) body.stripe_secret_key = secretKey.trim();
      if (webhookSecret.trim()) body.stripe_webhook_secret = webhookSecret.trim();

      const res = await fetch("/api/proxy/organizations/me/payment-settings", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      setSecretKey("");
      setWebhookSecret("");
      await queryClient.invalidateQueries({ queryKey: ["admin", "payment-settings"] });
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 3000);
    } catch (err: any) {
      setSaveError(err.message || "Impossibile salvare le impostazioni di pagamento.");
    } finally {
      setSaveLoading(false);
    }
  }

  const cardReady = payment?.stripe_secret_key_configured && !!payment?.stripe_publishable_key;

  return (
    <div className="panel rounded-3xl p-7 sm:p-8">
      <div className="kpi-label">Incassi con carta</div>
      <div className="mt-1 flex items-center gap-3 flex-wrap mb-1">
        <h3 className="text-xl font-black tracking-tight text-white">Pagamenti con carta (Stripe)</h3>
        <Chip tone="accent">Solo Super Admin</Chip>
        <Chip tone={cardReady ? "ok" : "warn"} live={!cardReady}>{cardReady ? "Attivo" : "Non configurato"}</Chip>
      </div>
      <p className="text-xs text-surface-500 mb-4">
        Finché queste chiavi non sono entrambe configurate, il bottone "Paga con carta" non compare da nessuna parte
        nel sistema -- si offre solo il bonifico. Le chiavi possono essere preparate ora e attivate in un secondo momento.
      </p>
      {loadError && <p className="text-sm text-danger-400 mb-3">Impossibile caricare le impostazioni.</p>}

      <div className="mb-5 p-4 rounded-2xl bg-white/5 border border-white/10">
        <p className="text-xs text-surface-300">
          Stato: {cardReady ? (
            <span className="text-success-400 font-semibold">Attivo -- i clienti possono pagare con carta</span>
          ) : (
            <span className="text-warn-400 font-semibold">Non configurato</span>
          )}
        </p>
        {payment?.stripe_secret_key_configured && (
          <p className="text-[10px] text-surface-500 mt-1 font-mono">Chiave segreta salvata: •••• {payment.stripe_secret_key_last4}</p>
        )}
        <p className="text-[10px] text-surface-500 mt-1">
          Webhook: {payment?.stripe_webhook_secret_configured ? "configurato" : "non configurato"}
        </p>
      </div>

      <form onSubmit={handleSave} className="space-y-4">
        <div className="space-y-1">
          <label className="kpi-label block">Chiave pubblicabile (publishable key)</label>
          <input
            value={publishableKey}
            onChange={(e) => setPublishableKey(e.target.value)}
            placeholder="pk_live_... oppure pk_test_..."
            className="w-full rounded-xl field px-3 py-2 text-sm font-mono focus:border-brand-500"
          />
        </div>
        <div className="space-y-1">
          <label className="kpi-label block">Chiave segreta (secret key)</label>
          <PasswordInput
            autoComplete="off"
            value={secretKey}
            onChange={(e) => setSecretKey(e.target.value)}
            placeholder={payment?.stripe_secret_key_configured ? "Già impostata -- lascia vuoto per non cambiarla" : "sk_live_... oppure sk_test_..."}
            className="w-full rounded-xl field px-3 py-2 text-sm font-mono focus:border-brand-500"
          />
        </div>
        <div className="space-y-1">
          <label className="kpi-label block">Chiave segreta del webhook</label>
          <PasswordInput
            autoComplete="off"
            value={webhookSecret}
            onChange={(e) => setWebhookSecret(e.target.value)}
            placeholder={payment?.stripe_webhook_secret_configured ? "Già impostata -- lascia vuoto per non cambiarla" : "whsec_..."}
            className="w-full rounded-xl field px-3 py-2 text-sm font-mono focus:border-brand-500"
          />
          <p className="text-[10px] text-surface-500">
            Configura su Stripe un endpoint webhook con gli eventi <code>checkout.session.completed</code>,{" "}
            <code>invoice.paid</code> e <code>invoice.payment_failed</code> (senza gli ultimi due i pagamenti a rate
            non arrivano all&apos;app), puntato a:{" "}
            <code className="text-surface-400 break-all">
              {typeof window !== "undefined" ? window.location.origin : ""}/api/payments/stripe/webhook/{organizationId ?? "<ID-organizzazione>"}
            </code>
          </p>
        </div>
        <button
          type="submit"
          disabled={saveLoading}
          className="px-5 py-2.5 rounded-full bg-gradient-to-r from-brand-600 to-accent-500 text-xs font-black text-white shadow-lg shadow-brand-500/30 hover:brightness-110 transition cursor-pointer disabled:opacity-50"
        >
          {saveLoading ? "Salvataggio..." : "Salva"}
        </button>
        {saveError && (
          <div className="p-3 rounded-lg bg-danger-500/10 border border-danger-500/20 text-danger-400 text-xs">{saveError}</div>
        )}
        {saveSuccess && (
          <div className="p-3 rounded-lg bg-success-500/10 border border-success-500/20 text-success-400 text-xs">Impostazioni salvate.</div>
        )}
      </form>
    </div>
  );
}
