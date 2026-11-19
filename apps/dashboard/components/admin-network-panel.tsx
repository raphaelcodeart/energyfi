"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { AgentCardModal } from "@/components/agent-card-page";
import { NetworkTree } from "@/components/affiliate/network-tree";
import { affiliateGet, type Catalog } from "@/lib/affiliate";

/** The whole commercial network, opened one branch at a time: the server
    sends 100 people per branch (biggest first) and searches by name, code or
    email, so tens of thousands of people open in a moment. A person's full
    card (levels, contracts, products) opens from the side panel. */
export function AdminNetworkPanel() {
  const [selected, setSelected] = useState<string | null>(null);
  const { data: catalog } = useQuery({
    queryKey: ["affiliate", "catalog"],
    queryFn: () => affiliateGet<Catalog>("/catalog"),
    staleTime: 10 * 60_000,
  });

  return (
    <div className="panel panel-hover rounded-2xl p-6 border-white/5 light:border-surface-200 bg-surface-950/40 light:bg-white/70">
      <div className="mb-4">
        <h3 className="text-lg font-semibold text-white light:text-surface-900">Rete Commerciale</h3>
        <p className="text-xs text-surface-400 light:text-surface-500">
          Apri un ramo per vedere chi c&apos;è sotto; tocca una persona per la sua scheda e per aggiornare la sua rete da Mamify.
        </p>
      </div>
      <NetworkTree base="admin" levels={catalog?.config.career_levels} onOpenDetail={setSelected}
        emptyText="Nessun collaboratore nella rete." />
      {selected && (
        <AgentCardModal agentId={selected} onClose={() => setSelected(null)} onOpenAgent={(id) => setSelected(id)} />
      )}
    </div>
  );
}
