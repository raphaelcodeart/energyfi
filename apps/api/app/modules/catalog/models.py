import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.foundation.db import Base, TimestampMixin, UUIDPKMixin


#: How a sale's reference margin is derived. The product sets the margin's
#: size; the Split Plan decides how it is divided.
MARGIN_TYPES = ("FIXED", "PERCENTAGE")


class ProductCategory(UUIDPKMixin, TimestampMixin, Base):
    """Commercial category (telecom, energy, ...) used by Split Plans and
    reports. Unrelated to `Product.category`, which governs storefront and
    credit rules."""

    __tablename__ = "sn_product_categories"
    __table_args__ = (UniqueConstraint("organization_id", "code", name="uq_sn_product_categories_org_code"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_tenants.id"), index=True
    )
    code: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(120))
    #: Whether contracts need a supply point (POD/PDR): true for power and gas.
    requires_supply_point: Mapped[bool] = mapped_column(Boolean, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Company(UUIDPKMixin, TimestampMixin, Base):
    """The company behind a product (the energy supplier, the telco...).

    Each product belongs to one company. The company caps how deep into a
    collaborator's network its products reach (`max_network_depth`, null =
    no cap): the per-product network view stops there, and Split Plans for
    its products should not pay beyond it."""

    __tablename__ = "sn_suppliers"
    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_sn_suppliers_org_name"),
        CheckConstraint("max_network_depth IS NULL OR max_network_depth >= 1", name="depth_positive"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_tenants.id"), index=True
    )
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(String(2000), default="")
    logo_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    website_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    max_network_depth: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class CompanyMembership(UUIDPKMixin, TimestampMixin, Base):
    """A collaborator taking part in a company's plans ("Partecipa").

    It records who works with which company so staff can see each company's
    promoters. It does not gate commissions: sales pay by the Split Plan
    rules whether or not the seller joined. Leaving closes the row; joining
    again opens a new one, so the history stays."""

    __tablename__ = "sn_supplier_members"
    __table_args__ = (
        # One open membership per collaborator and company.
        Index("uq_sn_supplier_members_open", "company_id", "agent_id", unique=True,
              postgresql_where=text("left_at IS NULL")),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_tenants.id"), index=True
    )
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_suppliers.id"), index=True)
    agent_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_promoter_profiles.id"), index=True)
    joined_at: Mapped[datetime] = mapped_column()
    left_at: Mapped[datetime | None] = mapped_column(nullable=True)


class Product(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "sn_offers"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_tenants.id"), index=True
    )
    code: Mapped[str] = mapped_column(String(64))
    # ENERGY_CONTRACT / DIGITAL / PHYSICAL / SUBSCRIPTION; energy_type is null
    # for non-energy products.
    product_type: Mapped[str] = mapped_column(String(32), default="ENERGY_CONTRACT")
    energy_type: Mapped[str | None] = mapped_column(String(16), nullable=True)  # ELECTRICITY / GAS / DUAL_FUEL
    # PRIVATE / BUSINESS / BOTH: the single source of who may buy this product,
    # enforced by both customer-facing contract paths. Legacy values collapse
    # onto BUSINESS (see normalize_product_customer_type).
    customer_type: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE")
    commercial_category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_product_categories.id"), nullable=True, index=True
    )
    # Who supplies the product and how it may be paid, orthogonal to
    # product_type: INTERNAL (SOSNET's own supply, bank transfer only, never
    # discountable with credits), DROPSHIPPING (external supplier) or PARTNER
    # (on behalf of a collaborator). Defaults to the most restrictive value so
    # accepting credits is always an explicit opt-in.
    category: Mapped[str] = mapped_column(String(16), default="INTERNAL")
    #: The company behind the product; see Company.
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_suppliers.id"), nullable=True, index=True
    )


class ProductVersion(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "sn_offer_versions"
    __table_args__ = (
        CheckConstraint(
            "margin_type IS NULL"
            " OR (margin_type = 'FIXED' AND margin_amount_cents IS NOT NULL AND margin_amount_cents >= 0)"
            " OR (margin_type = 'PERCENTAGE' AND margin_percentage IS NOT NULL"
            " AND margin_percentage >= 0 AND margin_percentage <= 100)",
            name="margin_consistent",
        ),
    )

    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_offers.id"), index=True)
    version_label: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(String(2000), default="")
    image_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    base_price_cents: Mapped[int] = mapped_column(BigInteger)
    initial_fee_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    recurring_fee_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    billing_period: Mapped[str] = mapped_column(String(16), default="MONTHLY")
    # Drives Contract.expires_at; null means no renewal (one-off purchases).
    # No `default=`: SQLAlchemy would apply it even to an explicit None. The
    # default of 12 lives in the create schemas, which can tell an omitted
    # field from an explicit null.
    contract_duration_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tax_configuration: Mapped[dict] = mapped_column(JSONB, default=dict)
    commission_plan_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_payout_plans.id"), nullable=True
    )
    # Legacy token model: {career_level_code: token_cents} per-product
    # override of Rank.personal_token_cents. Not used by the Split Plan engine.
    commission_tokens: Mapped[dict] = mapped_column(JSONB, default=dict)
    required_documents: Mapped[dict] = mapped_column(JSONB, default=dict)
    terms_version: Mapped[str] = mapped_column(String(32), default="1.0")
    valid_from: Mapped[datetime] = mapped_column()
    valid_to: Mapped[datetime | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE")
    # 0-100: share of the price payable with wallet credit; the rest is bank
    # transfer. Versioned because it is an economic term. The service layer
    # forces it to 0 for INTERNAL products.
    credit_discount_percentage: Mapped[int] = mapped_column(Integer, default=0)
    # Whether orders may opt into instant cashback: the customer pays a
    # surcharge (orders/service.py::ORDER_CASHBACK_PERCENTAGE) and the whole
    # amount paid is credited as SosnetCash once payment is confirmed. Always
    # False for INTERNAL products, which are sold as contracts, not orders.
    cashback_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    # 0-100: share of a contract's gross amount (net + VAT) credited as
    # SosnetCash once the contract is paid. Unlike cashback_enabled (opt-in,
    # surcharge-funded, for orders) this is automatic with no surcharge.
    # 0 disables it. See pricing.cashback_mode_for.
    contract_cashback_percentage: Mapped[int] = mapped_column(Integer, default=0)
    # Legacy first-referrer bonus: a one-off amount per contract for the
    # promoter who originally brought the customer in, never the upline.
    first_referrer_bonus_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    first_referrer_bonus_cents: Mapped[int] = mapped_column(BigInteger, default=0)

    # --- Reference margin ---------------------------------------------------
    # Fixed amount or percentage of the net contract amount (VAT excluded).
    # Versioned like the price. NULL means unconfigured: no commission can be
    # computed and the contract cannot activate.
    margin_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    margin_amount_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    margin_percentage: Mapped[float | None] = mapped_column(Numeric(7, 4), nullable=True)
