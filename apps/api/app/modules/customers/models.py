import uuid

from sqlalchemy import BigInteger, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.foundation.db import Base, TimestampMixin, UUIDPKMixin


class Customer(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "sn_clients"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_tenants.id"), index=True
    )
    # Optional login link: imported or admin-created customers may have none.
    # Ownership checks use this column, never email matching.
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_accounts.id"), nullable=True, unique=True
    )
    kind: Mapped[str] = mapped_column(String(32))  # PRIVATE / SOLE_PROPRIETOR / COMPANY / CONDOMINIUM
    fiscal_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    vat_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    email: Mapped[str] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    pec: Mapped[str | None] = mapped_column(String(255), nullable=True)
    photo_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)


class CustomerProfile(Base):
    __tablename__ = "sn_client_profiles"

    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_clients.id"), primary_key=True
    )
    first_name: Mapped[str] = mapped_column(String(128))
    last_name: Mapped[str] = mapped_column(String(128))


class Company(Base):
    __tablename__ = "sn_businesses"

    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_clients.id"), primary_key=True
    )
    company_name: Mapped[str] = mapped_column(String(255))
    legal_form: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sdi_code: Mapped[str | None] = mapped_column(String(16), nullable=True)


class Address(UUIDPKMixin, Base):
    __tablename__ = "sn_postal_addresses"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_tenants.id"), index=True
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_clients.id"), index=True)
    kind: Mapped[str] = mapped_column(String(32), default="SUPPLY")
    street: Mapped[str] = mapped_column(String(255))
    city: Mapped[str] = mapped_column(String(128))
    province: Mapped[str] = mapped_column(String(8))
    postal_code: Mapped[str] = mapped_column(String(16))
    country: Mapped[str] = mapped_column(String(2), default="IT")


class SupplyPoint(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "sn_utility_points"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_tenants.id"), index=True
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_clients.id"), index=True)
    # Human-readable label, since POD/PDR codes mean nothing to a person.
    # Derived from energy_type + address when omitted; editable later.
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    #: ELECTRICITY / GAS / DUAL_FUEL. Null only while a pratica's package is
    #: not chosen yet, since the package determines it.
    energy_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    pod_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    pdr_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    meter_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    supply_address_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_postal_addresses.id"))
    estimated_consumption: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    actual_consumption: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    provider_reference: Mapped[str | None] = mapped_column(String(128), nullable=True)
