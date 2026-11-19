import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.foundation.storage import generate_presigned_document_url
from app.foundation.storage import upload_document as storage_upload_document
from app.modules.audit import service as audit_service
from app.modules.contracts.models import Contract, ContractRequest
from app.modules.documents.models import (
    DOCUMENT_TYPE_OTHER,
    DOCUMENT_TYPES,
    MAX_DOCUMENT_DESCRIPTION_LENGTH,
    MIN_DOCUMENT_DESCRIPTION_LENGTH,
    Document,
)

# Required for every contract; companies also need the chamber-of-commerce
# registration. A constant rather than ProductVersion.required_documents,
# which is not populated.
BASE_REQUIRED_DOCUMENT_TYPES = ["IDENTITY", "FISCAL_CODE", "UTILITY_BILL"]
COMPANY_LIKE_KINDS = {"COMPANY", "CONDOMINIUM"}
# A ditta individuale / libero professionista is a business for VAT
# (catalog/pricing.py) but may not be in the Registro Imprese, so the visura
# slot is offered as optional and never blocks the contract.
CHAMBER_OF_COMMERCE_OPTIONAL_KINDS = {"SOLE_PROPRIETOR"}


class DocumentValidationError(Exception):
    pass


@dataclass(frozen=True)
class DocumentSlot:
    """One named place to upload, on this contract, for this customer kind."""

    document_type: str
    #: False for a slot that is accepted but does not block the contract
    #: (see CHAMBER_OF_COMMERCE_OPTIONAL_KINDS).
    required: bool


def document_slots_for(customer_kind: str) -> list[DocumentSlot]:
    slots = [DocumentSlot(document_type=t, required=True) for t in BASE_REQUIRED_DOCUMENT_TYPES]
    if customer_kind in COMPANY_LIKE_KINDS:
        slots.append(DocumentSlot(document_type="CHAMBER_OF_COMMERCE", required=True))
    elif customer_kind in CHAMBER_OF_COMMERCE_OPTIONAL_KINDS:
        slots.append(DocumentSlot(document_type="CHAMBER_OF_COMMERCE", required=False))
    return slots


#: Slots describing the holder, not the supply point: collected once per
#: pratica.
REQUEST_LEVEL_DOCUMENT_TYPES = frozenset({"IDENTITY", "FISCAL_CODE", "CHAMBER_OF_COMMERCE"})


def request_document_slots_for(customer_kind: str) -> list[DocumentSlot]:
    """Slots a pratica collects once for all its points: the holder's slots
    plus an optional shared bill. A pratica bill fills the bill slot of every
    contract that has none of its own."""
    slots = [slot for slot in document_slots_for(customer_kind) if slot.document_type in REQUEST_LEVEL_DOCUMENT_TYPES]
    slots.append(DocumentSlot(document_type="UTILITY_BILL", required=False))
    return slots


def required_document_types_for(customer_kind: str) -> list[str]:
    """Only the types that block the contract; `maybe_advance_to_under_review`
    gates on this list. Optional slots and extra attachments are excluded."""
    return [slot.document_type for slot in document_slots_for(customer_kind) if slot.required]


def normalize_document_description(description: str | None) -> str:
    """Normalize an extra attachment's label: collapse whitespace so equal
    labels compare equal, and bound the length on input."""
    cleaned = " ".join((description or "").split())
    if len(cleaned) < MIN_DOCUMENT_DESCRIPTION_LENGTH:
        raise DocumentValidationError(
            "Indica di che documento si tratta (almeno "
            f"{MIN_DOCUMENT_DESCRIPTION_LENGTH} caratteri)."
        )
    if len(cleaned) > MAX_DOCUMENT_DESCRIPTION_LENGTH:
        raise DocumentValidationError(
            f"La descrizione del documento non può superare i {MAX_DOCUMENT_DESCRIPTION_LENGTH} caratteri."
        )
    return cleaned


