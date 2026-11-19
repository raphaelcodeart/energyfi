"use client";

import { useState, type ReactNode } from "react";
import { AdminAffiliatePanel, type AdminAffiliateView } from "@/components/affiliate/admin-panel";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AppFrame, type NavGroup, type NavItem } from "@/components/app-frame";
import { AdminOverviewPanel } from "@/components/admin-overview-panel";
import { AdminCustomersPanel } from "@/components/admin-customers-panel";
import { MamifyCustomersPanel, MamifyOrdersPanel } from "@/components/sales/mamify-sales";
import { AdminPromotersPanel } from "@/components/admin-promoters-panel";
import { AdminProductsPanel } from "@/components/admin-products-panel";
import { AdminCompaniesPanel } from "@/components/admin-companies-panel";
import { AdminFeaturesCard } from "@/components/admin-features-card";
import { AdminNetworkPanel } from "@/components/admin-network-panel";
import { AdminContractRequestsPanel } from "@/components/admin-contract-requests-panel";
import { AdminCreateContractPanel } from "@/components/admin-create-contract-panel";
import { PraticheForCustomersPanel } from "@/components/pratiche-for-customers-panel";
import { ContractDocumentsPanel } from "@/components/contract-documents-panel";
import { ContractDossierActions } from "@/components/contract-dossier-actions";
import { AdminTicketsPanel } from "@/components/admin-tickets-panel";
import { AdminCommissionsPanel } from "@/components/admin-commissions-panel";
import { AdminSplitPlansPanel } from "@/components/admin-split-plans-panel";
import { AdminCommercialPanel } from "@/components/admin-commercial-panel";
import { AdminCommissionReportsPanel } from "@/components/admin-commission-reports-panel";
import { CommissionSimulator } from "@/components/commission-simulator";
import { LeadsPanel } from "@/components/leads-panel";
import { AdminWalletsPanel } from "@/components/admin-wallets-panel";
import { AdminPartnersPanel } from "@/components/admin-partners-panel";
import { AdminFriendReferralClaimsPanel } from "@/components/admin-friend-referral-claims-panel";
import { AdminInvoiceRedemptionsPanel } from "@/components/admin-invoice-redemptions-panel";
import { AdminOrdersPanel } from "@/components/admin-orders-panel";
import { AdminCjPanel } from "@/components/admin-cj-panel";
import { AdminShopifyPanel } from "@/components/admin-shopify-panel";
import { MarketplaceRulesCard, ShopSectionsCard } from "@/components/marketplace-rules-card";
import { AdminAliexpressPanel } from "@/components/admin-aliexpress-panel";
import { AdminSosnetMarketPanel } from "@/components/admin-sosnet-market-panel";
import { AdminAccountingPanel } from "@/components/admin-accounting-panel";
import { Pagination, usePagination } from "@/components/pagination";
import { Chip, Figure, IdTag, Identity, KpiTile, RowActions, type ChipTone } from "@/components/ui/data-cells";
import { AdminDocumentationPanel } from "@/components/admin-documentation-panel";
import { AdminOrganizationSettingsPanel } from "@/components/admin-organization-settings-panel";
import { CommissionPreviewView } from "@/components/contract-commission-preview";
import { ContractCommissionsModal } from "@/components/contract-commissions-modal";
import { ContractStatusHistoryModal } from "@/components/contract-status-history-modal";
import { friendlyApiError } from "@/lib/api-error";
import { downloadCsv } from "@/lib/csv-export";
import { formatEuroCents as euro } from "@/lib/product-audience";
import type { CommissionPreviewRead, ContractRead, CustomerRead } from "@/lib/types";

async function fetchCustomersForLookup(): Promise<CustomerRead[]> {
  const res = await fetch("/api/proxy/customers");
  if (!res.ok) throw new Error("Impossibile caricare i clienti.");
  return res.json();
}

interface AdminClientPageProps {
  initialContracts: ContractRead[];
  email?: string;
  organizationId?: string;
  /**
   * UI convenience only: hides the Stripe settings from users who could not
   * call them. The organization.manage_payments permission (SUPER_ADMIN only)
   * is enforced server-side.
   */
  isSuperAdmin?: boolean;
}

const STATUS_LABELS: Record<string, string> = {
  DRAFT: "Bozza",
  SUBMITTED: "Inviata",
  DOCUMENTS_PENDING: "Documenti mancanti",
  UNDER_REVIEW: "In revisione",
  APPROVED: "Approvata",
  PAYMENT_PENDING: "In attesa di pagamento",
  PAID: "Pagata",
  ACTIVATION_PENDING: "In attivazione",
  ACTIVE: "Attiva",
  SUSPENDED: "Sospesa",
  CANCELLED: "Cessata",
  EXPIRED: "Scaduta",
  RENEWED: "Rinnovata",
  REJECTED: "Respinta",
};

// Mirrors apps/api/app/modules/contracts/state_machine.py::ALLOWED_TRANSITIONS
// so the dropdown only offers transitions the backend accepts.
// Mirrors contracts/router.py::_ACTIVATION_PATH_TARGETS: moving a never-active
// contract into one of these can activate it, which pays commissions, so the
// server requires the commission preview to be accepted first.
const ACTIVATION_PATH_TARGETS = new Set(["APPROVED", "PAYMENT_PENDING", "PAID", "ACTIVATION_PENDING", "ACTIVE"]);

const CONTRACT_ALLOWED_TRANSITIONS: Record<string, string[]> = {
  DRAFT: ["SUBMITTED", "REJECTED", "CANCELLED"],
  SUBMITTED: ["DOCUMENTS_PENDING", "UNDER_REVIEW", "REJECTED"],
  DOCUMENTS_PENDING: ["UNDER_REVIEW", "REJECTED"],
  UNDER_REVIEW: ["APPROVED", "REJECTED", "DOCUMENTS_PENDING"],
  APPROVED: ["PAYMENT_PENDING", "REJECTED"],
  PAYMENT_PENDING: ["PAID", "REJECTED"],
  PAID: ["ACTIVATION_PENDING"],
  ACTIVATION_PENDING: ["ACTIVE"],
  ACTIVE: ["SUSPENDED", "CANCELLED", "EXPIRED", "RENEWED"],
  SUSPENDED: ["ACTIVE", "CANCELLED"],
  REJECTED: [],
  CANCELLED: [],
  EXPIRED: ["RENEWED", "CANCELLED"],
  RENEWED: ["SUSPENDED", "CANCELLED", "EXPIRED", "RENEWED"],
};

// Virtual combined filters matching the Panoramica KPI cards
// (reports/service.py PENDING_APPROVAL_STATUSES; "Respinti / cessati" =
// REJECTED + CANCELLED), so a KPI click shows exactly the rows it counted.
const PENDING_APPROVAL_STATUSES = new Set([
  "DRAFT", "SUBMITTED", "DOCUMENTS_PENDING", "UNDER_REVIEW", "APPROVED", "PAYMENT_PENDING", "PAID", "ACTIVATION_PENDING",
]);
const REJECTED_CANCELLED_STATUSES = new Set(["REJECTED", "CANCELLED"]);

