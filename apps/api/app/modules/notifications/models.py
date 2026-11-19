import uuid

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.foundation.db import Base, TimestampMixin, UUIDPKMixin

# Notification subject: selects the sidebar item with the unread dot
# (app-shell.tsx NOTIFICATION_NAV_MAP) and the bell dropdown icon/label.
NOTIFICATION_TYPES = {
    "CONTRACT_CREATED",
    "TICKET_CREATED",
    "PROMOTER_APPROVAL_REQUESTED",
    "PROMOTER_APPROVED",
    "PROMOTER_REJECTED",
    "COMMISSION_EARNED",
    "CASHBACK_RECEIVED",
    "WALLET_TRANSFER_RECEIVED",
    "INVOICE_REDEMPTION_VERIFIED",
    "INVOICE_REDEMPTION_REJECTED",
    "ORDER_CREDIT_APPLIED",
    "ORDER_PAID",
    "ORDER_PAYMENT_PROOF_UPLOADED",
    "IMPORTED_ORDER_CREATED",
}


class Notification(UUIDPKMixin, TimestampMixin, Base):
    """One row per recipient user, not per role, fanned out by
    notify_staff(), so read state is tracked per person
    (docs/business-rules.md#notifications)."""

    __tablename__ = "sn_inbox_messages"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_tenants.id"), index=True
    )
    recipient_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_accounts.id"), index=True
    )
    type: Mapped[str] = mapped_column(String(64), index=True)
    entity_type: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(255))
    body: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
