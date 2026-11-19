// Hand-written mirrors of the Pydantic response schemas in
// apps/api/app/modules/*/schemas.py.

export type ContractRead = {
  id: string;
  customer_id: string;
  supply_point_id: string | null;
  /** Null while a draft pratica point has no package chosen yet. */
  product_version_id: string | null;
  contract_request_id?: string | null;
  status: string;
  notes: string | null;
  created_at: string;
  activated_at: string | null;
  expires_at: string | null;
  product_name: string | null;
  supply_point_label: string | null;
  pod_code?: string | null;
  pdr_code?: string | null;
  /** ELECTRICITY / GAS */
  energy_type?: string | null;
  iban: string | null;
  email: string | null;
  /** Holder as entered in the activation wizard; null on older and
      staff-created contracts. */
  holder_first_name: string | null;
  holder_last_name: string | null;
  pec: string | null;

  // --- Who created it ---
  /** CUSTOMER / PROMOTER / ADMIN. Null on older contracts (see the status
      history). */
  created_by_role: string | null;
  /** Set only when a promoter completed the contract on the customer's
      behalf; null means the customer did it themselves. */
  activated_by_promoter_id: string | null;
  activated_by_promoter_name: string | null;
  /** The promoter who originally brought the customer in (may differ from
      the one who assisted). */
  first_referrer_agent_id: string | null;
  first_referrer_name: string | null;

  // --- Economics frozen at creation ---
  customer_kind: string | null;
  net_amount_cents: number | null;
  /** Percentage points (22.0), not a fraction. 0 for a private customer. */
  vat_rate: number | null;
  vat_amount_cents: number | null;
  gross_amount_cents: number | null;

  // --- Payment ---
  payment_plan: string | null;
  /** Discount for paying in one go (0 otherwise). */
  payment_discount_cents?: number;
  payment_method: string | null;
  paid_at: string | null;
  /** An admin stopped the monthly Stripe charge. */
  billing_stopped_at?: string | null;
  terms_accepted_at: string | null;
  terms_version: string | null;
};

// --- Activation pratica ---------------------------------

/** One pratiche list row. Counts are derived server-side from the contracts. */
export type ContractRequestSummaryRead = {
  id: string;
  /** First 8 characters of the id, upper case. */
  code: string;
  customer_id: string;
  customer_name: string | null;
  customer_kind: string | null;
  /** DRAFT / SUBMITTED / CANCELLED */
  status: string;
  created_at: string;
  submitted_at: string | null;
  updated_at: string | null;
  created_by_role: string | null;
  activated_by_promoter_id: string | null;
  activated_by_promoter_name: string | null;
  holder_name: string | null;
  points_total: number;
  points_by_status: Record<string, number>;
  points_active: number;
  points_to_review: number;
  points_documents_pending: number;
  points_without_package: number;
  points_paid: number;
  points_payable: number;
  total_gross_cents: number;
  payment_plans: string[];
  instalments_failed: number;
  /** The customer announced a bank transfer, not yet confirmed. */
  bank_transfer_pending: boolean;
  bank_transfer_total_cents: number | null;
  bank_transfer_requested_at: string | null;
  payment_proof_uploaded_at: string | null;
  /** What was actually paid for the paid points (discounts taken off). */
  total_paid_cents: number;
};

export type ContractRequestPointRead = ContractRead & {
  /** 1-based place of the POD in the pratica. */
  position: number;
  meter_number: string | null;
  street: string | null;
  city: string | null;
  province: string | null;
  postal_code: string | null;
  product_id: string | null;
  documents_missing: number;
  documents_rejected: number;
  instalments_total: number | null;
  instalments_paid: number;
  instalments_failed: number;
  /** Stripe is still charging this contract every month. */
  billing_active: boolean;
};

export type ContractRequestCheckoutRead = {
  id: string;
  created_at: string;
  payment_plan: string;
  total_cents: number;
  instalment_cents: number;
  contracts: number;
  completed_at: string | null;
  stripe_checkout_session_id: string;
  stripe_subscription_id: string | null;
  outcome: string | null;
};

export type ContractRequestDetailRead = ContractRequestSummaryRead & {
  /** The supply address every POD of the pratica starts from. */
  street: string | null;
  city: string | null;
  province: string | null;
  postal_code: string | null;
  holder_first_name: string | null;
  holder_last_name: string | null;
  email: string | null;
  pec: string | null;
  iban: string | null;
  points: ContractRequestPointRead[];
  /** Staff only. */
  checkouts: ContractRequestCheckoutRead[];
};

export type ContractRequestPaymentOptionRead = {
  key: string;
  label: string;
  description: string;
  instalments: number;
  instalment_cents: number;
  total_cents: number;
  rounding_difference_cents: number;
  available: boolean;
  unavailable_reason: string | null;
  /** Price before the one-go discount, the discount, and the
      SosnetCash this option earns. */
  list_total_cents: number;
  discount_percentage: number;
  discount_cents: number;
  cashback_cents: number;
};

export type ContractRequestPaymentOptionsRead = {
  contract_request_id: string;
  card_available: boolean;
  lines: { contract_id: string; label: string; gross_cents: number }[];
  total_gross_cents: number;
  options: ContractRequestPaymentOptionRead[];
  points_paid: number;
  cashback_total_cents: number;
  /** On an instalment plan: a slice per instalment, or all at the first. */
  cashback_mode: "PER_INSTALMENT" | "UPFRONT";
  /** Paying by bank transfer (single payment, same discount). */
  bank_transfer_available: boolean;
  bank_transfer_pending: boolean;
  bank_transfer_total_cents: number | null;
  bank_transfer_requested_at: string | null;
  payment_proof_uploaded_at: string | null;
  bank_iban: string | null;
  bank_account_holder: string | null;
  bank_transfer_instructions: string | null;
  bank_transfer_reference: string | null;
};

export type ContractStatusHistoryRead = {
  id: string;
  from_status: string | null;
  to_status: string;
  actor_user_id: string;
  actor_name: string;
  reason: string | null;
  notes: string | null;
  created_at: string;
};

export type CommissionMovementRead = {
  id: string;
  beneficiary_kind?: "AGENT" | "COMPANY";
  agent_id: string | null;
  contract_id: string;
  movement_type: string;
  amount_cents: number;
  currency: string;
  status: string;
  effective_date: string;
};

export type NotificationRead = {
  id: string;
  type: string;
  entity_type: string;
  entity_id: string;
  title: string;
  body: string | null;
  is_read: boolean;
  created_at: string;
};

export type CommissionMovementDetailRead = {
  id: string;
  contract_id: string;
  customer_id: string;
  customer_name: string;
  product_name: string;
  value_cents: number;
  beneficiary_kind: "AGENT" | "COMPANY";
  agent_id: string | null;
  agent_name: string;
  agent_promoter_code: string;
  agent_current_role_code: string | null;
  producer_agent_id: string;
  producer_name: string;
  /** Distance from the seller: 0 = seller, 1 = direct sponsor, ... */
  depth_from_producer: number | null;
  /** DIRECT / INDIRECT / PROMOTER_FEE / COMPANY_SHARE / REVERSAL */
  movement_type: string;
  beneficiary_type: string | null;
  role_at_calculation: string | null;
  plan_id: string | null;
  plan_name: string | null;
  plan_version: number | null;
  rule_label: string | null;
  calculation_type: string | null;
  calculation_value: number | null;
  reference_margin_cents: number | null;
  fallback_applied: string | null;
  amount_cents: number;
  explanation: string | null;
  /** PENDING / APPROVED / PAYABLE / PAID / CANCELLED / RETAINED (company) */
  status: string;
  effective_date: string;
  approved_at: string | null;
  paid_date: string | null;
};

export type CommissionLevelTotalsRead = {
  depth: number;
  contracts: number;
  value_cents: number;
  commission_cents: number;
};

