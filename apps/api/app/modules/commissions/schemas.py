import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class CommissionMovementRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    beneficiary_kind: str = "AGENT"
    agent_id: uuid.UUID | None
    contract_id: uuid.UUID
    movement_type: str
    amount_cents: int
    currency: str
    status: str
    effective_date: date


class CommissionMovementDetailRead(BaseModel):
    """Full explanation of a movement, from frozen data, never recalculated."""

    id: uuid.UUID
    contract_id: uuid.UUID
    customer_id: uuid.UUID
    customer_name: str
    product_name: str
    value_cents: int
    beneficiary_kind: str
    agent_id: uuid.UUID | None
    agent_name: str
    agent_promoter_code: str
    agent_current_role_code: str | None
    producer_agent_id: uuid.UUID
    producer_name: str
    depth_from_producer: int | None
    movement_type: str
    beneficiary_type: str | None
    role_at_calculation: str | None
    plan_id: uuid.UUID | None
    plan_name: str | None
    plan_version: int | None
    rule_label: str | None
    calculation_type: str | None
    calculation_value: float | None
    reference_margin_cents: int | None
    fallback_applied: str | None
    amount_cents: int
    explanation: str | None
    status: str
    effective_date: date
    approved_at: datetime | None
    paid_date: date | None


class CommissionLevelTotalsRead(BaseModel):
    depth: int
    contracts: int
    value_cents: int
    commission_cents: int


class CommissionPaymentRequest(BaseModel):
    note: str | None = None


class MovementTransitionRequest(BaseModel):
    movement_ids: list[uuid.UUID] = Field(min_length=1, max_length=500)
    to_status: str
    note: str | None = None


class SellerSummaryRead(BaseModel):
    agent_name: str | None
    direct_cents: int
    indirect_cents: int
    promoter_fee_cents: int
    reversal_cents: int
    pending_cents: int
    approved_cents: int
    paid_cents: int
    personal_sales: int
    personal_sales_amount_cents: int


class RankRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str
    level: int
    personal_token_cents: int


# --- Split Plan -------------------------------------------------------------------


class SplitRuleIn(BaseModel):
    sequence: int | None = None
    label: str | None = Field(default=None, max_length=120)
    beneficiary_type: str
    network_level: int | None = Field(default=None, ge=1, le=50)
    required_role_id: uuid.UUID | None = None
    calculation_type: str
    percentage: Decimal | None = Field(default=None, ge=0, le=100, decimal_places=4)
    amount_cents: int | None = Field(default=None, ge=0)
    min_amount_cents: int | None = Field(default=None, ge=0)
    max_amount_cents: int | None = Field(default=None, ge=0)
    fallback_strategy: str | None = None


class SplitRuleRead(SplitRuleIn):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    required_role_code: str | None = None


class SplitPlanIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    product_id: uuid.UUID | None = None
    category_id: uuid.UUID | None = None
    seller_role_id: uuid.UUID
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    fallback_strategy: str = "COMPANY"
    distribution_mode: str = "FULL"
    accrual_trigger: str = "PER_INSTALMENT"
    notes: str = Field(default="", max_length=2000)
    rules: list[SplitRuleIn] = Field(default_factory=list, max_length=50)


class SplitPlanUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    product_id: uuid.UUID | None = None
    category_id: uuid.UUID | None = None
    seller_role_id: uuid.UUID | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    fallback_strategy: str | None = None
    distribution_mode: str | None = None
    accrual_trigger: str | None = None
    notes: str | None = Field(default=None, max_length=2000)
    rules: list[SplitRuleIn] | None = Field(default=None, max_length=50)


class PlanValidationRead(BaseModel):
    ok: bool
    errors: list[str]
    warnings: list[str]
    percentage_total: Decimal
    fixed_total_cents: int
    has_remainder: bool
    reference_margin_cents: int | None
    distributed_cents: int | None
    residual_cents: int | None


class SplitPlanRead(BaseModel):
    id: uuid.UUID
    plan_key: uuid.UUID | None
    name: str | None
    version: int
    status: str
    product_id: uuid.UUID | None
    product_code: str | None = None
    category_id: uuid.UUID | None
    category_name: str | None = None
    seller_role_id: uuid.UUID | None
    seller_role_code: str | None = None
    seller_role_name: str | None = None
    valid_from: datetime
    valid_to: datetime | None
    fallback_strategy: str
    distribution_mode: str
    accrual_trigger: str
    notes: str
    activated_at: datetime | None
    retired_at: datetime | None
    created_at: datetime
    rules: list[SplitRuleRead] = []
    validation: PlanValidationRead | None = None


class RetirePlanRequest(BaseModel):
    effective_at: datetime | None = None


class NewVersionRequest(BaseModel):
    valid_from: datetime | None = None


class SimulateSaleRequest(BaseModel):
    seller_agent_id: uuid.UUID
    product_id: uuid.UUID
    sold_at: datetime | None = None
    sale_amount_cents: int | None = Field(default=None, ge=0)
    promoter_agent_id: uuid.UUID | None = None
    plan_id: uuid.UUID | None = None