async def upload_document(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    contract_id: uuid.UUID | None = None,
    contract_request_id: uuid.UUID | None = None,
    document_type: str,
    file_bytes: bytes,
    content_type: str,
    original_filename: str,
    actor_user_id: uuid.UUID,
    actor_role: str,
    description: str | None = None,
) -> Document:
    """Attach a document to one contract or, with `contract_request_id`, to a
    whole pratica, where it counts for every contract in it."""
    if (contract_id is None) == (contract_request_id is None):
        raise DocumentValidationError("Un documento appartiene a un contratto oppure a una pratica.")
    if document_type not in DOCUMENT_TYPES:
        raise DocumentValidationError(f"document_type must be one of {sorted(DOCUMENT_TYPES)}")

    # Only extra attachments carry a label, and they must: slot documents are
    # named by type and must not be relabelled.
    description = normalize_document_description(description) if document_type == DOCUMENT_TYPE_OTHER else None

    storage_key = storage_upload_document(
        file_bytes=file_bytes, content_type=content_type,
        key_prefix=f"documents/{contract_id}" if contract_id else f"documents/requests/{contract_request_id}",
    )

    document = Document(
        organization_id=organization_id,
        contract_id=contract_id,
        contract_request_id=contract_request_id,
        document_type=document_type,
        description=description,
        original_filename=original_filename,
        storage_key=storage_key,
        content_type=content_type,
        size_bytes=len(file_bytes),
        uploaded_by_user_id=actor_user_id,
        uploaded_by_role=actor_role,
        status="PENDING_REVIEW",
    )
    db.add(document)
    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="document.uploaded", entity_type="document", entity_id=str(contract_id or contract_request_id),
        new_value={
            "document_type": document_type,
            "uploaded_by_role": actor_role,
            **({"description": description} if description else {}),
        },
    )
    await db.commit()
    await db.refresh(document)

    if contract_id is not None:
        contract_ids = [contract_id]
    else:
        contract_ids = list(
            (await db.execute(select(Contract.id).where(Contract.contract_request_id == contract_request_id))).scalars()
        )
    for target_id in contract_ids:
        await maybe_advance_to_under_review(
            db, organization_id=organization_id, contract_id=target_id, actor_user_id=actor_user_id
        )
    return document


async def maybe_advance_to_under_review(
    db: AsyncSession, *, organization_id: uuid.UUID, contract_id: uuid.UUID, actor_user_id: uuid.UUID
) -> None:
    """Move the contract from SUBMITTED/DOCUMENTS_PENDING to UNDER_REVIEW once
    every required type has at least one upload, in any status: staff still
    reviews each document, this only signals the customer is done (see
    business-rules.md#contract-self-service). Applies equally to
    staff-created contracts."""
    from app.modules.contracts import service as contracts_service
    from app.modules.customers.models import Customer

    contract = await db.get(Contract, contract_id)
    if contract is None or contract.status not in ("SUBMITTED", "DOCUMENTS_PENDING"):
        return

    customer = await db.get(Customer, contract.customer_id)
    customer_kind = customer.kind if customer else "PRIVATE"
    rows = await get_contract_documents_status(
        db, organization_id=organization_id, contract=contract, customer_kind=customer_kind
    )
    # Only required slots gate the advance, never optional slots or extra
    # attachments.
    if not all(row["document"] is not None for row in rows if row["required"]):
        return

    if contract.status == "SUBMITTED":
        contract = await contracts_service.transition_contract(
            db, organization_id=organization_id, contract=contract, to_status="DOCUMENTS_PENDING",
            actor_user_id=actor_user_id, reason=None, notes=None, correlation_id=str(uuid.uuid4()),
        )
    await contracts_service.transition_contract(
        db, organization_id=organization_id, contract=contract, to_status="UNDER_REVIEW",
        actor_user_id=actor_user_id, reason="Tutti i documenti richiesti sono stati caricati", notes=None,
        correlation_id=str(uuid.uuid4()),
    )


async def list_documents_for_contract(
    db: AsyncSession, *, organization_id: uuid.UUID, contract_id: uuid.UUID
) -> list[Document]:
    """The contract's own documents only, newest first -- not its pratica's."""
    stmt = (
        select(Document)
        .where(Document.organization_id == organization_id, Document.contract_id == contract_id)
        .order_by(Document.created_at.desc())
    )
    return list((await db.execute(stmt)).scalars().all())