export type BranchMemberRead = {
  agent_id: string;
  depth: number;
  display_name: string;
  promoter_code: string;
  status: string;
  rank_code: string | null;
  /** Current commercial role (Networker, Agente, Influencer, ...). */
  role_code?: string | null;
  role_name?: string | null;
  parent_agent_id: string | null;
  /** The account is frozen (unlike `status`, the agent lifecycle). Only admin
      viewers ever see true: for everyone else the server prunes frozen members
      and their subtree. */
  is_frozen?: boolean;
};

export type AgentProfileRead = {
  id: string;
  organization_id: string;
  user_id: string | null;
  display_name: string;
  promoter_code: string;
  status: string;
  photo_url: string | null;
  current_rank_id: string | null;
  rank_code: string | null;
  current_commercial_role_id?: string | null;
  rejection_reason: string | null;
  is_blacklisted: boolean;
  collaboration_accepted_at: string | null;
  /** {key: {version, accepted_at}}: which document versions were accepted.
      May be empty on older sign-ups. */
  collaboration_accepted_documents?: Record<string, { version: string; accepted_at: string }>;
};

export type SimulationStepRead = {
  beneficiary_agent_id: string;
  rank_code: string;
  gross_amount_cents: number;
  movement_type: string;
  explanation: string;
};

export type RankRead = {
  id: string;
  code: string;
  name: string;
  level: number;
  personal_token_cents: number;
};

export type RankEvaluationChangeRead = {
  agent_id: string;
  display_name: string;
  previous_rank_code: string | null;
  new_rank_code: string;
  direction: "PROMOTED" | "DEMOTED";
};

export type CustomerRead = {
  id: string;
  organization_id: string;
  user_id: string | null;
  kind: string;
  fiscal_code: string | null;
  vat_number: string | null;
  email: string;
  phone: string | null;
  pec: string | null;
  photo_url: string | null;
  display_name: string;
  /** Null for a company/condominium with no person's profile. */
  first_name: string | null;
  last_name: string | null;
  created_at: string;
  email_verified: boolean | null;
  privacy_accepted: boolean | null;
  user_status: "ACTIVE" | "FROZEN" | null;
};

export type AddressRead = {
  id: string;
  kind: string;
  street: string;
  city: string;
  province: string;
  postal_code: string;
  country: string;
};

export type SupplyPointRead = {
  id: string;
  label: string | null;
  energy_type: string;
  pod_code: string | null;
  pdr_code: string | null;
  meter_number: string | null;
  supply_address_id: string;
};

export type CustomerDetailRead = CustomerRead & {
  addresses: AddressRead[];
  supply_points: SupplyPointRead[];
  current_promoter_agent_id: string | null;
  current_promoter_name: string | null;
};

export type AgentListItemRead = {
  id: string;
  display_name: string;
  first_name: string | null;
  last_name: string | null;
  promoter_code: string;
  status: string;
  photo_url: string | null;
  current_rank_id: string | null;
  rank_code: string | null;
  commercial_role_id?: string | null;
  role_code?: string | null;
  role_name?: string | null;
  direct_parent_agent_id: string | null;
  joined_at: string;
  rejection_reason: string | null;
  email: string | null;
  is_blacklisted: boolean;
  user_id: string | null;
  collaboration_accepted_at: string | null;
  /** {key: {version, accepted_at}}: which document versions were accepted.
      May be empty on older sign-ups. */
  collaboration_accepted_documents?: Record<string, { version: string; accepted_at: string }>;
  email_verified: boolean;
  privacy_accepted: boolean;
  user_status: "ACTIVE" | "FROZEN" | null;
};

export type RootPromoterCreateResponse = {
  agent_id: string;
  display_name: string;
  promoter_code: string;
  personal_link: string;
  email: string;
  temporary_password: string;
};

export type DocumentationPostRead = {
  id: string;
  title: string;
  body: string | null;
  audience: "CUSTOMER" | "PROMOTER" | "BOTH";
  status: "PUBLISHED" | "ARCHIVED";
  image_url: string | null;
  pdf_url: string | null;
  pdf_filename: string | null;
  video_url: string | null;
  created_at: string;
};

export type ProductVersionRead = {
  id: string;
  version_label: string;
  name: string;
  description: string;
  image_url: string | null;
  base_price_cents: number;
  initial_fee_cents: number;
  recurring_fee_cents: number;
  billing_period: string;
  vat_percentage: number | null;
  contract_duration_months: number | null;
  commission_tokens: Record<string, number>;
  credit_discount_percentage: number;
  cashback_enabled: boolean;
  /** 0-100: share of a paid contract's gross (VAT included) credited as
      SosnetCash. INTERNAL products only; 0 means none. */
  contract_cashback_percentage: number;
  /** One-off bonus to the promoter who originally brought the customer in. */
  first_referrer_bonus_enabled: boolean;
  first_referrer_bonus_cents: number;
  /** NO_CASHBACK / STANDARD / AUTOMATIC_INTERNAL_SERVICE, derived server-side. */
  cashback_mode: string;
  /** Number of periodic fees in one contract (12 for monthly over 12 months)
      and the whole contract's net price, both computed server-side
      (catalog/pricing.py::contract_net_amount_cents). */
  contract_billing_periods: number;
  contract_net_amount_cents: number;
  /** Margin a sale makes available to the network: fixed amount or share of
      the net amount. null = not configured. */
  margin_type?: "FIXED" | "PERCENTAGE" | null;
  margin_amount_cents?: number | null;
  margin_percentage?: string | number | null;
  valid_from: string;
  valid_to: string | null;
  status: string;
};

export type ProductRead = {
  id: string;
  organization_id: string;
  code: string;
  product_type: string;
  energy_type: string | null;
  customer_type: string;
  status: string;
  category: "INTERNAL" | "DROPSHIPPING" | "PARTNER";
  /** Commercial category (Energia, TLC, ...) used by commission plans. */
  commercial_category_id?: string | null;
  /** The company behind the product (CompanyRead). */
  company_id?: string | null;
};

export type ProductWithVersionsRead = ProductRead & {
  versions: ProductVersionRead[];
};

export type ProductCatalogRead = ProductRead & {
  current_version: ProductVersionRead | null;
  /** Shop categories within the product's section (`category`), see
      ShopCategoryRead. Optional: older products may have none. */
  category_ids?: string[];
};

export type ContractTotals = {
  total: number;
  active: number;
  pending_approval: number;
  rejected: number;
  cancelled: number;
  suspended: number;
  expired: number;
};

export type CommissionTotals = {
  accrued_cents: number;
  payable_cents: number;
  paid_cents: number;
  reversed_cents: number;
};

export type DashboardSummary = {
  contracts: ContractTotals;
  commissions: CommissionTotals;
  active_promoters: number;
  active_customers: number;
  period_new_contracts: number;
  period_new_commissions_cents: number;
  generated_at: string;
};

export type AttentionItem = {
  contract_id: string;
  customer_id: string;
  status: string;
  days_in_status: number;
  reason: string;
};

export type RecentActivityItem = {
  id: string;
  action: string;
  entity_type: string;
  entity_id: string;
  reason: string | null;
  created_at: string;
};

export type TimeseriesPoint = {
  period: string;
  value: number;
};

export type PromoterCodeRead = {
  id: string;
  code: string;
  personal_link: string;
  status: string;
  promoter_display_name: string | null;
};

export type BranchAgentSummaryRead = {
  agent_id: string;
  depth: number;
  display_name: string;
  promoter_code: string;
  status: string;
  rank_code: string | null;
  role_code?: string | null;
  role_name?: string | null;
  contracts_total: number;
  contracts_by_status: Record<string, number>;
  contracts_problem: number;
  contracts_in_progress: number;
  contracts_processed: number;
  commission_cents: number;
};

export type BranchSummaryTotals = {
  contracts: number;
  commission_cents: number;
  contracts_by_status: Record<string, number>;
  contracts_closed: number;
  contracts_rejected: number;
  contracts_pending: number;
  contracts_in_progress: number;
  levels_below: number;
  people_total: number;
};

export type BranchSummaryRead = {
  agents: BranchAgentSummaryRead[];
  totals: BranchSummaryTotals;
};