function contractMatchesStatusFilter(status: string, filter: string): boolean {
  if (filter === "PENDING_APPROVAL") return PENDING_APPROVAL_STATUSES.has(status);
  if (filter === "REJECTED_CANCELLED") return REJECTED_CANCELLED_STATUSES.has(status);
  return status === filter;
}

const svgProps = { className: "w-5 h-5", fill: "none", viewBox: "0 0 24 24", stroke: "currentColor" } as const;

const NAV_GROUPS: NavGroup[] = [
  {
    key: "sos",
    label: "SOS Affiliate",
    icon: <svg {...svgProps}><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 3v4M3 5h4M6 17v4m-2-2h4m5-16l2.286 6.857L21 12l-5.714 2.143L13 21l-2.286-6.857L5 12l5.714-2.143L13 3z" /></svg>,
  },
  {
    key: "sales",
    label: "Vendite",
    icon: <svg {...svgProps}><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" /></svg>,
  },
  {
    key: "network",
    label: "Rete",
    icon: <svg {...svgProps}><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 5a2 2 0 100-4 2 2 0 000 4zm-7 9a2 2 0 100-4 2 2 0 000 4zm14 0a2 2 0 100-4 2 2 0 000 4zm-7 9a2 2 0 100-4 2 2 0 000 4zM12 5v4m0 0l-5.5 3M12 9l5.5 3M12 19v-4m0 0l-5.5-3M12 15l5.5-3" /></svg>,
  },
  {
    key: "money",
    label: "Denaro",
    icon: <svg {...svgProps}><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V6m0 10v2M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>,
  },
  {
    key: "shop",
    label: "Shop",
    icon: <svg {...svgProps}><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 11V7a4 4 0 00-8 0v4M5 9h14l1 12H4L5 9z" /></svg>,
  },
  {
    key: "system",
    label: "Sistema",
    icon: <svg {...svgProps}><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" /></svg>,
  },
];

