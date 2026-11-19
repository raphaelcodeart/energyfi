import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.foundation.db import Base, TimestampMixin, UUIDPKMixin

#: DRAFT: being filled in. SUBMITTED: its contracts are in normal review.
#: CANCELLED: abandoned while still a draft.
CONTRACT_REQUEST_STATUSES = frozenset({"DRAFT", "SUBMITTED", "CANCELLED"})


class ContractRequest(UUIDPKMixin, TimestampMixin, Base):
    """An activation request: one customer, N supply points, N contracts,
    filled in and paid together.

    Intentionally thin: each contract keeps its own package, frozen price,
    status, documents, approval, instalments and commissions. The request
    holds only what is shared (holder data, common documents, the single
    checkout). A contract rejected, suspended or cancelled affects no other
    contract in the request.

    Holder fields are copied onto every contract at creation and on each
    edit while in DRAFT, so a contract is self-describing and readers of
    `contracts.email`/`iban` need not join upward.
    """

    __tablename__ = "sn_agreement_requests"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_tenants.id"), index=True
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_clients.id"), index=True)
    status: Mapped[str] = mapped_column(String(16), default="DRAFT", index=True)
    holder_first_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    holder_last_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    pec: Mapped[str | None] = mapped_column(String(320), nullable=True)
    iban: Mapped[str | None] = mapped_column(String(34), nullable=True)
    #: Default supply address for every point; a point elsewhere stores its
    #: own address on its supply point.
    street: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str | None] = mapped_column(String(128), nullable=True)
    province: Mapped[str | None] = mapped_column(String(8), nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_accounts.id"), nullable=True
    )
    #: CUSTOMER / PROMOTER / ADMIN -- same meaning as on contracts.
    created_by_role: Mapped[str | None] = mapped_column(String(32), nullable=True)
    #: Set when a promoter fills the request in for their customer; also
    #: grants that promoter continued access to it.
    activated_by_promoter_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_promoter_profiles.id"), nullable=True
    )
    submitted_at: Mapped[datetime | None] = mapped_column(nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(nullable=True)
    # --- Bank transfer payment --------------------------------------------
    #: Single payment (with the single-payment discount); the amount is frozen
    #: when chosen and later confirmed by an administrator.
    bank_transfer_requested_at: Mapped[datetime | None] = mapped_column(nullable=True)
    bank_transfer_total_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    bank_transfer_confirmed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    bank_transfer_confirmed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_accounts.id"), nullable=True
    )
    payment_proof_storage_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    payment_proof_original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    payment_proof_uploaded_at: Mapped[datetime | None] = mapped_column(nullable=True)


class ContractRequestCheckout(UUIDPKMixin, TimestampMixin, Base):
    """One Stripe Checkout Session opened to pay a contract request.

    `lines` freezes what the session charges, one
    `{"contract_id", "gross_cents", "instalment_cents"}` entry per contract.
    The webhook pays exactly those contracts; one rejected meanwhile is still
    recorded as paid (money moved) and staff are told to refund it.

    One row per session, not a single "current session" column, so a payment
    completed in an older tab is still found.
    """

    __tablename__ = "sn_agreement_checkouts"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_tenants.id"), index=True
    )
    contract_request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_agreement_requests.id"), index=True
    )
    stripe_checkout_session_id: Mapped[str] = mapped_column(String(255), unique=True)
    payment_plan: Mapped[str] = mapped_column(String(16))
    lines: Mapped[list] = mapped_column(JSONB, default=list)
    #: Sum over the lines of what the plan collects in total, and per month.
    total_cents: Mapped[int] = mapped_column(BigInteger)
    instalment_cents: Mapped[int] = mapped_column(BigInteger)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_accounts.id"), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    stripe_customer_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    #: Human-readable webhook outcome, for troubleshooting.
    outcome: Mapped[str | None] = mapped_column(String(255), nullable=True)