export type RankProgressRead = {
  current_rank_code: string | null;
  current_rank_name: string | null;
  next_rank_code: string | null;
  next_rank_name: string | null;
  is_max_rank: boolean;
  personal_volume_cents: number;
  personal_volume_threshold_cents: number;
  group_volume_cents: number;
  group_volume_threshold_cents: number;
};

export type OrganizationNetworkLevelsRead = {
  people_total: number;
  levels_total: number;
  people_by_level: Record<string, number>;
};

export type BranchContractRead = {
  contract_id: string;
  status: string;
  customer_id: string;
  customer_name: string;
  customer_email: string | null;
  customer_phone: string | null;
  product_name: string;
  value_cents: number;
  supply_point_label: string | null;
  expires_at: string | null;
  producer_agent_id: string;
  producer_name: string;
  commission_cents: number;
  my_commission_cents: number | null;
  is_problem: boolean;
  admin_note: string | null;
};

export type TicketMessageRead = {
  id: string;
  ticket_id: string;
  author_user_id: string;
  author_role: string;
  author_name: string | null;
  body: string;
  created_at: string;
};

export type TicketRead = {
  id: string;
  organization_id: string;
  opened_by_user_id: string;
  opened_by_role: string;
  opened_by_name: string | null;
  subject: string;
  category: string;
  status: string;
  contract_id: string | null;
  created_at: string;
  message_count: number;
  last_message_at: string | null;
};

export type TicketDetailRead = TicketRead & {
  messages: TicketMessageRead[];
};

export type WalletRead = {
  id: string;
  user_id: string;
  address: string;
  balance_cents: number;
  currency: string;
  can_transfer: boolean;
  created_at: string;
};

export type WalletAdminListItemRead = WalletRead & {
  owner_display_name: string;
  owner_email: string;
  owner_roles: string[];
};

export type WalletTransactionRead = {
  id: string;
  from_wallet_id: string | null;
  from_address: string | null;
  from_display_name: string | null;
  to_wallet_id: string | null;
  to_address: string | null;
  to_display_name: string | null;
  amount_cents: number;
  currency: string;
  type: string;
  source: string | null;
  reference_contract_id: string | null;
  reference_invoice_redemption_id: string | null;
  reference_order_id: string | null;
  reference_imported_order_id: string | null;
  /** Marketplace orders (CJ, Shopify, AliExpress API).
      reference_imported_order_id refers to the manually kept AliExpress plugin
      orders. */
  reference_cj_order_id?: string | null;
  reference_shopify_order_id?: string | null;
  reference_aliexpress_order_id?: string | null;
  reverses_transaction_id: string | null;
  note: string | null;
  actor_user_id: string | null;
  created_at: string;
};

export type OrganizationSettingsRead = {
  bank_iban: string | null;
  bank_account_holder: string | null;
  bank_transfer_instructions: string | null;
  /** PER_INSTALMENT (default) / UPFRONT. */
  contract_instalment_cashback_mode: "PER_INSTALMENT" | "UPFRONT" | null;
  /** Discount (%) for paying a contract in one go; null = default (32). */
  contract_full_payment_discount_percentage: number | null;
};

export type PaymentSettingsRead = {
  stripe_publishable_key: string | null;
  stripe_secret_key_configured: boolean;
  stripe_secret_key_last4: string | null;
  stripe_webhook_secret_configured: boolean;
};

export type PartnerRead = {
  id: string;
  name: string;
  logo_url: string | null;
  is_active: boolean;
};

export type OrderRead = {
  id: string;
  customer_user_id: string;
  customer_display_name: string;
  product_version_id: string;
  product_name: string;
  product_image_url: string | null;
  created_by_user_id: string;
  amount_cents: number;
  credit_applied_cents: number;
  residual_amount_cents: number;
  cashback_requested: boolean;
  cashback_surcharge_cents: number;
  cashback_credited_at: string | null;
  status: "AWAITING_PAYMENT" | "PAID" | "CANCELLED";
  payment_method: "BANK_TRANSFER" | "CARD";
  stripe_checkout_session_id: string | null;
  payment_proof_uploaded_at: string | null;
  note: string | null;
  paid_at: string | null;
  cancelled_at: string | null;
  cancellation_reason: string | null;
  created_at: string;
};

export type OrderQuoteRead = {
  product_version_id: string;
  product_name: string;
  amount_cents: number;
  credit_discount_percentage: number;
  max_creditable_cents: number;
  customer_wallet_balance_cents: number;
  bank_transfer_available: boolean;
  card_available: boolean;
  cashback_available: boolean;
  cashback_percentage: number;
};

export type ImportProviderRead = {
  id: string;
  provider_type: string;
  name: string;
  base_url: string | null;
  api_key_configured: boolean;
  api_key_last4: string | null;
  /** AliExpress Dropshipping API. */
  app_key: string | null;
  app_secret_configured: boolean;
  app_secret_hint: string | null;
  connected: boolean;
  account_label: string | null;
  token_expires_at: string | null;
  last_connected_at: string | null;
  enabled: boolean;
  created_at: string;
};

export type ImportedProductAdminRead = {
  id: string;
  provider_id: string;
  provider_name: string;
  external_id: string | null;
  external_url: string | null;
  name: string;
  description: string;
  image_url: string | null;
  price_cents: number;
  credit_discount_percentage: number;
  status: "ACTIVE" | "INACTIVE";
  created_at: string;
  category_ids?: string[];
};

export type ImportedProductRead = {
  id: string;
  name: string;
  description: string;
  image_url: string | null;
  price_cents: number;
  credit_discount_percentage: number;
  /** price_cents is the full (card) price; bank transfer takes this % off. */
  bank_transfer_discount_percentage?: number;
  /** Manually added products behave as AliExpress ones: same categories,
      same product card in the Shop. */
  category_ids?: string[];
};

export type ImportedOrderRead = {
  id: string;
  customer_user_id: string;
  customer_display_name: string;
  imported_product_id: string;
  product_name: string;
  product_image_url: string | null;
  created_by_user_id: string;
  amount_cents: number;
  credit_applied_cents: number;
  residual_amount_cents: number;
  /** Taken off by bank transfer (frozen), and residual minus that discount. */
  bank_transfer_discount_cents?: number;
  amount_due_cents?: number;
  bank_transfer_discount_percentage?: number;
  /** VAT included in the price, frozen on the order as on Marketplace
      orders. Missing on older orders. */
  vat_percentage?: number;
  vat_amount_cents?: number;
  /** INCLUDED on older orders, ADDED on newer ones; the same columns mean
      opposite things in the two modes. */
  vat_mode?: "INCLUDED" | "ADDED";
  status: "AWAITING_PAYMENT" | "PAID" | "CANCELLED";
  payment_method: "BANK_TRANSFER" | "CARD";
  stripe_checkout_session_id: string | null;
  payment_proof_uploaded_at: string | null;
  note: string | null;
  paid_at: string | null;
  cancelled_at: string | null;
  cancellation_reason: string | null;
  created_at: string;
};

export type ImportedOrderQuoteRead = {
  imported_product_id: string;
  product_name: string;
  amount_cents: number;
  /** The catalog price is the taxable base and this is the VAT added on top;
      amount_cents includes both. */
  items_cents?: number;
  vat_cents?: number;
  vat_percentage?: number;
  credit_discount_percentage: number;
  max_creditable_cents: number;
  customer_wallet_balance_cents: number;
  bank_transfer_available: boolean;
  card_available: boolean;
  /** Bank transfer costs less than card. */
  bank_transfer_discount_percentage?: number;
  bank_transfer_amount_cents?: number;
};

export type FinancialMovementRead = {
  id: string;
  /** CONTRACT_PAYMENT: one paid contract instalment. */
  kind: "WALLET" | "ORDER_PAYMENT" | "REDEMPTION_PAYMENT" | "CONTRACT_PAYMENT";
  type: string | null;
  source: string | null;
  payment_method: "BANK_TRANSFER" | "CARD" | null;
  amount_cents: number;
  currency: "SOSNETCASH" | "EUR";
  product_name: string | null;
  order_id: string | null;
  invoice_redemption_id: string | null;
  contract_id?: string | null;
  contract_request_id?: string | null;
  note: string | null;
  customer_user_id: string | null;
  customer_display_name: string | null;
  created_at: string;
};