// SOS Affiliate administration (components/affiliate/admin-panel.tsx), first
// because the plan is what this console runs.
const SOS_ITEMS: NavItem[] = [
  { key: "sos-overview", label: "Panoramica SOS", description: "Rete, punti del mese, qualificati, pagamenti da confermare e compensi dovuti.",
    icon: <svg {...svgProps}><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 13h4v8H3v-8zm7-9h4v17h-4V4zm7 5h4v12h-4V9z" /></svg> },
  { key: "sos-tree", group: "sos", label: "Albero della rete", description: "Tutta la rete Mamify ramo per ramo, con volumi, livelli e gambe di ogni persona.",
    icon: <svg {...svgProps}><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 5a2 2 0 100-4 2 2 0 000 4zm-7 9a2 2 0 100-4 2 2 0 000 4zm14 0a2 2 0 100-4 2 2 0 000 4zm-7 9a2 2 0 100-4 2 2 0 000 4zM12 5v4m0 0l-5.5 3M12 9l5.5 3M12 19v-4m0 0l-5.5-3M12 15l5.5-3" /></svg> },
  { key: "sos-operations", group: "sos", label: "Operazioni e pagamenti", description: "Conferma i pagamenti ricevuti, annulla o rettifica le operazioni.",
    icon: <svg {...svgProps}><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" /></svg> },
  { key: "sos-affiliates", group: "sos", label: "Digital Ambassador", description: "Ogni affiliato con BCP, gambe, BCT, livello e abbonamento.",
    icon: <svg {...svgProps}><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 20h5v-2a4 4 0 00-3-3.87M9 20H4v-2a4 4 0 013-3.87m6-1.13a4 4 0 10-4-4 4 4 0 004 4zm6 0a4 4 0 10-4-4" /></svg> },
  { key: "sos-commissions", group: "sos", label: "Compensi BC · BD · BM", description: "Bonus maturati, separati per tipo, e pagamenti agli affiliati.",
    icon: <svg {...svgProps}><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V6m0 10v2M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg> },
  { key: "sos-periods", group: "sos", label: "Chiusure mensili", description: "Volumi e livelli congelati mese per mese, e chiusura del Bonus Carriera.",
    icon: <svg {...svgProps}><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" /></svg> },
  { key: "sos-registry", group: "sos", label: "Licenze e imprese", description: "Ogni licenza dall'acquisto alla rivendita e le imprese clienti.",
    icon: <svg {...svgProps}><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" /></svg> },
  { key: "sos-plan", group: "sos", label: "Piano compensi", description: "Livelli, aliquote, prodotti e promozioni in vigore, con le versioni.",
    icon: <svg {...svgProps}><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg> },
  { key: "sos-mamify", group: "sos", label: "Collegamento Mamify", description: "Chiave API, copia della rete, abbinamento prodotti, ordini ricevuti e accrediti sui portafogli.",
    icon: <svg {...svgProps}><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" /></svg> },
];

/** Sections of the inherited energy/contracts model, kept in the code but
 * out of the SOS Affiliate console. */
// Hidden for now (2026-11-05): the luce e gas contracts and everything built
// on them (Clienti with supply points, Premi invito), and the whole Shop group.
const HIDDEN_KEYS = new Set([
  "overview", "requests", "list", "create", "products", "companies", "commercial", "split-plans", "simulator", "leads", "commission-reports", "commissions",
  "customers", "friend-referral-claims",
  "partners", "orders", "partner-shop", "shopify-products", "sosnet-market", "imported-products",
]);

const LEGACY_NAV_ITEMS: NavItem[] = [
  {
    key: "overview",
    description: "Il polso dell'azienda in tempo reale: vendite, rete, compensi.",
    label: "Quadro generale",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 13h4v8H3v-8zm7-9h4v17h-4V4zm7 5h4v12h-4V9z" />
      </svg>
    ),
  },
  {
    // Pratiche first: a customer's points are filled in and paid together, but
    // each is still reviewed as its own contract.
    key: "requests",
    group: "sales",
    description: "Pratiche aperte dai clienti e dalla rete, da seguire fino alla firma.",
    label: "Richieste in corso",
    notificationTypes: ["CONTRACT_CREATED", "CONTRACT_PAID_BEFORE_APPROVAL", "CONTRACT_INSTALMENT_FAILED"],
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
      </svg>
    ),
  },
  {
    key: "list",
    group: "sales",
    description: "Tutti i contratti, filtrabili per stato, anno e cliente.",
    label: "Archivio contratti",
    notificationTypes: ["CONTRACT_CREATED"],
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 17V7m0 10a2 2 0 01-2 2H5a2 2 0 01-2-2V7a2 2 0 012-2h2a2 2 0 012 2m0 10a2 2 0 002 2h2a2 2 0 002-2M9 7a2 2 0 012-2h2a2 2 0 012 2m0 10V7m0 10a2 2 0 002 2h2a2 2 0 002-2V7a2 2 0 00-2-2h-2a2 2 0 00-2 2" />
      </svg>
    ),
  },
  {
    key: "create",
    group: "sales",
    description: "Nuova pratica per un cliente nuovo o già presente.",
    label: "Apri un contratto",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
      </svg>
    ),
  },
  {
    key: "sales-orders",
    group: "sales",
    description: "Ordini SOS letti da Mamify: chi ha comprato cosa, pagati, in attesa, da abbinare.",
    label: "Ordini",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 3h2l.4 2M7 13h10l4-8H5.4M7 13L5.4 5M7 13l-2.293 2.293c-.63.63-.184 1.707.707 1.707H17m0 0a2 2 0 100 4 2 2 0 000-4zm-8 2a2 2 0 11-4 0 2 2 0 014 0z" />
      </svg>
    ),
  },
  {
    key: "customers",
    group: "sales",
    description: "Anagrafiche, punti di fornitura e storico di ogni cliente.",
    label: "Clienti",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
      </svg>
    ),
  },
  {
    key: "promoters",
    group: "network",
    description: "Chi fa parte della rete, con ruolo, stato e sponsor.",
    label: "Collaboratori",
    notificationTypes: ["PROMOTER_APPROVAL_REQUESTED"],
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 20h5v-2a4 4 0 00-3-3.87M9 20H4v-2a4 4 0 013-3.87m6-1.13a4 4 0 10-4-4 4 4 0 004 4zm6 0a4 4 0 10-4-4" />
      </svg>
    ),
  },
  {
    key: "companies",
    group: "shop",
    description: "Le aziende dietro ai prodotti, con i livelli di rete che raggiungono.",
    label: "Aziende",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
      </svg>
    ),
  },
  {
    key: "products",
    group: "shop",
    description: "Offerte, listini e margini del catalogo.",
    label: "Catalogo e negozi",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />
      </svg>
    ),
  },
  {
    key: "network",
    group: "network",
    description: "L'albero della rete, ramo per ramo.",
    label: "Albero della rete",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 3H5a2 2 0 00-2 2v4m6-6h10a2 2 0 012 2v4M9 3v18m0 0H5a2 2 0 01-2-2v-4m6 6h10a2 2 0 002-2v-4m0-6h-6m6 0v6m0-6l-8 8" />
      </svg>
    ),
  },
  {
    key: "tickets",
    group: "system",
    description: "Richieste di assistenza di clienti e rete.",
    label: "Assistenza",
    notificationTypes: ["TICKET_CREATED"],
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
      </svg>
    ),
  },
  {
    key: "commercial",
    group: "network",
    description: "Ruoli commerciali, deleghe e categorie di prodotto.",
    label: "Ruoli e deleghe",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H5a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2V8a2 2 0 00-2-2h-5m-4 0V5a2 2 0 114 0v1m-4 0a2 2 0 104 0m-5 8a2 2 0 100-4 2 2 0 000 4zm0 0c1.306 0 2.417.835 2.83 2M9 14a3.001 3.001 0 00-2.83 2M15 11h3m-3 4h2" />
      </svg>
    ),
  },
  {
    key: "split-plans",
    group: "network",
    description: "Come si divide il margine di ogni vendita.",
    label: "Split Plan",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 3.055A9.001 9.001 0 1020.945 13H11V3.055z" />
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20.488 9H15V3.512A9.025 9.025 0 0120.488 9z" />
      </svg>
    ),
  },
  {
    key: "simulator",
    group: "network",
    description: "Prova una vendita e guarda chi guadagna cosa.",
    label: "Simula commissione",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 7h6m0 10v-3m-3 3h.01M9 17h.01M9 14h.01M12 14h.01M15 11h.01M12 11h.01M9 11h.01M7 21h10a2 2 0 002-2V5a2 2 0 00-2-2H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
      </svg>
    ),
  },
  {
    key: "leads",
    group: "sales",
    description: "Contatti portati dai promoter, da qualificare e chiudere.",
    label: "Segnalazioni",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5.882V19.24a1.76 1.76 0 01-3.417.592l-2.147-6.15M18 13a3 3 0 100-6M5.436 13.683A4.001 4.001 0 017 6h1.832c4.1 0 7.625-1.234 9.168-3v14c-1.543-1.766-5.067-3-9.168-3H7a3.988 3.988 0 01-1.564-.317z" />
      </svg>
    ),
  },
  {
    key: "commission-reports",
    group: "money",
    description: "Andamento dei compensi per persona, prodotto e periodo.",
    label: "Report provvigioni",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
      </svg>
    ),
  },
  {
    key: "commissions",
    group: "money",
    description: "Ogni movimento: da approvare, pagabile, pagato.",
    label: "Compensi",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V6m0 10v2M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    ),
  },
  {
    key: "wallets",
    group: "money",
    description: "Saldi e movimenti dei portafogli.",
    label: "Portafogli",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a2 2 0 00-2-2H7a2 2 0 00-2 2m16 0v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6m16 0V9a2 2 0 00-2-2H5a2 2 0 00-2 2v3m16 0h-4a1 1 0 00-1 1v0a1 1 0 001 1h4" />
      </svg>
    ),
  },
  {
    key: "partners",
    group: "shop",
    description: "Aziende partner e forniture.",
    label: "Partner e forniture",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 20h5v-2a4 4 0 00-3-3.87M9 20H4v-2a4 4 0 013-3.87m6-1.13a4 4 0 10-4-4 4 4 0 004 4zm6 0a4 4 0 10-4-4" />
      </svg>
    ),
  },
  {
    key: "friend-referral-claims",
    group: "money",
    description: "Premi per gli inviti andati a buon fine.",
    label: "Premi invito",
    notificationTypes: ["FRIEND_REFERRAL_REWARD_REQUESTED"],
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v13m0-13V6a2 2 0 112 2h-2zm0 0V5.5A2.5 2.5 0 109.5 8H12zM5 12h14M5 12a2 2 0 110-4h14a2 2 0 110 4M5 12v7a2 2 0 002 2h10a2 2 0 002-2v-7" />
      </svg>
    ),
  },
  {
    key: "invoice-redemptions",
    group: "money",
    description: "Richieste di riscatto delle fatture da confermare.",
    label: "Riscatti Fatture",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 14l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    ),
  },
  {
    key: "orders",
    group: "shop",
    description: "Acquisti dei clienti da tutti i negozi.",
    label: "Ordini",
    notificationTypes: ["IMPORTED_ORDER_CREATED"],
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16.5 7.5h-9v9h9v-9zM3 6a3 3 0 013-3h12a3 3 0 013 3v12a3 3 0 01-3 3H6a3 3 0 01-3-3V6z" />
      </svg>
    ),
  },
  {
    key: "partner-shop",
    group: "shop",
    description: "Catalogo e ordini del fornitore CJ.",
    label: "Shop CJ",
    notificationTypes: ["CJ_ORDER_PAID", "CJ_ORDER_FAILED", "CJ_ORDER_CREATED", "CJ_PAYMENT_REQUIRED"],
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />
      </svg>
    ),
  },
  {
    key: "shopify-products",
    group: "shop",
    description: "Catalogo e ordini dal negozio Shopify collegato.",
    label: "Shop Shopify",
    notificationTypes: ["SHOPIFY_ORDER_CREATED", "SHOPIFY_ORDER_PAID", "SHOPIFY_ORDER_FAILED"],
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 11V7a4 4 0 00-8 0v4M5 9h14l1 12H4L5 9z" />
      </svg>
    ),
  },
  {
    // Marketplace 4, "Fai la Spesa con Sosnet", listed first because it is the
    // only catalog we maintain ourselves; the other three are supplier-fed.
    key: "sosnet-market",
    group: "shop",
    description: "Il negozio gestito direttamente da SOSNET.",
    label: "Fai la Spesa con Sosnet",
    notificationTypes: ["SOSNET_MARKET_ORDER_CREATED", "SOSNET_MARKET_ORDER_PAID"],
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 3h2l.4 2M7 13h10l3-8H5.4M7 13L5.4 5M7 13l-2 5h13" />
        <circle cx="9" cy="20" r="1" />
        <circle cx="17" cy="20" r="1" />
      </svg>
    ),
  },
  {
    // Supplier-fed shops, named by source. Customers see CJ as "Marketplace 1",
    // Shopify as "Marketplace 2", AliExpress as "Marketplace 3".
    key: "imported-products",
    group: "shop",
    description: "Catalogo e ordini da AliExpress.",
    label: "Shop AliExpress",
    notificationTypes: ["ALIEXPRESS_ORDER_CREATED", "ALIEXPRESS_ORDER_PAID", "ALIEXPRESS_ORDER_FAILED"],
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4h1.5l1.5 9h9l1.5-6H6M9 20a1 1 0 100-2 1 1 0 000 2zm8 0a1 1 0 100-2 1 1 0 000 2z" />
      </svg>
    ),
  },
  {
    key: "accounting",
    group: "money",
    description: "Entrate, uscite e documenti contabili.",
    label: "Contabilità",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 7h6m-6 4h6m-6 4h4M5 3h14a2 2 0 012 2v14a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2z" />
      </svg>
    ),
  },
  {
    key: "documentation",
    group: "system",
    description: "Guide, moduli e documenti condivisi.",
    label: "Documentazione",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
      </svg>
    ),
  },
  {
    key: "settings",
    group: "system",
    description: "Dati aziendali, pagamenti e integrazioni.",
    label: "Impostazioni",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
      </svg>
    ),
  },
];

