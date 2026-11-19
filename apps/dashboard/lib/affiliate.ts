import { friendlyApiError } from "@/lib/api-error";

/*
 * SOS Affiliate client helpers. Amounts arrive as decimal strings ("12.50")
 * and are only formatted here, never computed: every figure is the server's.
 */

export type Money = string;

export interface AgentBrief {
  id: string;
  name: string;
  code: string;
  status: string;
}

export interface CareerBlock {
  bcp: number;
  bct: number;
  level: number | null;
  bonus: Money;
  next_level: number | null;
  next_total_bc: number | null;
  next_leg_min_bc: number | null;
  next_qualifying_legs: number;
  required_legs: number;
  pay_on: string;
}

export interface AffiliateSummary {
  /** "queued": the server is re-reading this person's own Mamify orders. */
  orders_check?: "queued" | "recent" | "unavailable";
  agent: AgentBrief;
  joined_at: string;
  sponsor: AgentBrief | null;
  direct_count: number;
  network_size: number;
  subscription: {
    status: "ACTIVE" | "SUSPENDED" | "CANCELLED" | "NONE";
    started_at: string | null;
    monthly_fee: Money;
    paid_months: number;
    last_paid_period: string | null;
    current_period_paid: boolean;
    months_to_gift_license: number | null;
  };
  period: string;
  plan_version: { id: string; label: string };
  career: CareerBlock;
  legs: { agent: AgentBrief | null; points: number; descendants: number }[];
  commissions: Record<string, { payable: Money; paid: Money }>;
  licenses: { available: number; reserved: number; resold: number };
  history: { period: string; bcp: number; bct: number; level: number | null; bonus: Money }[];
  rome_event: { period: string; target_bc: number; bct: number; qualified: boolean; open: boolean } | null;
}

export interface PlanConfig {
  subscription: { code: string; name: string; price: Money; bc: number };
  license_products: { code: string; name: string; licenses: number; nominal: Money; price: Money; bc: number }[];
  event_ticket_products: { code: string; name: string; tickets: number; price: Money; bc: number }[];
  license_resale: { price: Money; seller_amount: Money; company_amount: Money; client_mamicash: Money };
  packs: { code: string; name: string; price: Money }[];
  career_levels: { level: number; total_bc: number; leg_min_bc: number; bonus: Money }[];
  required_legs: number;
  career_bonus_pay_day: number;
  bm_rates: string[];
  bd_rates: string[];
  promotions: {
    gift_license_every_paid_months?: number;
    rome_launch_event?: { period: string; target_bc: number };
  };
}

export interface Catalog {
  plan_version: { id: string; label: string; valid_from: string };
  config: PlanConfig;
  /** Purchases happen on Mamify: the in-app shop is replaced by a link. */
  external_shop?: boolean;
}

export interface OperationRow {
  id: string;
  kind: string;
  status: string;
  agent: AgentBrief | null;
  client: { id: string; name: string } | null;
  product_code: string | null;
  quantity: number;
  period: string | null;
  nominal_amount: Money;
  discount_amount: Money;
  paid_amount: Money;
  bc_points: number;
  license_code: string | null;
  payment_method: string | null;
  note: string | null;
  reverses_operation_id: string | null;
  created_at: string;
  confirmed_at: string | null;
}

export interface CommissionRow {
  id: string;
  kind: "BC" | "BD" | "BM" | "RESALE";
  status: string;
  period: string;
  position: number;
  rate: string | null;
  base_amount: Money;
  amount: Money;
  career_level: number | null;
  payable_on: string;
  paid_at: string | null;
  beneficiary: AgentBrief | null;
  operation: { id: string; kind: string; product_code: string | null; seller: AgentBrief | null } | null;
  details: Record<string, unknown>;
  created_at: string;
}

