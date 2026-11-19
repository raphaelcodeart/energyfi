"use client";

import { useQuery } from "@tanstack/react-query";
import type { BranchMemberRead } from "@/lib/types";
import { BranchVisualizer } from "@/components/branch-visualizer";
import { PromoterAziendaPanel } from "@/components/promoter-azienda-panel";
import { Chip, Orb } from "@/components/ui/data-cells";
import { BranchSyncButton } from "@/components/branch-sync-button";

async function fetchBranch(agentId: string): Promise<BranchMemberRead[]> {
  const res = await fetch(`/api/proxy/network/agents/${agentId}/branch`);
  if (!res.ok) throw new Error("Impossibile caricare la rete di questo promoter.");
  return res.json();
}

/**
 * Admin drill-down into one promoter's network: the same "La mia Azienda" /
 * "Rete Commerciale" components and data the promoter sees (admin roles
 * bypass branch-ownership checks, see network/router.py::_assert_branch_access),
 * without the rest of the promoter dashboard.
 */
export function AdminPromoterNetworkModal({
  agentId,
  displayName,
  onClose,
}: {
  agentId: string;
  displayName: string;
  onClose: () => void;
}) {
  const { data: branch, error: branchError, isLoading: branchLoading } = useQuery({
    queryKey: ["admin", "promoter-network", "branch", agentId],
    queryFn: () => fetchBranch(agentId),
  });

  const self = branch?.find((m) => m.depth === 0);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-fade-in">
      <div className="w-full max-w-6xl max-h-[92vh] overflow-y-auto panel rounded-3xl p-6 md:p-8 border-white/10 bg-surface-950 pop">
        <div className="flex items-start justify-between mb-7 gap-3">
          <div className="flex items-center gap-4 min-w-0">
            <div className="scale-125 origin-left">
              <Orb name={displayName.trim() || "?"} />
            </div>
            <div className="min-w-0 pl-2">
              <div className="kpi-label">Vista amministratore</div>
              <h3 className="mt-1 text-2xl font-black tracking-tight text-white">
                Rete di <span className="text-gradient">{displayName}</span>
              </h3>
              <div className="flex flex-wrap items-center gap-2 mt-2">
                {self?.promoter_code && <span className="tag-id">{self.promoter_code}</span>}
                {self?.role_name && <Chip tone="accent">{self.role_name}</Chip>}
                <span className="text-[11px] text-surface-400">
                  Gli stessi dati che vede questo promoter, senza il resto della sua dashboard
                </span>
              </div>
            </div>
          </div>
          <button onClick={onClose} aria-label="Chiudi" className="act !h-9 !w-9 !p-0 justify-center shrink-0">
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="space-y-8">
          <BranchSyncButton agentId={agentId} />
          <PromoterAziendaPanel agentId={agentId} />

          <div>
            <div className="kpi-label">Struttura</div>
            <h4 className="mt-1 mb-4 text-xl font-black tracking-tight text-white">Albero della rete</h4>
            {branchLoading ? (
              <p className="text-sm text-surface-400">Caricamento albero...</p>
            ) : branchError ? (
              <p className="text-sm text-danger-400">Impossibile caricare l&apos;albero della rete.</p>
            ) : branch && branch.length > 0 ? (
              <BranchVisualizer members={branch} />
            ) : (
              <p className="text-sm text-surface-400">Nessun membro della rete da visualizzare.</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
