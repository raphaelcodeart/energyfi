"use client";

import { type CSSProperties, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { friendlyApiError } from "@/lib/api-error";
import { formatEuroCents as euro } from "@/lib/product-audience";
import type { CommissionPreviewRead, ContractCommissionLogRead } from "@/lib/types";
import { Chip, Figure, Identity, Orb, RowActions } from "@/components/ui/data-cells";

function formatDate(iso: string | null): string {
  return iso ? new Date(iso).toLocaleDateString("it-IT", { day: "2-digit", month: "short", year: "numeric" }) : "—";
}

const SOURCE_LABELS: Record<string, string> = {
  STRIPE_CHECKOUT: "Stripe (primo pagamento)",
  STRIPE_INVOICE: "Stripe (rata mensile)",
  ADMIN: "Confermata a mano",
};

/**
 * Commission preview the administrator reviews before approving. Every figure
 * comes from the server (commissions/services/preview.py): the upline, what
 * each earns, and how it spreads over the customer's payments. Layout only;
 * reused read-only in the log.
 */
export function CommissionPreviewView({ preview }: { preview: CommissionPreviewRead }) {
  const { payment } = preview;
  const payees = preview.beneficiaries.filter((b) => b.total_cents > 0 && b.beneficiary_kind === "AGENT").length;
  const blocking = preview.blocking_errors ?? [];
  const split = payment.paid && (payment.instalments ?? 1) > 1;
  const firstRow = payment.schedule[0];

  const margin = preview.reference_margin_cents;
  const totalShares = preview.beneficiaries.reduce((acc, b) => acc + Math.max(0, b.total_cents), 0);

  return (
    <div className="space-y-5">
      {blocking.length > 0 && (
        <div className="space-y-1 rounded-2xl border border-danger-500/30 bg-danger-500/15 p-4">
          <p className="text-sm font-bold text-danger-200">Le provvigioni di questo contratto non si possono ancora calcolare</p>
          {blocking.map((e) => <p key={e} className="text-xs text-danger-300">{e}</p>)}
          <p className="text-[11px] text-surface-300">Finché non è risolto l&apos;anteprima non si può accettare e il contratto non parte.</p>
        </div>
      )}
      <div className="panel relative overflow-hidden rounded-3xl p-5">
        <div className="flex flex-wrap items-end gap-x-8 gap-y-3">
          <div>
            <p className="kpi-label">Provvigioni totali su questo contratto</p>
            <p className="kpi-value mt-2">{euro(preview.total_commission_cents)}</p>
            <p className="mt-1.5 text-xs text-surface-300">a {payees} {payees === 1 ? "collaboratore" : "collaboratori"}</p>
          </div>
          {preview.company_share_cents ? (
            <div>
              <p className="kpi-label">Quota azienda</p>
              <p className="mt-2 text-2xl font-black tabular-nums text-white">{euro(preview.company_share_cents)}</p>
            </div>
          ) : null}
          {margin != null && margin > 0 && (
            <div className="min-w-[180px] flex-1">
              <p className="kpi-label">Margine distribuito alla rete</p>
              <div className="meter mt-3 h-2"><i style={{ width: `${Math.max(3, Math.min(100, (preview.total_commission_cents / margin) * 100))}%` }} /></div>
              <p className="mt-1 text-[11px] tabular-nums text-surface-300">{Math.round((preview.total_commission_cents / margin) * 100)}% di {euro(margin)}</p>
            </div>
          )}
        </div>
        {preview.plan && (
          <div className="mt-4 flex flex-wrap items-center gap-2 text-[11px] text-surface-300">
            <Chip tone="accent">{preview.plan.name} v{preview.plan.version}</Chip>
            <span>Margine {preview.reference_margin_cents != null ? euro(preview.reference_margin_cents) : "—"}</span>
            {preview.seller_role ? <span>· venditore come <strong className="text-white">{preview.seller_role}</strong></span> : null}
            {preview.sold_at ? <span>· vendita del {formatDate(preview.sold_at)}</span> : null}
          </div>
        )}
        <p className="mt-3 text-xs text-surface-300">
          {!payment.paid
            ? "Il cliente non ha ancora pagato: le provvigioni partiranno da sole al primo pagamento, divise come mostrato sotto."
            : split
              ? `Pagamento in ${payment.instalments} rate: all'approvazione parte la quota della 1ª rata (${euro(firstRow?.commission_cents ?? 0)}); le altre partono a ogni rata incassata, fino al ${formatDate(payment.last_release_date)}.`
              : "Pagamento unico: all'approvazione partono tutte le provvigioni, una volta sola."}
        </p>
        <span className="pointer-events-none absolute -right-8 -top-8 h-32 w-32 rounded-full bg-gradient-to-br from-brand-400/40 to-accent-400/10 blur-2xl" />
      </div>

      {preview.warnings.length > 0 && (
        <ul className="space-y-1.5">
          {preview.warnings.map((w) => (
            <li key={w} className="rounded-xl border border-warn-500/30 bg-warn-500/15 p-2.5 text-xs text-warn-300">{w}</li>
          ))}
        </ul>
      )}

      <div>
        <p className="kpi-label mb-3">Chi riceve cosa — secondo lo Split Plan</p>
        <div className="stagger space-y-2">
          {preview.beneficiaries.map((b, i) => {
            const base = margin != null && margin > 0 ? margin : totalShares;
            const ratio = base > 0 ? Math.max(0, b.total_cents) / base : null;
            return (
              <div
                key={b.key}
                style={{ "--i": i } as CSSProperties}
                className={`flex items-center justify-between gap-4 rounded-2xl border p-4 ${
                  b.total_cents > 0 ? "border-white/10 bg-white/5" : "border-dashed border-white/10 opacity-60"
                }`}
              >
                <div className="min-w-0 flex-1">
                  <Identity
                    name={b.name}
                    detail={<>{b.role}{b.role_code ? <> · <span className="font-semibold text-brand-300">{b.role_code}</span></> : null}</>}
                  />
                  <div className="mt-2 flex flex-wrap items-center gap-2">
                    <Chip tone={b.beneficiary_kind === "COMPANY" ? "muted" : "accent"}>{b.movement_label}</Chip>
                  </div>
                  <p className="mt-1.5 text-[10.5px] text-surface-400">{b.explanation}</p>
                </div>
                <div className="shrink-0">
                  <Figure
                    value={euro(b.total_cents)}
                    detail={split && b.total_cents > 0 && firstRow
                      ? `${euro(firstRow.per_beneficiary_cents[b.key] ?? 0)} a rata × ${payment.instalments}`
                      : ratio != null ? `${Math.round(ratio * 100)}% ${margin != null && margin > 0 ? "del margine" : "delle quote"}` : undefined}
                    ratio={ratio != null ? Math.min(1, ratio) : null}
                  />
                </div>
              </div>
            );
          })}
          {preview.beneficiaries.length === 0 && (
            <div className="flex flex-col items-center gap-2 py-6 text-center text-surface-400">
              <Orb name="vuoto" icon={<span className="text-sm">∅</span>} />
              <span className="text-sm">Nessuna quota da mostrare.</span>
            </div>
          )}
        </div>
      </div>

      <div>
        <p className="kpi-label mb-3">Come partono le provvigioni</p>
        {payment.paid ? (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr>
                  <th className="px-4 py-3">Rata</th>
                  <th className="px-4 py-3">Rilascio</th>
                  <th className="px-4 py-3 text-right">Dal cliente</th>
                  <th className="px-4 py-3 text-right">Alla rete</th>
                </tr>
              </thead>
              <tbody>
                {payment.schedule.map((row) => (
                  <tr key={row.number}>
                    <td className="px-4 py-3">
                      <Identity name={`Rata ${row.number}`} detail={`di ${payment.instalments} · ${formatDate(row.due_date)}`} icon={<span className="text-sm font-black">{row.number}</span>} />
                    </td>
                    <td className="px-4 py-3 text-[11px] text-surface-300">{row.release}</td>
                    <td className="px-4 py-3 text-right tabular-nums text-surface-300">{euro(row.customer_amount_cents)}</td>
                    <td className="px-4 py-3">
                      <div className="ml-auto w-fit">
                        <Figure
                          value={euro(row.commission_cents)}
                          ratio={preview.total_commission_cents > 0 ? row.commission_cents / preview.total_commission_cents : null}
                        />
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            {payment.scenarios.map((s) => (
              <div key={s.plan_key} data-tilt className="panel rounded-2xl p-4">
                <p className="kpi-label">Se paga: {s.plan_label.toLowerCase()}</p>
                <p className="mt-2 text-2xl font-black tabular-nums text-white">{euro(s.commission_per_instalment_cents)}</p>
                <p className="mt-1 text-[10.5px] text-surface-400">
                  {s.instalments === 1 ? "tutte subito, una volta" : `a ogni rata incassata, per ${s.instalments} mesi`}
                </p>
              </div>
            ))}
          </div>
        )}
      </div>

      {preview.customer_cashback_cents > 0 && (
        <p className="text-[11px] text-surface-300">
          Il cliente riceve inoltre{" "}
          <strong className="tabular-nums text-success-300">
            {(preview.customer_cashback_cents / 100).toLocaleString("it-IT", { minimumFractionDigits: 2 })} SosnetCash
          </strong>{" "}
          di cashback sul proprio wallet, man mano che paga. Non è una provvigione e non va ai promoter.
        </p>
      )}
    </div>
  );
}

async function fetchLog(contractId: string): Promise<ContractCommissionLogRead> {
  const res = await fetch(`/api/proxy/contracts/${contractId}/commission-log`);
  if (!res.ok) throw new Error("Impossibile caricare il registro provvigioni.");
  return res.json();
}

/**
 * A contract's "Registro provvigioni": the accepted preview (who, when, what
 * they saw) and the instalment schedule with what each payment has released.
 * An instalment Stripe did not collect can be confirmed by hand here.
 */
export function ContractCommissionLog({ contractId }: { contractId: string }) {
  const queryClient = useQueryClient();
  const { data, error } = useQuery({ queryKey: ["admin", "commission-log", contractId], queryFn: () => fetchLog(contractId) });
  const [showPreview, setShowPreview] = useState(false);
  const [confirming, setConfirming] = useState<number | null>(null);
  const [confirmError, setConfirmError] = useState<string | null>(null);

  async function handleConfirm(number: number) {
    if (!window.confirm(
      `Confermi di aver ricevuto la rata ${number}? Se il contratto è attivo partono subito le provvigioni di questa rata. ` +
      "Usalo solo se Stripe non l'ha incassata (es. il cliente ha pagato con bonifico)."
    )) return;
    setConfirming(number);
    setConfirmError(null);
    try {
      const res = await fetch(`/api/proxy/contracts/${contractId}/instalments/${number}/confirm`, { method: "POST" });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      await queryClient.invalidateQueries({ queryKey: ["admin", "commission-log", contractId] });
      await queryClient.invalidateQueries({ queryKey: ["admin", "commissions"] });
    } catch (err: any) {
      setConfirmError(err.message || "Impossibile confermare la rata.");
    } finally {
      setConfirming(null);
    }
  }

  if (error) return <p className="text-sm text-danger-300">Impossibile caricare il registro provvigioni.</p>;
  if (!data) return <div className="h-20 animate-pulse rounded-2xl bg-white/5" />;

  return (
    <div className="space-y-5">
      {data.accepted_plan ? (
        <div className="panel rounded-3xl p-5">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <p className="kpi-label">Anteprima accettata</p>
              <p className="mt-1 text-2xl font-black tabular-nums text-white">{euro(data.accepted_plan.total_commission_cents)}</p>
              <p className="mt-1 text-xs text-surface-300">
                il <strong className="text-white">{new Date(data.accepted_plan.accepted_at).toLocaleString("it-IT")}</strong>
                {data.accepted_plan.accepted_by && <> da <strong className="text-white">{data.accepted_plan.accepted_by}</strong></>}
              </p>
            </div>
            <button onClick={() => setShowPreview((v) => !v)} className="act">
              {showPreview ? "Nascondi anteprima" : "Apri l'anteprima accettata"}
            </button>
          </div>
          {showPreview && (
            <div className="rise mt-5">
              <CommissionPreviewView preview={data.accepted_plan.preview} />
            </div>
          )}
        </div>
      ) : (
        <div className="flex flex-col items-center gap-2 rounded-2xl border border-dashed border-white/15 p-6 text-center text-surface-400">
          <Orb name="anteprima" icon={<span className="text-sm">?</span>} />
          <span className="text-xs">Nessuna anteprima accettata: il contratto è stato approvato prima di questa funzione, oppure non è ancora approvato.</span>
        </div>
      )}

      {data.instalments.length > 0 && (
        <div>
          <p className="kpi-label mb-3">Rate e provvigioni rilasciate</p>
          {confirmError && (
            <div className="mb-2 rounded-xl border border-danger-500/30 bg-danger-500/15 p-2.5 text-xs text-danger-300">{confirmError}</div>
          )}
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr>
                  <th className="px-4 py-3">Rata</th>
                  <th className="px-4 py-3">Incasso</th>
                  <th className="px-4 py-3">Provvigioni</th>
                  <th className="px-4 py-3 text-right">Valore</th>
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody>
                {data.instalments.map((r) => (
                  <tr key={r.number}>
                    <td className="px-4 py-3">
                      <Identity
                        name={`Rata ${r.number}`}
                        detail={`di ${r.instalments_total} · prevista ${formatDate(r.due_date)}`}
                        icon={<span className="text-sm font-black">{r.number}</span>}
                      />
                    </td>
                    <td className="px-4 py-3">
                      {r.status === "PAID" ? (
                        <div className="space-y-1">
                          <Chip tone="ok">Pagata il {formatDate(r.paid_at)}</Chip>
                          <div className="text-[10.5px] text-surface-400">
                            {SOURCE_LABELS[r.payment_source ?? ""] ?? r.payment_source}
                            {r.confirmed_by ? ` · ${r.confirmed_by}` : ""}
                          </div>
                        </div>
                      ) : r.status === "FAILED" ? (
                        <Chip tone="bad">Addebito non riuscito</Chip>
                      ) : (
                        <Chip tone="warn" live>In attesa</Chip>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      {r.commission_released_at ? (
                        <Chip tone="ok">Partite il {formatDate(r.commission_released_at)}</Chip>
                      ) : r.commission_pending ? (
                        <Chip tone="info" live>In calcolo…</Chip>
                      ) : r.status === "PAID" ? (
                        <Chip tone="warn">All&apos;attivazione del contratto</Chip>
                      ) : (
                        <Chip tone="muted">Alla rata incassata</Chip>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <div className="ml-auto w-fit"><Figure value={euro(r.amount_cents)} detail="importo rata" /></div>
                    </td>
                    <td className="px-4 py-3">
                      <RowActions>
                        {r.status !== "PAID" && (
                          <button
                            onClick={() => handleConfirm(r.number)}
                            disabled={confirming === r.number}
                            className="act act-primary whitespace-nowrap"
                          >
                            {confirming === r.number ? "..." : "Conferma rata ricevuta"}
                          </button>
                        )}
                      </RowActions>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
