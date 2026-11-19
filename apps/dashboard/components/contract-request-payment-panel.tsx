"use client";

import { useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { friendlyApiError } from "@/lib/api-error";
import { formatEuroCents as euro } from "@/lib/product-audience";
import type { ContractRequestPaymentOptionRead, ContractRequestPaymentOptionsRead } from "@/lib/types";

function sosnetCash(cents: number): string {
  return `${(cents / 100).toLocaleString("it-IT", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} SosnetCash`;
}

export function useRequestPaymentOptions(requestId: string) {
  return useQuery<ContractRequestPaymentOptionsRead>({
    queryKey: ["contract-request", requestId, "payment-options"],
    queryFn: async () => {
      const res = await fetch(`/api/proxy/contract-requests/${requestId}/payment-options`);
      if (!res.ok) throw new Error(await friendlyApiError(res));
      return res.json();
    },
    // Payment happens in another tab and is confirmed by webhook shortly after;
    // returning to this tab must reflect it.
    refetchOnWindowFocus: true,
  });
}

/** The single-payment discount badge, meant to stand out. */
function DiscountTag({ percentage }: { percentage: number }) {
  return (
    <span className="absolute -top-3.5 -right-2 rotate-3 flex flex-col items-center leading-none px-3 py-1.5 rounded-xl bg-gradient-to-br from-success-400 via-success-500 to-teal-600 text-white shadow-xl shadow-success-500/40 ring-2 ring-white/30 light:ring-white">
      <span className="text-[8px] font-bold uppercase tracking-[0.2em] opacity-90">sconto</span>
      <span className="text-xl font-black tracking-tight">-{percentage}%</span>
    </span>
  );
}

function OptionCard({
  option,
  selected,
  onSelect,
}: {
  option: ContractRequestPaymentOptionRead;
  selected: boolean;
  onSelect: () => void;
}) {
  const discounted = option.available && option.discount_cents > 0;
  return (
    <button
      onClick={() => option.available && onSelect()}
      disabled={!option.available}
      className={`relative w-full text-left p-4 rounded-xl border-2 transition ${
        !option.available
          ? "opacity-50 cursor-not-allowed bg-white/5 light:bg-surface-900/5 border-white/10 light:border-surface-300"
          : selected
            ? discounted
              ? "cursor-pointer bg-success-500/10 border-success-500"
              : "cursor-pointer bg-brand-500/10 border-brand-500/60"
            : discounted
              ? "cursor-pointer bg-success-500/[0.06] border-success-500/40 hover:border-success-500/70"
              : "cursor-pointer bg-white/5 light:bg-surface-900/5 border-white/10 light:border-surface-300 hover:bg-white/10"
      } ${discounted ? "mt-3" : ""}`}
    >
      {discounted && <DiscountTag percentage={option.discount_percentage} />}
      <div className="min-w-0 pr-12">
        <p className="text-sm font-semibold text-white light:text-surface-900">{option.label}</p>
        <p className="text-[11px] text-surface-400 light:text-surface-500 mt-0.5">
          {option.available ? option.description : option.unavailable_reason}
        </p>
      </div>
      <div className="flex items-end justify-between gap-3 mt-2">
        {discounted ? (
          <p className="text-[11px] font-semibold text-success-400">Risparmi {euro(option.discount_cents)}</p>
        ) : (
          <span />
        )}
        <div className="text-right shrink-0">
          {discounted && <p className="text-xs text-surface-500 line-through tabular-nums">{euro(option.list_total_cents)}</p>}
          <p className={`font-extrabold tabular-nums ${discounted ? "text-2xl text-success-400" : "text-lg text-brand-400"}`}>
            {euro(option.instalment_cents)}
          </p>
          {option.instalments > 1 && <p className="text-[10px] text-surface-500">al mese × {option.instalments}</p>}
        </div>
      </div>
      {discounted && (
        <p className="text-[10px] text-surface-400 light:text-surface-500 mt-2 pt-2 border-t border-success-500/20">
          Sconto sul prezzo del contratto: l&apos;IVA, se dovuta, è calcolata sul prezzo scontato.
        </p>
      )}
      {option.instalments > 1 && (
        <p className="text-[10px] text-surface-500 mt-2 pt-2 border-t border-white/5 light:border-surface-200">
          Totale {euro(option.total_cents)}
          {option.rounding_difference_cents !== 0 && (
            <span className="text-surface-600">
              {" "}({option.rounding_difference_cents > 0 ? "+" : ""}
              {(option.rounding_difference_cents / 100).toFixed(2).replace(".", ",")} € per arrotondamento delle rate)
            </span>
          )}
        </p>
      )}
    </button>
  );
}

/**
 * "Paga la pratica": one payment for every submitted, unpaid contract of the pratica.
 * Card (single payment or instalments, via Stripe) or bank transfer (single
 * payment with the same discount, settled when an administrator confirms
 * receipt). All amounts come from the server: the browser only sends a plan
 * key, and only the signed Stripe webhook or an administrator marks anything paid.
 */
export function ContractRequestPaymentPanel({ requestId }: { requestId: string }) {
  const queryClient = useQueryClient();
  const { data, error } = useRequestPaymentOptions(requestId);
  const [selected, setSelected] = useState<string | null>(null);
  const [loading, setLoading] = useState<"card" | "transfer" | null>(null);
  const [payError, setPayError] = useState<string | null>(null);
  const [opened, setOpened] = useState(false);
  const [showCardInstead, setShowCardInstead] = useState(false);

  async function refresh() {
    await queryClient.invalidateQueries({ queryKey: ["contract-request", requestId] });
    await queryClient.invalidateQueries({ queryKey: ["contract-requests"] });
  }

  async function handlePayCard() {
    if (!selected) return;
    setLoading("card");
    setPayError(null);
    try {
      const origin = window.location.origin;
      const successUrl = `${origin}/customer?tab=contracts&payment=success`;
      const cancelUrl = `${origin}/customer?tab=contracts&payment=cancelled`;
      const res = await fetch(
        `/api/proxy/contract-requests/${requestId}/checkout-session?success_url=${encodeURIComponent(successUrl)}&cancel_url=${encodeURIComponent(cancelUrl)}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ payment_plan: selected }),
        }
      );
      if (!res.ok) throw new Error(await friendlyApiError(res));
      const { checkout_url } = await res.json();
      // New tab, never a redirect, so the pratica stays open.
      window.open(checkout_url, "_blank", "noopener,noreferrer");
      setOpened(true);
    } catch (err: any) {
      setPayError(err.message || "Impossibile avviare il pagamento.");
    } finally {
      setLoading(null);
    }
  }

  async function handlePayTransfer() {
    setLoading("transfer");
    setPayError(null);
    try {
      const res = await fetch(`/api/proxy/contract-requests/${requestId}/bank-transfer`, { method: "POST" });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      setShowCardInstead(false);
      await refresh();
    } catch (err: any) {
      setPayError(err.message || "Impossibile scegliere il bonifico.");
    } finally {
      setLoading(null);
    }
  }

  if (error) return <p className="text-sm text-danger-400">{(error as Error).message}</p>;
  if (!data) return <div className="h-32 rounded-2xl bg-white/5 light:bg-surface-900/5 animate-pulse" />;

  if (data.lines.length === 0) {
    return (
      <div className="rounded-2xl p-5 border border-success-500/25 bg-success-500/10">
        <p className="text-sm font-semibold text-success-400">
          {data.points_paid > 0 ? "Pagamento ricevuto" : "Niente da pagare in questo momento"}
        </p>
        <p className="text-xs text-surface-300 light:text-surface-600 mt-1">
          {data.points_paid > 0
            ? "Ogni contratto si attiva appena l'amministrazione approva i suoi documenti. Se ne mancano ancora, puoi caricarli quando vuoi."
            : "I contratti di questa pratica non sono in attesa di pagamento."}
        </p>
      </div>
    );
  }

  if (data.bank_transfer_pending && !showCardInstead) {
    return (
      <BankTransferInstructions
        data={data}
        requestId={requestId}
        onChanged={refresh}
        onPayByCard={() => setShowCardInstead(true)}
      />
    );
  }

  const selectedOption = data.options.find((o) => o.key === selected) ?? null;
  const fullOption = data.options.find((o) => o.instalments === 1) ?? null;
  const transferPossible = data.bank_transfer_available && !!fullOption?.available;
  const transferBlocked = selected !== null && selected !== fullOption?.key;

  if (!data.card_available && !transferPossible) {
    return (
      <div className="panel panel-hover rounded-2xl p-5 border-white/5 light:border-surface-200 bg-surface-950/40 light:bg-white/70">
        <p className="text-sm text-warn-400">
          Il pagamento non è ancora attivo. Contatta l&apos;assistenza per completare l&apos;attivazione.
        </p>
      </div>
    );
  }

  return (
    <div className="panel panel-hover rounded-2xl p-5 border-white/5 light:border-surface-200 bg-surface-950/40 light:bg-white/70">
      <h4 className="text-sm font-semibold text-white light:text-surface-900">Scegli come pagare</h4>
      <p className="text-xs text-surface-400 light:text-surface-500 mt-1">
        Un solo pagamento per {data.lines.length === 1 ? "il contratto" : `tutti i ${data.lines.length} contratti`} della
        pratica. Ogni contratto resta indipendente: si attiva quando i suoi documenti sono approvati.
      </p>

      <div className="mt-3 rounded-xl border border-white/10 light:border-surface-200 divide-y divide-white/5 light:divide-surface-200">
        {data.lines.map((line) => (
          <div key={line.contract_id} className="flex items-center justify-between gap-3 px-3 py-2 text-xs">
            <span className="text-surface-300 light:text-surface-600 min-w-0 truncate">{line.label}</span>
            <span className="text-white light:text-surface-900 font-semibold tabular-nums shrink-0">{euro(line.gross_cents)}</span>
          </div>
        ))}
        <div className="flex items-center justify-between gap-3 px-3 py-2 text-sm">
          <span className="font-semibold text-surface-300 light:text-surface-600">Totale</span>
          <span className="font-bold text-white light:text-surface-900 tabular-nums">{euro(data.total_gross_cents)}</span>
        </div>
      </div>

      {data.cashback_total_cents > 0 && (
        <div className="mt-3 p-3 rounded-xl bg-success-500/10 border border-success-500/20">
          <p className="text-xs text-success-400 font-semibold">
            Ricevi in cashback: {sosnetCash(selectedOption?.cashback_cents ?? data.cashback_total_cents)}
          </p>
          <p className="text-[10px] text-surface-400 light:text-surface-500 mt-0.5">
            {data.cashback_mode === "UPFRONT"
              ? "Accreditato per intero sul tuo wallet appena paghi — anche a rate, già alla prima rata."
              : "Accreditato in automatico sul tuo wallet appena paghi — con le rate, una parte a ogni rata pagata."}
          </p>
        </div>
      )}

      <div className="space-y-2.5 mt-4">
        {data.options.map((option) => (
          <OptionCard
            key={option.key}
            option={option}
            selected={selected === option.key}
            onSelect={() => setSelected(option.key)}
          />
        ))}
      </div>

      {payError && (
        <div className="mt-3 p-3 rounded-lg bg-danger-500/10 border border-danger-500/20 text-danger-400 text-xs">{payError}</div>
      )}

      <div className={`grid gap-2 mt-4 ${data.card_available && transferPossible ? "sm:grid-cols-2" : ""}`}>
        {data.card_available && (
          <button
            onClick={handlePayCard}
            disabled={!selected || loading !== null}
            className="w-full rounded-xl bg-gradient-to-r from-brand-600 to-accent-500 hover:from-brand-500 hover:to-accent-400 py-2.5 text-sm font-semibold text-white shadow-lg transition disabled:opacity-50 cursor-pointer"
          >
            {loading === "card" ? "Apertura del pagamento..." : selected ? "Paga con carta" : "Scegli una modalità per pagare con carta"}
          </button>
        )}
        {transferPossible && (
          <button
            onClick={handlePayTransfer}
            disabled={loading !== null || transferBlocked}
            title={transferBlocked ? "Il bonifico è per il pagamento in un'unica soluzione" : undefined}
            className="w-full rounded-xl bg-white/5 light:bg-surface-900/5 hover:bg-white/10 border-2 border-success-500/40 py-2.5 text-sm font-semibold text-white light:text-surface-900 transition disabled:opacity-50 cursor-pointer"
          >
            {loading === "transfer" ? "..." : `Paga con bonifico · ${euro(fullOption?.total_cents ?? 0)}`}
          </button>
        )}
      </div>
      <p className="text-[10px] text-surface-500 mt-2 text-center">
        {opened
          ? "Completa il pagamento nella scheda che si è aperta, poi torna qui: questa pagina si aggiorna da sola."
          : transferPossible
            ? "Con carta il pagamento si apre in una nuova scheda. Il bonifico è in un'unica soluzione, con lo stesso sconto: i contratti risultano pagati appena l'amministrazione lo riceve."
            : "Il pagamento si apre in una nuova scheda. Non serve aspettare l'approvazione dei documenti."}
      </p>
    </div>
  );
}

function BankTransferInstructions({
  data,
  requestId,
  onChanged,
  onPayByCard,
}: {
  data: ContractRequestPaymentOptionsRead;
  requestId: string;
  onChanged: () => Promise<void>;
  onPayByCard: () => void;
}) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState<string | null>(null);
  const fullOption = data.options.find((o) => o.instalments === 1);

  async function upload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setUploading(true);
    setError(null);
    try {
      const body = new FormData();
      body.append("file", file);
      const res = await fetch(`/api/proxy/contract-requests/${requestId}/bank-transfer/proof`, { method: "POST", body });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      await onChanged();
    } catch (err: any) {
      setError(err.message || "Impossibile caricare la ricevuta.");
    } finally {
      setUploading(false);
    }
  }

  function copy(label: string, value: string | null) {
    if (!value || !navigator.clipboard) return;
    navigator.clipboard
      .writeText(value)
      .then(() => {
        setCopied(label);
        window.setTimeout(() => setCopied(null), 1500);
      })
      .catch(() => undefined);
  }

  const row = (label: string, value: string | null, mono = false) => (
    <div className="flex items-center justify-between gap-3 py-2">
      <span className="text-[11px] text-surface-500 shrink-0">{label}</span>
      <span className="flex items-center gap-2 min-w-0">
        <span className={`text-sm text-white light:text-surface-900 font-semibold truncate ${mono ? "font-mono" : ""}`}>{value ?? "—"}</span>
        {value && (
          <button onClick={() => copy(label, value)} className="text-[10px] font-semibold text-brand-400 hover:text-brand-300 cursor-pointer shrink-0">
            {copied === label ? "Copiato" : "Copia"}
          </button>
        )}
      </span>
    </div>
  );

  return (
    <div className="panel panel-hover rounded-2xl p-5 border-2 border-warn-500/30 bg-surface-950/40 light:bg-white/70 space-y-4">
      <input ref={fileRef} type="file" accept="application/pdf,image/jpeg,image/png" className="hidden" onChange={upload} />
      <div>
        <p className="text-[10px] font-bold uppercase tracking-wider text-warn-400">Pagamento con bonifico in attesa</p>
        <div className="flex items-end gap-3 flex-wrap mt-1">
          <p className="text-3xl font-extrabold text-white light:text-surface-900 tabular-nums">{euro(data.bank_transfer_total_cents ?? 0)}</p>
          {fullOption && fullOption.discount_cents > 0 && (
            <span className="mb-1 flex items-center gap-2">
              <span className="text-sm text-surface-500 line-through tabular-nums">{euro(fullOption.list_total_cents)}</span>
              <span className="px-2 py-0.5 rounded-lg text-xs font-black bg-gradient-to-r from-success-500 to-teal-500 text-white">
                -{fullOption.discount_percentage}%
              </span>
            </span>
          )}
        </div>
        <p className="text-xs text-surface-400 light:text-surface-500 mt-1">
          I contratti risultano pagati appena l&apos;amministrazione riceve il bonifico. Nel frattempo puoi caricare i documenti.
        </p>
      </div>

      <div className="rounded-xl border border-white/10 light:border-surface-200 px-4 divide-y divide-white/5 light:divide-surface-200">
        {row("Importo", euro(data.bank_transfer_total_cents ?? 0))}
        {row("IBAN", data.bank_iban, true)}
        {row("Intestatario", data.bank_account_holder)}
        {row("Causale", data.bank_transfer_reference, true)}
      </div>
      {data.bank_transfer_instructions && (
        <p className="text-[11px] text-surface-400 light:text-surface-500">{data.bank_transfer_instructions}</p>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <button
          onClick={() => fileRef.current?.click()}
          disabled={uploading}
          className="px-4 py-2 rounded-xl bg-brand-600 hover:bg-brand-500 text-xs font-semibold text-white transition cursor-pointer disabled:opacity-50"
        >
          {uploading ? "Caricamento..." : data.payment_proof_uploaded_at ? "Sostituisci la ricevuta" : "Carica la ricevuta del bonifico"}
        </button>
        {data.payment_proof_uploaded_at && <span className="text-[11px] text-success-400">✓ Ricevuta caricata</span>}
        {data.card_available && (
          <button onClick={onPayByCard} className="ml-auto text-[11px] font-semibold text-surface-400 hover:text-brand-400 cursor-pointer">
            Preferisci pagare con carta?
          </button>
        )}
      </div>
      {error && <p className="text-xs text-danger-400">{error}</p>}
    </div>
  );
}
