import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.foundation.db import Base, TimestampMixin, UUIDPKMixin


class AgentProfile(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "sn_promoter_profiles"
    __table_args__ = (
        UniqueConstraint("organization_id", "promoter_code", name="uq_sn_invite_codes_agent"),
        Index("ix_sn_promoter_profiles_org_joined", "organization_id", "joined_at"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_tenants.id"), index=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_accounts.id"), nullable=True
    )
    # Denormalized "first last" for read paths needing one string; always
    # derived from first_name/last_name on write, never edited directly.
    display_name: Mapped[str] = mapped_column(String(255))
    first_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    promoter_code: Mapped[str] = mapped_column(String(32))
    # ACTIVE / SUSPENDED / TERMINATED / PENDING_APPROVAL. New collaborators are
    # created as suggestions (PENDING_APPROVAL) and activated by a
    # network.approve-gated action. They already appear in the tree, but
    # create_contract() rejects non-ACTIVE producers, so they cannot sell yet.
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE")
    photo_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    joined_at: Mapped[datetime] = mapped_column()
    current_rank_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_career_levels.id"), nullable=True
    )
    #: Read shortcut for today's commercial role. The source of truth, and the
    #: only thing the commission engine reads, is `sn_seller_role_history`.
    current_commercial_role_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_commercial_roles.id"), nullable=True
    )
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_accounts.id"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Blacklisted by an admin (stronger than a deactivation): a reapplication
    # via "Lavora con noi" requires manual approval instead of auto-activating.
    is_blacklisted: Mapped[bool] = mapped_column(Boolean, default=False)
    # Collaboration-agreement acceptance, confirmed by an emailed OTP to prove
    # the account holder agreed. Visible to admins (docs/business-rules.md).
    collaboration_contract_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    #: Every accepted document, as {key: {"version": ..., "accepted_at": <iso>}}
    #: (see network/collaboration_documents.py). JSONB so the document set can
    #: change without migrations. The two columns above mirror the main
    #: contract for existing readers.
    collaboration_accepted_documents: Mapped[dict] = mapped_column(JSONB, default=dict)
    collaboration_accepted_at: Mapped[datetime | None] = mapped_column(nullable=True)
    collaboration_otp_verified_at: Mapped[datetime | None] = mapped_column(nullable=True)


class NetworkNode(UUIDPKMixin, TimestampMixin, Base):
    """Current-state pointer, one row per agent, for cheap "direct parent now"
    lookups. Authoritative history is in NetworkEdge/NetworkClosure."""

    __tablename__ = "sn_tree_nodes"
    __table_args__ = (
        # Only one open (effective_to IS NULL) node per agent; closed history
        # rows must not collide with it.
        Index(
            "uq_sn_tree_nodes_active_agent",
            "organization_id",
            "agent_id",
            unique=True,
            postgresql_where=text("effective_to IS NULL"),
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_tenants.id"), index=True
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_promoter_profiles.id"), index=True
    )
    direct_parent_agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_promoter_profiles.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE")
    effective_from: Mapped[datetime] = mapped_column()
    effective_to: Mapped[datetime | None] = mapped_column(nullable=True)


class NetworkEdge(UUIDPKMixin, TimestampMixin, Base):
    """Append-only history of every parent/child relationship. Rows are closed
    (effective_to set), never deleted or overwritten."""

    __tablename__ = "sn_tree_links"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_tenants.id"), index=True
    )
    parent_agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_promoter_profiles.id"), index=True
    )
    child_agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_promoter_profiles.id"), index=True
    )
    effective_from: Mapped[datetime] = mapped_column()
    effective_to: Mapped[datetime | None] = mapped_column(nullable=True)


class NetworkClosure(Base):
    """Transitive closure of NetworkEdge, maintained transactionally on every
    move, including the reflexive depth-0 row per agent. Network reads should
    use this table; NetworkEdge/NetworkNode serve writes and point lookups."""

    __tablename__ = "sn_tree_paths"
    __table_args__ = (
        Index("ix_sn_tree_paths_org_ancestor", "organization_id", "ancestor_agent_id"),
        Index("ix_sn_tree_paths_org_descendant", "organization_id", "descendant_agent_id"),
        Index("ix_sn_tree_paths_org_ancestor_depth", "organization_id", "ancestor_agent_id", "depth"),
        Index("ix_sn_tree_paths_org_descendant_depth", "organization_id", "descendant_agent_id", "depth"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_tenants.id"), primary_key=True
    )
    ancestor_agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_promoter_profiles.id"), primary_key=True
    )
    descendant_agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_promoter_profiles.id"), primary_key=True
    )
    effective_from: Mapped[datetime] = mapped_column(primary_key=True)
    depth: Mapped[int] = mapped_column(Integer)
    effective_to: Mapped[datetime | None] = mapped_column(nullable=True)


class NetworkAssignmentHistory(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "sn_tree_moves"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_tenants.id"), index=True
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_promoter_profiles.id"))
    old_parent_agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_promoter_profiles.id"), nullable=True
    )
    new_parent_agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_promoter_profiles.id"), nullable=True
    )
    requested_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_accounts.id"))
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_accounts.id"), nullable=True
    )
    reason: Mapped[str] = mapped_column(String(500))
    effective_at: Mapped[datetime] = mapped_column()


class NetworkSnapshot(UUIDPKMixin, TimestampMixin, Base):
    """Immutable copy of a contract's ancestor chain, taken at activation.
    Contracts reference it instead of the live closure table, so later moves
    cannot rewrite historical attribution."""

    __tablename__ = "sn_tree_snapshots"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_tenants.id"), index=True
    )
    reason: Mapped[str] = mapped_column(String(64))
    #: Date the chain was read at (the sale date), not the write time.
    as_of: Mapped[datetime | None] = mapped_column(nullable=True)


class NetworkSnapshotNode(Base):
    __tablename__ = "sn_tree_snapshot_nodes"

    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_tree_snapshots.id"), primary_key=True
    )
    ancestor_agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_promoter_profiles.id"), primary_key=True
    )
    depth: Mapped[int] = mapped_column(Integer)
    rank_id_at_snapshot: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_career_levels.id"), nullable=True
    )
    #: This person's commercial role at the sale date.
    commercial_role_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_commercial_roles.id"), nullable=True
    )
    role_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    #: Status when the chain was frozen. A non-ACTIVE person keeps their level
    #: (levels never shift up) but receives no share; the plan's fallback
    #: strategy handles the empty slot.
    agent_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
