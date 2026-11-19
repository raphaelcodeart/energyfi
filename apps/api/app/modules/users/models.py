import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.foundation.db import Base, TimestampMixin, UUIDPKMixin


class User(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "sn_accounts"
    __table_args__ = (UniqueConstraint("organization_id", "email", name="uq_sn_accounts_org_email"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_tenants.id"), index=True
    )
    email: Mapped[str] = mapped_column(String(255), index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    # ACTIVE / FROZEN. A frozen account cannot log in and its sessions are
    # revoked, while all data and history stay intact (see
    # users/service.py::freeze_user and auth/service.py::authenticate).
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE")
    email_verified_at: Mapped[datetime | None] = mapped_column(nullable=True)
    failed_login_attempts: Mapped[int] = mapped_column(default=0)
    locked_until: Mapped[datetime | None] = mapped_column(nullable=True)
    # Set at self-registration when the mandatory privacy checkbox is accepted
    # (auth/service.py::register_with_referral). NULL for accounts without a
    # recorded consent, e.g. admin-created ones; never defaulted to accepted.
    privacy_accepted_at: Mapped[datetime | None] = mapped_column(nullable=True)
    # Required profile fields (users/service.py::is_profile_complete()). On
    # User rather than Customer/AgentProfile: this is role-independent identity
    # data, and promoters have no Customer row.
    fiscal_code: Mapped[str | None] = mapped_column(String(16), nullable=True)
    residence_street: Mapped[str | None] = mapped_column(String(255), nullable=True)
    residence_city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    residence_province: Mapped[str | None] = mapped_column(String(2), nullable=True)
    residence_postal_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    residence_country: Mapped[str] = mapped_column(String(2), default="IT")