/** The totals at the top of "Contabilità", computed server-side. */
export type AccountingSummaryRead = {
  spent_total_cents: number;
  spent_card_cents: number;
  spent_bank_transfer_cents: number;
  spent_this_month_cents: number;
  spent_orders_cents: number;
  spent_redemptions_cents: number;
  spent_contracts_cents: number;
  payments_count: number;
  sosnetcash_balance_cents: number;
  sosnetcash_received_cents: number;
  sosnetcash_spent_cents: number;
  cashback_received_cents: number;
  contracts_active: number;
  instalments_paid: number;
  next_instalment_due_date: string | null;
  next_instalment_cents: number | null;
  /** Null unless the account is also a promoter. */
  commissions_total_cents: number | null;
  commissions_to_collect_cents: number | null;
  commissions_paid_cents: number | null;
  commissions_count: number | null;
};

/** The "Contabilità" detail popup: one movement and the order, redemption
    or contract it belongs to. */
export type AccountingDetailRead = {
  ref: string;
  kind: "WALLET" | "ORDER" | "REDEMPTION" | "CONTRACT";
  title: string;
  subtitle: string | null;
  status: string | null;
  status_tone: "success" | "warning" | "danger" | "neutral";
  amount_cents: number | null;
  currency: "EUR" | "SOSNETCASH";
  direction: "in" | "out" | null;
  facts: { label: string; value: string; mono: boolean }[];
  timeline: { label: string; at: string | null; by: string | null; tone: "done" | "pending" | "warning" }[];
  instalments: {
    number: number;
    instalments_total: number;
    due_date: string;
    amount_cents: number;
    status: string;
    paid_at: string | null;
    source: string | null;
    confirmed_by: string | null;
  }[];
  related_refs: string[];
  tab: "orders" | "cashback" | "contracts" | "wallet" | null;
  order_id: string | null;
  invoice_redemption_id: string | null;
  contract_id: string | null;
};

export type InvoiceRedemptionRead = {
  id: string;
  partner_id: string;
  partner_name: string;
  customer_user_id: string;
  customer_display_name: string;
  original_filename: string;
  content_type: string;
  declared_amount_cents: number;
  confirmed_amount_cents: number | null;
  payment_due_cents: number | null;
  payment_reference_code: string | null;
  payment_method: "BANK_TRANSFER" | "CARD" | null;
  stripe_checkout_session_id: string | null;
  payment_proof_uploaded_at: string | null;
  status: "SUBMITTED" | "PAYMENT_PENDING" | "CREDITED" | "REJECTED";
  rejection_reason: string | null;
  created_at: string;
  verified_at: string | null;
  credited_at: string | null;
};


// --- "Invita un amico" ----------------------------------------
// A flat per-account list, separate from the commercial network: no
// hierarchy, no commissions (apps/api/app/modules/friend_referrals/models.py).

export type FriendReferralItemRead = {
  id: string;
  display_name: string;
  /** INVITED / IN_PROGRESS / ACTIVE -- only ACTIVE counts towards the gift. */
  state: string;
  /** PROMOTER_LINK / FRIEND_LINK -- which of the two kinds of link was used. */
  source: string;
  invited_at: string;
};

export type FriendReferralClaimRead = {
  id: string;
  milestone: number;
  status: "REQUESTED" | "FULFILLED" | "REJECTED";
  note: string | null;
  requested_at: string;
  handled_at: string | null;
};

export type FriendReferralSummaryRead = {
  code: string;
  invited_total: number;
  active_total: number;
  reward_every: number;
  /** Gift description, owned by the server (REWARD_DESCRIPTION). */
  reward_description: string;
  missing_for_next_reward: number;
  claimable_milestone: number | null;
  referrals: FriendReferralItemRead[];
  claims: FriendReferralClaimRead[];
};

export type FriendReferralAdminClaimRead = {
  id: string;
  referrer_user_id: string;
  referrer_name: string;
  referrer_email: string | null;
  milestone: number;
  status: "REQUESTED" | "FULFILLED" | "REJECTED";
  note: string | null;
  requested_at: string;
  handled_at: string | null;
};


// --- "Lavora con noi" collaboration agreement -------------
// The legal text is served by the backend as structured blocks, so it has one
// source and changes need no frontend release
// (apps/api/app/modules/network/collaboration_documents.py).

export type CollaborationDocumentBlock =
  | { type: "heading"; text: string }
  | { type: "paragraph"; text: string }
  | { type: "clause"; number: string; text: string }
  | { type: "bullets"; items: string[] }
  | { type: "table"; columns: string[]; rows: string[][]; caption: string | null }
  | { type: "signature"; text: string };

export type CollaborationDocumentRead = {
  key: string;
  /** Sent back on submit so the record stores which text was accepted. */
  version: string;
  title: string;
  subtitle: string;
  acceptance_label: string;
  blocks: CollaborationDocumentBlock[];
};


// --- Contract payment ----------------------------------
// Contracts only (the Shop checkout is separate). Every amount is computed
// server-side from the frozen contract figure; the browser sends only a plan key.

export type ContractPaymentOptionRead = {
  /** FULL / INSTALMENTS_3 / MONTHLY_12 */
  key: string;
  label: string;
  description: string;
  instalments: number;
  instalment_cents: number;
  total_cents: number;
  /** Plan total minus contract amount, from rounding instalments to the
      cent. Always shown. */
  rounding_difference_cents: number;
};

export type ContractPaymentOptionsRead = {
  contract_id: string;
  payable: boolean;
  status: string;
  /** At the payment step without a frozen amount (older contract). Kept
      apart from "not payable" so the message can explain the cause. */
  missing_amount: boolean;
  gross_amount_cents: number | null;
  card_available: boolean;
  options: ContractPaymentOptionRead[];
  /** Set once Stripe confirms the (first) payment, possibly before the
      documents are approved. */
  paid_at: string | null;
  payment_plan: string | null;
  /** Automatic SosnetCash: percentage and total. With instalments it is
      credited per instalment. */
  cashback_percentage: number;
  cashback_total_cents: number;
};


// --- Contract commission and instalment preview ---------------
// Computed server-side (commissions/services/preview.py); the dashboard only
// renders it and returns its checksum on acceptance.

export type CommissionPreviewBeneficiary = {
  key: string;
  rule_id: string | null;
  agent_id: string | null;
  beneficiary_kind: "AGENT" | "COMPANY";
  name: string;
  /** Rule label: Venditore, Sponsor livello 1, Influencer, ... */
  role: string;
  role_code: string | null;
  depth: number | null;
  calculation_type: string;
  calculation_value: string | null;
  movement_type: string;
  movement_label: string;
  total_cents: number;
  fallback_applied: string | null;
  explanation: string;
};

export type SplitPlanSummary = {
  id: string;
  name: string | null;
  version: number;
  status: string;
  valid_from: string | null;
  valid_to: string | null;
  fallback_strategy: string;
  distribution_mode: string;
  accrual_trigger: string;
};

export type CommissionPreviewScheduleRow = {
  number: number;
  due_date: string | null;
  customer_amount_cents: number;
  commission_cents: number;
  per_beneficiary_cents: Record<string, number>;
  release: string;
};

export type CommissionPreviewRead = {
  contract_id: string;
  customer_name: string;
  gross_amount_cents: number;
  beneficiaries: CommissionPreviewBeneficiary[];
  first_referrer_bonus: { agent_id: string; name: string; amount_cents: number; note: string } | null;
  total_commission_cents: number;
  company_share_cents?: number;
  reference_margin_cents?: number | null;
  sale_amount_cents?: number | null;
  sold_at?: string | null;
  seller_role?: string | null;
  plan?: SplitPlanSummary | null;
  /** Non-empty means the preview cannot be accepted: something (margin,
      role, plan) is missing, so payouts are undetermined. */
  blocking_errors?: string[];
  payment: {
    paid: boolean;
    paid_at: string | null;
    plan_key: string | null;
    plan_label: string | null;
    instalments: number | null;
    schedule: CommissionPreviewScheduleRow[];
    last_release_date: string | null;
    scenarios: { plan_key: string; plan_label: string; instalments: number; commission_per_instalment_cents: number }[];
  };
  customer_cashback_cents: number;
  warnings: string[];
  checksum: string;
  /** Only on GET /commission-preview. */
  already_accepted?: boolean;
};

