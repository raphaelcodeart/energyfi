"use client";

import { WhatsAppFab } from "@/components/whatsapp-support";
import { useCallback, useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";
import Image from "next/image";
import { AccountGate } from "@/components/account-gate";
import { AreaSwitcher } from "@/components/area-switcher";
import { CommandPalette, usePaletteShortcut } from "@/components/command-palette";
import { NotificationBell } from "@/components/notification-bell";
import { PulseGlobe } from "@/components/pulse-globe";
import { useScenePointer } from "@/components/scene-pointer";
import { SurfaceToggle } from "@/components/surface-toggle";
import { UserMenu } from "@/components/user-menu";
import { ShopCartButton, ShopCartPanel } from "@/components/shop-cart";
import { CartCheckoutModal, CartCheckoutShop } from "@/components/cart-checkout-modal";
import { sectionEnabled, useFeatures } from "@/lib/features";
import { useNotifications } from "@/lib/notification-meta";
import type { NotificationRead } from "@/lib/types";

/*
 * App shell on the red scene (globals.css §9):
 * - a floating command deck at the top. Sections are grouped; a group tab
 *   folds down a panel of section tiles, and ungrouped sections are tabs of
 *   their own;
 * - a hero with the section title, its sibling sections and the network
 *   globe;
 * - a floating dock and a full-screen menu on phones.
 * ⌘K still opens section search.
 */

export interface NavItem {
  key: string;
  label: string;
  description?: string;
  icon: ReactNode;
  /** Key of the NavGroup this section belongs to; none = a tab of its own. */
  group?: string;
  /**
   * Notification types that light the dot on this item. Items without
   * `notificationTypes` never show it.
   */
  notificationTypes?: string[];
}

export interface NavGroup {
  key: string;
  label: string;
  icon: ReactNode;
}

interface AppFrameProps {
  roleLabel: string;
  email?: string;
  navItems: NavItem[];
  navGroups?: NavGroup[];
  /** Sections in the phone dock, in order (up to 4); defaults to the first four. */
  dockKeys?: string[];
  activeKey: string;
  onNavigate: (key: string, filter?: string) => void;
  children: ReactNode;
  headerTitle?: string;
  headerSubtitle?: ReactNode;
  headerActions?: ReactNode;
  /** Stretches the header actions to the full width. */
  centerHeaderActions?: boolean;
  /**
   * Cart in the deck, visible from every tab, so it is not lost when the
   * customer leaves the Shop. Customer area only.
   */
  showCart?: boolean;
}


function LogoMark() {
  return (
    <span className="flex shrink-0 items-center rounded-2xl bg-white p-1.5 shadow-[0_10px_24px_-10px_rgba(255,255,255,0.7)]">
      <Image src="/logo.png" alt="SOS Affiliate" width={1200} height={231} priority className="h-6 w-auto" />
    </span>
  );
}

function DockButton({ item, active, unread, onClick }: { item: NavItem; active: boolean; unread: boolean; onClick: () => void }) {
  return (
    <button className="dock-item relative" data-active={active} onClick={onClick}>
      {item.icon}
      <span className="max-w-[72px] truncate">{item.label}</span>
      {unread && <span className="deck-dot" />}
    </button>
  );
}

type Entry = { kind: "item"; item: NavItem } | { kind: "group"; group: NavGroup; items: NavItem[] };

export function AppFrame({
  roleLabel,
  email,
  navItems,
  navGroups = [],
  dockKeys,
  activeKey,
  onNavigate,
  children,
  headerTitle,
  headerSubtitle,
  headerActions,
  showCart = false,
  centerHeaderActions = false,
}: AppFrameProps) {
  // Sections of switched-off features disappear everywhere at once: tabs,
  // fold-down panels, phone dock, search and user menu.
  const features = useFeatures();
  navItems = navItems.filter((item) => sectionEnabled(item.key, features));
  const [menuOpen, setMenuOpen] = useState(false);
  const [openGroup, setOpenGroup] = useState<string | null>(null);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [cartOpen, setCartOpen] = useState(false);
  const [cartCheckoutShop, setCartCheckoutShop] = useState<CartCheckoutShop | null>(null);
  const deckRef = useRef<HTMLElement>(null);

  // "← Indietro": the sections visited, however they were opened (menu, dock,
  // a tile or link inside a page), so one tap returns to the previous one.
  // Kept as state adjusted during render (React's "store the previous prop"
  // pattern): no effect, no ref read while rendering.
  const [seenKey, setSeenKey] = useState(activeKey);
  const [backStack, setBackStack] = useState<string[]>([]);
  const [goingBackTo, setGoingBackTo] = useState<string | null>(null);
  if (seenKey !== activeKey) {
    setSeenKey(activeKey);
    if (goingBackTo === activeKey) setGoingBackTo(null);
    else setBackStack((stack) => [...stack, seenKey].slice(-30));
  }

  const { unreadTypes } = useNotifications();
  useScenePointer();
  usePaletteShortcut(useCallback(() => setPaletteOpen(true), []));

  // Close the fold-down panel on Escape or a click outside the deck.
  useEffect(() => {
    if (!openGroup) return;
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") setOpenGroup(null);
    }
    function onClick(event: MouseEvent) {
      if (deckRef.current && !deckRef.current.contains(event.target as Node)) setOpenGroup(null);
    }
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onClick);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onClick);
    };
  }, [openGroup]);

  const groupByKey = new Map(navGroups.map((g) => [g.key, g]));
  // Ungrouped sections first, then the groups in the order they were given.
  const entries: Entry[] = [
    ...navItems.filter((item) => !item.group || !groupByKey.has(item.group)).map((item) => ({ kind: "item" as const, item })),
    ...navGroups
      .map((group) => ({ kind: "group" as const, group, items: navItems.filter((item) => item.group === group.key) }))
      .filter((entry) => entry.items.length > 0),
  ];

  const active = navItems.find((item) => item.key === activeKey) ?? navItems[0];
  const activeGroup = active?.group ? groupByKey.get(active.group) : undefined;
  const siblings = activeGroup ? navItems.filter((item) => item.group === activeGroup.key) : [];

  function go(key: string) {
    setOpenGroup(null);
    setMenuOpen(false);
    onNavigate(key);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  // Previous section still on the menu (a hidden one is skipped); with no
  // history the way back is the first section, the home.
  const visibleKeys = new Set(navItems.map((item) => item.key));
  const backIndex = backStack.findLastIndex((key) => visibleKeys.has(key) && key !== activeKey);
  const homeKey = navItems[0]?.key;
  const backKey = backIndex >= 0 ? backStack[backIndex] : homeKey !== activeKey ? homeKey : undefined;
  const backLabel = navItems.find((item) => item.key === backKey)?.label;

  function goBack() {
    if (!backKey) return;
    setBackStack((stack) => stack.slice(0, Math.max(0, backIndex)));
    setGoingBackTo(backKey);
    go(backKey);
  }

  function handleOpenNotification(notification: NotificationRead) {
    const targetKey = navItems.find((item) => item.notificationTypes?.includes(notification.type))?.key;
    if (targetKey) go(targetKey);
  }

  function hasUnread(item: NavItem) {
    return item.notificationTypes?.some((t) => unreadTypes.has(t)) ?? false;
  }

  const preferredDock = (dockKeys ?? [])
    .map((key) => navItems.find((item) => item.key === key))
    .filter((item): item is NavItem => item !== undefined);
  // Keep four shortcuts even when a preferred one is hidden.
  const dockItems = [...preferredDock, ...navItems.filter((item) => !preferredDock.includes(item))].slice(0, 4);

  const openEntry = entries.find((e) => e.kind === "group" && e.group.key === openGroup);

  return (
    <div className="min-h-screen">
      {/* ---- Scene layers ---- */}
      <div className="scene-floor" aria-hidden="true" />
      <div className="scene-orb" aria-hidden="true" style={{ left: "-10%", top: "20%", width: 520, height: 520, background: "#2a7cff" }} />
      <div
        className="scene-orb"
        aria-hidden="true"
        style={{ right: "-8%", top: "-10%", width: 460, height: 460, background: "#47e2ff", animationDelay: "-7s" } as CSSProperties}
      />

      {/* ---- Command deck ---- */}
      <header ref={deckRef} className="deck">
        <div className="flex h-[68px] items-center gap-3 px-3 lg:px-4">
          <button onClick={() => go(navItems[0]?.key ?? activeKey)} className="flex shrink-0 cursor-pointer items-center gap-3">
            <LogoMark />
            <span className="hidden text-left leading-tight sm:block">
              <span className="block text-[15px] font-black tracking-tight text-white">SOSNET</span>
              <span className="block text-[10px] font-bold uppercase tracking-[0.18em] text-surface-300">{roleLabel}</span>
            </span>
          </button>

          {/* Tabs (desktop) */}
          <nav className="mx-2 hidden min-w-0 flex-1 items-center gap-1 overflow-x-auto xl:flex [scrollbar-width:none]">
            {entries.map((entry) => {
              if (entry.kind === "item") {
                const item = entry.item;
                return (
                  <button key={item.key} className="deck-tab" data-active={item.key === activeKey} onClick={() => go(item.key)}>
                    {item.icon}
                    {item.label}
                    {hasUnread(item) && <span className="deck-dot" />}
                  </button>
                );
              }
              const { group, items } = entry;
              const containsActive = items.some((i) => i.key === activeKey);
              return (
                <button
                  key={group.key}
                  className="deck-tab"
                  data-active={containsActive}
                  aria-expanded={openGroup === group.key}
                  onClick={() => setOpenGroup((g) => (g === group.key ? null : group.key))}
                >
                  {group.icon}
                  {group.label}
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" className={`!h-3 !w-3 transition-transform ${openGroup === group.key ? "rotate-180" : ""}`}>
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M19 9l-7 7-7-7" />
                  </svg>
                  {items.some(hasUnread) && <span className="deck-dot" />}
                </button>
              );
            })}
          </nav>
          <div className="flex-1 xl:hidden" />

          <div className="flex shrink-0 items-center gap-2">
            <button
              onClick={() => setPaletteOpen(true)}
              className="hidden h-10 cursor-pointer items-center gap-2 rounded-xl bg-white/10 px-3 text-xs font-bold text-surface-200 transition hover:bg-white/20 hover:text-white 2xl:flex"
              title="Cerca una sezione"
            >
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.4} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
              <kbd className="font-mono text-[10px]">⌘K</kbd>
            </button>
            {showCart && <ShopCartButton onOpen={() => setCartOpen(true)} />}
            <AreaSwitcher />
            {/* On phones the switch lives in the full-screen menu, to keep the deck from overflowing. */}
            <SurfaceToggle className="hidden sm:grid" />
            <NotificationBell onOpenNotification={handleOpenNotification} />
            <UserMenu email={email} roleLabel={roleLabel} sections={navItems} onNavigate={go} />
          </div>
        </div>

        {openEntry && openEntry.kind === "group" && (
          <div className="mega">
            <div className="mb-3 flex items-center gap-2 px-1 text-[11px] font-extrabold uppercase tracking-[0.2em] text-surface-300">
              {openEntry.group.label}
            </div>
            <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
              {openEntry.items.map((item, i) => (
                <button
                  key={item.key}
                  className="mega-tile"
                  data-active={item.key === activeKey}
                  style={{ "--i": i } as CSSProperties}
                  onClick={() => go(item.key)}
                >
                  <span className="mega-icon">{item.icon}</span>
                  <span className="min-w-0">
                    <span className="block text-sm font-extrabold text-white">{item.label}</span>
                    {item.description && <span className="mt-0.5 block text-[11.5px] leading-snug text-surface-300">{item.description}</span>}
                  </span>
                  {hasUnread(item) && <span className="deck-dot" />}
                </button>
              ))}
            </div>
          </div>
        )}
      </header>

      {/* ---- Full-screen menu (phone) ---- */}
      {menuOpen && (
        <div className="fixed inset-0 z-50 overflow-y-auto bg-[#03111f]/95 p-5 backdrop-blur-xl xl:hidden animate-fade-in">
          <div className="mb-6 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <LogoMark />
              <span className="text-lg font-black text-white">SOSNET</span>
            </div>
            <div className="flex items-center gap-2">
            <SurfaceToggle />
            <button onClick={() => setMenuOpen(false)} className="grid h-11 w-11 cursor-pointer place-items-center rounded-2xl bg-white/10 text-white" aria-label="Chiudi il menu">
              <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.4} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
            </div>
          </div>
          <div className="space-y-6 pb-10">
            {entries.map((entry) => {
              const items = entry.kind === "item" ? [entry.item] : entry.items;
              return (
                <div key={entry.kind === "item" ? entry.item.key : entry.group.key}>
                  {entry.kind === "group" && (
                    <div className="mb-2 text-[11px] font-extrabold uppercase tracking-[0.2em] text-surface-300">{entry.group.label}</div>
                  )}
                  <div className="grid grid-cols-2 gap-2">
                    {items.map((item, i) => (
                      <button
                        key={item.key}
                        className="mega-tile !p-3"
                        data-active={item.key === activeKey}
                        style={{ "--i": i } as CSSProperties}
                        onClick={() => go(item.key)}
                      >
                        <span className="mega-icon !h-9 !w-9">{item.icon}</span>
                        <span className="text-[13px] font-bold text-white">{item.label}</span>
                      </button>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* ---- Content ---- */}
      <main className="px-4 pb-32 sm:px-6 lg:px-10 xl:pb-14">
        <section className="hero">
          <div className="min-w-0">
            {backKey && (
              <div className="mb-3 flex w-full">
              <button
                type="button"
                onClick={goBack}
                className="inline-flex items-center gap-1.5 rounded-full border border-[#bae6fd] bg-[#7dd3fc] px-4 py-2 text-sm font-bold text-[#0b1b3a] shadow-lg shadow-black/20 transition hover:bg-[#bae6fd] cursor-pointer"
                aria-label={backLabel ? `Indietro: ${backLabel}` : "Indietro"}
                title={backLabel ? `Torna a ${backLabel}` : undefined}
              >
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M15 19l-7-7 7-7" />
                </svg>
                Indietro
                {backLabel && <span className="hidden font-medium text-[#0b1b3a]/70 sm:inline">· {backLabel}</span>}
              </button>
              </div>
            )}
            <div className="hero-eyebrow">
              {activeGroup ? activeGroup.label : roleLabel}
            </div>
            <h1 key={active?.key} className="hero-title mt-3">
              {active?.label ?? headerTitle}
            </h1>
            {(headerTitle || active?.description) && (
              <p className="mt-3 max-w-2xl text-[15px] font-medium text-surface-200">
                {active?.description ?? headerTitle}
              </p>
            )}
            {headerSubtitle && <div className="mt-2 text-sm text-surface-300">{headerSubtitle}</div>}
            {siblings.length > 1 && (
              <div className="subnav mt-5">
                {siblings.map((item) => (
                  <button key={item.key} className="subnav-pill" data-active={item.key === activeKey} onClick={() => go(item.key)}>
                    {item.icon}
                    {item.label}
                  </button>
                ))}
              </div>
            )}
          </div>
          <div className="hero-globe">
            <PulseGlobe size={300} />
          </div>
        </section>

        {headerActions && <div className={`mb-6 ${centerHeaderActions ? "w-full" : "flex flex-wrap gap-3"}`}>{headerActions}</div>}

        <div className="pt-4">
          <AccountGate>{children}</AccountGate>
        </div>
      </main>

      {/* ---- Dock (phone): app-style bar, menu raised in the middle ---- */}
      <nav className="dock" aria-label="Scorciatoie">
        {dockItems.slice(0, 2).map((item) => (
          <DockButton key={item.key} item={item} active={item.key === activeKey} unread={hasUnread(item)} onClick={() => go(item.key)} />
        ))}
        <button className="dock-center" onClick={() => setMenuOpen(true)} aria-label="Apri il menu">
          <svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.4} d="M4 6h16M4 12h16M4 18h16" />
          </svg>
        </button>
        {dockItems.slice(2, 4).map((item) => (
          <DockButton key={item.key} item={item} active={item.key === activeKey} unread={hasUnread(item)} onClick={() => go(item.key)} />
        ))}
      </nav>

      <WhatsAppFab />

      <CommandPalette
        entries={navItems}
        open={paletteOpen}
        onClose={() => setPaletteOpen(false)}
        onSelect={(key) => go(key)}
        activeKey={activeKey}
      />

      {showCart && (
        <ShopCartPanel
          open={cartOpen}
          onClose={() => setCartOpen(false)}
          onCheckout={(shop) => {
            // Close the panel: editing the cart while paying for it could charge for
            // something other than what was confirmed.
            setCartOpen(false);
            // Only shops that have a checkout window.
            if (shop !== "catalog") setCartCheckoutShop(shop);
          }}
        />
      )}
      {cartCheckoutShop && <CartCheckoutModal shop={cartCheckoutShop} onClose={() => setCartCheckoutShop(null)} />}
    </div>
  );
}
