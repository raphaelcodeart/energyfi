"""Mamify connection tables.

Mamify is the source of truth for people, the sponsor tree, orders and the
MamiCash/Mamix wallets; SOS Affiliate only computes the compensation plan on
top of them. These tables hold what the computation needs locally:

- a mirror of the Mamify network (`sn_mamify_members`), because the plan
  walks the whole depth and 13 positions up on every calculation and a month
  close must freeze what it saw;
- every order received (`sn_mamify_orders`), so a webhook delivered twice, or
  an order seen both by webhook and by the periodic check, is applied once;
- `sn_mamify_payouts` is history only: SOS no longer credits wallets
  (Mamify is read only), the table is kept for what was recorded.

Secrets (`api_key`, `payout_password`) are stored like the other suppliers'
credentials and never returned by any endpoint.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.foundation.db import Base, TimestampMixin, UUIDPKMixin


class MamifyConfig(UUIDPKMixin, TimestampMixin, Base):
    """One row per organization: how to reach Mamify and how to read it."""

    __tablename__ = "sn_mamify_config"
    __table_args__ = (UniqueConstraint("organization_id", name="uq_sn_mamify_config_org"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_tenants.id"), index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    base_url: Mapped[str] = mapped_column(String(255), default="https://www.mamify.app/m/api")
    api_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    #: Mamify app code (X-Fw360-App / `functionality`) of SOS Affiliate.
    functionality: Mapped[str | None] = mapped_column(String(64), nullable=True)
    #: The Mamify customer at the top of the SOS network (customer id, email
    #: or invite code, as the service API accepts). Its whole downline is
    #: mirrored; the root itself is the company and is not an affiliate.
    root_customer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    #: Statuses of a Mamify order, by id or title (lower case), that mean
    #: "paid" and "cancelled or refunded". The API documentation does not
    #: list them, so they are configuration, not code.
    paid_statuses: Mapped[list] = mapped_column(JSONB, default=list)
    cancelled_statuses: Mapped[list] = mapped_column(JSONB, default=list)
    #: Secret path segment of the webhook URL. Mamify does not sign its
    #: webhooks, so an unguessable URL is what tells a real one from a forgery.
    webhook_token: Mapped[str] = mapped_column(String(64))
    #: Unused: SOS never registers webhooks on Mamify (read only).
    webhook_ids: Mapped[dict] = mapped_column(JSONB, default=dict)
    # Unused since the connection became read only (4/11/2026): SOS never
    # credits a Mamify wallet. Kept so no stored value is destroyed; the
    # password, if one was ever saved, is wiped by migration 0009.
    payout_mode: Mapped[str] = mapped_column(String(16), default="MANUAL")
    #: Mamify login of the company account whose balance funds the credits.
    payout_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    payout_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    #: Commission kind -> wallet ("mamicash" / "mamix"), e.g. {"BC": "mamix"}.
    payout_wallets: Mapped[dict] = mapped_column(JSONB, default=dict)
    #: Wallet units credited per euro of commission.
    units_per_euro: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=Decimal(1))
    auto_payout: Mapped[bool] = mapped_column(Boolean, default=False)
    #: Account recorded as the author of tree moves made by the sync.
    sync_actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_accounts.id"), nullable=True
    )
    #: Set while a network sync runs, so the periodic task and the button
    #: never rewrite the tree at the same time. A stale value (a crashed run)
    #: expires after SYNC_LEASE.
    network_sync_started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_network_sync_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_network_sync_result: Mapped[dict] = mapped_column(JSONB, default=dict)
    last_orders_sync_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    last_error_at: Mapped[datetime | None] = mapped_column(nullable=True)
    #: Mamify apps whose products count for SOS (order lines carry the app).
    order_apps: Mapped[list] = mapped_column(JSONB, default=list)
    #: Products of those apps as rag/products/search lists them, {"items", "at"}:
    #: order lines carry only app, name and price, matched against this.
    product_catalog: Mapped[dict] = mapped_column(JSONB, default=dict)
    #: Share of the key's budget (60 calls/minute) the order poller may use.
    orders_calls_per_minute: Mapped[int] = mapped_column(Integer, default=30, server_default="30")
    #: Last newest-registrations check, and how far a running sync is.
    last_new_members_at: Mapped[datetime | None] = mapped_column(nullable=True)
    network_sync_progress: Mapped[dict] = mapped_column(JSONB, default=dict)


class MamifyMember(UUIDPKMixin, TimestampMixin, Base):
    """A person of the Mamify network, mirrored as a node of the SOS tree."""

    __tablename__ = "sn_mamify_members"
    __table_args__ = (
        UniqueConstraint("organization_id", "mamify_customer_id", name="uq_sn_mamify_members_customer"),
        UniqueConstraint("organization_id", "agent_id", name="uq_sn_mamify_members_agent"),
        Index("ix_sn_mamify_members_orders_checked", "organization_id", "orders_checked_at"),
        Index("ix_sn_mamify_members_org_agent", "organization_id", "agent_id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_tenants.id"), index=True)
    mamify_customer_id: Mapped[str] = mapped_column(String(64))
    agent_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_promoter_profiles.id"))
    #: Mamify id of the sponsor; NULL for people directly under the root.
    sponsor_customer_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    first_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    #: Depth in the Mamify network as Mamify reports it.
    mamify_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    registered_at: Mapped[datetime | None] = mapped_column(nullable=True)
    #: False once the person no longer appears in the Mamify network.
    present: Mapped[bool] = mapped_column(Boolean, default=True)
    last_seen_at: Mapped[datetime] = mapped_column()
    raw: Mapped[dict] = mapped_column(JSONB, default=dict)
    #: People this person brought in (present ones), refreshed by every sync.
    direct_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    #: Last time the order poller read this person's orders.
    orders_checked_at: Mapped[datetime | None] = mapped_column(nullable=True)
    #: "Aggiorna rete" of this person's branch: asked, done, and its outcome.
    branch_sync_requested_at: Mapped[datetime | None] = mapped_column(nullable=True)
    branch_synced_at: Mapped[datetime | None] = mapped_column(nullable=True)
    branch_sync_result: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")


class MamifyProductMap(UUIDPKMixin, TimestampMixin, Base):
    """Which plan product a Mamify product is. An order line of a product
    without a mapping generates nothing, and is shown as such."""

    __tablename__ = "sn_mamify_products"
    __table_args__ = (UniqueConstraint("organization_id", "mamify_product_id", name="uq_sn_mamify_products_product"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_tenants.id"), index=True)
    mamify_product_id: Mapped[str] = mapped_column(String(64))
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    #: A plan code (DIGITAL_AMBASSADOR, LARGE, ROMA_10, START...), or
    #: MAMICASH_TOPUP for a MamiCash top-up, whose value is the BM base.
    plan_code: Mapped[str] = mapped_column(String(32))


class MamifyOrder(UUIDPKMixin, TimestampMixin, Base):
    """A Mamify order as last received, and what SOS Affiliate made of it."""

    __tablename__ = "sn_mamify_orders"
    __table_args__ = (UniqueConstraint("organization_id", "mamify_order_id", name="uq_sn_mamify_orders_order"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_tenants.id"), index=True)
    mamify_order_id: Mapped[str] = mapped_column(String(64))
    buyer_customer_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    status_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status_title: Mapped[str | None] = mapped_column(String(120), nullable=True)
    total: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    ordered_at: Mapped[datetime | None] = mapped_column(nullable=True)
    # RECEIVED (not paid yet) / APPLIED / IGNORED (no SOS product) /
    # UNMATCHED (buyer not in the network) / CANCELLED / ERROR
    state: Mapped[str] = mapped_column(String(16), default="RECEIVED", index=True)
    message: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    #: Operations created from the lines of this order.
    operation_ids: Mapped[list] = mapped_column(JSONB, default=list)
    #: webhook / sync
    source: Mapped[str] = mapped_column(String(16), default="webhook")
    raw: Mapped[dict] = mapped_column(JSONB, default=dict)


class MamifyWebhookEvent(UUIDPKMixin, TimestampMixin, Base):
    """Every webhook call, stored before it is handled. Mamify sends no event
    id, so a hash of the body is the key that drops an exact redelivery."""

    __tablename__ = "sn_mamify_webhook_events"
    __table_args__ = (UniqueConstraint("organization_id", "body_hash", name="uq_sn_mamify_webhook_events_body"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_tenants.id"), index=True)
    event_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    body_hash: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    processed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class MamifyPayout(UUIDPKMixin, TimestampMixin, Base):
    """One credit of one commission to a Mamify wallet.

    UNIQUE on the commission: a commission is credited at most once. The row
    is written SENDING before the call; if the answer is lost it stays
    UNCERTAIN and nobody retries it automatically, because Mamify has no
    idempotency key and a retry could credit twice."""

    __tablename__ = "sn_mamify_payouts"
    __table_args__ = (UniqueConstraint("commission_id", name="uq_sn_mamify_payouts_commission"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_tenants.id"), index=True)
    commission_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_aff_commissions.id"))
    mamify_customer_id: Mapped[str] = mapped_column(String(64))
    wallet: Mapped[str] = mapped_column(String(16))
    amount_eur: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    units: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    # SENDING / SENT / FAILED / UNCERTAIN
    status: Mapped[str] = mapped_column(String(16), default="SENDING", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=1)
    response: Mapped[dict] = mapped_column(JSONB, default=dict)
    error: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(nullable=True)
    requested_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_accounts.id"), nullable=True
    )
