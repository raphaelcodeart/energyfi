from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class PurchaseCreate(BaseModel):
    #: A plan code (DIGITAL_AMBASSADOR, LICENSE_1, SMALL, ..., ROMA_10): the
    #: price is the plan's, never the client's.
    product_code: str = Field(min_length=2, max_length=32)
    #: Paid month (YYYY-MM), subscription only.
    period: str | None = Field(default=None, max_length=7)
    payment_method: Literal["BANK_TRANSFER", "CARD", "CASH", "OTHER"] | None = None
    note: str | None = Field(default=None, max_length=1000)


class AdminPurchaseCreate(PurchaseCreate):
    agent_id: str
    #: Register and confirm in one step, when the money is already in.
    confirm_now: bool = False


class ClientCreate(BaseModel):
    company_name: str = Field(min_length=2, max_length=255)
    vat_number: str | None = Field(default=None, max_length=32)
    contact_name: str | None = Field(default=None, max_length=255)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=64)


class PackSaleCreate(BaseModel):
    client_id: str
    pack_code: str = Field(min_length=2, max_length=32)
    payment_method: Literal["BANK_TRANSFER", "CARD", "CASH", "OTHER"] | None = None
    note: str | None = Field(default=None, max_length=1000)


class TopupCreate(BaseModel):
    client_id: str
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    payment_method: Literal["BANK_TRANSFER", "CARD", "CASH", "OTHER"] | None = None
    note: str | None = Field(default=None, max_length=1000)


class ResaleCreate(BaseModel):
    license_id: str
    client_id: str
    payment_method: Literal["BANK_TRANSFER", "CARD", "CASH", "OTHER"] | None = None
    note: str | None = Field(default=None, max_length=1000)


class LicenseAssign(BaseModel):
    license_id: str
    #: An existing company of the licence owner...
    client_id: str | None = None
    #: ...or a new one, created with the assignment.
    new_client: ClientCreate | None = None
    payment_method: Literal["BANK_TRANSFER", "CARD", "CASH", "OTHER"] | None = None
    note: str | None = Field(default=None, max_length=1000)


class OperationDecision(BaseModel):
    reason: str | None = Field(default=None, max_length=500)
    payment_method: Literal["BANK_TRANSFER", "CARD", "CASH", "OTHER"] | None = None


class CommissionPayout(BaseModel):
    commission_ids: list[str] = Field(min_length=1, max_length=2000)


class SubscriptionStatusUpdate(BaseModel):
    status: Literal["ACTIVE", "SUSPENDED", "CANCELLED"]
    reason: str | None = Field(default=None, max_length=500)


class PlanVersionCreate(BaseModel):
    label: str = Field(min_length=1, max_length=64)
    valid_from: datetime
    config: dict
    notes: str | None = Field(default=None, max_length=1000)
