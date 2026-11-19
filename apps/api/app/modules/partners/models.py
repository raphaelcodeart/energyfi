import uuid

from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.foundation.db import Base, TimestampMixin, UUIDPKMixin


class Partner(UUIDPKMixin, TimestampMixin, Base):
    """An external energy supplier SOSNET brokers for, not an SOSNET product.
    A customer paying one directly can redeem part of that spend as wallet
    credit by uploading proof of payment (see
    invoice_redemptions.models.InvoiceRedemption). Only name and logo."""

    __tablename__ = "sn_merchants"
    __table_args__ = (UniqueConstraint("organization_id", "name", name="uq_sn_merchants_organization_name"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_tenants.id"), index=True
    )
    name: Mapped[str] = mapped_column(String(255))
    logo_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