class Contract(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "sn_agreements"
    __table_args__ = (
        # The package is chosen after the documents, so it may be missing
        # only while the contract is a draft.
        CheckConstraint(
            "product_version_id IS NOT NULL OR status IN ('DRAFT', 'CANCELLED')", name="product_required"
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_tenants.id"), index=True
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_clients.id"), index=True)
    #: Always set; a standalone contract gets a request of its own.
    contract_request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_agreement_requests.id"), index=True
    )
    #: Supply point (POD/PDR); required only by categories that have one
    #: (electricity, gas), not e.g. fibre.
    supply_point_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_utility_points.id"), nullable=True
    )
    product_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_offer_versions.id"), nullable=True
    )
    contract_attribution_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_agreement_attributions.id"), nullable=True
    )
    network_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_tree_snapshots.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(32), default="DRAFT", index=True)
    # Free-text context from whoever originated the deal. Distinct from the
    # per-transition ContractStatusHistory.notes.
    notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    # Per-contract direct-debit IBAN, never inferred from other contracts.
    # Nullable: staff may create a contract before it is known.
    iban: Mapped[str | None] = mapped_column(String(34), nullable=True)
    # Per-contract contact email, independent of the account login email.
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    # Contract holder as entered in the activation wizard (pre-filled from
    # the account, editable) plus optional PEC. May be null on staff-created
    # contracts.
    holder_first_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    holder_last_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    pec: Mapped[str | None] = mapped_column(String(320), nullable=True)
    # Set by transition_contract() on entering ACTIVE or RENEWED. expires_at
    # is frozen from the product version's contract_duration_months at that
    # moment and never recomputed if the duration changes later.
    activated_at: Mapped[datetime | None] = mapped_column(nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(nullable=True, index=True)

    # --- Who created this contract ----------------------------------------
    # Denormalized for the admin screen (self-service vs promoter-assisted);
    # ContractStatusHistory and audit_log remain the full trail.
    updated_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_accounts.id"), nullable=True
    )
    #: CUSTOMER / PROMOTER / ADMIN, frozen at creation
    #: (support/service.py::actor_role_for) since roles can change later.
    created_by_role: Mapped[str | None] = mapped_column(String(32), nullable=True)
    #: Set only when a promoter completed the contract for the customer (CRM
    #: path); independent of who earns the commission.
    activated_by_promoter_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_promoter_profiles.id"), nullable=True
    )
    #: Promoter who originally referred the customer, frozen at creation from
    #: CustomerAttribution. Distinct from ContractAttribution.producer_agent_id;
    #: kept for the legacy first-referrer bonus.
    first_referrer_agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_promoter_profiles.id"), nullable=True
    )

    # --- Sale data for the commission engine -------------------------------
    #: Sale date (contract creation). Seller role, network and plan are
    #: resolved as of this date, not activation, which depends on admin timing.
    sold_at: Mapped[datetime | None] = mapped_column(nullable=True)
    #: Net sale amount and reference margin, frozen at activation with the
    #: chosen Split Plan so commissions no longer depend on editable tables.
    sale_amount_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    reference_margin_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    split_plan_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_payout_plans.id"), nullable=True, index=True
    )
    seller_role_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    #: Originating lead, if any; makes the referring Promoter a beneficiary.
    lead_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_leads.id"), nullable=True, index=True
    )

    # --- Economics, frozen at creation --------------------------------------
    # A snapshot so later price/VAT edits never restate an agreed amount.
    # Computed only server-side by catalog/pricing.py::compute_contract_price.
    #: Customer kind at creation; it determines whether VAT applies.
    customer_kind: Mapped[str | None] = mapped_column(String(32), nullable=True)
    net_amount_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    #: Percentage points (e.g. 22.00); 0.00 for private customers.
    vat_rate: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    vat_amount_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    gross_amount_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # --- Payment -------------------------------------------------------------
    # Only the verified Stripe webhook proves payment, never the success URL.
    #: Plan key from payment_plans.py (FULL / INSTALMENTS_3 / MONTHLY_12).
    payment_plan: Mapped[str | None] = mapped_column(String(16), nullable=True)
    #: Single-payment discount frozen when chosen; 0 for instalments and
    #: bank transfers.
    payment_discount_cents: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    #: CARD / BANK_TRANSFER.
    payment_method: Mapped[str | None] = mapped_column(String(16), nullable=True)
    stripe_checkout_session_id: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
    stripe_customer_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    #: Shared by all contracts of a request paid in instalments: one
    #: subscription, one item (`stripe_subscription_item_id`) per contract.
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    stripe_subscription_item_id: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
    #: Set when an admin removes this contract's subscription item; the other
    #: contracts keep being billed.
    billing_stopped_at: Mapped[datetime | None] = mapped_column(nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(nullable=True)
    #: Exactly-once guard for the SosnetCash credit on webhook replays, in
    #: addition to the wallet ledger's idempotency key.
    cashback_credited_at: Mapped[datetime | None] = mapped_column(nullable=True)

    # --- Terms acceptance ---------------------------------------------------
    # The accepted version is stored here so replacing a product's contract
    # PDF never changes what this customer accepted.
    terms_accepted_at: Mapped[datetime | None] = mapped_column(nullable=True)
    terms_accepted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_accounts.id"), nullable=True
    )
    terms_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    terms_accepted_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    terms_accepted_user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)


