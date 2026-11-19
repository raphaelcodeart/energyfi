import uuid

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.foundation.db import Base, TimestampMixin, UUIDPKMixin

# Audience: CUSTOMER (end-customer material), PROMOTER (sales/training
# material) or BOTH. No staff audience: this is not an admin announcement
# board.
AUDIENCES = ["CUSTOMER", "PROMOTER", "BOTH"]

# ARCHIVED posts are kept but hidden from both feeds (soft hide); DELETE is
# the separate permanent removal.
STATUSES = ["PUBLISHED", "ARCHIVED"]


class DocumentationPost(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "sn_knowledge_articles"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_tenants.id"), index=True
    )
    title: Mapped[str] = mapped_column(String(200))
    # Plain text, rendered with whitespace preserved (documentation-feed.tsx).
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    audience: Mapped[str] = mapped_column(String(16), default="BOTH")
    status: Mapped[str] = mapped_column(String(16), default="PUBLISHED", index=True)
    # Attachments are optional and independent: text-only or any mix of
    # image, PDF and video link.
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    pdf_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    pdf_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    video_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_accounts.id"))