const NAV_ITEMS: NavItem[] = [...SOS_ITEMS, ...LEGACY_NAV_ITEMS.filter((item) => !HIDDEN_KEYS.has(item.key))];

/**
 * "Nuovo Contratto": same flow as the promoter's "Miei Clienti" (new or
 * existing customer, then the pratica wizard; the customer pays later from
 * their own area). The single-contract form stays at the bottom for manual
 * records on an existing supply point.
 */
function AdminNewContractTab({ onCreated }: { onCreated: (contract: ContractRead) => void }) {
  const [advanced, setAdvanced] = useState(false);
  return (
    <div className="space-y-6">
      <PraticheForCustomersPanel mode="admin" />
      <div className="panel rounded-3xl p-5">
        <button
          onClick={() => setAdvanced((v) => !v)}
          aria-expanded={advanced}
          className="group flex w-full cursor-pointer items-center gap-3 text-left"
        >
          <span
            className={`grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-white/10 text-white transition group-hover:bg-white group-hover:text-brand-600 ${advanced ? "rotate-90" : ""}`}
          >
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M9 5l7 7-7 7" />
            </svg>
          </span>
          <span className="min-w-0">
            <span className="kpi-label block">Casi particolari</span>
            <span className="block text-sm font-bold text-white">Modulo avanzato a contratto singolo</span>
          </span>
        </button>
        {advanced && (
          <div className="mt-5">
            <AdminCreateContractPanel onCreated={onCreated} />
          </div>
        )}
      </div>
    </div>
  );
}

