"use client";

import { sectionEnabled, useFeatures } from "@/lib/features";
import { ExternalWalletStats } from "@/components/external-wallet-stats";
import { VirtualNetworkButton } from "@/components/affiliate/virtual-network-button";
import { ProfilePanel } from "@/components/profile-panel";
import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { ShareButtons } from "@/components/share-buttons";
import { Chip } from "@/components/ui/data-cells";
import { AppFrame, type NavGroup, type NavItem } from "@/components/app-frame";
import { BranchTable } from "@/components/branch-table";
import { DashboardWalletStats } from "@/components/dashboard-wallet-stats";
import { WelcomeBonusCard } from "@/components/welcome-bonus-card";
import { BranchVisualizer } from "@/components/branch-visualizer";
import { AgentCardModal } from "@/components/agent-card-page";
import { MyPlansPanel } from "@/components/my-plans-panel";
import { MyCompaniesCard } from "@/components/my-companies-card";
import { MyCommissions } from "@/components/my-commissions";
import { CommissionSimulator } from "@/components/commission-simulator";
import { LeadsPanel } from "@/components/leads-panel";
import { CustomerProductsPanel } from "@/components/customer-products-panel";
import { FriendReferralsPanel } from "@/components/friend-referrals-panel";
import { NetworkCustomersPanel } from "@/components/network-customers-panel";
import { DocumentationFeed } from "@/components/documentation-feed";
import { PromoterAziendaPanel } from "@/components/promoter-azienda-panel";
import { RecruitForm } from "@/components/recruit-form";
import { SupportTicketsPanel } from "@/components/support-tickets-panel";
import { WhatsAppSupportPage } from "@/components/whatsapp-support";
import { SHOW_SUPPORT_TICKETS } from "@/lib/support";
import { WalletPanel } from "@/components/wallet-panel";
import { InvoiceRedemptionPanel } from "@/components/invoice-redemption-panel";
import { AmbassadorPanel, type AmbassadorView } from "@/components/affiliate/ambassador-panel";
import type { AgentProfileRead, BranchMemberRead, CommercialRoleRead, PromoterCodeRead, RoleHistoryRow } from "@/lib/types";

// Temporarily off: Digital Ambassadors must not copy or share their promoter
// link for now. Set back to true to show the share box in the header again.
const SHOW_PROMOTER_LINK = false;

interface PromoterClientPageProps {
  me: AgentProfileRead | null;
  branch: BranchMemberRead[];
  email?: string;
  organizationId?: string;
}

async function fetchMyReferralCode(): Promise<PromoterCodeRead | null> {
  const res = await fetch("/api/proxy/referral/mine");
  if (!res.ok) throw new Error("Impossibile caricare il link referral.");
  return res.json();
}

type MyCommercialProfile = {
  agent_id: string;
  role: CommercialRoleRead | null;
  role_history: RoleHistoryRow[];
  sponsor: { name: string; promoter_code: string } | null;
  direct_count: number;
};

async function fetchMyCommercialProfile(): Promise<MyCommercialProfile | null> {
  const res = await fetch("/api/proxy/commercial/me");
  if (!res.ok) throw new Error("Impossibile caricare il tuo ruolo.");
  return res.json();
}

const svgProps = { className: "w-5 h-5", fill: "none", viewBox: "0 0 24 24", stroke: "currentColor" } as const;

const NAV_GROUPS: NavGroup[] = [
  {
    key: "sos",
    label: "SOS Affiliate",
    icon: <svg {...svgProps}><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 3v4M3 5h4M6 17v4m-2-2h4m5-16l2.286 6.857L21 12l-5.714 2.143L13 21l-2.286-6.857L5 12l5.714-2.143L13 3z" /></svg>,
  },
  {
    key: "network",
    label: "Rete",
    icon: <svg {...svgProps}><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 20h5v-2a4 4 0 00-3-3.87M9 20H4v-2a4 4 0 013-3.87m6-1.13a4 4 0 10-4-4 4 4 0 004 4zm6 0a4 4 0 10-4-4" /></svg>,
  },
  {
    key: "sales",
    label: "Vendite",
    icon: <svg {...svgProps}><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" /></svg>,
  },
  {
    key: "money",
    label: "Denaro",
    icon: <svg {...svgProps}><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V6m0 10v2M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>,
  },
  {
    key: "help",
    label: "Aiuto",
    icon: <svg {...svgProps}><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>,
  },
];

