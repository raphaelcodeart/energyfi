"use client";

import { useState } from "react";
import type { BranchMemberRead } from "@/lib/types";
import { NetworkChart, type TreeNode } from "@/components/network-chart";
import { AgentCardModal } from "@/components/agent-card-page";

function buildTree(members: BranchMemberRead[]): TreeNode | null {
  if (!members || members.length === 0) return null;

  // Built strictly from parent_agent_id, not row order: the API query has no
  // guaranteed ORDER BY. Every member is either the root (parent_agent_id null)
  // or has its parent in the same list.
  const nodesById = new Map<string, TreeNode>();
  for (const m of members) {
    nodesById.set(m.agent_id, {
      agent_id: m.agent_id,
      depth: m.depth,
      display_name: m.display_name,
      promoter_code: m.promoter_code,
      status: m.status,
      role_label: m.role_name ?? null,
      is_frozen: m.is_frozen,
      children: [],
    });
  }

  let root: TreeNode | null = null;
  for (const m of members) {
    const node = nodesById.get(m.agent_id)!;
    if (m.parent_agent_id && nodesById.has(m.parent_agent_id)) {
      nodesById.get(m.parent_agent_id)!.children.push(node);
    } else {
      root = node; // no parent in this fetch -> branch root
    }
  }
  // Stable, readable child order regardless of fetch order.
  for (const node of nodesById.values()) {
    node.children.sort((a, b) => a.display_name.localeCompare(b.display_name));
  }

  return root;
}

export function BranchVisualizer({
  members,
  onOpenAgent,
}: {
  members: BranchMemberRead[];
  /** When given, the page around the tree shows the card instead of the tree itself. */
  onOpenAgent?: (agentId: string) => void;
}) {
  const rootNode = buildTree(members);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [selectedNode, setSelectedNode] = useState<{ agentId: string; displayName: string } | null>(null);

  const copyToClipboard = (id: string) => {
    navigator.clipboard.writeText(id);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };


  if (!rootNode) {
    return <p className="text-sm text-surface-500">Nessun membro della rete da visualizzare.</p>;
  }

  return (
    <div className="panel panel-hover rounded-2xl p-6 border-white/5 light:border-surface-200 bg-surface-950/40 light:bg-white/70">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4">
        <div>
          <h3 className="text-lg font-semibold text-white light:text-surface-900">Visualizzazione Albero Rete</h3>
          <p className="text-xs text-surface-400 light:text-surface-500">Struttura gerarchica dei tuoi promoter affiliati</p>
        </div>
        <span className="px-3 py-1 text-xs font-semibold rounded-full bg-violet-500/10 text-violet-400 border border-violet-500/20 shrink-0">
          {members.length} Agenti Totali
        </span>
      </div>

      <NetworkChart
        roots={[rootNode]}
        onCopy={copyToClipboard}
        copiedId={copiedId}
        onNodeSelect={(agentId, displayName) =>
          onOpenAgent ? onOpenAgent(agentId) : setSelectedNode({ agentId, displayName })
        }
      />

      {selectedNode && (
        <AgentCardModal
          agentId={selectedNode.agentId}
          onClose={() => setSelectedNode(null)}
          onOpenAgent={(agentId) => setSelectedNode({ agentId, displayName: "" })}
          canOpen={(agentId) => members.some((m) => m.agent_id === agentId)}
        />
      )}
    </div>
  );
}
