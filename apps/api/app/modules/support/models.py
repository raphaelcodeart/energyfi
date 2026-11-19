import uuid

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.foundation.db import Base, TimestampMixin, UUIDPKMixin

TICKET_CATEGORIES = {"ASSISTENZA_TECNICA", "FATTURAZIONE", "CONTRATTO", "COMMISSIONI", "ALTRO"}
TICKET_STATUSES = {"OPEN", "IN_PROGRESS", "RESOLVED", "CLOSED"}
TICKET_OPENER_ROLES = {"CUSTOMER", "PROMOTER"}


class Ticket(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "sn_support_cases"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_tenants.id"), index=True
    )
    opened_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_accounts.id"), index=True)
    # Stored at open time so a later role change cannot alter ticket
    # visibility.
    opened_by_role: Mapped[str] = mapped_column(String(32))
    subject: Mapped[str] = mapped_column(String(255))
    category: Mapped[str] = mapped_column(String(32), default="ALTRO")
    status: Mapped[str] = mapped_column(String(16), default="OPEN", index=True)
    # Optional: ties the ticket to a contract so staff has the context.
    contract_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_agreements.id"), nullable=True
    )


class TicketMessage(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "sn_support_replies"

    ticket_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_support_cases.id"), index=True)
    author_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_accounts.id"))
    # Stored for the same reason as Ticket.opened_by_role.
    author_role: Mapped[str] = mapped_column(String(32))
    body: Mapped[str] = mapped_column(Text)
