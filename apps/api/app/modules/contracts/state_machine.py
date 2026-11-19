"""Contract state machine. Any status write must first pass
`assert_transition_allowed`; see docs/business-rules.md#contract-state-machine."""

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    # DRAFT -> CANCELLED: a supply point withdrawn from a request before
    # submission; nothing was reviewed, so it is not a rejection.
    "DRAFT": {"SUBMITTED", "REJECTED", "CANCELLED"},
    "SUBMITTED": {"DOCUMENTS_PENDING", "UNDER_REVIEW", "REJECTED"},
    "DOCUMENTS_PENDING": {"UNDER_REVIEW", "REJECTED"},
    "UNDER_REVIEW": {"APPROVED", "REJECTED", "DOCUMENTS_PENDING"},
    "APPROVED": {"PAYMENT_PENDING", "REJECTED"},
    "PAYMENT_PENDING": {"PAID", "REJECTED"},
    "PAID": {"ACTIVATION_PENDING"},
    "ACTIVATION_PENDING": {"ACTIVE"},
    "ACTIVE": {"SUSPENDED", "CANCELLED", "EXPIRED", "RENEWED"},
    "SUSPENDED": {"ACTIVE", "CANCELLED"},
    "REJECTED": set(),
    "CANCELLED": set(),
    "EXPIRED": {"RENEWED", "CANCELLED"},
    # A renewed contract is still in force and may renew again each term,
    # so it has the same onward transitions as ACTIVE.
    "RENEWED": {"SUSPENDED", "CANCELLED", "EXPIRED", "RENEWED"},
}

EVENT_FOR_TRANSITION: dict[tuple[str, str], str] = {
    ("DRAFT", "SUBMITTED"): "ContractSubmitted",
    ("UNDER_REVIEW", "APPROVED"): "ContractApproved",
    ("PAYMENT_PENDING", "PAID"): "PaymentConfirmed",
    ("ACTIVATION_PENDING", "ACTIVE"): "ContractActivated",
    ("ACTIVE", "CANCELLED"): "ContractCancelled",
    # Cancelling from any in-force status: the dispatcher voids unpaid
    # commissions and reverses paid ones; nothing is deleted.
    ("SUSPENDED", "CANCELLED"): "ContractCancelled",
    ("EXPIRED", "CANCELLED"): "ContractCancelled",
    ("RENEWED", "CANCELLED"): "ContractCancelled",
    ("ACTIVE", "RENEWED"): "ContractRenewed",
    # Later renewals and revived expired contracts reuse the same event so
    # the dispatcher recalculates exactly as for a first renewal.
    ("RENEWED", "RENEWED"): "ContractRenewed",
    ("EXPIRED", "RENEWED"): "ContractRenewed",
}


class InvalidTransitionError(Exception):
    pass


def assert_transition_allowed(from_status: str, to_status: str) -> None:
    allowed = ALLOWED_TRANSITIONS.get(from_status, set())
    if to_status not in allowed:
        raise InvalidTransitionError(f"Cannot transition contract from {from_status} to {to_status}")


def event_name_for(from_status: str, to_status: str) -> str | None:
    return EVENT_FOR_TRANSITION.get((from_status, to_status))
