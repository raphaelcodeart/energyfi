--
-- PostgreSQL database dump
--

\restrict nP9nauzuXkEhaNdBYHFJBb4ICzhzXGpjBtlFWLhnw5Cj4K0jk37cdZbQBM7afyM

-- Dumped from database version 16.15
-- Dumped by pg_dump version 16.15

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: btree_gist; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS btree_gist WITH SCHEMA public;


--
-- Name: EXTENSION btree_gist; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION btree_gist IS 'support for indexing common datatypes in GiST';


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: alembic_version; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.alembic_version (
    version_num character varying(32) NOT NULL
);


--
-- Name: sn_account_roles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_account_roles (
    user_id uuid NOT NULL,
    organization_id uuid NOT NULL,
    role_id uuid NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: sn_accounts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_accounts (
    organization_id uuid NOT NULL,
    email character varying(255) NOT NULL,
    password_hash character varying(255) NOT NULL,
    status character varying(32) NOT NULL,
    email_verified_at timestamp with time zone,
    failed_login_attempts integer NOT NULL,
    locked_until timestamp with time zone,
    privacy_accepted_at timestamp with time zone,
    fiscal_code character varying(16),
    residence_street character varying(255),
    residence_city character varying(100),
    residence_province character varying(2),
    residence_postal_code character varying(10),
    residence_country character varying(2) DEFAULT 'IT'::character varying NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: sn_activity_log; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_activity_log (
    organization_id uuid NOT NULL,
    actor_user_id uuid,
    action character varying(128) NOT NULL,
    entity_type character varying(64) NOT NULL,
    entity_id character varying(64) NOT NULL,
    previous_value jsonb,
    new_value jsonb,
    reason character varying(500),
    ip_address character varying(64),
    user_agent character varying(255),
    correlation_id character varying(64),
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: sn_aff_clients; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_aff_clients (
    organization_id uuid NOT NULL,
    agent_id uuid NOT NULL,
    company_name character varying(255) NOT NULL,
    vat_number character varying(32),
    contact_name character varying(255),
    email character varying(255),
    phone character varying(64),
    mamicash_balance numeric(14,2) NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    mamify_customer_id character varying(64)
);


--
-- Name: sn_aff_commissions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_aff_commissions (
    organization_id uuid NOT NULL,
    kind character varying(8) NOT NULL,
    operation_id uuid,
    period character varying(7) NOT NULL,
    beneficiary_agent_id uuid NOT NULL,
    "position" integer NOT NULL,
    rate numeric(7,4),
    base_amount numeric(14,2) NOT NULL,
    amount numeric(14,2) NOT NULL,
    career_level integer,
    status character varying(16) NOT NULL,
    payable_on date NOT NULL,
    paid_at timestamp with time zone,
    paid_by_user_id uuid,
    plan_version_id uuid NOT NULL,
    details jsonb NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: sn_aff_licenses; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_aff_licenses (
    organization_id uuid NOT NULL,
    code character varying(32) NOT NULL,
    owner_agent_id uuid NOT NULL,
    purchase_operation_id uuid NOT NULL,
    origin character varying(16) NOT NULL,
    unit_cost numeric(14,2) NOT NULL,
    status character varying(16) NOT NULL,
    resale_operation_id uuid,
    client_id uuid,
    resold_at timestamp with time zone,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: sn_aff_monthly_results; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_aff_monthly_results (
    organization_id uuid NOT NULL,
    period character varying(7) NOT NULL,
    agent_id uuid NOT NULL,
    bcp integer NOT NULL,
    bct integer NOT NULL,
    legs jsonb NOT NULL,
    career_level integer,
    bonus_amount numeric(14,2) NOT NULL,
    plan_version_id uuid NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: sn_aff_operations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_aff_operations (
    organization_id uuid NOT NULL,
    kind character varying(32) NOT NULL,
    status character varying(16) NOT NULL,
    agent_id uuid NOT NULL,
    client_id uuid,
    product_code character varying(32),
    quantity integer NOT NULL,
    period character varying(7),
    nominal_amount numeric(14,2) NOT NULL,
    discount_amount numeric(14,2) NOT NULL,
    paid_amount numeric(14,2) NOT NULL,
    bc_points integer NOT NULL,
    license_id uuid,
    plan_version_id uuid NOT NULL,
    idempotency_key character varying(160) NOT NULL,
    reverses_operation_id uuid,
    payment_method character varying(32),
    note character varying(1000),
    created_by_user_id uuid,
    confirmed_at timestamp with time zone,
    confirmed_by_user_id uuid,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_sn_aff_operations_paid_amount_non_negative CHECK ((paid_amount >= (0)::numeric))
);


--
-- Name: sn_aff_period_closes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_aff_period_closes (
    organization_id uuid NOT NULL,
    period character varying(7) NOT NULL,
    plan_version_id uuid NOT NULL,
    closed_by_user_id uuid,
    affiliates_count integer NOT NULL,
    qualified_count integer NOT NULL,
    total_points integer NOT NULL,
    total_bonus numeric(14,2) NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: sn_aff_plan_versions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_aff_plan_versions (
    organization_id uuid NOT NULL,
    label character varying(64) NOT NULL,
    valid_from timestamp with time zone NOT NULL,
    config jsonb NOT NULL,
    notes character varying(1000),
    created_by_user_id uuid,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: sn_aff_points; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_aff_points (
    organization_id uuid NOT NULL,
    operation_id uuid NOT NULL,
    agent_id uuid NOT NULL,
    period character varying(7) NOT NULL,
    points integer NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: sn_aff_subscriptions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_aff_subscriptions (
    organization_id uuid NOT NULL,
    agent_id uuid NOT NULL,
    status character varying(16) NOT NULL,
    started_at timestamp with time zone NOT NULL,
    cancelled_at timestamp with time zone,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: sn_agreement_attributions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_agreement_attributions (
    organization_id uuid NOT NULL,
    producer_agent_id uuid NOT NULL,
    attributed_promoter_id uuid NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: sn_agreement_checkouts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_agreement_checkouts (
    organization_id uuid NOT NULL,
    contract_request_id uuid NOT NULL,
    stripe_checkout_session_id character varying(255) NOT NULL,
    payment_plan character varying(16) NOT NULL,
    lines jsonb NOT NULL,
    total_cents bigint NOT NULL,
    instalment_cents bigint NOT NULL,
    created_by_user_id uuid,
    completed_at timestamp with time zone,
    stripe_subscription_id character varying(255),
    stripe_customer_id character varying(255),
    outcome character varying(255),
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: sn_agreement_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_agreement_events (
    contract_id uuid NOT NULL,
    event_type character varying(64) NOT NULL,
    payload jsonb NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: sn_agreement_instalments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_agreement_instalments (
    organization_id uuid NOT NULL,
    contract_id uuid NOT NULL,
    number integer NOT NULL,
    instalments_total integer NOT NULL,
    due_date date NOT NULL,
    amount_cents bigint NOT NULL,
    status character varying(16) NOT NULL,
    paid_at timestamp with time zone,
    payment_source character varying(16),
    confirmed_by_user_id uuid,
    stripe_invoice_id character varying(255),
    commission_event_id uuid,
    commission_released_at timestamp with time zone,
    commission_calculation_id uuid,
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: sn_agreement_payout_plans; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_agreement_payout_plans (
    organization_id uuid NOT NULL,
    contract_id uuid NOT NULL,
    accepted_by_user_id uuid NOT NULL,
    accepted_at timestamp with time zone NOT NULL,
    payment_plan character varying(16),
    total_commission_cents bigint NOT NULL,
    preview jsonb NOT NULL,
    checksum character varying(64) NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: sn_agreement_requests; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_agreement_requests (
    organization_id uuid NOT NULL,
    customer_id uuid NOT NULL,
    status character varying(16) NOT NULL,
    holder_first_name character varying(128),
    holder_last_name character varying(128),
    email character varying(320),
    pec character varying(320),
    iban character varying(34),
    street character varying(255),
    city character varying(128),
    province character varying(8),
    postal_code character varying(16),
    created_by_user_id uuid,
    created_by_role character varying(32),
    activated_by_promoter_id uuid,
    submitted_at timestamp with time zone,
    cancelled_at timestamp with time zone,
    updated_at timestamp with time zone,
    bank_transfer_requested_at timestamp with time zone,
    bank_transfer_total_cents bigint,
    bank_transfer_confirmed_at timestamp with time zone,
    bank_transfer_confirmed_by_user_id uuid,
    payment_proof_storage_key character varying(500),
    payment_proof_original_filename character varying(255),
    payment_proof_uploaded_at timestamp with time zone,
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: sn_agreement_status_log; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_agreement_status_log (
    contract_id uuid NOT NULL,
    from_status character varying(32),
    to_status character varying(32) NOT NULL,
    actor_user_id uuid NOT NULL,
    reason character varying(500),
    notes character varying(2000),
    correlation_id character varying(64) NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: sn_agreements; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_agreements (
    organization_id uuid NOT NULL,
    customer_id uuid NOT NULL,
    contract_request_id uuid NOT NULL,
    supply_point_id uuid,
    product_version_id uuid,
    contract_attribution_id uuid,
    network_snapshot_id uuid,
    status character varying(32) NOT NULL,
    notes character varying(2000),
    iban character varying(34),
    email character varying(320),
    holder_first_name character varying(128),
    holder_last_name character varying(128),
    pec character varying(320),
    activated_at timestamp with time zone,
    expires_at timestamp with time zone,
    updated_at timestamp with time zone,
    created_by_user_id uuid,
    created_by_role character varying(32),
    activated_by_promoter_id uuid,
    first_referrer_agent_id uuid,
    customer_kind character varying(32),
    net_amount_cents bigint,
    vat_rate numeric(5,2),
    vat_amount_cents bigint,
    gross_amount_cents bigint,
    payment_plan character varying(16),
    payment_discount_cents integer DEFAULT 0 NOT NULL,
    payment_method character varying(16),
    stripe_checkout_session_id character varying(255),
    stripe_customer_id character varying(255),
    stripe_subscription_id character varying(255),
    stripe_subscription_item_id character varying(255),
    billing_stopped_at timestamp with time zone,
    paid_at timestamp with time zone,
    cashback_credited_at timestamp with time zone,
    terms_accepted_at timestamp with time zone,
    terms_accepted_by_user_id uuid,
    terms_version character varying(32),
    terms_accepted_ip character varying(45),
    terms_accepted_user_agent character varying(500),
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    sold_at timestamp with time zone,
    sale_amount_cents bigint,
    reference_margin_cents bigint,
    split_plan_id uuid,
    seller_role_code character varying(32),
    lead_id uuid,
    CONSTRAINT ck_sn_agreements_product_required CHECK (((product_version_id IS NOT NULL) OR ((status)::text = ANY ((ARRAY['DRAFT'::character varying, 'CANCELLED'::character varying])::text[]))))
);


--
-- Name: sn_aliexpress_config; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_aliexpress_config (
    organization_id uuid NOT NULL,
    app_key character varying(64),
    app_secret character varying(255),
    access_token character varying(500),
    refresh_token character varying(500),
    token_expires_at timestamp with time zone,
    account_label character varying(255),
    last_connected_at timestamp with time zone,
    enabled boolean DEFAULT false NOT NULL,
    ship_to_country character varying(2) DEFAULT 'IT'::character varying NOT NULL,
    target_currency character varying(3) DEFAULT 'EUR'::character varying NOT NULL,
    target_language character varying(8) DEFAULT 'it'::character varying NOT NULL,
    currency_rate numeric(10,6) DEFAULT '1'::numeric NOT NULL,
    price_basis character varying(8) DEFAULT 'COST'::character varying NOT NULL,
    markup_percentage integer DEFAULT 100 NOT NULL,
    markup_fixed_cents integer DEFAULT 0 NOT NULL,
    price_rounding character varying(8) DEFAULT '90'::character varying NOT NULL,
    shipping_mode character varying(16) DEFAULT 'CUSTOMER_PAYS'::character varying NOT NULL,
    shipping_minimum_cents integer DEFAULT 590 NOT NULL,
    shipping_days character varying(32) DEFAULT '10-20'::character varying,
    default_credit_percentage integer DEFAULT 30 NOT NULL,
    auto_forward boolean DEFAULT true NOT NULL,
    updated_at timestamp with time zone,
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: sn_aliexpress_item_variants; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_aliexpress_item_variants (
    product_id uuid NOT NULL,
    aliexpress_sku_id character varying(128) NOT NULL,
    sku_attr character varying(500),
    sku character varying(128),
    label character varying(255) DEFAULT ''::character varying NOT NULL,
    image_url character varying(1000),
    cost_amount numeric(12,2),
    source_price_amount numeric(12,2) NOT NULL,
    price_cents bigint NOT NULL,
    price_override_cents bigint,
    inventory integer,
    active boolean DEFAULT true NOT NULL,
    available_in_store boolean DEFAULT true NOT NULL,
    last_synced_at timestamp with time zone,
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: sn_aliexpress_items; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_aliexpress_items (
    organization_id uuid NOT NULL,
    aliexpress_product_id character varying(128) NOT NULL,
    product_url character varying(1000),
    name character varying(255) NOT NULL,
    source_title character varying(500),
    vendor character varying(255),
    description character varying(8000) DEFAULT ''::character varying NOT NULL,
    image_url character varying(1000),
    images jsonb DEFAULT '[]'::jsonb NOT NULL,
    status character varying(16) DEFAULT 'ACTIVE'::character varying NOT NULL,
    credit_discount_percentage integer DEFAULT 30 NOT NULL,
    markup_percentage integer,
    last_synced_at timestamp with time zone,
    sync_error character varying(500),
    created_by_user_id uuid NOT NULL,
    updated_at timestamp with time zone,
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_sn_aliexpress_items_credit_discount_percentage_below_100 CHECK (((credit_discount_percentage >= 0) AND (credit_discount_percentage <= 99)))
);


--
-- Name: sn_aliexpress_order_lines; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_aliexpress_order_lines (
    order_id uuid NOT NULL,
    aliexpress_product_id uuid NOT NULL,
    aliexpress_variant_id uuid NOT NULL,
    quantity integer NOT NULL,
    unit_price_cents bigint NOT NULL,
    unit_cost_amount numeric(12,2),
    supplier_shipping_cents bigint,
    product_name character varying(255) NOT NULL,
    variant_label character varying(255),
    credit_discount_percentage integer DEFAULT 0 NOT NULL,
    aliexpress_order_id character varying(128),
    tracking_number character varying(128),
    tracking_url character varying(1000),
    tracking_company character varying(128),
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_sn_aliexpress_order_lines_quantity_positive CHECK ((quantity > 0))
);


--
-- Name: sn_order_number_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.sn_order_number_seq
    START WITH 1000
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: sn_aliexpress_orders; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_aliexpress_orders (
    organization_id uuid NOT NULL,
    customer_user_id uuid NOT NULL,
    aliexpress_product_id uuid NOT NULL,
    aliexpress_variant_id uuid NOT NULL,
    created_by_user_id uuid NOT NULL,
    number bigint DEFAULT nextval('public.sn_order_number_seq'::regclass) NOT NULL,
    quantity integer DEFAULT 1 NOT NULL,
    unit_price_cents bigint NOT NULL,
    shipping_cents bigint DEFAULT '0'::bigint NOT NULL,
    supplier_shipping_cents bigint,
    minimum_shipping_cents bigint,
    amount_cents bigint NOT NULL,
    credit_applied_cents bigint DEFAULT '0'::bigint NOT NULL,
    bank_transfer_discount_cents bigint DEFAULT '0'::bigint NOT NULL,
    vat_percentage integer DEFAULT 0 NOT NULL,
    vat_amount_cents bigint DEFAULT '0'::bigint NOT NULL,
    vat_mode character varying(16) DEFAULT 'ADDED'::character varying NOT NULL,
    credit_debit_transaction_id uuid,
    status character varying(16) DEFAULT 'AWAITING_PAYMENT'::character varying NOT NULL,
    payment_method character varying(16) DEFAULT 'BANK_TRANSFER'::character varying NOT NULL,
    stripe_checkout_session_id character varying(255),
    note character varying(1000),
    payment_proof_storage_key character varying(500),
    payment_proof_original_filename character varying(255),
    payment_proof_uploaded_at timestamp with time zone,
    paid_by_user_id uuid,
    paid_at timestamp with time zone,
    cancelled_by_user_id uuid,
    cancelled_at timestamp with time zone,
    cancellation_reason character varying(500),
    recipient_name character varying(128) NOT NULL,
    recipient_phone character varying(32),
    address_line1 character varying(255) NOT NULL,
    address_line2 character varying(255),
    city character varying(128) NOT NULL,
    province character varying(64) NOT NULL,
    postal_code character varying(16) NOT NULL,
    country_code character varying(2) DEFAULT 'IT'::character varying NOT NULL,
    shipping_days character varying(32),
    unit_cost_amount numeric(12,2),
    currency_rate numeric(10,6) DEFAULT '1'::numeric NOT NULL,
    fulfillment_status character varying(16) DEFAULT 'NOT_SENT'::character varying NOT NULL,
    out_order_id character varying(64),
    aliexpress_order_id character varying(128),
    aliexpress_order_status character varying(64),
    forwarded_at timestamp with time zone,
    forwarded_by_user_id uuid,
    forward_error character varying(500),
    tracking_number character varying(128),
    tracking_url character varying(1000),
    tracking_company character varying(128),
    shipped_at timestamp with time zone,
    delivered_at timestamp with time zone,
    last_sync_at timestamp with time zone,
    attempt_count integer DEFAULT 0 NOT NULL,
    last_attempt_at timestamp with time zone,
    next_retry_at timestamp with time zone,
    last_error_kind character varying(24),
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_sn_aliexpress_orders_credit_applied_non_negative CHECK ((credit_applied_cents >= 0)),
    CONSTRAINT ck_sn_aliexpress_orders_credit_applied_not_over_amount CHECK ((credit_applied_cents <= amount_cents)),
    CONSTRAINT ck_sn_aliexpress_orders_quantity_positive CHECK ((quantity > 0)),
    CONSTRAINT ck_sn_aliexpress_orders_vat_mode CHECK (((vat_mode)::text = ANY ((ARRAY['INCLUDED'::character varying, 'ADDED'::character varying])::text[])))
);


--
-- Name: sn_attribution_fixes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_attribution_fixes (
    organization_id uuid NOT NULL,
    customer_attribution_id uuid NOT NULL,
    previous_promoter_code_id uuid NOT NULL,
    new_promoter_code_id uuid NOT NULL,
    requested_by uuid NOT NULL,
    approved_by uuid,
    reason character varying(500) NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: sn_basket_lines; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_basket_lines (
    cart_id uuid NOT NULL,
    quantity bigint NOT NULL,
    aliexpress_variant_id uuid,
    cj_variant_id uuid,
    shopify_variant_id uuid,
    sosnet_market_variant_id uuid,
    product_version_id uuid,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_sn_basket_lines_exactly_one_reference CHECK ((num_nonnulls(aliexpress_variant_id, cj_variant_id, shopify_variant_id, sosnet_market_variant_id, product_version_id) = 1)),
    CONSTRAINT ck_sn_basket_lines_quantity_max CHECK ((quantity <= 99)),
    CONSTRAINT ck_sn_basket_lines_quantity_positive CHECK ((quantity > 0))
);


--
-- Name: sn_baskets; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_baskets (
    organization_id uuid NOT NULL,
    customer_user_id uuid NOT NULL,
    shop character varying(16) NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_sn_baskets_shop CHECK (((shop)::text = ANY ((ARRAY['aliexpress'::character varying, 'cj'::character varying, 'shopify'::character varying, 'sosnet_market'::character varying, 'catalog'::character varying])::text[])))
);


--
-- Name: sn_businesses; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_businesses (
    customer_id uuid NOT NULL,
    company_name character varying(255) NOT NULL,
    legal_form character varying(64),
    sdi_code character varying(16)
);


--
-- Name: sn_career_levels; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_career_levels (
    organization_id uuid NOT NULL,
    code character varying(16) NOT NULL,
    name character varying(128) NOT NULL,
    level integer NOT NULL,
    personal_token_cents bigint NOT NULL,
    energy_share_percentage numeric(5,2) NOT NULL,
    personal_volume_threshold_cents bigint NOT NULL,
    group_volume_threshold_cents bigint NOT NULL,
    evaluation_window_months integer NOT NULL,
    single_branch_cap_percentage numeric(5,2) NOT NULL,
    valid_from timestamp with time zone NOT NULL,
    valid_to timestamp with time zone,
    rule_version character varying(32) NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: sn_catalog_section_items; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_catalog_section_items (
    organization_id uuid NOT NULL,
    category_id uuid NOT NULL,
    shop character varying(16) NOT NULL,
    product_id uuid NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: sn_catalog_sections; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_catalog_sections (
    organization_id uuid NOT NULL,
    shop character varying(16) NOT NULL,
    name character varying(120) NOT NULL,
    "position" integer DEFAULT 0 NOT NULL,
    active boolean DEFAULT true NOT NULL,
    updated_at timestamp with time zone,
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: sn_cj_config; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_cj_config (
    organization_id uuid NOT NULL,
    api_key character varying(255),
    access_token text,
    access_token_expires_at timestamp with time zone,
    refresh_token text,
    refresh_token_expires_at timestamp with time zone,
    open_id character varying(64),
    enabled boolean DEFAULT false NOT NULL,
    sandbox boolean DEFAULT true NOT NULL,
    usd_eur_rate numeric(10,6) DEFAULT 0.92 NOT NULL,
    markup_percentage integer DEFAULT 40 NOT NULL,
    markup_fixed_cents integer DEFAULT 0 NOT NULL,
    price_rounding character varying(8) DEFAULT '90'::character varying NOT NULL,
    shipping_mode character varying(16) DEFAULT 'CUSTOMER_PAYS'::character varying NOT NULL,
    default_credit_percentage integer DEFAULT 30 NOT NULL,
    destination_country character varying(2) DEFAULT 'IT'::character varying NOT NULL,
    auto_forward boolean DEFAULT false NOT NULL,
    last_balance_usd numeric(12,2),
    last_balance_at timestamp with time zone,
    updated_at timestamp with time zone,
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_sn_cj_config_default_credit_below_100 CHECK (((default_credit_percentage >= 0) AND (default_credit_percentage <= 99)))
);


--
-- Name: sn_cj_item_variants; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_cj_item_variants (
    product_id uuid NOT NULL,
    cj_vid character varying(64) NOT NULL,
    cj_sku character varying(128),
    label character varying(255) DEFAULT ''::character varying NOT NULL,
    image_url character varying(1000),
    cost_usd numeric(10,2) NOT NULL,
    weight_g integer DEFAULT 0 NOT NULL,
    price_cents bigint NOT NULL,
    price_override_cents bigint,
    inventory integer DEFAULT 0 NOT NULL,
    active boolean DEFAULT true NOT NULL,
    available_on_cj boolean DEFAULT true NOT NULL,
    last_synced_at timestamp with time zone,
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: sn_cj_items; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_cj_items (
    organization_id uuid NOT NULL,
    cj_pid character varying(64) NOT NULL,
    cj_sku character varying(64),
    name character varying(255) NOT NULL,
    name_en character varying(500),
    description character varying(8000) DEFAULT ''::character varying NOT NULL,
    image_url character varying(1000),
    images jsonb DEFAULT '[]'::jsonb NOT NULL,
    category_name character varying(255),
    origin_country character varying(2) DEFAULT 'CN'::character varying NOT NULL,
    shipping_estimate_usd numeric(10,2),
    shipping_days character varying(32),
    status character varying(16) DEFAULT 'ACTIVE'::character varying NOT NULL,
    credit_discount_percentage integer DEFAULT 100 NOT NULL,
    markup_percentage integer,
    last_synced_at timestamp with time zone,
    sync_error character varying(500),
    created_by_user_id uuid NOT NULL,
    updated_at timestamp with time zone,
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_sn_cj_items_credit_below_100 CHECK (((credit_discount_percentage >= 0) AND (credit_discount_percentage <= 99)))
);


--
-- Name: sn_cj_order_lines; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_cj_order_lines (
    order_id uuid NOT NULL,
    product_id uuid NOT NULL,
    variant_id uuid NOT NULL,
    quantity integer NOT NULL,
    unit_price_cents bigint NOT NULL,
    product_name character varying(255) NOT NULL,
    variant_label character varying(255),
    credit_discount_percentage integer DEFAULT 0 NOT NULL,
    supplier_order_id character varying(128),
    tracking_number character varying(128),
    tracking_url character varying(1000),
    tracking_company character varying(128),
    unit_cost_usd numeric(12,2),
    origin_country character varying(8),
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_sn_cj_order_lines_quantity_positive CHECK ((quantity > 0))
);


--
-- Name: sn_cj_orders; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_cj_orders (
    organization_id uuid NOT NULL,
    customer_user_id uuid NOT NULL,
    cj_product_id uuid NOT NULL,
    cj_variant_id uuid NOT NULL,
    created_by_user_id uuid NOT NULL,
    number bigint DEFAULT nextval('public.sn_order_number_seq'::regclass) NOT NULL,
    quantity integer DEFAULT 1 NOT NULL,
    unit_price_cents bigint NOT NULL,
    shipping_cents bigint DEFAULT '0'::bigint NOT NULL,
    amount_cents bigint NOT NULL,
    credit_applied_cents bigint DEFAULT '0'::bigint NOT NULL,
    bank_transfer_discount_cents bigint DEFAULT '0'::bigint NOT NULL,
    vat_percentage integer DEFAULT 0 NOT NULL,
    vat_amount_cents bigint DEFAULT '0'::bigint NOT NULL,
    vat_mode character varying(16) DEFAULT 'ADDED'::character varying NOT NULL,
    credit_debit_transaction_id uuid,
    status character varying(16) DEFAULT 'AWAITING_PAYMENT'::character varying NOT NULL,
    payment_method character varying(16) DEFAULT 'BANK_TRANSFER'::character varying NOT NULL,
    stripe_checkout_session_id character varying(255),
    note character varying(1000),
    payment_proof_storage_key character varying(500),
    payment_proof_original_filename character varying(255),
    payment_proof_uploaded_at timestamp with time zone,
    paid_by_user_id uuid,
    paid_at timestamp with time zone,
    cancelled_by_user_id uuid,
    cancelled_at timestamp with time zone,
    cancellation_reason character varying(500),
    recipient_name character varying(128) NOT NULL,
    recipient_phone character varying(32),
    address_line1 character varying(255) NOT NULL,
    address_line2 character varying(255),
    city character varying(128) NOT NULL,
    province character varying(64) NOT NULL,
    postal_code character varying(16) NOT NULL,
    country_code character varying(2) DEFAULT 'IT'::character varying NOT NULL,
    logistic_name character varying(64) NOT NULL,
    origin_country character varying(2) DEFAULT 'CN'::character varying NOT NULL,
    shipping_days character varying(32),
    unit_cost_usd numeric(10,2) NOT NULL,
    shipping_cost_usd numeric(10,2) DEFAULT '0'::numeric NOT NULL,
    usd_eur_rate numeric(10,6) NOT NULL,
    fulfillment_status character varying(16) DEFAULT 'NOT_SENT'::character varying NOT NULL,
    sandbox boolean DEFAULT false NOT NULL,
    cj_order_id character varying(64),
    cj_order_status character varying(32),
    cj_amount_usd numeric(12,2),
    forwarded_at timestamp with time zone,
    forwarded_by_user_id uuid,
    forward_error character varying(500),
    tracking_number character varying(128),
    tracking_provider character varying(64),
    shipped_at timestamp with time zone,
    delivered_at timestamp with time zone,
    last_cj_sync_at timestamp with time zone,
    cj_order_code character varying(64),
    cj_shipment_order_id character varying(64),
    cj_pay_url character varying(1000),
    cj_payment_status character varying(24) DEFAULT 'NOT_REQUIRED'::character varying NOT NULL,
    cj_product_amount_usd numeric(10,2),
    cj_postage_amount_usd numeric(10,2),
    cj_ioss_amount_usd numeric(10,2),
    cj_paid_at timestamp with time zone,
    attempt_count integer DEFAULT 0 NOT NULL,
    last_attempt_at timestamp with time zone,
    next_retry_at timestamp with time zone,
    last_error_kind character varying(24),
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_sn_cj_orders_credit_applied_non_negative CHECK ((credit_applied_cents >= 0)),
    CONSTRAINT ck_sn_cj_orders_credit_applied_not_over_amount CHECK ((credit_applied_cents <= amount_cents)),
    CONSTRAINT ck_sn_cj_orders_quantity_positive CHECK ((quantity > 0)),
    CONSTRAINT ck_sn_cj_orders_vat_mode CHECK (((vat_mode)::text = ANY ((ARRAY['INCLUDED'::character varying, 'ADDED'::character varying])::text[])))
);


--
-- Name: sn_client_attributions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_client_attributions (
    organization_id uuid NOT NULL,
    customer_id uuid NOT NULL,
    promoter_code_id uuid NOT NULL,
    referral_session_id uuid,
    attributed_at timestamp with time zone NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: sn_client_profiles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_client_profiles (
    customer_id uuid NOT NULL,
    first_name character varying(128) NOT NULL,
    last_name character varying(128) NOT NULL
);


--
-- Name: sn_clients; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_clients (
    organization_id uuid NOT NULL,
    user_id uuid,
    kind character varying(32) NOT NULL,
    fiscal_code character varying(32),
    vat_number character varying(32),
    email character varying(255) NOT NULL,
    phone character varying(32),
    pec character varying(255),
    photo_url character varying(1000),
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: sn_commercial_roles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_commercial_roles (
    organization_id uuid NOT NULL,
    code character varying(32) NOT NULL,
    name character varying(120) NOT NULL,
    description character varying(1000) NOT NULL,
    commission_mode character varying(16) NOT NULL,
    network_depth integer,
    allows_delegation boolean NOT NULL,
    allows_downline boolean NOT NULL,
    can_close_sales boolean NOT NULL,
    is_default boolean NOT NULL,
    is_active boolean NOT NULL,
    sort_order integer NOT NULL,
    metadata jsonb NOT NULL,
    updated_at timestamp with time zone,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: sn_credit_accounts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_credit_accounts (
    organization_id uuid NOT NULL,
    user_id uuid NOT NULL,
    address character varying(42) NOT NULL,
    balance_cents bigint DEFAULT '0'::bigint NOT NULL,
    currency character varying(3) DEFAULT 'EUR'::character varying NOT NULL,
    can_transfer boolean DEFAULT false NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_sn_credit_accounts_balance_non_negative CHECK ((balance_cents >= 0))
);


--
-- Name: sn_credit_ledger; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_credit_ledger (
    organization_id uuid NOT NULL,
    from_wallet_id uuid,
    to_wallet_id uuid,
    amount_cents bigint NOT NULL,
    currency character varying(3) DEFAULT 'EUR'::character varying NOT NULL,
    type character varying(16) NOT NULL,
    reference_contract_id uuid,
    source character varying(32),
    reference_invoice_redemption_id uuid,
    reference_order_id uuid,
    reference_imported_order_id uuid,
    reference_cj_order_id uuid,
    reference_shopify_order_id uuid,
    reference_aliexpress_order_id uuid,
    reference_sosnet_market_order_id uuid,
    reverses_transaction_id uuid,
    note character varying(500),
    actor_user_id uuid,
    idempotency_key character varying(128) NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_sn_credit_ledger_has_a_side CHECK (((from_wallet_id IS NOT NULL) OR (to_wallet_id IS NOT NULL)))
);


--
-- Name: sn_delegations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_delegations (
    organization_id uuid NOT NULL,
    influencer_agent_id uuid NOT NULL,
    delegate_agent_id uuid NOT NULL,
    valid_from timestamp with time zone NOT NULL,
    valid_to timestamp with time zone,
    created_by_user_id uuid,
    reason character varying(500),
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: sn_email_confirmations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_email_confirmations (
    user_id uuid NOT NULL,
    token_hash character varying(64) NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    used_at timestamp with time zone,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: sn_event_outbox; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_event_outbox (
    organization_id uuid NOT NULL,
    event_type character varying(64) NOT NULL,
    payload jsonb NOT NULL,
    processed_at timestamp with time zone,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: sn_friend_invite_codes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_friend_invite_codes (
    organization_id uuid NOT NULL,
    user_id uuid NOT NULL,
    code character varying(32) NOT NULL,
    status character varying(16) DEFAULT 'ACTIVE'::character varying NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: sn_friend_invite_rewards; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_friend_invite_rewards (
    organization_id uuid NOT NULL,
    referrer_user_id uuid NOT NULL,
    milestone integer NOT NULL,
    status character varying(16) DEFAULT 'REQUESTED'::character varying NOT NULL,
    handled_by_user_id uuid,
    handled_at timestamp with time zone,
    note character varying(500),
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: sn_friend_invites; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_friend_invites (
    organization_id uuid NOT NULL,
    referrer_user_id uuid NOT NULL,
    referred_customer_id uuid NOT NULL,
    code_used character varying(32) NOT NULL,
    source character varying(16) NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: sn_inbox_messages; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_inbox_messages (
    organization_id uuid NOT NULL,
    recipient_user_id uuid NOT NULL,
    type character varying(64) NOT NULL,
    entity_type character varying(64) NOT NULL,
    entity_id character varying(64) NOT NULL,
    title character varying(255) NOT NULL,
    body character varying(1000),
    is_read boolean DEFAULT false NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: sn_invite_codes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_invite_codes (
    organization_id uuid NOT NULL,
    agent_id uuid NOT NULL,
    code character varying(32) NOT NULL,
    personal_link character varying(500) NOT NULL,
    qr_code_url character varying(500),
    status character varying(32) NOT NULL,
    valid_from timestamp with time zone NOT NULL,
    valid_to timestamp with time zone,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: sn_invite_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_invite_events (
    organization_id uuid NOT NULL,
    promoter_code_id uuid NOT NULL,
    ip_address character varying(64),
    user_agent character varying(255),
    occurred_at timestamp with time zone NOT NULL,
    id uuid NOT NULL
);


--
-- Name: sn_invite_visits; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_invite_visits (
    organization_id uuid NOT NULL,
    promoter_code_id uuid NOT NULL,
    cookie_token_hash character varying(64) NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: sn_knowledge_articles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_knowledge_articles (
    organization_id uuid NOT NULL,
    title character varying(200) NOT NULL,
    body text,
    audience character varying(16) DEFAULT 'BOTH'::character varying NOT NULL,
    status character varying(16) DEFAULT 'PUBLISHED'::character varying NOT NULL,
    image_url character varying(500),
    pdf_url character varying(500),
    pdf_filename character varying(255),
    video_url character varying(500),
    created_by_user_id uuid NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: sn_leads; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_leads (
    organization_id uuid NOT NULL,
    promoter_agent_id uuid NOT NULL,
    customer_id uuid,
    product_id uuid,
    contact_name character varying(200) NOT NULL,
    contact_email character varying(255),
    contact_phone character varying(40),
    notes character varying(2000) DEFAULT ''::character varying NOT NULL,
    status character varying(16) NOT NULL,
    assigned_agent_id uuid,
    converted_contract_id uuid,
    converted_at timestamp with time zone,
    closed_reason character varying(500),
    created_by_user_id uuid,
    updated_at timestamp with time zone,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: sn_login_sessions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_login_sessions (
    user_id uuid NOT NULL,
    refresh_token_hash character varying(64) NOT NULL,
    user_agent character varying(255),
    ip_address character varying(64),
    expires_at timestamp with time zone NOT NULL,
    revoked_at timestamp with time zone,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: sn_mamify_config; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_mamify_config (
    organization_id uuid NOT NULL,
    enabled boolean NOT NULL,
    base_url character varying(255) NOT NULL,
    api_key character varying(255),
    functionality character varying(64),
    root_customer character varying(255),
    paid_statuses jsonb NOT NULL,
    cancelled_statuses jsonb NOT NULL,
    webhook_token character varying(64) NOT NULL,
    webhook_ids jsonb NOT NULL,
    payout_mode character varying(16) NOT NULL,
    payout_email character varying(255),
    payout_password character varying(255),
    payout_wallets jsonb NOT NULL,
    units_per_euro numeric(10,4) NOT NULL,
    auto_payout boolean NOT NULL,
    sync_actor_user_id uuid,
    network_sync_started_at timestamp with time zone,
    last_network_sync_at timestamp with time zone,
    last_network_sync_result jsonb NOT NULL,
    last_orders_sync_at timestamp with time zone,
    last_error character varying(1000),
    last_error_at timestamp with time zone,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    order_apps jsonb NOT NULL,
    product_catalog jsonb NOT NULL,
    orders_calls_per_minute integer DEFAULT 30 NOT NULL,
    last_new_members_at timestamp with time zone,
    network_sync_progress jsonb NOT NULL
);


--
-- Name: sn_mamify_members; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_mamify_members (
    organization_id uuid NOT NULL,
    mamify_customer_id character varying(64) NOT NULL,
    agent_id uuid NOT NULL,
    sponsor_customer_id character varying(64),
    email character varying(255),
    first_name character varying(120),
    last_name character varying(120),
    phone character varying(64),
    mamify_level integer,
    registered_at timestamp with time zone,
    present boolean NOT NULL,
    last_seen_at timestamp with time zone NOT NULL,
    raw jsonb NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    direct_count integer DEFAULT 0 NOT NULL,
    orders_checked_at timestamp with time zone,
    branch_sync_requested_at timestamp with time zone,
    branch_synced_at timestamp with time zone,
    branch_sync_result jsonb DEFAULT '{}'::jsonb NOT NULL
);


--
-- Name: sn_mamify_orders; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_mamify_orders (
    organization_id uuid NOT NULL,
    mamify_order_id character varying(64) NOT NULL,
    buyer_customer_id character varying(64),
    status_code character varying(64),
    status_title character varying(120),
    total numeric(14,2),
    ordered_at timestamp with time zone,
    state character varying(16) NOT NULL,
    message character varying(1000),
    operation_ids jsonb NOT NULL,
    source character varying(16) NOT NULL,
    raw jsonb NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: sn_mamify_payouts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_mamify_payouts (
    organization_id uuid NOT NULL,
    commission_id uuid NOT NULL,
    mamify_customer_id character varying(64) NOT NULL,
    wallet character varying(16) NOT NULL,
    amount_eur numeric(14,2) NOT NULL,
    units numeric(14,2) NOT NULL,
    status character varying(16) NOT NULL,
    attempts integer NOT NULL,
    response jsonb NOT NULL,
    error character varying(1000),
    sent_at timestamp with time zone,
    requested_by_user_id uuid,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: sn_mamify_products; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_mamify_products (
    organization_id uuid NOT NULL,
    mamify_product_id character varying(64) NOT NULL,
    title character varying(255),
    plan_code character varying(32) NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: sn_mamify_webhook_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_mamify_webhook_events (
    organization_id uuid NOT NULL,
    event_type character varying(64),
    body_hash character varying(64) NOT NULL,
    payload jsonb NOT NULL,
    processed_at timestamp with time zone,
    error text,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: sn_market_config; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_market_config (
    organization_id uuid NOT NULL,
    enabled boolean DEFAULT false NOT NULL,
    shipping_mode character varying(16) DEFAULT 'CUSTOMER_PAYS'::character varying NOT NULL,
    shipping_flat_cents integer DEFAULT 0 NOT NULL,
    shipping_days character varying(32),
    ship_to_country character varying(2) DEFAULT 'IT'::character varying NOT NULL,
    auto_forward boolean DEFAULT false NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: sn_market_item_variants; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_market_item_variants (
    product_id uuid NOT NULL,
    label character varying(255) DEFAULT 'Unica'::character varying NOT NULL,
    sku character varying(128),
    image_url character varying(1000),
    price_cents bigint NOT NULL,
    inventory integer,
    active boolean DEFAULT true NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_sn_market_item_variants_price_positive CHECK ((price_cents > 0))
);


--
-- Name: sn_market_items; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_market_items (
    organization_id uuid NOT NULL,
    producer_id uuid,
    name character varying(255) NOT NULL,
    description character varying(8000) DEFAULT ''::character varying NOT NULL,
    image_url character varying(1000),
    images jsonb DEFAULT '[]'::jsonb NOT NULL,
    status character varying(16) DEFAULT 'ACTIVE'::character varying NOT NULL,
    credit_discount_percentage integer DEFAULT 30 NOT NULL,
    unit_cost_cents bigint,
    created_by_user_id uuid NOT NULL,
    updated_at timestamp with time zone,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_sn_market_items_credit_percentage_range CHECK (((credit_discount_percentage >= 0) AND (credit_discount_percentage <= 99)))
);


--
-- Name: sn_market_order_lines; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_market_order_lines (
    order_id uuid NOT NULL,
    product_id uuid NOT NULL,
    variant_id uuid NOT NULL,
    quantity integer NOT NULL,
    unit_price_cents bigint NOT NULL,
    unit_cost_cents bigint,
    product_name character varying(255) NOT NULL,
    variant_label character varying(255),
    producer_name character varying(160),
    credit_discount_percentage integer DEFAULT 0 NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_sn_market_order_lines_quantity_positive CHECK ((quantity > 0))
);


--
-- Name: sn_market_orders; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_market_orders (
    organization_id uuid NOT NULL,
    customer_user_id uuid NOT NULL,
    created_by_user_id uuid NOT NULL,
    number bigint DEFAULT nextval('public.sn_order_number_seq'::regclass) NOT NULL,
    items_cents bigint DEFAULT '0'::bigint NOT NULL,
    shipping_cents bigint DEFAULT '0'::bigint NOT NULL,
    amount_cents bigint NOT NULL,
    credit_applied_cents bigint DEFAULT '0'::bigint NOT NULL,
    bank_transfer_discount_cents bigint DEFAULT '0'::bigint NOT NULL,
    vat_percentage integer DEFAULT 0 NOT NULL,
    vat_amount_cents bigint DEFAULT '0'::bigint NOT NULL,
    vat_mode character varying(16) DEFAULT 'ADDED'::character varying NOT NULL,
    credit_debit_transaction_id uuid,
    status character varying(16) DEFAULT 'AWAITING_PAYMENT'::character varying NOT NULL,
    payment_method character varying(16) DEFAULT 'BANK_TRANSFER'::character varying NOT NULL,
    stripe_checkout_session_id character varying(255),
    note character varying(1000),
    payment_proof_storage_key character varying(500),
    payment_proof_original_filename character varying(255),
    payment_proof_uploaded_at timestamp with time zone,
    paid_by_user_id uuid,
    paid_at timestamp with time zone,
    cancelled_by_user_id uuid,
    cancelled_at timestamp with time zone,
    cancellation_reason character varying(500),
    recipient_name character varying(128) NOT NULL,
    recipient_phone character varying(32),
    address_line1 character varying(255) NOT NULL,
    address_line2 character varying(255),
    city character varying(128) NOT NULL,
    province character varying(64) NOT NULL,
    postal_code character varying(16) NOT NULL,
    country_code character varying(2) DEFAULT 'IT'::character varying NOT NULL,
    shipping_days character varying(32),
    fulfillment_status character varying(16) DEFAULT 'NOT_SENT'::character varying NOT NULL,
    forwarded_at timestamp with time zone,
    forwarded_by_user_id uuid,
    forward_error character varying(500),
    tracking_number character varying(128),
    tracking_url character varying(1000),
    tracking_company character varying(128),
    shipped_at timestamp with time zone,
    delivered_at timestamp with time zone,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_sn_market_orders_credit_applied_non_negative CHECK ((credit_applied_cents >= 0)),
    CONSTRAINT ck_sn_market_orders_credit_applied_not_over_amount CHECK ((credit_applied_cents <= amount_cents)),
    CONSTRAINT ck_sn_market_orders_vat_mode CHECK (((vat_mode)::text = ANY ((ARRAY['INCLUDED'::character varying, 'ADDED'::character varying])::text[])))
);


--
-- Name: sn_market_producers; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_market_producers (
    organization_id uuid NOT NULL,
    name character varying(160) NOT NULL,
    description character varying(4000) DEFAULT ''::character varying NOT NULL,
    website_url character varying(1000),
    logo_url character varying(1000),
    vat_number character varying(32),
    email character varying(255),
    phone character varying(32),
    address character varying(500),
    active boolean DEFAULT true NOT NULL,
    created_by_user_id uuid NOT NULL,
    updated_at timestamp with time zone,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: sn_merchants; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_merchants (
    organization_id uuid NOT NULL,
    name character varying(255) NOT NULL,
    logo_url character varying(1000),
    is_active boolean DEFAULT true NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: sn_offer_versions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_offer_versions (
    product_id uuid NOT NULL,
    version_label character varying(32) NOT NULL,
    name character varying(255) NOT NULL,
    description character varying(2000) NOT NULL,
    image_url character varying(1000),
    base_price_cents bigint NOT NULL,
    initial_fee_cents bigint NOT NULL,
    recurring_fee_cents bigint NOT NULL,
    billing_period character varying(16) NOT NULL,
    contract_duration_months integer DEFAULT 12,
    tax_configuration jsonb NOT NULL,
    commission_plan_version_id uuid,
    commission_tokens jsonb DEFAULT '{}'::jsonb NOT NULL,
    required_documents jsonb NOT NULL,
    terms_version character varying(32) NOT NULL,
    valid_from timestamp with time zone NOT NULL,
    valid_to timestamp with time zone,
    status character varying(32) NOT NULL,
    credit_discount_percentage integer DEFAULT 0 NOT NULL,
    cashback_enabled boolean DEFAULT false NOT NULL,
    contract_cashback_percentage integer DEFAULT 0 NOT NULL,
    first_referrer_bonus_enabled boolean DEFAULT false NOT NULL,
    first_referrer_bonus_cents bigint DEFAULT '0'::bigint NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    margin_type character varying(16),
    margin_amount_cents bigint,
    margin_percentage numeric(7,4),
    CONSTRAINT ck_sn_offer_versions_margin_consistent CHECK (((margin_type IS NULL) OR (((margin_type)::text = 'FIXED'::text) AND (margin_amount_cents IS NOT NULL) AND (margin_amount_cents >= 0)) OR (((margin_type)::text = 'PERCENTAGE'::text) AND (margin_percentage IS NOT NULL) AND (margin_percentage >= (0)::numeric) AND (margin_percentage <= (100)::numeric))))
);


--
-- Name: sn_offers; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_offers (
    organization_id uuid NOT NULL,
    code character varying(64) NOT NULL,
    product_type character varying(32) DEFAULT 'ENERGY_CONTRACT'::character varying NOT NULL,
    energy_type character varying(16),
    customer_type character varying(32) NOT NULL,
    status character varying(32) NOT NULL,
    category character varying(16) DEFAULT 'INTERNAL'::character varying NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    commercial_category_id uuid,
    company_id uuid
);


--
-- Name: sn_one_time_codes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_one_time_codes (
    user_id uuid NOT NULL,
    purpose character varying(32) NOT NULL,
    code_hash character varying(64) NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    used_at timestamp with time zone,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: sn_password_recoveries; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_password_recoveries (
    user_id uuid NOT NULL,
    token_hash character varying(64) NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    used_at timestamp with time zone,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: sn_payout_adjustments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_payout_adjustments (
    organization_id uuid NOT NULL,
    original_movement_id uuid NOT NULL,
    new_movement_id uuid NOT NULL,
    reason character varying(500) NOT NULL,
    requested_by uuid NOT NULL,
    approved_by uuid,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: sn_payout_entries; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_payout_entries (
    organization_id uuid NOT NULL,
    agent_id uuid,
    contract_id uuid NOT NULL,
    origin_event_id uuid NOT NULL,
    calculation_id uuid NOT NULL,
    movement_type character varying(32) NOT NULL,
    amount_cents bigint NOT NULL,
    currency character varying(3) NOT NULL,
    status character varying(32) NOT NULL,
    effective_date date NOT NULL,
    scheduled_date date,
    paid_date date,
    rule_version_id character varying(32) NOT NULL,
    network_snapshot_id uuid NOT NULL,
    idempotency_key character varying(128) NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    beneficiary_kind character varying(8) DEFAULT 'AGENT'::character varying NOT NULL,
    split_plan_id uuid,
    plan_version integer,
    rule_id uuid,
    beneficiary_type character varying(24),
    network_level integer,
    role_code_snapshot character varying(32),
    calculation_type character varying(24),
    calculation_value numeric(12,4),
    reference_margin_cents bigint,
    source_seller_agent_id uuid,
    product_id uuid,
    fallback_applied character varying(16),
    snapshot jsonb DEFAULT '{}'::jsonb NOT NULL,
    approved_at timestamp with time zone,
    approved_by_user_id uuid,
    CONSTRAINT ck_sn_payout_entries_beneficiary_consistent CHECK (((((beneficiary_kind)::text = 'AGENT'::text) AND (agent_id IS NOT NULL)) OR (((beneficiary_kind)::text = 'COMPANY'::text) AND (agent_id IS NULL))))
);


--
-- Name: sn_payout_offsets; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_payout_offsets (
    organization_id uuid NOT NULL,
    debit_movement_id uuid NOT NULL,
    credit_movement_id uuid NOT NULL,
    reason character varying(500) NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: sn_payout_plans; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_payout_plans (
    organization_id uuid NOT NULL,
    version_label character varying(32) NOT NULL,
    valid_from timestamp with time zone NOT NULL,
    valid_to timestamp with time zone,
    status character varying(32) NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    name character varying(160),
    plan_key uuid,
    version integer DEFAULT 1 NOT NULL,
    product_id uuid,
    category_id uuid,
    seller_role_id uuid,
    fallback_strategy character varying(16) DEFAULT 'COMPANY'::character varying NOT NULL,
    distribution_mode character varying(8) DEFAULT 'FULL'::character varying NOT NULL,
    accrual_trigger character varying(16) DEFAULT 'PER_INSTALMENT'::character varying NOT NULL,
    notes character varying(2000) DEFAULT ''::character varying NOT NULL,
    created_by_user_id uuid,
    activated_by_user_id uuid,
    activated_at timestamp with time zone,
    retired_at timestamp with time zone,
    updated_at timestamp with time zone,
    CONSTRAINT ck_sn_payout_plans_one_scope CHECK ((((status)::text = 'LEGACY'::text) OR ((product_id IS NULL) <> (category_id IS NULL)))),
    CONSTRAINT ck_sn_payout_plans_valid_range CHECK (((valid_to IS NULL) OR (valid_to > valid_from)))
);


--
-- Name: sn_payout_reversals; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_payout_reversals (
    organization_id uuid NOT NULL,
    original_movement_id uuid NOT NULL,
    new_movement_id uuid NOT NULL,
    reason character varying(500) NOT NULL,
    requested_by uuid,
    approved_by uuid,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: sn_payout_rules; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_payout_rules (
    commission_plan_version_id uuid NOT NULL,
    rule_type character varying(64) NOT NULL,
    parameters jsonb NOT NULL,
    valid_from timestamp with time zone,
    valid_to timestamp with time zone,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    sequence integer DEFAULT 0 NOT NULL,
    label character varying(120),
    beneficiary_type character varying(24),
    network_level integer,
    required_role_id uuid,
    calculation_type character varying(24),
    percentage numeric(7,4),
    amount_cents bigint,
    min_amount_cents bigint,
    max_amount_cents bigint,
    fallback_strategy character varying(16),
    CONSTRAINT ck_sn_payout_rules_amount_non_negative CHECK (((amount_cents IS NULL) OR (amount_cents >= 0))),
    CONSTRAINT ck_sn_payout_rules_level_positive CHECK (((network_level IS NULL) OR (network_level >= 1))),
    CONSTRAINT ck_sn_payout_rules_max_non_negative CHECK (((max_amount_cents IS NULL) OR (max_amount_cents >= 0))),
    CONSTRAINT ck_sn_payout_rules_min_non_negative CHECK (((min_amount_cents IS NULL) OR (min_amount_cents >= 0))),
    CONSTRAINT ck_sn_payout_rules_percentage_range CHECK (((percentage IS NULL) OR ((percentage >= (0)::numeric) AND (percentage <= (100)::numeric))))
);


--
-- Name: sn_payout_run_steps; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_payout_run_steps (
    calculation_id uuid NOT NULL,
    step_order integer NOT NULL,
    beneficiary_agent_id uuid,
    rank_at_calculation character varying(32),
    base_amount_cents bigint NOT NULL,
    already_distributed_cents bigint NOT NULL,
    entrepreneurial_difference_cents bigint NOT NULL,
    personal_bonus_cents bigint NOT NULL,
    gross_amount_cents bigint NOT NULL,
    movement_type character varying(32) NOT NULL,
    explanation character varying(1000) NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    rule_id uuid
);


--
-- Name: sn_payout_runs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_payout_runs (
    organization_id uuid NOT NULL,
    contract_id uuid NOT NULL,
    network_snapshot_id uuid NOT NULL,
    commission_plan_version_id uuid,
    trigger_event_id uuid NOT NULL,
    input_snapshot jsonb NOT NULL,
    output_snapshot jsonb NOT NULL,
    checksum character varying(64) NOT NULL,
    status character varying(32) NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    reference_margin_cents bigint
);


--
-- Name: sn_permissions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_permissions (
    code character varying(64) NOT NULL,
    description character varying(255) NOT NULL,
    id uuid NOT NULL
);


--
-- Name: sn_postal_addresses; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_postal_addresses (
    organization_id uuid NOT NULL,
    customer_id uuid NOT NULL,
    kind character varying(32) NOT NULL,
    street character varying(255) NOT NULL,
    city character varying(128) NOT NULL,
    province character varying(8) NOT NULL,
    postal_code character varying(16) NOT NULL,
    country character varying(2) NOT NULL,
    id uuid NOT NULL
);


--
-- Name: sn_product_categories; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_product_categories (
    organization_id uuid NOT NULL,
    code character varying(32) NOT NULL,
    name character varying(120) NOT NULL,
    requires_supply_point boolean NOT NULL,
    is_active boolean NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: sn_promoter_level_log; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_promoter_level_log (
    organization_id uuid NOT NULL,
    agent_id uuid NOT NULL,
    rank_id uuid NOT NULL,
    effective_from timestamp with time zone NOT NULL,
    effective_to timestamp with time zone,
    calculation_source character varying(32) NOT NULL,
    rule_version_id character varying(32) NOT NULL,
    approved_by uuid,
    reason character varying(500),
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: sn_promoter_profiles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_promoter_profiles (
    organization_id uuid NOT NULL,
    user_id uuid,
    display_name character varying(255) NOT NULL,
    first_name character varying(120),
    last_name character varying(120),
    promoter_code character varying(32) NOT NULL,
    status character varying(32) NOT NULL,
    photo_url character varying(1000),
    joined_at timestamp with time zone NOT NULL,
    current_rank_id uuid,
    approved_by_user_id uuid,
    approved_at timestamp with time zone,
    rejection_reason character varying(500),
    is_blacklisted boolean DEFAULT false NOT NULL,
    collaboration_contract_version character varying(32),
    collaboration_accepted_documents jsonb DEFAULT '{}'::jsonb NOT NULL,
    collaboration_accepted_at timestamp with time zone,
    collaboration_otp_verified_at timestamp with time zone,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    current_commercial_role_id uuid
);


--
-- Name: sn_receipt_claims; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_receipt_claims (
    organization_id uuid NOT NULL,
    customer_user_id uuid NOT NULL,
    partner_id uuid NOT NULL,
    storage_key character varying(500) NOT NULL,
    original_filename character varying(255) NOT NULL,
    content_type character varying(100) NOT NULL,
    size_bytes bigint NOT NULL,
    declared_amount_cents bigint NOT NULL,
    confirmed_amount_cents bigint,
    payment_reference_code character varying(32),
    status character varying(16) DEFAULT 'SUBMITTED'::character varying NOT NULL,
    rejection_reason character varying(500),
    payment_method character varying(16),
    stripe_checkout_session_id character varying(255),
    payment_proof_storage_key character varying(500),
    payment_proof_original_filename character varying(255),
    payment_proof_uploaded_at timestamp with time zone,
    verified_by_user_id uuid,
    verified_at timestamp with time zone,
    credited_by_user_id uuid,
    credited_at timestamp with time zone,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_sn_receipt_claims_confirmed_amount_positive CHECK (((confirmed_amount_cents IS NULL) OR (confirmed_amount_cents > 0)))
);


--
-- Name: sn_role_grants; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_role_grants (
    role_id uuid NOT NULL,
    permission_id uuid NOT NULL
);


--
-- Name: sn_roles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_roles (
    organization_id uuid,
    code character varying(64) NOT NULL,
    name character varying(128) NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: sn_seller_role_history; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_seller_role_history (
    organization_id uuid NOT NULL,
    agent_id uuid NOT NULL,
    role_id uuid NOT NULL,
    valid_from timestamp with time zone NOT NULL,
    valid_to timestamp with time zone,
    reason character varying(500),
    changed_by_user_id uuid,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: sn_shop_orders; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_shop_orders (
    organization_id uuid NOT NULL,
    customer_user_id uuid NOT NULL,
    product_version_id uuid NOT NULL,
    created_by_user_id uuid NOT NULL,
    amount_cents bigint NOT NULL,
    credit_applied_cents bigint DEFAULT '0'::bigint NOT NULL,
    credit_debit_transaction_id uuid,
    cashback_requested boolean DEFAULT false NOT NULL,
    cashback_surcharge_cents bigint DEFAULT '0'::bigint NOT NULL,
    cashback_credited_at timestamp with time zone,
    status character varying(16) DEFAULT 'AWAITING_PAYMENT'::character varying NOT NULL,
    payment_method character varying(16) DEFAULT 'BANK_TRANSFER'::character varying NOT NULL,
    stripe_checkout_session_id character varying(255),
    note character varying(1000),
    payment_proof_storage_key character varying(500),
    payment_proof_original_filename character varying(255),
    payment_proof_uploaded_at timestamp with time zone,
    paid_by_user_id uuid,
    paid_at timestamp with time zone,
    cancelled_by_user_id uuid,
    cancelled_at timestamp with time zone,
    cancellation_reason character varying(500),
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_sn_shop_orders_credit_applied_non_negative CHECK ((credit_applied_cents >= 0)),
    CONSTRAINT ck_sn_shop_orders_credit_applied_not_over_amount CHECK ((credit_applied_cents <= amount_cents))
);


--
-- Name: sn_shopify_config; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_shopify_config (
    organization_id uuid NOT NULL,
    shop_domain character varying(255),
    access_token character varying(255),
    client_id character varying(255),
    client_secret character varying(255),
    token_expires_at timestamp with time zone,
    api_version character varying(16) DEFAULT '2025-07'::character varying NOT NULL,
    enabled boolean DEFAULT false NOT NULL,
    shop_name character varying(255),
    shop_currency character varying(3),
    currency_rate numeric(10,6) DEFAULT '1'::numeric NOT NULL,
    price_basis character varying(8) DEFAULT 'COST'::character varying NOT NULL,
    markup_percentage integer DEFAULT 100 NOT NULL,
    markup_fixed_cents integer DEFAULT 0 NOT NULL,
    price_rounding character varying(8) DEFAULT '90'::character varying NOT NULL,
    shipping_mode character varying(16) DEFAULT 'CUSTOMER_PAYS'::character varying NOT NULL,
    shipping_flat_cents integer DEFAULT 590 NOT NULL,
    shipping_days character varying(32) DEFAULT '7-15'::character varying,
    default_credit_percentage integer DEFAULT 30 NOT NULL,
    auto_forward boolean DEFAULT true NOT NULL,
    last_connected_at timestamp with time zone,
    updated_at timestamp with time zone,
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: sn_shopify_item_variants; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_shopify_item_variants (
    product_id uuid NOT NULL,
    shopify_variant_id character varying(128) NOT NULL,
    sku character varying(128),
    label character varying(255) DEFAULT ''::character varying NOT NULL,
    image_url character varying(1000),
    cost_amount numeric(12,2),
    source_price_amount numeric(12,2) NOT NULL,
    price_cents bigint NOT NULL,
    price_override_cents bigint,
    inventory integer,
    active boolean DEFAULT true NOT NULL,
    available_in_store boolean DEFAULT true NOT NULL,
    last_synced_at timestamp with time zone,
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: sn_shopify_items; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_shopify_items (
    organization_id uuid NOT NULL,
    shopify_product_id character varying(128) NOT NULL,
    handle character varying(255),
    name character varying(255) NOT NULL,
    source_title character varying(500),
    vendor character varying(255),
    description character varying(8000) DEFAULT ''::character varying NOT NULL,
    image_url character varying(1000),
    images jsonb DEFAULT '[]'::jsonb NOT NULL,
    status character varying(16) DEFAULT 'ACTIVE'::character varying NOT NULL,
    credit_discount_percentage integer DEFAULT 30 NOT NULL,
    markup_percentage integer,
    last_synced_at timestamp with time zone,
    sync_error character varying(500),
    created_by_user_id uuid NOT NULL,
    updated_at timestamp with time zone,
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_sn_shopify_items_credit_discount_percentage_below_100 CHECK (((credit_discount_percentage >= 0) AND (credit_discount_percentage <= 99)))
);


--
-- Name: sn_shopify_order_lines; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_shopify_order_lines (
    order_id uuid NOT NULL,
    product_id uuid NOT NULL,
    variant_id uuid NOT NULL,
    quantity integer NOT NULL,
    unit_price_cents bigint NOT NULL,
    product_name character varying(255) NOT NULL,
    variant_label character varying(255),
    credit_discount_percentage integer DEFAULT 0 NOT NULL,
    supplier_order_id character varying(128),
    tracking_number character varying(128),
    tracking_url character varying(1000),
    tracking_company character varying(128),
    unit_cost_amount numeric(12,2),
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_sn_shopify_order_lines_quantity_positive CHECK ((quantity > 0))
);


--
-- Name: sn_shopify_orders; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_shopify_orders (
    organization_id uuid NOT NULL,
    customer_user_id uuid NOT NULL,
    shopify_product_id uuid NOT NULL,
    shopify_variant_id uuid NOT NULL,
    created_by_user_id uuid NOT NULL,
    number bigint DEFAULT nextval('public.sn_order_number_seq'::regclass) NOT NULL,
    quantity integer DEFAULT 1 NOT NULL,
    unit_price_cents bigint NOT NULL,
    shipping_cents bigint DEFAULT '0'::bigint NOT NULL,
    amount_cents bigint NOT NULL,
    credit_applied_cents bigint DEFAULT '0'::bigint NOT NULL,
    bank_transfer_discount_cents bigint DEFAULT '0'::bigint NOT NULL,
    vat_percentage integer DEFAULT 0 NOT NULL,
    vat_amount_cents bigint DEFAULT '0'::bigint NOT NULL,
    vat_mode character varying(16) DEFAULT 'ADDED'::character varying NOT NULL,
    credit_debit_transaction_id uuid,
    status character varying(16) DEFAULT 'AWAITING_PAYMENT'::character varying NOT NULL,
    payment_method character varying(16) DEFAULT 'BANK_TRANSFER'::character varying NOT NULL,
    stripe_checkout_session_id character varying(255),
    note character varying(1000),
    payment_proof_storage_key character varying(500),
    payment_proof_original_filename character varying(255),
    payment_proof_uploaded_at timestamp with time zone,
    paid_by_user_id uuid,
    paid_at timestamp with time zone,
    cancelled_by_user_id uuid,
    cancelled_at timestamp with time zone,
    cancellation_reason character varying(500),
    recipient_name character varying(128) NOT NULL,
    recipient_phone character varying(32),
    address_line1 character varying(255) NOT NULL,
    address_line2 character varying(255),
    city character varying(128) NOT NULL,
    province character varying(64) NOT NULL,
    postal_code character varying(16) NOT NULL,
    country_code character varying(2) DEFAULT 'IT'::character varying NOT NULL,
    shipping_days character varying(32),
    unit_cost_amount numeric(12,2),
    currency_rate numeric(10,6) DEFAULT '1'::numeric NOT NULL,
    fulfillment_status character varying(16) DEFAULT 'NOT_SENT'::character varying NOT NULL,
    shopify_draft_order_id character varying(128),
    shopify_order_id character varying(128),
    shopify_order_name character varying(64),
    shopify_fulfillment_status character varying(32),
    forwarded_at timestamp with time zone,
    forwarded_by_user_id uuid,
    forward_error character varying(500),
    tracking_number character varying(128),
    tracking_url character varying(1000),
    tracking_company character varying(128),
    shipped_at timestamp with time zone,
    delivered_at timestamp with time zone,
    last_sync_at timestamp with time zone,
    attempt_count integer DEFAULT 0 NOT NULL,
    last_attempt_at timestamp with time zone,
    next_retry_at timestamp with time zone,
    last_error_kind character varying(24),
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_sn_shopify_orders_credit_applied_non_negative CHECK ((credit_applied_cents >= 0)),
    CONSTRAINT ck_sn_shopify_orders_credit_applied_not_over_amount CHECK ((credit_applied_cents <= amount_cents)),
    CONSTRAINT ck_sn_shopify_orders_quantity_positive CHECK ((quantity > 0)),
    CONSTRAINT ck_sn_shopify_orders_vat_mode CHECK (((vat_mode)::text = ANY ((ARRAY['INCLUDED'::character varying, 'ADDED'::character varying])::text[])))
);


--
-- Name: sn_stored_files; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_stored_files (
    organization_id uuid NOT NULL,
    contract_id uuid,
    contract_request_id uuid,
    document_type character varying(32) NOT NULL,
    description character varying(120),
    original_filename character varying(255) NOT NULL,
    storage_key character varying(500) NOT NULL,
    content_type character varying(100) NOT NULL,
    size_bytes bigint NOT NULL,
    uploaded_by_user_id uuid NOT NULL,
    uploaded_by_role character varying(32) NOT NULL,
    status character varying(32) NOT NULL,
    reviewed_by_user_id uuid,
    reviewed_at timestamp with time zone,
    review_note character varying(1000),
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_sn_stored_files_one_owner CHECK ((num_nonnulls(contract_id, contract_request_id) = 1))
);


--
-- Name: sn_stripe_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_stripe_events (
    organization_id uuid NOT NULL,
    stripe_event_id character varying(255) NOT NULL,
    event_type character varying(64) NOT NULL,
    processed_at timestamp with time zone,
    outcome character varying(255),
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: sn_supplier_item_orders; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_supplier_item_orders (
    organization_id uuid NOT NULL,
    customer_user_id uuid NOT NULL,
    imported_product_id uuid NOT NULL,
    created_by_user_id uuid NOT NULL,
    number bigint DEFAULT nextval('public.sn_order_number_seq'::regclass) NOT NULL,
    amount_cents bigint NOT NULL,
    credit_applied_cents bigint DEFAULT '0'::bigint NOT NULL,
    bank_transfer_discount_cents bigint DEFAULT '0'::bigint NOT NULL,
    vat_percentage integer DEFAULT 0 NOT NULL,
    vat_amount_cents bigint DEFAULT '0'::bigint NOT NULL,
    vat_mode character varying(16) DEFAULT 'ADDED'::character varying NOT NULL,
    credit_debit_transaction_id uuid,
    status character varying(16) DEFAULT 'AWAITING_PAYMENT'::character varying NOT NULL,
    payment_method character varying(16) DEFAULT 'BANK_TRANSFER'::character varying NOT NULL,
    stripe_checkout_session_id character varying(255),
    note character varying(1000),
    payment_proof_storage_key character varying(500),
    payment_proof_original_filename character varying(255),
    payment_proof_uploaded_at timestamp with time zone,
    paid_by_user_id uuid,
    paid_at timestamp with time zone,
    cancelled_by_user_id uuid,
    cancelled_at timestamp with time zone,
    cancellation_reason character varying(500),
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_sn_supplier_item_orders_credit_applied_non_negative CHECK ((credit_applied_cents >= 0)),
    CONSTRAINT ck_sn_supplier_item_orders_credit_applied_not_over_amount CHECK ((credit_applied_cents <= amount_cents)),
    CONSTRAINT ck_sn_supplier_item_orders_vat_mode CHECK (((vat_mode)::text = ANY ((ARRAY['INCLUDED'::character varying, 'ADDED'::character varying])::text[])))
);


--
-- Name: sn_supplier_items; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_supplier_items (
    organization_id uuid NOT NULL,
    provider_id uuid NOT NULL,
    external_id character varying(255),
    external_url character varying(1000),
    name character varying(255) NOT NULL,
    description character varying(2000) DEFAULT ''::character varying NOT NULL,
    image_url character varying(1000),
    price_cents bigint NOT NULL,
    credit_discount_percentage integer DEFAULT 0 NOT NULL,
    status character varying(16) DEFAULT 'ACTIVE'::character varying NOT NULL,
    created_by_user_id uuid NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_sn_supplier_items_credit_below_100 CHECK (((credit_discount_percentage >= 0) AND (credit_discount_percentage <= 99)))
);


--
-- Name: sn_supplier_members; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_supplier_members (
    organization_id uuid NOT NULL,
    company_id uuid NOT NULL,
    agent_id uuid NOT NULL,
    joined_at timestamp with time zone NOT NULL,
    left_at timestamp with time zone,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: sn_supplier_sources; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_supplier_sources (
    organization_id uuid NOT NULL,
    provider_type character varying(32) NOT NULL,
    name character varying(128) NOT NULL,
    base_url character varying(500),
    api_key character varying(500),
    enabled boolean DEFAULT true NOT NULL,
    created_by_user_id uuid NOT NULL,
    app_key character varying(64),
    app_secret character varying(255),
    access_token character varying(500),
    refresh_token character varying(500),
    token_expires_at timestamp with time zone,
    account_label character varying(255),
    last_connected_at timestamp with time zone,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: sn_suppliers; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_suppliers (
    organization_id uuid NOT NULL,
    name character varying(160) NOT NULL,
    description character varying(2000) NOT NULL,
    logo_url character varying(1000),
    website_url character varying(1000),
    max_network_depth integer,
    is_active boolean NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_sn_suppliers_depth_positive CHECK (((max_network_depth IS NULL) OR (max_network_depth >= 1)))
);


--
-- Name: sn_support_cases; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_support_cases (
    organization_id uuid NOT NULL,
    opened_by_user_id uuid NOT NULL,
    opened_by_role character varying(32) NOT NULL,
    subject character varying(255) NOT NULL,
    category character varying(32) NOT NULL,
    status character varying(16) NOT NULL,
    contract_id uuid,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: sn_support_replies; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_support_replies (
    ticket_id uuid NOT NULL,
    author_user_id uuid NOT NULL,
    author_role character varying(32) NOT NULL,
    body text NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: sn_tenants; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_tenants (
    name character varying(255) NOT NULL,
    legal_name character varying(255),
    vat_number character varying(32),
    status character varying(32) NOT NULL,
    settings jsonb NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: sn_tree_links; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_tree_links (
    organization_id uuid NOT NULL,
    parent_agent_id uuid NOT NULL,
    child_agent_id uuid NOT NULL,
    effective_from timestamp with time zone NOT NULL,
    effective_to timestamp with time zone,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: sn_tree_moves; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_tree_moves (
    organization_id uuid NOT NULL,
    agent_id uuid NOT NULL,
    old_parent_agent_id uuid,
    new_parent_agent_id uuid,
    requested_by uuid NOT NULL,
    approved_by uuid,
    reason character varying(500) NOT NULL,
    effective_at timestamp with time zone NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: sn_tree_nodes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_tree_nodes (
    organization_id uuid NOT NULL,
    agent_id uuid NOT NULL,
    direct_parent_agent_id uuid,
    status character varying(32) NOT NULL,
    effective_from timestamp with time zone NOT NULL,
    effective_to timestamp with time zone,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: sn_tree_paths; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_tree_paths (
    organization_id uuid NOT NULL,
    ancestor_agent_id uuid NOT NULL,
    descendant_agent_id uuid NOT NULL,
    effective_from timestamp with time zone NOT NULL,
    depth integer NOT NULL,
    effective_to timestamp with time zone
);


--
-- Name: sn_tree_snapshot_nodes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_tree_snapshot_nodes (
    snapshot_id uuid NOT NULL,
    ancestor_agent_id uuid NOT NULL,
    depth integer NOT NULL,
    rank_id_at_snapshot uuid,
    commercial_role_id uuid,
    role_code character varying(32),
    agent_status character varying(32)
);


--
-- Name: sn_tree_snapshots; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_tree_snapshots (
    organization_id uuid NOT NULL,
    reason character varying(64) NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    as_of timestamp with time zone
);


--
-- Name: sn_utility_points; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sn_utility_points (
    organization_id uuid NOT NULL,
    customer_id uuid NOT NULL,
    label character varying(255),
    energy_type character varying(16),
    pod_code character varying(32),
    pdr_code character varying(32),
    meter_number character varying(64),
    supply_address_id uuid NOT NULL,
    estimated_consumption bigint,
    actual_consumption bigint,
    provider_reference character varying(128),
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: alembic_version alembic_version_pkc; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);


--
-- Name: sn_payout_plans ex_sn_payout_plans_no_overlap; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_payout_plans
    ADD CONSTRAINT ex_sn_payout_plans_no_overlap EXCLUDE USING gist (organization_id WITH =, seller_role_id WITH =, COALESCE(product_id, category_id) WITH =, tstzrange(valid_from, valid_to) WITH &&) WHERE (((status)::text = 'ACTIVE'::text));


--
-- Name: sn_seller_role_history ex_sn_seller_role_history_no_overlap; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_seller_role_history
    ADD CONSTRAINT ex_sn_seller_role_history_no_overlap EXCLUDE USING gist (agent_id WITH =, tstzrange(valid_from, valid_to) WITH &&);


--
-- Name: sn_account_roles pk_sn_account_roles; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_account_roles
    ADD CONSTRAINT pk_sn_account_roles PRIMARY KEY (id);


--
-- Name: sn_accounts pk_sn_accounts; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_accounts
    ADD CONSTRAINT pk_sn_accounts PRIMARY KEY (id);


--
-- Name: sn_activity_log pk_sn_activity_log; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_activity_log
    ADD CONSTRAINT pk_sn_activity_log PRIMARY KEY (id);


--
-- Name: sn_aff_clients pk_sn_aff_clients; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_aff_clients
    ADD CONSTRAINT pk_sn_aff_clients PRIMARY KEY (id);


--
-- Name: sn_aff_commissions pk_sn_aff_commissions; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_aff_commissions
    ADD CONSTRAINT pk_sn_aff_commissions PRIMARY KEY (id);


--
-- Name: sn_aff_licenses pk_sn_aff_licenses; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_aff_licenses
    ADD CONSTRAINT pk_sn_aff_licenses PRIMARY KEY (id);


--
-- Name: sn_aff_monthly_results pk_sn_aff_monthly_results; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_aff_monthly_results
    ADD CONSTRAINT pk_sn_aff_monthly_results PRIMARY KEY (id);


--
-- Name: sn_aff_operations pk_sn_aff_operations; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_aff_operations
    ADD CONSTRAINT pk_sn_aff_operations PRIMARY KEY (id);


--
-- Name: sn_aff_period_closes pk_sn_aff_period_closes; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_aff_period_closes
    ADD CONSTRAINT pk_sn_aff_period_closes PRIMARY KEY (id);


--
-- Name: sn_aff_plan_versions pk_sn_aff_plan_versions; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_aff_plan_versions
    ADD CONSTRAINT pk_sn_aff_plan_versions PRIMARY KEY (id);


--
-- Name: sn_aff_points pk_sn_aff_points; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_aff_points
    ADD CONSTRAINT pk_sn_aff_points PRIMARY KEY (id);


--
-- Name: sn_aff_subscriptions pk_sn_aff_subscriptions; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_aff_subscriptions
    ADD CONSTRAINT pk_sn_aff_subscriptions PRIMARY KEY (id);


--
-- Name: sn_agreement_attributions pk_sn_agreement_attributions; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_agreement_attributions
    ADD CONSTRAINT pk_sn_agreement_attributions PRIMARY KEY (id);


--
-- Name: sn_agreement_checkouts pk_sn_agreement_checkouts; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_agreement_checkouts
    ADD CONSTRAINT pk_sn_agreement_checkouts PRIMARY KEY (id);


--
-- Name: sn_agreement_events pk_sn_agreement_events; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_agreement_events
    ADD CONSTRAINT pk_sn_agreement_events PRIMARY KEY (id);


--
-- Name: sn_agreement_instalments pk_sn_agreement_instalments; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_agreement_instalments
    ADD CONSTRAINT pk_sn_agreement_instalments PRIMARY KEY (id);


--
-- Name: sn_agreement_payout_plans pk_sn_agreement_payout_plans; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_agreement_payout_plans
    ADD CONSTRAINT pk_sn_agreement_payout_plans PRIMARY KEY (id);


--
-- Name: sn_agreement_requests pk_sn_agreement_requests; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_agreement_requests
    ADD CONSTRAINT pk_sn_agreement_requests PRIMARY KEY (id);


--
-- Name: sn_agreement_status_log pk_sn_agreement_status_log; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_agreement_status_log
    ADD CONSTRAINT pk_sn_agreement_status_log PRIMARY KEY (id);


--
-- Name: sn_agreements pk_sn_agreements; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_agreements
    ADD CONSTRAINT pk_sn_agreements PRIMARY KEY (id);


--
-- Name: sn_aliexpress_config pk_sn_aliexpress_config; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_aliexpress_config
    ADD CONSTRAINT pk_sn_aliexpress_config PRIMARY KEY (id);


--
-- Name: sn_aliexpress_item_variants pk_sn_aliexpress_item_variants; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_aliexpress_item_variants
    ADD CONSTRAINT pk_sn_aliexpress_item_variants PRIMARY KEY (id);


--
-- Name: sn_aliexpress_items pk_sn_aliexpress_items; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_aliexpress_items
    ADD CONSTRAINT pk_sn_aliexpress_items PRIMARY KEY (id);


--
-- Name: sn_aliexpress_order_lines pk_sn_aliexpress_order_lines; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_aliexpress_order_lines
    ADD CONSTRAINT pk_sn_aliexpress_order_lines PRIMARY KEY (id);


--
-- Name: sn_aliexpress_orders pk_sn_aliexpress_orders; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_aliexpress_orders
    ADD CONSTRAINT pk_sn_aliexpress_orders PRIMARY KEY (id);


--
-- Name: sn_attribution_fixes pk_sn_attribution_fixes; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_attribution_fixes
    ADD CONSTRAINT pk_sn_attribution_fixes PRIMARY KEY (id);


--
-- Name: sn_basket_lines pk_sn_basket_lines; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_basket_lines
    ADD CONSTRAINT pk_sn_basket_lines PRIMARY KEY (id);


--
-- Name: sn_baskets pk_sn_baskets; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_baskets
    ADD CONSTRAINT pk_sn_baskets PRIMARY KEY (id);


--
-- Name: sn_businesses pk_sn_businesses; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_businesses
    ADD CONSTRAINT pk_sn_businesses PRIMARY KEY (customer_id);


--
-- Name: sn_career_levels pk_sn_career_levels; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_career_levels
    ADD CONSTRAINT pk_sn_career_levels PRIMARY KEY (id);


--
-- Name: sn_catalog_section_items pk_sn_catalog_section_items; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_catalog_section_items
    ADD CONSTRAINT pk_sn_catalog_section_items PRIMARY KEY (id);


--
-- Name: sn_catalog_sections pk_sn_catalog_sections; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_catalog_sections
    ADD CONSTRAINT pk_sn_catalog_sections PRIMARY KEY (id);


--
-- Name: sn_cj_config pk_sn_cj_config; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_cj_config
    ADD CONSTRAINT pk_sn_cj_config PRIMARY KEY (id);


--
-- Name: sn_cj_item_variants pk_sn_cj_item_variants; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_cj_item_variants
    ADD CONSTRAINT pk_sn_cj_item_variants PRIMARY KEY (id);


--
-- Name: sn_cj_items pk_sn_cj_items; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_cj_items
    ADD CONSTRAINT pk_sn_cj_items PRIMARY KEY (id);


--
-- Name: sn_cj_order_lines pk_sn_cj_order_lines; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_cj_order_lines
    ADD CONSTRAINT pk_sn_cj_order_lines PRIMARY KEY (id);


--
-- Name: sn_cj_orders pk_sn_cj_orders; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_cj_orders
    ADD CONSTRAINT pk_sn_cj_orders PRIMARY KEY (id);


--
-- Name: sn_client_attributions pk_sn_client_attributions; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_client_attributions
    ADD CONSTRAINT pk_sn_client_attributions PRIMARY KEY (id);


--
-- Name: sn_client_profiles pk_sn_client_profiles; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_client_profiles
    ADD CONSTRAINT pk_sn_client_profiles PRIMARY KEY (customer_id);


--
-- Name: sn_clients pk_sn_clients; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_clients
    ADD CONSTRAINT pk_sn_clients PRIMARY KEY (id);


--
-- Name: sn_commercial_roles pk_sn_commercial_roles; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_commercial_roles
    ADD CONSTRAINT pk_sn_commercial_roles PRIMARY KEY (id);


--
-- Name: sn_credit_accounts pk_sn_credit_accounts; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_credit_accounts
    ADD CONSTRAINT pk_sn_credit_accounts PRIMARY KEY (id);


--
-- Name: sn_credit_ledger pk_sn_credit_ledger; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_credit_ledger
    ADD CONSTRAINT pk_sn_credit_ledger PRIMARY KEY (id);


--
-- Name: sn_delegations pk_sn_delegations; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_delegations
    ADD CONSTRAINT pk_sn_delegations PRIMARY KEY (id);


--
-- Name: sn_email_confirmations pk_sn_email_confirmations; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_email_confirmations
    ADD CONSTRAINT pk_sn_email_confirmations PRIMARY KEY (id);


--
-- Name: sn_event_outbox pk_sn_event_outbox; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_event_outbox
    ADD CONSTRAINT pk_sn_event_outbox PRIMARY KEY (id);


--
-- Name: sn_friend_invite_codes pk_sn_friend_invite_codes; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_friend_invite_codes
    ADD CONSTRAINT pk_sn_friend_invite_codes PRIMARY KEY (id);


--
-- Name: sn_friend_invite_rewards pk_sn_friend_invite_rewards; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_friend_invite_rewards
    ADD CONSTRAINT pk_sn_friend_invite_rewards PRIMARY KEY (id);


--
-- Name: sn_friend_invites pk_sn_friend_invites; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_friend_invites
    ADD CONSTRAINT pk_sn_friend_invites PRIMARY KEY (id);


--
-- Name: sn_inbox_messages pk_sn_inbox_messages; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_inbox_messages
    ADD CONSTRAINT pk_sn_inbox_messages PRIMARY KEY (id);


--
-- Name: sn_invite_codes pk_sn_invite_codes; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_invite_codes
    ADD CONSTRAINT pk_sn_invite_codes PRIMARY KEY (id);


--
-- Name: sn_invite_events pk_sn_invite_events; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_invite_events
    ADD CONSTRAINT pk_sn_invite_events PRIMARY KEY (id);


--
-- Name: sn_invite_visits pk_sn_invite_visits; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_invite_visits
    ADD CONSTRAINT pk_sn_invite_visits PRIMARY KEY (id);


--
-- Name: sn_knowledge_articles pk_sn_knowledge_articles; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_knowledge_articles
    ADD CONSTRAINT pk_sn_knowledge_articles PRIMARY KEY (id);


--
-- Name: sn_leads pk_sn_leads; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_leads
    ADD CONSTRAINT pk_sn_leads PRIMARY KEY (id);


--
-- Name: sn_login_sessions pk_sn_login_sessions; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_login_sessions
    ADD CONSTRAINT pk_sn_login_sessions PRIMARY KEY (id);


--
-- Name: sn_mamify_config pk_sn_mamify_config; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_mamify_config
    ADD CONSTRAINT pk_sn_mamify_config PRIMARY KEY (id);


--
-- Name: sn_mamify_members pk_sn_mamify_members; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_mamify_members
    ADD CONSTRAINT pk_sn_mamify_members PRIMARY KEY (id);


--
-- Name: sn_mamify_orders pk_sn_mamify_orders; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_mamify_orders
    ADD CONSTRAINT pk_sn_mamify_orders PRIMARY KEY (id);


--
-- Name: sn_mamify_payouts pk_sn_mamify_payouts; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_mamify_payouts
    ADD CONSTRAINT pk_sn_mamify_payouts PRIMARY KEY (id);


--
-- Name: sn_mamify_products pk_sn_mamify_products; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_mamify_products
    ADD CONSTRAINT pk_sn_mamify_products PRIMARY KEY (id);


--
-- Name: sn_mamify_webhook_events pk_sn_mamify_webhook_events; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_mamify_webhook_events
    ADD CONSTRAINT pk_sn_mamify_webhook_events PRIMARY KEY (id);


--
-- Name: sn_market_config pk_sn_market_config; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_market_config
    ADD CONSTRAINT pk_sn_market_config PRIMARY KEY (id);


--
-- Name: sn_market_item_variants pk_sn_market_item_variants; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_market_item_variants
    ADD CONSTRAINT pk_sn_market_item_variants PRIMARY KEY (id);


--
-- Name: sn_market_items pk_sn_market_items; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_market_items
    ADD CONSTRAINT pk_sn_market_items PRIMARY KEY (id);


--
-- Name: sn_market_order_lines pk_sn_market_order_lines; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_market_order_lines
    ADD CONSTRAINT pk_sn_market_order_lines PRIMARY KEY (id);


--
-- Name: sn_market_orders pk_sn_market_orders; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_market_orders
    ADD CONSTRAINT pk_sn_market_orders PRIMARY KEY (id);


--
-- Name: sn_market_producers pk_sn_market_producers; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_market_producers
    ADD CONSTRAINT pk_sn_market_producers PRIMARY KEY (id);


--
-- Name: sn_merchants pk_sn_merchants; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_merchants
    ADD CONSTRAINT pk_sn_merchants PRIMARY KEY (id);


--
-- Name: sn_offer_versions pk_sn_offer_versions; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_offer_versions
    ADD CONSTRAINT pk_sn_offer_versions PRIMARY KEY (id);


--
-- Name: sn_offers pk_sn_offers; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_offers
    ADD CONSTRAINT pk_sn_offers PRIMARY KEY (id);


--
-- Name: sn_one_time_codes pk_sn_one_time_codes; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_one_time_codes
    ADD CONSTRAINT pk_sn_one_time_codes PRIMARY KEY (id);


--
-- Name: sn_password_recoveries pk_sn_password_recoveries; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_password_recoveries
    ADD CONSTRAINT pk_sn_password_recoveries PRIMARY KEY (id);


--
-- Name: sn_payout_adjustments pk_sn_payout_adjustments; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_payout_adjustments
    ADD CONSTRAINT pk_sn_payout_adjustments PRIMARY KEY (id);


--
-- Name: sn_payout_entries pk_sn_payout_entries; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_payout_entries
    ADD CONSTRAINT pk_sn_payout_entries PRIMARY KEY (id);


--
-- Name: sn_payout_offsets pk_sn_payout_offsets; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_payout_offsets
    ADD CONSTRAINT pk_sn_payout_offsets PRIMARY KEY (id);


--
-- Name: sn_payout_plans pk_sn_payout_plans; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_payout_plans
    ADD CONSTRAINT pk_sn_payout_plans PRIMARY KEY (id);


--
-- Name: sn_payout_reversals pk_sn_payout_reversals; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_payout_reversals
    ADD CONSTRAINT pk_sn_payout_reversals PRIMARY KEY (id);


--
-- Name: sn_payout_rules pk_sn_payout_rules; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_payout_rules
    ADD CONSTRAINT pk_sn_payout_rules PRIMARY KEY (id);


--
-- Name: sn_payout_run_steps pk_sn_payout_run_steps; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_payout_run_steps
    ADD CONSTRAINT pk_sn_payout_run_steps PRIMARY KEY (id);


--
-- Name: sn_payout_runs pk_sn_payout_runs; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_payout_runs
    ADD CONSTRAINT pk_sn_payout_runs PRIMARY KEY (id);


--
-- Name: sn_permissions pk_sn_permissions; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_permissions
    ADD CONSTRAINT pk_sn_permissions PRIMARY KEY (id);


--
-- Name: sn_postal_addresses pk_sn_postal_addresses; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_postal_addresses
    ADD CONSTRAINT pk_sn_postal_addresses PRIMARY KEY (id);


--
-- Name: sn_product_categories pk_sn_product_categories; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_product_categories
    ADD CONSTRAINT pk_sn_product_categories PRIMARY KEY (id);


--
-- Name: sn_promoter_level_log pk_sn_promoter_level_log; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_promoter_level_log
    ADD CONSTRAINT pk_sn_promoter_level_log PRIMARY KEY (id);


--
-- Name: sn_promoter_profiles pk_sn_promoter_profiles; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_promoter_profiles
    ADD CONSTRAINT pk_sn_promoter_profiles PRIMARY KEY (id);


--
-- Name: sn_receipt_claims pk_sn_receipt_claims; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_receipt_claims
    ADD CONSTRAINT pk_sn_receipt_claims PRIMARY KEY (id);


--
-- Name: sn_role_grants pk_sn_role_grants; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_role_grants
    ADD CONSTRAINT pk_sn_role_grants PRIMARY KEY (role_id, permission_id);


--
-- Name: sn_roles pk_sn_roles; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_roles
    ADD CONSTRAINT pk_sn_roles PRIMARY KEY (id);


--
-- Name: sn_seller_role_history pk_sn_seller_role_history; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_seller_role_history
    ADD CONSTRAINT pk_sn_seller_role_history PRIMARY KEY (id);


--
-- Name: sn_shop_orders pk_sn_shop_orders; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_shop_orders
    ADD CONSTRAINT pk_sn_shop_orders PRIMARY KEY (id);


--
-- Name: sn_shopify_config pk_sn_shopify_config; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_shopify_config
    ADD CONSTRAINT pk_sn_shopify_config PRIMARY KEY (id);


--
-- Name: sn_shopify_item_variants pk_sn_shopify_item_variants; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_shopify_item_variants
    ADD CONSTRAINT pk_sn_shopify_item_variants PRIMARY KEY (id);


--
-- Name: sn_shopify_items pk_sn_shopify_items; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_shopify_items
    ADD CONSTRAINT pk_sn_shopify_items PRIMARY KEY (id);


--
-- Name: sn_shopify_order_lines pk_sn_shopify_order_lines; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_shopify_order_lines
    ADD CONSTRAINT pk_sn_shopify_order_lines PRIMARY KEY (id);


--
-- Name: sn_shopify_orders pk_sn_shopify_orders; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_shopify_orders
    ADD CONSTRAINT pk_sn_shopify_orders PRIMARY KEY (id);


--
-- Name: sn_stored_files pk_sn_stored_files; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_stored_files
    ADD CONSTRAINT pk_sn_stored_files PRIMARY KEY (id);


--
-- Name: sn_stripe_events pk_sn_stripe_events; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_stripe_events
    ADD CONSTRAINT pk_sn_stripe_events PRIMARY KEY (id);


--
-- Name: sn_supplier_item_orders pk_sn_supplier_item_orders; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_supplier_item_orders
    ADD CONSTRAINT pk_sn_supplier_item_orders PRIMARY KEY (id);


--
-- Name: sn_supplier_items pk_sn_supplier_items; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_supplier_items
    ADD CONSTRAINT pk_sn_supplier_items PRIMARY KEY (id);


--
-- Name: sn_supplier_members pk_sn_supplier_members; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_supplier_members
    ADD CONSTRAINT pk_sn_supplier_members PRIMARY KEY (id);


--
-- Name: sn_supplier_sources pk_sn_supplier_sources; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_supplier_sources
    ADD CONSTRAINT pk_sn_supplier_sources PRIMARY KEY (id);


--
-- Name: sn_suppliers pk_sn_suppliers; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_suppliers
    ADD CONSTRAINT pk_sn_suppliers PRIMARY KEY (id);


--
-- Name: sn_support_cases pk_sn_support_cases; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_support_cases
    ADD CONSTRAINT pk_sn_support_cases PRIMARY KEY (id);


--
-- Name: sn_support_replies pk_sn_support_replies; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_support_replies
    ADD CONSTRAINT pk_sn_support_replies PRIMARY KEY (id);


--
-- Name: sn_tenants pk_sn_tenants; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_tenants
    ADD CONSTRAINT pk_sn_tenants PRIMARY KEY (id);


--
-- Name: sn_tree_links pk_sn_tree_links; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_tree_links
    ADD CONSTRAINT pk_sn_tree_links PRIMARY KEY (id);


--
-- Name: sn_tree_moves pk_sn_tree_moves; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_tree_moves
    ADD CONSTRAINT pk_sn_tree_moves PRIMARY KEY (id);


--
-- Name: sn_tree_nodes pk_sn_tree_nodes; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_tree_nodes
    ADD CONSTRAINT pk_sn_tree_nodes PRIMARY KEY (id);


--
-- Name: sn_tree_paths pk_sn_tree_paths; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_tree_paths
    ADD CONSTRAINT pk_sn_tree_paths PRIMARY KEY (organization_id, ancestor_agent_id, descendant_agent_id, effective_from);


--
-- Name: sn_tree_snapshot_nodes pk_sn_tree_snapshot_nodes; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_tree_snapshot_nodes
    ADD CONSTRAINT pk_sn_tree_snapshot_nodes PRIMARY KEY (snapshot_id, ancestor_agent_id);


--
-- Name: sn_tree_snapshots pk_sn_tree_snapshots; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_tree_snapshots
    ADD CONSTRAINT pk_sn_tree_snapshots PRIMARY KEY (id);


--
-- Name: sn_utility_points pk_sn_utility_points; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_utility_points
    ADD CONSTRAINT pk_sn_utility_points PRIMARY KEY (id);


--
-- Name: sn_account_roles uq_sn_account_roles; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_account_roles
    ADD CONSTRAINT uq_sn_account_roles UNIQUE (user_id, organization_id, role_id);


--
-- Name: sn_accounts uq_sn_accounts_org_email; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_accounts
    ADD CONSTRAINT uq_sn_accounts_org_email UNIQUE (organization_id, email);


--
-- Name: sn_aff_clients uq_sn_aff_clients_mamify_customer; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_aff_clients
    ADD CONSTRAINT uq_sn_aff_clients_mamify_customer UNIQUE (organization_id, mamify_customer_id);


--
-- Name: sn_aff_commissions uq_sn_aff_commissions_operation_position; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_aff_commissions
    ADD CONSTRAINT uq_sn_aff_commissions_operation_position UNIQUE (operation_id, kind, "position");


--
-- Name: sn_aff_licenses uq_sn_aff_licenses_code; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_aff_licenses
    ADD CONSTRAINT uq_sn_aff_licenses_code UNIQUE (organization_id, code);


--
-- Name: sn_aff_monthly_results uq_sn_aff_monthly_results_agent; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_aff_monthly_results
    ADD CONSTRAINT uq_sn_aff_monthly_results_agent UNIQUE (organization_id, period, agent_id);


--
-- Name: sn_aff_operations uq_sn_aff_operations_idempotency; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_aff_operations
    ADD CONSTRAINT uq_sn_aff_operations_idempotency UNIQUE (organization_id, idempotency_key);


--
-- Name: sn_aff_period_closes uq_sn_aff_period_closes_period; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_aff_period_closes
    ADD CONSTRAINT uq_sn_aff_period_closes_period UNIQUE (organization_id, period);


--
-- Name: sn_aff_plan_versions uq_sn_aff_plan_versions_valid_from; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_aff_plan_versions
    ADD CONSTRAINT uq_sn_aff_plan_versions_valid_from UNIQUE (organization_id, valid_from);


--
-- Name: sn_aff_points uq_sn_aff_points_operation; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_aff_points
    ADD CONSTRAINT uq_sn_aff_points_operation UNIQUE (operation_id);


--
-- Name: sn_aff_subscriptions uq_sn_aff_subscriptions_agent; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_aff_subscriptions
    ADD CONSTRAINT uq_sn_aff_subscriptions_agent UNIQUE (organization_id, agent_id);


--
-- Name: sn_agreement_checkouts uq_sn_agreement_checkouts_stripe_checkout_session_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_agreement_checkouts
    ADD CONSTRAINT uq_sn_agreement_checkouts_stripe_checkout_session_id UNIQUE (stripe_checkout_session_id);


--
-- Name: sn_agreement_instalments uq_sn_agreement_instalments_contract_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_agreement_instalments
    ADD CONSTRAINT uq_sn_agreement_instalments_contract_id UNIQUE (contract_id, stripe_invoice_id);


--
-- Name: sn_agreement_instalments uq_sn_agreement_instalments_contract_number; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_agreement_instalments
    ADD CONSTRAINT uq_sn_agreement_instalments_contract_number UNIQUE (contract_id, number);


--
-- Name: sn_agreement_payout_plans uq_sn_agreement_payout_plans_contract_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_agreement_payout_plans
    ADD CONSTRAINT uq_sn_agreement_payout_plans_contract_id UNIQUE (contract_id);


--
-- Name: sn_agreements uq_sn_agreements_stripe_checkout_session_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_agreements
    ADD CONSTRAINT uq_sn_agreements_stripe_checkout_session_id UNIQUE (stripe_checkout_session_id);


--
-- Name: sn_agreements uq_sn_agreements_stripe_subscription_item_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_agreements
    ADD CONSTRAINT uq_sn_agreements_stripe_subscription_item_id UNIQUE (stripe_subscription_item_id);


--
-- Name: sn_aliexpress_config uq_sn_aliexpress_config_organization_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_aliexpress_config
    ADD CONSTRAINT uq_sn_aliexpress_config_organization_id UNIQUE (organization_id);


--
-- Name: sn_aliexpress_item_variants uq_sn_aliexpress_item_variants_product_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_aliexpress_item_variants
    ADD CONSTRAINT uq_sn_aliexpress_item_variants_product_id UNIQUE (product_id, aliexpress_sku_id);


--
-- Name: sn_aliexpress_items uq_sn_aliexpress_items_organization_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_aliexpress_items
    ADD CONSTRAINT uq_sn_aliexpress_items_organization_id UNIQUE (organization_id, aliexpress_product_id);


--
-- Name: sn_aliexpress_order_lines uq_sn_aliexpress_order_lines_variant; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_aliexpress_order_lines
    ADD CONSTRAINT uq_sn_aliexpress_order_lines_variant UNIQUE (order_id, aliexpress_variant_id);


--
-- Name: sn_aliexpress_orders uq_sn_aliexpress_orders_number; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_aliexpress_orders
    ADD CONSTRAINT uq_sn_aliexpress_orders_number UNIQUE (number);


--
-- Name: sn_aliexpress_orders uq_sn_aliexpress_orders_stripe_checkout_session_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_aliexpress_orders
    ADD CONSTRAINT uq_sn_aliexpress_orders_stripe_checkout_session_id UNIQUE (stripe_checkout_session_id);


--
-- Name: sn_basket_lines uq_sn_basket_lines_aliexpress_variant; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_basket_lines
    ADD CONSTRAINT uq_sn_basket_lines_aliexpress_variant UNIQUE (cart_id, aliexpress_variant_id);


--
-- Name: sn_basket_lines uq_sn_basket_lines_cj_variant; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_basket_lines
    ADD CONSTRAINT uq_sn_basket_lines_cj_variant UNIQUE (cart_id, cj_variant_id);


--
-- Name: sn_basket_lines uq_sn_basket_lines_product_version; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_basket_lines
    ADD CONSTRAINT uq_sn_basket_lines_product_version UNIQUE (cart_id, product_version_id);


--
-- Name: sn_basket_lines uq_sn_basket_lines_shopify_variant; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_basket_lines
    ADD CONSTRAINT uq_sn_basket_lines_shopify_variant UNIQUE (cart_id, shopify_variant_id);


--
-- Name: sn_basket_lines uq_sn_basket_lines_sosnet_market_variant; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_basket_lines
    ADD CONSTRAINT uq_sn_basket_lines_sosnet_market_variant UNIQUE (cart_id, sosnet_market_variant_id);


--
-- Name: sn_baskets uq_sn_baskets_customer_shop; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_baskets
    ADD CONSTRAINT uq_sn_baskets_customer_shop UNIQUE (customer_user_id, shop);


--
-- Name: sn_career_levels uq_sn_career_levels_org_code_version; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_career_levels
    ADD CONSTRAINT uq_sn_career_levels_org_code_version UNIQUE (organization_id, code, rule_version);


--
-- Name: sn_catalog_section_items uq_sn_catalog_section_items_category_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_catalog_section_items
    ADD CONSTRAINT uq_sn_catalog_section_items_category_id UNIQUE (category_id, product_id);


--
-- Name: sn_cj_config uq_sn_cj_config_organization_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_cj_config
    ADD CONSTRAINT uq_sn_cj_config_organization_id UNIQUE (organization_id);


--
-- Name: sn_cj_item_variants uq_sn_cj_item_variants_product_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_cj_item_variants
    ADD CONSTRAINT uq_sn_cj_item_variants_product_id UNIQUE (product_id, cj_vid);


--
-- Name: sn_cj_items uq_sn_cj_items_organization_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_cj_items
    ADD CONSTRAINT uq_sn_cj_items_organization_id UNIQUE (organization_id, cj_pid);


--
-- Name: sn_cj_order_lines uq_sn_cj_order_lines_variant; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_cj_order_lines
    ADD CONSTRAINT uq_sn_cj_order_lines_variant UNIQUE (order_id, variant_id);


--
-- Name: sn_cj_orders uq_sn_cj_orders_number; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_cj_orders
    ADD CONSTRAINT uq_sn_cj_orders_number UNIQUE (number);


--
-- Name: sn_cj_orders uq_sn_cj_orders_stripe_checkout_session_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_cj_orders
    ADD CONSTRAINT uq_sn_cj_orders_stripe_checkout_session_id UNIQUE (stripe_checkout_session_id);


--
-- Name: sn_clients uq_sn_clients_user_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_clients
    ADD CONSTRAINT uq_sn_clients_user_id UNIQUE (user_id);


--
-- Name: sn_commercial_roles uq_sn_commercial_roles_org_code; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_commercial_roles
    ADD CONSTRAINT uq_sn_commercial_roles_org_code UNIQUE (organization_id, code);


--
-- Name: sn_credit_accounts uq_sn_credit_accounts_address; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_credit_accounts
    ADD CONSTRAINT uq_sn_credit_accounts_address UNIQUE (address);


--
-- Name: sn_credit_accounts uq_sn_credit_accounts_user_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_credit_accounts
    ADD CONSTRAINT uq_sn_credit_accounts_user_id UNIQUE (user_id);


--
-- Name: sn_credit_ledger uq_sn_credit_ledger_idempotency_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_credit_ledger
    ADD CONSTRAINT uq_sn_credit_ledger_idempotency_key UNIQUE (idempotency_key);


--
-- Name: sn_friend_invite_codes uq_sn_friend_invite_codes_code; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_friend_invite_codes
    ADD CONSTRAINT uq_sn_friend_invite_codes_code UNIQUE (code);


--
-- Name: sn_friend_invite_codes uq_sn_friend_invite_codes_user_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_friend_invite_codes
    ADD CONSTRAINT uq_sn_friend_invite_codes_user_id UNIQUE (user_id);


--
-- Name: sn_friend_invite_rewards uq_sn_friend_invite_rewards_user_milestone; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_friend_invite_rewards
    ADD CONSTRAINT uq_sn_friend_invite_rewards_user_milestone UNIQUE (referrer_user_id, milestone);


--
-- Name: sn_friend_invites uq_sn_friend_invites_referred_customer_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_friend_invites
    ADD CONSTRAINT uq_sn_friend_invites_referred_customer_id UNIQUE (referred_customer_id);


--
-- Name: sn_promoter_profiles uq_sn_invite_codes_agent; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_promoter_profiles
    ADD CONSTRAINT uq_sn_invite_codes_agent UNIQUE (organization_id, promoter_code);


--
-- Name: sn_mamify_config uq_sn_mamify_config_org; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_mamify_config
    ADD CONSTRAINT uq_sn_mamify_config_org UNIQUE (organization_id);


--
-- Name: sn_mamify_members uq_sn_mamify_members_agent; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_mamify_members
    ADD CONSTRAINT uq_sn_mamify_members_agent UNIQUE (organization_id, agent_id);


--
-- Name: sn_mamify_members uq_sn_mamify_members_customer; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_mamify_members
    ADD CONSTRAINT uq_sn_mamify_members_customer UNIQUE (organization_id, mamify_customer_id);


--
-- Name: sn_mamify_orders uq_sn_mamify_orders_order; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_mamify_orders
    ADD CONSTRAINT uq_sn_mamify_orders_order UNIQUE (organization_id, mamify_order_id);


--
-- Name: sn_mamify_payouts uq_sn_mamify_payouts_commission; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_mamify_payouts
    ADD CONSTRAINT uq_sn_mamify_payouts_commission UNIQUE (commission_id);


--
-- Name: sn_mamify_products uq_sn_mamify_products_product; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_mamify_products
    ADD CONSTRAINT uq_sn_mamify_products_product UNIQUE (organization_id, mamify_product_id);


--
-- Name: sn_mamify_webhook_events uq_sn_mamify_webhook_events_body; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_mamify_webhook_events
    ADD CONSTRAINT uq_sn_mamify_webhook_events_body UNIQUE (organization_id, body_hash);


--
-- Name: sn_market_config uq_sn_market_config_organization_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_market_config
    ADD CONSTRAINT uq_sn_market_config_organization_id UNIQUE (organization_id);


--
-- Name: sn_market_item_variants uq_sn_market_item_variants_sku; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_market_item_variants
    ADD CONSTRAINT uq_sn_market_item_variants_sku UNIQUE (product_id, sku);


--
-- Name: sn_market_order_lines uq_sn_market_order_lines_variant; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_market_order_lines
    ADD CONSTRAINT uq_sn_market_order_lines_variant UNIQUE (order_id, variant_id);


--
-- Name: sn_market_orders uq_sn_market_orders_number; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_market_orders
    ADD CONSTRAINT uq_sn_market_orders_number UNIQUE (number);


--
-- Name: sn_market_orders uq_sn_market_orders_stripe_checkout_session_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_market_orders
    ADD CONSTRAINT uq_sn_market_orders_stripe_checkout_session_id UNIQUE (stripe_checkout_session_id);


--
-- Name: sn_market_producers uq_sn_market_producers_name; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_market_producers
    ADD CONSTRAINT uq_sn_market_producers_name UNIQUE (organization_id, name);


--
-- Name: sn_merchants uq_sn_merchants_organization_name; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_merchants
    ADD CONSTRAINT uq_sn_merchants_organization_name UNIQUE (organization_id, name);


--
-- Name: sn_payout_entries uq_sn_payout_entries_idempotency_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_payout_entries
    ADD CONSTRAINT uq_sn_payout_entries_idempotency_key UNIQUE (idempotency_key);


--
-- Name: sn_payout_runs uq_sn_payout_runs_contract_trigger; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_payout_runs
    ADD CONSTRAINT uq_sn_payout_runs_contract_trigger UNIQUE (contract_id, trigger_event_id);


--
-- Name: sn_permissions uq_sn_permissions_code; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_permissions
    ADD CONSTRAINT uq_sn_permissions_code UNIQUE (code);


--
-- Name: sn_product_categories uq_sn_product_categories_org_code; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_product_categories
    ADD CONSTRAINT uq_sn_product_categories_org_code UNIQUE (organization_id, code);


--
-- Name: sn_receipt_claims uq_sn_receipt_claims_payment_reference_code; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_receipt_claims
    ADD CONSTRAINT uq_sn_receipt_claims_payment_reference_code UNIQUE (payment_reference_code);


--
-- Name: sn_receipt_claims uq_sn_receipt_claims_storage_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_receipt_claims
    ADD CONSTRAINT uq_sn_receipt_claims_storage_key UNIQUE (storage_key);


--
-- Name: sn_receipt_claims uq_sn_receipt_claims_stripe_checkout_session_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_receipt_claims
    ADD CONSTRAINT uq_sn_receipt_claims_stripe_checkout_session_id UNIQUE (stripe_checkout_session_id);


--
-- Name: sn_roles uq_sn_roles_org_code; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_roles
    ADD CONSTRAINT uq_sn_roles_org_code UNIQUE (organization_id, code);


--
-- Name: sn_shop_orders uq_sn_shop_orders_stripe_checkout_session_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_shop_orders
    ADD CONSTRAINT uq_sn_shop_orders_stripe_checkout_session_id UNIQUE (stripe_checkout_session_id);


--
-- Name: sn_shopify_config uq_sn_shopify_config_organization_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_shopify_config
    ADD CONSTRAINT uq_sn_shopify_config_organization_id UNIQUE (organization_id);


--
-- Name: sn_shopify_item_variants uq_sn_shopify_item_variants_product_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_shopify_item_variants
    ADD CONSTRAINT uq_sn_shopify_item_variants_product_id UNIQUE (product_id, shopify_variant_id);


--
-- Name: sn_shopify_items uq_sn_shopify_items_organization_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_shopify_items
    ADD CONSTRAINT uq_sn_shopify_items_organization_id UNIQUE (organization_id, shopify_product_id);


--
-- Name: sn_shopify_order_lines uq_sn_shopify_order_lines_variant; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_shopify_order_lines
    ADD CONSTRAINT uq_sn_shopify_order_lines_variant UNIQUE (order_id, variant_id);


--
-- Name: sn_shopify_orders uq_sn_shopify_orders_number; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_shopify_orders
    ADD CONSTRAINT uq_sn_shopify_orders_number UNIQUE (number);


--
-- Name: sn_shopify_orders uq_sn_shopify_orders_stripe_checkout_session_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_shopify_orders
    ADD CONSTRAINT uq_sn_shopify_orders_stripe_checkout_session_id UNIQUE (stripe_checkout_session_id);


--
-- Name: sn_stored_files uq_sn_stored_files_storage_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_stored_files
    ADD CONSTRAINT uq_sn_stored_files_storage_key UNIQUE (storage_key);


--
-- Name: sn_stripe_events uq_sn_stripe_events_event_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_stripe_events
    ADD CONSTRAINT uq_sn_stripe_events_event_id UNIQUE (stripe_event_id);


--
-- Name: sn_supplier_item_orders uq_sn_supplier_item_orders_number; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_supplier_item_orders
    ADD CONSTRAINT uq_sn_supplier_item_orders_number UNIQUE (number);


--
-- Name: sn_supplier_item_orders uq_sn_supplier_item_orders_stripe_checkout_session_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_supplier_item_orders
    ADD CONSTRAINT uq_sn_supplier_item_orders_stripe_checkout_session_id UNIQUE (stripe_checkout_session_id);


--
-- Name: sn_suppliers uq_sn_suppliers_org_name; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_suppliers
    ADD CONSTRAINT uq_sn_suppliers_org_name UNIQUE (organization_id, name);


--
-- Name: ix_sn_account_roles_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_account_roles_organization_id ON public.sn_account_roles USING btree (organization_id);


--
-- Name: ix_sn_account_roles_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_account_roles_user_id ON public.sn_account_roles USING btree (user_id);


--
-- Name: ix_sn_accounts_email; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_accounts_email ON public.sn_accounts USING btree (email);


--
-- Name: ix_sn_accounts_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_accounts_organization_id ON public.sn_accounts USING btree (organization_id);


--
-- Name: ix_sn_activity_log_action; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_activity_log_action ON public.sn_activity_log USING btree (action);


--
-- Name: ix_sn_activity_log_correlation_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_activity_log_correlation_id ON public.sn_activity_log USING btree (correlation_id);


--
-- Name: ix_sn_activity_log_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_activity_log_organization_id ON public.sn_activity_log USING btree (organization_id);


--
-- Name: ix_sn_aff_clients_agent_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_aff_clients_agent_id ON public.sn_aff_clients USING btree (agent_id);


--
-- Name: ix_sn_aff_clients_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_aff_clients_organization_id ON public.sn_aff_clients USING btree (organization_id);


--
-- Name: ix_sn_aff_commissions_beneficiary_agent_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_aff_commissions_beneficiary_agent_id ON public.sn_aff_commissions USING btree (beneficiary_agent_id);


--
-- Name: ix_sn_aff_commissions_kind; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_aff_commissions_kind ON public.sn_aff_commissions USING btree (kind);


--
-- Name: ix_sn_aff_commissions_operation_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_aff_commissions_operation_id ON public.sn_aff_commissions USING btree (operation_id);


--
-- Name: ix_sn_aff_commissions_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_aff_commissions_organization_id ON public.sn_aff_commissions USING btree (organization_id);


--
-- Name: ix_sn_aff_commissions_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_aff_commissions_status ON public.sn_aff_commissions USING btree (status);


--
-- Name: ix_sn_aff_licenses_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_aff_licenses_organization_id ON public.sn_aff_licenses USING btree (organization_id);


--
-- Name: ix_sn_aff_licenses_owner_agent_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_aff_licenses_owner_agent_id ON public.sn_aff_licenses USING btree (owner_agent_id);


--
-- Name: ix_sn_aff_licenses_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_aff_licenses_status ON public.sn_aff_licenses USING btree (status);


--
-- Name: ix_sn_aff_monthly_results_agent_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_aff_monthly_results_agent_id ON public.sn_aff_monthly_results USING btree (agent_id);


--
-- Name: ix_sn_aff_monthly_results_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_aff_monthly_results_organization_id ON public.sn_aff_monthly_results USING btree (organization_id);


--
-- Name: ix_sn_aff_monthly_results_period; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_aff_monthly_results_period ON public.sn_aff_monthly_results USING btree (period);


--
-- Name: ix_sn_aff_operations_agent_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_aff_operations_agent_id ON public.sn_aff_operations USING btree (agent_id);


--
-- Name: ix_sn_aff_operations_client_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_aff_operations_client_id ON public.sn_aff_operations USING btree (client_id);


--
-- Name: ix_sn_aff_operations_kind; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_aff_operations_kind ON public.sn_aff_operations USING btree (kind);


--
-- Name: ix_sn_aff_operations_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_aff_operations_organization_id ON public.sn_aff_operations USING btree (organization_id);


--
-- Name: ix_sn_aff_operations_period; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_aff_operations_period ON public.sn_aff_operations USING btree (period);


--
-- Name: ix_sn_aff_operations_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_aff_operations_status ON public.sn_aff_operations USING btree (status);


--
-- Name: ix_sn_aff_period_closes_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_aff_period_closes_organization_id ON public.sn_aff_period_closes USING btree (organization_id);


--
-- Name: ix_sn_aff_plan_versions_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_aff_plan_versions_organization_id ON public.sn_aff_plan_versions USING btree (organization_id);


--
-- Name: ix_sn_aff_points_agent_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_aff_points_agent_id ON public.sn_aff_points USING btree (agent_id);


--
-- Name: ix_sn_aff_points_org_period; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_aff_points_org_period ON public.sn_aff_points USING btree (organization_id, period);


--
-- Name: ix_sn_aff_subscriptions_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_aff_subscriptions_organization_id ON public.sn_aff_subscriptions USING btree (organization_id);


--
-- Name: ix_sn_agreement_attributions_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_agreement_attributions_organization_id ON public.sn_agreement_attributions USING btree (organization_id);


--
-- Name: ix_sn_agreement_checkouts_contract_request_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_agreement_checkouts_contract_request_id ON public.sn_agreement_checkouts USING btree (contract_request_id);


--
-- Name: ix_sn_agreement_checkouts_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_agreement_checkouts_organization_id ON public.sn_agreement_checkouts USING btree (organization_id);


--
-- Name: ix_sn_agreement_events_contract_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_agreement_events_contract_id ON public.sn_agreement_events USING btree (contract_id);


--
-- Name: ix_sn_agreement_instalments_contract_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_agreement_instalments_contract_id ON public.sn_agreement_instalments USING btree (contract_id);


--
-- Name: ix_sn_agreement_instalments_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_agreement_instalments_organization_id ON public.sn_agreement_instalments USING btree (organization_id);


--
-- Name: ix_sn_agreement_payout_plans_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_agreement_payout_plans_organization_id ON public.sn_agreement_payout_plans USING btree (organization_id);


--
-- Name: ix_sn_agreement_requests_customer_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_agreement_requests_customer_id ON public.sn_agreement_requests USING btree (customer_id);


--
-- Name: ix_sn_agreement_requests_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_agreement_requests_organization_id ON public.sn_agreement_requests USING btree (organization_id);


--
-- Name: ix_sn_agreement_requests_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_agreement_requests_status ON public.sn_agreement_requests USING btree (status);


--
-- Name: ix_sn_agreement_status_log_contract_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_agreement_status_log_contract_id ON public.sn_agreement_status_log USING btree (contract_id);


--
-- Name: ix_sn_agreements_contract_request_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_agreements_contract_request_id ON public.sn_agreements USING btree (contract_request_id);


--
-- Name: ix_sn_agreements_customer_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_agreements_customer_id ON public.sn_agreements USING btree (customer_id);


--
-- Name: ix_sn_agreements_expires_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_agreements_expires_at ON public.sn_agreements USING btree (expires_at);


--
-- Name: ix_sn_agreements_lead_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_agreements_lead_id ON public.sn_agreements USING btree (lead_id);


--
-- Name: ix_sn_agreements_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_agreements_organization_id ON public.sn_agreements USING btree (organization_id);


--
-- Name: ix_sn_agreements_split_plan_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_agreements_split_plan_id ON public.sn_agreements USING btree (split_plan_id);


--
-- Name: ix_sn_agreements_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_agreements_status ON public.sn_agreements USING btree (status);


--
-- Name: ix_sn_aliexpress_item_variants_product_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_aliexpress_item_variants_product_id ON public.sn_aliexpress_item_variants USING btree (product_id);


--
-- Name: ix_sn_aliexpress_items_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_aliexpress_items_organization_id ON public.sn_aliexpress_items USING btree (organization_id);


--
-- Name: ix_sn_aliexpress_items_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_aliexpress_items_status ON public.sn_aliexpress_items USING btree (status);


--
-- Name: ix_sn_aliexpress_order_lines_aliexpress_order_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_aliexpress_order_lines_aliexpress_order_id ON public.sn_aliexpress_order_lines USING btree (aliexpress_order_id);


--
-- Name: ix_sn_aliexpress_order_lines_order_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_aliexpress_order_lines_order_id ON public.sn_aliexpress_order_lines USING btree (order_id);


--
-- Name: ix_sn_aliexpress_orders_aliexpress_order_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_aliexpress_orders_aliexpress_order_id ON public.sn_aliexpress_orders USING btree (aliexpress_order_id);


--
-- Name: ix_sn_aliexpress_orders_customer_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_aliexpress_orders_customer_user_id ON public.sn_aliexpress_orders USING btree (customer_user_id);


--
-- Name: ix_sn_aliexpress_orders_fulfillment_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_aliexpress_orders_fulfillment_status ON public.sn_aliexpress_orders USING btree (fulfillment_status);


--
-- Name: ix_sn_aliexpress_orders_next_retry_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_aliexpress_orders_next_retry_at ON public.sn_aliexpress_orders USING btree (next_retry_at);


--
-- Name: ix_sn_aliexpress_orders_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_aliexpress_orders_organization_id ON public.sn_aliexpress_orders USING btree (organization_id);


--
-- Name: ix_sn_aliexpress_orders_out_order_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_aliexpress_orders_out_order_id ON public.sn_aliexpress_orders USING btree (out_order_id);


--
-- Name: ix_sn_aliexpress_orders_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_aliexpress_orders_status ON public.sn_aliexpress_orders USING btree (status);


--
-- Name: ix_sn_attribution_fixes_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_attribution_fixes_organization_id ON public.sn_attribution_fixes USING btree (organization_id);


--
-- Name: ix_sn_basket_lines_cart_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_basket_lines_cart_id ON public.sn_basket_lines USING btree (cart_id);


--
-- Name: ix_sn_baskets_customer_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_baskets_customer_user_id ON public.sn_baskets USING btree (customer_user_id);


--
-- Name: ix_sn_baskets_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_baskets_organization_id ON public.sn_baskets USING btree (organization_id);


--
-- Name: ix_sn_career_levels_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_career_levels_organization_id ON public.sn_career_levels USING btree (organization_id);


--
-- Name: ix_sn_catalog_section_items_category_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_catalog_section_items_category_id ON public.sn_catalog_section_items USING btree (category_id);


--
-- Name: ix_sn_catalog_section_items_organization_id_shop_product_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_catalog_section_items_organization_id_shop_product_id ON public.sn_catalog_section_items USING btree (organization_id, shop, product_id);


--
-- Name: ix_sn_catalog_sections_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_catalog_sections_organization_id ON public.sn_catalog_sections USING btree (organization_id);


--
-- Name: ix_sn_cj_item_variants_product_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_cj_item_variants_product_id ON public.sn_cj_item_variants USING btree (product_id);


--
-- Name: ix_sn_cj_items_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_cj_items_organization_id ON public.sn_cj_items USING btree (organization_id);


--
-- Name: ix_sn_cj_items_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_cj_items_status ON public.sn_cj_items USING btree (status);


--
-- Name: ix_sn_cj_order_lines_order_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_cj_order_lines_order_id ON public.sn_cj_order_lines USING btree (order_id);


--
-- Name: ix_sn_cj_orders_cj_order_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_cj_orders_cj_order_id ON public.sn_cj_orders USING btree (cj_order_id);


--
-- Name: ix_sn_cj_orders_cj_payment_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_cj_orders_cj_payment_status ON public.sn_cj_orders USING btree (cj_payment_status);


--
-- Name: ix_sn_cj_orders_customer_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_cj_orders_customer_user_id ON public.sn_cj_orders USING btree (customer_user_id);


--
-- Name: ix_sn_cj_orders_fulfillment_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_cj_orders_fulfillment_status ON public.sn_cj_orders USING btree (fulfillment_status);


--
-- Name: ix_sn_cj_orders_next_retry_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_cj_orders_next_retry_at ON public.sn_cj_orders USING btree (next_retry_at);


--
-- Name: ix_sn_cj_orders_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_cj_orders_organization_id ON public.sn_cj_orders USING btree (organization_id);


--
-- Name: ix_sn_cj_orders_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_cj_orders_status ON public.sn_cj_orders USING btree (status);


--
-- Name: ix_sn_client_attributions_customer_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_client_attributions_customer_id ON public.sn_client_attributions USING btree (customer_id);


--
-- Name: ix_sn_client_attributions_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_client_attributions_organization_id ON public.sn_client_attributions USING btree (organization_id);


--
-- Name: ix_sn_clients_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_clients_organization_id ON public.sn_clients USING btree (organization_id);


--
-- Name: ix_sn_commercial_roles_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_commercial_roles_organization_id ON public.sn_commercial_roles USING btree (organization_id);


--
-- Name: ix_sn_credit_accounts_address; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_credit_accounts_address ON public.sn_credit_accounts USING btree (address);


--
-- Name: ix_sn_credit_accounts_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_credit_accounts_organization_id ON public.sn_credit_accounts USING btree (organization_id);


--
-- Name: ix_sn_credit_accounts_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_credit_accounts_user_id ON public.sn_credit_accounts USING btree (user_id);


--
-- Name: ix_sn_credit_ledger_from_wallet_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_credit_ledger_from_wallet_id ON public.sn_credit_ledger USING btree (from_wallet_id);


--
-- Name: ix_sn_credit_ledger_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_credit_ledger_organization_id ON public.sn_credit_ledger USING btree (organization_id);


--
-- Name: ix_sn_credit_ledger_reference_sosnet_market_order_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_credit_ledger_reference_sosnet_market_order_id ON public.sn_credit_ledger USING btree (reference_sosnet_market_order_id);


--
-- Name: ix_sn_credit_ledger_to_wallet_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_credit_ledger_to_wallet_id ON public.sn_credit_ledger USING btree (to_wallet_id);


--
-- Name: ix_sn_credit_ledger_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_credit_ledger_type ON public.sn_credit_ledger USING btree (type);


--
-- Name: ix_sn_delegations_delegate_agent_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_delegations_delegate_agent_id ON public.sn_delegations USING btree (delegate_agent_id);


--
-- Name: ix_sn_delegations_influencer_agent_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_delegations_influencer_agent_id ON public.sn_delegations USING btree (influencer_agent_id);


--
-- Name: ix_sn_delegations_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_delegations_organization_id ON public.sn_delegations USING btree (organization_id);


--
-- Name: ix_sn_email_confirmations_token_hash; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_sn_email_confirmations_token_hash ON public.sn_email_confirmations USING btree (token_hash);


--
-- Name: ix_sn_email_confirmations_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_email_confirmations_user_id ON public.sn_email_confirmations USING btree (user_id);


--
-- Name: ix_sn_event_outbox_event_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_event_outbox_event_type ON public.sn_event_outbox USING btree (event_type);


--
-- Name: ix_sn_event_outbox_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_event_outbox_organization_id ON public.sn_event_outbox USING btree (organization_id);


--
-- Name: ix_sn_event_outbox_processed_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_event_outbox_processed_at ON public.sn_event_outbox USING btree (processed_at);


--
-- Name: ix_sn_friend_invite_codes_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_friend_invite_codes_organization_id ON public.sn_friend_invite_codes USING btree (organization_id);


--
-- Name: ix_sn_friend_invite_rewards_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_friend_invite_rewards_organization_id ON public.sn_friend_invite_rewards USING btree (organization_id);


--
-- Name: ix_sn_friend_invite_rewards_referrer_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_friend_invite_rewards_referrer_user_id ON public.sn_friend_invite_rewards USING btree (referrer_user_id);


--
-- Name: ix_sn_friend_invite_rewards_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_friend_invite_rewards_status ON public.sn_friend_invite_rewards USING btree (status);


--
-- Name: ix_sn_friend_invites_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_friend_invites_organization_id ON public.sn_friend_invites USING btree (organization_id);


--
-- Name: ix_sn_friend_invites_referrer_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_friend_invites_referrer_user_id ON public.sn_friend_invites USING btree (referrer_user_id);


--
-- Name: ix_sn_inbox_messages_is_read; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_inbox_messages_is_read ON public.sn_inbox_messages USING btree (is_read);


--
-- Name: ix_sn_inbox_messages_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_inbox_messages_organization_id ON public.sn_inbox_messages USING btree (organization_id);


--
-- Name: ix_sn_inbox_messages_recipient_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_inbox_messages_recipient_user_id ON public.sn_inbox_messages USING btree (recipient_user_id);


--
-- Name: ix_sn_inbox_messages_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_inbox_messages_type ON public.sn_inbox_messages USING btree (type);


--
-- Name: ix_sn_invite_codes_agent_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_invite_codes_agent_id ON public.sn_invite_codes USING btree (agent_id);


--
-- Name: ix_sn_invite_codes_code; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_sn_invite_codes_code ON public.sn_invite_codes USING btree (code);


--
-- Name: ix_sn_invite_codes_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_invite_codes_organization_id ON public.sn_invite_codes USING btree (organization_id);


--
-- Name: ix_sn_invite_events_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_invite_events_organization_id ON public.sn_invite_events USING btree (organization_id);


--
-- Name: ix_sn_invite_events_promoter_code_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_invite_events_promoter_code_id ON public.sn_invite_events USING btree (promoter_code_id);


--
-- Name: ix_sn_invite_visits_cookie_token_hash; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_sn_invite_visits_cookie_token_hash ON public.sn_invite_visits USING btree (cookie_token_hash);


--
-- Name: ix_sn_invite_visits_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_invite_visits_organization_id ON public.sn_invite_visits USING btree (organization_id);


--
-- Name: ix_sn_invite_visits_promoter_code_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_invite_visits_promoter_code_id ON public.sn_invite_visits USING btree (promoter_code_id);


--
-- Name: ix_sn_knowledge_articles_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_knowledge_articles_organization_id ON public.sn_knowledge_articles USING btree (organization_id);


--
-- Name: ix_sn_knowledge_articles_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_knowledge_articles_status ON public.sn_knowledge_articles USING btree (status);


--
-- Name: ix_sn_leads_customer_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_leads_customer_id ON public.sn_leads USING btree (customer_id);


--
-- Name: ix_sn_leads_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_leads_organization_id ON public.sn_leads USING btree (organization_id);


--
-- Name: ix_sn_leads_promoter_agent_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_leads_promoter_agent_id ON public.sn_leads USING btree (promoter_agent_id);


--
-- Name: ix_sn_leads_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_leads_status ON public.sn_leads USING btree (status);


--
-- Name: ix_sn_login_sessions_refresh_token_hash; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_sn_login_sessions_refresh_token_hash ON public.sn_login_sessions USING btree (refresh_token_hash);


--
-- Name: ix_sn_login_sessions_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_login_sessions_user_id ON public.sn_login_sessions USING btree (user_id);


--
-- Name: ix_sn_mamify_config_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_mamify_config_organization_id ON public.sn_mamify_config USING btree (organization_id);


--
-- Name: ix_sn_mamify_members_email; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_mamify_members_email ON public.sn_mamify_members USING btree (email);


--
-- Name: ix_sn_mamify_members_orders_checked; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_mamify_members_orders_checked ON public.sn_mamify_members USING btree (organization_id, orders_checked_at);


--
-- Name: ix_sn_mamify_members_org_agent; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_mamify_members_org_agent ON public.sn_mamify_members USING btree (organization_id, agent_id);


--
-- Name: ix_sn_mamify_members_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_mamify_members_organization_id ON public.sn_mamify_members USING btree (organization_id);


--
-- Name: ix_sn_mamify_members_sponsor_customer_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_mamify_members_sponsor_customer_id ON public.sn_mamify_members USING btree (sponsor_customer_id);


--
-- Name: ix_sn_mamify_orders_buyer_customer_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_mamify_orders_buyer_customer_id ON public.sn_mamify_orders USING btree (buyer_customer_id);


--
-- Name: ix_sn_mamify_orders_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_mamify_orders_organization_id ON public.sn_mamify_orders USING btree (organization_id);


--
-- Name: ix_sn_mamify_orders_state; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_mamify_orders_state ON public.sn_mamify_orders USING btree (state);


--
-- Name: ix_sn_mamify_payouts_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_mamify_payouts_organization_id ON public.sn_mamify_payouts USING btree (organization_id);


--
-- Name: ix_sn_mamify_payouts_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_mamify_payouts_status ON public.sn_mamify_payouts USING btree (status);


--
-- Name: ix_sn_mamify_products_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_mamify_products_organization_id ON public.sn_mamify_products USING btree (organization_id);


--
-- Name: ix_sn_mamify_webhook_events_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_mamify_webhook_events_organization_id ON public.sn_mamify_webhook_events USING btree (organization_id);


--
-- Name: ix_sn_market_config_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_market_config_organization_id ON public.sn_market_config USING btree (organization_id);


--
-- Name: ix_sn_market_item_variants_product_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_market_item_variants_product_id ON public.sn_market_item_variants USING btree (product_id);


--
-- Name: ix_sn_market_items_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_market_items_organization_id ON public.sn_market_items USING btree (organization_id);


--
-- Name: ix_sn_market_items_producer_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_market_items_producer_id ON public.sn_market_items USING btree (producer_id);


--
-- Name: ix_sn_market_items_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_market_items_status ON public.sn_market_items USING btree (status);


--
-- Name: ix_sn_market_order_lines_order_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_market_order_lines_order_id ON public.sn_market_order_lines USING btree (order_id);


--
-- Name: ix_sn_market_orders_customer_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_market_orders_customer_user_id ON public.sn_market_orders USING btree (customer_user_id);


--
-- Name: ix_sn_market_orders_fulfillment_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_market_orders_fulfillment_status ON public.sn_market_orders USING btree (fulfillment_status);


--
-- Name: ix_sn_market_orders_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_market_orders_organization_id ON public.sn_market_orders USING btree (organization_id);


--
-- Name: ix_sn_market_orders_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_market_orders_status ON public.sn_market_orders USING btree (status);


--
-- Name: ix_sn_market_producers_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_market_producers_organization_id ON public.sn_market_producers USING btree (organization_id);


--
-- Name: ix_sn_merchants_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_merchants_organization_id ON public.sn_merchants USING btree (organization_id);


--
-- Name: ix_sn_offer_versions_product_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_offer_versions_product_id ON public.sn_offer_versions USING btree (product_id);


--
-- Name: ix_sn_offers_commercial_category_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_offers_commercial_category_id ON public.sn_offers USING btree (commercial_category_id);


--
-- Name: ix_sn_offers_company_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_offers_company_id ON public.sn_offers USING btree (company_id);


--
-- Name: ix_sn_offers_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_offers_organization_id ON public.sn_offers USING btree (organization_id);


--
-- Name: ix_sn_one_time_codes_code_hash; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_one_time_codes_code_hash ON public.sn_one_time_codes USING btree (code_hash);


--
-- Name: ix_sn_one_time_codes_purpose; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_one_time_codes_purpose ON public.sn_one_time_codes USING btree (purpose);


--
-- Name: ix_sn_one_time_codes_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_one_time_codes_user_id ON public.sn_one_time_codes USING btree (user_id);


--
-- Name: ix_sn_password_recoveries_token_hash; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_sn_password_recoveries_token_hash ON public.sn_password_recoveries USING btree (token_hash);


--
-- Name: ix_sn_password_recoveries_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_password_recoveries_user_id ON public.sn_password_recoveries USING btree (user_id);


--
-- Name: ix_sn_payout_adjustments_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_payout_adjustments_organization_id ON public.sn_payout_adjustments USING btree (organization_id);


--
-- Name: ix_sn_payout_entries_agent_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_payout_entries_agent_id ON public.sn_payout_entries USING btree (agent_id);


--
-- Name: ix_sn_payout_entries_contract_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_payout_entries_contract_id ON public.sn_payout_entries USING btree (contract_id);


--
-- Name: ix_sn_payout_entries_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_payout_entries_organization_id ON public.sn_payout_entries USING btree (organization_id);


--
-- Name: ix_sn_payout_entries_product_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_payout_entries_product_id ON public.sn_payout_entries USING btree (product_id);


--
-- Name: ix_sn_payout_entries_source_seller_agent_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_payout_entries_source_seller_agent_id ON public.sn_payout_entries USING btree (source_seller_agent_id);


--
-- Name: ix_sn_payout_entries_split_plan_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_payout_entries_split_plan_id ON public.sn_payout_entries USING btree (split_plan_id);


--
-- Name: ix_sn_payout_offsets_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_payout_offsets_organization_id ON public.sn_payout_offsets USING btree (organization_id);


--
-- Name: ix_sn_payout_plans_category_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_payout_plans_category_id ON public.sn_payout_plans USING btree (category_id);


--
-- Name: ix_sn_payout_plans_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_payout_plans_organization_id ON public.sn_payout_plans USING btree (organization_id);


--
-- Name: ix_sn_payout_plans_plan_key; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_payout_plans_plan_key ON public.sn_payout_plans USING btree (plan_key);


--
-- Name: ix_sn_payout_plans_product_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_payout_plans_product_id ON public.sn_payout_plans USING btree (product_id);


--
-- Name: ix_sn_payout_plans_seller_role_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_payout_plans_seller_role_id ON public.sn_payout_plans USING btree (seller_role_id);


--
-- Name: ix_sn_payout_reversals_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_payout_reversals_organization_id ON public.sn_payout_reversals USING btree (organization_id);


--
-- Name: ix_sn_payout_rules_commission_plan_version_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_payout_rules_commission_plan_version_id ON public.sn_payout_rules USING btree (commission_plan_version_id);


--
-- Name: ix_sn_payout_run_steps_calculation_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_payout_run_steps_calculation_id ON public.sn_payout_run_steps USING btree (calculation_id);


--
-- Name: ix_sn_payout_runs_contract_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_payout_runs_contract_id ON public.sn_payout_runs USING btree (contract_id);


--
-- Name: ix_sn_payout_runs_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_payout_runs_organization_id ON public.sn_payout_runs USING btree (organization_id);


--
-- Name: ix_sn_postal_addresses_customer_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_postal_addresses_customer_id ON public.sn_postal_addresses USING btree (customer_id);


--
-- Name: ix_sn_postal_addresses_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_postal_addresses_organization_id ON public.sn_postal_addresses USING btree (organization_id);


--
-- Name: ix_sn_product_categories_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_product_categories_organization_id ON public.sn_product_categories USING btree (organization_id);


--
-- Name: ix_sn_promoter_level_log_agent_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_promoter_level_log_agent_id ON public.sn_promoter_level_log USING btree (agent_id);


--
-- Name: ix_sn_promoter_level_log_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_promoter_level_log_organization_id ON public.sn_promoter_level_log USING btree (organization_id);


--
-- Name: ix_sn_promoter_profiles_org_joined; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_promoter_profiles_org_joined ON public.sn_promoter_profiles USING btree (organization_id, joined_at);


--
-- Name: ix_sn_promoter_profiles_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_promoter_profiles_organization_id ON public.sn_promoter_profiles USING btree (organization_id);


--
-- Name: ix_sn_receipt_claims_customer_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_receipt_claims_customer_user_id ON public.sn_receipt_claims USING btree (customer_user_id);


--
-- Name: ix_sn_receipt_claims_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_receipt_claims_organization_id ON public.sn_receipt_claims USING btree (organization_id);


--
-- Name: ix_sn_receipt_claims_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_receipt_claims_status ON public.sn_receipt_claims USING btree (status);


--
-- Name: ix_sn_roles_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_roles_organization_id ON public.sn_roles USING btree (organization_id);


--
-- Name: ix_sn_seller_role_history_agent_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_seller_role_history_agent_id ON public.sn_seller_role_history USING btree (agent_id);


--
-- Name: ix_sn_seller_role_history_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_seller_role_history_organization_id ON public.sn_seller_role_history USING btree (organization_id);


--
-- Name: ix_sn_shop_orders_customer_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_shop_orders_customer_user_id ON public.sn_shop_orders USING btree (customer_user_id);


--
-- Name: ix_sn_shop_orders_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_shop_orders_organization_id ON public.sn_shop_orders USING btree (organization_id);


--
-- Name: ix_sn_shop_orders_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_shop_orders_status ON public.sn_shop_orders USING btree (status);


--
-- Name: ix_sn_shopify_item_variants_product_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_shopify_item_variants_product_id ON public.sn_shopify_item_variants USING btree (product_id);


--
-- Name: ix_sn_shopify_items_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_shopify_items_organization_id ON public.sn_shopify_items USING btree (organization_id);


--
-- Name: ix_sn_shopify_items_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_shopify_items_status ON public.sn_shopify_items USING btree (status);


--
-- Name: ix_sn_shopify_order_lines_order_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_shopify_order_lines_order_id ON public.sn_shopify_order_lines USING btree (order_id);


--
-- Name: ix_sn_shopify_orders_customer_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_shopify_orders_customer_user_id ON public.sn_shopify_orders USING btree (customer_user_id);


--
-- Name: ix_sn_shopify_orders_fulfillment_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_shopify_orders_fulfillment_status ON public.sn_shopify_orders USING btree (fulfillment_status);


--
-- Name: ix_sn_shopify_orders_next_retry_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_shopify_orders_next_retry_at ON public.sn_shopify_orders USING btree (next_retry_at);


--
-- Name: ix_sn_shopify_orders_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_shopify_orders_organization_id ON public.sn_shopify_orders USING btree (organization_id);


--
-- Name: ix_sn_shopify_orders_shopify_order_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_shopify_orders_shopify_order_id ON public.sn_shopify_orders USING btree (shopify_order_id);


--
-- Name: ix_sn_shopify_orders_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_shopify_orders_status ON public.sn_shopify_orders USING btree (status);


--
-- Name: ix_sn_stored_files_contract_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_stored_files_contract_id ON public.sn_stored_files USING btree (contract_id);


--
-- Name: ix_sn_stored_files_contract_request_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_stored_files_contract_request_id ON public.sn_stored_files USING btree (contract_request_id);


--
-- Name: ix_sn_stored_files_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_stored_files_organization_id ON public.sn_stored_files USING btree (organization_id);


--
-- Name: ix_sn_stored_files_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_stored_files_status ON public.sn_stored_files USING btree (status);


--
-- Name: ix_sn_stripe_events_event_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_stripe_events_event_type ON public.sn_stripe_events USING btree (event_type);


--
-- Name: ix_sn_stripe_events_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_stripe_events_organization_id ON public.sn_stripe_events USING btree (organization_id);


--
-- Name: ix_sn_supplier_item_orders_customer_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_supplier_item_orders_customer_user_id ON public.sn_supplier_item_orders USING btree (customer_user_id);


--
-- Name: ix_sn_supplier_item_orders_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_supplier_item_orders_organization_id ON public.sn_supplier_item_orders USING btree (organization_id);


--
-- Name: ix_sn_supplier_item_orders_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_supplier_item_orders_status ON public.sn_supplier_item_orders USING btree (status);


--
-- Name: ix_sn_supplier_items_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_supplier_items_organization_id ON public.sn_supplier_items USING btree (organization_id);


--
-- Name: ix_sn_supplier_items_provider_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_supplier_items_provider_id ON public.sn_supplier_items USING btree (provider_id);


--
-- Name: ix_sn_supplier_members_agent_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_supplier_members_agent_id ON public.sn_supplier_members USING btree (agent_id);


--
-- Name: ix_sn_supplier_members_company_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_supplier_members_company_id ON public.sn_supplier_members USING btree (company_id);


--
-- Name: ix_sn_supplier_members_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_supplier_members_organization_id ON public.sn_supplier_members USING btree (organization_id);


--
-- Name: ix_sn_supplier_sources_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_supplier_sources_organization_id ON public.sn_supplier_sources USING btree (organization_id);


--
-- Name: ix_sn_suppliers_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_suppliers_organization_id ON public.sn_suppliers USING btree (organization_id);


--
-- Name: ix_sn_support_cases_opened_by_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_support_cases_opened_by_user_id ON public.sn_support_cases USING btree (opened_by_user_id);


--
-- Name: ix_sn_support_cases_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_support_cases_organization_id ON public.sn_support_cases USING btree (organization_id);


--
-- Name: ix_sn_support_cases_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_support_cases_status ON public.sn_support_cases USING btree (status);


--
-- Name: ix_sn_support_replies_ticket_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_support_replies_ticket_id ON public.sn_support_replies USING btree (ticket_id);


--
-- Name: ix_sn_tree_links_child_agent_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_tree_links_child_agent_id ON public.sn_tree_links USING btree (child_agent_id);


--
-- Name: ix_sn_tree_links_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_tree_links_organization_id ON public.sn_tree_links USING btree (organization_id);


--
-- Name: ix_sn_tree_links_parent_agent_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_tree_links_parent_agent_id ON public.sn_tree_links USING btree (parent_agent_id);


--
-- Name: ix_sn_tree_moves_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_tree_moves_organization_id ON public.sn_tree_moves USING btree (organization_id);


--
-- Name: ix_sn_tree_nodes_agent_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_tree_nodes_agent_id ON public.sn_tree_nodes USING btree (agent_id);


--
-- Name: ix_sn_tree_nodes_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_tree_nodes_organization_id ON public.sn_tree_nodes USING btree (organization_id);


--
-- Name: ix_sn_tree_paths_org_ancestor; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_tree_paths_org_ancestor ON public.sn_tree_paths USING btree (organization_id, ancestor_agent_id);


--
-- Name: ix_sn_tree_paths_org_ancestor_depth; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_tree_paths_org_ancestor_depth ON public.sn_tree_paths USING btree (organization_id, ancestor_agent_id, depth);


--
-- Name: ix_sn_tree_paths_org_descendant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_tree_paths_org_descendant ON public.sn_tree_paths USING btree (organization_id, descendant_agent_id);


--
-- Name: ix_sn_tree_paths_org_descendant_depth; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_tree_paths_org_descendant_depth ON public.sn_tree_paths USING btree (organization_id, descendant_agent_id, depth);


--
-- Name: ix_sn_tree_snapshots_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_tree_snapshots_organization_id ON public.sn_tree_snapshots USING btree (organization_id);


--
-- Name: ix_sn_utility_points_customer_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_utility_points_customer_id ON public.sn_utility_points USING btree (customer_id);


--
-- Name: ix_sn_utility_points_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sn_utility_points_organization_id ON public.sn_utility_points USING btree (organization_id);


--
-- Name: uq_sn_aff_commissions_career_month; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_sn_aff_commissions_career_month ON public.sn_aff_commissions USING btree (organization_id, beneficiary_agent_id, period) WHERE ((kind)::text = 'BC'::text);


--
-- Name: uq_sn_aff_operations_subscription_month; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_sn_aff_operations_subscription_month ON public.sn_aff_operations USING btree (organization_id, agent_id, period) WHERE (((kind)::text = 'SUBSCRIPTION_PAYMENT'::text) AND ((status)::text <> 'CANCELLED'::text));


--
-- Name: uq_sn_catalog_sections_organization_id_shop_name; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_sn_catalog_sections_organization_id_shop_name ON public.sn_catalog_sections USING btree (organization_id, shop, lower((name)::text));


--
-- Name: uq_sn_delegations_open_delegate; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_sn_delegations_open_delegate ON public.sn_delegations USING btree (delegate_agent_id) WHERE (valid_to IS NULL);


--
-- Name: uq_sn_seller_role_history_open; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_sn_seller_role_history_open ON public.sn_seller_role_history USING btree (agent_id) WHERE (valid_to IS NULL);


--
-- Name: uq_sn_supplier_members_open; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_sn_supplier_members_open ON public.sn_supplier_members USING btree (company_id, agent_id) WHERE (left_at IS NULL);


--
-- Name: uq_sn_tree_nodes_active_agent; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_sn_tree_nodes_active_agent ON public.sn_tree_nodes USING btree (organization_id, agent_id) WHERE (effective_to IS NULL);


--
-- Name: sn_account_roles fk_sn_account_roles_organization_id_sn_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_account_roles
    ADD CONSTRAINT fk_sn_account_roles_organization_id_sn_tenants FOREIGN KEY (organization_id) REFERENCES public.sn_tenants(id);


--
-- Name: sn_account_roles fk_sn_account_roles_role_id_sn_roles; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_account_roles
    ADD CONSTRAINT fk_sn_account_roles_role_id_sn_roles FOREIGN KEY (role_id) REFERENCES public.sn_roles(id);


--
-- Name: sn_account_roles fk_sn_account_roles_user_id_sn_accounts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_account_roles
    ADD CONSTRAINT fk_sn_account_roles_user_id_sn_accounts FOREIGN KEY (user_id) REFERENCES public.sn_accounts(id);


--
-- Name: sn_accounts fk_sn_accounts_organization_id_sn_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_accounts
    ADD CONSTRAINT fk_sn_accounts_organization_id_sn_tenants FOREIGN KEY (organization_id) REFERENCES public.sn_tenants(id);


--
-- Name: sn_activity_log fk_sn_activity_log_actor_user_id_sn_accounts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_activity_log
    ADD CONSTRAINT fk_sn_activity_log_actor_user_id_sn_accounts FOREIGN KEY (actor_user_id) REFERENCES public.sn_accounts(id);


--
-- Name: sn_activity_log fk_sn_activity_log_organization_id_sn_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_activity_log
    ADD CONSTRAINT fk_sn_activity_log_organization_id_sn_tenants FOREIGN KEY (organization_id) REFERENCES public.sn_tenants(id);


--
-- Name: sn_aff_clients fk_sn_aff_clients_agent_id_sn_promoter_profiles; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_aff_clients
    ADD CONSTRAINT fk_sn_aff_clients_agent_id_sn_promoter_profiles FOREIGN KEY (agent_id) REFERENCES public.sn_promoter_profiles(id);


--
-- Name: sn_aff_clients fk_sn_aff_clients_organization_id_sn_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_aff_clients
    ADD CONSTRAINT fk_sn_aff_clients_organization_id_sn_tenants FOREIGN KEY (organization_id) REFERENCES public.sn_tenants(id);


--
-- Name: sn_aff_commissions fk_sn_aff_commissions_beneficiary_agent_id_sn_promoter_profiles; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_aff_commissions
    ADD CONSTRAINT fk_sn_aff_commissions_beneficiary_agent_id_sn_promoter_profiles FOREIGN KEY (beneficiary_agent_id) REFERENCES public.sn_promoter_profiles(id);


--
-- Name: sn_aff_commissions fk_sn_aff_commissions_operation_id_sn_aff_operations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_aff_commissions
    ADD CONSTRAINT fk_sn_aff_commissions_operation_id_sn_aff_operations FOREIGN KEY (operation_id) REFERENCES public.sn_aff_operations(id);


--
-- Name: sn_aff_commissions fk_sn_aff_commissions_organization_id_sn_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_aff_commissions
    ADD CONSTRAINT fk_sn_aff_commissions_organization_id_sn_tenants FOREIGN KEY (organization_id) REFERENCES public.sn_tenants(id);


--
-- Name: sn_aff_commissions fk_sn_aff_commissions_paid_by_user_id_sn_accounts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_aff_commissions
    ADD CONSTRAINT fk_sn_aff_commissions_paid_by_user_id_sn_accounts FOREIGN KEY (paid_by_user_id) REFERENCES public.sn_accounts(id);


--
-- Name: sn_aff_commissions fk_sn_aff_commissions_plan_version_id_sn_aff_plan_versions; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_aff_commissions
    ADD CONSTRAINT fk_sn_aff_commissions_plan_version_id_sn_aff_plan_versions FOREIGN KEY (plan_version_id) REFERENCES public.sn_aff_plan_versions(id);


--
-- Name: sn_aff_licenses fk_sn_aff_licenses_client_id_sn_aff_clients; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_aff_licenses
    ADD CONSTRAINT fk_sn_aff_licenses_client_id_sn_aff_clients FOREIGN KEY (client_id) REFERENCES public.sn_aff_clients(id);


--
-- Name: sn_aff_licenses fk_sn_aff_licenses_organization_id_sn_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_aff_licenses
    ADD CONSTRAINT fk_sn_aff_licenses_organization_id_sn_tenants FOREIGN KEY (organization_id) REFERENCES public.sn_tenants(id);


--
-- Name: sn_aff_licenses fk_sn_aff_licenses_owner_agent_id_sn_promoter_profiles; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_aff_licenses
    ADD CONSTRAINT fk_sn_aff_licenses_owner_agent_id_sn_promoter_profiles FOREIGN KEY (owner_agent_id) REFERENCES public.sn_promoter_profiles(id);


--
-- Name: sn_aff_licenses fk_sn_aff_licenses_purchase_operation_id_sn_aff_operations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_aff_licenses
    ADD CONSTRAINT fk_sn_aff_licenses_purchase_operation_id_sn_aff_operations FOREIGN KEY (purchase_operation_id) REFERENCES public.sn_aff_operations(id);


--
-- Name: sn_aff_licenses fk_sn_aff_licenses_resale_operation_id_sn_aff_operations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_aff_licenses
    ADD CONSTRAINT fk_sn_aff_licenses_resale_operation_id_sn_aff_operations FOREIGN KEY (resale_operation_id) REFERENCES public.sn_aff_operations(id);


--
-- Name: sn_aff_monthly_results fk_sn_aff_monthly_results_agent_id_sn_promoter_profiles; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_aff_monthly_results
    ADD CONSTRAINT fk_sn_aff_monthly_results_agent_id_sn_promoter_profiles FOREIGN KEY (agent_id) REFERENCES public.sn_promoter_profiles(id);


--
-- Name: sn_aff_monthly_results fk_sn_aff_monthly_results_organization_id_sn_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_aff_monthly_results
    ADD CONSTRAINT fk_sn_aff_monthly_results_organization_id_sn_tenants FOREIGN KEY (organization_id) REFERENCES public.sn_tenants(id);


--
-- Name: sn_aff_monthly_results fk_sn_aff_monthly_results_plan_version_id_sn_aff_plan_versions; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_aff_monthly_results
    ADD CONSTRAINT fk_sn_aff_monthly_results_plan_version_id_sn_aff_plan_versions FOREIGN KEY (plan_version_id) REFERENCES public.sn_aff_plan_versions(id);


--
-- Name: sn_aff_operations fk_sn_aff_operations_agent_id_sn_promoter_profiles; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_aff_operations
    ADD CONSTRAINT fk_sn_aff_operations_agent_id_sn_promoter_profiles FOREIGN KEY (agent_id) REFERENCES public.sn_promoter_profiles(id);


--
-- Name: sn_aff_operations fk_sn_aff_operations_client_id_sn_aff_clients; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_aff_operations
    ADD CONSTRAINT fk_sn_aff_operations_client_id_sn_aff_clients FOREIGN KEY (client_id) REFERENCES public.sn_aff_clients(id);


--
-- Name: sn_aff_operations fk_sn_aff_operations_confirmed_by_user_id_sn_accounts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_aff_operations
    ADD CONSTRAINT fk_sn_aff_operations_confirmed_by_user_id_sn_accounts FOREIGN KEY (confirmed_by_user_id) REFERENCES public.sn_accounts(id);


--
-- Name: sn_aff_operations fk_sn_aff_operations_created_by_user_id_sn_accounts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_aff_operations
    ADD CONSTRAINT fk_sn_aff_operations_created_by_user_id_sn_accounts FOREIGN KEY (created_by_user_id) REFERENCES public.sn_accounts(id);


--
-- Name: sn_aff_operations fk_sn_aff_operations_license_id_sn_aff_licenses; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_aff_operations
    ADD CONSTRAINT fk_sn_aff_operations_license_id_sn_aff_licenses FOREIGN KEY (license_id) REFERENCES public.sn_aff_licenses(id);


--
-- Name: sn_aff_operations fk_sn_aff_operations_organization_id_sn_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_aff_operations
    ADD CONSTRAINT fk_sn_aff_operations_organization_id_sn_tenants FOREIGN KEY (organization_id) REFERENCES public.sn_tenants(id);


--
-- Name: sn_aff_operations fk_sn_aff_operations_plan_version_id_sn_aff_plan_versions; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_aff_operations
    ADD CONSTRAINT fk_sn_aff_operations_plan_version_id_sn_aff_plan_versions FOREIGN KEY (plan_version_id) REFERENCES public.sn_aff_plan_versions(id);


--
-- Name: sn_aff_operations fk_sn_aff_operations_reverses_operation_id_sn_aff_operations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_aff_operations
    ADD CONSTRAINT fk_sn_aff_operations_reverses_operation_id_sn_aff_operations FOREIGN KEY (reverses_operation_id) REFERENCES public.sn_aff_operations(id);


--
-- Name: sn_aff_period_closes fk_sn_aff_period_closes_closed_by_user_id_sn_accounts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_aff_period_closes
    ADD CONSTRAINT fk_sn_aff_period_closes_closed_by_user_id_sn_accounts FOREIGN KEY (closed_by_user_id) REFERENCES public.sn_accounts(id);


--
-- Name: sn_aff_period_closes fk_sn_aff_period_closes_organization_id_sn_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_aff_period_closes
    ADD CONSTRAINT fk_sn_aff_period_closes_organization_id_sn_tenants FOREIGN KEY (organization_id) REFERENCES public.sn_tenants(id);


--
-- Name: sn_aff_period_closes fk_sn_aff_period_closes_plan_version_id_sn_aff_plan_versions; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_aff_period_closes
    ADD CONSTRAINT fk_sn_aff_period_closes_plan_version_id_sn_aff_plan_versions FOREIGN KEY (plan_version_id) REFERENCES public.sn_aff_plan_versions(id);


--
-- Name: sn_aff_plan_versions fk_sn_aff_plan_versions_created_by_user_id_sn_accounts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_aff_plan_versions
    ADD CONSTRAINT fk_sn_aff_plan_versions_created_by_user_id_sn_accounts FOREIGN KEY (created_by_user_id) REFERENCES public.sn_accounts(id);


--
-- Name: sn_aff_plan_versions fk_sn_aff_plan_versions_organization_id_sn_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_aff_plan_versions
    ADD CONSTRAINT fk_sn_aff_plan_versions_organization_id_sn_tenants FOREIGN KEY (organization_id) REFERENCES public.sn_tenants(id);


--
-- Name: sn_aff_points fk_sn_aff_points_agent_id_sn_promoter_profiles; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_aff_points
    ADD CONSTRAINT fk_sn_aff_points_agent_id_sn_promoter_profiles FOREIGN KEY (agent_id) REFERENCES public.sn_promoter_profiles(id);


--
-- Name: sn_aff_points fk_sn_aff_points_operation_id_sn_aff_operations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_aff_points
    ADD CONSTRAINT fk_sn_aff_points_operation_id_sn_aff_operations FOREIGN KEY (operation_id) REFERENCES public.sn_aff_operations(id);


--
-- Name: sn_aff_points fk_sn_aff_points_organization_id_sn_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_aff_points
    ADD CONSTRAINT fk_sn_aff_points_organization_id_sn_tenants FOREIGN KEY (organization_id) REFERENCES public.sn_tenants(id);


--
-- Name: sn_aff_subscriptions fk_sn_aff_subscriptions_agent_id_sn_promoter_profiles; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_aff_subscriptions
    ADD CONSTRAINT fk_sn_aff_subscriptions_agent_id_sn_promoter_profiles FOREIGN KEY (agent_id) REFERENCES public.sn_promoter_profiles(id);


--
-- Name: sn_aff_subscriptions fk_sn_aff_subscriptions_organization_id_sn_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_aff_subscriptions
    ADD CONSTRAINT fk_sn_aff_subscriptions_organization_id_sn_tenants FOREIGN KEY (organization_id) REFERENCES public.sn_tenants(id);


--
-- Name: sn_agreement_attributions fk_sn_agreement_attributions_attributed_promoter_id_sn__d013; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_agreement_attributions
    ADD CONSTRAINT fk_sn_agreement_attributions_attributed_promoter_id_sn__d013 FOREIGN KEY (attributed_promoter_id) REFERENCES public.sn_promoter_profiles(id);


--
-- Name: sn_agreement_attributions fk_sn_agreement_attributions_organization_id_sn_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_agreement_attributions
    ADD CONSTRAINT fk_sn_agreement_attributions_organization_id_sn_tenants FOREIGN KEY (organization_id) REFERENCES public.sn_tenants(id);


--
-- Name: sn_agreement_attributions fk_sn_agreement_attributions_producer_agent_id_sn_promo_5315; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_agreement_attributions
    ADD CONSTRAINT fk_sn_agreement_attributions_producer_agent_id_sn_promo_5315 FOREIGN KEY (producer_agent_id) REFERENCES public.sn_promoter_profiles(id);


--
-- Name: sn_agreement_checkouts fk_sn_agreement_checkouts_contract_request_id_sn_agreem_6e04; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_agreement_checkouts
    ADD CONSTRAINT fk_sn_agreement_checkouts_contract_request_id_sn_agreem_6e04 FOREIGN KEY (contract_request_id) REFERENCES public.sn_agreement_requests(id);


--
-- Name: sn_agreement_checkouts fk_sn_agreement_checkouts_created_by_user_id_sn_accounts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_agreement_checkouts
    ADD CONSTRAINT fk_sn_agreement_checkouts_created_by_user_id_sn_accounts FOREIGN KEY (created_by_user_id) REFERENCES public.sn_accounts(id);


--
-- Name: sn_agreement_checkouts fk_sn_agreement_checkouts_organization_id_sn_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_agreement_checkouts
    ADD CONSTRAINT fk_sn_agreement_checkouts_organization_id_sn_tenants FOREIGN KEY (organization_id) REFERENCES public.sn_tenants(id);


--
-- Name: sn_agreement_events fk_sn_agreement_events_contract_id_sn_agreements; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_agreement_events
    ADD CONSTRAINT fk_sn_agreement_events_contract_id_sn_agreements FOREIGN KEY (contract_id) REFERENCES public.sn_agreements(id);


--
-- Name: sn_agreement_instalments fk_sn_agreement_instalments_commission_calculation_id_s_a19a; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_agreement_instalments
    ADD CONSTRAINT fk_sn_agreement_instalments_commission_calculation_id_s_a19a FOREIGN KEY (commission_calculation_id) REFERENCES public.sn_payout_runs(id);


--
-- Name: sn_agreement_instalments fk_sn_agreement_instalments_confirmed_by_user_id_sn_accounts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_agreement_instalments
    ADD CONSTRAINT fk_sn_agreement_instalments_confirmed_by_user_id_sn_accounts FOREIGN KEY (confirmed_by_user_id) REFERENCES public.sn_accounts(id);


--
-- Name: sn_agreement_instalments fk_sn_agreement_instalments_contract_id_sn_agreements; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_agreement_instalments
    ADD CONSTRAINT fk_sn_agreement_instalments_contract_id_sn_agreements FOREIGN KEY (contract_id) REFERENCES public.sn_agreements(id);


--
-- Name: sn_agreement_instalments fk_sn_agreement_instalments_organization_id_sn_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_agreement_instalments
    ADD CONSTRAINT fk_sn_agreement_instalments_organization_id_sn_tenants FOREIGN KEY (organization_id) REFERENCES public.sn_tenants(id);


--
-- Name: sn_agreement_payout_plans fk_sn_agreement_payout_plans_accepted_by_user_id_sn_accounts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_agreement_payout_plans
    ADD CONSTRAINT fk_sn_agreement_payout_plans_accepted_by_user_id_sn_accounts FOREIGN KEY (accepted_by_user_id) REFERENCES public.sn_accounts(id);


--
-- Name: sn_agreement_payout_plans fk_sn_agreement_payout_plans_contract_id_sn_agreements; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_agreement_payout_plans
    ADD CONSTRAINT fk_sn_agreement_payout_plans_contract_id_sn_agreements FOREIGN KEY (contract_id) REFERENCES public.sn_agreements(id);


--
-- Name: sn_agreement_payout_plans fk_sn_agreement_payout_plans_organization_id_sn_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_agreement_payout_plans
    ADD CONSTRAINT fk_sn_agreement_payout_plans_organization_id_sn_tenants FOREIGN KEY (organization_id) REFERENCES public.sn_tenants(id);


--
-- Name: sn_agreement_requests fk_sn_agreement_requests_activated_by_promoter_id_sn_pr_5845; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_agreement_requests
    ADD CONSTRAINT fk_sn_agreement_requests_activated_by_promoter_id_sn_pr_5845 FOREIGN KEY (activated_by_promoter_id) REFERENCES public.sn_promoter_profiles(id);


--
-- Name: sn_agreement_requests fk_sn_agreement_requests_bank_transfer_confirmed_by_use_a464; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_agreement_requests
    ADD CONSTRAINT fk_sn_agreement_requests_bank_transfer_confirmed_by_use_a464 FOREIGN KEY (bank_transfer_confirmed_by_user_id) REFERENCES public.sn_accounts(id);


--
-- Name: sn_agreement_requests fk_sn_agreement_requests_created_by_user_id_sn_accounts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_agreement_requests
    ADD CONSTRAINT fk_sn_agreement_requests_created_by_user_id_sn_accounts FOREIGN KEY (created_by_user_id) REFERENCES public.sn_accounts(id);


--
-- Name: sn_agreement_requests fk_sn_agreement_requests_customer_id_sn_clients; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_agreement_requests
    ADD CONSTRAINT fk_sn_agreement_requests_customer_id_sn_clients FOREIGN KEY (customer_id) REFERENCES public.sn_clients(id);


--
-- Name: sn_agreement_requests fk_sn_agreement_requests_organization_id_sn_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_agreement_requests
    ADD CONSTRAINT fk_sn_agreement_requests_organization_id_sn_tenants FOREIGN KEY (organization_id) REFERENCES public.sn_tenants(id);


--
-- Name: sn_agreement_status_log fk_sn_agreement_status_log_actor_user_id_sn_accounts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_agreement_status_log
    ADD CONSTRAINT fk_sn_agreement_status_log_actor_user_id_sn_accounts FOREIGN KEY (actor_user_id) REFERENCES public.sn_accounts(id);


--
-- Name: sn_agreement_status_log fk_sn_agreement_status_log_contract_id_sn_agreements; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_agreement_status_log
    ADD CONSTRAINT fk_sn_agreement_status_log_contract_id_sn_agreements FOREIGN KEY (contract_id) REFERENCES public.sn_agreements(id);


--
-- Name: sn_agreements fk_sn_agreements_activated_by_promoter_id_sn_promoter_profiles; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_agreements
    ADD CONSTRAINT fk_sn_agreements_activated_by_promoter_id_sn_promoter_profiles FOREIGN KEY (activated_by_promoter_id) REFERENCES public.sn_promoter_profiles(id);


--
-- Name: sn_agreements fk_sn_agreements_contract_attribution_id_sn_agreement_a_8f51; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_agreements
    ADD CONSTRAINT fk_sn_agreements_contract_attribution_id_sn_agreement_a_8f51 FOREIGN KEY (contract_attribution_id) REFERENCES public.sn_agreement_attributions(id);


--
-- Name: sn_agreements fk_sn_agreements_contract_request_id_sn_agreement_requests; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_agreements
    ADD CONSTRAINT fk_sn_agreements_contract_request_id_sn_agreement_requests FOREIGN KEY (contract_request_id) REFERENCES public.sn_agreement_requests(id);


--
-- Name: sn_agreements fk_sn_agreements_created_by_user_id_sn_accounts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_agreements
    ADD CONSTRAINT fk_sn_agreements_created_by_user_id_sn_accounts FOREIGN KEY (created_by_user_id) REFERENCES public.sn_accounts(id);


--
-- Name: sn_agreements fk_sn_agreements_customer_id_sn_clients; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_agreements
    ADD CONSTRAINT fk_sn_agreements_customer_id_sn_clients FOREIGN KEY (customer_id) REFERENCES public.sn_clients(id);


--
-- Name: sn_agreements fk_sn_agreements_first_referrer_agent_id_sn_promoter_profiles; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_agreements
    ADD CONSTRAINT fk_sn_agreements_first_referrer_agent_id_sn_promoter_profiles FOREIGN KEY (first_referrer_agent_id) REFERENCES public.sn_promoter_profiles(id);


--
-- Name: sn_agreements fk_sn_agreements_lead_id_sn_leads; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_agreements
    ADD CONSTRAINT fk_sn_agreements_lead_id_sn_leads FOREIGN KEY (lead_id) REFERENCES public.sn_leads(id);


--
-- Name: sn_agreements fk_sn_agreements_network_snapshot_id_sn_tree_snapshots; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_agreements
    ADD CONSTRAINT fk_sn_agreements_network_snapshot_id_sn_tree_snapshots FOREIGN KEY (network_snapshot_id) REFERENCES public.sn_tree_snapshots(id);


--
-- Name: sn_agreements fk_sn_agreements_organization_id_sn_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_agreements
    ADD CONSTRAINT fk_sn_agreements_organization_id_sn_tenants FOREIGN KEY (organization_id) REFERENCES public.sn_tenants(id);


--
-- Name: sn_agreements fk_sn_agreements_product_version_id_sn_offer_versions; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_agreements
    ADD CONSTRAINT fk_sn_agreements_product_version_id_sn_offer_versions FOREIGN KEY (product_version_id) REFERENCES public.sn_offer_versions(id);


--
-- Name: sn_agreements fk_sn_agreements_split_plan_id_sn_payout_plans; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_agreements
    ADD CONSTRAINT fk_sn_agreements_split_plan_id_sn_payout_plans FOREIGN KEY (split_plan_id) REFERENCES public.sn_payout_plans(id);


--
-- Name: sn_agreements fk_sn_agreements_supply_point_id_sn_utility_points; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_agreements
    ADD CONSTRAINT fk_sn_agreements_supply_point_id_sn_utility_points FOREIGN KEY (supply_point_id) REFERENCES public.sn_utility_points(id);


--
-- Name: sn_agreements fk_sn_agreements_terms_accepted_by_user_id_sn_accounts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_agreements
    ADD CONSTRAINT fk_sn_agreements_terms_accepted_by_user_id_sn_accounts FOREIGN KEY (terms_accepted_by_user_id) REFERENCES public.sn_accounts(id);


--
-- Name: sn_aliexpress_config fk_sn_aliexpress_config_organization_id_sn_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_aliexpress_config
    ADD CONSTRAINT fk_sn_aliexpress_config_organization_id_sn_tenants FOREIGN KEY (organization_id) REFERENCES public.sn_tenants(id);


--
-- Name: sn_aliexpress_item_variants fk_sn_aliexpress_item_variants_product_id_sn_aliexpress_items; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_aliexpress_item_variants
    ADD CONSTRAINT fk_sn_aliexpress_item_variants_product_id_sn_aliexpress_items FOREIGN KEY (product_id) REFERENCES public.sn_aliexpress_items(id);


--
-- Name: sn_aliexpress_items fk_sn_aliexpress_items_created_by_user_id_sn_accounts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_aliexpress_items
    ADD CONSTRAINT fk_sn_aliexpress_items_created_by_user_id_sn_accounts FOREIGN KEY (created_by_user_id) REFERENCES public.sn_accounts(id);


--
-- Name: sn_aliexpress_items fk_sn_aliexpress_items_organization_id_sn_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_aliexpress_items
    ADD CONSTRAINT fk_sn_aliexpress_items_organization_id_sn_tenants FOREIGN KEY (organization_id) REFERENCES public.sn_tenants(id);


--
-- Name: sn_aliexpress_order_lines fk_sn_aliexpress_order_lines_aliexpress_product_id_sn_a_9e1e; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_aliexpress_order_lines
    ADD CONSTRAINT fk_sn_aliexpress_order_lines_aliexpress_product_id_sn_a_9e1e FOREIGN KEY (aliexpress_product_id) REFERENCES public.sn_aliexpress_items(id);


--
-- Name: sn_aliexpress_order_lines fk_sn_aliexpress_order_lines_aliexpress_variant_id_sn_a_9d89; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_aliexpress_order_lines
    ADD CONSTRAINT fk_sn_aliexpress_order_lines_aliexpress_variant_id_sn_a_9d89 FOREIGN KEY (aliexpress_variant_id) REFERENCES public.sn_aliexpress_item_variants(id);


--
-- Name: sn_aliexpress_order_lines fk_sn_aliexpress_order_lines_order_id_sn_aliexpress_orders; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_aliexpress_order_lines
    ADD CONSTRAINT fk_sn_aliexpress_order_lines_order_id_sn_aliexpress_orders FOREIGN KEY (order_id) REFERENCES public.sn_aliexpress_orders(id) ON DELETE CASCADE;


--
-- Name: sn_aliexpress_orders fk_sn_aliexpress_orders_aliexpress_product_id_sn_aliexp_2429; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_aliexpress_orders
    ADD CONSTRAINT fk_sn_aliexpress_orders_aliexpress_product_id_sn_aliexp_2429 FOREIGN KEY (aliexpress_product_id) REFERENCES public.sn_aliexpress_items(id);


--
-- Name: sn_aliexpress_orders fk_sn_aliexpress_orders_aliexpress_variant_id_sn_aliexp_bb27; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_aliexpress_orders
    ADD CONSTRAINT fk_sn_aliexpress_orders_aliexpress_variant_id_sn_aliexp_bb27 FOREIGN KEY (aliexpress_variant_id) REFERENCES public.sn_aliexpress_item_variants(id);


--
-- Name: sn_aliexpress_orders fk_sn_aliexpress_orders_cancelled_by_user_id_sn_accounts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_aliexpress_orders
    ADD CONSTRAINT fk_sn_aliexpress_orders_cancelled_by_user_id_sn_accounts FOREIGN KEY (cancelled_by_user_id) REFERENCES public.sn_accounts(id);


--
-- Name: sn_aliexpress_orders fk_sn_aliexpress_orders_created_by_user_id_sn_accounts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_aliexpress_orders
    ADD CONSTRAINT fk_sn_aliexpress_orders_created_by_user_id_sn_accounts FOREIGN KEY (created_by_user_id) REFERENCES public.sn_accounts(id);


--
-- Name: sn_aliexpress_orders fk_sn_aliexpress_orders_credit_debit_transaction_id_sn__25b9; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_aliexpress_orders
    ADD CONSTRAINT fk_sn_aliexpress_orders_credit_debit_transaction_id_sn__25b9 FOREIGN KEY (credit_debit_transaction_id) REFERENCES public.sn_credit_ledger(id);


--
-- Name: sn_aliexpress_orders fk_sn_aliexpress_orders_customer_user_id_sn_accounts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_aliexpress_orders
    ADD CONSTRAINT fk_sn_aliexpress_orders_customer_user_id_sn_accounts FOREIGN KEY (customer_user_id) REFERENCES public.sn_accounts(id);


--
-- Name: sn_aliexpress_orders fk_sn_aliexpress_orders_forwarded_by_user_id_sn_accounts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_aliexpress_orders
    ADD CONSTRAINT fk_sn_aliexpress_orders_forwarded_by_user_id_sn_accounts FOREIGN KEY (forwarded_by_user_id) REFERENCES public.sn_accounts(id);


--
-- Name: sn_aliexpress_orders fk_sn_aliexpress_orders_organization_id_sn_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_aliexpress_orders
    ADD CONSTRAINT fk_sn_aliexpress_orders_organization_id_sn_tenants FOREIGN KEY (organization_id) REFERENCES public.sn_tenants(id);


--
-- Name: sn_aliexpress_orders fk_sn_aliexpress_orders_paid_by_user_id_sn_accounts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_aliexpress_orders
    ADD CONSTRAINT fk_sn_aliexpress_orders_paid_by_user_id_sn_accounts FOREIGN KEY (paid_by_user_id) REFERENCES public.sn_accounts(id);


--
-- Name: sn_attribution_fixes fk_sn_attribution_fixes_approved_by_sn_accounts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_attribution_fixes
    ADD CONSTRAINT fk_sn_attribution_fixes_approved_by_sn_accounts FOREIGN KEY (approved_by) REFERENCES public.sn_accounts(id);


--
-- Name: sn_attribution_fixes fk_sn_attribution_fixes_customer_attribution_id_sn_clie_c5c6; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_attribution_fixes
    ADD CONSTRAINT fk_sn_attribution_fixes_customer_attribution_id_sn_clie_c5c6 FOREIGN KEY (customer_attribution_id) REFERENCES public.sn_client_attributions(id);


--
-- Name: sn_attribution_fixes fk_sn_attribution_fixes_new_promoter_code_id_sn_invite_codes; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_attribution_fixes
    ADD CONSTRAINT fk_sn_attribution_fixes_new_promoter_code_id_sn_invite_codes FOREIGN KEY (new_promoter_code_id) REFERENCES public.sn_invite_codes(id);


--
-- Name: sn_attribution_fixes fk_sn_attribution_fixes_organization_id_sn_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_attribution_fixes
    ADD CONSTRAINT fk_sn_attribution_fixes_organization_id_sn_tenants FOREIGN KEY (organization_id) REFERENCES public.sn_tenants(id);


--
-- Name: sn_attribution_fixes fk_sn_attribution_fixes_previous_promoter_code_id_sn_in_0517; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_attribution_fixes
    ADD CONSTRAINT fk_sn_attribution_fixes_previous_promoter_code_id_sn_in_0517 FOREIGN KEY (previous_promoter_code_id) REFERENCES public.sn_invite_codes(id);


--
-- Name: sn_attribution_fixes fk_sn_attribution_fixes_requested_by_sn_accounts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_attribution_fixes
    ADD CONSTRAINT fk_sn_attribution_fixes_requested_by_sn_accounts FOREIGN KEY (requested_by) REFERENCES public.sn_accounts(id);


--
-- Name: sn_basket_lines fk_sn_basket_lines_aliexpress_variant_id_sn_aliexpress__cf89; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_basket_lines
    ADD CONSTRAINT fk_sn_basket_lines_aliexpress_variant_id_sn_aliexpress__cf89 FOREIGN KEY (aliexpress_variant_id) REFERENCES public.sn_aliexpress_item_variants(id) ON DELETE CASCADE;


--
-- Name: sn_basket_lines fk_sn_basket_lines_cart_id_sn_baskets; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_basket_lines
    ADD CONSTRAINT fk_sn_basket_lines_cart_id_sn_baskets FOREIGN KEY (cart_id) REFERENCES public.sn_baskets(id) ON DELETE CASCADE;


--
-- Name: sn_basket_lines fk_sn_basket_lines_cj_variant_id_sn_cj_item_variants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_basket_lines
    ADD CONSTRAINT fk_sn_basket_lines_cj_variant_id_sn_cj_item_variants FOREIGN KEY (cj_variant_id) REFERENCES public.sn_cj_item_variants(id) ON DELETE CASCADE;


--
-- Name: sn_basket_lines fk_sn_basket_lines_product_version_id_sn_offer_versions; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_basket_lines
    ADD CONSTRAINT fk_sn_basket_lines_product_version_id_sn_offer_versions FOREIGN KEY (product_version_id) REFERENCES public.sn_offer_versions(id) ON DELETE CASCADE;


--
-- Name: sn_basket_lines fk_sn_basket_lines_shopify_variant_id_sn_shopify_item_variants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_basket_lines
    ADD CONSTRAINT fk_sn_basket_lines_shopify_variant_id_sn_shopify_item_variants FOREIGN KEY (shopify_variant_id) REFERENCES public.sn_shopify_item_variants(id) ON DELETE CASCADE;


--
-- Name: sn_basket_lines fk_sn_basket_lines_sosnet_market_variant_id_sn_market_i_f323; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_basket_lines
    ADD CONSTRAINT fk_sn_basket_lines_sosnet_market_variant_id_sn_market_i_f323 FOREIGN KEY (sosnet_market_variant_id) REFERENCES public.sn_market_item_variants(id) ON DELETE CASCADE;


--
-- Name: sn_baskets fk_sn_baskets_customer_user_id_sn_accounts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_baskets
    ADD CONSTRAINT fk_sn_baskets_customer_user_id_sn_accounts FOREIGN KEY (customer_user_id) REFERENCES public.sn_accounts(id);


--
-- Name: sn_baskets fk_sn_baskets_organization_id_sn_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_baskets
    ADD CONSTRAINT fk_sn_baskets_organization_id_sn_tenants FOREIGN KEY (organization_id) REFERENCES public.sn_tenants(id);


--
-- Name: sn_businesses fk_sn_businesses_customer_id_sn_clients; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_businesses
    ADD CONSTRAINT fk_sn_businesses_customer_id_sn_clients FOREIGN KEY (customer_id) REFERENCES public.sn_clients(id);


--
-- Name: sn_career_levels fk_sn_career_levels_organization_id_sn_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_career_levels
    ADD CONSTRAINT fk_sn_career_levels_organization_id_sn_tenants FOREIGN KEY (organization_id) REFERENCES public.sn_tenants(id);


--
-- Name: sn_catalog_section_items fk_sn_catalog_section_items_category_id_sn_catalog_sections; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_catalog_section_items
    ADD CONSTRAINT fk_sn_catalog_section_items_category_id_sn_catalog_sections FOREIGN KEY (category_id) REFERENCES public.sn_catalog_sections(id) ON DELETE CASCADE;


--
-- Name: sn_catalog_section_items fk_sn_catalog_section_items_organization_id_sn_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_catalog_section_items
    ADD CONSTRAINT fk_sn_catalog_section_items_organization_id_sn_tenants FOREIGN KEY (organization_id) REFERENCES public.sn_tenants(id);


--
-- Name: sn_catalog_sections fk_sn_catalog_sections_organization_id_sn_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_catalog_sections
    ADD CONSTRAINT fk_sn_catalog_sections_organization_id_sn_tenants FOREIGN KEY (organization_id) REFERENCES public.sn_tenants(id);


--
-- Name: sn_cj_config fk_sn_cj_config_organization_id_sn_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_cj_config
    ADD CONSTRAINT fk_sn_cj_config_organization_id_sn_tenants FOREIGN KEY (organization_id) REFERENCES public.sn_tenants(id);


--
-- Name: sn_cj_item_variants fk_sn_cj_item_variants_product_id_sn_cj_items; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_cj_item_variants
    ADD CONSTRAINT fk_sn_cj_item_variants_product_id_sn_cj_items FOREIGN KEY (product_id) REFERENCES public.sn_cj_items(id);


--
-- Name: sn_cj_items fk_sn_cj_items_created_by_user_id_sn_accounts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_cj_items
    ADD CONSTRAINT fk_sn_cj_items_created_by_user_id_sn_accounts FOREIGN KEY (created_by_user_id) REFERENCES public.sn_accounts(id);


--
-- Name: sn_cj_items fk_sn_cj_items_organization_id_sn_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_cj_items
    ADD CONSTRAINT fk_sn_cj_items_organization_id_sn_tenants FOREIGN KEY (organization_id) REFERENCES public.sn_tenants(id);


--
-- Name: sn_cj_order_lines fk_sn_cj_order_lines_order_id_sn_cj_orders; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_cj_order_lines
    ADD CONSTRAINT fk_sn_cj_order_lines_order_id_sn_cj_orders FOREIGN KEY (order_id) REFERENCES public.sn_cj_orders(id) ON DELETE CASCADE;


--
-- Name: sn_cj_order_lines fk_sn_cj_order_lines_product_id_sn_cj_items; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_cj_order_lines
    ADD CONSTRAINT fk_sn_cj_order_lines_product_id_sn_cj_items FOREIGN KEY (product_id) REFERENCES public.sn_cj_items(id);


--
-- Name: sn_cj_order_lines fk_sn_cj_order_lines_variant_id_sn_cj_item_variants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_cj_order_lines
    ADD CONSTRAINT fk_sn_cj_order_lines_variant_id_sn_cj_item_variants FOREIGN KEY (variant_id) REFERENCES public.sn_cj_item_variants(id);


--
-- Name: sn_cj_orders fk_sn_cj_orders_cancelled_by_user_id_sn_accounts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_cj_orders
    ADD CONSTRAINT fk_sn_cj_orders_cancelled_by_user_id_sn_accounts FOREIGN KEY (cancelled_by_user_id) REFERENCES public.sn_accounts(id);


--
-- Name: sn_cj_orders fk_sn_cj_orders_cj_product_id_sn_cj_items; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_cj_orders
    ADD CONSTRAINT fk_sn_cj_orders_cj_product_id_sn_cj_items FOREIGN KEY (cj_product_id) REFERENCES public.sn_cj_items(id);


--
-- Name: sn_cj_orders fk_sn_cj_orders_cj_variant_id_sn_cj_item_variants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_cj_orders
    ADD CONSTRAINT fk_sn_cj_orders_cj_variant_id_sn_cj_item_variants FOREIGN KEY (cj_variant_id) REFERENCES public.sn_cj_item_variants(id);


--
-- Name: sn_cj_orders fk_sn_cj_orders_created_by_user_id_sn_accounts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_cj_orders
    ADD CONSTRAINT fk_sn_cj_orders_created_by_user_id_sn_accounts FOREIGN KEY (created_by_user_id) REFERENCES public.sn_accounts(id);


--
-- Name: sn_cj_orders fk_sn_cj_orders_credit_debit_transaction_id_sn_credit_ledger; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_cj_orders
    ADD CONSTRAINT fk_sn_cj_orders_credit_debit_transaction_id_sn_credit_ledger FOREIGN KEY (credit_debit_transaction_id) REFERENCES public.sn_credit_ledger(id);


--
-- Name: sn_cj_orders fk_sn_cj_orders_customer_user_id_sn_accounts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_cj_orders
    ADD CONSTRAINT fk_sn_cj_orders_customer_user_id_sn_accounts FOREIGN KEY (customer_user_id) REFERENCES public.sn_accounts(id);


--
-- Name: sn_cj_orders fk_sn_cj_orders_forwarded_by_user_id_sn_accounts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_cj_orders
    ADD CONSTRAINT fk_sn_cj_orders_forwarded_by_user_id_sn_accounts FOREIGN KEY (forwarded_by_user_id) REFERENCES public.sn_accounts(id);


--
-- Name: sn_cj_orders fk_sn_cj_orders_organization_id_sn_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_cj_orders
    ADD CONSTRAINT fk_sn_cj_orders_organization_id_sn_tenants FOREIGN KEY (organization_id) REFERENCES public.sn_tenants(id);


--
-- Name: sn_cj_orders fk_sn_cj_orders_paid_by_user_id_sn_accounts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_cj_orders
    ADD CONSTRAINT fk_sn_cj_orders_paid_by_user_id_sn_accounts FOREIGN KEY (paid_by_user_id) REFERENCES public.sn_accounts(id);


--
-- Name: sn_client_attributions fk_sn_client_attributions_customer_id_sn_clients; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_client_attributions
    ADD CONSTRAINT fk_sn_client_attributions_customer_id_sn_clients FOREIGN KEY (customer_id) REFERENCES public.sn_clients(id);


--
-- Name: sn_client_attributions fk_sn_client_attributions_organization_id_sn_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_client_attributions
    ADD CONSTRAINT fk_sn_client_attributions_organization_id_sn_tenants FOREIGN KEY (organization_id) REFERENCES public.sn_tenants(id);


--
-- Name: sn_client_attributions fk_sn_client_attributions_promoter_code_id_sn_invite_codes; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_client_attributions
    ADD CONSTRAINT fk_sn_client_attributions_promoter_code_id_sn_invite_codes FOREIGN KEY (promoter_code_id) REFERENCES public.sn_invite_codes(id);


--
-- Name: sn_client_attributions fk_sn_client_attributions_referral_session_id_sn_invite_visits; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_client_attributions
    ADD CONSTRAINT fk_sn_client_attributions_referral_session_id_sn_invite_visits FOREIGN KEY (referral_session_id) REFERENCES public.sn_invite_visits(id);


--
-- Name: sn_client_profiles fk_sn_client_profiles_customer_id_sn_clients; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_client_profiles
    ADD CONSTRAINT fk_sn_client_profiles_customer_id_sn_clients FOREIGN KEY (customer_id) REFERENCES public.sn_clients(id);


--
-- Name: sn_clients fk_sn_clients_organization_id_sn_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_clients
    ADD CONSTRAINT fk_sn_clients_organization_id_sn_tenants FOREIGN KEY (organization_id) REFERENCES public.sn_tenants(id);


--
-- Name: sn_clients fk_sn_clients_user_id_sn_accounts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_clients
    ADD CONSTRAINT fk_sn_clients_user_id_sn_accounts FOREIGN KEY (user_id) REFERENCES public.sn_accounts(id);


--
-- Name: sn_commercial_roles fk_sn_commercial_roles_organization_id_sn_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_commercial_roles
    ADD CONSTRAINT fk_sn_commercial_roles_organization_id_sn_tenants FOREIGN KEY (organization_id) REFERENCES public.sn_tenants(id);


--
-- Name: sn_credit_accounts fk_sn_credit_accounts_organization_id_sn_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_credit_accounts
    ADD CONSTRAINT fk_sn_credit_accounts_organization_id_sn_tenants FOREIGN KEY (organization_id) REFERENCES public.sn_tenants(id);


--
-- Name: sn_credit_accounts fk_sn_credit_accounts_user_id_sn_accounts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_credit_accounts
    ADD CONSTRAINT fk_sn_credit_accounts_user_id_sn_accounts FOREIGN KEY (user_id) REFERENCES public.sn_accounts(id);


--
-- Name: sn_credit_ledger fk_sn_credit_ledger_actor_user_id_sn_accounts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_credit_ledger
    ADD CONSTRAINT fk_sn_credit_ledger_actor_user_id_sn_accounts FOREIGN KEY (actor_user_id) REFERENCES public.sn_accounts(id);


--
-- Name: sn_credit_ledger fk_sn_credit_ledger_from_wallet_id_sn_credit_accounts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_credit_ledger
    ADD CONSTRAINT fk_sn_credit_ledger_from_wallet_id_sn_credit_accounts FOREIGN KEY (from_wallet_id) REFERENCES public.sn_credit_accounts(id);


--
-- Name: sn_credit_ledger fk_sn_credit_ledger_organization_id_sn_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_credit_ledger
    ADD CONSTRAINT fk_sn_credit_ledger_organization_id_sn_tenants FOREIGN KEY (organization_id) REFERENCES public.sn_tenants(id);


--
-- Name: sn_credit_ledger fk_sn_credit_ledger_reference_aliexpress_order_id_sn_al_e1b3; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_credit_ledger
    ADD CONSTRAINT fk_sn_credit_ledger_reference_aliexpress_order_id_sn_al_e1b3 FOREIGN KEY (reference_aliexpress_order_id) REFERENCES public.sn_aliexpress_orders(id);


--
-- Name: sn_credit_ledger fk_sn_credit_ledger_reference_cj_order_id_sn_cj_orders; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_credit_ledger
    ADD CONSTRAINT fk_sn_credit_ledger_reference_cj_order_id_sn_cj_orders FOREIGN KEY (reference_cj_order_id) REFERENCES public.sn_cj_orders(id);


--
-- Name: sn_credit_ledger fk_sn_credit_ledger_reference_contract_id_sn_agreements; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_credit_ledger
    ADD CONSTRAINT fk_sn_credit_ledger_reference_contract_id_sn_agreements FOREIGN KEY (reference_contract_id) REFERENCES public.sn_agreements(id);


--
-- Name: sn_credit_ledger fk_sn_credit_ledger_reference_imported_order_id_sn_supp_1e22; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_credit_ledger
    ADD CONSTRAINT fk_sn_credit_ledger_reference_imported_order_id_sn_supp_1e22 FOREIGN KEY (reference_imported_order_id) REFERENCES public.sn_supplier_item_orders(id);


--
-- Name: sn_credit_ledger fk_sn_credit_ledger_reference_invoice_redemption_id_sn__2da8; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_credit_ledger
    ADD CONSTRAINT fk_sn_credit_ledger_reference_invoice_redemption_id_sn__2da8 FOREIGN KEY (reference_invoice_redemption_id) REFERENCES public.sn_receipt_claims(id);


--
-- Name: sn_credit_ledger fk_sn_credit_ledger_reference_order_id_sn_shop_orders; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_credit_ledger
    ADD CONSTRAINT fk_sn_credit_ledger_reference_order_id_sn_shop_orders FOREIGN KEY (reference_order_id) REFERENCES public.sn_shop_orders(id);


--
-- Name: sn_credit_ledger fk_sn_credit_ledger_reference_shopify_order_id_sn_shopi_5f73; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_credit_ledger
    ADD CONSTRAINT fk_sn_credit_ledger_reference_shopify_order_id_sn_shopi_5f73 FOREIGN KEY (reference_shopify_order_id) REFERENCES public.sn_shopify_orders(id);


--
-- Name: sn_credit_ledger fk_sn_credit_ledger_reference_sosnet_market_order_id_sn_16af; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_credit_ledger
    ADD CONSTRAINT fk_sn_credit_ledger_reference_sosnet_market_order_id_sn_16af FOREIGN KEY (reference_sosnet_market_order_id) REFERENCES public.sn_market_orders(id);


--
-- Name: sn_credit_ledger fk_sn_credit_ledger_reverses_transaction_id_sn_credit_ledger; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_credit_ledger
    ADD CONSTRAINT fk_sn_credit_ledger_reverses_transaction_id_sn_credit_ledger FOREIGN KEY (reverses_transaction_id) REFERENCES public.sn_credit_ledger(id);


--
-- Name: sn_credit_ledger fk_sn_credit_ledger_to_wallet_id_sn_credit_accounts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_credit_ledger
    ADD CONSTRAINT fk_sn_credit_ledger_to_wallet_id_sn_credit_accounts FOREIGN KEY (to_wallet_id) REFERENCES public.sn_credit_accounts(id);


--
-- Name: sn_delegations fk_sn_delegations_created_by_user_id_sn_accounts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_delegations
    ADD CONSTRAINT fk_sn_delegations_created_by_user_id_sn_accounts FOREIGN KEY (created_by_user_id) REFERENCES public.sn_accounts(id);


--
-- Name: sn_delegations fk_sn_delegations_delegate_agent_id_sn_promoter_profiles; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_delegations
    ADD CONSTRAINT fk_sn_delegations_delegate_agent_id_sn_promoter_profiles FOREIGN KEY (delegate_agent_id) REFERENCES public.sn_promoter_profiles(id);


--
-- Name: sn_delegations fk_sn_delegations_influencer_agent_id_sn_promoter_profiles; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_delegations
    ADD CONSTRAINT fk_sn_delegations_influencer_agent_id_sn_promoter_profiles FOREIGN KEY (influencer_agent_id) REFERENCES public.sn_promoter_profiles(id);


--
-- Name: sn_delegations fk_sn_delegations_organization_id_sn_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_delegations
    ADD CONSTRAINT fk_sn_delegations_organization_id_sn_tenants FOREIGN KEY (organization_id) REFERENCES public.sn_tenants(id);


--
-- Name: sn_email_confirmations fk_sn_email_confirmations_user_id_sn_accounts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_email_confirmations
    ADD CONSTRAINT fk_sn_email_confirmations_user_id_sn_accounts FOREIGN KEY (user_id) REFERENCES public.sn_accounts(id);


--
-- Name: sn_event_outbox fk_sn_event_outbox_organization_id_sn_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_event_outbox
    ADD CONSTRAINT fk_sn_event_outbox_organization_id_sn_tenants FOREIGN KEY (organization_id) REFERENCES public.sn_tenants(id);


--
-- Name: sn_friend_invite_codes fk_sn_friend_invite_codes_organization_id_sn_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_friend_invite_codes
    ADD CONSTRAINT fk_sn_friend_invite_codes_organization_id_sn_tenants FOREIGN KEY (organization_id) REFERENCES public.sn_tenants(id);


--
-- Name: sn_friend_invite_codes fk_sn_friend_invite_codes_user_id_sn_accounts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_friend_invite_codes
    ADD CONSTRAINT fk_sn_friend_invite_codes_user_id_sn_accounts FOREIGN KEY (user_id) REFERENCES public.sn_accounts(id);


--
-- Name: sn_friend_invite_rewards fk_sn_friend_invite_rewards_handled_by_user_id_sn_accounts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_friend_invite_rewards
    ADD CONSTRAINT fk_sn_friend_invite_rewards_handled_by_user_id_sn_accounts FOREIGN KEY (handled_by_user_id) REFERENCES public.sn_accounts(id);


--
-- Name: sn_friend_invite_rewards fk_sn_friend_invite_rewards_organization_id_sn_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_friend_invite_rewards
    ADD CONSTRAINT fk_sn_friend_invite_rewards_organization_id_sn_tenants FOREIGN KEY (organization_id) REFERENCES public.sn_tenants(id);


--
-- Name: sn_friend_invite_rewards fk_sn_friend_invite_rewards_referrer_user_id_sn_accounts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_friend_invite_rewards
    ADD CONSTRAINT fk_sn_friend_invite_rewards_referrer_user_id_sn_accounts FOREIGN KEY (referrer_user_id) REFERENCES public.sn_accounts(id);


--
-- Name: sn_friend_invites fk_sn_friend_invites_organization_id_sn_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_friend_invites
    ADD CONSTRAINT fk_sn_friend_invites_organization_id_sn_tenants FOREIGN KEY (organization_id) REFERENCES public.sn_tenants(id);


--
-- Name: sn_friend_invites fk_sn_friend_invites_referred_customer_id_sn_clients; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_friend_invites
    ADD CONSTRAINT fk_sn_friend_invites_referred_customer_id_sn_clients FOREIGN KEY (referred_customer_id) REFERENCES public.sn_clients(id);


--
-- Name: sn_friend_invites fk_sn_friend_invites_referrer_user_id_sn_accounts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_friend_invites
    ADD CONSTRAINT fk_sn_friend_invites_referrer_user_id_sn_accounts FOREIGN KEY (referrer_user_id) REFERENCES public.sn_accounts(id);


--
-- Name: sn_inbox_messages fk_sn_inbox_messages_organization_id_sn_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_inbox_messages
    ADD CONSTRAINT fk_sn_inbox_messages_organization_id_sn_tenants FOREIGN KEY (organization_id) REFERENCES public.sn_tenants(id);


--
-- Name: sn_inbox_messages fk_sn_inbox_messages_recipient_user_id_sn_accounts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_inbox_messages
    ADD CONSTRAINT fk_sn_inbox_messages_recipient_user_id_sn_accounts FOREIGN KEY (recipient_user_id) REFERENCES public.sn_accounts(id);


--
-- Name: sn_invite_codes fk_sn_invite_codes_agent_id_sn_promoter_profiles; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_invite_codes
    ADD CONSTRAINT fk_sn_invite_codes_agent_id_sn_promoter_profiles FOREIGN KEY (agent_id) REFERENCES public.sn_promoter_profiles(id);


--
-- Name: sn_invite_codes fk_sn_invite_codes_organization_id_sn_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_invite_codes
    ADD CONSTRAINT fk_sn_invite_codes_organization_id_sn_tenants FOREIGN KEY (organization_id) REFERENCES public.sn_tenants(id);


--
-- Name: sn_invite_events fk_sn_invite_events_organization_id_sn_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_invite_events
    ADD CONSTRAINT fk_sn_invite_events_organization_id_sn_tenants FOREIGN KEY (organization_id) REFERENCES public.sn_tenants(id);


--
-- Name: sn_invite_events fk_sn_invite_events_promoter_code_id_sn_invite_codes; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_invite_events
    ADD CONSTRAINT fk_sn_invite_events_promoter_code_id_sn_invite_codes FOREIGN KEY (promoter_code_id) REFERENCES public.sn_invite_codes(id);


--
-- Name: sn_invite_visits fk_sn_invite_visits_organization_id_sn_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_invite_visits
    ADD CONSTRAINT fk_sn_invite_visits_organization_id_sn_tenants FOREIGN KEY (organization_id) REFERENCES public.sn_tenants(id);


--
-- Name: sn_invite_visits fk_sn_invite_visits_promoter_code_id_sn_invite_codes; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_invite_visits
    ADD CONSTRAINT fk_sn_invite_visits_promoter_code_id_sn_invite_codes FOREIGN KEY (promoter_code_id) REFERENCES public.sn_invite_codes(id);


--
-- Name: sn_knowledge_articles fk_sn_knowledge_articles_created_by_user_id_sn_accounts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_knowledge_articles
    ADD CONSTRAINT fk_sn_knowledge_articles_created_by_user_id_sn_accounts FOREIGN KEY (created_by_user_id) REFERENCES public.sn_accounts(id);


--
-- Name: sn_knowledge_articles fk_sn_knowledge_articles_organization_id_sn_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_knowledge_articles
    ADD CONSTRAINT fk_sn_knowledge_articles_organization_id_sn_tenants FOREIGN KEY (organization_id) REFERENCES public.sn_tenants(id);


--
-- Name: sn_leads fk_sn_leads_assigned_agent_id_sn_promoter_profiles; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_leads
    ADD CONSTRAINT fk_sn_leads_assigned_agent_id_sn_promoter_profiles FOREIGN KEY (assigned_agent_id) REFERENCES public.sn_promoter_profiles(id);


--
-- Name: sn_leads fk_sn_leads_converted_contract_id_sn_agreements; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_leads
    ADD CONSTRAINT fk_sn_leads_converted_contract_id_sn_agreements FOREIGN KEY (converted_contract_id) REFERENCES public.sn_agreements(id);


--
-- Name: sn_leads fk_sn_leads_created_by_user_id_sn_accounts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_leads
    ADD CONSTRAINT fk_sn_leads_created_by_user_id_sn_accounts FOREIGN KEY (created_by_user_id) REFERENCES public.sn_accounts(id);


--
-- Name: sn_leads fk_sn_leads_customer_id_sn_clients; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_leads
    ADD CONSTRAINT fk_sn_leads_customer_id_sn_clients FOREIGN KEY (customer_id) REFERENCES public.sn_clients(id);


--
-- Name: sn_leads fk_sn_leads_organization_id_sn_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_leads
    ADD CONSTRAINT fk_sn_leads_organization_id_sn_tenants FOREIGN KEY (organization_id) REFERENCES public.sn_tenants(id);


--
-- Name: sn_leads fk_sn_leads_product_id_sn_offers; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_leads
    ADD CONSTRAINT fk_sn_leads_product_id_sn_offers FOREIGN KEY (product_id) REFERENCES public.sn_offers(id);


--
-- Name: sn_leads fk_sn_leads_promoter_agent_id_sn_promoter_profiles; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_leads
    ADD CONSTRAINT fk_sn_leads_promoter_agent_id_sn_promoter_profiles FOREIGN KEY (promoter_agent_id) REFERENCES public.sn_promoter_profiles(id);


--
-- Name: sn_login_sessions fk_sn_login_sessions_user_id_sn_accounts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_login_sessions
    ADD CONSTRAINT fk_sn_login_sessions_user_id_sn_accounts FOREIGN KEY (user_id) REFERENCES public.sn_accounts(id);


--
-- Name: sn_mamify_config fk_sn_mamify_config_organization_id_sn_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_mamify_config
    ADD CONSTRAINT fk_sn_mamify_config_organization_id_sn_tenants FOREIGN KEY (organization_id) REFERENCES public.sn_tenants(id);


--
-- Name: sn_mamify_config fk_sn_mamify_config_sync_actor_user_id_sn_accounts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_mamify_config
    ADD CONSTRAINT fk_sn_mamify_config_sync_actor_user_id_sn_accounts FOREIGN KEY (sync_actor_user_id) REFERENCES public.sn_accounts(id);


--
-- Name: sn_mamify_members fk_sn_mamify_members_agent_id_sn_promoter_profiles; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_mamify_members
    ADD CONSTRAINT fk_sn_mamify_members_agent_id_sn_promoter_profiles FOREIGN KEY (agent_id) REFERENCES public.sn_promoter_profiles(id);


--
-- Name: sn_mamify_members fk_sn_mamify_members_organization_id_sn_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_mamify_members
    ADD CONSTRAINT fk_sn_mamify_members_organization_id_sn_tenants FOREIGN KEY (organization_id) REFERENCES public.sn_tenants(id);


--
-- Name: sn_mamify_orders fk_sn_mamify_orders_organization_id_sn_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_mamify_orders
    ADD CONSTRAINT fk_sn_mamify_orders_organization_id_sn_tenants FOREIGN KEY (organization_id) REFERENCES public.sn_tenants(id);


--
-- Name: sn_mamify_payouts fk_sn_mamify_payouts_commission_id_sn_aff_commissions; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_mamify_payouts
    ADD CONSTRAINT fk_sn_mamify_payouts_commission_id_sn_aff_commissions FOREIGN KEY (commission_id) REFERENCES public.sn_aff_commissions(id);


--
-- Name: sn_mamify_payouts fk_sn_mamify_payouts_organization_id_sn_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_mamify_payouts
    ADD CONSTRAINT fk_sn_mamify_payouts_organization_id_sn_tenants FOREIGN KEY (organization_id) REFERENCES public.sn_tenants(id);


--
-- Name: sn_mamify_payouts fk_sn_mamify_payouts_requested_by_user_id_sn_accounts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_mamify_payouts
    ADD CONSTRAINT fk_sn_mamify_payouts_requested_by_user_id_sn_accounts FOREIGN KEY (requested_by_user_id) REFERENCES public.sn_accounts(id);


--
-- Name: sn_mamify_products fk_sn_mamify_products_organization_id_sn_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_mamify_products
    ADD CONSTRAINT fk_sn_mamify_products_organization_id_sn_tenants FOREIGN KEY (organization_id) REFERENCES public.sn_tenants(id);


--
-- Name: sn_mamify_webhook_events fk_sn_mamify_webhook_events_organization_id_sn_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_mamify_webhook_events
    ADD CONSTRAINT fk_sn_mamify_webhook_events_organization_id_sn_tenants FOREIGN KEY (organization_id) REFERENCES public.sn_tenants(id);


--
-- Name: sn_market_config fk_sn_market_config_organization_id_sn_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_market_config
    ADD CONSTRAINT fk_sn_market_config_organization_id_sn_tenants FOREIGN KEY (organization_id) REFERENCES public.sn_tenants(id);


--
-- Name: sn_market_item_variants fk_sn_market_item_variants_product_id_sn_market_items; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_market_item_variants
    ADD CONSTRAINT fk_sn_market_item_variants_product_id_sn_market_items FOREIGN KEY (product_id) REFERENCES public.sn_market_items(id) ON DELETE CASCADE;


--
-- Name: sn_market_items fk_sn_market_items_created_by_user_id_sn_accounts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_market_items
    ADD CONSTRAINT fk_sn_market_items_created_by_user_id_sn_accounts FOREIGN KEY (created_by_user_id) REFERENCES public.sn_accounts(id);


--
-- Name: sn_market_items fk_sn_market_items_organization_id_sn_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_market_items
    ADD CONSTRAINT fk_sn_market_items_organization_id_sn_tenants FOREIGN KEY (organization_id) REFERENCES public.sn_tenants(id);


--
-- Name: sn_market_items fk_sn_market_items_producer_id_sn_market_producers; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_market_items
    ADD CONSTRAINT fk_sn_market_items_producer_id_sn_market_producers FOREIGN KEY (producer_id) REFERENCES public.sn_market_producers(id);


--
-- Name: sn_market_order_lines fk_sn_market_order_lines_order_id_sn_market_orders; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_market_order_lines
    ADD CONSTRAINT fk_sn_market_order_lines_order_id_sn_market_orders FOREIGN KEY (order_id) REFERENCES public.sn_market_orders(id) ON DELETE CASCADE;


--
-- Name: sn_market_order_lines fk_sn_market_order_lines_product_id_sn_market_items; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_market_order_lines
    ADD CONSTRAINT fk_sn_market_order_lines_product_id_sn_market_items FOREIGN KEY (product_id) REFERENCES public.sn_market_items(id);


--
-- Name: sn_market_order_lines fk_sn_market_order_lines_variant_id_sn_market_item_variants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_market_order_lines
    ADD CONSTRAINT fk_sn_market_order_lines_variant_id_sn_market_item_variants FOREIGN KEY (variant_id) REFERENCES public.sn_market_item_variants(id);


--
-- Name: sn_market_orders fk_sn_market_orders_cancelled_by_user_id_sn_accounts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_market_orders
    ADD CONSTRAINT fk_sn_market_orders_cancelled_by_user_id_sn_accounts FOREIGN KEY (cancelled_by_user_id) REFERENCES public.sn_accounts(id);


--
-- Name: sn_market_orders fk_sn_market_orders_created_by_user_id_sn_accounts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_market_orders
    ADD CONSTRAINT fk_sn_market_orders_created_by_user_id_sn_accounts FOREIGN KEY (created_by_user_id) REFERENCES public.sn_accounts(id);


--
-- Name: sn_market_orders fk_sn_market_orders_credit_debit_transaction_id_sn_cred_6af1; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_market_orders
    ADD CONSTRAINT fk_sn_market_orders_credit_debit_transaction_id_sn_cred_6af1 FOREIGN KEY (credit_debit_transaction_id) REFERENCES public.sn_credit_ledger(id);


--
-- Name: sn_market_orders fk_sn_market_orders_customer_user_id_sn_accounts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_market_orders
    ADD CONSTRAINT fk_sn_market_orders_customer_user_id_sn_accounts FOREIGN KEY (customer_user_id) REFERENCES public.sn_accounts(id);


--
-- Name: sn_market_orders fk_sn_market_orders_forwarded_by_user_id_sn_accounts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_market_orders
    ADD CONSTRAINT fk_sn_market_orders_forwarded_by_user_id_sn_accounts FOREIGN KEY (forwarded_by_user_id) REFERENCES public.sn_accounts(id);


--
-- Name: sn_market_orders fk_sn_market_orders_organization_id_sn_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_market_orders
    ADD CONSTRAINT fk_sn_market_orders_organization_id_sn_tenants FOREIGN KEY (organization_id) REFERENCES public.sn_tenants(id);


--
-- Name: sn_market_orders fk_sn_market_orders_paid_by_user_id_sn_accounts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_market_orders
    ADD CONSTRAINT fk_sn_market_orders_paid_by_user_id_sn_accounts FOREIGN KEY (paid_by_user_id) REFERENCES public.sn_accounts(id);


--
-- Name: sn_market_producers fk_sn_market_producers_created_by_user_id_sn_accounts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_market_producers
    ADD CONSTRAINT fk_sn_market_producers_created_by_user_id_sn_accounts FOREIGN KEY (created_by_user_id) REFERENCES public.sn_accounts(id);


--
-- Name: sn_market_producers fk_sn_market_producers_organization_id_sn_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_market_producers
    ADD CONSTRAINT fk_sn_market_producers_organization_id_sn_tenants FOREIGN KEY (organization_id) REFERENCES public.sn_tenants(id);


--
-- Name: sn_merchants fk_sn_merchants_organization_id_sn_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_merchants
    ADD CONSTRAINT fk_sn_merchants_organization_id_sn_tenants FOREIGN KEY (organization_id) REFERENCES public.sn_tenants(id);


--
-- Name: sn_offer_versions fk_sn_offer_versions_commission_plan_version_id_sn_payout_plans; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_offer_versions
    ADD CONSTRAINT fk_sn_offer_versions_commission_plan_version_id_sn_payout_plans FOREIGN KEY (commission_plan_version_id) REFERENCES public.sn_payout_plans(id);


--
-- Name: sn_offer_versions fk_sn_offer_versions_product_id_sn_offers; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_offer_versions
    ADD CONSTRAINT fk_sn_offer_versions_product_id_sn_offers FOREIGN KEY (product_id) REFERENCES public.sn_offers(id);


--
-- Name: sn_offers fk_sn_offers_commercial_category_id_sn_product_categories; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_offers
    ADD CONSTRAINT fk_sn_offers_commercial_category_id_sn_product_categories FOREIGN KEY (commercial_category_id) REFERENCES public.sn_product_categories(id);


--
-- Name: sn_offers fk_sn_offers_company_id_sn_suppliers; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_offers
    ADD CONSTRAINT fk_sn_offers_company_id_sn_suppliers FOREIGN KEY (company_id) REFERENCES public.sn_suppliers(id);


--
-- Name: sn_offers fk_sn_offers_organization_id_sn_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_offers
    ADD CONSTRAINT fk_sn_offers_organization_id_sn_tenants FOREIGN KEY (organization_id) REFERENCES public.sn_tenants(id);


--
-- Name: sn_one_time_codes fk_sn_one_time_codes_user_id_sn_accounts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_one_time_codes
    ADD CONSTRAINT fk_sn_one_time_codes_user_id_sn_accounts FOREIGN KEY (user_id) REFERENCES public.sn_accounts(id);


--
-- Name: sn_password_recoveries fk_sn_password_recoveries_user_id_sn_accounts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_password_recoveries
    ADD CONSTRAINT fk_sn_password_recoveries_user_id_sn_accounts FOREIGN KEY (user_id) REFERENCES public.sn_accounts(id);


--
-- Name: sn_payout_adjustments fk_sn_payout_adjustments_approved_by_sn_accounts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_payout_adjustments
    ADD CONSTRAINT fk_sn_payout_adjustments_approved_by_sn_accounts FOREIGN KEY (approved_by) REFERENCES public.sn_accounts(id);


--
-- Name: sn_payout_adjustments fk_sn_payout_adjustments_new_movement_id_sn_payout_entries; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_payout_adjustments
    ADD CONSTRAINT fk_sn_payout_adjustments_new_movement_id_sn_payout_entries FOREIGN KEY (new_movement_id) REFERENCES public.sn_payout_entries(id);


--
-- Name: sn_payout_adjustments fk_sn_payout_adjustments_organization_id_sn_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_payout_adjustments
    ADD CONSTRAINT fk_sn_payout_adjustments_organization_id_sn_tenants FOREIGN KEY (organization_id) REFERENCES public.sn_tenants(id);


--
-- Name: sn_payout_adjustments fk_sn_payout_adjustments_original_movement_id_sn_payout_entries; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_payout_adjustments
    ADD CONSTRAINT fk_sn_payout_adjustments_original_movement_id_sn_payout_entries FOREIGN KEY (original_movement_id) REFERENCES public.sn_payout_entries(id);


--
-- Name: sn_payout_adjustments fk_sn_payout_adjustments_requested_by_sn_accounts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_payout_adjustments
    ADD CONSTRAINT fk_sn_payout_adjustments_requested_by_sn_accounts FOREIGN KEY (requested_by) REFERENCES public.sn_accounts(id);


--
-- Name: sn_payout_entries fk_sn_payout_entries_agent_id_sn_promoter_profiles; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_payout_entries
    ADD CONSTRAINT fk_sn_payout_entries_agent_id_sn_promoter_profiles FOREIGN KEY (agent_id) REFERENCES public.sn_promoter_profiles(id);


--
-- Name: sn_payout_entries fk_sn_payout_entries_approved_by_user_id_sn_accounts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_payout_entries
    ADD CONSTRAINT fk_sn_payout_entries_approved_by_user_id_sn_accounts FOREIGN KEY (approved_by_user_id) REFERENCES public.sn_accounts(id);


--
-- Name: sn_payout_entries fk_sn_payout_entries_calculation_id_sn_payout_runs; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_payout_entries
    ADD CONSTRAINT fk_sn_payout_entries_calculation_id_sn_payout_runs FOREIGN KEY (calculation_id) REFERENCES public.sn_payout_runs(id);


--
-- Name: sn_payout_entries fk_sn_payout_entries_contract_id_sn_agreements; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_payout_entries
    ADD CONSTRAINT fk_sn_payout_entries_contract_id_sn_agreements FOREIGN KEY (contract_id) REFERENCES public.sn_agreements(id);


--
-- Name: sn_payout_entries fk_sn_payout_entries_network_snapshot_id_sn_tree_snapshots; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_payout_entries
    ADD CONSTRAINT fk_sn_payout_entries_network_snapshot_id_sn_tree_snapshots FOREIGN KEY (network_snapshot_id) REFERENCES public.sn_tree_snapshots(id);


--
-- Name: sn_payout_entries fk_sn_payout_entries_organization_id_sn_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_payout_entries
    ADD CONSTRAINT fk_sn_payout_entries_organization_id_sn_tenants FOREIGN KEY (organization_id) REFERENCES public.sn_tenants(id);


--
-- Name: sn_payout_entries fk_sn_payout_entries_product_id_sn_offers; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_payout_entries
    ADD CONSTRAINT fk_sn_payout_entries_product_id_sn_offers FOREIGN KEY (product_id) REFERENCES public.sn_offers(id);


--
-- Name: sn_payout_entries fk_sn_payout_entries_rule_id_sn_payout_rules; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_payout_entries
    ADD CONSTRAINT fk_sn_payout_entries_rule_id_sn_payout_rules FOREIGN KEY (rule_id) REFERENCES public.sn_payout_rules(id);


--
-- Name: sn_payout_entries fk_sn_payout_entries_source_seller_agent_id_sn_promoter_43f3; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_payout_entries
    ADD CONSTRAINT fk_sn_payout_entries_source_seller_agent_id_sn_promoter_43f3 FOREIGN KEY (source_seller_agent_id) REFERENCES public.sn_promoter_profiles(id);


--
-- Name: sn_payout_entries fk_sn_payout_entries_split_plan_id_sn_payout_plans; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_payout_entries
    ADD CONSTRAINT fk_sn_payout_entries_split_plan_id_sn_payout_plans FOREIGN KEY (split_plan_id) REFERENCES public.sn_payout_plans(id);


--
-- Name: sn_payout_offsets fk_sn_payout_offsets_credit_movement_id_sn_payout_entries; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_payout_offsets
    ADD CONSTRAINT fk_sn_payout_offsets_credit_movement_id_sn_payout_entries FOREIGN KEY (credit_movement_id) REFERENCES public.sn_payout_entries(id);


--
-- Name: sn_payout_offsets fk_sn_payout_offsets_debit_movement_id_sn_payout_entries; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_payout_offsets
    ADD CONSTRAINT fk_sn_payout_offsets_debit_movement_id_sn_payout_entries FOREIGN KEY (debit_movement_id) REFERENCES public.sn_payout_entries(id);


--
-- Name: sn_payout_offsets fk_sn_payout_offsets_organization_id_sn_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_payout_offsets
    ADD CONSTRAINT fk_sn_payout_offsets_organization_id_sn_tenants FOREIGN KEY (organization_id) REFERENCES public.sn_tenants(id);


--
-- Name: sn_payout_plans fk_sn_payout_plans_activated_by_user_id_sn_accounts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_payout_plans
    ADD CONSTRAINT fk_sn_payout_plans_activated_by_user_id_sn_accounts FOREIGN KEY (activated_by_user_id) REFERENCES public.sn_accounts(id);


--
-- Name: sn_payout_plans fk_sn_payout_plans_category_id_sn_product_categories; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_payout_plans
    ADD CONSTRAINT fk_sn_payout_plans_category_id_sn_product_categories FOREIGN KEY (category_id) REFERENCES public.sn_product_categories(id);


--
-- Name: sn_payout_plans fk_sn_payout_plans_created_by_user_id_sn_accounts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_payout_plans
    ADD CONSTRAINT fk_sn_payout_plans_created_by_user_id_sn_accounts FOREIGN KEY (created_by_user_id) REFERENCES public.sn_accounts(id);


--
-- Name: sn_payout_plans fk_sn_payout_plans_organization_id_sn_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_payout_plans
    ADD CONSTRAINT fk_sn_payout_plans_organization_id_sn_tenants FOREIGN KEY (organization_id) REFERENCES public.sn_tenants(id);


--
-- Name: sn_payout_plans fk_sn_payout_plans_product_id_sn_offers; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_payout_plans
    ADD CONSTRAINT fk_sn_payout_plans_product_id_sn_offers FOREIGN KEY (product_id) REFERENCES public.sn_offers(id);


--
-- Name: sn_payout_plans fk_sn_payout_plans_seller_role_id_sn_commercial_roles; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_payout_plans
    ADD CONSTRAINT fk_sn_payout_plans_seller_role_id_sn_commercial_roles FOREIGN KEY (seller_role_id) REFERENCES public.sn_commercial_roles(id);


--
-- Name: sn_payout_reversals fk_sn_payout_reversals_approved_by_sn_accounts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_payout_reversals
    ADD CONSTRAINT fk_sn_payout_reversals_approved_by_sn_accounts FOREIGN KEY (approved_by) REFERENCES public.sn_accounts(id);


--
-- Name: sn_payout_reversals fk_sn_payout_reversals_new_movement_id_sn_payout_entries; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_payout_reversals
    ADD CONSTRAINT fk_sn_payout_reversals_new_movement_id_sn_payout_entries FOREIGN KEY (new_movement_id) REFERENCES public.sn_payout_entries(id);


--
-- Name: sn_payout_reversals fk_sn_payout_reversals_organization_id_sn_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_payout_reversals
    ADD CONSTRAINT fk_sn_payout_reversals_organization_id_sn_tenants FOREIGN KEY (organization_id) REFERENCES public.sn_tenants(id);


--
-- Name: sn_payout_reversals fk_sn_payout_reversals_original_movement_id_sn_payout_entries; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_payout_reversals
    ADD CONSTRAINT fk_sn_payout_reversals_original_movement_id_sn_payout_entries FOREIGN KEY (original_movement_id) REFERENCES public.sn_payout_entries(id);


--
-- Name: sn_payout_reversals fk_sn_payout_reversals_requested_by_sn_accounts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_payout_reversals
    ADD CONSTRAINT fk_sn_payout_reversals_requested_by_sn_accounts FOREIGN KEY (requested_by) REFERENCES public.sn_accounts(id);


--
-- Name: sn_payout_rules fk_sn_payout_rules_commission_plan_version_id_sn_payout_plans; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_payout_rules
    ADD CONSTRAINT fk_sn_payout_rules_commission_plan_version_id_sn_payout_plans FOREIGN KEY (commission_plan_version_id) REFERENCES public.sn_payout_plans(id);


--
-- Name: sn_payout_rules fk_sn_payout_rules_required_role_id_sn_commercial_roles; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_payout_rules
    ADD CONSTRAINT fk_sn_payout_rules_required_role_id_sn_commercial_roles FOREIGN KEY (required_role_id) REFERENCES public.sn_commercial_roles(id);


--
-- Name: sn_payout_run_steps fk_sn_payout_run_steps_beneficiary_agent_id_sn_promoter_c065; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_payout_run_steps
    ADD CONSTRAINT fk_sn_payout_run_steps_beneficiary_agent_id_sn_promoter_c065 FOREIGN KEY (beneficiary_agent_id) REFERENCES public.sn_promoter_profiles(id);


--
-- Name: sn_payout_run_steps fk_sn_payout_run_steps_calculation_id_sn_payout_runs; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_payout_run_steps
    ADD CONSTRAINT fk_sn_payout_run_steps_calculation_id_sn_payout_runs FOREIGN KEY (calculation_id) REFERENCES public.sn_payout_runs(id);


--
-- Name: sn_payout_run_steps fk_sn_payout_run_steps_rule_id_sn_payout_rules; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_payout_run_steps
    ADD CONSTRAINT fk_sn_payout_run_steps_rule_id_sn_payout_rules FOREIGN KEY (rule_id) REFERENCES public.sn_payout_rules(id);


--
-- Name: sn_payout_runs fk_sn_payout_runs_commission_plan_version_id_sn_payout_plans; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_payout_runs
    ADD CONSTRAINT fk_sn_payout_runs_commission_plan_version_id_sn_payout_plans FOREIGN KEY (commission_plan_version_id) REFERENCES public.sn_payout_plans(id);


--
-- Name: sn_payout_runs fk_sn_payout_runs_contract_id_sn_agreements; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_payout_runs
    ADD CONSTRAINT fk_sn_payout_runs_contract_id_sn_agreements FOREIGN KEY (contract_id) REFERENCES public.sn_agreements(id);


--
-- Name: sn_payout_runs fk_sn_payout_runs_network_snapshot_id_sn_tree_snapshots; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_payout_runs
    ADD CONSTRAINT fk_sn_payout_runs_network_snapshot_id_sn_tree_snapshots FOREIGN KEY (network_snapshot_id) REFERENCES public.sn_tree_snapshots(id);


--
-- Name: sn_payout_runs fk_sn_payout_runs_organization_id_sn_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_payout_runs
    ADD CONSTRAINT fk_sn_payout_runs_organization_id_sn_tenants FOREIGN KEY (organization_id) REFERENCES public.sn_tenants(id);


--
-- Name: sn_postal_addresses fk_sn_postal_addresses_customer_id_sn_clients; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_postal_addresses
    ADD CONSTRAINT fk_sn_postal_addresses_customer_id_sn_clients FOREIGN KEY (customer_id) REFERENCES public.sn_clients(id);


--
-- Name: sn_postal_addresses fk_sn_postal_addresses_organization_id_sn_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_postal_addresses
    ADD CONSTRAINT fk_sn_postal_addresses_organization_id_sn_tenants FOREIGN KEY (organization_id) REFERENCES public.sn_tenants(id);


--
-- Name: sn_product_categories fk_sn_product_categories_organization_id_sn_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_product_categories
    ADD CONSTRAINT fk_sn_product_categories_organization_id_sn_tenants FOREIGN KEY (organization_id) REFERENCES public.sn_tenants(id);


--
-- Name: sn_promoter_level_log fk_sn_promoter_level_log_agent_id_sn_promoter_profiles; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_promoter_level_log
    ADD CONSTRAINT fk_sn_promoter_level_log_agent_id_sn_promoter_profiles FOREIGN KEY (agent_id) REFERENCES public.sn_promoter_profiles(id);


--
-- Name: sn_promoter_level_log fk_sn_promoter_level_log_approved_by_sn_accounts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_promoter_level_log
    ADD CONSTRAINT fk_sn_promoter_level_log_approved_by_sn_accounts FOREIGN KEY (approved_by) REFERENCES public.sn_accounts(id);


--
-- Name: sn_promoter_level_log fk_sn_promoter_level_log_organization_id_sn_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_promoter_level_log
    ADD CONSTRAINT fk_sn_promoter_level_log_organization_id_sn_tenants FOREIGN KEY (organization_id) REFERENCES public.sn_tenants(id);


--
-- Name: sn_promoter_level_log fk_sn_promoter_level_log_rank_id_sn_career_levels; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_promoter_level_log
    ADD CONSTRAINT fk_sn_promoter_level_log_rank_id_sn_career_levels FOREIGN KEY (rank_id) REFERENCES public.sn_career_levels(id);


--
-- Name: sn_promoter_profiles fk_sn_promoter_profiles_approved_by_user_id_sn_accounts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_promoter_profiles
    ADD CONSTRAINT fk_sn_promoter_profiles_approved_by_user_id_sn_accounts FOREIGN KEY (approved_by_user_id) REFERENCES public.sn_accounts(id);


--
-- Name: sn_promoter_profiles fk_sn_promoter_profiles_current_commercial_role_id_sn_c_51aa; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_promoter_profiles
    ADD CONSTRAINT fk_sn_promoter_profiles_current_commercial_role_id_sn_c_51aa FOREIGN KEY (current_commercial_role_id) REFERENCES public.sn_commercial_roles(id);


--
-- Name: sn_promoter_profiles fk_sn_promoter_profiles_current_rank_id_sn_career_levels; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_promoter_profiles
    ADD CONSTRAINT fk_sn_promoter_profiles_current_rank_id_sn_career_levels FOREIGN KEY (current_rank_id) REFERENCES public.sn_career_levels(id);


--
-- Name: sn_promoter_profiles fk_sn_promoter_profiles_organization_id_sn_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_promoter_profiles
    ADD CONSTRAINT fk_sn_promoter_profiles_organization_id_sn_tenants FOREIGN KEY (organization_id) REFERENCES public.sn_tenants(id);


--
-- Name: sn_promoter_profiles fk_sn_promoter_profiles_user_id_sn_accounts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_promoter_profiles
    ADD CONSTRAINT fk_sn_promoter_profiles_user_id_sn_accounts FOREIGN KEY (user_id) REFERENCES public.sn_accounts(id);


--
-- Name: sn_receipt_claims fk_sn_receipt_claims_credited_by_user_id_sn_accounts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_receipt_claims
    ADD CONSTRAINT fk_sn_receipt_claims_credited_by_user_id_sn_accounts FOREIGN KEY (credited_by_user_id) REFERENCES public.sn_accounts(id);


--
-- Name: sn_receipt_claims fk_sn_receipt_claims_customer_user_id_sn_accounts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_receipt_claims
    ADD CONSTRAINT fk_sn_receipt_claims_customer_user_id_sn_accounts FOREIGN KEY (customer_user_id) REFERENCES public.sn_accounts(id);


--
-- Name: sn_receipt_claims fk_sn_receipt_claims_organization_id_sn_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_receipt_claims
    ADD CONSTRAINT fk_sn_receipt_claims_organization_id_sn_tenants FOREIGN KEY (organization_id) REFERENCES public.sn_tenants(id);


--
-- Name: sn_receipt_claims fk_sn_receipt_claims_partner_id_sn_merchants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_receipt_claims
    ADD CONSTRAINT fk_sn_receipt_claims_partner_id_sn_merchants FOREIGN KEY (partner_id) REFERENCES public.sn_merchants(id);


--
-- Name: sn_receipt_claims fk_sn_receipt_claims_verified_by_user_id_sn_accounts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_receipt_claims
    ADD CONSTRAINT fk_sn_receipt_claims_verified_by_user_id_sn_accounts FOREIGN KEY (verified_by_user_id) REFERENCES public.sn_accounts(id);


--
-- Name: sn_role_grants fk_sn_role_grants_permission_id_sn_permissions; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_role_grants
    ADD CONSTRAINT fk_sn_role_grants_permission_id_sn_permissions FOREIGN KEY (permission_id) REFERENCES public.sn_permissions(id);


--
-- Name: sn_role_grants fk_sn_role_grants_role_id_sn_roles; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_role_grants
    ADD CONSTRAINT fk_sn_role_grants_role_id_sn_roles FOREIGN KEY (role_id) REFERENCES public.sn_roles(id);


--
-- Name: sn_roles fk_sn_roles_organization_id_sn_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_roles
    ADD CONSTRAINT fk_sn_roles_organization_id_sn_tenants FOREIGN KEY (organization_id) REFERENCES public.sn_tenants(id);


--
-- Name: sn_seller_role_history fk_sn_seller_role_history_agent_id_sn_promoter_profiles; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_seller_role_history
    ADD CONSTRAINT fk_sn_seller_role_history_agent_id_sn_promoter_profiles FOREIGN KEY (agent_id) REFERENCES public.sn_promoter_profiles(id);


--
-- Name: sn_seller_role_history fk_sn_seller_role_history_changed_by_user_id_sn_accounts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_seller_role_history
    ADD CONSTRAINT fk_sn_seller_role_history_changed_by_user_id_sn_accounts FOREIGN KEY (changed_by_user_id) REFERENCES public.sn_accounts(id);


--
-- Name: sn_seller_role_history fk_sn_seller_role_history_organization_id_sn_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_seller_role_history
    ADD CONSTRAINT fk_sn_seller_role_history_organization_id_sn_tenants FOREIGN KEY (organization_id) REFERENCES public.sn_tenants(id);


--
-- Name: sn_seller_role_history fk_sn_seller_role_history_role_id_sn_commercial_roles; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_seller_role_history
    ADD CONSTRAINT fk_sn_seller_role_history_role_id_sn_commercial_roles FOREIGN KEY (role_id) REFERENCES public.sn_commercial_roles(id);


--
-- Name: sn_shop_orders fk_sn_shop_orders_cancelled_by_user_id_sn_accounts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_shop_orders
    ADD CONSTRAINT fk_sn_shop_orders_cancelled_by_user_id_sn_accounts FOREIGN KEY (cancelled_by_user_id) REFERENCES public.sn_accounts(id);


--
-- Name: sn_shop_orders fk_sn_shop_orders_created_by_user_id_sn_accounts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_shop_orders
    ADD CONSTRAINT fk_sn_shop_orders_created_by_user_id_sn_accounts FOREIGN KEY (created_by_user_id) REFERENCES public.sn_accounts(id);


--
-- Name: sn_shop_orders fk_sn_shop_orders_credit_debit_transaction_id_sn_credit_ledger; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_shop_orders
    ADD CONSTRAINT fk_sn_shop_orders_credit_debit_transaction_id_sn_credit_ledger FOREIGN KEY (credit_debit_transaction_id) REFERENCES public.sn_credit_ledger(id);


--
-- Name: sn_shop_orders fk_sn_shop_orders_customer_user_id_sn_accounts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_shop_orders
    ADD CONSTRAINT fk_sn_shop_orders_customer_user_id_sn_accounts FOREIGN KEY (customer_user_id) REFERENCES public.sn_accounts(id);


--
-- Name: sn_shop_orders fk_sn_shop_orders_organization_id_sn_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_shop_orders
    ADD CONSTRAINT fk_sn_shop_orders_organization_id_sn_tenants FOREIGN KEY (organization_id) REFERENCES public.sn_tenants(id);


--
-- Name: sn_shop_orders fk_sn_shop_orders_paid_by_user_id_sn_accounts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_shop_orders
    ADD CONSTRAINT fk_sn_shop_orders_paid_by_user_id_sn_accounts FOREIGN KEY (paid_by_user_id) REFERENCES public.sn_accounts(id);


--
-- Name: sn_shop_orders fk_sn_shop_orders_product_version_id_sn_offer_versions; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_shop_orders
    ADD CONSTRAINT fk_sn_shop_orders_product_version_id_sn_offer_versions FOREIGN KEY (product_version_id) REFERENCES public.sn_offer_versions(id);


--
-- Name: sn_shopify_config fk_sn_shopify_config_organization_id_sn_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_shopify_config
    ADD CONSTRAINT fk_sn_shopify_config_organization_id_sn_tenants FOREIGN KEY (organization_id) REFERENCES public.sn_tenants(id);


--
-- Name: sn_shopify_item_variants fk_sn_shopify_item_variants_product_id_sn_shopify_items; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_shopify_item_variants
    ADD CONSTRAINT fk_sn_shopify_item_variants_product_id_sn_shopify_items FOREIGN KEY (product_id) REFERENCES public.sn_shopify_items(id);


--
-- Name: sn_shopify_items fk_sn_shopify_items_created_by_user_id_sn_accounts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_shopify_items
    ADD CONSTRAINT fk_sn_shopify_items_created_by_user_id_sn_accounts FOREIGN KEY (created_by_user_id) REFERENCES public.sn_accounts(id);


--
-- Name: sn_shopify_items fk_sn_shopify_items_organization_id_sn_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_shopify_items
    ADD CONSTRAINT fk_sn_shopify_items_organization_id_sn_tenants FOREIGN KEY (organization_id) REFERENCES public.sn_tenants(id);


--
-- Name: sn_shopify_order_lines fk_sn_shopify_order_lines_order_id_sn_shopify_orders; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_shopify_order_lines
    ADD CONSTRAINT fk_sn_shopify_order_lines_order_id_sn_shopify_orders FOREIGN KEY (order_id) REFERENCES public.sn_shopify_orders(id) ON DELETE CASCADE;


--
-- Name: sn_shopify_order_lines fk_sn_shopify_order_lines_product_id_sn_shopify_items; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_shopify_order_lines
    ADD CONSTRAINT fk_sn_shopify_order_lines_product_id_sn_shopify_items FOREIGN KEY (product_id) REFERENCES public.sn_shopify_items(id);


--
-- Name: sn_shopify_order_lines fk_sn_shopify_order_lines_variant_id_sn_shopify_item_variants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_shopify_order_lines
    ADD CONSTRAINT fk_sn_shopify_order_lines_variant_id_sn_shopify_item_variants FOREIGN KEY (variant_id) REFERENCES public.sn_shopify_item_variants(id);


--
-- Name: sn_shopify_orders fk_sn_shopify_orders_cancelled_by_user_id_sn_accounts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_shopify_orders
    ADD CONSTRAINT fk_sn_shopify_orders_cancelled_by_user_id_sn_accounts FOREIGN KEY (cancelled_by_user_id) REFERENCES public.sn_accounts(id);


--
-- Name: sn_shopify_orders fk_sn_shopify_orders_created_by_user_id_sn_accounts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_shopify_orders
    ADD CONSTRAINT fk_sn_shopify_orders_created_by_user_id_sn_accounts FOREIGN KEY (created_by_user_id) REFERENCES public.sn_accounts(id);


--
-- Name: sn_shopify_orders fk_sn_shopify_orders_credit_debit_transaction_id_sn_cre_c68f; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_shopify_orders
    ADD CONSTRAINT fk_sn_shopify_orders_credit_debit_transaction_id_sn_cre_c68f FOREIGN KEY (credit_debit_transaction_id) REFERENCES public.sn_credit_ledger(id);


--
-- Name: sn_shopify_orders fk_sn_shopify_orders_customer_user_id_sn_accounts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_shopify_orders
    ADD CONSTRAINT fk_sn_shopify_orders_customer_user_id_sn_accounts FOREIGN KEY (customer_user_id) REFERENCES public.sn_accounts(id);


--
-- Name: sn_shopify_orders fk_sn_shopify_orders_forwarded_by_user_id_sn_accounts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_shopify_orders
    ADD CONSTRAINT fk_sn_shopify_orders_forwarded_by_user_id_sn_accounts FOREIGN KEY (forwarded_by_user_id) REFERENCES public.sn_accounts(id);


--
-- Name: sn_shopify_orders fk_sn_shopify_orders_organization_id_sn_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_shopify_orders
    ADD CONSTRAINT fk_sn_shopify_orders_organization_id_sn_tenants FOREIGN KEY (organization_id) REFERENCES public.sn_tenants(id);


--
-- Name: sn_shopify_orders fk_sn_shopify_orders_paid_by_user_id_sn_accounts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_shopify_orders
    ADD CONSTRAINT fk_sn_shopify_orders_paid_by_user_id_sn_accounts FOREIGN KEY (paid_by_user_id) REFERENCES public.sn_accounts(id);


--
-- Name: sn_shopify_orders fk_sn_shopify_orders_shopify_product_id_sn_shopify_items; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_shopify_orders
    ADD CONSTRAINT fk_sn_shopify_orders_shopify_product_id_sn_shopify_items FOREIGN KEY (shopify_product_id) REFERENCES public.sn_shopify_items(id);


--
-- Name: sn_shopify_orders fk_sn_shopify_orders_shopify_variant_id_sn_shopify_item_bc2a; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_shopify_orders
    ADD CONSTRAINT fk_sn_shopify_orders_shopify_variant_id_sn_shopify_item_bc2a FOREIGN KEY (shopify_variant_id) REFERENCES public.sn_shopify_item_variants(id);


--
-- Name: sn_stored_files fk_sn_stored_files_contract_id_sn_agreements; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_stored_files
    ADD CONSTRAINT fk_sn_stored_files_contract_id_sn_agreements FOREIGN KEY (contract_id) REFERENCES public.sn_agreements(id);


--
-- Name: sn_stored_files fk_sn_stored_files_contract_request_id_sn_agreement_requests; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_stored_files
    ADD CONSTRAINT fk_sn_stored_files_contract_request_id_sn_agreement_requests FOREIGN KEY (contract_request_id) REFERENCES public.sn_agreement_requests(id);


--
-- Name: sn_stored_files fk_sn_stored_files_organization_id_sn_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_stored_files
    ADD CONSTRAINT fk_sn_stored_files_organization_id_sn_tenants FOREIGN KEY (organization_id) REFERENCES public.sn_tenants(id);


--
-- Name: sn_stored_files fk_sn_stored_files_reviewed_by_user_id_sn_accounts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_stored_files
    ADD CONSTRAINT fk_sn_stored_files_reviewed_by_user_id_sn_accounts FOREIGN KEY (reviewed_by_user_id) REFERENCES public.sn_accounts(id);


--
-- Name: sn_stored_files fk_sn_stored_files_uploaded_by_user_id_sn_accounts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_stored_files
    ADD CONSTRAINT fk_sn_stored_files_uploaded_by_user_id_sn_accounts FOREIGN KEY (uploaded_by_user_id) REFERENCES public.sn_accounts(id);


--
-- Name: sn_stripe_events fk_sn_stripe_events_organization_id_sn_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_stripe_events
    ADD CONSTRAINT fk_sn_stripe_events_organization_id_sn_tenants FOREIGN KEY (organization_id) REFERENCES public.sn_tenants(id);


--
-- Name: sn_supplier_item_orders fk_sn_supplier_item_orders_cancelled_by_user_id_sn_accounts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_supplier_item_orders
    ADD CONSTRAINT fk_sn_supplier_item_orders_cancelled_by_user_id_sn_accounts FOREIGN KEY (cancelled_by_user_id) REFERENCES public.sn_accounts(id);


--
-- Name: sn_supplier_item_orders fk_sn_supplier_item_orders_created_by_user_id_sn_accounts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_supplier_item_orders
    ADD CONSTRAINT fk_sn_supplier_item_orders_created_by_user_id_sn_accounts FOREIGN KEY (created_by_user_id) REFERENCES public.sn_accounts(id);


--
-- Name: sn_supplier_item_orders fk_sn_supplier_item_orders_credit_debit_transaction_id__a9c8; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_supplier_item_orders
    ADD CONSTRAINT fk_sn_supplier_item_orders_credit_debit_transaction_id__a9c8 FOREIGN KEY (credit_debit_transaction_id) REFERENCES public.sn_credit_ledger(id);


--
-- Name: sn_supplier_item_orders fk_sn_supplier_item_orders_customer_user_id_sn_accounts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_supplier_item_orders
    ADD CONSTRAINT fk_sn_supplier_item_orders_customer_user_id_sn_accounts FOREIGN KEY (customer_user_id) REFERENCES public.sn_accounts(id);


--
-- Name: sn_supplier_item_orders fk_sn_supplier_item_orders_imported_product_id_sn_suppl_75fa; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_supplier_item_orders
    ADD CONSTRAINT fk_sn_supplier_item_orders_imported_product_id_sn_suppl_75fa FOREIGN KEY (imported_product_id) REFERENCES public.sn_supplier_items(id);


--
-- Name: sn_supplier_item_orders fk_sn_supplier_item_orders_organization_id_sn_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_supplier_item_orders
    ADD CONSTRAINT fk_sn_supplier_item_orders_organization_id_sn_tenants FOREIGN KEY (organization_id) REFERENCES public.sn_tenants(id);


--
-- Name: sn_supplier_item_orders fk_sn_supplier_item_orders_paid_by_user_id_sn_accounts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_supplier_item_orders
    ADD CONSTRAINT fk_sn_supplier_item_orders_paid_by_user_id_sn_accounts FOREIGN KEY (paid_by_user_id) REFERENCES public.sn_accounts(id);


--
-- Name: sn_supplier_items fk_sn_supplier_items_created_by_user_id_sn_accounts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_supplier_items
    ADD CONSTRAINT fk_sn_supplier_items_created_by_user_id_sn_accounts FOREIGN KEY (created_by_user_id) REFERENCES public.sn_accounts(id);


--
-- Name: sn_supplier_items fk_sn_supplier_items_organization_id_sn_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_supplier_items
    ADD CONSTRAINT fk_sn_supplier_items_organization_id_sn_tenants FOREIGN KEY (organization_id) REFERENCES public.sn_tenants(id);


--
-- Name: sn_supplier_items fk_sn_supplier_items_provider_id_sn_supplier_sources; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_supplier_items
    ADD CONSTRAINT fk_sn_supplier_items_provider_id_sn_supplier_sources FOREIGN KEY (provider_id) REFERENCES public.sn_supplier_sources(id);


--
-- Name: sn_supplier_members fk_sn_supplier_members_agent_id_sn_promoter_profiles; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_supplier_members
    ADD CONSTRAINT fk_sn_supplier_members_agent_id_sn_promoter_profiles FOREIGN KEY (agent_id) REFERENCES public.sn_promoter_profiles(id);


--
-- Name: sn_supplier_members fk_sn_supplier_members_company_id_sn_suppliers; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_supplier_members
    ADD CONSTRAINT fk_sn_supplier_members_company_id_sn_suppliers FOREIGN KEY (company_id) REFERENCES public.sn_suppliers(id);


--
-- Name: sn_supplier_members fk_sn_supplier_members_organization_id_sn_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_supplier_members
    ADD CONSTRAINT fk_sn_supplier_members_organization_id_sn_tenants FOREIGN KEY (organization_id) REFERENCES public.sn_tenants(id);


--
-- Name: sn_supplier_sources fk_sn_supplier_sources_created_by_user_id_sn_accounts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_supplier_sources
    ADD CONSTRAINT fk_sn_supplier_sources_created_by_user_id_sn_accounts FOREIGN KEY (created_by_user_id) REFERENCES public.sn_accounts(id);


--
-- Name: sn_supplier_sources fk_sn_supplier_sources_organization_id_sn_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_supplier_sources
    ADD CONSTRAINT fk_sn_supplier_sources_organization_id_sn_tenants FOREIGN KEY (organization_id) REFERENCES public.sn_tenants(id);


--
-- Name: sn_suppliers fk_sn_suppliers_organization_id_sn_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_suppliers
    ADD CONSTRAINT fk_sn_suppliers_organization_id_sn_tenants FOREIGN KEY (organization_id) REFERENCES public.sn_tenants(id);


--
-- Name: sn_support_cases fk_sn_support_cases_contract_id_sn_agreements; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_support_cases
    ADD CONSTRAINT fk_sn_support_cases_contract_id_sn_agreements FOREIGN KEY (contract_id) REFERENCES public.sn_agreements(id);


--
-- Name: sn_support_cases fk_sn_support_cases_opened_by_user_id_sn_accounts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_support_cases
    ADD CONSTRAINT fk_sn_support_cases_opened_by_user_id_sn_accounts FOREIGN KEY (opened_by_user_id) REFERENCES public.sn_accounts(id);


--
-- Name: sn_support_cases fk_sn_support_cases_organization_id_sn_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_support_cases
    ADD CONSTRAINT fk_sn_support_cases_organization_id_sn_tenants FOREIGN KEY (organization_id) REFERENCES public.sn_tenants(id);


--
-- Name: sn_support_replies fk_sn_support_replies_author_user_id_sn_accounts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_support_replies
    ADD CONSTRAINT fk_sn_support_replies_author_user_id_sn_accounts FOREIGN KEY (author_user_id) REFERENCES public.sn_accounts(id);


--
-- Name: sn_support_replies fk_sn_support_replies_ticket_id_sn_support_cases; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_support_replies
    ADD CONSTRAINT fk_sn_support_replies_ticket_id_sn_support_cases FOREIGN KEY (ticket_id) REFERENCES public.sn_support_cases(id);


--
-- Name: sn_tree_links fk_sn_tree_links_child_agent_id_sn_promoter_profiles; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_tree_links
    ADD CONSTRAINT fk_sn_tree_links_child_agent_id_sn_promoter_profiles FOREIGN KEY (child_agent_id) REFERENCES public.sn_promoter_profiles(id);


--
-- Name: sn_tree_links fk_sn_tree_links_organization_id_sn_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_tree_links
    ADD CONSTRAINT fk_sn_tree_links_organization_id_sn_tenants FOREIGN KEY (organization_id) REFERENCES public.sn_tenants(id);


--
-- Name: sn_tree_links fk_sn_tree_links_parent_agent_id_sn_promoter_profiles; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_tree_links
    ADD CONSTRAINT fk_sn_tree_links_parent_agent_id_sn_promoter_profiles FOREIGN KEY (parent_agent_id) REFERENCES public.sn_promoter_profiles(id);


--
-- Name: sn_tree_moves fk_sn_tree_moves_agent_id_sn_promoter_profiles; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_tree_moves
    ADD CONSTRAINT fk_sn_tree_moves_agent_id_sn_promoter_profiles FOREIGN KEY (agent_id) REFERENCES public.sn_promoter_profiles(id);


--
-- Name: sn_tree_moves fk_sn_tree_moves_approved_by_sn_accounts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_tree_moves
    ADD CONSTRAINT fk_sn_tree_moves_approved_by_sn_accounts FOREIGN KEY (approved_by) REFERENCES public.sn_accounts(id);


--
-- Name: sn_tree_moves fk_sn_tree_moves_new_parent_agent_id_sn_promoter_profiles; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_tree_moves
    ADD CONSTRAINT fk_sn_tree_moves_new_parent_agent_id_sn_promoter_profiles FOREIGN KEY (new_parent_agent_id) REFERENCES public.sn_promoter_profiles(id);


--
-- Name: sn_tree_moves fk_sn_tree_moves_old_parent_agent_id_sn_promoter_profiles; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_tree_moves
    ADD CONSTRAINT fk_sn_tree_moves_old_parent_agent_id_sn_promoter_profiles FOREIGN KEY (old_parent_agent_id) REFERENCES public.sn_promoter_profiles(id);


--
-- Name: sn_tree_moves fk_sn_tree_moves_organization_id_sn_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_tree_moves
    ADD CONSTRAINT fk_sn_tree_moves_organization_id_sn_tenants FOREIGN KEY (organization_id) REFERENCES public.sn_tenants(id);


--
-- Name: sn_tree_moves fk_sn_tree_moves_requested_by_sn_accounts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_tree_moves
    ADD CONSTRAINT fk_sn_tree_moves_requested_by_sn_accounts FOREIGN KEY (requested_by) REFERENCES public.sn_accounts(id);


--
-- Name: sn_tree_nodes fk_sn_tree_nodes_agent_id_sn_promoter_profiles; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_tree_nodes
    ADD CONSTRAINT fk_sn_tree_nodes_agent_id_sn_promoter_profiles FOREIGN KEY (agent_id) REFERENCES public.sn_promoter_profiles(id);


--
-- Name: sn_tree_nodes fk_sn_tree_nodes_direct_parent_agent_id_sn_promoter_profiles; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_tree_nodes
    ADD CONSTRAINT fk_sn_tree_nodes_direct_parent_agent_id_sn_promoter_profiles FOREIGN KEY (direct_parent_agent_id) REFERENCES public.sn_promoter_profiles(id);


--
-- Name: sn_tree_nodes fk_sn_tree_nodes_organization_id_sn_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_tree_nodes
    ADD CONSTRAINT fk_sn_tree_nodes_organization_id_sn_tenants FOREIGN KEY (organization_id) REFERENCES public.sn_tenants(id);


--
-- Name: sn_tree_paths fk_sn_tree_paths_ancestor_agent_id_sn_promoter_profiles; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_tree_paths
    ADD CONSTRAINT fk_sn_tree_paths_ancestor_agent_id_sn_promoter_profiles FOREIGN KEY (ancestor_agent_id) REFERENCES public.sn_promoter_profiles(id);


--
-- Name: sn_tree_paths fk_sn_tree_paths_descendant_agent_id_sn_promoter_profiles; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_tree_paths
    ADD CONSTRAINT fk_sn_tree_paths_descendant_agent_id_sn_promoter_profiles FOREIGN KEY (descendant_agent_id) REFERENCES public.sn_promoter_profiles(id);


--
-- Name: sn_tree_paths fk_sn_tree_paths_organization_id_sn_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_tree_paths
    ADD CONSTRAINT fk_sn_tree_paths_organization_id_sn_tenants FOREIGN KEY (organization_id) REFERENCES public.sn_tenants(id);


--
-- Name: sn_tree_snapshot_nodes fk_sn_tree_snapshot_nodes_ancestor_agent_id_sn_promoter_157d; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_tree_snapshot_nodes
    ADD CONSTRAINT fk_sn_tree_snapshot_nodes_ancestor_agent_id_sn_promoter_157d FOREIGN KEY (ancestor_agent_id) REFERENCES public.sn_promoter_profiles(id);


--
-- Name: sn_tree_snapshot_nodes fk_sn_tree_snapshot_nodes_commercial_role_id_sn_commerc_165a; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_tree_snapshot_nodes
    ADD CONSTRAINT fk_sn_tree_snapshot_nodes_commercial_role_id_sn_commerc_165a FOREIGN KEY (commercial_role_id) REFERENCES public.sn_commercial_roles(id);


--
-- Name: sn_tree_snapshot_nodes fk_sn_tree_snapshot_nodes_rank_id_at_snapshot_sn_career_levels; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_tree_snapshot_nodes
    ADD CONSTRAINT fk_sn_tree_snapshot_nodes_rank_id_at_snapshot_sn_career_levels FOREIGN KEY (rank_id_at_snapshot) REFERENCES public.sn_career_levels(id);


--
-- Name: sn_tree_snapshot_nodes fk_sn_tree_snapshot_nodes_snapshot_id_sn_tree_snapshots; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_tree_snapshot_nodes
    ADD CONSTRAINT fk_sn_tree_snapshot_nodes_snapshot_id_sn_tree_snapshots FOREIGN KEY (snapshot_id) REFERENCES public.sn_tree_snapshots(id);


--
-- Name: sn_tree_snapshots fk_sn_tree_snapshots_organization_id_sn_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_tree_snapshots
    ADD CONSTRAINT fk_sn_tree_snapshots_organization_id_sn_tenants FOREIGN KEY (organization_id) REFERENCES public.sn_tenants(id);


--
-- Name: sn_utility_points fk_sn_utility_points_customer_id_sn_clients; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_utility_points
    ADD CONSTRAINT fk_sn_utility_points_customer_id_sn_clients FOREIGN KEY (customer_id) REFERENCES public.sn_clients(id);


--
-- Name: sn_utility_points fk_sn_utility_points_organization_id_sn_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_utility_points
    ADD CONSTRAINT fk_sn_utility_points_organization_id_sn_tenants FOREIGN KEY (organization_id) REFERENCES public.sn_tenants(id);


--
-- Name: sn_utility_points fk_sn_utility_points_supply_address_id_sn_postal_addresses; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sn_utility_points
    ADD CONSTRAINT fk_sn_utility_points_supply_address_id_sn_postal_addresses FOREIGN KEY (supply_address_id) REFERENCES public.sn_postal_addresses(id);


--
-- PostgreSQL database dump complete
--

\unrestrict nP9nauzuXkEhaNdBYHFJBb4ICzhzXGpjBtlFWLhnw5Cj4K0jk37cdZbQBM7afyM