class ContractStatusHistory(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "sn_agreement_status_log"

    contract_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_agreements.id"), index=True)
    from_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    to_status: Mapped[str] = mapped_column(String(32))
    actor_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_accounts.id"))
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    correlation_id: Mapped[str] = mapped_column(String(64))


class ContractEvent(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "sn_agreement_events"

    contract_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_agreements.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)


class ContractAttribution(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "sn_agreement_attributions"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_tenants.id"), index=True
    )
    producer_agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_promoter_profiles.id")
    )
    attributed_promoter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_promoter_profiles.id")
    )


class ContractCommissionPlan(UUIDPKMixin, TimestampMixin, Base):
    """The commission preview an administrator accepted before activation,
    stored verbatim.

    Approval starts commissions, so the admin must first see who is paid what
    and how it spreads over instalments. `preview` is exactly what they saw;
    the ledger rows written later may differ if the network changed, and
    both are shown side by side.
    """

    __tablename__ = "sn_agreement_payout_plans"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_tenants.id"), index=True
    )
    contract_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_agreements.id"), unique=True
    )
    accepted_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_accounts.id"))
    accepted_at: Mapped[datetime] = mapped_column()
    #: Payment plan at acceptance; null if unpaid, in which case the preview
    #: lists every possible split.
    payment_plan: Mapped[str | None] = mapped_column(String(16), nullable=True)
    total_commission_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    preview: Mapped[dict] = mapped_column(JSONB, default=dict)
    checksum: Mapped[str] = mapped_column(String(64))


class ContractInstalment(UUIDPKMixin, TimestampMixin, Base):
    """One payment owed on a contract: 1 row for a single payment, 3 or 12
    for an instalment plan.

    Once PAID on an ACTIVE contract, each row emits exactly one
    ContractInstalmentPaid event (commission_event_id, set once) and the
    engine pays 1/N of each commission. The unique constraints below stop a
    Stripe and an admin confirmation from paying the same month twice.
    """

    __tablename__ = "sn_agreement_instalments"
    __table_args__ = (
        UniqueConstraint("contract_id", "number", name="uq_sn_agreement_instalments_contract_number"),
        # Per contract, not global: one invoice pays every contract of a request.
        UniqueConstraint("contract_id", "stripe_invoice_id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_tenants.id"), index=True
    )
    contract_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_agreements.id"), index=True)
    number: Mapped[int] = mapped_column(Integer)
    instalments_total: Mapped[int] = mapped_column(Integer)
    #: First payment date plus (number - 1) months.
    due_date: Mapped[date] = mapped_column(Date)
    amount_cents: Mapped[int] = mapped_column(BigInteger)
    #: SCHEDULED / PAID / FAILED
    status: Mapped[str] = mapped_column(String(16), default="SCHEDULED")
    paid_at: Mapped[datetime | None] = mapped_column(nullable=True)
    #: STRIPE_CHECKOUT / STRIPE_INVOICE / ADMIN
    payment_source: Mapped[str | None] = mapped_column(String(16), nullable=True)
    confirmed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_accounts.id"), nullable=True
    )
    stripe_invoice_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    commission_event_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    commission_released_at: Mapped[datetime | None] = mapped_column(nullable=True)
    commission_calculation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_payout_runs.id"), nullable=True
    )
