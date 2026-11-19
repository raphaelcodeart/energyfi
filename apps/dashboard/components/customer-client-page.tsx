"use client";

import { sectionEnabled, useFeatures } from "@/lib/features";
import { ExternalWalletStats } from "@/components/external-wallet-stats";
import { ProfilePanel } from "@/components/profile-panel";
import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter, useSearchParams } from "next/navigation";
import { AccountingPanel } from "@/components/accounting-panel";
import { AppFrame, type NavGroup, type NavItem } from "@/components/app-frame";
import { ContractRequestWizard } from "@/components/contract-request-wizard";
import { ContractRequestsList, type WizardTarget } from "@/components/contract-requests-list";
import { DashboardWalletStats } from "@/components/dashboard-wallet-stats";
import { WelcomeBonusCard } from "@/components/welcome-bonus-card";
import { CustomerOrdersPanel } from "@/components/customer-orders-panel";
import { MamifyOrders } from "@/components/affiliate/mamify-orders";
import { CustomerProductsPanel } from "@/components/customer-products-panel";
import { CustomerPromoterApplicationCard } from "@/components/customer-promoter-application-card";
import { FriendReferralsPanel } from "@/components/friend-referrals-panel";
import { DocumentationFeed } from "@/components/documentation-feed";
import { SupportTicketsPanel } from "@/components/support-tickets-panel";
import { WhatsAppSupportPage } from "@/components/whatsapp-support";
import { SHOW_SUPPORT_TICKETS } from "@/lib/support";
import { WalletPanel } from "@/components/wallet-panel";
import { InvoiceRedemptionPanel } from "@/components/invoice-redemption-panel";
import type { ContractRead, CustomerRead } from "@/lib/types";

/**
 * "Back from Stripe Checkout" banner shared by the "I miei Ordini" and
 * "Riscatta Cashback" tabs (set by the effect reading ?payment=...&tab=...).
 */
function PaymentReturnBanner({
  state, onDismiss, successBody, cancelledBody,
}: {
  state: "success" | "cancelled" | null;
  onDismiss: () => void;
  successBody: string;
  cancelledBody: string;
}) {
  if (state === null) return null;
  const isSuccess = state === "success";
  return (
    <div
      className={`panel pop flex items-start gap-3 p-5 rounded-3xl border text-sm ${
        isSuccess
          ? "border-success-500/30 text-success-300"
          : "border-warn-500/30 text-warn-300"
      }`}
    >
      <svg className="w-5 h-5 shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        {isSuccess ? (
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
        ) : (
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        )}
      </svg>
      <div className="flex-1">
        <p className="text-base font-black tracking-tight">{isSuccess ? "Pagamento completato con successo!" : "Pagamento non completato"}</p>
        <p className={`text-xs mt-0.5 ${isSuccess ? "text-success-400/80" : "text-warn-400/80"}`}>
          {isSuccess ? successBody : cancelledBody}
        </p>
      </div>
      <button
        onClick={onDismiss}
        className={`p-1 rounded-lg cursor-pointer shrink-0 ${isSuccess ? "hover:bg-success-500/10" : "hover:bg-warn-500/10"}`}
      >
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
    </div>
  );
}

async function fetchMyCustomerRecord(): Promise<CustomerRead | null> {
  const res = await fetch("/api/proxy/customers/me");
  if (res.status === 404) return null;
  if (!res.ok) throw new Error("Impossibile caricare la tua anagrafica.");
  return res.json();
}

interface CustomerClientPageProps {
  /**
   * Fetched server-side at page load. Not rendered directly: contracts appear
   * inside their pratiche (contract-requests-list.tsx), which load themselves.
   */
  contracts: ContractRead[];
  email?: string;
  /**
   * Needed for the customer's "Invita un amico" link, which carries ?org= like
   * a promoter's referral link.
   */
  organizationId?: string;
}

const svgProps = { className: "w-5 h-5", fill: "none", viewBox: "0 0 24 24", stroke: "currentColor" } as const;

const NAV_GROUPS: NavGroup[] = [
  {
    key: "services",
    label: "Servizi",
    icon: <svg {...svgProps}><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>,
  },
  {
    key: "money",
    label: "Denaro",
    icon: <svg {...svgProps}><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V6m0 10v2M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>,
  },
  {
    key: "community",
    label: "Community",
    icon: <svg {...svgProps}><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 20h5v-2a4 4 0 00-3-3.87M9 20H4v-2a4 4 0 013-3.87m6-1.13a4 4 0 10-4-4 4 4 0 004 4zm6 0a4 4 0 10-4-4" /></svg>,
  },
  {
    key: "help",
    label: "Aiuto",
    icon: <svg {...svgProps}><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>,
  },
];

