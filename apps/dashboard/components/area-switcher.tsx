"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { usePathname } from "next/navigation";

async function fetchMyRoles(): Promise<string[]> {
  const res = await fetch("/api/proxy/auth/me");
  if (!res.ok) return [];
  const data = await res.json();
  return data.roles ?? [];
}

/**
 * Shared by AreaSwitcher and the UserMenu entry. Uses live roles rather than
 * the access token's (only as fresh as the last login/refresh, see
 * auth/router.py get_me), so it reacts immediately to activation or
 * deactivation.
 */
export function useDualRoleAreas() {
  const pathname = usePathname();
  const { data: roles = [] } = useQuery({
    queryKey: ["auth", "me", "roles"],
    queryFn: fetchMyRoles,
    staleTime: 30_000,
    refetchOnWindowFocus: true,
  });

  return {
    hasBothRoles: roles.includes("CUSTOMER") && roles.includes("PROMOTER"),
    isCustomerArea: pathname?.startsWith("/customer") ?? false,
  };
}

/**
 * Customer/promoter toggle for users holding both roles; renders nothing
 * otherwise. Shown on every screen size: on phones the labels shorten.
 */
export function AreaSwitcher() {
  const { hasBothRoles, isCustomerArea } = useDualRoleAreas();

  if (!hasBothRoles) return null;

  const item = (active: boolean) =>
    `flex h-8 items-center gap-1.5 rounded-lg px-2.5 text-[11.5px] font-extrabold transition sm:px-3 ${
      active
        ? "bg-white text-[#041f3a] shadow-[0_8px_20px_-10px_rgba(255,255,255,0.8)]"
        : "text-surface-200 hover:bg-white/10 hover:text-white"
    }`;

  return (
    <div className="inline-flex items-center gap-1 rounded-xl bg-black/25 p-1 ring-1 ring-white/10" role="group" aria-label="Cambia area">
      <Link href="/customer" className={item(isCustomerArea)} aria-current={isCustomerArea ? "page" : undefined}>
        <span className="sm:hidden">Cliente</span>
        <span className="hidden sm:inline">Area Cliente</span>
      </Link>
      <Link href="/promoter" className={item(!isCustomerArea)} aria-current={!isCustomerArea ? "page" : undefined}>
        <span className="sm:hidden">Promoter</span>
        <span className="hidden sm:inline">Area Promoter</span>
      </Link>
    </div>
  );
}