export function AdminClientPage({ initialContracts, email, organizationId, isSuperAdmin }: AdminClientPageProps) {
  const [contracts, setContracts] = useState<ContractRead[]>(initialContracts);
  const { data: customersForLookup } = useQuery({
    queryKey: ["admin", "customers"],
    queryFn: fetchCustomersForLookup,
  });
  const customerNameById = new Map((customersForLookup ?? []).map((c) => [c.id, c.display_name]));
  const queryClient = useQueryClient();
  const [openRequestId, setOpenRequestId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<AdminAffiliateView | "overview" | "requests" | "list" | "create" | "customers" | "promoters" | "products" | "companies" | "network" | "tickets" | "commissions" | "commercial" | "split-plans" | "simulator" | "leads" | "commission-reports" | "wallets" | "partners" | "friend-referral-claims" | "invoice-redemptions" | "orders" | "sales-orders" | "imported-products" | "sosnet-market" | "partner-shop" | "shopify-products" | "accounting" | "documentation" | "settings">("sos-overview");
  // Filters set by a Panoramica KPI click, consumed once by the target tab and
  // then cleared.
  const [pendingCustomerActiveOnly, setPendingCustomerActiveOnly] = useState(false);
  const [pendingPromoterStatusFilter, setPendingPromoterStatusFilter] = useState<string | null>(null);
  const [pendingCommissionStatusFilter, setPendingCommissionStatusFilter] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("ALL");
  const [yearFilter, setYearFilter] = useState<string>("ALL");
  // Lazy initializer: Date.now() runs once at mount, keeping render pure.
  const [nowMs] = useState(() => Date.now());

  const [selectedContract, setSelectedContract] = useState<ContractRead | null>(null);
  const [commissionsContractId, setCommissionsContractId] = useState<string | null>(null);
  const [historyContractId, setHistoryContractId] = useState<string | null>(null);
  const [targetStatus, setTargetStatus] = useState("UNDER_REVIEW");
  const [transitionReason, setTransitionReason] = useState("");
  const [transitionNotes, setTransitionNotes] = useState("");
  const [transitionLoading, setTransitionLoading] = useState(false);
  const [transitionError, setTransitionError] = useState<string | null>(null);

  const byStatus = contracts.reduce<Record<string, number>>((acc, c) => {
    acc[c.status] = (acc[c.status] ?? 0) + 1;
    return acc;
  }, {});

  const contractYears = Array.from(
    new Set(contracts.map((c) => new Date(c.created_at).getFullYear()))
  ).sort((a, b) => b - a);

  const filteredContracts = contracts.filter((c) => {
    const matchesSearch =
      (c.product_name ?? "").toLowerCase().includes(searchQuery.toLowerCase()) ||
      (customerNameById.get(c.customer_id) ?? "").toLowerCase().includes(searchQuery.toLowerCase()) ||
      c.id.toLowerCase().includes(searchQuery.toLowerCase()) ||
      c.customer_id.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesStatus = statusFilter === "ALL" || contractMatchesStatusFilter(c.status, statusFilter);
    const matchesYear = yearFilter === "ALL" || new Date(c.created_at).getFullYear().toString() === yearFilter;
    return matchesSearch && matchesStatus && matchesYear;
  });

  const EXPIRY_URGENT_MS = 30 * 24 * 60 * 60 * 1000;
  const expiryColor = (expiresAt: string | null) => {
    if (!expiresAt) return "text-surface-500";
    const delta = new Date(expiresAt).getTime() - nowMs;
    if (delta < 0) return "text-danger-400 font-semibold";
    if (delta < EXPIRY_URGENT_MS) return "text-warn-400 font-semibold";
    return "text-white";
  };

  const handleOpenTransition = (contract: ContractRead) => {
    setSelectedContract(contract);
    setTransitionReason("");
    setTransitionNotes("");
    setTransitionError(null);
    setPreviewChecked(false);

    // Preselect the first allowed forward transition rather than a rejection.
    const allowed = CONTRACT_ALLOWED_TRANSITIONS[contract.status] ?? [];
    const forwardStep = allowed.find((s) => s !== "REJECTED" && s !== "CANCELLED");
    setTargetStatus(forwardStep ?? allowed[0] ?? "");
  };

  const availableTargets = selectedContract ? CONTRACT_ALLOWED_TRANSITIONS[selectedContract.status] ?? [] : [];

  const needsCommissionPreview = Boolean(
    selectedContract &&
      ACTIVATION_PATH_TARGETS.has(targetStatus) &&
      !selectedContract.activated_at &&
      selectedContract.status !== "SUSPENDED"
  );
  const {
    data: commissionPreview,
    error: commissionPreviewError,
    refetch: refetchCommissionPreview,
  } = useQuery<CommissionPreviewRead>({
    queryKey: ["admin", "commission-preview", selectedContract?.id],
    queryFn: async () => {
      const res = await fetch(`/api/proxy/contracts/${selectedContract!.id}/commission-preview`);
      if (!res.ok) throw new Error(await friendlyApiError(res));
      return res.json();
    },
    enabled: needsCommissionPreview,
    // Always fetch a fresh preview; a stale one would be refused by the server.
    staleTime: 0,
    gcTime: 0,
  });
  const [previewChecked, setPreviewChecked] = useState(false);
  const mustAcceptPreview = needsCommissionPreview && !commissionPreview?.already_accepted;

  const handleExecuteTransition = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedContract) return;

    setTransitionLoading(true);
    setTransitionError(null);

    try {
      const res = await fetch(`/api/proxy/contracts/${selectedContract.id}/transition`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          to_status: targetStatus,
          reason: transitionReason || null,
          notes: transitionNotes || null,
          accept_commission_preview_checksum: mustAcceptPreview ? commissionPreview?.checksum ?? null : null,
        }),
      });

      if (res.status === 409) {
        // Figures changed while the form was open: show the new ones and require
        // another review before accepting.
        setPreviewChecked(false);
        await refetchCommissionPreview();
      }
      if (!res.ok) {
        throw new Error(await friendlyApiError(res, "Errore durante il cambio di stato del contratto."));
      }

      const updatedContract = await res.json() as ContractRead;

      setContracts(prev => prev.map(c => c.id === updatedContract.id ? updatedContract : c));
      setSelectedContract(null);
      // The same contract may also be shown inside its pratica.
      queryClient.invalidateQueries({ queryKey: ["contract-request"] });
      queryClient.invalidateQueries({ queryKey: ["admin", "contract-requests"] });
    } catch (err: any) {
      setTransitionError(err.message || "Transizione fallita. Controlla le regole della macchina di stato.");
    } finally {
      setTransitionLoading(false);
    }
  };

  // Pages the filtered list; the CSV export uses the full filtered set.
  const contractsPagination = usePagination(filteredContracts);

  const handleContractCreated = (newContract: ContractRead) => {
    setContracts((prev) => [newContract, ...prev]);
    setTimeout(() => setActiveTab("list"), 1500);
  };

  const handleExportContractsCsv = () => {
    downloadCsv(
      `contratti_${new Date().toISOString().slice(0, 10)}`,
      ["ID Contratto", "Cliente", "Prodotto", "Punto di Fornitura", "Stato", "IBAN", "Creato il", "Attivato il", "Scadenza"],
      filteredContracts.map((c) => [
        c.id, customerNameById.get(c.customer_id) ?? c.customer_id, c.product_name ?? "", c.supply_point_label ?? "",
        STATUS_LABELS[c.status] ?? c.status, c.iban ?? "", c.created_at, c.activated_at ?? "", c.expires_at ?? "",
      ])
    );
  };

  const statusTone = (status: string): { tone: ChipTone; live: boolean } => {
    switch (status.toUpperCase()) {
      case "ACTIVE":
      case "PAID":
      case "APPROVED":
      case "RENEWED":
        return { tone: "ok", live: false };
      case "DRAFT":
      case "EXPIRED":
        return { tone: "muted", live: false };
      case "REJECTED":
      case "CANCELLED":
        return { tone: "bad", live: false };
      case "SUSPENDED":
        return { tone: "warn", live: false };
      default:
        return { tone: "warn", live: true };
    }
  };

  const shortDate = (iso: string) =>
    new Date(iso).toLocaleDateString("it-IT", { day: "2-digit", month: "short", year: "numeric" });

  const DAY_MS = 24 * 60 * 60 * 1000;
  const expiryHint = (expiresAt: string) => {
    const days = Math.round((new Date(expiresAt).getTime() - nowMs) / DAY_MS);
    if (days < 0) return `scaduto da ${-days} g`;
    if (days === 0) return "scade oggi";
    return `tra ${days} g`;
  };

  return (
    <>
      <AppFrame
        roleLabel="Console amministratore"
        email={email}
        navItems={NAV_ITEMS}
        navGroups={NAV_GROUPS}
        dockKeys={["sos-overview", "sos-tree", "sos-operations", "sos-commissions"]}
        activeKey={activeTab}
        onNavigate={(key) => setActiveTab(key as typeof activeTab)}
      >
        {activeTab.startsWith("sos-") && (
          <AdminAffiliatePanel view={activeTab as AdminAffiliateView} onNavigate={(key) => setActiveTab(key)} />
        )}
        {activeTab === "overview" && (
          <>
            <AdminOverviewPanel
              onNavigate={(key, filter) => {
                setActiveTab(key as typeof activeTab);
                if (key === "list") setStatusFilter(filter ?? "ALL");
                if (key === "customers") setPendingCustomerActiveOnly(filter === "ACTIVE");
                if (key === "promoters") setPendingPromoterStatusFilter(filter ?? null);
                if (key === "commissions") setPendingCommissionStatusFilter(filter ?? null);
              }}
            />
          </>
        )}

        {activeTab === "requests" && (
          <div className="space-y-6">
            <AdminContractRequestsPanel
              openRequestId={openRequestId}
              onOpenRequest={setOpenRequestId}
              onReview={handleOpenTransition}
              onCommissions={setCommissionsContractId}
              onHistory={setHistoryContractId}
              onContractsChanged={async () => {
                const res = await fetch("/api/proxy/contracts");
                if (res.ok) setContracts(await res.json());
              }}
            />
          </div>
        )}

        {activeTab === "list" && (
          <div className="space-y-6">
            {/* Summary tiles: click to filter the archive */}
            <div className="stagger grid grid-cols-2 gap-4 lg:grid-cols-5">
              {[
                { key: "ALL", label: "Totali", value: contracts.length, hint: "Tutto l'archivio" },
                ...["DRAFT", "SUBMITTED", "UNDER_REVIEW", "ACTIVE"].map((status) => ({
                  key: status,
                  label: STATUS_LABELS[status] || status,
                  value: byStatus[status] ?? 0,
                  hint: contracts.length
                    ? `${Math.round(((byStatus[status] ?? 0) / contracts.length) * 100)}% del totale`
                    : "—",
                })),
              ].map((tile, i) => (
                <div key={tile.key} className="grid" style={{ "--i": i } as React.CSSProperties}>
                  <KpiTile
                    label={tile.label}
                    value={tile.value}
                    hint={tile.hint}
                    active={statusFilter === tile.key}
                    onClick={() => setStatusFilter(tile.key)}
                  />
                </div>
              ))}
            </div>

            {/* Search and filters */}
            <div className="panel rounded-3xl p-4 sm:p-5">
              <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
                <div className="relative flex-1">
                  <svg className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-surface-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                  </svg>
                  <input
                    type="text"
                    placeholder="Cerca intestatario, prodotto o codice contratto..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="w-full rounded-2xl field py-2.5 pl-11 pr-4 text-sm"
                  />
                </div>

                <div className="flex flex-wrap items-center gap-2">
                  <label className="flex items-center gap-2">
                    <span className="kpi-label shrink-0">Situazione</span>
                    <select
                      value={statusFilter}
                      onChange={(e) => setStatusFilter(e.target.value)}
                      className="w-44 rounded-2xl field px-3 py-2.5 text-xs"
                    >
                      <option value="ALL">Tutti</option>
                      <option value="PENDING_APPROVAL">In attesa di approvazione</option>
                      <option value="REJECTED_CANCELLED">Respinti o cessati</option>
                      {Object.entries(STATUS_LABELS).map(([code, label]) => (
                        <option key={code} value={code}>{label}</option>
                      ))}
                    </select>
                  </label>

                  <label className="flex items-center gap-2">
                    <span className="kpi-label shrink-0">Anno</span>
                    <select
                      value={yearFilter}
                      onChange={(e) => setYearFilter(e.target.value)}
                      className="w-36 rounded-2xl field px-3 py-2.5 text-xs"
                    >
                      <option value="ALL">Storico completo</option>
                      {contractYears.map((year) => (
                        <option key={year} value={year.toString()}>{year}</option>
                      ))}
                    </select>
                  </label>

                  <button onClick={handleExportContractsCsv} className="act">
                    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                    </svg>
                    Esporta CSV
                  </button>
                </div>
              </div>
            </div>

            {/* Contracts archive */}
            <div className="panel rounded-3xl p-4 sm:p-6">
              <div className="mb-2 flex flex-wrap items-end justify-between gap-3">
                <div>
                  <p className="kpi-label">Archivio</p>
                  <h3 className="mt-1 text-xl font-black tracking-tight text-white">Contratti</h3>
                </div>
                <span className="text-xs font-semibold text-surface-300">
                  {filteredContracts.length} di {contracts.length}
                </span>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr>
                      <th className="px-4 py-3">Intestatario</th>
                      <th className="px-4 py-3">Pratica e provenienza</th>
                      <th className="px-4 py-3">Situazione</th>
                      <th className="px-4 py-3">Scade</th>
                      <th className="px-4 py-3 text-right">Valore</th>
                      <th className="px-4 py-3"><span className="sr-only">Azioni</span></th>
                    </tr>
                  </thead>
                  <tbody>
                    {contractsPagination.pageItems.map((c) => {
                      const customerName = customerNameById.get(c.customer_id) ?? "Cliente sconosciuto";
                      const { tone, live } = statusTone(c.status);
                      return (
                        <tr key={c.id} className="text-surface-300">
                          <td className="px-4 py-3">
                            <Identity
                              name={customerName}
                              detail={
                                <>
                                  {c.product_name ?? "Prodotto"}
                                  {c.supply_point_label ? ` · ${c.supply_point_label}` : ""}
                                </>
                              }
                            >
                              <div className="mt-1">
                                <IdTag id={c.customer_id} prefix="CL-" />
                              </div>
                            </Identity>
                          </td>
                          <td className="px-4 py-3">
                            <div className="flex flex-wrap items-center gap-1.5">
                              <span title={`Contratto ${c.id}`}>
                                <IdTag id={c.id} />
                              </span>
                              {c.supply_point_id && (
                                <span title={`Punto di fornitura: ${c.supply_point_label ?? c.supply_point_id}`}>
                                  <IdTag id={c.supply_point_id} prefix="PDF-" />
                                </span>
                              )}
                              {c.contract_request_id && (
                                <button
                                  onClick={() => { setOpenRequestId(c.contract_request_id!); setActiveTab("requests"); }}
                                  title={`Apri pratica ${c.contract_request_id}`}
                                  className="cursor-pointer rounded-lg px-1.5 py-0.5 text-[10.5px] font-extrabold text-accent-300 transition hover:bg-white/10 hover:text-white"
                                >
                                  Pratica #{c.contract_request_id.slice(0, 8).toUpperCase()} →
                                </button>
                              )}
                            </div>
                            {/* Self sign-up vs. filled in by a promoter: activated_by_promoter_id is set
                               only in the latter case, never inferred from who earns the commission. */}
                            <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-surface-400">
                              {c.activated_by_promoter_id ? (
                                <>
                                  <Chip tone="info">Compilato dal promoter</Chip>
                                  <span className="text-surface-200">{c.activated_by_promoter_name ?? "—"}</span>
                                </>
                              ) : (
                                <Chip tone="muted">
                                  {c.created_by_role === "ADMIN"
                                    ? "Creato da amministrazione"
                                    : c.created_by_role === "CUSTOMER"
                                      ? "Sottoscritto dal cliente"
                                      : "—"}
                                </Chip>
                              )}
                              {c.first_referrer_name && <span>Invitato da {c.first_referrer_name}</span>}
                            </div>
                          </td>
                          <td className="px-4 py-3">
                            <div className="flex flex-col items-start gap-1.5">
                              <button
                                onClick={() => setHistoryContractId(c.id)}
                                title="Vedi storico stati"
                                className="cursor-pointer transition hover:brightness-125"
                              >
                                <Chip tone={tone} live={live}>{STATUS_LABELS[c.status] ?? c.status}</Chip>
                              </button>
                              {/* Paid before approval: approving the documents activates the contract immediately. */}
                              {c.paid_at && ["SUBMITTED", "DOCUMENTS_PENDING", "UNDER_REVIEW", "APPROVED", "PAYMENT_PENDING"].includes(c.status) && (
                                <span title={`Pagato il ${new Date(c.paid_at).toLocaleDateString("it-IT")}: si attiva all'approvazione dei documenti`}>
                                  <Chip tone="ok">Pagato</Chip>
                                </span>
                              )}
                            </div>
                          </td>
                          <td className="px-4 py-3 whitespace-nowrap">
                            {c.expires_at ? (
                              <>
                                <div className={`text-[13px] ${expiryColor(c.expires_at)}`}>{shortDate(c.expires_at)}</div>
                                <div className="text-[10.5px] text-surface-400">{expiryHint(c.expires_at)}</div>
                              </>
                            ) : (
                              <span className="text-surface-500">—</span>
                            )}
                          </td>
                          <td className="px-4 py-3">
                            {/* Frozen at creation, never recomputed from the current product (see contracts/models.py). */}
                            {c.gross_amount_cents != null ? (
                              <div className="flex justify-end">
                                <Figure
                                  value={euro(c.gross_amount_cents)}
                                  detail={
                                    <>
                                      {euro(c.net_amount_cents ?? 0)} netto
                                      {c.vat_amount_cents ? ` + ${euro(c.vat_amount_cents)} IVA ${c.vat_rate}%` : " · IVA n/a"}
                                    </>
                                  }
                                />
                              </div>
                            ) : (
                              <div className="text-right text-surface-500">—</div>
                            )}
                          </td>
                          <td className="px-4 py-3">
                            <RowActions>
                              <button onClick={() => setCommissionsContractId(c.id)} className="act">
                                Provvigioni
                              </button>
                              <button onClick={() => handleOpenTransition(c)} className="act act-primary">
                                Recensisci
                              </button>
                            </RowActions>
                          </td>
                        </tr>
                      );
                    })}
                    {filteredContracts.length === 0 && (
                      <tr>
                        <td colSpan={6} className="px-4 py-12">
                          <div className="flex flex-col items-center gap-3 text-center">
                            <span className="grid h-12 w-12 place-items-center rounded-2xl bg-white/10 text-white">
                              <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                              </svg>
                            </span>
                            <p className="text-sm text-surface-300">Nessun contratto corrisponde ai filtri impostati.</p>
                          </div>
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
              <div className="pt-3">
                <Pagination {...contractsPagination} label="contratti" />
              </div>
            </div>
          </div>
        )}

        {activeTab === "create" && (
          <div className="space-y-6">
            <AdminNewContractTab onCreated={handleContractCreated} />
          </div>
        )}

        {activeTab === "sales-orders" && <MamifyOrdersPanel />}
        {activeTab === "customers" && (
          <CustomersView legacy={<AdminCustomersPanel initialActiveOnly={pendingCustomerActiveOnly} isSuperAdmin={isSuperAdmin} />} />
        )}
        {activeTab === "promoters" && (
          <div className="space-y-6">
            <AdminPromotersPanel initialStatusFilter={pendingPromoterStatusFilter ?? undefined} isSuperAdmin={isSuperAdmin} />
          </div>
        )}
        {activeTab === "companies" && <AdminCompaniesPanel />}

        {activeTab === "products" && (
          <div className="space-y-6">
            <ShopSectionsCard />
            <AdminProductsPanel />
          </div>
        )}
        {activeTab === "network" && (
          <div className="space-y-6">
            <AdminNetworkPanel />
          </div>
        )}
        {activeTab === "tickets" && (
          <div className="space-y-6">
            <AdminTicketsPanel />
          </div>
        )}
        {activeTab === "commissions" && (
          <div className="space-y-6">
            <AdminCommissionsPanel initialStatusFilter={pendingCommissionStatusFilter ?? undefined} />
          </div>
        )}
        {activeTab === "commercial" && <AdminCommercialPanel />}
        {activeTab === "split-plans" && <AdminSplitPlansPanel />}
        {activeTab === "simulator" && (
          <div className="panel rounded-3xl p-6 space-y-3">
            <p className="kpi-label">Laboratorio</p>
            <h3 className="text-xl font-black tracking-tight text-white">Simula commissione</h3>
            <p className="text-xs text-surface-300">
              Stesso motore delle vendite reali: rete, ruolo e piano letti alla data scelta. Non scrive niente.
            </p>
            <CommissionSimulator adminMode />
          </div>
        )}
        {activeTab === "leads" && <LeadsPanel mode="admin" />}
        {activeTab === "commission-reports" && <AdminCommissionReportsPanel />}
        {activeTab === "wallets" && (
          <div className="space-y-6">
            <AdminWalletsPanel isSuperAdmin={isSuperAdmin} />
          </div>
        )}
        {activeTab === "partners" && (
          <div className="space-y-6">
            <AdminPartnersPanel />
          </div>
        )}
        {activeTab === "friend-referral-claims" && (
          <div className="space-y-6">
            <AdminFriendReferralClaimsPanel />
          </div>
        )}
        {activeTab === "invoice-redemptions" && (
          <div className="space-y-6">
            <AdminInvoiceRedemptionsPanel />
          </div>
        )}
        {activeTab === "orders" && (
          <div className="space-y-6">
            <AdminOrdersPanel />
          </div>
        )}
        {activeTab === "sosnet-market" && (
          <div className="space-y-6">
            <MarketplaceRulesCard highlight="sosnet_market" />
            <AdminSosnetMarketPanel />
          </div>
        )}
        {activeTab === "imported-products" && (
          <div className="space-y-6">
            <MarketplaceRulesCard highlight="aliexpress" />
            <AdminAliexpressPanel />
          </div>
        )}
        {activeTab === "partner-shop" && (
          <div className="space-y-6">
            <MarketplaceRulesCard highlight="cj" />
            <AdminCjPanel />
          </div>
        )}
        {activeTab === "shopify-products" && (
          <div className="space-y-6">
            <MarketplaceRulesCard highlight="shopify" />
            <AdminShopifyPanel />
          </div>
        )}
        {activeTab === "accounting" && (
          <div className="space-y-6">
            <AdminAccountingPanel />
          </div>
        )}
        {activeTab === "documentation" && (
          <div className="space-y-6">
            <AdminDocumentationPanel />
          </div>
        )}
        {activeTab === "settings" && (
          <div className="space-y-6">
            {/* Organization-wide switches: organization.manage, i.e. the super admin. */}
            {isSuperAdmin && <AdminFeaturesCard />}
            <AdminOrganizationSettingsPanel isSuperAdmin={isSuperAdmin} organizationId={organizationId} />
          </div>
        )}
      </AppFrame>

      {/* Transition Modal / Drawer Overlay */}
      {selectedContract && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-fade-in">
          <div className={`w-full ${needsCommissionPreview ? "max-w-3xl" : "max-w-lg"} max-h-[85vh] overflow-y-auto panel rounded-3xl p-6 border-white/10 bg-surface-950 pop`}>
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-xl font-black tracking-tight text-white">Recensisci / Transiziona Stato</h3>
              <button
                onClick={() => setSelectedContract(null)}
                className="p-1 hover:bg-white/5 rounded-lg text-surface-400 hover:text-white transition cursor-pointer"
              >
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <div className="p-3 mb-4 rounded-xl bg-white/5 border border-white/5 text-xs text-surface-400 space-y-1">
              <p>Cliente: <span className="font-semibold text-white">{customerNameById.get(selectedContract.customer_id) ?? "Cliente sconosciuto"}</span></p>
              <p>ID Contratto: <span className="font-mono text-white text-[10px]">{selectedContract.id}</span></p>
              <p>Email contratto: <span className="font-semibold text-white">{selectedContract.email ?? "Non specificata"}</span></p>
              <p>Stato Attuale: <span className="font-bold text-brand-400">{STATUS_LABELS[selectedContract.status] || selectedContract.status}</span></p>
            </div>

            <div className="mb-5">
              <p className="text-xs font-semibold text-surface-300 uppercase mb-2">Documenti Contrattuali</p>
              <ContractDocumentsPanel contractId={selectedContract.id} isStaff />
            </div>

            <div className="mb-5">
              <p className="text-xs font-semibold text-surface-300 uppercase mb-2">
                Fascicolo Completo
              </p>
              <ContractDossierActions contractId={selectedContract.id} />
            </div>

            {availableTargets.length === 0 ? (
              <div className="p-4 rounded-xl bg-white/5 border border-white/5 text-sm text-surface-400 text-center">
                Questo contratto ha raggiunto uno stato finale ({STATUS_LABELS[selectedContract.status] ?? selectedContract.status}) e non può essere transizionato ulteriormente.
                <div className="flex justify-center mt-4">
                  <button
                    type="button"
                    onClick={() => setSelectedContract(null)}
                    className="px-4 py-2 rounded-xl bg-white/5 hover:bg-white/10 text-xs font-semibold text-surface-300 border border-white/5 transition cursor-pointer"
                  >
                    Chiudi
                  </button>
                </div>
              </div>
            ) : (
            <form onSubmit={handleExecuteTransition} className="space-y-4">
              <div className="space-y-1">
                <label className="text-xs font-semibold text-surface-300 block">Seleziona Stato di Destinazione</label>
                <select
                  value={targetStatus}
                  onChange={(e) => setTargetStatus(e.target.value)}
                  className="w-full rounded-xl field px-3 py-2.5 text-sm bg-surface-900 focus:border-brand-500"
                >
                  {availableTargets.map((code) => (
                    <option key={code} value={code} className="bg-surface-950">{STATUS_LABELS[code] ?? code} ({code})</option>
                  ))}
                </select>
                <p className="text-[10px] text-surface-500 mt-1">
                  Solo le transizioni valide da &quot;{STATUS_LABELS[selectedContract.status] ?? selectedContract.status}&quot; sono elencate qui.
                </p>
              </div>

              {needsCommissionPreview && (
                <div className="space-y-3 p-4 rounded-2xl border border-brand-500/25 bg-surface-900/40">
                  <p className="text-sm font-bold text-white">Anteprima provvigioni</p>
                  {commissionPreviewError ? (
                    <p className="text-xs text-danger-400">{(commissionPreviewError as Error).message}</p>
                  ) : !commissionPreview ? (
                    <div className="h-24 rounded-xl bg-white/5 animate-pulse" />
                  ) : commissionPreview.already_accepted ? (
                    <p className="text-xs text-success-400">
                      Anteprima già accettata per questo contratto: la trovi nel registro, pulsante “Provvigioni”.
                    </p>
                  ) : (
                    <>
                      <CommissionPreviewView preview={commissionPreview} />
                      <label className="flex items-start gap-2 pt-2 border-t border-white/10 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={previewChecked}
                          onChange={(e) => setPreviewChecked(e.target.checked)}
                          className="mt-0.5 accent-brand-500"
                        />
                        <span className="text-xs text-surface-300">
                          Ho controllato l&apos;anteprima e accetto che le provvigioni partano come indicato.
                          Resterà salvata nel registro del contratto.
                        </span>
                      </label>
                    </>
                  )}
                </div>
              )}

              <div className="space-y-1">
                <label className="text-xs font-semibold text-surface-300 block">Motivazione</label>
                <input
                  type="text"
                  required
                  placeholder="Es: Documenti validati con successo"
                  value={transitionReason}
                  onChange={(e) => setTransitionReason(e.target.value)}
                  className="w-full rounded-xl field px-3 py-2 text-sm focus:border-brand-500"
                />
              </div>

              <div className="space-y-1">
                <label className="text-xs font-semibold text-surface-300 block">Note aggiuntive (opzionale)</label>
                <textarea
                  rows={3}
                  placeholder="Dettagli interni o appunti..."
                  value={transitionNotes}
                  onChange={(e) => setTransitionNotes(e.target.value)}
                  className="w-full rounded-xl field px-3 py-2 text-sm focus:border-brand-500 resize-none"
                />
              </div>

              {transitionError && (
                <div className="p-3 rounded-lg bg-danger-500/10 border border-danger-500/20 text-danger-400 text-xs">
                  {transitionError}
                </div>
              )}

              <div className="flex justify-end gap-3 mt-4">
                <button
                  type="button"
                  onClick={() => setSelectedContract(null)}
                  className="px-4 py-2 rounded-xl bg-white/5 hover:bg-white/10 text-xs font-semibold text-surface-300 border border-white/5 transition cursor-pointer"
                >
                  Annulla
                </button>
                <button
                  type="submit"
                  disabled={transitionLoading || (mustAcceptPreview && (!commissionPreview || !previewChecked))}
                  className="px-4 py-2 rounded-xl bg-brand-600 hover:bg-brand-500 text-xs font-semibold text-white transition cursor-pointer disabled:opacity-50"
                >
                  {transitionLoading ? "Salvataggio..." : mustAcceptPreview ? "Accetta anteprima e salva" : "Salva Stato"}
                </button>
              </div>
            </form>
            )}
          </div>
        </div>
      )}

      {commissionsContractId && (
        <ContractCommissionsModal
          contractId={commissionsContractId}
          onClose={() => setCommissionsContractId(null)}
        />
      )}

      {historyContractId && (
        <ContractStatusHistoryModal
          contractId={historyContractId}
          onClose={() => setHistoryContractId(null)}
        />
      )}
    </>
  );
}


/** Vendite → Clienti: the Mamify customers first (where SOS sales come
    from); the customer records of the contracts module stay one click away. */
function CustomersView({ legacy }: { legacy: ReactNode }) {
  const [view, setView] = useState<"mamify" | "records">("mamify");
  return (
    <div className="space-y-5">
      <div className="subnav">
        <button type="button" className="subnav-pill" data-active={view === "mamify" || undefined} onClick={() => setView("mamify")}>Clienti Mamify</button>
        <button type="button" className="subnav-pill" data-active={view === "records" || undefined} onClick={() => setView("records")}>Anagrafiche contratti</button>
      </div>
      {view === "mamify" ? <MamifyCustomersPanel /> : <div className="space-y-6">{legacy}</div>}
    </div>
  );
}
