"""SOS Affiliate tables.

A Digital Ambassador is an existing network agent (`sn_promoter_profiles`):
the sponsor tree, its history and the closure table are reused as they are.
These tables add what the compensation plan needs on top of the tree.

Double counting is prevented by the database, never by an application flag:
one point entry per operation, one commission row per (operation, kind,
position), one career bonus per (affiliate, month), one subscription payment
per (affiliate, month), one operation per idempotency key.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.foundation.db import Base, TimestampMixin, UUIDPKMixin

MONEY = Numeric(14, 2)
RATE = Numeric(7, 4)


class AffiliatePlanVersion(UUIDPKMixin, TimestampMixin, Base):
    """A complete plan configuration. The version valid at an operation's
    date is the one applied to it, and its id is stored on the operation."""

    __tablename__ = "sn_aff_plan_versions"
    __table_args__ = (UniqueConstraint("organization_id", "valid_from", name="uq_sn_aff_plan_versions_valid_from"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_tenants.id"), index=True)
    label: Mapped[str] = mapped_column(String(64))
    valid_from: Mapped[datetime] = mapped_column()
    config: Mapped[dict] = mapped_column(JSONB)
    notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_accounts.id"), nullable=True
    )


class AffiliateSubscription(UUIDPKMixin, TimestampMixin, Base):
    """Digital Ambassador subscription state (AFF-03, AFF-04). Payment
    history lives in the operations of kind SUBSCRIPTION_PAYMENT."""

    __tablename__ = "sn_aff_subscriptions"
    __table_args__ = (UniqueConstraint("organization_id", "agent_id", name="uq_sn_aff_subscriptions_agent"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_tenants.id"), index=True)
    agent_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_promoter_profiles.id"))
    # ACTIVE / SUSPENDED / CANCELLED
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE")
    started_at: Mapped[datetime] = mapped_column()
    cancelled_at: Mapped[datetime | None] = mapped_column(nullable=True)


class AffiliateClient(UUIDPKMixin, TimestampMixin, Base):
    """A client company served by a Digital Ambassador: buys Packs, receives
    resold licences and tops up MamiCash. The ambassador is the direct
    seller of every BD/BM operation of the client."""

    __tablename__ = "sn_aff_clients"
    __table_args__ = (
        UniqueConstraint("organization_id", "mamify_customer_id", name="uq_sn_aff_clients_mamify_customer"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_tenants.id"), index=True)
    #: The company's Mamify customer id, when it was created from a Mamify order.
    mamify_customer_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    agent_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_promoter_profiles.id"), index=True)
    company_name: Mapped[str] = mapped_column(String(255))
    vat_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    contact_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # MamiCash units credited to the company (resale bonus + top-ups). A
    # quantity of MamiCash, not euro: the spec keeps the two apart.
    mamicash_balance: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))


class AffiliateOperation(UUIDPKMixin, TimestampMixin, Base):
    """Every commercial operation, the origin of every point and commission.

    Created PENDING (the money has not arrived yet), applied when CONFIRMED,
    and never edited afterwards: a correction is a REVERSAL operation that
    points back to the original (INT-05, INT-10)."""

    __tablename__ = "sn_aff_operations"
    __table_args__ = (
        UniqueConstraint("organization_id", "idempotency_key", name="uq_sn_aff_operations_idempotency"),
        # BC-02 and INT-01: a subscription month can be paid once.
        Index(
            "uq_sn_aff_operations_subscription_month", "organization_id", "agent_id", "period",
            unique=True,
            postgresql_where=text("kind = 'SUBSCRIPTION_PAYMENT' AND status <> 'CANCELLED'"),
        ),
        CheckConstraint("paid_amount >= 0", name="paid_amount_non_negative"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_tenants.id"), index=True)
    # SUBSCRIPTION_PAYMENT / LICENSE_PURCHASE / EVENT_TICKET_PURCHASE /
    # LICENSE_RESALE / PACK_SALE / MAMICASH_TOPUP / GIFT_LICENSE / REVERSAL
    kind: Mapped[str] = mapped_column(String(32), index=True)
    # PENDING / CONFIRMED / CANCELLED / REVERSED
    status: Mapped[str] = mapped_column(String(16), default="PENDING", index=True)
    #: Buyer for purchases, seller for sales.
    agent_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_promoter_profiles.id"), index=True)
    client_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_aff_clients.id"), nullable=True, index=True
    )
    product_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    #: Month the points belong to (YYYY-MM): the paid month for a
    #: subscription, the confirmation month otherwise.
    period: Mapped[str | None] = mapped_column(String(7), nullable=True, index=True)
    nominal_amount: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    discount_amount: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    paid_amount: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    bc_points: Mapped[int] = mapped_column(Integer, default=0)
    license_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_aff_licenses.id", use_alter=True), nullable=True
    )
    plan_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_aff_plan_versions.id"))
    idempotency_key: Mapped[str] = mapped_column(String(160))
    reverses_operation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_aff_operations.id"), nullable=True
    )
    payment_method: Mapped[str | None] = mapped_column(String(32), nullable=True)
    note: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_accounts.id"), nullable=True
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    confirmed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_accounts.id"), nullable=True
    )


class AffiliatePointEntry(UUIDPKMixin, TimestampMixin, Base):
    """Personal BC generated by one operation. Network volumes are derived
    from these rows, never stored per ancestor, so the same points cannot be
    counted twice in a total (NET-06, INT-03)."""

    __tablename__ = "sn_aff_points"
    __table_args__ = (
        UniqueConstraint("operation_id", name="uq_sn_aff_points_operation"),
        Index("ix_sn_aff_points_org_period", "organization_id", "period"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_tenants.id"))
    operation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_aff_operations.id"))
    agent_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_promoter_profiles.id"), index=True)
    period: Mapped[str] = mapped_column(String(7))
    #: Negative only on a reversal.
    points: Mapped[int] = mapped_column(Integer)


class AffiliateCommission(UUIDPKMixin, TimestampMixin, Base):
    """One amount owed to one affiliate: a BD or BM share, a monthly BC bonus
    or the seller's part of a licence resale. Kept as separate kinds in one
    table so payouts and exports see a single list (BM-05, UI-08)."""

    __tablename__ = "sn_aff_commissions"
    __table_args__ = (
        UniqueConstraint("operation_id", "kind", "position", name="uq_sn_aff_commissions_operation_position"),
        Index(
            "uq_sn_aff_commissions_career_month", "organization_id", "beneficiary_agent_id", "period",
            unique=True, postgresql_where=text("kind = 'BC'"),
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_tenants.id"), index=True)
    # BC / BD / BM / RESALE
    kind: Mapped[str] = mapped_column(String(8), index=True)
    operation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_aff_operations.id"), nullable=True, index=True
    )
    period: Mapped[str] = mapped_column(String(7))
    beneficiary_agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_promoter_profiles.id"), index=True
    )
    position: Mapped[int] = mapped_column(Integer, default=1)
    rate: Mapped[Decimal | None] = mapped_column(RATE, nullable=True)
    base_amount: Mapped[Decimal] = mapped_column(MONEY)
    amount: Mapped[Decimal] = mapped_column(MONEY)
    career_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # PAYABLE / PAID / CANCELLED. BC rows become payable on `payable_on`.
    status: Mapped[str] = mapped_column(String(16), default="PAYABLE", index=True)
    payable_on: Mapped[date] = mapped_column(Date)
    paid_at: Mapped[datetime | None] = mapped_column(nullable=True)
    paid_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_accounts.id"), nullable=True
    )
    plan_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_aff_plan_versions.id"))
    details: Mapped[dict] = mapped_column(JSONB, default=dict)


class AffiliateLicense(UUIDPKMixin, TimestampMixin, Base):
    """One licence unit, from its purchase to its resale (LIC-01..LIC-06)."""

    __tablename__ = "sn_aff_licenses"
    __table_args__ = (UniqueConstraint("organization_id", "code", name="uq_sn_aff_licenses_code"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_tenants.id"), index=True)
    code: Mapped[str] = mapped_column(String(32))
    owner_agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_promoter_profiles.id"), index=True
    )
    purchase_operation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_aff_operations.id"))
    # PURCHASE / GIFT
    origin: Mapped[str] = mapped_column(String(16), default="PURCHASE")
    #: Cost of this unit to the owner (package price / licences), for the margin.
    unit_cost: Mapped[Decimal] = mapped_column(MONEY)
    # AVAILABLE / RESERVED / RESOLD / VOID
    status: Mapped[str] = mapped_column(String(16), default="AVAILABLE", index=True)
    resale_operation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_aff_operations.id"), nullable=True
    )
    client_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_aff_clients.id"), nullable=True)
    resold_at: Mapped[datetime | None] = mapped_column(nullable=True)


class AffiliatePeriodClose(UUIDPKMixin, TimestampMixin, Base):
    """A consolidated month (ADM-06). After this row exists the month's
    results are history: nothing recomputes them (INT-10)."""

    __tablename__ = "sn_aff_period_closes"
    __table_args__ = (UniqueConstraint("organization_id", "period", name="uq_sn_aff_period_closes_period"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_tenants.id"), index=True)
    period: Mapped[str] = mapped_column(String(7))
    plan_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_aff_plan_versions.id"))
    closed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_accounts.id"), nullable=True
    )
    affiliates_count: Mapped[int] = mapped_column(Integer, default=0)
    qualified_count: Mapped[int] = mapped_column(Integer, default=0)
    total_points: Mapped[int] = mapped_column(Integer, default=0)
    total_bonus: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))


class AffiliateMonthlyResult(UUIDPKMixin, TimestampMixin, Base):
    """Frozen BCP, legs, BCT and level of one affiliate in a closed month (CAR-06)."""

    __tablename__ = "sn_aff_monthly_results"
    __table_args__ = (UniqueConstraint("organization_id", "period", "agent_id", name="uq_sn_aff_monthly_results_agent"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_tenants.id"), index=True)
    period: Mapped[str] = mapped_column(String(7), index=True)
    agent_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_promoter_profiles.id"), index=True)
    bcp: Mapped[int] = mapped_column(Integer)
    bct: Mapped[int] = mapped_column(Integer)
    #: [{"leg_agent_id": ..., "points": ...}], largest first.
    legs: Mapped[list] = mapped_column(JSONB, default=list)
    career_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bonus_amount: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    plan_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_aff_plan_versions.id"))