// The first four sections fill the phone dock.
const NAV_ITEMS: NavItem[] = [
  {
    key: "sosnet-contracts",
    description: "Accessi rapidi, i tuoi saldi e le tue attività.",
    // The dashboard home (wallet stats, shortcuts, then contracts); "Home" reads
    // clearer on a mobile tab bar than "Dashboard".
    label: "Il mio quadro",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 12l9-9 9 9M5 10v10a1 1 0 001 1h3a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1h3a1 1 0 001-1V10" />
      </svg>
    ),
  },
  {
    key: "contracts",
    group: "services",
    description: "Le tue pratiche luce e gas: attiva, riprendi, paga.",
    label: "I miei contratti",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
      </svg>
    ),
  },
  {
    key: "products",
    group: "services",
    description: "Prodotti dei partner da acquistare con cashback.",
    label: "Negozio",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />
      </svg>
    ),
  },
  {
    key: "orders",
    group: "services",
    description: "I tuoi acquisti, i pagamenti e le spedizioni.",
    label: "I miei ordini",
    notificationTypes: ["ORDER_PAID", "ORDER_SHIPPED"],
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 2l1 4H4a1 1 0 00-1 1v1a1 1 0 001 1h16a1 1 0 001-1V7a1 1 0 00-1-1h-6l1-4M5 9v9a2 2 0 002 2h10a2 2 0 002-2V9M10 13h4" />
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
    key: "accounting",
    group: "money",
    description: "Tutte le transazioni del tuo conto, in ordine.",
    label: "Movimenti contabili",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 7h6m-6 4h6m-6 4h4M5 3h14a2 2 0 012 2v14a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2z" />
      </svg>
    ),
  },
  {
    key: "friend-referrals",
    group: "community",
    description: "Invita amici col tuo link e ricevi premi.",
    label: "Porta un amico",
    notificationTypes: ["FRIEND_REFERRAL_ACTIVATED", "FRIEND_REFERRAL_REWARD_HANDLED"],
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z" />
      </svg>
    ),
  },
  {
    key: "promoter-application",
    group: "community",
    description: "Candidati per diventare promoter SOSNET.",
    label: "Diventa promoter",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 20h5v-2a4 4 0 00-3-3.87M9 20H4v-2a4 4 0 013-3.87m6-8a4 4 0 11-8 0 4 4 0 018 0zm6 3a4 4 0 11-8 0 4 4 0 018 0z" />
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
    description: "Guide, condizioni e novità da consultare.",
    label: "Documentazione",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
      </svg>
    ),
  },
];

/**
 * Home shortcuts to the sections customers return to most, as on the
 * promoter home and admin Panoramica.
 */
/** Sections kept in the code but out of this console for now: "I miei
 * contratti" (pratiche luce e gas of the inherited energy model), "Negozio" and
 * "Invita amici" (its reward counts friends' contracts). Remove a key to show it again. */
const HIDDEN_KEYS = new Set(["contracts", "products", "friend-referrals"]);
const VISIBLE_NAV_ITEMS = NAV_ITEMS.filter((item) => !HIDDEN_KEYS.has(item.key));

/** Key -> rail label: the single source of section names. */
const NAV_LABEL_BY_KEY = new Map(NAV_ITEMS.map((item) => [item.key, item.label]));

/**
 * A shortcut's label, taken from the nav item with the same key so the two
 * never diverge.
 */
function labelForKey(key: string): string {
  return NAV_LABEL_BY_KEY.get(key) ?? key;
}

/** Home shortcuts: labels and icons come from the navigation. */
const HOME_QUICK_LINKS: { key: string; description: string; icon: React.ReactNode }[] = [
  { key: "contracts", description: "Attiva e segui i tuoi contratti" },
  { key: "products", description: "Le offerte e il negozio" },
  { key: "orders", description: "I tuoi acquisti" },
  { key: "accounting", description: "Pagamenti e ricevute" },
  { key: "support", description: "Hai bisogno di aiuto?" },
  { key: "profile", description: "I tuoi dati personali" },
].filter((link) => !HIDDEN_KEYS.has(link.key)).map((link) => ({ ...link, icon: NAV_ITEMS.find((item) => item.key === link.key)?.icon ?? null }));

