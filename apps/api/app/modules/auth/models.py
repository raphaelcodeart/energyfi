import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.foundation.db import Base, TimestampMixin, UUIDPKMixin


class Session(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "sn_login_sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_accounts.id"), index=True)
    refresh_token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    expires_at: Mapped[datetime] = mapped_column()
    revoked_at: Mapped[datetime | None] = mapped_column(nullable=True)


class PasswordResetToken(UUIDPKMixin, TimestampMixin, Base):
    """The raw token only ever leaves in the reset link; the DB stores its
    hash, so a database leak alone never yields a usable reset token."""

    __tablename__ = "sn_password_recoveries"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_accounts.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column()
    used_at: Mapped[datetime | None] = mapped_column(nullable=True)


class EmailVerificationToken(UUIDPKMixin, TimestampMixin, Base):
    """Opaque token, hashed at rest, emailed at self-registration and consumed
    once by GET /auth/verify-email to set users.email_verified_at."""

    __tablename__ = "sn_email_confirmations"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_accounts.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column()
    used_at: Mapped[datetime | None] = mapped_column(nullable=True)


class OtpCode(UUIDPKMixin, TimestampMixin, Base):
    """Short numeric code emailed to confirm a sensitive self-service action
    (promoter application, wallet credit spend at checkout). `purpose`
    distinguishes the gated actions so new ones need no new table."""

    __tablename__ = "sn_one_time_codes"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_accounts.id"), index=True)
    purpose: Mapped[str] = mapped_column(String(32), index=True)
    code_hash: Mapped[str] = mapped_column(String(64), index=True)
    expires_at: Mapped[datetime] = mapped_column()
    used_at: Mapped[datetime | None] = mapped_column(nullable=True)
