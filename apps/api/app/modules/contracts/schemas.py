import re
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from app.modules.customers.schemas import SupplyPointCreate

IBAN_PATTERN = re.compile(r"^[A-Z]{2}[0-9A-Z]{13,32}$")
# Intentionally loose (not RFC 5322): catches form typos without an extra
# dependency.
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _validate_iban(v: str | None) -> str | None:
    if v is None:
        return v
    cleaned = v.replace(" ", "").upper()
    if not IBAN_PATTERN.match(cleaned):
        raise ValueError("IBAN non valido")
    return cleaned


def _validate_email(v: str | None) -> str | None:
    if v is None:
        return v
    cleaned = v.strip()
    if not EMAIL_PATTERN.match(cleaned):
        raise ValueError("Email non valida")
    return cleaned


class ContractRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    customer_id: uuid.UUID
    supply_point_id: uuid.UUID | None = None
    #: None only while a draft point has no package chosen yet.
    product_version_id: uuid.UUID | None = None
    contract_request_id: uuid.UUID | None = None
    status: str
    notes: str | None = None
    iban: str | None = None
    email: str | None = None
    holder_first_name: str | None = None
    holder_last_name: str | None = None
    pec: str | None = None
    created_at: datetime
    activated_at: datetime | None = None
    expires_at: datetime | None = None
    # Denormalized display names filled by the service to avoid N+1 lookups;
    # the FKs above remain authoritative.
    product_name: str | None = None
    supply_point_label: str | None = None
    pod_code: str | None = None
    pdr_code: str | None = None
    energy_type: str | None = None

    # --- Who created it -----------------------------------------------------
    #: CUSTOMER / PROMOTER / ADMIN; may be None (see the status history).
    created_by_role: str | None = None
    #: Set only when a promoter completed the contract for the customer.
    activated_by_promoter_id: uuid.UUID | None = None
    activated_by_promoter_name: str | None = None
    #: Promoter who originally referred the customer (legacy first-referrer).
    first_referrer_agent_id: uuid.UUID | None = None
    first_referrer_name: str | None = None

    # --- Frozen economics --------------------------------------------------
    customer_kind: str | None = None
    net_amount_cents: int | None = None
    #: Percentage points (22.0); 0.0 for private customers.
    vat_rate: float | None = None
    vat_amount_cents: int | None = None
    gross_amount_cents: int | None = None

    # --- Payment -----------------------------------------------------------
    payment_plan: str | None = None
    #: Single-payment discount (0 otherwise).
    payment_discount_cents: int = 0
    payment_method: str | None = None
    paid_at: datetime | None = None
    billing_stopped_at: datetime | None = None
    terms_accepted_at: datetime | None = None
    terms_version: str | None = None


class ContractCreate(BaseModel):
    customer_id: uuid.UUID
    #: Required only for categories with a supply point (electricity, gas).
    supply_point_id: uuid.UUID | None = None
    product_version_id: uuid.UUID
    producer_agent_id: uuid.UUID
    lead_id: uuid.UUID | None = None
    notes: str | None = None
    iban: str | None = None
    email: str | None = None

    @field_validator("iban")
    @classmethod
    def validate_iban(cls, v: str | None) -> str | None:
        return _validate_iban(v)

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str | None) -> str | None:
        return _validate_email(v)


class ContractSelfServiceCreate(BaseModel):
    """POST /contracts/mine (customer self-service). No producer_agent_id: the
    referring promoter is resolved server-side
    (service.py::create_contract_self_service). The contact email is required
    and may differ from the login email."""

    product_version_id: uuid.UUID
    supply_point: SupplyPointCreate
    email: str

    # Holder: name required; PEC and IBAN optional (the IBAN can be added
    # later, so a missing one never blocks a contract).
    holder_first_name: str
    holder_last_name: str
    pec: str | None = None
    iban: str | None = None

    @field_validator("holder_first_name", "holder_last_name", mode="before")
    @classmethod
    def validate_name(cls, v: str | None) -> str:
        cleaned = (v or "").strip()
        if not cleaned:
            raise ValueError("campo obbligatorio")
        return cleaned

    @field_validator("pec", "iban", mode="before")
    @classmethod
    def blank_to_none(cls, v: str | None) -> str | None:
        return (v or "").strip() or None

    @field_validator("pec")
    @classmethod
    def validate_pec(cls, v: str | None) -> str | None:
        return _validate_email(v)

    @field_validator("iban")
    @classmethod
    def validate_iban(cls, v: str | None) -> str | None:
        return _validate_iban(v)

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        validated = _validate_email(v)
        if validated is None:
            raise ValueError("email is required")
        return validated


