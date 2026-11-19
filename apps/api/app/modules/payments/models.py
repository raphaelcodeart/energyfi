"""Event-level idempotency for Stripe webhooks.

Stripe does not guarantee exactly-once delivery, and some events (e.g.
monthly `invoice.paid`) recur for the same object. Each event id is recorded
before its handler runs, and an already-seen event is acknowledged and
skipped.
"""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.foundation.db import Base, TimestampMixin, UUIDPKMixin


class StripeWebhookEvent(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "sn_stripe_events"
    __table_args__ = (
        # Inserted before handling, so concurrent redeliveries of the same
        # event cannot both be processed.
        UniqueConstraint("stripe_event_id", name="uq_sn_stripe_events_event_id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_tenants.id"), index=True
    )
    stripe_event_id: Mapped[str] = mapped_column(String(255))
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    #: NULL means the event was received but processing did not complete.
    processed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    #: Short support note on what was done, or why nothing was.
    outcome: Mapped[str | None] = mapped_column(String(255), nullable=True)