export interface LicenseRow {
  id: string;
  code: string;
  status: "AVAILABLE" | "RESERVED" | "RESOLD" | "VOID";
  origin: "PURCHASE" | "GIFT";
  unit_cost: Money;
  owner: AgentBrief | null;
  client: string | null;
  resold_at: string | null;
  created_at: string;
}

/** A row of the licence register (GET /affiliate/{me,admin}/licenses/page). */
export interface LicenseRegisterRow extends LicenseRow {
  client_detail: { id: string; name: string; vat_number: string | null; email: string | null; phone: string | null; mamify_customer_id: string | null } | null;
  purchase: { product_code: string | null; kind: string | null; at: string | null; via_mamify: boolean };
  assignment: { operation_id: string; status: "PENDING" | "CONFIRMED"; assigned_at: string; paid_at: string | null; via_mamify: boolean; note: string | null } | null;
  seller_amount: Money | null;
  margin: Money | null;
}

export interface LicensesPage {
  total: number;
  page: number;
  page_size: number;
  counts: Record<"AVAILABLE" | "RESERVED" | "RESOLD" | "VOID", number>;
  items: LicenseRegisterRow[];
}

export interface MarginFigures {
  licenses: number;
  available: number;
  reserved: number;
  resold: number;
  cost: Money;
  collected: Money;
  margin: Money;
  potential_margin: Money;
}

export interface MarginGroup extends MarginFigures {
  purchase_operation_id: string;
  origin: "PURCHASE" | "GIFT";
  product_code: string | null;
  purchased_at: string | null;
  via_mamify: boolean;
}

export interface AgentMargins {
  seller_amount: Money;
  resale_price: Money;
  totals: MarginFigures;
  groups: MarginGroup[];
}

export interface AgentMarginRow extends MarginFigures {
  agent: AgentBrief | null;
}

export interface ClientRow {
  id: string;
  company_name: string;
  vat_number: string | null;
  contact_name?: string | null;
  email: string | null;
  phone?: string | null;
  mamicash_balance: Money;
  agent?: { id: string; name: string } | null;
}

/** One node of the tree, parents before children (pre-order). */
export interface TreeRow {
  agent: AgentBrief;
  parent_id: string | null;
  depth: number;
  bcp: number;
  bct: number;
  level: number | null;
  direct_count: number;
  /** Everyone below this person, at any depth. */
  network_size: number;
  /** Legs with points this month. */
  active_legs: number;
  /** Legs already at the minimum of the next level. */
  qualifying_legs: number;
  next_level: number | null;
  joined_at: string;
  subscription_paid: boolean;
  mamify: { id: string; present: boolean; email: string | null; phone: string | null } | null;
}

/** Figures of a whole branch, computed by the server (affiliate/tree.py). */
export interface BranchSummary {
  people: number;
  active: number;
  paid: number;
  missing: number;
  by_depth: { depth: number; people: number }[];
  max_depth: number;
  period: string;
}

/** A person (or the top), the path to them, and one page of their directs. */
export interface TreeBranch {
  root: TreeRow | null;
  path: TreeRow[];
  children: TreeRow[];
  total_children: number;
  offset: number;
  limit: number;
  summary: BranchSummary;
  /** The viewer's own node for a Digital Ambassador, null for the admin. */
  scope: string | null;
}

export interface TreeSearch {
  results: (TreeRow & { path: { id: string; name: string }[] })[];
  total: number;
}

