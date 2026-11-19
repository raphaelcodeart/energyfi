"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { ContractCommissionLog } from "@/components/contract-commission-preview";
import { friendlyApiError } from "@/lib/api-error";
import { MOVEMENT_STATUS_LABELS as STATUS_LABELS, MOVEMENT_TYPE_LABELS } from "@/lib/commission-labels";
import { Chip, type ChipTone, Figure, IdTag, Identity, KpiTile, Orb, RowActions } from "@/components/ui/data-cells";
import { formatEuroCents as euro } from "@/lib/product-audience";
import type { CommissionMovementDetailRead } from "@/lib/types";

async function fetchContractMovements(contractId: string): Promise<CommissionMovementDetailRead[]> {
  const res = await fetch(`/api/proxy/commissions/movements?contract_id=${contractId}&include_company=true`);
  if (!res.ok) throw new Error("Impossibile caricare le provvigioni di questo contratto.");
  return res.json();
}

function statusTone(status: string): ChipTone {
  switch (status) {
    case "PAID":
    case "APPROVED":
      return "ok";
    case "PAYABLE":
      return "accent";
    case "PENDING":
    case "ACCRUED":
      return "warn";
    case "CANCELLED":
    case "REVERSED":
      return "bad";
    case "RETAINED":
      return "muted";
    default:
      return "info";
  }
}

function typeTone(type: string): ChipTone {
  if (type === "DIRECT") return "accent";
  if (type === "REVERSAL") return "bad";
  if (type === "COMPANY_SHARE") return "muted";
  return "info";
}