// SOS Affiliate: the Digital Ambassador area (components/affiliate). These
// come first: the plan is what this console is for.
const SOS_ITEMS: NavItem[] = [
  { key: "sos-plan", label: "Il mio piano", description: "Punti personali e della rete, gambe, livello del mese e bonus maturati.",
    icon: <svg {...svgProps}><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" /></svg> },
  { key: "sos-orders", group: "sos", label: "I miei ordini Mamify", description: "Gli acquisti fatti su Mamify con il tuo account e i punti che ti hanno dato.",
    icon: <svg {...svgProps}><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" /></svg> },
  { key: "sos-shop", group: "sos", label: "Acquista", description: "Mensilità Digital Ambassador, pacchetti licenze e biglietti dell'Evento Roma.",
    icon: <svg {...svgProps}><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 3h2l.4 2M7 13h10l4-8H5.4M7 13L5.4 5M7 13l-2.293 2.293c-.63.63-.184 1.707.707 1.707H17m0 0a2 2 0 100 4 2 2 0 000-4zm-8 2a2 2 0 11-4 0 2 2 0 014 0z" /></svg> },
  { key: "sos-licenses", group: "sos", label: "Le mie licenze", description: "Licenze disponibili e rivendute alle imprese, con il tuo margine.",
    icon: <svg {...svgProps}><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4M7.835 4.697a3.42 3.42 0 001.946-.806 3.42 3.42 0 014.438 0 3.42 3.42 0 001.946.806 3.42 3.42 0 013.138 3.138 3.42 3.42 0 00.806 1.946 3.42 3.42 0 010 4.438 3.42 3.42 0 00-.806 1.946 3.42 3.42 0 01-3.138 3.138 3.42 3.42 0 00-1.946.806 3.42 3.42 0 01-4.438 0 3.42 3.42 0 00-1.946-.806 3.42 3.42 0 01-3.138-3.138 3.42 3.42 0 00-.806-1.946 3.42 3.42 0 010-4.438 3.42 3.42 0 00.806-1.946 3.42 3.42 0 013.138-3.138z" /></svg> },
  { key: "sos-clients", group: "sos", label: "Imprese clienti", description: "Le imprese che segui: vendita dei Pack e ricariche MamiCash.",
    icon: <svg {...svgProps}><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" /></svg> },
  { key: "sos-earnings", group: "sos", label: "I miei bonus", description: "Bonus Carriera, Vendita Diretta, MamiCash e rivendite, separati.",
    notificationTypes: ["COMMISSION_EARNED"],
    icon: <svg {...svgProps}><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V6m0 10v2M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg> },
  { key: "sos-network", group: "sos", label: "La mia rete", description: "Il tuo albero ramo per ramo: punti del mese, livelli, gambe e contatti.",
    icon: <svg {...svgProps}><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 5a2 2 0 100-4 2 2 0 000 4zm-7 9a2 2 0 100-4 2 2 0 000 4zm14 0a2 2 0 100-4 2 2 0 000 4zm-7 9a2 2 0 100-4 2 2 0 000 4zM12 5v4m0 0l-5.5 3M12 9l5.5 3M12 19v-4m0 0l-5.5-3M12 15l5.5-3" /></svg> },
  { key: "sos-history", group: "sos", label: "Storico operazioni", description: "Ogni acquisto, vendita e ricarica con il suo stato.",
    icon: <svg {...svgProps}><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" /></svg> },
];

/** Sections of the inherited energy/contracts model, kept in the code but
 * out of the SOS Affiliate console. */
const HIDDEN_KEYS = new Set(["azienda", "customers", "leads", "products", "plans", "simulator", "commissions", "cashback", "invita-amici"]);

// The first four sections fill the phone dock.
const LEGACY_NAV_ITEMS: NavItem[] = [
  {
    key: "azienda",
    description: "I tuoi piani, gli accessi rapidi e l'andamento della tua attività.",
    label: "Il mio quadro",
    notificationTypes: ["PROMOTER_APPROVED", "PROMOTER_REJECTED"],
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 21h18M5 21V7l8-4v18M19 21V11l-6-4" />
      </svg>
    ),
  },
  {
    key: "customers",
    group: "network",
    description: "I clienti che hai portato e i loro contratti.",
    label: "I miei clienti",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
      </svg>
    ),
  },
  {
    key: "commissions",
    group: "money",
    description: "Provvigioni dirette, indirette e fee, con lo stato di ognuna.",
    label: "I miei compensi",
    notificationTypes: ["COMMISSION_EARNED"],
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 7h6m0 10v-3m-3 3v-6m-3 6v-1m6-13H9a2 2 0 00-2 2v14a2 2 0 002 2h6a2 2 0 002-2V6a2 2 0 00-2-2z" />
      </svg>
    ),
  },
  {
    key: "network",
    group: "network",
    description: "Il tuo albero commerciale fino a 12 livelli.",
    label: "La mia rete",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 20h5v-2a4 4 0 00-3-3.87M9 20H4v-2a4 4 0 013-3.87m6-1.13a4 4 0 10-4-4 4 4 0 004 4zm6 0a4 4 0 10-4-4" />
      </svg>
    ),
  },
  {
    // Not the commission network: the flat friend-invite list every account has
    // (friend_referrals/models.py).
    key: "invita-amici",
    group: "network",
    description: "Invita amici col tuo link e segui i premi.",
    label: "Porta un amico",
    notificationTypes: ["FRIEND_REFERRAL_ACTIVATED", "FRIEND_REFERRAL_REWARD_HANDLED"],
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z" />
      </svg>
    ),
  },
  {
    key: "leads",
    group: "network",
    description: "I contatti che hai segnalato e come stanno andando.",
    label: "Le mie segnalazioni",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5.882V19.24a1.76 1.76 0 01-3.417.592l-2.147-6.15M18 13a3 3 0 100-6M5.436 13.683A4.001 4.001 0 017 6h1.832c4.1 0 7.625-1.234 9.168-3v14c-1.543-1.766-5.067-3-9.168-3H7a3.988 3.988 0 01-1.564-.317z" />
      </svg>
    ),
  },
  {
    key: "products",
    group: "sales",
    description: "Il catalogo da proporre, pronto da condividere.",
    label: "Cosa posso proporre",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />
      </svg>
    ),
  },
  {
    key: "plans",
    group: "sales",
    description: "I piani provvigionali con cui lavori: quanto ti rende ogni prodotto e cosa hai già guadagnato.",
    label: "I miei piani",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 3.055A9.001 9.001 0 1020.945 13H11V3.055z" />
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20.488 9H15V3.512A9.025 9.025 0 0120.488 9z" />
      </svg>
    ),
  },
  {
    key: "simulator",
    group: "sales",
    description: "Stima quanto puoi guadagnare con la tua rete.",
    label: "Simulatore guadagni",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
      </svg>
    ),
  },
  {
    key: "wallet",
    group: "money",
    description: "Saldo SosnetCash e tutti i movimenti.",
    label: "Portafoglio",
    notificationTypes: ["CASHBACK_RECEIVED", "WALLET_TRANSFER_RECEIVED"],
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a2 2 0 00-2-2H7a2 2 0 00-2 2m16 0v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6m16 0V9a2 2 0 00-2-2H5a2 2 0 00-2 2v3m16 0h-4a1 1 0 00-1 1v0a1 1 0 001 1h4" />
      </svg>
    ),
  },
  {
    key: "cashback",
    group: "money",
    description: "Carica una fattura e trasformala in SosnetCash.",
    label: "Incassa il cashback",
    notificationTypes: ["INVOICE_REDEMPTION_VERIFIED", "INVOICE_REDEMPTION_REJECTED"],
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 14l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    ),
  },
  {
    key: "support",
    group: "help",
    description: "Scrivici su WhatsApp: ti risponde il nostro team.",
    label: "Assistenza",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
      </svg>
    ),
  },
  {
    key: "profile",
    group: "help",
    description: "Codice fiscale e residenza, da compilare quando vuoi.",
    label: "Il mio profilo",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H5a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2V8a2 2 0 00-2-2h-5m-4 0V5a2 2 0 114 0v1m-4 0a2 2 0 104 0m-5 8a2 2 0 100-4 2 2 0 000 4zm0 0c1.306 0 2.417.835 2.83 2M9 14a3.001 3.001 0 00-2.83 2M15 11h3m-3 4h2" />
      </svg>
    ),
  },
  {
    key: "documentation",
    group: "help",
    description: "Guide, materiali e novità da consultare.",
    label: "Documentazione",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
      </svg>
    ),
  },
];