class ContractForCustomerCreate(BaseModel):
    """POST /contracts/for-customer: a promoter activates a contract for one
    of their own customers (service.py::create_contract_for_recruited_customer).
    The producer is the calling promoter, resolved server-side."""

    customer_id: uuid.UUID
    product_version_id: uuid.UUID
    supply_point: SupplyPointCreate
    email: str

    # Holder: name required; PEC and IBAN optional (the IBAN can be added
    # later, so a missing one never blocks a contract).
    holder_first_name: str
    holder_last_name: str
    pec: str | None = None
    iban: str | None = None

    @field_validator("holder_first_name", "holder_last_name", mode="before")
    @classmethod
    def validate_name(cls, v: str | None) -> str:
        cleaned = (v or "").strip()
        if not cleaned:
            raise ValueError("campo obbligatorio")
        return cleaned

    @field_validator("pec", "iban", mode="before")
    @classmethod
    def blank_to_none(cls, v: str | None) -> str | None:
        return (v or "").strip() or None

    @field_validator("pec")
    @classmethod
    def validate_pec(cls, v: str | None) -> str | None:
        return _validate_email(v)

    @field_validator("iban")
    @classmethod
    def validate_iban(cls, v: str | None) -> str | None:
        return _validate_iban(v)

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        validated = _validate_email(v)
        if validated is None:
            raise ValueError("email is required")
        return validated


class ContractIbanUpdate(BaseModel):
    iban: str

    @field_validator("iban")
    @classmethod
    def validate_iban(cls, v: str | None) -> str | None:
        result = _validate_iban(v)
        if result is None:
            raise ValueError("iban is required")
        return result


class ContractTransitionRequest(BaseModel):
    to_status: str
    reason: str | None = None
    notes: str | None = None
    #: Checksum of the commission preview being accepted (GET
    #: /contracts/{id}/commission-preview). Required towards activation if none
    #: was accepted yet; see router.py::transition_contract.
    accept_commission_preview_checksum: str | None = None


class ContractStatusHistoryRead(BaseModel):
    id: uuid.UUID
    from_status: str | None
    to_status: str
    actor_user_id: uuid.UUID
    actor_name: str
    reason: str | None
    notes: str | None
    created_at: datetime


class ContractPaymentOptionRead(BaseModel):
    """One priced way to pay this contract, computed server-side from the
    frozen amount; the client only picks a key."""

    key: str
    label: str
    description: str
    instalments: int
    instalment_cents: int
    total_cents: int
    #: Plan total minus contract amount, from rounding instalments to the
    #: cent; shown to the customer.
    rounding_difference_cents: int
    #: Taken off a single payment only.
    discount_percentage: int = 0
    discount_cents: int = 0


class ContractPaymentOptionsRead(BaseModel):
    contract_id: uuid.UUID
    #: False when not at the payment step or already paid.
    payable: bool
    status: str
    #: At the payment step but without a frozen amount. Kept separate from
    #: `payable` so the UI can report it as a platform-side problem.
    missing_amount: bool = False
    gross_amount_cents: int | None = None
    card_available: bool = False
    options: list[ContractPaymentOptionRead] = []
    #: Set when Stripe confirms the first payment, possibly before approval.
    paid_at: datetime | None = None
    payment_plan: str | None = None
    #: Product SosnetCash percentage and its total for the contract; on
    #: instalment plans it is credited per instalment.
    cashback_percentage: int = 0
    cashback_total_cents: int = 0


class ContractCheckoutRequest(BaseModel):
    #: FULL / INSTALMENTS_3 / MONTHLY_12 (see payment_plans.py).
    payment_plan: str
