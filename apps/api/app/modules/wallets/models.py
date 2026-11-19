import uuid

from sqlalchemy import BigInteger, Boolean, CheckConstraint, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.foundation.db import Base, TimestampMixin, UUIDPKMixin

# ADMIN_CREDIT: money enters from outside the wallet system (from_wallet_id NULL).
# TRANSFER: peer-to-peer, both sides set.
# PURCHASE_DEBIT: money leaves a wallet to pay (part of) an order (to_wallet_id NULL).
# REVERSAL: a correction linked to the original row via reverses_transaction_id;
# settled rows are never mutated (same pattern as CommissionReversal).
WALLET_TRANSACTION_TYPES = ["ADMIN_CREDIT", "TRANSFER", "PURCHASE_DEBIT", "REVERSAL"]


class Wallet(UUIDPKMixin, TimestampMixin, Base):
    """One wallet per login, created lazily by get_or_create_wallet().

    Owned by user_id alone because one login can be both customer and
    promoter. `address` is a globally unique, crypto-style identifier;
    organization_id scopes queries and the same-org transfer rule.
    balance_cents can never go negative: enforced by an atomic conditional
    UPDATE in the service and by a CHECK constraint."""

    __tablename__ = "sn_credit_accounts"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_sn_credit_accounts_user_id"),
        UniqueConstraint("address", name="uq_sn_credit_accounts_address"),
        CheckConstraint("balance_cents >= 0", name="balance_non_negative"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_tenants.id"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_accounts.id"), index=True)
    # "0x" + 40 hex chars; uniqueness is guaranteed by the DB constraint.
    address: Mapped[str] = mapped_column(String(42), index=True)
    balance_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    # Peer-to-peer sending is off by default and enabled per wallet by an
    # admin. A per-wallet flag rather than a role permission, because it is
    # granted to individual promoters, not to a whole role.
    # See docs/business-rules.md#internal-wallet.
    can_transfer: Mapped[bool] = mapped_column(Boolean, default=False)


class WalletTransaction(UUIDPKMixin, TimestampMixin, Base):
    """Append-only ledger with one row per transaction (not double-entry).

    A NULL from_wallet_id means money came from outside the wallet system; a
    NULL to_wallet_id means it left it. At least one side is always set.
    idempotency_key is unique, so a retried submit cannot post twice.
    See docs/business-rules.md#internal-wallet."""

    __tablename__ = "sn_credit_ledger"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_sn_credit_ledger_idempotency_key"),
        CheckConstraint(
            "from_wallet_id IS NOT NULL OR to_wallet_id IS NOT NULL",
            name="has_a_side",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_tenants.id"), index=True
    )
    from_wallet_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_credit_accounts.id"), nullable=True, index=True
    )
    to_wallet_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_credit_accounts.id"), nullable=True, index=True
    )
    amount_cents: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    # One of WALLET_TRANSACTION_TYPES.
    type: Mapped[str] = mapped_column(String(16), index=True)
    # Contract behind a cashback ADMIN_CREDIT; NULL otherwise.
    reference_contract_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_agreements.id"), nullable=True
    )
    # Structured reason for an ADMIN_CREDIT: MANUAL_ADMIN, or the
    # INVOICE_REDEMPTION_BASE / INVOICE_REDEMPTION_BONUS pair written by a
    # confirmed invoice redemption. NULL where `type` says enough.
    source: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reference_invoice_redemption_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_receipt_claims.id"), nullable=True
    )
    # The reference_*order_id columns identify the order a PURCHASE_DEBIT (or
    # the REVERSAL refunding it) paid for; one column per order table so each
    # is a real foreign key. At most one is set per row.
    reference_order_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_shop_orders.id"), nullable=True
    )
    reference_imported_order_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_supplier_item_orders.id"), nullable=True
    )
    reference_cj_order_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_cj_orders.id"), nullable=True
    )
    reference_shopify_order_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_shopify_orders.id"), nullable=True
    )
    reference_aliexpress_order_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_aliexpress_orders.id"), nullable=True
    )
    reference_sosnet_market_order_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_market_orders.id"), nullable=True, index=True
    )
    # Set only on a REVERSAL: the row it corrects.
    reverses_transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_credit_ledger.id"), nullable=True
    )
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # The admin for credits/reversals, the sender for a TRANSFER.
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_accounts.id"), nullable=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(128))