export function ContractCommissionsModal({
  contractId,
  onClose,
}: {
  contractId: string;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [payingId, setPayingId] = useState<string | null>(null);
  const [payingAll, setPayingAll] = useState(false);
  const [payError, setPayError] = useState<string | null>(null);

  const { data: movements, error, isLoading } = useQuery({
    queryKey: ["admin", "commissions", "by-contract", contractId],
    queryFn: () => fetchContractMovements(contractId),
  });

  // Seller (level 0) first, then the upline, the company last.
  const sorted = [...(movements ?? [])].sort(
    (a, b) => (a.depth_from_producer ?? 99) - (b.depth_from_producer ?? 99)
  );
  const first = sorted[0];
  const agentRows = sorted.filter((m) => m.beneficiary_kind === "AGENT");
  const totalAccrued = agentRows.filter((m) => m.status === "PENDING" || m.status === "ACCRUED" || m.status === "APPROVED" || m.status === "PAYABLE").reduce((sum, m) => sum + m.amount_cents, 0);
  const totalPaid = agentRows.filter((m) => m.status === "PAID").reduce((sum, m) => sum + m.amount_cents, 0);
  const totalAll = sorted.filter((m) => m.status !== "CANCELLED").reduce((sum, m) => sum + m.amount_cents, 0);
  const toApprove = agentRows.filter((m) => m.status === "PENDING" || m.status === "ACCRUED").map((m) => m.id);
  const toPay = agentRows.filter((m) => m.status === "APPROVED" || m.status === "PAYABLE").map((m) => m.id);

  async function transition(ids: string[], toStatus: string, busyKey: string) {
    if (busyKey === "all") setPayingAll(true);
    else setPayingId(busyKey);
    setPayError(null);
    try {
      const res = await fetch("/api/proxy/commissions/movements/transition", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ movement_ids: ids, to_status: toStatus, note: "Dalla scheda provvigioni del contratto" }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      await queryClient.invalidateQueries({ queryKey: ["admin", "commissions"] });
    } catch (err: any) {
      setPayError(err.message || "Operazione non riuscita.");
    } finally {
      setPayingAll(false);
      setPayingId(null);
    }
  }

  return (
    <div className="animate-fade-in fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm">
      <div className="panel pop max-h-[85vh] w-full max-w-4xl overflow-y-auto rounded-3xl p-6 md:p-8">
        <div className="mb-6 flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="kpi-label">Contratto <IdTag id={contractId} /></p>
            <h3 className="mt-1 text-2xl font-black tracking-tight text-white">Provvigioni generate da questo contratto</h3>
            {first && (
              <div className="mt-1.5 flex flex-wrap items-center gap-2 text-xs text-surface-300">
                <span>{first.customer_name} — {first.product_name}</span>
                <span className="text-surface-500">·</span>
                <span>Venduto da {first.producer_name}</span>
              </div>
            )}
          </div>
          <div className="flex shrink-0 flex-wrap items-center justify-end gap-2">
            {toApprove.length > 0 && (
              <button
                onClick={() => transition(toApprove, "APPROVED", "all")}
                disabled={payingAll}
                className="act"
              >
                Approva tutte ({toApprove.length})
              </button>
            )}
            {toPay.length > 0 && (
              <button
                onClick={() => transition(toPay, "PAID", "all")}
                disabled={payingAll}
                className="act act-primary"
              >
                {payingAll ? "..." : `Paga le approvate (${toPay.length})`}
              </button>
            )}
            <button
              onClick={onClose}
              aria-label="Chiudi"
              className="act !px-2"
            >
              <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>

        {error && (
          <p className="mb-4 text-sm text-danger-300">Impossibile caricare le provvigioni di questo contratto.</p>
        )}
        {payError && (
          <div className="mb-4 rounded-xl border border-danger-500/30 bg-danger-500/15 p-3 text-xs text-danger-300">{payError}</div>
        )}

        <div className="mb-7 grid grid-cols-1 gap-3 sm:grid-cols-3">
          <KpiTile label="Totale movimenti" value={isLoading ? "…" : euro(totalAll)} />
          <KpiTile label="Da pagare" value={isLoading ? "…" : euro(totalAccrued)} hint="da approvare o approvate" />
          <KpiTile label="Pagate" value={isLoading ? "…" : euro(totalPaid)} />
        </div>

        <p className="kpi-label">Rate</p>
        <h4 className="mb-3 mt-1 text-xl font-black tracking-tight text-white">Registro provvigioni</h4>
        <div className="mb-8">
          <ContractCommissionLog contractId={contractId} />
        </div>

        <p className="kpi-label">Contabilità</p>
        <h4 className="mb-3 mt-1 text-xl font-black tracking-tight text-white">Movimenti scritti in contabilità</h4>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr>
                <th className="px-4 py-3">Beneficiario</th>
                <th className="px-4 py-3">Posizione</th>
                <th className="px-4 py-3">Natura</th>
                <th className="px-4 py-3 text-right">Valore</th>
                <th className="px-4 py-3">Situazione</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {isLoading && (
                <tr><td colSpan={6} className="px-4 py-10 text-center text-surface-400">Caricamento...</td></tr>
              )}
              {!isLoading && sorted.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-4 py-10">
                    <div className="flex flex-col items-center gap-2 text-center text-surface-400">
                      <Orb name="vuoto" icon={<span className="text-sm">€</span>} />
                      <span className="text-sm">Nessuna provvigione ancora calcolata per questo contratto.</span>
                    </div>
                  </td>
                </tr>
              )}
              {sorted.map((m) => (
                <tr key={m.id}>
                  <td className="px-4 py-3">
                    <Identity name={m.agent_name} detail={<span className="font-mono">{m.agent_promoter_code}</span>} />
                  </td>
                  <td className="px-4 py-3">
                    <div className="font-semibold text-white">
                      {m.beneficiary_kind === "COMPANY" ? "Azienda" : m.depth_from_producer === 0 ? "Venditore" : m.depth_from_producer != null ? `Livello ${m.depth_from_producer}` : m.rule_label ?? "—"}
                    </div>
                    <div className="text-[10.5px] font-semibold text-brand-300">{m.role_at_calculation ?? "—"}</div>
                  </td>
                  <td className="px-4 py-3">
                    <Chip tone={typeTone(m.movement_type)}>{MOVEMENT_TYPE_LABELS[m.movement_type] ?? m.movement_type}</Chip>
                  </td>
                  <td className="px-4 py-3">
                    <div className="ml-auto w-fit">
                      <Figure
                        value={euro(m.amount_cents)}
                        detail={totalAll > 0 && m.status !== "CANCELLED" ? `${Math.round((m.amount_cents / totalAll) * 100)}% del totale` : undefined}
                        ratio={totalAll > 0 && m.status !== "CANCELLED" ? Math.max(0, Math.min(1, m.amount_cents / totalAll)) : null}
                      />
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <Chip tone={statusTone(m.status)} live={m.status === "PENDING" || m.status === "ACCRUED"}>
                      {STATUS_LABELS[m.status] ?? m.status}
                    </Chip>
                  </td>
                  <td className="px-4 py-3">
                    <RowActions>
                      {m.beneficiary_kind === "AGENT" && (m.status === "PENDING" || m.status === "ACCRUED") && (
                        <button
                          onClick={() => transition([m.id], "APPROVED", m.id)}
                          disabled={payingId === m.id}
                          className="act act-primary"
                        >
                          {payingId === m.id ? "..." : "Approva"}
                        </button>
                      )}
                      {m.beneficiary_kind === "AGENT" && (m.status === "APPROVED" || m.status === "PAYABLE") && (
                        <button
                          onClick={() => transition([m.id], "PAID", m.id)}
                          disabled={payingId === m.id}
                          className="act act-primary"
                        >
                          {payingId === m.id ? "..." : "Segna pagata"}
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
    </div>
  );
}
