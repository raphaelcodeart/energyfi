import uuid
from datetime import date, datetime

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.foundation.db import Base, TimestampMixin, UUIDPKMixin


class Rank(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "sn_career_levels"
    __table_args__ = (UniqueConstraint("organization_id", "code", "rule_version", name="uq_sn_career_levels_org_code_version"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_tenants.id"), index=True
    )
    code: Mapped[str] = mapped_column(String(16))
    name: Mapped[str] = mapped_column(String(128))
    level: Mapped[int] = mapped_column(Integer)
    personal_token_cents: Mapped[int] = mapped_column(BigInteger)
    energy_share_percentage: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    personal_volume_threshold_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    group_volume_threshold_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    evaluation_window_months: Mapped[int] = mapped_column(Integer, default=3)
    single_branch_cap_percentage: Mapped[float] = mapped_column(Numeric(5, 2), default=33)
    valid_from: Mapped[datetime] = mapped_column()
    valid_to: Mapped[datetime | None] = mapped_column(nullable=True)
    rule_version: Mapped[str] = mapped_column(String(32))


class AgentRankHistory(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "sn_promoter_level_log"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_tenants.id"), index=True
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_promoter_profiles.id"), index=True)
    rank_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_career_levels.id"))
    effective_from: Mapped[datetime] = mapped_column()
    effective_to: Mapped[datetime | None] = mapped_column(nullable=True)
    calculation_source: Mapped[str] = mapped_column(String(32), default="MANUAL")
    rule_version_id: Mapped[str] = mapped_column(String(32))
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_accounts.id"), nullable=True
    )
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)


#: Only ACTIVE plans are selected by the engine. An ACTIVE plan is immutable:
#: retire it and create the next version. LEGACY marks rows from the legacy
#: token model, which the engine ignores.
PLAN_STATUSES = ("DRAFT", "ACTIVE", "RETIRED", "LEGACY")

#: What happens to a rule's share when its beneficiary does not exist (network
#: too shallow, no ancestor with the role, no referrer...). A business choice,
#: set per plan and optionally per rule:
#:   COMPANY         the share is booked to the company;
#:   NEXT_AVAILABLE  it moves up to the next eligible ancestor;
#:   STOP            it is not distributed (unattributed residual, reported
#:                   separately from COMPANY).
FALLBACK_STRATEGIES = ("COMPANY", "NEXT_AVAILABLE", "STOP")

#: FULL distributes the whole margin (needs a REMAINDER rule, or percentages
#: summing to exactly 100 with no fixed amounts). PARTIAL distributes what the
#: rules say and leaves the rest to the company.
DISTRIBUTION_MODES = ("FULL", "PARTIAL")

#: PER_INSTALMENT accrues a share per collected instalment (a one-off payment
#: counts as one instalment); ON_ACTIVATION accrues everything at activation.
ACCRUAL_TRIGGERS = ("PER_INSTALMENT", "ON_ACTIVATION")

BENEFICIARY_TYPES = ("SELLER", "UPLINE_LEVEL", "ROLE_IN_UPLINE", "INFLUENCER", "PROMOTER", "COMPANY")
CALCULATION_TYPES = ("PERCENTAGE", "FIXED_AMOUNT", "MINIMUM_GUARANTEE", "REMAINDER")


class SplitPlan(UUIDPKMixin, TimestampMixin, Base):
    """How a sale's margin is divided, scoped by product (or whole category),
    seller role and validity period.

    Versions share `plan_key` with increasing `version`; their validity periods
    are contiguous and never overlap (DB exclusion constraint on ACTIVE plans).
    A sale freezes the plan valid on its date, so editing plans never
    recalculates the past. Rows from the legacy token model are marked LEGACY."""

    __tablename__ = "sn_payout_plans"
    __table_args__ = (
        CheckConstraint(
            "status = 'LEGACY' OR ((product_id IS NULL) <> (category_id IS NULL))",
            name="one_scope",
        ),
        CheckConstraint("valid_to IS NULL OR valid_to > valid_from", name="valid_range"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_tenants.id"), index=True
    )
    version_label: Mapped[str] = mapped_column(String(32))
    valid_from: Mapped[datetime] = mapped_column()
    valid_to: Mapped[datetime | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="DRAFT")
    name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    plan_key: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_offers.id"), nullable=True, index=True
    )
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_product_categories.id"), nullable=True, index=True
    )
    seller_role_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_commercial_roles.id"), nullable=True, index=True
    )
    fallback_strategy: Mapped[str] = mapped_column(String(16), default="COMPANY")
    distribution_mode: Mapped[str] = mapped_column(String(8), default="FULL")
    accrual_trigger: Mapped[str] = mapped_column(String(16), default="PER_INSTALMENT")
    notes: Mapped[str] = mapped_column(String(2000), default="")
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_accounts.id"), nullable=True
    )
    activated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_accounts.id"), nullable=True
    )
    activated_at: Mapped[datetime | None] = mapped_column(nullable=True)
    retired_at: Mapped[datetime | None] = mapped_column(nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(nullable=True)


class SplitRule(UUIDPKMixin, TimestampMixin, Base):
    """One Split Plan line: who (beneficiary_type + level/role) and how much
    (calculation_type + value). The engine evaluates rules in passes (fixed,
    percentage, minimum, remainder) rather than `sequence` order, so the result
    does not depend on how rules are arranged."""

    __tablename__ = "sn_payout_rules"
    __table_args__ = (
        CheckConstraint("percentage IS NULL OR (percentage >= 0 AND percentage <= 100)", name="percentage_range"),
        CheckConstraint("amount_cents IS NULL OR amount_cents >= 0", name="amount_non_negative"),
        CheckConstraint("min_amount_cents IS NULL OR min_amount_cents >= 0", name="min_non_negative"),
        CheckConstraint("max_amount_cents IS NULL OR max_amount_cents >= 0", name="max_non_negative"),
        CheckConstraint("network_level IS NULL OR network_level >= 1", name="level_positive"),
    )

    commission_plan_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_payout_plans.id"), index=True
    )
    rule_type: Mapped[str] = mapped_column(String(64), default="SPLIT")
    parameters: Mapped[dict] = mapped_column(JSONB, default=dict)
    valid_from: Mapped[datetime | None] = mapped_column(nullable=True)
    valid_to: Mapped[datetime | None] = mapped_column(nullable=True)
    sequence: Mapped[int] = mapped_column(Integer, default=0)
    label: Mapped[str | None] = mapped_column(String(120), nullable=True)
    beneficiary_type: Mapped[str | None] = mapped_column(String(24), nullable=True)
    #: Distance from the seller (1 = direct sponsor). For ROLE_IN_UPLINE and
    #: INFLUENCER it is the maximum search distance (NULL = the role's depth).
    network_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    required_role_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_commercial_roles.id"), nullable=True
    )
    calculation_type: Mapped[str | None] = mapped_column(String(24), nullable=True)
    #: Share of the margin; NUMERIC, handled as Decimal, never float.
    percentage: Mapped[float | None] = mapped_column(Numeric(7, 4), nullable=True)
    amount_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    min_amount_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    max_amount_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    #: Overrides the plan's fallback strategy for this rule.
    fallback_strategy: Mapped[str | None] = mapped_column(String(16), nullable=True)


