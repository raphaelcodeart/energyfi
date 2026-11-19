import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.foundation.db import Base, TimestampMixin, UUIDPKMixin

#: "OTHER" covers anything beyond the fixed list (back of an ID, a lease, a
#: delega, a visura requested by hand). It is the only type with a
#: `description`, supplied by the uploader, so the review queue stays
#: readable.
DOCUMENT_TYPE_OTHER = "OTHER"
DOCUMENT_TYPES = {"IDENTITY", "FISCAL_CODE", "UTILITY_BILL", "CHAMBER_OF_COMMERCE", DOCUMENT_TYPE_OTHER}
DOCUMENT_STATUSES = {"PENDING_REVIEW", "APPROVED", "REJECTED"}
ALLOWED_DOCUMENT_CONTENT_TYPES = {"application/pdf", "image/jpeg", "image/png"}
MAX_DOCUMENT_BYTES = 15 * 1024 * 1024  # 15 MB: a phone photo of a bill/ID
MIN_DOCUMENT_DESCRIPTION_LENGTH = 3
#: Fits a descriptive label while staying on one line in the review list.
MAX_DOCUMENT_DESCRIPTION_LENGTH = 120


class Document(UUIDPKMixin, TimestampMixin, Base):
    """A sensitive customer document attached to a contract or pratica
    (identity, fiscal code, utility bill, company registration, or a labelled
    extra attachment, see DOCUMENT_TYPE_OTHER).

    Stored in the private "sosnet-documents" bucket, never the public
    "sosnet-media" one (see foundation/storage.py and security-model.md
    §Documents). Access is only through short-lived presigned URLs issued after
    an authorization check."""

    __tablename__ = "sn_stored_files"
    __table_args__ = (CheckConstraint("num_nonnulls(contract_id, contract_request_id) = 1", name="one_owner"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_tenants.id"), index=True
    )
    #: Exactly one of these is set. A pratica document (identity, fiscal code,
    #: visura, or one bill listing every point) is uploaded once and counts for
    #: every contract in it; a contract document belongs to that supply point
    #: alone. See documents/service.py::get_contract_documents_status.
    contract_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_agreements.id"), index=True, nullable=True
    )
    contract_request_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_agreement_requests.id"), index=True, nullable=True
    )
    document_type: Mapped[str] = mapped_column(String(32))
    #: Uploader-supplied label, only for DOCUMENT_TYPE_OTHER. Other types have
    #: fixed labels (schemas.py::DOCUMENT_TYPE_LABELS); relabelling them would
    #: mislead the required-document check.
    description: Mapped[str | None] = mapped_column(String(MAX_DOCUMENT_DESCRIPTION_LENGTH), nullable=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    # Opaque key in the private bucket, used only server-side to mint
    # presigned GET URLs.
    storage_key: Mapped[str] = mapped_column(String(500), unique=True)
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    uploaded_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_accounts.id"))
    # Stored at upload time, like tickets.opened_by_role, so later role
    # changes never rewrite history.
    uploaded_by_role: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), default="PENDING_REVIEW", index=True)
    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_accounts.id"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    review_note: Mapped[str | None] = mapped_column(String(1000), nullable=True)