const NAV_ITEMS: NavItem[] = [...SOS_ITEMS, ...LEGACY_NAV_ITEMS.filter((item) => !HIDDEN_KEYS.has(item.key))];

/** Key -> rail label: the single source of section names. */
const NAV_LABEL_BY_KEY = new Map(NAV_ITEMS.map((item) => [item.key, item.label]));

/** Shortcut label, taken from the nav entry with the same key so the
    names cannot diverge. */
function labelForKey(key: string): string {
  return NAV_LABEL_BY_KEY.get(key) ?? key;
}

/** Home shortcuts: labels and icons come from the navigation. */
const QUICK_LINKS: { key: string; description: string; icon: React.ReactNode }[] = [
  { key: "network", description: "Il tuo albero e le schede dei collaboratori" },
  { key: "customers", description: "Clienti e nuovi contratti" },
  { key: "plans", description: "Aziende, piani e rete per prodotto" },
  { key: "leads", description: "Contatti da far diventare clienti" },
  { key: "commissions", description: "Quanto hai maturato e incassato" },
  { key: "simulator", description: "Quanto rende una vendita" },
  { key: "products", description: "Le offerte da proporre" },
  { key: "support", description: "Hai bisogno di aiuto?" },
].map((link) => ({ ...link, icon: LEGACY_NAV_ITEMS.find((item) => item.key === link.key)?.icon ?? null }));

