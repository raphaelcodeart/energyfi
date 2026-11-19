"use client";

import { useEffect, useRef, useState } from "react";
import {
  notificationIcon,
  notificationLabel,
  timeAgo,
  useNotifications,
} from "@/lib/notification-meta";
import type { NotificationRead } from "@/lib/types";

/** Notification bell and panel, presentation only. Data and mutations live in
 *  `lib/notification-meta`, sharing one cache with the app shell. */
export function NotificationBell({
  onOpenNotification,
}: {
  onOpenNotification: (n: NotificationRead) => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const { list, unreadCount, markRead, markAllRead } = useNotifications();

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

  async function handleClick(notification: NotificationRead) {
    setOpen(false);
    if (!notification.is_read) await markRead(notification.id);
    onOpenNotification(notification);
  }

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((v) => !v)}
        className={`relative grid h-9 w-9 cursor-pointer place-items-center rounded-xl border border-white/5 light:border-surface-200 text-surface-300 light:text-surface-600 transition hover:border-brand-500/40 hover:text-white light:hover:text-surface-900 ${
          unreadCount > 0 ? "bg-brand-500/10" : "bg-white/5 light:bg-surface-900/5"
        }`}
        aria-label={unreadCount > 0 ? `Notifiche (${unreadCount} da leggere)` : "Notifiche"}
      >
        <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
        </svg>
        {unreadCount > 0 && (
          <span className="absolute -right-1 -top-1 flex h-4 min-w-[16px] items-center justify-center rounded-full bg-brand-500 px-1 text-[9px] font-bold text-white pulse-ring">
            {unreadCount > 9 ? "9+" : unreadCount}
          </span>
        )}
      </button>

      {open && (
        <div className="pop absolute right-0 top-12 z-50 max-h-[440px] w-84 overflow-y-auto rounded-2xl border border-white/10 light:border-surface-200 bg-surface-900 light:bg-white shadow-2xl">
          <div className="sticky top-0 flex items-center justify-between border-b border-white/5 light:border-surface-100 bg-surface-900 light:bg-white px-4 py-3">
            <p className="text-sm font-semibold text-white light:text-surface-900">Notifiche</p>
            {unreadCount > 0 && (
              <button
                onClick={markAllRead}
                className="cursor-pointer text-[11px] text-brand-400 transition hover:text-brand-300"
              >
                Segna tutte come lette
              </button>
            )}
          </div>

          {list.length === 0 ? (
            <p className="py-10 text-center text-xs text-surface-500">Nessuna notifica.</p>
          ) : (
            <div className="stagger divide-y divide-white/5 light:divide-surface-100">
              {list.map((n, i) => (
                <button
                  key={n.id}
                  style={{ "--i": i } as React.CSSProperties}
                  onClick={() => handleClick(n)}
                  className={`flex w-full cursor-pointer items-start gap-3 px-4 py-3 text-left transition hover:bg-white/5 light:hover:bg-surface-50 ${
                    !n.is_read ? "bg-brand-500/5" : ""
                  }`}
                >
                  <span className="mt-0.5 shrink-0 rounded-lg bg-brand-500/10 p-1.5 text-brand-400">
                    <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      {notificationIcon(n.type)}
                    </svg>
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="flex items-center gap-1.5">
                      <span className="truncate text-xs font-semibold text-white light:text-surface-900">{n.title}</span>
                      {!n.is_read && <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-brand-500" />}
                    </span>
                    {n.body && (
                      <span className="mt-0.5 block line-clamp-2 text-[11px] text-surface-400 light:text-surface-500">
                        {n.body}
                      </span>
                    )}
                    <span className="mt-1 block text-[10px] text-surface-500">
                      {notificationLabel(n.type)} · {timeAgo(n.created_at)}
                    </span>
                  </span>
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