# Aliases still imported by seed and catalog code.
CommissionPlanVersion = SplitPlan
CommissionRuleVersion = SplitRule


class CommissionCalculation(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "sn_payout_runs"
    __table_args__ = (
        # Backstop for the application-level SELECT-then-INSERT idempotency
        # check in run_calculation_for_contract(), which races if the same
        # event is dispatched concurrently.
        UniqueConstraint(
            "contract_id", "trigger_event_id", name="uq_sn_payout_runs_contract_trigger"
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_tenants.id"), index=True
    )
    contract_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_agreements.id"), index=True)
    network_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_tree_snapshots.id")
    )
    commission_plan_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_payout_plans.id"), nullable=True
    )
    trigger_event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    reference_margin_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    input_snapshot: Mapped[dict] = mapped_column(JSONB)
    output_snapshot: Mapped[dict] = mapped_column(JSONB)
    checksum: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="COMPLETED")


class CommissionCalculationStep(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "sn_payout_run_steps"

    calculation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_payout_runs.id"), index=True
    )
    step_order: Mapped[int] = mapped_column(Integer)
    #: NULL when the beneficiary is the company.
    beneficiary_agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_promoter_profiles.id"), nullable=True
    )
    rule_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_payout_rules.id"), nullable=True
    )
    rank_at_calculation: Mapped[str | None] = mapped_column(String(32), nullable=True)
    base_amount_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    already_distributed_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    entrepreneurial_difference_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    personal_bonus_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    gross_amount_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    movement_type: Mapped[str] = mapped_column(String(32))
    explanation: Mapped[str] = mapped_column(String(1000))