const PROMOTER_VALID_TABS = [
  "sos-plan", "sos-orders", "sos-shop", "sos-licenses", "sos-clients", "sos-earnings", "sos-network", "sos-history",
  "azienda", "network", "invita-amici", "customers", "products", "commissions", "leads", "simulator", "plans", "support", "documentation", "profile", "wallet", "cashback",
] as const;

export function PromoterClientPage({ me, branch, email, organizationId }: PromoterClientPageProps) {
  const features = useFeatures();
  const [activeTab, setActiveTab] = useState<AmbassadorView | "azienda" | "network" | "invita-amici" | "customers" | "products" | "commissions" | "leads" | "simulator" | "plans" | "support" | "documentation" | "profile" | "wallet" | "cashback">("sos-plan");
  const [openAgentId, setOpenAgentId] = useState<string | null>(null);
  const router = useRouter();
  const searchParams = useSearchParams();
  const maxDepth = branch.reduce((max, m) => Math.max(max, m.depth), 0);

  // Opens the tab named in `?tab=` (e.g. from a wallet movement chip), then
  // clears the query.
  useEffect(() => {
    // Legacy "pratiche" links now open "Miei Clienti".
    const requested = searchParams.get("tab");
    const tab = requested === "pratiche" ? "customers" : requested;
    if (!tab || !(PROMOTER_VALID_TABS as readonly string[]).includes(tab)) return;
    setActiveTab(tab as typeof activeTab);
    router.replace("/promoter", { scroll: false });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const { data: referralCode } = useQuery({
    queryKey: ["promoter", "referral-mine"],
    queryFn: fetchMyReferralCode,
    enabled: !!me,
  });
  const { data: commercial } = useQuery({
    queryKey: ["promoter", "commercial-me"],
    queryFn: fetchMyCommercialProfile,
    enabled: !!me,
  });
  const personalLink = (() => {
    if (!referralCode || typeof window === "undefined") return "";
    const url = new URL(`/r/${referralCode.code}`, window.location.origin);
    if (organizationId) url.searchParams.set("org", organizationId);
    return url.toString();
  })();

  return (
    <AppFrame
      roleLabel="Area Digital Ambassador"
      email={email}
      navItems={NAV_ITEMS}
      navGroups={NAV_GROUPS}
      dockKeys={["sos-plan", "sos-shop", "sos-clients", "sos-earnings"]}
      activeKey={activeTab}
      onNavigate={(key) => setActiveTab(key as typeof activeTab)}
      headerTitle={`Benvenuto, ${me?.display_name || "Digital Ambassador"}`}
      centerHeaderActions
      headerActions={
        me ? (
          <div className="panel w-full flex flex-wrap items-center justify-between gap-5 rounded-3xl px-6 py-4">
            <div className="flex flex-wrap items-center gap-5">
              <div>
                <p className="kpi-label">Codice Digital Ambassador</p>
                <p className="mt-1 tag-id text-sm">{me.promoter_code}</p>
              </div>
              <div className="h-10 w-px bg-white/10" />
              <div>
                <p className="kpi-label">Il tuo ruolo</p>
                <p className="mt-1 text-xl font-black tracking-tight text-gradient leading-tight">{commercial?.role?.name ?? "—"}</p>
                <p className="text-[11px] text-surface-300 mt-0.5">
                  {commercial?.sponsor ? `Sponsor: ${commercial.sponsor.name}` : "Nessuno sponsor (radice)"}
                  {commercial ? ` · ${commercial.direct_count} diretti` : ""}
                </p>
              </div>
            </div>
            {/* Share targets shown directly, not behind a menu, since promoters
                share this link constantly. Icons only on phones to keep the header
                on one line. */}
            {SHOW_PROMOTER_LINK && (
              <div className="flex flex-col items-start sm:items-end gap-1.5">
                <p className="kpi-label">Condividi il tuo link</p>
                <ShareButtons
                  url={personalLink}
                  text="Diventa Digital Ambassador SOS Affiliate con il mio link:"
                  hideLabelsOnMobile
                />
              </div>
            )}
          </div>
        ) : undefined
      }
    >
      {!me ? (
        <div className="panel rise rounded-3xl p-10 text-center max-w-xl mx-auto mt-12">
          <svg className="float-soft w-14 h-14 text-danger-300 mx-auto mb-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <h3 className="text-xl font-black tracking-tight text-white">Nessun profilo agente</h3>
          <p className="text-sm text-surface-300 mt-2">
            Non è stato trovato alcun profilo promoter collegato a questo account. Contatta l&apos;amministratore del sistema per l&apos;assegnazione.
          </p>
        </div>
      ) : (
        <div>
          {activeTab.startsWith("sos-") && (
            <AmbassadorPanel view={activeTab as AmbassadorView} onNavigate={(key) => setActiveTab(key)} />
          )}
          {activeTab === "azienda" && (
            <div className="space-y-6">
              <div data-tilt className="panel sheen rise relative overflow-hidden rounded-3xl px-7 py-6">
                <p className="kpi-label">Bentornato</p>
                <h2 className="mt-1 text-2xl sm:text-3xl font-black tracking-tight text-gradient truncate max-w-[70vw] sm:max-w-none">{me.display_name}</h2>
                <span className="pointer-events-none absolute -right-10 -top-10 h-40 w-40 rounded-full bg-gradient-to-br from-brand-400/40 to-accent-400/10 blur-3xl" />
              </div>

              {features.welcome_bonus && <WelcomeBonusCard />}

              <MyCompaniesCard agentId={me.id} onOpenPlans={() => setActiveTab("plans")} />


              {features.wallet && <DashboardWalletStats />}
              {features.external_wallet && <ExternalWalletStats />}

              {/* Section shortcuts, as on the admin overview. */}
              <p className="kpi-label">Accesso rapido</p>
              <div className="stagger grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-7 gap-3">
                {QUICK_LINKS.filter((link) => sectionEnabled(link.key, features)).map((link, i) => (
                  <button
                    key={link.key}
                    data-tilt
                    style={{ "--i": i } as React.CSSProperties}
                    onClick={() => setActiveTab(link.key as typeof activeTab)}
                    className="panel group flex flex-col items-start gap-3 p-4 rounded-3xl cursor-pointer text-left"
                  >
                    <span className="p-2.5 rounded-2xl bg-gradient-to-br from-brand-500/30 to-accent-500/20 text-white shadow-lg shadow-brand-500/20 group-hover:from-brand-500 group-hover:to-accent-500 transition-colors">
                      {link.icon}
                    </span>
                    <span className="min-w-0">
                      <span className="block text-sm font-bold text-white truncate">
                        {labelForKey(link.key)}
                      </span>
                      <span className="block text-[11px] text-surface-300 truncate">{link.description}</span>
                    </span>
                  </button>
                ))}
              </div>

              <PromoterAziendaPanel agentId={me.id} />
            </div>
          )}

          {activeTab === "invita-amici" && (
            <div className="space-y-6">
              <FriendReferralsPanel organizationId={organizationId} />
            </div>
          )}

          {activeTab === "customers" && (
            <div className="space-y-6">
              <NetworkCustomersPanel />
            </div>
          )}

          {activeTab === "network" && (
            <div className="space-y-6">
              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
                <div className="flex flex-wrap items-center gap-2">
                  <Chip tone="accent">{branch.length} agenti nel ramo</Chip>
                  <Chip tone="info">Profondità massima: {maxDepth} / 12 livelli</Chip>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <VirtualNetworkButton />
                  <RecruitForm onRecruited={() => router.refresh()} />
                </div>
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                <div className="lg:col-span-2">
                  <BranchVisualizer members={branch} onOpenAgent={setOpenAgentId} />
                </div>
                <div className="panel rounded-3xl p-6">
                  <p className="kpi-label">Il tuo ramo</p>
                  <h3 className="mt-1 text-xl font-black tracking-tight text-white mb-2">Dettaglio ramo</h3>
                  <p className="text-xs text-surface-300 mb-6">
                    Elenco tabellare di tutti i collaboratori diretti e indiretti, fino a 12 livelli di profondità.
                  </p>
                  <div className="overflow-x-auto">
                    <BranchTable members={branch} onOpenAgent={setOpenAgentId} />
                  </div>
                </div>
              </div>
              {openAgentId && (
                <AgentCardModal
                  agentId={openAgentId}
                  onClose={() => setOpenAgentId(null)}
                  onOpenAgent={setOpenAgentId}
                  canOpen={(agentId) => branch.some((m) => m.agent_id === agentId)}
                />
              )}
            </div>
          )}

          {activeTab === "products" && (
            <div className="space-y-6">
              <CustomerProductsPanel referralCode={referralCode?.code} organizationId={organizationId} showImportedTab />
            </div>
          )}

          {activeTab === "commissions" && (
            <div className="space-y-6">
              <div className="panel rounded-3xl p-6 sm:p-8">
                <p className="kpi-label">Compensi</p>
                <h3 className="mt-1 text-xl font-black tracking-tight text-white mb-2">Estratto conto provvigioni</h3>
                <p className="text-xs text-surface-300 mb-6">
                  Le tue provvigioni dirette (vendite tue), indirette (vendite della tua rete) e le fee delle tue segnalazioni, con lo stato di ciascuna.
                </p>
                <MyCommissions />
              </div>
            </div>
          )}

          {activeTab === "leads" && (
            <div className="space-y-6">
              <LeadsPanel mode="mine" />
            </div>
          )}

          {activeTab === "plans" && <MyPlansPanel />}

          {activeTab === "simulator" && (
            <div className="space-y-6">
              <CommissionSimulator agentId={me.id} />
            </div>
          )}

          {activeTab === "support" && (
            <div className="space-y-6">
              <WhatsAppSupportPage />
              {SHOW_SUPPORT_TICKETS && (
              <SupportTicketsPanel
                title="Supporto"
                subtitle="Hai bisogno di aiuto dall'amministrazione? Apri un ticket: lo vedrai qui appena ricevi risposta."
              />
              )}
            </div>
          )}

          {activeTab === "profile" && <ProfilePanel email={email} />}

          {activeTab === "documentation" && (
            <div className="space-y-6">
              <DocumentationFeed />
            </div>
          )}

          {activeTab === "wallet" && (
            <div className="space-y-6">
              <WalletPanel />
            </div>
          )}

          {activeTab === "cashback" && (
            <div className="space-y-6">
              <InvoiceRedemptionPanel />
            </div>
          )}
        </div>
      )}
    </AppFrame>
  );
}
