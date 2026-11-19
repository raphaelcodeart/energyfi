"""Leads: opportunities a Promoter refers without handling the negotiation.

A lead earns nothing by itself. The Promoter fee comes from the PROMOTER rule
of the sale's Split Plan once the lead converts into a contract
(`Contract.lead_id`), and accrues like every other share.
"""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.foundation.db import Base, TimestampMixin, UUIDPKMixin

#: NEW -> QUALIFIED -> CONVERTED; LOST and EXPIRED are terminal.
LEAD_STATUSES = ("NEW", "QUALIFIED", "CONVERTED", "LOST", "EXPIRED")
OPEN_LEAD_STATUSES = ("NEW", "QUALIFIED")


class Lead(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "sn_leads"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_tenants.id"), index=True
    )
    promoter_agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_promoter_profiles.id"), index=True
    )
    #: Existing customer, if any; otherwise contact details suffice.
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_clients.id"), nullable=True, index=True
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_offers.id"), nullable=True
    )
    contact_name: Mapped[str] = mapped_column(String(200))
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    notes: Mapped[str] = mapped_column(String(2000), default="")
    status: Mapped[str] = mapped_column(String(16), default="NEW", index=True)
    #: Assigned handler; becomes the contract's seller.
    assigned_agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_promoter_profiles.id"), nullable=True
    )
    converted_contract_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_agreements.id", use_alter=True), nullable=True
    )
    converted_at: Mapped[datetime | None] = mapped_column(nullable=True)
    closed_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_accounts.id"), nullable=True
    )
    updated_at: Mapped[datetime | None] = mapped_column(nullable=True)
