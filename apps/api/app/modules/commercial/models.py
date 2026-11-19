"""Commercial roles: who sells and under which economic model.

Distinct from access roles (`rbac`), which govern screens and actions. A
PROMOTER account can hold any commercial role and change it over time without
affecting what it sees. The engine never branches on `code`; it reads only the
configuration (`network_depth`, `allows_delegation`, `can_close_sales`, ...).
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.foundation.db import Base, TimestampMixin, UUIDPKMixin

#: Descriptive only (admin UI and plan validation); Split Plans set the shares.
COMMISSION_MODES = ("PERCENTAGE", "FIXED", "MIXED", "REFERRAL_FEE", "CUSTOM")


class CommercialRole(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "sn_commercial_roles"
    __table_args__ = (UniqueConstraint("organization_id", "code", name="uq_sn_commercial_roles_org_code"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_tenants.id"), index=True
    )
    code: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(String(1000), default="")
    commission_mode: Mapped[str] = mapped_column(String(16), default="PERCENTAGE")
    #: Levels above a seller with this role the engine may reach (NULL = plan decides).
    network_depth: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #: May have delegates selling on their behalf (influencer model).
    allows_delegation: Mapped[bool] = mapped_column(Boolean, default=False)
    allows_downline: Mapped[bool] = mapped_column(Boolean, default=True)
    #: False for referrers, who bring opportunities but do not close them.
    can_close_sales: Mapped[bool] = mapped_column(Boolean, default=True)
    #: Assigned to members joining without an explicit role; one per organization.
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    updated_at: Mapped[datetime | None] = mapped_column(nullable=True)


class SellerRoleHistory(UUIDPKMixin, TimestampMixin, Base):
    """A member's commercial role over time. Sales use the role valid on the
    sale date, not the current one.

    Half-open periods [valid_from, valid_to); the current one has valid_to
    NULL. A database exclusion constraint prevents overlapping periods."""

    __tablename__ = "sn_seller_role_history"
    __table_args__ = (
        Index(
            "uq_sn_seller_role_history_open",
            "agent_id",
            unique=True,
            postgresql_where=text("valid_to IS NULL"),
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_tenants.id"), index=True
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_promoter_profiles.id"), index=True
    )
    role_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_commercial_roles.id"))
    valid_from: Mapped[datetime] = mapped_column()
    valid_to: Mapped[datetime | None] = mapped_column(nullable=True)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    changed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_accounts.id"), nullable=True
    )


class Delegation(UUIDPKMixin, TimestampMixin, Base):
    """A delegate selling on behalf of an influencer.

    Not a second tree: the delegate stays in the single network. This row is
    needed only when the link must be explicit (e.g. the delegate has another
    sponsor). It overrides chain search and, like all money-relevant data, is
    dated."""

    __tablename__ = "sn_delegations"
    __table_args__ = (
        Index(
            "uq_sn_delegations_open_delegate",
            "delegate_agent_id",
            unique=True,
            postgresql_where=text("valid_to IS NULL"),
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_tenants.id"), index=True
    )
    influencer_agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_promoter_profiles.id"), index=True
    )
    delegate_agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_promoter_profiles.id"), index=True
    )
    valid_from: Mapped[datetime] = mapped_column()
    valid_to: Mapped[datetime | None] = mapped_column(nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_accounts.id"), nullable=True
    )
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
