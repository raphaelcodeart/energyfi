import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

# Upper bound against typos and overflow: 10,000,000.00 EUR.
MAX_AMOUNT_CENTS = 10_000_000_00


class WalletRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    address: str
    balance_cents: int
    currency: str
    can_transfer: bool
    created_at: datetime


class WalletAdminListItemRead(WalletRead):
    """Admin list row, including owner info to avoid per-row lookups."""

    owner_display_name: str
    owner_email: str
    owner_roles: list[str]


class WalletTransactionRead(BaseModel):
    """Transaction with resolved counterparty details; built from the dict
    produced by service._to_transaction_dict, not from the ORM object."""

    id: uuid.UUID
    from_wallet_id: uuid.UUID | None
    from_address: str | None
    from_display_name: str | None
    # NULL when money leaves the wallet system (purchase debit, reversed credit).
    to_wallet_id: uuid.UUID | None
    to_address: str | None
    to_display_name: str | None
    amount_cents: int
    currency: str
    type: str
    source: str | None
    reference_contract_id: uuid.UUID | None
    reference_invoice_redemption_id: uuid.UUID | None
    reference_order_id: uuid.UUID | None
    reference_imported_order_id: uuid.UUID | None
    reference_cj_order_id: uuid.UUID | None = None
    reference_shopify_order_id: uuid.UUID | None = None
    reference_aliexpress_order_id: uuid.UUID | None = None
    reverses_transaction_id: uuid.UUID | None
    note: str | None
    actor_user_id: uuid.UUID | None
    created_at: datetime


class WelcomeBonusStatusRead(BaseModel):
    """Drives the welcome-bonus card on the dashboard home; the card is shown
    only while `available` is true."""

    available: bool
    amount_cents: int


class WalletTopUpRequest(BaseModel):
    """Admin credit (top-up or cashback). Targets a user_id rather than an
    address because the wallet may not exist yet; it is created on demand."""

    user_id: uuid.UUID
    amount_cents: int = Field(gt=0, le=MAX_AMOUNT_CENTS)
    reference_contract_id: uuid.UUID | None = None
    note: str | None = Field(default=None, max_length=500)
    idempotency_key: str = Field(min_length=1, max_length=128)


class WalletTransferRequest(BaseModel):
    to_address: str = Field(min_length=1, max_length=42)
    amount_cents: int = Field(gt=0, le=MAX_AMOUNT_CENTS)
    note: str | None = Field(default=None, max_length=500)
    idempotency_key: str = Field(min_length=1, max_length=128)


class WalletTransferPermissionUpdate(BaseModel):
    can_transfer: bool


class WalletTransactionReverseRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)
    idempotency_key: str = Field(min_length=1, max_length=128)
