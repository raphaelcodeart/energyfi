"use client";

import { sectionEnabled, useFeatures } from "@/lib/features";
import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Pagination, serverPagination } from "@/components/pagination";
import { AgentPicker } from "@/components/agent-picker";
import { BranchSyncButton } from "@/components/branch-sync-button";
import { exportAgentsCsvUrl, useAgentPage } from "@/lib/agents";
import { ShareButtons } from "@/components/share-buttons";
import { PhotoUpload } from "@/components/photo-upload";
import { AdminPromoterNetworkModal } from "@/components/admin-promoter-network-modal";
import { friendlyApiError } from "@/lib/api-error";
import { DEFAULT_ORGANIZATION_ID } from "@/lib/config";
import type { AgentListItemRead, CommercialRoleRead, PromoterCodeRead, RoleHistoryRow, RootPromoterCreateResponse, WalletAdminListItemRead } from "@/lib/types";
import { Chip, IdTag, Identity, KpiTile, RowActions, Stack, type ChipTone } from "@/components/ui/data-cells";

const STATUS_TONES: Record<string, ChipTone> = {
  ACTIVE: "ok",
  SUSPENDED: "warn",
  TERMINATED: "bad",
  PENDING_APPROVAL: "warn",
};
const STATUS_LABELS: Record<string, string> = {
  ACTIVE: "Attivo",
  SUSPENDED: "Sospeso",
  TERMINATED: "Cessato",
  PENDING_APPROVAL: "Da approvare",
};

async function fetchWallets(): Promise<WalletAdminListItemRead[]> {
  const res = await fetch("/api/proxy/wallets/admin");
  if (!res.ok) throw new Error("Impossibile caricare i wallet.");
  return res.json();
}

async function fetchRoles(): Promise<CommercialRoleRead[]> {
  const res = await fetch("/api/proxy/commercial/roles");
  if (!res.ok) throw new Error("Impossibile caricare i ruoli commerciali.");
  return res.json();
}

async function fetchRoleHistory(agentId: string): Promise<RoleHistoryRow[]> {
  const res = await fetch(`/api/proxy/commercial/agents/${agentId}/roles`);
  if (!res.ok) throw new Error("Impossibile caricare lo storico dei ruoli.");
  return res.json();
}

const STATUS_FILTERS: { key: string; label: string }[] = [
  { key: "ALL", label: "Tutti" },
  { key: "ACTIVE", label: "Attivi" },
  { key: "PENDING_APPROVAL", label: "Da approvare" },
  { key: "SUSPENDED", label: "Sospesi" },
  { key: "TERMINATED", label: "Cessati" },
];

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString("it-IT", { day: "2-digit", month: "short", year: "numeric" });
}

/** Uploaded photo rendered inside the identity orb; initials are the fallback. */
function agentPhoto(url: string | null) {
  if (!url) return undefined;
  // eslint-disable-next-line @next/next/no-img-element -- externally-hosted, variable-source uploaded photo
  return <img src={url} alt="" className="h-full w-full rounded-[14px] object-cover" />;
}

function CloseIcon() {
  return (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M6 18L18 6M6 6l12 12" />
    </svg>
  );
}