class CommissionMovement(UUIDPKMixin, TimestampMixin, Base):
    """Append-only ledger. Rows past PENDING are never updated in amount;
    corrections are new rows linked through adjustments, offsets or reversals
    (see docs/commission-engine-specification.md)."""

    __tablename__ = "sn_payout_entries"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_sn_payout_entries_idempotency_key"),
        # Exactly one of: an agent, or the company.
        CheckConstraint(
            "(beneficiary_kind = 'AGENT' AND agent_id IS NOT NULL)"
            " OR (beneficiary_kind = 'COMPANY' AND agent_id IS NULL)",
            name="beneficiary_consistent",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_tenants.id"), index=True
    )
    #: COMPANY shares are real rows, so a sale's rows always sum to its margin.
    beneficiary_kind: Mapped[str] = mapped_column(String(8), default="AGENT")
    agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_promoter_profiles.id"), index=True, nullable=True
    )
    contract_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_agreements.id"), index=True)
    origin_event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    calculation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_payout_runs.id")
    )
    movement_type: Mapped[str] = mapped_column(String(32))
    amount_cents: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    #: PENDING -> APPROVED -> PAYABLE -> PAID. CANCELLED: voided before payment;
    #: REVERSED: paid, then offset by a negative row. Company shares stay
    #: RETAINED. ACCRUED is a legacy status treated as PENDING.
    status: Mapped[str] = mapped_column(String(32), default="PENDING")
    effective_date: Mapped[date] = mapped_column()
    scheduled_date: Mapped[date | None] = mapped_column(nullable=True)
    paid_date: Mapped[date | None] = mapped_column(nullable=True)
    rule_version_id: Mapped[str] = mapped_column(String(32))
    network_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_tree_snapshots.id")
    )
    idempotency_key: Mapped[str] = mapped_column(String(128))

    # Frozen provenance: enough to rebuild the calculation without reading the
    # current state of any other table; `snapshot` holds the full context.
    split_plan_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_payout_plans.id"), nullable=True, index=True
    )
    plan_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rule_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_payout_rules.id"), nullable=True
    )
    beneficiary_type: Mapped[str | None] = mapped_column(String(24), nullable=True)
    network_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    role_code_snapshot: Mapped[str | None] = mapped_column(String(32), nullable=True)
    calculation_type: Mapped[str | None] = mapped_column(String(24), nullable=True)
    calculation_value: Mapped[float | None] = mapped_column(Numeric(12, 4), nullable=True)
    reference_margin_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    source_seller_agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_promoter_profiles.id"), nullable=True, index=True
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_offers.id"), nullable=True, index=True
    )
    fallback_applied: Mapped[str | None] = mapped_column(String(16), nullable=True)
    snapshot: Mapped[dict] = mapped_column(JSONB, default=dict)
    approved_at: Mapped[datetime | None] = mapped_column(nullable=True)
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_accounts.id"), nullable=True
    )


class CommissionReversal(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "sn_payout_reversals"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_tenants.id"), index=True
    )
    original_movement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_payout_entries.id")
    )
    new_movement_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_payout_entries.id"))
    reason: Mapped[str] = mapped_column(String(500))
    requested_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_accounts.id"), nullable=True)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_accounts.id"), nullable=True
    )


class CommissionAdjustment(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "sn_payout_adjustments"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_tenants.id"), index=True
    )
    original_movement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_payout_entries.id")
    )
    new_movement_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_payout_entries.id"))
    reason: Mapped[str] = mapped_column(String(500))
    requested_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_accounts.id"))
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_accounts.id"), nullable=True
    )


class CommissionOffset(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "sn_payout_offsets"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_tenants.id"), index=True
    )
    debit_movement_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_payout_entries.id"))
    credit_movement_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_payout_entries.id"))
    reason: Mapped[str] = mapped_column(String(500))