async function call<T>(base: string, path: string, method = "GET", body?: unknown): Promise<T> {
  const res = await fetch(`/api/proxy/${base}${path}`, {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await friendlyApiError(res));
  return res.json();
}

export function affiliateGet<T>(path: string): Promise<T> {
  return call<T>("affiliate", path);
}

export function affiliateSend<T>(path: string, body?: unknown, method = "POST"): Promise<T> {
  return call<T>("affiliate", path, method, body ?? undefined);
}

/** The Mamify connection API (/api/mamify/admin/*). */
export function mamifyGet<T>(path: string): Promise<T> {
  return call<T>("mamify/admin", path);
}

export function mamifySend<T>(path: string, body: unknown = {}, method = "POST"): Promise<T> {
  return call<T>("mamify/admin", path, method, body);
}

const EUR = new Intl.NumberFormat("it-IT", { style: "currency", currency: "EUR" });
const INT = new Intl.NumberFormat("it-IT");

export function eur(value: Money | number | null | undefined): string {
  return EUR.format(Number(value ?? 0));
}

export function bc(value: number | null | undefined): string {
  return `${INT.format(value ?? 0)} BC`;
}

export function num(value: number | null | undefined): string {
  return INT.format(value ?? 0);
}

export function mamicash(value: Money | number | null | undefined): string {
  return `${new Intl.NumberFormat("it-IT", { maximumFractionDigits: 2 }).format(Number(value ?? 0))} MamiCash`;
}

const MONTHS = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"];

export function periodLabel(period: string | null | undefined): string {
  if (!period) return "—";
  const [y, m] = period.split("-").map(Number);
  return `${MONTHS[(m ?? 1) - 1] ?? ""} ${y}`;
}

export function shortDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("it-IT", { day: "2-digit", month: "short", year: "numeric" });
}

export const OPERATION_LABELS: Record<string, string> = {
  SUBSCRIPTION_PAYMENT: "Mensilità Digital Ambassador",
  LICENSE_PURCHASE: "Acquisto licenze",
  EVENT_TICKET_PURCHASE: "Biglietti Evento Roma",
  LICENSE_RESALE: "Rivendita licenza",
  PACK_SALE: "Vendita Pack",
  MAMICASH_TOPUP: "Ricarica MamiCash",
  GIFT_LICENSE: "Licenza in omaggio",
  REVERSAL: "Rettifica",
};

export const OPERATION_STATUS: Record<string, { label: string; tone: "ok" | "warn" | "bad" | "muted" | "info" }> = {
  PENDING: { label: "In attesa di pagamento", tone: "warn" },
  CONFIRMED: { label: "Confermata", tone: "ok" },
  CANCELLED: { label: "Annullata", tone: "muted" },
  REVERSED: { label: "Rettificata", tone: "bad" },
};

export const COMMISSION_LABELS: Record<string, string> = {
  BC: "Bonus Carriera",
  BD: "Bonus Vendita Diretta",
  BM: "Bonus MamiCash",
  RESALE: "Rivendita licenze",
};

export const COMMISSION_STATUS: Record<string, { label: string; tone: "ok" | "warn" | "bad" | "muted" | "info" }> = {
  PAYABLE: { label: "Da pagare", tone: "warn" },
  PAID: { label: "Pagato", tone: "ok" },
  CANCELLED: { label: "Annullato", tone: "muted" },
};

export const LICENSE_STATUS: Record<string, { label: string; tone: "ok" | "warn" | "bad" | "muted" | "info" }> = {
  AVAILABLE: { label: "Disponibile", tone: "ok" },
  RESERVED: { label: "Assegnata · da pagare", tone: "warn" },
  RESOLD: { label: "Rivenduta", tone: "info" },
  VOID: { label: "Annullata", tone: "muted" },
};

export const PAYMENT_METHODS: { value: string; label: string }[] = [
  { value: "BANK_TRANSFER", label: "Bonifico" },
  { value: "CARD", label: "Carta" },
  { value: "CASH", label: "Contanti" },
  { value: "OTHER", label: "Altro" },
];

export function productName(config: PlanConfig | undefined, code: string | null): string {
  if (!code) return "—";
  if (!config) return code;
  if (config.subscription.code === code) return config.subscription.name;
  return (
    config.license_products.find((p) => p.code === code)?.name ??
    config.event_ticket_products.find((p) => p.code === code)?.name ??
    (config.packs.find((p) => p.code === code) ? `Pack ${code}` : code === "LICENSE_RESALE" ? "Licenza" : code)
  );
}
