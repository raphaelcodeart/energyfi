"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useDualRoleAreas } from "@/components/area-switcher";
import { useTheme } from "@/lib/theme";

/** Avatar initials when there is no photo, from the email's local part
 *  split on common separators. */
export function initialsFromEmail(email?: string): string {
  const local = (email || "?").split("@")[0] ?? "?";
  return (
    local
      .split(/[._-]/)
      .map((part) => part[0] ?? "")
      .join("")
      .slice(0, 2)
      .toUpperCase() || "?"
  );
}

/** Sections offered as shortcuts in the menu, in this order, when the area has them. */
const SHORTCUT_KEYS = [
  "profile", "wallet", "commissions", "orders", "plans", "invita-amici", "friend-referrals",
  "support", "tickets", "documentation", "settings",
];

export interface UserMenuShortcut {
  key: string;
  label: string;
  icon: ReactNode;
}

export function UserMenu({
  email,
  roleLabel,
  sections = [],
  onNavigate,
}: {
  email?: string;
  roleLabel: string;
  /** The area's sections; the useful ones become shortcuts. */
  sections?: UserMenuShortcut[];
  onNavigate?: (key: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const router = useRouter();
  const { hasBothRoles, isCustomerArea } = useDualRoleAreas();
  const { theme, toggleTheme } = useTheme();

  useEffect(() => {
    if (!open) return;
    function onClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    function onEscape(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onClickOutside);
    document.addEventListener("keydown", onEscape);
    return () => {
      document.removeEventListener("mousedown", onClickOutside);
      document.removeEventListener("keydown", onEscape);
    };
  }, [open]);

  async function handleLogout() {
    await fetch("/api/auth/logout", { method: "POST" });
    router.push("/login");
    router.refresh();
  }

  const shortcuts = SHORTCUT_KEYS.map((key) => sections.find((s) => s.key === key))
    .filter((s): s is UserMenuShortcut => s !== undefined)
    .slice(0, 6);
  const row =
    "flex w-full cursor-pointer items-center gap-3 rounded-xl px-3 py-2.5 text-left text-[13px] font-semibold text-surface-100 transition hover:bg-white/10 hover:text-white [&_svg]:h-[18px] [&_svg]:w-[18px] [&_svg]:shrink-0";

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((v) => !v)}
        className="grid h-9 w-9 cursor-pointer place-items-center rounded-xl bg-gradient-to-br from-brand-500 to-accent-400 text-[11px] font-bold text-white shadow-lg shadow-brand-500/25 transition hover:scale-105"
        aria-label="Menu utente"
        aria-expanded={open}
      >
        {initialsFromEmail(email)}
      </button>

      {open && (
        <div className="pop absolute right-0 top-12 z-50 w-72 overflow-hidden rounded-3xl bg-gradient-to-b from-[#08294e] to-[#031323] p-2 shadow-[0_40px_90px_-30px_rgba(0,0,0,0.95)] ring-1 ring-white/15">
          {/* Who is signed in */}
          <div className="flex items-center gap-3 rounded-2xl bg-white/5 p-3">
            <span className="grid h-11 w-11 shrink-0 place-items-center rounded-2xl bg-gradient-to-br from-brand-500 to-accent-400 text-sm font-black text-white">
              {initialsFromEmail(email)}
            </span>
            <span className="min-w-0">
              <span className="block truncate text-sm font-bold text-white">{email}</span>
              <span className="block truncate text-[11px] font-semibold uppercase tracking-wider text-surface-300">{roleLabel}</span>
            </span>
          </div>

          {hasBothRoles && (
            <Link
              href={isCustomerArea ? "/promoter" : "/customer"}
              onClick={() => setOpen(false)}
              className="mt-2 flex items-center gap-3 rounded-2xl bg-gradient-to-r from-brand-600 to-accent-500 px-3 py-3 text-white shadow-lg shadow-brand-600/30 transition hover:brightness-110"
            >
              <svg className="h-5 w-5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7h12m0 0l-4-4m4 4l-4 4M16 17H4m0 0l4 4m-4-4l4-4" />
              </svg>
              <span className="min-w-0">
                <span className="block text-[13px] font-extrabold">{isCustomerArea ? "Area Promoter" : "Area Cliente"}</span>
                <span className="block text-[11px] text-white/80">
                  {isCustomerArea ? "La tua rete, i compensi e i piani" : "I tuoi ordini, il portafoglio e il profilo"}
                </span>
              </span>
            </Link>
          )}

          {shortcuts.length > 0 && onNavigate && (
            <div className="mt-2">
              <p className="px-3 pb-1 pt-2 text-[10px] font-extrabold uppercase tracking-[0.18em] text-surface-400">Vai a</p>
              {shortcuts.map((item) => (
                <button
                  key={item.key}
                  className={row}
                  onClick={() => {
                    setOpen(false);
                    onNavigate(item.key);
                  }}
                >
                  {item.icon}
                  {item.label}
                </button>
              ))}
            </div>
          )}

          <div className="mt-2 border-t border-white/10 pt-2">
            <button className={row} onClick={toggleTheme}>
              {theme === "light" ? (
                <svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
                </svg>
              ) : (
                <svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
                </svg>
              )}
              {theme === "light" ? "Modalità notte" : "Modalità chiara"}
            </button>
            <Link href={`/forgot-password${email ? `?email=${encodeURIComponent(email)}` : ""}`} className={row} onClick={() => setOpen(false)}>
              <svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z" />
              </svg>
              Cambia password
            </Link>
            <button onClick={handleLogout} className={`${row} !text-danger-300 hover:!bg-danger-500/15`}>
              <svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
              </svg>
              Esci
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