async def list_documents_for_request(
    db: AsyncSession, *, organization_id: uuid.UUID, contract_request_id: uuid.UUID
) -> list[Document]:
    """The documents uploaded once for a whole pratica, newest first."""
    stmt = (
        select(Document)
        .where(Document.organization_id == organization_id, Document.contract_request_id == contract_request_id)
        .order_by(Document.created_at.desc())
    )
    return list((await db.execute(stmt)).scalars().all())


def _latest_by_type(docs: list[Document]) -> dict[str, Document]:
    latest: dict[str, Document] = {}
    for doc in sorted(docs, key=lambda d: d.created_at, reverse=True):
        latest.setdefault(doc.document_type, doc)
    return latest


async def get_contract_documents_status(
    db: AsyncSession, *, organization_id: uuid.UUID, contract: Contract, customer_kind: str
) -> list[dict]:
    """One row per document slot: the latest document of that type (or None)
    and whether the slot is required or offered. Rejected documents are
    superseded by newer uploads here and remain in list_documents_for_contract
    as history.

    Pratica documents fill the same slots, so identity uploaded once serves
    every contract of the pratica. When both exist the contract's own document
    wins as the more specific one."""
    own = _latest_by_type(
        await list_documents_for_contract(db, organization_id=organization_id, contract_id=contract.id)
    )
    shared = _latest_by_type(
        await list_documents_for_request(
            db, organization_id=organization_id, contract_request_id=contract.contract_request_id
        )
    )

    return [
        {
            "document_type": slot.document_type,
            "required": slot.required,
            "document": own.get(slot.document_type) or shared.get(slot.document_type),
        }
        for slot in document_slots_for(customer_kind)
    ]


async def get_request_documents_status(
    db: AsyncSession, *, organization_id: uuid.UUID, request: ContractRequest, customer_kind: str
) -> list[dict]:
    """Same shape as get_contract_documents_status, for the slots a pratica
    collects once (request_document_slots_for)."""
    shared = _latest_by_type(
        await list_documents_for_request(db, organization_id=organization_id, contract_request_id=request.id)
    )
    return [
        {"document_type": slot.document_type, "required": slot.required, "document": shared.get(slot.document_type)}
        for slot in request_document_slots_for(customer_kind)
    ]


async def get_extra_documents_for_request(
    db: AsyncSession, *, organization_id: uuid.UUID, request: ContractRequest, customer_kind: str
) -> list[Document]:
    slot_types = {slot.document_type for slot in request_document_slots_for(customer_kind)}
    docs = await list_documents_for_request(db, organization_id=organization_id, contract_request_id=request.id)
    return [doc for doc in reversed(docs) if doc.document_type not in slot_types]


async def get_extra_documents_for_contract(
    db: AsyncSession, *, organization_id: uuid.UUID, contract: Contract, customer_kind: str
) -> list[Document]:
    """Everything attached to the contract that no slot accounts for.

    All OTHER attachments (oldest first; extra documents never supersede each
    other) plus any document whose type has no slot for the current customer
    kind, e.g. a visura from when the customer was a company. A documents list
    must never hide something still stored in the bucket."""
    slot_types = {slot.document_type for slot in document_slots_for(customer_kind)}
    docs = await list_documents_for_contract(db, organization_id=organization_id, contract_id=contract.id)
    return [doc for doc in reversed(docs) if doc.document_type not in slot_types]


async def get_document(db: AsyncSession, *, organization_id: uuid.UUID, document_id: uuid.UUID) -> Document | None:
    document = await db.get(Document, document_id)
    if document is None or document.organization_id != organization_id:
        return None
    return document


async def get_presigned_url_for_document(document: Document) -> str:
    return generate_presigned_document_url(storage_key=document.storage_key)


async def review_document(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    document_id: uuid.UUID,
    new_status: str,
    review_note: str | None,
    actor_user_id: uuid.UUID,
) -> Document | None:
    document = await get_document(db, organization_id=organization_id, document_id=document_id)
    if document is None:
        return None

    previous_status = document.status
    document.status = new_status
    document.review_note = review_note
    document.reviewed_by_user_id = actor_user_id
    document.reviewed_at = datetime.now(UTC)

    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="document.reviewed", entity_type="document", entity_id=str(document_id),
        previous_value={"status": previous_status}, new_value={"status": new_status},
        reason=review_note,
    )
    await db.commit()
    await db.refresh(document)
    return document