export type ContractInstalmentRead = {
  number: number;
  instalments_total: number;
  due_date: string;
  amount_cents: number;
  /** SCHEDULED / PAID / FAILED */
  status: string;
  paid_at: string | null;
  /** STRIPE_CHECKOUT / STRIPE_INVOICE / ADMIN */
  payment_source: string | null;
  confirmed_by: string | null;
  commission_released_at: string | null;
  commission_pending: boolean;
};

export type ContractCommissionLogRead = {
  contract_id: string;
  status: string;
  payment_plan: string | null;
  accepted_plan: {
    accepted_at: string;
    accepted_by: string | null;
    total_commission_cents: number;
    preview: CommissionPreviewRead;
  } | null;
  instalments: ContractInstalmentRead[];
};

// --- Shop Sosnet Partner (CJ Dropshipping) ---

export type CjSettingsRead = {
  api_key_configured: boolean;
  api_key_hint: string | null;
  connected: boolean;
  token_expires_at: string | null;
  enabled: boolean;
  sandbox: boolean;
  usd_eur_rate: number;
  markup_percentage: number;
  markup_fixed_cents: number;
  price_rounding: "90" | "99" | "NONE";
  shipping_mode: "CUSTOMER_PAYS" | "INCLUDED";
  default_credit_percentage: number;
  destination_country: string;
  auto_forward: boolean;
  last_balance_usd: number | null;
  last_balance_at: string | null;
};

export type CjCatalogItem = {
  pid: string;
  name_en: string;
  sku: string;
  image_url: string | null;
  sell_price_usd: string;
  estimated_price_cents: number | null;
  inventory: number | null;
  category_name: string | null;
  free_shipping: boolean;
  already_imported: boolean;
};

export type CjCatalogPage = {
  page: number;
  total_pages: number;
  total_records: number;
  items: CjCatalogItem[];
};

export type CjProductPreview = {
  pid: string;
  sku: string;
  name_en: string;
  description_text: string;
  category_name: string | null;
  images: string[];
  origin_country: string;
  shipping_estimate_usd: number | null;
  shipping_estimate_cents: number | null;
  shipping_days: string | null;
  shipping_carrier: string | null;
  ships_to_destination: boolean;
  variants: {
    vid: string;
    sku: string;
    label: string;
    image_url: string | null;
    cost_usd: number;
    weight_g: number;
    inventory: number;
    price_cents: number;
  }[];
};

export type CjVariantAdminRead = {
  id: string;
  cj_vid: string;
  cj_sku: string | null;
  label: string;
  image_url: string | null;
  cost_usd: number;
  weight_g: number;
  price_cents: number;
  price_override_cents: number | null;
  effective_price_cents: number;
  inventory: number;
  active: boolean;
  available_on_cj: boolean;
};

export type CjProductAdminRead = {
  id: string;
  cj_pid: string;
  cj_sku: string | null;
  name: string;
  name_en: string | null;
  description: string;
  image_url: string | null;
  images: string[];
  category_name: string | null;
  origin_country: string;
  shipping_estimate_usd: number | null;
  shipping_days: string | null;
  status: "ACTIVE" | "INACTIVE";
  credit_discount_percentage: number;
  markup_percentage: number | null;
  last_synced_at: string | null;
  sync_error: string | null;
  paid_orders: number;
  created_at: string;
  variants: CjVariantAdminRead[];
  category_ids?: string[];
};

/** Rules shared by the three shops of imported products. */
export type ShopSectionKey = "internal" | "partner" | "dropshipping";

export type MarketplaceConfigRead = {
  /** Four shops, including «Fai la Spesa con Sosnet». */
  labels: { aliexpress: string; cj: string; shopify: string; sosnet_market: string };
  /** The Shop's own sections, each renamable and switchable. */
  sections: Record<ShopSectionKey, { label: string; enabled: boolean }>;
  bank_transfer_discount_percentage: number;
  /** VAT rate added on top of the listed price (22% by default). When
      missing, no VAT is shown rather than a wrong one. */
  vat_percentage?: number;
  default_credit_percentage: number;
  max_credit_percentage: number;
};

export type CjProductRead = {
  id: string;
  name: string;
  description: string;
  image_url: string | null;
  images: string[];
  min_price_cents: number;
  max_price_cents: number;
  credit_discount_percentage: number;
  shipping_days: string | null;
  shipping_included: boolean;
  /** Prices are the full (card) ones; bank transfer takes this % off. */
  bank_transfer_discount_percentage: number;
  in_stock: boolean;
  variants: { id: string; label: string; image_url: string | null; price_cents: number; in_stock: boolean }[];
  /** This Marketplace's categories for the product, used by the Shop filter. */
  category_ids?: string[];
};

export type CjQuoteRead = {
  variant_id: string;
  product_name: string;
  variant_label: string;
  quantity: number;
  unit_price_cents: number;
  items_cents: number;
  /** What the customer pays: max(actual AliExpress cost, configured minimum). */
  shipping_cents: number;
  /** VAT added on the goods, already included in amount_cents. */
  vat_cents?: number;
  vat_percentage?: number;
  /** Informational only: our cost, the minimum in force and whether it
      applied. Customers see shipping_cents. */
  supplier_shipping_cents?: number;
  minimum_shipping_cents?: number;
  shipping_is_minimum?: boolean;
  shipping_included: boolean;
  shipping_days: string | null;
  amount_cents: number;
  credit_discount_percentage: number;
  max_creditable_cents: number;
  customer_wallet_balance_cents: number;
  bank_transfer_discount_percentage: number;
  /** amount_cents paid all by bank transfer, discount taken off (no SosnetCash). */
  bank_transfer_amount_cents: number;
  bank_transfer_available: boolean;
  card_available: boolean;
  default_address: { street: string | null; city: string | null; province: string | null; postal_code: string | null };
};

export type CjFulfillmentStatus =
  | "NOT_SENT" | "SENDING" | "SENT" | "PROCESSING" | "SHIPPED" | "DELIVERED" | "ERROR" | "CJ_CANCELLED";

export type CjDeliveryStatus = "RECEIVED" | "PREPARING" | "SHIPPED" | "DELIVERED" | "PROBLEM";

export type CjPaymentStatus = "NOT_REQUIRED" | "PENDING" | "PAYMENT_REQUIRED" | "PAID" | "FAILED";

export type CjCashSummary = {
  orders_to_pay: number;
  orders_payment_required: number;
  required_usd: number;
  required_cents: number;
  balance_usd: number | null;
  balance_at: string | null;
  shortfall_usd: number;
  shortfall_cents: number;
  sandbox: boolean;
  auto_forward: boolean;
};