export function AdminPromotersPanel({
  initialStatusFilter,
  isSuperAdmin = false,
}: { initialStatusFilter?: string; isSuperAdmin?: boolean } = {}) {
  const features = useFeatures();
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [statusFilter, setStatusFilterRaw] = useState(initialStatusFilter ?? "ALL");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  useEffect(() => {
    const t = setTimeout(() => { setDebouncedSearch(search.trim()); setPage(1); }, 300);
    return () => clearTimeout(t);
  }, [search]);
  const setStatusFilter = (key: string) => { setStatusFilterRaw(key); setPage(1); };
  // One page at a time, filtered on the server: the network has tens of
  // thousands of people and the browser never receives them all.
  const { data: pageData, error: loadError, isFetching: pageFetching } = useAgentPage({
    page, pageSize, search: debouncedSearch, status: statusFilter,
  });
  const pageItems = pageData?.items ?? [];
  const { data: roles = [] } = useQuery({
    queryKey: ["commercial", "roles"],
    queryFn: fetchRoles,
  });
  const { data: wallets } = useQuery({
    queryKey: ["admin", "wallets", "all"],
    queryFn: fetchWallets,
  });
  const canTransferByUserId = new Map((wallets ?? []).map((w) => [w.user_id, w.can_transfer]));
  const [transferToggleId, setTransferToggleId] = useState<string | null>(null);

  // Freeze/unfreeze login (SUPER_ADMIN only, see users/router.py)
  const [freezeLoadingId, setFreezeLoadingId] = useState<string | null>(null);
  const [freezeError, setFreezeError] = useState<string | null>(null);

  async function handleToggleFreeze(userId: string, currentlyFrozen: boolean) {
    setFreezeLoadingId(userId);
    setFreezeError(null);
    try {
      const res = await fetch(`/api/proxy/users/${userId}/${currentlyFrozen ? "unfreeze" : "freeze"}`, { method: "PATCH" });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      await queryClient.invalidateQueries({ queryKey: ["admin", "agents"] });
    } catch (err: any) {
      setFreezeError(err.message || "Impossibile aggiornare lo stato dell'account.");
    } finally {
      setFreezeLoadingId(null);
    }
  }

  async function handleToggleTransfer(userId: string, next: boolean) {
    setTransferToggleId(userId);
    try {
      const res = await fetch(`/api/proxy/wallets/admin/${userId}/transfer-permission`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ can_transfer: next }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      await queryClient.invalidateQueries({ queryKey: ["admin", "wallets"] });
    } finally {
      setTransferToggleId(null);
    }
  }

  const [showCreate, setShowCreate] = useState(false);

  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [promoterCode, setPromoterCode] = useState("");
  const [parentAgentId, setParentAgentId] = useState("");
  const [roleId, setRoleId] = useState("");
  const [customerEmail, setCustomerEmail] = useState("");
  const [createLoading, setCreateLoading] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);


  // Approval: only network.approve holders (SUPER_ADMIN / ORGANIZATION_ADMIN)
  // succeed. A plain ADMIN sees the buttons but gets a 403, shown as approvalError.
  const [approvalActionId, setApprovalActionId] = useState<string | null>(null);
  const [approvalError, setApprovalError] = useState<string | null>(null);
  const [rejectingAgent, setRejectingAgent] = useState<AgentListItemRead | null>(null);
  const [rejectReason, setRejectReason] = useState("");

  // Deactivate / blacklist / reactivate. "Lavora con noi" activates a promoter
  // immediately (network/service.py apply_as_promoter), so this is how an admin
  // revokes it. A blacklisted agent who re-applies goes through manual approval.
  const [agentActionId, setAgentActionId] = useState<string | null>(null);
  const [agentActionError, setAgentActionError] = useState<string | null>(null);

  async function handleSetAgentStatus(agentId: string, patch: { status?: string; is_blacklisted?: boolean }) {
    setAgentActionId(agentId);
    setAgentActionError(null);
    try {
      const res = await fetch(`/api/proxy/network/agents/${agentId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(patch),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      await queryClient.invalidateQueries({ queryKey: ["admin", "agents"] });
    } catch (err: any) {
      setAgentActionError(err.message || "Operazione non riuscita.");
    } finally {
      setAgentActionId(null);
    }
  }

  // Opens an agent's referral link, created server-side on demand. The tab is
  // opened before the fetch resolves so popup blockers treat it as part of the
  // click.
  const [referralLinkLoadingId, setReferralLinkLoadingId] = useState<string | null>(null);

  async function handleOpenReferralLink(agentId: string) {
    setReferralLinkLoadingId(agentId);
    setAgentActionError(null);
    const newTab = window.open("", "_blank");
    try {
      const res = await fetch(`/api/proxy/network/agents/${agentId}/referral-link`);
      if (!res.ok) throw new Error(await friendlyApiError(res, "Impossibile recuperare il link del promoter."));
      const data: PromoterCodeRead = await res.json();
      const url = new URL(`/r/${data.code}`, window.location.origin);
      url.searchParams.set("org", DEFAULT_ORGANIZATION_ID);
      if (newTab) newTab.location.href = url.toString();
    } catch (err: any) {
      newTab?.close();
      setAgentActionError(err.message || "Impossibile recuperare il link del promoter.");
    } finally {
      setReferralLinkLoadingId(null);
    }
  }

  async function handleApprove(agentId: string) {
    setApprovalActionId(agentId);
    setApprovalError(null);
    try {
      const res = await fetch(`/api/proxy/network/agents/${agentId}/approve`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: "{}" });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      await queryClient.invalidateQueries({ queryKey: ["admin", "agents"] });
    } catch (err: any) {
      setApprovalError(err.message || "Impossibile approvare -- solo l'amministratore principale può farlo.");
    } finally {
      setApprovalActionId(null);
    }
  }

  async function handleReject() {
    if (!rejectingAgent) return;
    setApprovalActionId(rejectingAgent.id);
    setApprovalError(null);
    try {
      const res = await fetch(`/api/proxy/network/agents/${rejectingAgent.id}/reject`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reason: rejectReason || null }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      await queryClient.invalidateQueries({ queryKey: ["admin", "agents"] });
      setRejectingAgent(null);
      setRejectReason("");
    } catch (err: any) {
      setApprovalError(err.message || "Impossibile rifiutare -- solo l'amministratore principale può farlo.");
    } finally {
      setApprovalActionId(null);
    }
  }

  const [editingAgent, setEditingAgent] = useState<AgentListItemRead | null>(null);
  const [networkAgent, setNetworkAgent] = useState<AgentListItemRead | null>(null);
  const [editFirstName, setEditFirstName] = useState("");
  const [editLastName, setEditLastName] = useState("");
  const [editStatus, setEditStatus] = useState("ACTIVE");
  const [editRoleId, setEditRoleId] = useState("");
  const [editRoleFrom, setEditRoleFrom] = useState("");
  const [editRoleReason, setEditRoleReason] = useState("");
  const [editPhotoUrl, setEditPhotoUrl] = useState<string | null>(null);
  const [editLoading, setEditLoading] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);

  function openEdit(a: AgentListItemRead) {
    setEditFirstName(a.first_name ?? "");
    setEditLastName(a.last_name ?? "");
    setEditStatus(a.status);
    setEditRoleId(a.commercial_role_id ?? "");
    setEditRoleFrom("");
    setEditRoleReason("");
    setEditPhotoUrl(a.photo_url);
    setEditError(null);
    setEditingAgent(a);
  }

  async function handleEditSave(e: React.FormEvent) {
    e.preventDefault();
    if (!editingAgent) return;
    setEditLoading(true);
    setEditError(null);
    try {
      const res = await fetch(`/api/proxy/network/agents/${editingAgent.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          first_name: editFirstName,
          last_name: editLastName,
          status: editStatus,
        }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      // A commercial role is never overwritten: the current period is closed and a
      // new one opened, so past sales keep the role held at the time.
      if (editRoleId && editRoleId !== (editingAgent.commercial_role_id ?? "")) {
        const roleRes = await fetch(`/api/proxy/commercial/agents/${editingAgent.id}/role`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            role_id: editRoleId,
            effective_from: editRoleFrom ? new Date(`${editRoleFrom}T00:00:00`).toISOString() : null,
            reason: editRoleReason || null,
          }),
        });
        if (!roleRes.ok) throw new Error(await friendlyApiError(roleRes));
        await queryClient.invalidateQueries({ queryKey: ["admin", "role-history", editingAgent.id] });
      }
      setEditingAgent(null);
      await queryClient.invalidateQueries({ queryKey: ["admin", "agents"] });
    } catch (err: any) {
      setEditError(err.message || "Impossibile salvare le modifiche.");
    } finally {
      setEditLoading(false);
    }
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setCreateLoading(true);
    setCreateError(null);
    try {
      const res = await fetch("/api/proxy/network/agents", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          first_name: firstName,
          last_name: lastName,
          promoter_code: promoterCode,
          parent_agent_id: parentAgentId || null,
          commercial_role_id: roleId || null,
          customer_email: customerEmail || null,
        }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      setShowCreate(false);
      setFirstName("");
      setLastName("");
      setPromoterCode("");
      setParentAgentId("");
      setRoleId("");
      setCustomerEmail("");
      await queryClient.invalidateQueries({ queryKey: ["admin", "agents"] });
    } catch (err: any) {
      setCreateError(err.message || "Impossibile creare l'agente.");
    } finally {
      setCreateLoading(false);
    }
  }

  // Root promoter bootstrap (network.approve server-side). Unlike "+ Nuovo
  // Promoter", which only suggests a candidate, this creates a login and an
  // ACTIVE parentless agent in one step: the only way to start an independent
  // branch, since every other signup needs a referral code.
  const [showCreateRoot, setShowCreateRoot] = useState(false);
  const [rootFirstName, setRootFirstName] = useState("");
  const [rootLastName, setRootLastName] = useState("");
  const [rootEmail, setRootEmail] = useState("");
  const [rootPromoterCode, setRootPromoterCode] = useState("");
  const [rootCreateLoading, setRootCreateLoading] = useState(false);
  const [rootCreateError, setRootCreateError] = useState<string | null>(null);
  const [rootCreateResult, setRootCreateResult] = useState<RootPromoterCreateResponse | null>(null);
  const [rootLinkCopied, setRootLinkCopied] = useState(false);
  const [rootPasswordCopied, setRootPasswordCopied] = useState(false);

  async function handleCreateRoot(e: React.FormEvent) {
    e.preventDefault();
    setRootCreateLoading(true);
    setRootCreateError(null);
    try {
      const res = await fetch("/api/proxy/network/agents/root", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          first_name: rootFirstName,
          last_name: rootLastName,
          email: rootEmail,
          promoter_code: rootPromoterCode || null,
        }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      const result: RootPromoterCreateResponse = await res.json();
      setShowCreateRoot(false);
      setRootFirstName("");
      setRootLastName("");
      setRootEmail("");
      setRootPromoterCode("");
      setRootCreateResult(result);
      await queryClient.invalidateQueries({ queryKey: ["admin", "agents"] });
    } catch (err: any) {
      setRootCreateError(err.message || "Impossibile creare il promoter radice -- solo l'amministratore principale può farlo.");
    } finally {
      setRootCreateLoading(false);
    }
  }

  const pagination = serverPagination(pageData?.total ?? 0, page, pageSize, setPage, setPageSize);

  const handleExportCsv = () => {
    // Streamed by the server: the whole filtered registry, not just this page.
    const a = document.createElement("a");
    a.href = exportAgentsCsvUrl(debouncedSearch, statusFilter);
    a.download = "";
    document.body.appendChild(a);
    a.click();
    a.remove();
  };

  const counts = pageData?.counts ?? {};
  const all = counts.ALL ?? 0;
  const countBy = (status: string) => counts[status] ?? 0;
  const kpis: { key: string; label: string; value: number; hint: string }[] = [
    { key: "ALL", label: "Collaboratori", value: all, hint: "in tutta la rete" },
    { key: "ACTIVE", label: "Attivi", value: countBy("ACTIVE"), hint: all ? `${Math.round((countBy("ACTIVE") / all) * 100)}% della rete` : "—" },
    { key: "PENDING_APPROVAL", label: "Da approvare", value: countBy("PENDING_APPROVAL"), hint: "in attesa di decisione" },
    { key: "TERMINATED", label: "Cessati", value: countBy("TERMINATED"), hint: `${counts.BLACKLISTED ?? 0} in blacklist` },
  ];

  return (
    <div className="space-y-6">
      {pageData !== undefined && (
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4 stagger">
          {kpis.map((k, i) => (
            <div key={k.key} style={{ "--i": i } as React.CSSProperties}>
              <KpiTile label={k.label} value={k.value} hint={k.hint} active={statusFilter === k.key} onClick={() => setStatusFilter(k.key)} />
            </div>
          ))}
        </div>
      )}

      <div className="flex flex-col xl:flex-row gap-4 xl:items-center justify-between">
        <div className="flex flex-col sm:flex-row gap-3 sm:items-center min-w-0">
          <div className="w-full sm:w-72 relative shrink-0">
            <input
              type="text"
              placeholder="Cerca nome, codice o email..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full rounded-xl field pl-10 pr-4 py-2 text-xs focus:border-brand-500"
            />
            <svg className="w-4 h-4 text-surface-400 absolute left-3 top-2.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
          </div>
          <div className="subnav">
            {STATUS_FILTERS.map((f) => (
              <button key={f.key} onClick={() => setStatusFilter(f.key)} data-active={statusFilter === f.key} className="subnav-pill">
                {f.label}
              </button>
            ))}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2 shrink-0">
          <button onClick={handleExportCsv} className="act !h-10 !px-4">
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
            </svg>
            CSV
          </button>
          <button
            onClick={() => setShowCreateRoot(true)}
            title="Crea un promoter senza sponsor, con accesso già attivo -- l'unico modo di avviare un nuovo ramo indipendente, dato che ogni altra iscrizione richiede il link di un promoter già esistente"
            className="act !h-10 !px-4"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 3H5a2 2 0 00-2 2v4m6-6h10a2 2 0 012 2v4M9 3v18m0 0H5a2 2 0 01-2-2v-4m6 6h10a2 2 0 002-2v-4" />
            </svg>
            + Collaboratore radice
          </button>
          <button onClick={() => setShowCreate(true)} className="act act-primary !h-10 !px-5">
            + Nuovo collaboratore
          </button>
        </div>
      </div>

      {loadError && <p className="text-sm text-danger-400">Impossibile caricare la rete commerciale.</p>}
      {freezeError && <p className="text-sm text-danger-400">{freezeError}</p>}
      {approvalError && (
        <div className="p-3 rounded-2xl bg-danger-500/10 border border-danger-500/20 text-danger-400 text-xs pop">{approvalError}</div>
      )}
      {agentActionError && (
        <div className="p-3 rounded-2xl bg-danger-500/10 border border-danger-500/20 text-danger-400 text-xs pop">{agentActionError}</div>
      )}
      <div className="panel rounded-3xl p-4 md:p-6">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr>
                <th className="px-4 py-3">Collaboratore</th>
                <th className="px-4 py-3">Posizione</th>
                <th className="px-4 py-3">Introdotto da</th>
                <th className="px-4 py-3">Rete</th>
                <th className="px-4 py-3">Verifiche</th>
                <th className="px-4 py-3">Situazione</th>
                <th className="px-4 py-3"><span className="sr-only">Azioni</span></th>
              </tr>
            </thead>
            <tbody className={`text-surface-300 transition-opacity ${pageFetching && pageData ? "opacity-60" : ""}`}>
              {pageData === undefined ? (
                Array.from({ length: 6 }, (_, i) => (
                  <tr key={i}><td colSpan={7} className="px-4 py-3"><div className="h-9 animate-pulse rounded-xl bg-white/5" /></td></tr>
                ))
              ) : pageItems.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-4 py-12">
                    <div className="flex flex-col items-center gap-2 text-center">
                      <svg viewBox="0 0 24 24" className="h-8 w-8 text-accent-300 float-soft" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
                        <path d="M17 20h5v-2a4 4 0 00-3-3.87M9 20H4v-2a4 4 0 013-3.87m6-1.13a4 4 0 10-4-4 4 4 0 004 4zm6 0a4 4 0 10-4-4" strokeLinejoin="round" />
                      </svg>
                      <span className="text-sm font-semibold text-surface-200">Nessun promoter trovato.</span>
                    </div>
                  </td>
                </tr>
              ) : (
                pageItems.map((a) => (
                  <tr key={a.id}>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-1.5">
                        <Identity
                          name={a.display_name}
                          icon={agentPhoto(a.photo_url)}
                          detail={<span title={`Iscritto il ${fmtDate(a.joined_at)}`}>{a.contact_email ?? "Nessuna email"}{!a.user_id && <span className="text-surface-500"> · senza accesso</span>}</span>}
                        >
                          <div className="text-[10.5px] text-surface-400">dal {fmtDate(a.joined_at)}</div>
                        </Identity>
                        <button
                          onClick={() => handleOpenReferralLink(a.id)}
                          disabled={referralLinkLoadingId === a.id}
                          title="Apri il link personale di invito di questo promoter"
                          aria-label="Apri link di invito"
                          className="act !h-7 !px-1.5 shrink-0 self-start"
                        >
                          {referralLinkLoadingId === a.id ? (
                            <svg className="w-3.5 h-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
                              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                            </svg>
                          ) : (
                            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
                            </svg>
                          )}
                        </button>
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex flex-col items-start gap-1.5">
                        <Chip tone="accent">{a.role_name ?? "—"}</Chip>
                        <span className="tag-id" title="Codice promoter">{a.promoter_code}</span>
                        {a.rank_code && <span className="text-[10.5px] text-surface-400">livello {a.rank_code}</span>}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      {a.direct_parent_agent_id ? (
                        <Stack title={a.parent_name ?? "—"} detail={a.parent_code ? <span className="tag-id">{a.parent_code}</span> : <IdTag id={a.direct_parent_agent_id} />} />
                      ) : (
                        <Chip tone="info">Radice</Chip>
                      )}
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap">
                      <button type="button" onClick={() => setNetworkAgent(a)} title="Apri la rete" className="text-left hover:underline">
                        <span className="font-semibold text-white light:text-surface-900">{a.network_size.toLocaleString("it-IT")}</span>
                        <span className="text-surface-400"> persone</span>
                        <div className="text-[10.5px] text-surface-400">{a.direct_count.toLocaleString("it-IT")} diretti</div>
                      </button>
                    </td>
                    <td className="px-4 py-3">
                      {a.user_id ? (
                        <div className="flex max-w-[220px] flex-wrap items-center gap-1.5">
                          <span title={a.email_verified ? "Email verificata" : "Email non verificata"}>
                            <Chip tone={a.email_verified ? "ok" : "bad"}>Email {a.email_verified ? "✓" : "✗"}</Chip>
                          </span>
                          <span title={a.privacy_accepted ? "Privacy accettata" : "Privacy non accettata"}>
                            <Chip tone={a.privacy_accepted ? "ok" : "bad"}>Privacy {a.privacy_accepted ? "✓" : "✗"}</Chip>
                          </span>
                          <span
                            title={
                              a.collaboration_accepted_at
                                ? [
                                    `Accettato il ${new Date(a.collaboration_accepted_at).toLocaleString("it-IT")}`,
                                    // Which documents and which version: an acceptance only means something with its version.
                                    ...Object.entries(a.collaboration_accepted_documents ?? {}).map(
                                      ([key, v]) => `${key} v${v.version}`
                                    ),
                                  ].join(" · ")
                                : "Contratto di collaborazione non accettato"
                            }
                          >
                            <Chip tone={a.collaboration_accepted_at ? "ok" : "bad"}>
                              Contratto {a.collaboration_accepted_at ? "✓" : "✗"}
                              {Object.keys(a.collaboration_accepted_documents ?? {}).length > 1 && (
                                <span className="opacity-75">
                                  ({Object.keys(a.collaboration_accepted_documents ?? {}).length} doc.)
                                </span>
                              )}
                            </Chip>
                          </span>
                          {a.user_status === "FROZEN" && <Chip tone="info">Congelato</Chip>}
                        </div>
                      ) : (
                        <span className="text-[11px] text-surface-400">nessun accesso</span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex flex-col items-start gap-1.5">
                        <Chip tone={STATUS_TONES[a.status] ?? "ok"} live={a.status === "PENDING_APPROVAL"}>
                          {STATUS_LABELS[a.status] ?? a.status}
                        </Chip>
                        {a.is_blacklisted && <Chip tone="bad">In blacklist</Chip>}
                        {a.status === "TERMINATED" && a.rejection_reason && (
                          <p className="text-[10.5px] text-danger-400 max-w-[160px]">{a.rejection_reason}</p>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <RowActions>
                        {a.status === "PENDING_APPROVAL" ? (
                          <>
                            <button onClick={() => handleApprove(a.id)} disabled={approvalActionId === a.id} className="act act-primary">
                              Approva
                            </button>
                            <button onClick={() => setRejectingAgent(a)} disabled={approvalActionId === a.id} className="act !text-danger-400">
                              Rifiuta
                            </button>
                          </>
                        ) : (
                          <div className="flex max-w-[360px] flex-wrap items-center justify-end gap-1.5">
                            <button onClick={() => setNetworkAgent(a)} title="Apri la rete di questo promoter" className="act act-primary">
                              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 3H5a2 2 0 00-2 2v4m6-6h10a2 2 0 012 2v4M9 3v18m0 0H5a2 2 0 01-2-2v-4m6 6h10a2 2 0 002-2v-4m0-6h-6m6 0v6m0-6l-8 8" />
                              </svg>
                              Apri Rete
                            </button>
                            <button onClick={() => openEdit(a)} title="Modifica promoter" aria-label="Modifica promoter" className="act !px-2">
                              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                              </svg>
                            </button>
                            {isSuperAdmin && a.user_id && (
                              <button
                                onClick={() => handleToggleFreeze(a.user_id!, a.user_status === "FROZEN")}
                                disabled={freezeLoadingId === a.user_id}
                                title={a.user_status === "FROZEN" ? "Riattiva account" : "Congela account (blocca l'accesso)"}
                                aria-label={a.user_status === "FROZEN" ? "Riattiva account" : "Congela account"}
                                className={`act !px-2 ${a.user_status === "FROZEN" ? "!text-success-400" : "!text-info-400"}`}
                              >
                                {a.user_status === "FROZEN" ? (
                                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 11V7a4 4 0 118 0m-4 8v2m-6 2h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2z" />
                                  </svg>
                                ) : (
                                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                                  </svg>
                                )}
                              </button>
                            )}
                            {a.user_id && features.wallet && (() => {
                              const enabled = canTransferByUserId.get(a.user_id) ?? false;
                              return (
                                <button
                                  onClick={() => handleToggleTransfer(a.user_id!, !enabled)}
                                  disabled={transferToggleId === a.user_id}
                                  title={enabled ? "Disabilita l'invio di bonifici wallet per questo promoter" : "Abilita l'invio di bonifici wallet per questo promoter"}
                                  className={`act ${enabled ? "!text-success-400" : ""}`}
                                >
                                  {transferToggleId === a.user_id ? "..." : enabled ? "Bonifico: ON" : "Bonifico: OFF"}
                                </button>
                              );
                            })()}
                            {a.status === "ACTIVE" && (
                              <>
                                <button
                                  onClick={() => handleSetAgentStatus(a.id, { status: "TERMINATED" })}
                                  disabled={agentActionId === a.id}
                                  title="Toglie l'accesso da collaboratore: torna un semplice cliente. Può ricandidarsi in autonomia con 'Lavora con noi'."
                                  className="act"
                                >
                                  Disattiva
                                </button>
                                <button
                                  onClick={() => handleSetAgentStatus(a.id, { status: "TERMINATED", is_blacklisted: true })}
                                  disabled={agentActionId === a.id}
                                  title="Disattiva e blocca: se si ricandida, resta in attesa di approvazione invece di attivarsi da solo."
                                  className="act !text-danger-400"
                                >
                                  Blacklist
                                </button>
                              </>
                            )}
                            {(a.status === "TERMINATED" || a.status === "SUSPENDED") && (
                              <>
                                <button
                                  onClick={() => handleSetAgentStatus(a.id, { status: "ACTIVE" })}
                                  disabled={agentActionId === a.id}
                                  className="act !text-success-400"
                                >
                                  Riattiva
                                </button>
                                {a.is_blacklisted && (
                                  <button
                                    onClick={() => handleSetAgentStatus(a.id, { is_blacklisted: false })}
                                    disabled={agentActionId === a.id}
                                    title="Toglie il blocco: da ora una nuova candidatura 'Lavora con noi' torna ad attivarsi da sola."
                                    className="act"
                                  >
                                    Rimuovi blacklist
                                  </button>
                                )}
                              </>
                            )}
                          </div>
                        )}
                      </RowActions>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
        <div className="px-2 pt-3">
          <Pagination {...pagination} label="collaboratori" />
        </div>
      </div>

      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-fade-in">
          <div className="w-full max-w-lg panel rounded-3xl p-6 md:p-7 border-white/10 bg-surface-950 pop max-h-[90vh] overflow-y-auto">
            <div className="flex items-start justify-between mb-5">
              <div>
                <div className="kpi-label">Nuovo collaboratore</div>
                <h3 className="mt-0.5 text-xl font-black tracking-tight text-white">Nuovo Promoter</h3>
              </div>
              <button onClick={() => setShowCreate(false)} aria-label="Chiudi" className="act !h-9 !w-9 !p-0 justify-center">
                <CloseIcon />
              </button>
            </div>

            <form onSubmit={handleCreate} className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1">
                  <label className="kpi-label block">Nome</label>
                  <input required value={firstName} onChange={(e) => setFirstName(e.target.value)}
                    className="w-full rounded-xl field px-3 py-2 text-sm focus:border-brand-500" />
                </div>
                <div className="space-y-1">
                  <label className="kpi-label block">Cognome</label>
                  <input required value={lastName} onChange={(e) => setLastName(e.target.value)}
                    className="w-full rounded-xl field px-3 py-2 text-sm focus:border-brand-500" />
                </div>
              </div>

              <div className="space-y-1">
                <label className="kpi-label block">Codice Promoter</label>
                <input required value={promoterCode} onChange={(e) => setPromoterCode(e.target.value)}
                  placeholder="Es: SP1-MARIO-ROSSI"
                  className="w-full rounded-xl field px-3 py-2 text-sm font-mono focus:border-brand-500" />
              </div>

              <div className="space-y-1">
                <label className="kpi-label block">Sponsor (ramo di appartenenza)</label>
                <AgentPicker
                  value={parentAgentId}
                  onChange={(id) => setParentAgentId(id)}
                  ariaLabel="Sponsor"
                  emptyLabel="— Nessuno (nuova radice di rete) —"
                  placeholder="Nessuno (nuova radice) · cerca per nome o codice…"
                />
              </div>

              <div className="space-y-1">
                <label className="kpi-label block">Cliente già registrato (opzionale)</label>
                <input type="email" value={customerEmail} onChange={(e) => setCustomerEmail(e.target.value)}
                  placeholder="Email del cliente da promuovere a promoter"
                  className="w-full rounded-xl field px-3 py-2 text-sm focus:border-brand-500" />
                <p className="text-[11px] text-surface-400">Se indicata, il login esistente del cliente diventerà anche promoter una volta approvato — invece di crearne uno nuovo senza accesso.</p>
              </div>

              <div className="space-y-1">
                <label className="kpi-label block">Ruolo commerciale</label>
                <select
                  value={roleId}
                  onChange={(e) => setRoleId(e.target.value)}
                  className="w-full rounded-xl field px-3 py-2.5 text-sm bg-surface-900 focus:border-brand-500"
                >
                  <option value="">— Ruolo predefinito —</option>
                  {roles.filter((r) => r.is_active).map((r) => (
                    <option key={r.id} value={r.id}>{r.name}</option>
                  ))}
                </select>
              </div>

              {createError && (
                <div className="p-3 rounded-lg bg-danger-500/10 border border-danger-500/20 text-danger-400 text-xs">{createError}</div>
              )}

              <div className="flex justify-end gap-3 mt-4">
                <button type="button" onClick={() => setShowCreate(false)}
                  className="act !h-10 !px-4">
                  Annulla
                </button>
                <button type="submit" disabled={createLoading}
                  className="act act-primary !h-10 !px-4">
                  {createLoading ? "Creazione..." : "Crea Promoter"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {showCreateRoot && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-fade-in">
          <div className="w-full max-w-lg panel rounded-3xl p-6 md:p-7 border-white/10 bg-surface-950 pop max-h-[90vh] overflow-y-auto">
            <div className="flex items-start justify-between mb-5">
              <div>
                <div className="kpi-label">Nuovo ramo</div>
                <h3 className="mt-0.5 text-xl font-black tracking-tight text-white">Nuovo Promoter Radice</h3>
              </div>
              <button onClick={() => setShowCreateRoot(false)} aria-label="Chiudi" className="act !h-9 !w-9 !p-0 justify-center">
                <CloseIcon />
              </button>
            </div>
            <p className="text-xs text-surface-400 mb-4">
              Crea un account già attivo, senza sponsor sopra di lui. Genero password temporanea e link personale pronti da consegnare.
            </p>

            <form onSubmit={handleCreateRoot} className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1">
                  <label className="kpi-label block">Nome</label>
                  <input required value={rootFirstName} onChange={(e) => setRootFirstName(e.target.value)}
                    className="w-full rounded-xl field px-3 py-2 text-sm focus:border-brand-500" />
                </div>
                <div className="space-y-1">
                  <label className="kpi-label block">Cognome</label>
                  <input required value={rootLastName} onChange={(e) => setRootLastName(e.target.value)}
                    className="w-full rounded-xl field px-3 py-2 text-sm focus:border-brand-500" />
                </div>
              </div>

              <div className="space-y-1">
                <label className="kpi-label block">Email</label>
                <input required type="email" value={rootEmail} onChange={(e) => setRootEmail(e.target.value)}
                  className="w-full rounded-xl field px-3 py-2 text-sm focus:border-brand-500" />
              </div>

              <div className="space-y-1">
                <label className="kpi-label block">Codice Promoter (opzionale)</label>
                <input value={rootPromoterCode} onChange={(e) => setRootPromoterCode(e.target.value)}
                  placeholder="Vuoto = generato automaticamente"
                  className="w-full rounded-xl field px-3 py-2 text-sm font-mono focus:border-brand-500" />
              </div>

              {rootCreateError && (
                <div className="p-3 rounded-lg bg-danger-500/10 border border-danger-500/20 text-danger-400 text-xs">{rootCreateError}</div>
              )}

              <div className="flex justify-end gap-3 mt-4">
                <button type="button" onClick={() => setShowCreateRoot(false)}
                  className="act !h-10 !px-4">
                  Annulla
                </button>
                <button type="submit" disabled={rootCreateLoading}
                  className="act act-primary !h-10 !px-4">
                  {rootCreateLoading ? "Creazione..." : "Crea Promoter Radice"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {rootCreateResult && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-fade-in">
          <div className="w-full max-w-lg panel rounded-3xl p-6 md:p-7 border-white/10 bg-surface-950 pop">
            <div className="kpi-label">Credenziali</div>
            <h3 className="mt-0.5 mb-1 text-xl font-black tracking-tight text-white">
              <span className="text-gradient">{rootCreateResult.display_name}</span> è attivo
            </h3>
            <p className="text-xs text-surface-400 mb-4">
              Consegna queste credenziali fuori da questa schermata (non restano salvate da nessuna parte): questa è l&apos;unica volta in cui la password viene mostrata. Digli di cambiarla al primo accesso.
            </p>

            <div className="space-y-3 mb-4">
              <div>
                <label className="kpi-label block mb-1">Email</label>
                <div className="rounded-xl field px-3 py-2 text-sm font-mono">{rootCreateResult.email}</div>
              </div>
              <div>
                <label className="kpi-label block mb-1">Password temporanea</label>
                <div className="flex gap-2">
                  <div className="flex-1 rounded-xl field px-3 py-2 text-sm font-mono">{rootCreateResult.temporary_password}</div>
                  <button
                    type="button"
                    onClick={() => {
                      navigator.clipboard.writeText(rootCreateResult.temporary_password);
                      setRootPasswordCopied(true);
                      setTimeout(() => setRootPasswordCopied(false), 2000);
                    }}
                    className="act !h-[38px] !px-3"
                  >
                    {rootPasswordCopied ? "Copiata!" : "Copia"}
                  </button>
                </div>
              </div>
              <div>
                <label className="kpi-label block mb-1">Link personale (da condividere con i suoi invitati)</label>
                <div className="flex gap-2">
                  <div className="flex-1 rounded-xl field px-3 py-2 text-xs font-mono truncate">{rootCreateResult.personal_link}</div>
                  <button
                    type="button"
                    onClick={() => {
                      navigator.clipboard.writeText(rootCreateResult.personal_link);
                      setRootLinkCopied(true);
                      setTimeout(() => setRootLinkCopied(false), 2000);
                    }}
                    className="act !h-[38px] !px-3"
                  >
                    {rootLinkCopied ? "Copiato!" : "Copia"}
                  </button>
                </div>
                {/* Share options so the admin can send the new root promoter their link right away. */}
                <ShareButtons
                  className="mt-2"
                  url={rootCreateResult.personal_link}
                  text="Ecco il tuo link personale SOSNET:"
                />
              </div>
            </div>

            <div className="flex justify-end">
              <button
                onClick={() => setRootCreateResult(null)}
                className="act act-primary !h-10 !px-5"
              >
                Fatto
              </button>
            </div>
          </div>
        </div>
      )}

      {editingAgent && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-fade-in">
          <div className="w-full max-w-lg panel rounded-3xl p-6 md:p-7 border-white/10 bg-surface-950 pop max-h-[90vh] overflow-y-auto">
            <div className="flex items-start justify-between mb-5">
              <div>
                <div className="kpi-label">Collaboratore</div>
                <h3 className="mt-0.5 text-xl font-black tracking-tight text-white">Modifica Promoter</h3>
              </div>
              <button onClick={() => setEditingAgent(null)} aria-label="Chiudi" className="act !h-9 !w-9 !p-0 justify-center">
                <CloseIcon />
              </button>
            </div>

            <div className="mb-5 pb-5 border-b border-white/5">
              <label className="kpi-label block mb-2">Foto profilo</label>
              <PhotoUpload
                currentUrl={editPhotoUrl}
                uploadPath={`network/agents/${editingAgent.id}/photo`}
                onUploaded={(url) => {
                  setEditPhotoUrl(url);
                  queryClient.invalidateQueries({ queryKey: ["admin", "agents"] });
                }}
                alt={editingAgent.display_name}
              />
            </div>

            <form onSubmit={handleEditSave} className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1">
                  <label className="kpi-label block">Nome</label>
                  <input required value={editFirstName} onChange={(e) => setEditFirstName(e.target.value)}
                    className="w-full rounded-xl field px-3 py-2 text-sm focus:border-brand-500" />
                </div>
                <div className="space-y-1">
                  <label className="kpi-label block">Cognome</label>
                  <input required value={editLastName} onChange={(e) => setEditLastName(e.target.value)}
                    className="w-full rounded-xl field px-3 py-2 text-sm focus:border-brand-500" />
                </div>
              </div>

              <div className="space-y-1">
                <label className="kpi-label block">Codice Promoter</label>
                <input disabled value={editingAgent.promoter_code}
                  title="Il codice promoter non è modificabile: è incorporato nei link di invito già condivisi"
                  className="w-full rounded-xl field px-3 py-2 text-sm font-mono opacity-60 cursor-not-allowed" />
              </div>

              <div className="space-y-1">
                <label className="kpi-label block">Ruolo commerciale</label>
                <select
                  value={editRoleId}
                  onChange={(e) => setEditRoleId(e.target.value)}
                  className="w-full rounded-xl field px-3 py-2.5 text-sm bg-surface-900 focus:border-brand-500"
                >
                  <option value="">— Nessuno —</option>
                  {roles.filter((r) => r.is_active || r.id === editRoleId).map((r) => (
                    <option key={r.id} value={r.id}>{r.name}</option>
                  ))}
                </select>
                {editRoleId !== (editingAgent.commercial_role_id ?? "") && editRoleId && (
                  <div className="grid grid-cols-2 gap-2 pt-1">
                    <input type="date" value={editRoleFrom} onChange={(e) => setEditRoleFrom(e.target.value)} title="Dal giorno (vuoto = da adesso)"
                      className="w-full rounded-xl field px-3 py-2 text-xs focus:border-brand-500" />
                    <input value={editRoleReason} onChange={(e) => setEditRoleReason(e.target.value)} placeholder="Motivo del cambio"
                      className="w-full rounded-xl field px-3 py-2 text-xs focus:border-brand-500" />
                    <p className="col-span-2 text-[10px] text-surface-400">Vale dalla data indicata in poi: le vendite precedenti restano calcolate con il ruolo di allora.</p>
                  </div>
                )}
                <RoleHistory agentId={editingAgent.id} />
              </div>

              <div className="space-y-1">
                <label className="kpi-label block">Stato</label>
                <select
                  value={editStatus}
                  onChange={(e) => setEditStatus(e.target.value)}
                  className="w-full rounded-xl field px-3 py-2.5 text-sm bg-surface-900 focus:border-brand-500"
                >
                  <option value="ACTIVE">Attivo</option>
                  <option value="SUSPENDED">Sospeso</option>
                  <option value="TERMINATED">Cessato</option>
                </select>
              </div>

              {editError && (
                <div className="p-3 rounded-lg bg-danger-500/10 border border-danger-500/20 text-danger-400 text-xs">{editError}</div>
              )}

              <div className="flex justify-end gap-3 mt-4">
                <button type="button" onClick={() => setEditingAgent(null)}
                  className="act !h-10 !px-4">
                  Annulla
                </button>
                <button type="submit" disabled={editLoading}
                  className="act act-primary !h-10 !px-4">
                  {editLoading ? "Salvataggio..." : "Salva Modifiche"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {networkAgent && (
        <AdminPromoterNetworkModal
          agentId={networkAgent.id}
          displayName={networkAgent.display_name}
          onClose={() => setNetworkAgent(null)}
        />
      )}

      {rejectingAgent && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-fade-in">
          <div className="w-full max-w-md panel rounded-3xl p-6 md:p-7 border-white/10 bg-surface-950 pop">
            <div className="kpi-label">Candidatura</div>
            <h3 className="mt-0.5 mb-2 text-xl font-black tracking-tight text-white">Rifiuta {rejectingAgent.display_name}</h3>
            <p className="text-xs text-surface-400 mb-4">
              Il profilo suggerito viene segnato come cessato. Il codice promoter {rejectingAgent.promoter_code} non sarà più utilizzabile.
            </p>
            <label className="kpi-label block mb-1">Motivazione (opzionale)</label>
            <textarea
              rows={3}
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
              placeholder="Es: codice duplicato, dati incompleti..."
              className="w-full rounded-xl field px-3 py-2 text-sm focus:border-brand-500 resize-none mb-4"
            />
            <div className="flex justify-end gap-3">
              <button
                onClick={() => { setRejectingAgent(null); setRejectReason(""); }}
                className="act !h-10 !px-4"
              >
                Annulla
              </button>
              <button
                onClick={handleReject}
                disabled={approvalActionId === rejectingAgent.id}
                className="act act-primary !h-10 !px-4"
              >
                {approvalActionId === rejectingAgent.id ? "Salvataggio..." : "Conferma Rifiuto"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function RoleHistory({ agentId }: { agentId: string }) {
  const { data } = useQuery({ queryKey: ["admin", "role-history", agentId], queryFn: () => fetchRoleHistory(agentId) });
  if (!data || data.length === 0) return null;
  return (
    <div className="pt-3">
      <p className="kpi-label mb-2">Storico ruoli</p>
      <ol className="relative space-y-2 border-l border-white/15 pl-4 text-[11px] text-surface-300">
        {data.map((h) => (
          <li key={h.id} className="relative">
            <span
              className={`absolute -left-[21px] top-1 h-2.5 w-2.5 rounded-full ${h.valid_to ? "bg-surface-400" : "bg-brand-400 pulse-ring"}`}
              aria-hidden="true"
            />
            <div className="flex flex-wrap items-center gap-2">
              <strong className="text-white">{h.role_name}</strong>
              {!h.valid_to && <Chip tone="ok">attuale</Chip>}
            </div>
            <div className="text-surface-400">
              dal {fmtDate(h.valid_from)}
              {h.valid_to ? ` al ${fmtDate(h.valid_to)}` : ""}
              {h.reason ? ` · ${h.reason}` : ""}
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}
