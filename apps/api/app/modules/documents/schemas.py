import uuid
from datetime import datetime

from pydantic import BaseModel, field_validator

from app.modules.documents.models import DOCUMENT_STATUSES, DOCUMENT_TYPES


class DocumentRead(BaseModel):
    id: uuid.UUID
    #: Exactly one of these is set: the document belongs to one contract, or
    #: to its whole pratica.
    contract_id: uuid.UUID | None = None
    contract_request_id: uuid.UUID | None = None
    document_type: str
    #: Uploader's label for an OTHER attachment; None for slot documents,
    #: which are named by type.
    description: str | None = None
    original_filename: str
    content_type: str
    size_bytes: int
    uploaded_by_user_id: uuid.UUID
    uploaded_by_role: str
    uploaded_by_name: str | None = None
    status: str
    reviewed_by_user_id: uuid.UUID | None = None
    reviewed_by_name: str | None = None
    reviewed_at: datetime | None = None
    review_note: str | None = None
    created_at: datetime


class DocumentUrlRead(BaseModel):
    url: str
    expires_in_seconds: int


class DocumentReviewRequest(BaseModel):
    status: str
    review_note: str | None = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        if v not in DOCUMENT_STATUSES - {"PENDING_REVIEW"}:
            raise ValueError("status must be APPROVED or REJECTED")
        return v


class RequiredDocumentStatus(BaseModel):
    """One row per document slot on a contract, with its latest upload and
    review status. `document` is None while the slot is still expected."""

    document_type: str
    #: False for an offered slot that does not block the contract (visura of a
    #: ditta individuale). Defaults to True so clients ignoring the field treat
    #: every row as required, the safe direction.
    required: bool = True
    document: DocumentRead | None = None


class ContractDocumentsRead(BaseModel):
    #: Set for a contract's documents, or contract_request_id for a pratica's.
    contract_id: uuid.UUID | None = None
    contract_request_id: uuid.UUID | None = None
    required: list[RequiredDocumentStatus]
    #: Free-form labelled attachments, oldest first. Never block the contract.
    extra: list[DocumentRead] = []


class DocumentTypeInfo(BaseModel):
    code: str
    label: str


DOCUMENT_TYPE_LABELS = {
    "IDENTITY": "Documento d'identità",
    "FISCAL_CODE": "Codice fiscale",
    "UTILITY_BILL": "Fattura luce/gas",
    "CHAMBER_OF_COMMERCE": "Visura camerale",
    "OTHER": "Documento aggiuntivo",
}

assert set(DOCUMENT_TYPE_LABELS) == DOCUMENT_TYPES