export type CjOrderRead = {
  id: string;
  customer_user_id: string;
  customer_display_name: string;
  cj_product_id: string;
  cj_variant_id: string;
  product_name: string;
  product_image_url: string | null;
  variant_label: string | null;
  created_by_user_id: string;
  quantity: number;
  unit_price_cents: number;
  shipping_cents: number;
  amount_cents: number;
  credit_applied_cents: number;
  residual_amount_cents: number;
  /** Taken off for paying by bank transfer (0 by card). */
  bank_transfer_discount_cents: number;
  /** Today's bank-transfer discount, for switching an unpaid order to bank transfer. */
  bank_transfer_discount_percentage: number;
  /** What is really paid in euro: residual - bank-transfer discount. */
  amount_due_cents: number;
  /** VAT included in the price, frozen at order creation (taxable base =
      amount - bank-transfer discount; SosnetCash does not reduce it).
      Missing or 0 on older orders: show nothing, never "IVA 0,00 €". */
  vat_percentage?: number;
  vat_amount_cents?: number;
  status: "AWAITING_PAYMENT" | "PAID" | "CANCELLED";
  payment_method: "BANK_TRANSFER" | "CARD";
  stripe_checkout_session_id: string | null;
  payment_proof_uploaded_at: string | null;
  note: string | null;
  paid_at: string | null;
  cancelled_at: string | null;
  cancellation_reason: string | null;
  created_at: string;
  recipient_name: string;
  recipient_phone: string | null;
  address_line1: string;
  address_line2: string | null;
  city: string;
  province: string;
  postal_code: string;
  country_code: string;
  shipping_days: string | null;
  /** Customer-facing shipping state: RECEIVED until the supplier is paid,
      then PREPARING, SHIPPED, DELIVERED. */
  delivery_status: CjDeliveryStatus | null;
  tracking_number: string | null;
  tracking_url: string | null;
  shipped_at: string | null;
  delivered_at: string | null;
  // Admin only
  fulfillment_status?: CjFulfillmentStatus;
  cj_payment_status?: CjPaymentStatus;
  cj_cost_usd?: number;
  cj_cost_is_actual?: boolean;
  cj_cost_cents?: number;
  cj_order_code?: string | null;
  cj_pay_url?: string | null;
  cj_product_amount_usd?: number | null;
  cj_postage_amount_usd?: number | null;
  cj_ioss_amount_usd?: number | null;
  cj_paid_at?: string | null;
  attempt_count?: number;
  last_attempt_at?: string | null;
  next_retry_at?: string | null;
  last_error_kind?: string | null;
  cj_order_id?: string | null;
  cj_order_status?: string | null;
  cj_amount_usd?: number | null;
  sandbox?: boolean;
  logistic_name?: string;
  origin_country?: string;
  unit_cost_usd?: number;
  shipping_cost_usd?: number;
  usd_eur_rate?: number;
  estimated_margin_cents?: number;
  forwarded_at?: string | null;
  forward_error?: string | null;
  last_cj_sync_at?: string | null;
};

// --- Shopify dropshipping ---

/** Same shape as CjProductRead so every Marketplace renders alike. */
export type ShopifyProductRead = CjProductRead;
/** Same fields as CjQuoteRead. */
export type ShopifyQuoteRead = CjQuoteRead;

export type ShopifySettingsRead = {
  shop_domain: string | null;
  /** CLIENT_CREDENTIALS = Dev Dashboard app; TOKEN = legacy shpat_ token. */
  auth_mode: "CLIENT_CREDENTIALS" | "TOKEN" | null;
  client_id: string | null;
  client_secret_configured: boolean;
  client_secret_hint: string | null;
  access_token_configured: boolean;
  access_token_hint: string | null;
  api_version: string;
  enabled: boolean;
  shop_name: string | null;
  shop_currency: string | null;
  currency_rate: number;
  price_basis: "COST" | "PRICE";
  markup_percentage: number;
  markup_fixed_cents: number;
  price_rounding: "90" | "99" | "NONE";
  shipping_mode: "CUSTOMER_PAYS" | "INCLUDED";
  shipping_flat_cents: number;
  shipping_days: string | null;
  default_credit_percentage: number;
  max_credit_percentage: number;
  auto_forward: boolean;
  last_connected_at: string | null;
};

export type ShopifyCatalogVariant = {
  variant_id: string;
  sku: string | null;
  label: string;
  image_url: string | null;
  cost_amount: number | null;
  source_price_amount: number;
  inventory: number | null;
  price_cents: number;
};

export type ShopifyCatalogProduct = {
  product_id: string;
  handle: string | null;
  title: string;
  vendor: string | null;
  status: string | null;
  description_text: string;
  image_url: string | null;
  images: string[];
  variants: ShopifyCatalogVariant[];
  min_price_cents: number | null;
  max_price_cents: number | null;
  currency: string | null;
  already_imported?: boolean;
};

export type ShopifyCatalogPage = { items: ShopifyCatalogProduct[]; next_cursor: string | null };

export type ShopifyProductAdminRead = {
  id: string;
  shopify_product_id: string;
  handle: string | null;
  name: string;
  source_title: string | null;
  vendor: string | null;
  description: string;
  image_url: string | null;
  images: string[];
  status: "ACTIVE" | "INACTIVE";
  credit_discount_percentage: number;
  markup_percentage: number | null;
  last_synced_at: string | null;
  sync_error: string | null;
  paid_orders: number;
  created_at: string;
  variants: {
    id: string;
    shopify_variant_id: string;
    sku: string | null;
    label: string;
    image_url: string | null;
    cost_amount: number | null;
    source_price_amount: number;
    price_cents: number;
    price_override_cents: number | null;
    effective_price_cents: number;
    inventory: number | null;
    active: boolean;
    available_in_store: boolean;
  }[];
  category_ids?: string[];
};

export type ShopifyFulfillmentStatus = "NOT_SENT" | "SENDING" | "SENT" | "SHIPPED" | "DELIVERED" | "ERROR" | "CANCELLED";

export type ShopifyOrderRead = Omit<
  CjOrderRead,
  | "cj_product_id" | "cj_variant_id" | "fulfillment_status" | "cj_payment_status" | "cj_cost_usd" | "cj_cost_is_actual"
  | "cj_cost_cents" | "cj_order_code" | "cj_pay_url" | "cj_product_amount_usd" | "cj_postage_amount_usd"
  | "cj_ioss_amount_usd" | "cj_paid_at" | "cj_order_id" | "cj_order_status" | "cj_amount_usd" | "sandbox"
  | "logistic_name" | "origin_country" | "unit_cost_usd" | "shipping_cost_usd" | "usd_eur_rate" | "last_cj_sync_at"
> & {
  shopify_product_id: string;
  shopify_variant_id: string;
  // Admin only
  fulfillment_status?: ShopifyFulfillmentStatus;
  shopify_order_id?: string | null;
  shopify_order_name?: string | null;
  shopify_draft_order_id?: string | null;
  shopify_fulfillment_status?: string | null;
  tracking_company?: string | null;
  unit_cost_amount?: number | null;
  currency_rate?: number;
  supplier_cost_cents?: number | null;
  last_sync_at?: string | null;
};

// --- AliExpress dropshipping API ---

/** Same shape as CjProductRead so every Marketplace renders alike. */
export type AliexpressProductRead = CjProductRead;
/** Same fields as CjQuoteRead. */
export type AliexpressQuoteRead = CjQuoteRead;

/** Same pricing settings as Shopify. The connection is an
    openservice.aliexpress.com app (App Key + App Secret) plus seller
    authorization, whose expiring token the server renews itself. */
export type AliexpressSettingsRead = {
  app_key: string | null;
  app_secret_configured: boolean;
  app_secret_hint: string | null;
  connected: boolean;
  account_label: string | null;
  token_expires_at: string | null;
  last_connected_at: string | null;
  enabled: boolean;
  /** Ship-to country and AliExpress response currency/language. */
  ship_to_country: string;
  target_currency: string;
  target_language: string;
  currency_rate: number;
  price_basis: "COST" | "PRICE";
  markup_percentage: number;
  markup_fixed_cents: number;
  price_rounding: "90" | "99" | "NONE";
  shipping_mode: "CUSTOMER_PAYS" | "INCLUDED";
  /** Minimum shipping charged to the customer: the actual AliExpress quote
      for the cart, or this amount when the quote is lower. Applies once per
      order, not per item. */
  shipping_minimum_cents: number;
  shipping_days: string | null;
  default_credit_percentage: number;
  max_credit_percentage: number;
  auto_forward: boolean;
};

export type AliexpressCatalogVariant = {
  variant_id: string;
  /** AliExpress' own SKU key, needed when the order is placed. */
  sku_attr: string | null;
  sku: string | null;
  label: string;
  image_url: string | null;
  cost_amount: number | null;
  source_price_amount: number;
  inventory: number | null;
  price_cents: number;
};

