"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { friendlyApiError } from "@/lib/api-error";
import type { AgentLookup, AgentPageRead } from "@/lib/types";

/** The collaborator registry, read a page at a time: the organization may
    hold tens of thousands of people, so no screen downloads it whole. */

export type AgentPageParams = {
  page: number;
  pageSize: number;
  search?: string;
  status?: string;
  sort?: "recent" | "oldest" | "name" | "code";
  parentId?: string;
};

async function getJson<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(await friendlyApiError(res));
  return res.json();
}

export function agentPageUrl(p: AgentPageParams): string {
  const q = new URLSearchParams({ page: String(p.page), page_size: String(p.pageSize) });
  if (p.search?.trim()) q.set("search", p.search.trim());
  if (p.status && p.status !== "ALL") q.set("status", p.status);
  if (p.sort) q.set("sort", p.sort);
  if (p.parentId) q.set("parent_id", p.parentId);
  return `/api/proxy/network/agents/page?${q}`;
}

/** One page; the previous page stays on screen while the next one loads. */
export function useAgentPage(p: AgentPageParams) {
  return useQuery({
    queryKey: ["admin", "agents", "page", p],
    queryFn: () => getJson<AgentPageRead>(agentPageUrl(p)),
    placeholderData: keepPreviousData,
  });
}

export function lookupAgents(q: string, status?: string): Promise<AgentLookup[]> {
  const params = new URLSearchParams({ q, limit: "20" });
  if (status) params.set("status", status);
  return getJson<AgentLookup[]>(`/api/proxy/network/agents/lookup?${params}`);
}

/** Names of the given ids (for showing who is already chosen). */
export function useAgentNames(ids: (string | null | undefined)[]) {
  const wanted = [...new Set(ids.filter((x): x is string => !!x))].sort();
  return useQuery({
    queryKey: ["admin", "agents", "names", wanted],
    queryFn: () => getJson<AgentLookup[]>(`/api/proxy/network/agents/lookup?ids=${wanted.join(",")}`),
    enabled: wanted.length > 0,
    staleTime: 5 * 60_000,
    select: (rows) => new Map(rows.map((r) => [r.id, r])),
  });
}

export function exportAgentsCsvUrl(search?: string, status?: string): string {
  const q = new URLSearchParams();
  if (search?.trim()) q.set("search", search.trim());
  if (status && status !== "ALL") q.set("status", status);
  return `/api/proxy/network/agents/export.csv${q.size ? `?${q}` : ""}`;
}
