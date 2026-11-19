import uuid
from datetime import datetime

from pydantic import BaseModel


class FinancialMovementRead(BaseModel):
    """One row of the accounting view: SosnetCash wallet transactions merged
    with real-money payments (orders, invoice redemptions, contract
    instalments). Computed on read, not stored; each source table remains
    the source of truth."""

    id: str
    kind: str  # "WALLET" | "ORDER_PAYMENT" | "REDEMPTION_PAYMENT" | "CONTRACT_PAYMENT"
    # Raw wallet type/source codes (null on real-money rows); the frontend
    # maps them to labels.
    type: str | None = None
    source: str | None = None
    # Null on WALLET rows.
    payment_method: str | None = None
    # Signed on WALLET rows (negative = outgoing); always positive on payments.
    amount_cents: int
    currency: str  # "SOSNETCASH" | "EUR"
    # Product name for order/contract rows, partner name for redemption rows.
    product_name: str | None = None
    # Id from whichever order table backs the order; the frontend treats all
    # order tables uniformly.
    order_id: uuid.UUID | None = None
    invoice_redemption_id: uuid.UUID | None = None
    #: A contract instalment paid (CONTRACT_PAYMENT) or the
    #: SosnetCash cashback a contract earned (WALLET).
    contract_id: uuid.UUID | None = None
    contract_request_id: uuid.UUID | None = None
    note: str | None = None
    # Lets the admin view filter and total by customer without extra lookups.
    customer_user_id: uuid.UUID | None = None
    customer_display_name: str | None = None
    created_at: datetime


class AccountingSummaryRead(BaseModel):
    """Accounting totals, computed server-side from the same movements as
    the list so the two always agree."""

    #: Real money paid, card + bank transfer, and its split.
    spent_total_cents: int = 0
    spent_card_cents: int = 0
    spent_bank_transfer_cents: int = 0
    spent_this_month_cents: int = 0
    spent_orders_cents: int = 0
    spent_redemptions_cents: int = 0
    spent_contracts_cents: int = 0
    payments_count: int = 0
    #: SosnetCash.
    sosnetcash_balance_cents: int = 0
    sosnetcash_received_cents: int = 0
    sosnetcash_spent_cents: int = 0
    cashback_received_cents: int = 0
    #: Contracts.
    contracts_active: int = 0
    instalments_paid: int = 0
    next_instalment_due_date: str | None = None
    next_instalment_cents: int | None = None
    #: Commissions, only for someone who is also a promoter (null otherwise).
    commissions_total_cents: int | None = None
    commissions_to_collect_cents: int | None = None
    commissions_paid_cents: int | None = None
    commissions_count: int | None = None


class DetailFact(BaseModel):
    label: str
    value: str
    mono: bool = False


class DetailEvent(BaseModel):
    label: str
    at: datetime | None = None
    by: str | None = None
    #: done / pending / warning -- how the step is drawn on the timeline.
    tone: str = "done"


class DetailInstalment(BaseModel):
    number: int
    instalments_total: int
    due_date: str
    amount_cents: int
    status: str
    paid_at: datetime | None = None
    source: str | None = None
    confirmed_by: str | None = None


class AccountingDetailRead(BaseModel):
    """Uniform detail for a movement, order, redemption or contract: facts,
    a timeline of who did what and when, and instalments for contracts."""

    ref: str
    kind: str  # WALLET / ORDER / REDEMPTION / CONTRACT
    title: str
    subtitle: str | None = None
    status: str | None = None
    #: success / warning / danger / neutral
    status_tone: str = "neutral"
    amount_cents: int | None = None
    currency: str = "EUR"
    direction: str | None = None  # in / out
    facts: list[DetailFact] = []
    timeline: list[DetailEvent] = []
    instalments: list[DetailInstalment] = []
    #: Refs of the things this one is tied to ("order:<id>", "contract:<id>").
    related_refs: list[str] = []
    #: Which dashboard tab manages it: orders / cashback / contracts / wallet.
    tab: str | None = None
    #: Order id / redemption id / contract id this detail is about, so the
    #: popup can list every movement of the same thing.
    order_id: uuid.UUID | None = None
    invoice_redemption_id: uuid.UUID | None = None
    contract_id: uuid.UUID | None = None