export type AliexpressCatalogProduct = {
  product_id: string;
  product_url: string | null;
  title: string;
  vendor: string | null;
  status: string | null;
  description_text: string;
  image_url: string | null;
  images: string[];
  /** Empty on search hits: SKUs come only from the detail call, which the
      import window loads. */
  variants: AliexpressCatalogVariant[];
  min_price_cents: number | null;
  max_price_cents: number | null;
  currency: string | null;
  /** Search hits only. */
  evaluate_rate?: string | null;
  already_imported?: boolean;
};

export type AliexpressCatalogPage = { items: AliexpressCatalogProduct[]; next_cursor: string | null };

export type AliexpressProductAdminRead = {
  id: string;
  aliexpress_product_id: string;
  product_url: string | null;
  name: string;
  source_title: string | null;
  vendor: string | null;
  description: string;
  image_url: string | null;
  images: string[];
  status: "ACTIVE" | "INACTIVE";
  credit_discount_percentage: number;
  markup_percentage: number | null;
  last_synced_at: string | null;
  sync_error: string | null;
  paid_orders: number;
  created_at: string;
  variants: {
    id: string;
    aliexpress_sku_id: string;
    sku_attr: string | null;
    sku: string | null;
    label: string;
    image_url: string | null;
    cost_amount: number | null;
    source_price_amount: number;
    price_cents: number;
    price_override_cents: number | null;
    effective_price_cents: number;
    inventory: number | null;
    active: boolean;
    available_in_store: boolean;
  }[];
  category_ids?: string[];
};

/** Supplier order state, as for Shopify. */
export type AliexpressFulfillmentStatus = ShopifyFulfillmentStatus;

export type AliexpressOrderRead = Omit<
  ShopifyOrderRead,
  | "shopify_product_id" | "shopify_variant_id" | "fulfillment_status" | "shopify_order_id" | "shopify_order_name"
  | "shopify_draft_order_id" | "shopify_fulfillment_status"
> & {
  aliexpress_product_id: string;
  aliexpress_variant_id: string;
  // Admin only
  fulfillment_status?: AliexpressFulfillmentStatus;
  aliexpress_order_id?: string | null;
  aliexpress_order_status?: string | null;
  /** Our own reference, the one AliExpress echoes back on the order. */
  out_order_id?: string | null;
  /** Customer-facing sequential order number shared across shops.
      `order_code` is the same as a string, falling back to the UUID on
      orders older than the sequence. */
  number?: number;
  order_code?: string;
  /** Order lines: what was actually bought. Always at least one; the header
      columns (product_name, quantity, unit_price_cents) describe the first
      line and remain for older orders. */
  items?: AliexpressOrderItemRead[];
  /** Admin: which AliExpress order number maps to which line. One order can
      span several supplier orders (different sellers). */
  item_supplier_orders?: { item_id: string; product_name: string; aliexpress_order_id: string | null }[];
  /** Admin: shipping margin. `null` on orders without a recorded actual cost. */
  supplier_shipping_cents?: number | null;
  minimum_shipping_cents?: number | null;
  shipping_margin_cents?: number | null;
};

export type AliexpressOrderItemRead = {
  id: string;
  product_id: string;
  variant_id: string;
  /** Frozen on the line, so renaming a product does not rewrite past orders. */
  product_name: string;
  variant_label: string | null;
  quantity: number;
  unit_price_cents: number;
  line_total_cents: number;
  /** This line's AliExpress freight; the order's actual cost is their sum.
      `null` on older orders. */
  supplier_shipping_cents: number | null;
  /** Per line: the supplier may split an order into several shipments. */
  tracking_number: string | null;
  tracking_url: string | null;
};

// --- Shop categories ------------------------------------
// Each shop has its own categories, created by admins on that shop's page
// and used by customers to filter. A category belongs to exactly one shop.
export type ShopKey = "internal" | "partner" | "dropshipping" | "aliexpress" | "cj" | "shopify" | "sosnet_market";

export type ShopCategoryRead = {
  id: string;
  shop: ShopKey;
  name: string;
  /** Display order in the customer's category bar. */
  position: number;
  active: boolean;
  /** Number of that shop's products in this category. */
  product_count: number;
};

/** Each product's categories within its shop. */
export type ShopCategoryAssignments = Record<string, string[]>;

// --- Shop cart ---------------------------------
//
// One cart split into one section per shop: the shops have incompatible
// rules (address and shipping vs cashback), so lines from different shops
// never share an order.

export type CartShop = "aliexpress" | "cj" | "shopify" | "sosnet_market" | "catalog";

export type CartLineRead = {
  cart_item_id: string;
  variant_id: string;
  product_name: string;
  variant_label: string | null;
  image_url: string | null;
  quantity: number;
  unit_price_cents: number;
  line_total_cents: number;
  credit_discount_percentage: number;
  /** SosnetCash this line allows: its own percentage of its value, shipping
      share included. The order cap is the sum over lines, not an average. */
  max_creditable_cents?: number;
  /** false when the item can no longer be bought; the line stays visible
      with the reason. */
  available: boolean;
  unavailable_reason: string | null;
};

/** A cart section: the shop's quote figures plus lines and purchasability. */
export type CartSectionRead = Omit<CjQuoteRead, "variant_id" | "product_name" | "variant_label" | "quantity" | "unit_price_cents"> & {
  cart_id: string;
  shop: CartShop;
  items: CartLineRead[];
  /** false if any line can no longer be bought. */
  purchasable: boolean;
  problems: string[];
  /** Legacy keys describing the first line. */
  variant_id: string;
  product_name: string;
  variant_label: string | null;
  quantity: number;
  unit_price_cents: number;
};

export type CartRead = {
  sections: CartSectionRead[];
  item_count: number;
  total_cents: number;
};


// --- «Fai la Spesa con Sosnet» -----------------
//
// Admin-curated catalog with a separate producer record. For customers it
// behaves like the other Marketplaces, so its card reuses CjProductRead.

export type SosnetMarketProducerPublic = {
  name: string;
  description: string;
  website_url: string | null;
  logo_url: string | null;
};

export type SosnetMarketProducerRead = SosnetMarketProducerPublic & {
  id: string;
  vat_number: string | null;
  email: string | null;
  phone: string | null;
  address: string | null;
  active: boolean;
};

/** Customer grid card: CjProductRead plus the producer. */
export type SosnetMarketProductRead = CjProductRead & {
  producer: SosnetMarketProducerPublic | null;
};

/** Admin record: editable variants, cost and producer. */
export type SosnetMarketAdminProductRead = {
  id: string;
  name: string;
  description: string;
  image_url: string | null;
  images: string[];
  status: "ACTIVE" | "INACTIVE";
  credit_discount_percentage: number;
  unit_cost_cents: number | null;
  producer_id: string | null;
  producer: SosnetMarketProducerRead | null;
  variants: {
    id: string; label: string; sku: string | null; image_url: string | null;
    price_cents: number; inventory: number | null; active: boolean; in_stock: boolean;
  }[];
};

export type SosnetMarketSettingsRead = {
  enabled: boolean;
  /** Paid orders are sent to producers automatically. Off by default, since
      it emails real external companies. */
  auto_forward: boolean;
  shipping_mode: "CUSTOMER_PAYS" | "INCLUDED";
  /** A fixed amount, not a minimum: there is no supplier quote to compare. */
  shipping_flat_cents: number;
  shipping_days: string | null;
  ship_to_country: string;
};

/** Same shape as other Marketplace orders, plus the producer frozen on
    each line. */
export type SosnetMarketOrderRead = Omit<
  AliexpressOrderRead,
  "aliexpress_product_id" | "aliexpress_variant_id" | "aliexpress_order_id" | "aliexpress_order_status" | "out_order_id"
> & {
  items_cents: number;
  items?: (AliexpressOrderItemRead & { producer_name: string | null })[];
  /** Admin: status of the dispatch to producers. */
  forwarded_at?: string | null;
  forward_error?: string | null;
  producers?: { name: string }[];
};


// --- Network and Split Plan ---

