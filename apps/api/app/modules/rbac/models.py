import uuid

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.foundation.db import Base, TimestampMixin, UUIDPKMixin

# Fixed catalogue of system roles (also seeded as rows for FK integrity).
SYSTEM_ROLES = [
    "SUPER_ADMIN",
    "ORGANIZATION_ADMIN",
    "ADMIN",
    "BACK_OFFICE_OPERATOR",
    "ACCOUNTING_OPERATOR",
    "SALES_MANAGER",
    # Software ACCESS roles, not commercial roles: FINANCE approves and pays
    # commissions, NETWORK_MANAGER manages the network and commercial roles.
    # A person's commercial role (Networker, Agent, Influencer...) lives in
    # sn_commercial_roles.
    "FINANCE",
    "NETWORK_MANAGER",
    "TEAM_LEADER",
    "PROMOTER",
    "CUSTOMER",
    "AUDITOR",
]

# Flat list rather than an enum, so permissions can be added by data
# migration without a deploy.
PERMISSIONS = [
    "customers.read", "customers.create", "customers.update",
    "contracts.read", "contracts.create", "contracts.submit",
    "contracts.review", "contracts.approve", "contracts.activate",
    "network.read_branch", "network.manage", "network.recruit", "network.approve",
    "commissions.read_own", "commissions.read_branch", "commissions.simulate",
    "commissions.approve", "commissions.evaluate_ranks", "commission_adjustments.create",
    "payments.manage", "documents.download", "reports.export", "reports.read",
    "audit.read", "settings.manage",
    "products.read", "products.manage",
    "tickets.create", "tickets.respond", "tickets.delete",
    "documents.upload", "documents.review",
    "documentation.manage",
    "wallet.manage",
    "imported_products.manage",
    "commercial_roles.manage", "split_plans.manage", "split_plans.activate",
    "commissions.pay", "leads.create", "leads.manage",
]

# Default role -> permission grants used for seeding: a bootstrap default,
# not a hardcoded ceiling.
DEFAULT_ROLE_PERMISSIONS: dict[str, list[str]] = {
    "SUPER_ADMIN": PERMISSIONS,
    "ORGANIZATION_ADMIN": PERMISSIONS,
    "ADMIN": [
        "customers.read", "customers.create", "customers.update",
        "contracts.read", "contracts.create", "contracts.submit",
        "contracts.review", "contracts.approve", "contracts.activate",
        "network.read_branch", "network.manage", "network.recruit",
        "commissions.read_branch", "commissions.simulate", "commissions.approve",
        "commission_adjustments.create", "payments.manage", "documents.download",
        "reports.export", "reports.read", "audit.read", "settings.manage",
        "products.read", "products.manage", "tickets.respond", "tickets.delete",
        "documents.upload", "documents.review", "documentation.manage", "wallet.manage",
        "imported_products.manage",
        "commercial_roles.manage", "split_plans.manage", "split_plans.activate",
        "commissions.pay", "leads.create", "leads.manage",
    ],
    "FINANCE": [
        "contracts.read", "customers.read", "products.read", "network.read_branch",
        "commissions.read_branch", "commissions.simulate", "commissions.approve", "commissions.pay",
        "commission_adjustments.create", "payments.manage", "reports.read", "reports.export",
        "split_plans.manage", "audit.read",
    ],
    "NETWORK_MANAGER": [
        "customers.read", "contracts.read", "products.read",
        "network.read_branch", "network.manage", "network.recruit", "network.approve",
        "commercial_roles.manage", "commissions.read_branch", "commissions.simulate",
        "leads.create", "leads.manage", "reports.read",
    ],
    "BACK_OFFICE_OPERATOR": [
        "customers.read", "customers.create", "customers.update",
        "contracts.read", "contracts.create", "contracts.submit", "contracts.review",
        "documents.download", "products.read", "tickets.respond",
        "documents.upload", "documents.review",
    ],
    "ACCOUNTING_OPERATOR": [
        "contracts.read", "payments.manage", "commissions.read_branch",
        "commission_adjustments.create", "reports.export", "reports.read",
        "commissions.approve", "commissions.pay",
    ],
    "SALES_MANAGER": [
        "customers.read", "contracts.read", "contracts.approve",
        "network.read_branch", "network.manage", "network.recruit",
        "commissions.read_branch", "commissions.simulate", "reports.export", "reports.read",
        "products.read", "products.manage",
    ],
    "TEAM_LEADER": [
        "customers.read", "contracts.read", "contracts.create",
        "network.read_branch", "network.recruit",
        "commissions.read_own", "commissions.read_branch", "products.read",
    ],
    "PROMOTER": [
        "customers.read", "customers.create",
        "contracts.read", "contracts.create",
        "network.read_branch", "network.recruit", "commissions.read_own",
        # Read-only earnings preview that never writes to the ledger
        # (commissions/simulations/simulate.py).
        "commissions.simulate", "products.read", "tickets.create", "leads.create",
        # "Miei Clienti": documents only for contracts they produced, enforced by
        # documents/router.py::_assert_contract_document_access. No
        # documents.review, which is staff-only.
        "documents.upload", "documents.download",
    ],
    "CUSTOMER": [
        "contracts.read", "documents.download", "documents.upload", "products.read", "tickets.create",
    ],
    "AUDITOR": ["audit.read", "reports.export", "reports.read"],
}


class Role(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "sn_roles"
    __table_args__ = (UniqueConstraint("organization_id", "code", name="uq_sn_roles_org_code"),)

    # organization_id NULL = system-wide role definition available to every org
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_tenants.id"), nullable=True, index=True
    )
    code: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(128))


class Permission(UUIDPKMixin, Base):
    __tablename__ = "sn_permissions"

    code: Mapped[str] = mapped_column(String(64), unique=True)
    description: Mapped[str] = mapped_column(String(255), default="")


class RolePermission(Base):
    __tablename__ = "sn_role_grants"

    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_roles.id"), primary_key=True
    )
    permission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_permissions.id"), primary_key=True
    )


class UserRole(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "sn_account_roles"
    __table_args__ = (
        UniqueConstraint("user_id", "organization_id", "role_id", name="uq_sn_account_roles"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_accounts.id"), index=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_tenants.id"), index=True
    )
    role_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_roles.id"))