export function CustomerClientPage({ email, organizationId }: CustomerClientPageProps) {
  const features = useFeatures();
  // "sosnet-contracts" is the customer's home tab.
  const [activeTab, setActiveTab] = useState<"sosnet-contracts" | "contracts" | "products" | "orders" | "support" | "promoter-application" | "friend-referrals" | "documentation" | "profile" | "wallet" | "cashback" | "accounting">("sosnet-contracts");
  // "Attiva nuovo contratto" / "Riprendi" / "Paga": the pratica wizard, opened
  // over the current tab.
  const [wizard, setWizard] = useState<WizardTarget | "new" | null>(null);
  const router = useRouter();
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();
  const [paymentBanner, setPaymentBanner] = useState<"success" | "cancelled" | null>(null);

  // Return from Stripe Checkout (success_url/cancel_url set by "Paga con carta"
  // in customer-orders-panel.tsx or invoice-redemption-panel.tsx): switch tab,
  // show a banner and refetch so the status updates once the webhook lands.
  // The query params are stripped right away so a refresh does not repeat the banner.
  const VALID_TABS = [
    "sosnet-contracts", "activate-contract", "contracts", "products", "orders", "support",
    "promoter-application", "friend-referrals", "documentation", "profile", "wallet", "cashback", "accounting",
  ] as const;

  useEffect(() => {
    const payment = searchParams.get("payment");
    const tab = searchParams.get("tab");
    const isValidTab = (VALID_TABS as readonly string[]).includes(tab ?? "");
    if (!payment && !isValidTab) return;

    // A plain email deep link (?tab=wallet, no ?payment=) only switches tab; a
    // Stripe return (?payment=success|cancelled, with tab=orders|cashback) also
    // shows the banner and refetches.
    // "activate-contract" is still accepted from existing links and emails.
    // Links to a hidden section land on the home.
    if (tab === "activate-contract" || HIDDEN_KEYS.has(tab ?? "")) setActiveTab("sosnet-contracts");
    else if (isValidTab) setActiveTab(tab as typeof activeTab);
    const queryKey =
      tab === "cashback"
        ? ["invoice-redemptions", "mine"]
        : tab === "contracts"
          ? ["contract-requests"]
          : ["customer", "orders"];
    if (payment === "success" || payment === "cancelled") {
      setPaymentBanner(payment);
      queryClient.invalidateQueries({ queryKey });
    }
    router.replace("/customer", { scroll: false });

    if (payment === "success") {
      // The webhook may not have landed when Stripe redirects back; a second
      // refetch a couple of seconds later picks up the PAID/CREDITED status.
      const timer = setTimeout(() => {
        queryClient.invalidateQueries({ queryKey });
      }, 3000);
      return () => clearTimeout(timer);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const { data: myCustomer } = useQuery({
    queryKey: ["customer", "me", "record"],
    queryFn: fetchMyCustomerRecord,
  });

  return (
    <AppFrame
      roleLabel="Console cliente"
      email={email}
      navItems={VISIBLE_NAV_ITEMS}
      navGroups={NAV_GROUPS}
      dockKeys={["sosnet-contracts", "orders", "wallet", "profile"].filter((k) => !HIDDEN_KEYS.has(k))}
      activeKey={activeTab}
      onNavigate={(key) => setActiveTab(key as typeof activeTab)}
      headerTitle="La mia Area Cliente"
      showCart={!HIDDEN_KEYS.has("products")}
      // Not on Contabilità: it has its own heading, and the space goes to the totals.
    >
      {activeTab === "contracts" && !HIDDEN_KEYS.has("contracts") && (
        <div className="space-y-6">
          <PaymentReturnBanner
            state={paymentBanner}
            onDismiss={() => setPaymentBanner(null)}
            successBody="La pratica si aggiorna a “Pagato” appena Stripe conferma, di solito in pochi secondi. Ogni contratto si attiva quando i suoi documenti sono approvati."
            cancelledBody="Nessun addebito. Puoi pagare quando vuoi con il pulsante “Paga” della pratica."
          />
          <div className="panel sheen relative overflow-hidden flex flex-col sm:flex-row sm:items-center justify-between gap-5 p-6 sm:p-7 rounded-3xl">
            <div>
              <p className="kpi-label">Pratiche</p>
              <h3 className="mt-1 text-xl font-black tracking-tight text-white">Le tue pratiche di attivazione</h3>
              <p className="text-xs text-surface-300 mt-1.5 max-w-2xl">
                Una pratica può contenere uno o più contratti, anche di offerte diverse: ognuno è un contratto a sé,
                con il suo pacchetto. Dati, documenti e pagamento li gestisci una volta sola.
              </p>
            </div>
            <button
              onClick={() => setWizard("new")}
              className="pulse-ring shrink-0 inline-flex items-center justify-center gap-2 px-6 py-3.5 rounded-2xl bg-gradient-to-r from-brand-600 to-accent-500 hover:from-brand-500 hover:to-accent-400 text-white text-sm font-bold shadow-lg shadow-brand-500/20 transition cursor-pointer"
            >
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M12 4v16m8-8H4" />
              </svg>
              Attiva nuovo contratto
            </button>
          </div>
          <ContractRequestsList mode="customer" onOpenWizard={(target) => setWizard(target)} />
          <div className="pt-2">
            <p className="kpi-label mb-3">Scopri i pacchetti</p>
            <CustomerProductsPanel visibleCategories={["INTERNAL"]} accountEmail={email} />
          </div>
        </div>
      )}

      {activeTab === "sosnet-contracts" && (
        <div className="space-y-6">
          <div data-tilt className="panel sheen rise relative overflow-hidden rounded-3xl px-7 py-6">
            <p className="kpi-label">Bentornato</p>
            <h2 className="mt-1 text-2xl sm:text-3xl font-black tracking-tight text-gradient truncate max-w-[70vw] sm:max-w-none">{email}</h2>
            <span className="pointer-events-none absolute -right-10 -top-10 h-40 w-40 rounded-full bg-gradient-to-br from-brand-400/40 to-accent-400/10 blur-3xl" />
          </div>

          {features.welcome_bonus && <WelcomeBonusCard />}


          {features.wallet && <DashboardWalletStats />}
              {features.external_wallet && <ExternalWalletStats />}

          <div>
            <p className="kpi-label mb-3">Accesso rapido</p>
            <div className="stagger grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-7 gap-3">
              {HOME_QUICK_LINKS.filter((link) => sectionEnabled(link.key, features)).map((link, i) => (
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
          </div>

          <CustomerPromoterApplicationCard hideWhenActive />
          {/* SOSNET packages open the luce e gas pratica: off with "I miei contratti". */}
          {!HIDDEN_KEYS.has("contracts") && <CustomerProductsPanel visibleCategories={["INTERNAL"]} accountEmail={email} />}
        </div>
      )}

      {activeTab === "products" && !HIDDEN_KEYS.has("products") && (
        <div className="space-y-6">
          <CustomerProductsPanel visibleCategories={["PARTNER", "DROPSHIPPING"]} showImportedTab />
        </div>
      )}

      {activeTab === "orders" && (
        <div className="space-y-6">
          <PaymentReturnBanner
            state={paymentBanner}
            onDismiss={() => setPaymentBanner(null)}
            successBody="L'ordine si aggiorna automaticamente a “Pagato” non appena Stripe conferma -- di solito pochi secondi."
            cancelledBody="Puoi riprovare quando vuoi dal tuo ordine qui sotto."
          />
          <MamifyOrders quiet />
          {/* Shop orders: hidden with the shop (HIDDEN_KEYS "products"). */}
          {!HIDDEN_KEYS.has("products") && <CustomerOrdersPanel />}
        </div>
      )}

      {activeTab === "support" && (
        <div className="space-y-6">
          <WhatsAppSupportPage />
          {SHOW_SUPPORT_TICKETS && (
          <SupportTicketsPanel
            title="Supporto & Assistenza"
            subtitle="Apri un ticket per problemi tecnici, fatturazione o domande sul tuo account: un operatore ti risponderà qui."
          />
          )}
        </div>
      )}

      {activeTab === "friend-referrals" && !HIDDEN_KEYS.has("friend-referrals") && (
        <FriendReferralsPanel organizationId={organizationId} />
      )}

      {activeTab === "promoter-application" && (
        <div className="space-y-6">
          <CustomerPromoterApplicationCard />
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
          <PaymentReturnBanner
            state={paymentBanner}
            onDismiss={() => setPaymentBanner(null)}
            successBody="La richiesta si aggiorna automaticamente ad “Accreditata” non appena Stripe conferma -- di solito pochi secondi."
            cancelledBody="Puoi riprovare quando vuoi dalla tua richiesta qui sotto."
          />
          <InvoiceRedemptionPanel />
        </div>
      )}

      {activeTab === "accounting" && (
        <AccountingPanel onOpenTab={(tab) => setActiveTab(tab as typeof activeTab)} />
      )}
      {wizard && (
        <ContractRequestWizard
          requestId={wizard === "new" ? undefined : wizard.requestId}
          initialStep={wizard === "new" ? undefined : wizard.step}
          customerKind={myCustomer?.kind ?? null}
          accountEmail={email}
          holder={{ firstName: myCustomer?.first_name, lastName: myCustomer?.last_name, pec: myCustomer?.pec }}
          onClose={() => setWizard(null)}
        />
      )}
    </AppFrame>
  );
}