export type CommercialRoleRead = {
  id: string;
  code: string;
  name: string;
  description: string;
  /** PERCENTAGE / FIXED / MIXED / REFERRAL_FEE / CUSTOM */
  commission_mode: string;
  /** Levels reachable above the seller; null = unlimited. */
  network_depth: number | null;
  allows_delegation: boolean;
  allows_downline: boolean;
  can_close_sales: boolean;
  is_default: boolean;
  is_active: boolean;
  sort_order: number;
};

export type RoleHistoryRow = {
  id: string;
  role_id: string;
  role_code: string;
  role_name: string;
  valid_from: string;
  valid_to: string | null;
  reason: string | null;
};

export type DelegationRead = {
  id: string;
  influencer_agent_id: string;
  influencer_name: string;
  delegate_agent_id: string;
  delegate_name: string;
  valid_from: string;
  valid_to: string | null;
  reason: string | null;
};

export type ProductCategoryRead = {
  id: string;
  code: string;
  name: string;
  requires_supply_point: boolean;
  is_active: boolean;
};

export type SplitRuleInput = {
  sequence?: number | null;
  label?: string | null;
  /** SELLER / UPLINE_LEVEL / ROLE_IN_UPLINE / INFLUENCER / PROMOTER / COMPANY */
  beneficiary_type: string;
  network_level?: number | null;
  required_role_id?: string | null;
  /** PERCENTAGE / FIXED_AMOUNT / MINIMUM_GUARANTEE / REMAINDER */
  calculation_type: string;
  percentage?: string | number | null;
  amount_cents?: number | null;
  min_amount_cents?: number | null;
  max_amount_cents?: number | null;
  fallback_strategy?: string | null;
};

export type SplitRuleRead = SplitRuleInput & { id: string; required_role_code: string | null };

export type PlanValidationRead = {
  ok: boolean;
  errors: string[];
  warnings: string[];
  percentage_total: string | number;
  fixed_total_cents: number;
  has_remainder: boolean;
  reference_margin_cents: number | null;
  distributed_cents: number | null;
  residual_cents: number | null;
};

export type SplitPlanRead = {
  id: string;
  plan_key: string | null;
  name: string | null;
  version: number;
  /** DRAFT / ACTIVE / RETIRED */
  status: string;
  product_id: string | null;
  product_code: string | null;
  category_id: string | null;
  category_name: string | null;
  seller_role_id: string | null;
  seller_role_code: string | null;
  seller_role_name: string | null;
  valid_from: string;
  valid_to: string | null;
  fallback_strategy: string;
  distribution_mode: string;
  accrual_trigger: string;
  notes: string;
  activated_at: string | null;
  retired_at: string | null;
  created_at: string;
  rules: SplitRuleRead[];
  validation: PlanValidationRead | null;
};

export type SimulationRead = {
  product_name: string;
  product_code: string;
  sold_at: string;
  sale_amount_cents: number | null;
  reference_margin_cents: number | null;
  seller_role: string | null;
  plan: SplitPlanSummary | null;
  chain: { agent_id: string; name: string; depth: number; role_code: string | null; status: string | null }[];
  rows: CommissionPreviewBeneficiary[];
  agents_cents: number;
  company_cents: number;
  distributed_cents: number;
  errors: string[];
  warnings: string[];
};

export type SellerSummaryRead = {
  agent_name: string | null;
  direct_cents: number;
  indirect_cents: number;
  promoter_fee_cents: number;
  reversal_cents: number;
  pending_cents: number;
  approved_cents: number;
  paid_cents: number;
  personal_sales: number;
  personal_sales_amount_cents: number;
};

export type ReportBucket = {
  key: string;
  sales?: number;
  revenue_cents?: number;
  margin_cents?: number;
  commission_cents?: number;
  company_cents?: number;
  plan_id?: string | null;
};

export type CommissionReportRead = {
  totals: {
    sales: number;
    revenue_cents: number;
    margin_cents: number;
    commissions_cents: number;
    company_cents: number;
    direct_cents: number;
    indirect_cents: number;
    promoter_fee_cents: number;
    reversal_cents: number;
  };
  by_seller_role: ReportBucket[];
  by_product: ReportBucket[];
  by_level: ReportBucket[];
  by_plan: ReportBucket[];
  by_category: ReportBucket[];
  by_status: ReportBucket[];
  by_beneficiary_role: ReportBucket[];
};

export type LeadRead = {
  id: string;
  promoter_agent_id: string;
  promoter_name: string;
  customer_id: string | null;
  product_id: string | null;
  contact_name: string;
  contact_email: string | null;
  contact_phone: string | null;
  notes: string;
  /** NEW / QUALIFIED / CONVERTED / LOST / EXPIRED */
  status: string;
  assigned_agent_id: string | null;
  assigned_agent_name: string | null;
  converted_contract_id: string | null;
  converted_at: string | null;
  closed_reason: string | null;
  created_at: string;
};

/** GET /network/agents/{id}/card (apps/api/app/modules/network/card.py). */
export type AgentCardRead = {
  agent: {
    id: string;
    display_name: string;
    promoter_code: string;
    status: string;
    joined_at: string;
    photo_url: string | null;
    role_name: string | null;
    role_code: string | null;
    rank_code: string | null;
    rank_name: string | null;
    email: string | null;
    has_login: boolean;
  };
  upline: { agent_id: string; name: string; depth: number; status: string; role_name: string | null }[];
  role_history: { role_name: string; valid_from: string; valid_to: string | null; reason: string | null }[];
  delegations: {
    delegates: AgentCardDelegation[];
    represents: AgentCardDelegation[];
  };
  network: {
    direct: number;
    total: number;
    active: number;
    levels: { depth: number; people: number; active: number }[];
    joined_last_30_days: number;
    joined_last_90_days: number;
  };
  sales: {
    own_total: number;
    own_sold: number;
    own_open: number;
    own_lost: number;
    own_value_cents: number;
    network_sold: number;
    network_value_cents: number;
    by_product: { product: string; contracts: number; value_cents: number }[];
  };
  earnings: {
    total_cents: number;
    last_30_days_cents: number;
    pending_cents: number;
    approved_cents: number;
    payable_cents: number;
    paid_cents: number;
    cancelled_cents: number;
    by_type: { type: string; cents: number }[];
    by_month: { month: string; cents: number }[];
    movements: number;
  };
  plans: {
    plan_id: string | null;
    name: string;
    version: number | null;
    status: string;
    scope: string | null;
    seller_role_name: string | null;
    earned_cents: number;
    contracts: number;
    people: { agent_id: string | null; name: string; level: number | null; via: string | null; earned_cents: number; contracts: number }[];
  }[];
  wallet_cents: number | null;
  leads: { total: number; open: number; converted: number };
};

export type AgentCardDelegation = {
  agent_id: string;
  name: string;
  valid_from: string;
  valid_to: string | null;
  active: boolean;
};

/** GET /products/companies (catalog/schemas.py::CompanyRead). */
export type CompanyRead = {
  id: string;
  name: string;
  description: string;
  logo_url: string | null;
  website_url: string | null;
  max_network_depth: number | null;
  is_active: boolean;
  products: number;
};

/** One row of GET /network/agents/page: the registry row plus its sponsor
    and network figures, computed on the server. */
export type AgentPageItem = AgentListItemRead & {
  parent_name: string | null;
  parent_code: string | null;
  direct_count: number;
  network_size: number;
  mamify_customer_id: string | null;
  contact_email: string | null;
};

export type AgentPageRead = {
  items: AgentPageItem[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
  /** Whole organization: ALL, BLACKLISTED and one entry per status. */
  counts: Record<string, number>;
};

export type AgentLookup = {
  id: string;
  display_name: string;
  promoter_code: string;
  status: string;
  user_id: string | null;
};

/** "Aggiorna rete" of one collaborator's branch, re-read from Mamify. */
export type BranchSyncView = {
  available: boolean;
  mamify_customer_id?: string;
  requested_at?: string | null;
  synced_at?: string | null;
  running?: boolean;
  queued?: boolean;
  result?: {
    created?: number; moved?: number; updated?: number; missing?: number; members?: number;
    calls?: number; skipped?: string; gone?: boolean; message?: string; error_count?: number; unchecked?: number;
  };
};
