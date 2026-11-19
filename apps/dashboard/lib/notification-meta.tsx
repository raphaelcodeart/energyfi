"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import type { ReactNode } from "react";
import type { NotificationRead } from "@/lib/types";

/* Notification type registry and data access. Adding a type means touching
   the two tables below; the bell component stays purely presentational. */

export const NOTIFICATION_TYPE_LABELS: Record<string, string> = {
  CONTRACT_CREATED: "Nuovo contratto",
  TICKET_CREATED: "Nuovo ticket",
  PROMOTER_APPROVAL_REQUESTED: "Promoter da approvare",
  PROMOTER_APPROVED: "Promoter approvato",
  PROMOTER_REJECTED: "Promoter non approvato",
  COMMISSION_EARNED: "Nuova provvigione",
  CASHBACK_RECEIVED: "Cashback ricevuto",
  WALLET_TRANSFER_RECEIVED: "SosnetCash ricevuti",
  INVOICE_REDEMPTION_VERIFIED: "Fattura verificata",
  INVOICE_REDEMPTION_REJECTED: "Fattura rifiutata",
  ORDER_CREDIT_APPLIED: "SosnetCash usati per un ordine",
  ORDER_PAID: "Ordine confermato",
  ORDER_PAYMENT_PROOF_UPLOADED: "Prova di pagamento caricata",
  INVOICE_REDEMPTION_PAYMENT_PROOF_UPLOADED: "Prova di pagamento riscatto caricata",
  IMPORTED_ORDER_CREATED: "Nuovo ordine Acquisti SOSNET",
  CJ_ORDER_CREATED: "Nuovo ordine Shop Sosnet Partner",
  CJ_ORDER_PAID: "Ordine Shop Sosnet Partner pagato",
  CJ_ORDER_FAILED: "Ordine Shop Sosnet Partner da controllare",
  CJ_PAYMENT_REQUIRED: "Pagamento CJ richiesto",
  SHOPIFY_ORDER_CREATED: "Nuovo ordine Shopify",
  SHOPIFY_ORDER_PAID: "Ordine Shopify pagato",
  SHOPIFY_ORDER_FAILED: "Ordine Shopify da controllare",
  ALIEXPRESS_ORDER_CREATED: "Nuovo ordine AliExpress",
  ALIEXPRESS_ORDER_PAID: "Ordine AliExpress pagato",
  ALIEXPRESS_ORDER_FAILED: "Ordine AliExpress da controllare",
  ORDER_SHIPPED: "Aggiornamento spedizione",
};

export const NOTIFICATION_TYPE_ICONS: Record<string, ReactNode> = {
  CONTRACT_CREATED: (
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 17V7m0 10a2 2 0 01-2 2H5a2 2 0 01-2-2V7a2 2 0 012-2h2a2 2 0 012 2m0 10a2 2 0 002 2h2a2 2 0 002-2M9 7a2 2 0 012-2h2a2 2 0 012 2m0 10V7m0 10a2 2 0 002 2h2a2 2 0 002-2V7a2 2 0 00-2-2h-2a2 2 0 00-2 2" />
  ),
  TICKET_CREATED: (
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
  ),
  PROMOTER_APPROVAL_REQUESTED: (
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 20h5v-2a4 4 0 00-3-3.87M9 20H4v-2a4 4 0 013-3.87m6-1.13a4 4 0 10-4-4 4 4 0 004 4zm6 0a4 4 0 10-4-4" />
  ),
  PROMOTER_APPROVED: (
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
  ),
  PROMOTER_REJECTED: (
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
  ),
  COMMISSION_EARNED: (
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V6m0 10v2" />
  ),
  CASHBACK_RECEIVED: (
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V6m0 10v2" />
  ),
  WALLET_TRANSFER_RECEIVED: (
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 8l4 4m0 0l-4 4m4-4H3" />
  ),
  INVOICE_REDEMPTION_VERIFIED: (
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
  ),
  INVOICE_REDEMPTION_REJECTED: (
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
  ),
  ORDER_CREDIT_APPLIED: (
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a2 2 0 00-2-2H7a2 2 0 00-2 2m16 0v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6m16 0V9a2 2 0 00-2-2H5a2 2 0 00-2 2v3m16 0h-4a1 1 0 00-1 1v0a1 1 0 001 1h4" />
  ),
  ORDER_PAID: (
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16.5 7.5h-9v9h9v-9zM3 6a3 3 0 013-3h12a3 3 0 013 3v12a3 3 0 01-3 3H6a3 3 0 01-3-3V6z" />
  ),
  IMPORTED_ORDER_CREATED: (
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16.5 7.5h-9v9h9v-9zM3 6a3 3 0 013-3h12a3 3 0 013 3v12a3 3 0 01-3 3H6a3 3 0 01-3-3V6z" />
  ),  ORDER_SHIPPED: (
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16V6a1 1 0 00-1-1H4a1 1 0 00-1 1v10a1 1 0 001 1h1m8-1a1 1 0 01-1 1H9m4-1V8a1 1 0 011-1h2.586a1 1 0 01.707.293l3.414 3.414a1 1 0 01.293.707V16a1 1 0 01-1 1h-1m-6-1a1 1 0 001 1h1M5 17a2 2 0 104 0m-4 0a2 2 0 114 0m6 0a2 2 0 104 0m-4 0a2 2 0 114 0" />
  ),
};

export function timeAgo(iso: string): string {
  const seconds = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (seconds < 60) return "adesso";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} min fa`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} ${hours === 1 ? "ora" : "ore"} fa`;
  const days = Math.floor(hours / 24);
  return `${days} ${days === 1 ? "giorno" : "giorni"} fa`;
}

/** Single source of notifications. A 25-second poll is enough for a few
 *  dozen events a day, cheaper than a WebSocket. The shared query key lets
 *  the shell and the bell read one cache. */
export const NOTIFICATIONS_QUERY_KEY = ["notifications", "mine"] as const;

export async function fetchNotifications(): Promise<NotificationRead[]> {
  const res = await fetch("/api/proxy/notifications/mine");
  if (!res.ok) return [];
  return res.json();
}

export function useNotifications() {
  const queryClient = useQueryClient();
  const { data } = useQuery({
    queryKey: NOTIFICATIONS_QUERY_KEY,
    queryFn: fetchNotifications,
    refetchInterval: 25_000,
  });

  const list = data ?? [];

  return {
    list,
    unreadCount: list.filter((n) => !n.is_read).length,
    /** Unread types, to light the dot on the matching menu entry. */
    unreadTypes: new Set(list.filter((n) => !n.is_read).map((n) => n.type)),
    async markRead(id: string) {
      await fetch(`/api/proxy/notifications/${id}/read`, { method: "PATCH" });
      queryClient.invalidateQueries({ queryKey: NOTIFICATIONS_QUERY_KEY });
    },
    async markAllRead() {
      await fetch("/api/proxy/notifications/mark-all-read", { method: "POST" });
      queryClient.invalidateQueries({ queryKey: NOTIFICATIONS_QUERY_KEY });
    },
  };
}

export function notificationLabel(type: string): string {
  return NOTIFICATION_TYPE_LABELS[type] ?? type;
}

export function notificationIcon(type: string): ReactNode {
  return (
    NOTIFICATION_TYPE_ICONS[type] ?? (
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01" />
    )
  );
}
