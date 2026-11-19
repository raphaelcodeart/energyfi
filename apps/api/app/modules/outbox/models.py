import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.foundation.db import Base, TimestampMixin, UUIDPKMixin


class DomainOutbox(UUIDPKMixin, TimestampMixin, Base):
    """Transactional outbox (ADR 0005): events are written in the same
    transaction as the state change and published only after commit, so no
    event fires for a rolled-back change and no committed change goes
    unannounced."""

    __tablename__ = "sn_event_outbox"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_tenants.id"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    payload: Mapped[dict] = mapped_column(JSONB)
    processed_at: Mapped[datetime | None] = mapped_column(nullable=True, index=True)
