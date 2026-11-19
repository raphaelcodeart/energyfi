"""Plain data types for the margin-split engine.

No sessions or ORM models: the engine receives everything pre-resolved (chain
at the sale date, plan, margin) and returns money lines, so real calculation,
contract preview and simulator all run the same code.
"""

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass(frozen=True)
class ChainNode:
    """A member of the seller's sponsorship chain as of the sale date
    (depth 0 = seller, 1 = direct sponsor)."""

    agent_id: str
    name: str
    depth: int
    role_id: str | None
    role_code: str | None
    #: Inactive members keep their position in the chain but receive nothing.
    eligible: bool = True
    allows_delegation: bool = False


@dataclass(frozen=True)
class RuleSpec:
    id: str
    sequence: int
    beneficiary_type: str
    calculation_type: str
    label: str | None = None
    network_level: int | None = None
    required_role_id: str | None = None
    required_role_code: str | None = None
    percentage: Decimal | None = None
    amount_cents: int | None = None
    min_amount_cents: int | None = None
    max_amount_cents: int | None = None
    fallback_strategy: str | None = None


@dataclass(frozen=True)
class PlanSpec:
    id: str
    version: int
    name: str
    fallback_strategy: str
    distribution_mode: str
    rules: tuple[RuleSpec, ...]


@dataclass(frozen=True)
class SaleContext:
    margin_cents: int
    #: Sorted by depth; chain[0] is the seller.
    chain: tuple[ChainNode, ...]
    #: Depth limit from the seller's role (None = only the plan's limits).
    max_depth: int | None = None
    #: Explicitly delegated influencer; takes precedence over chain search.
    delegation_influencer: ChainNode | None = None
    #: Promoter of the referral the sale originates from, if any.
    promoter: ChainNode | None = None


COMPANY = "COMPANY"
AGENT = "AGENT"


@dataclass(frozen=True)
class Allocation:
    rule_id: str | None
    sequence: int
    label: str
    beneficiary_type: str
    beneficiary_kind: str  # AGENT | COMPANY
    agent_id: str | None
    agent_name: str
    network_level: int | None
    role_code: str | None
    calculation_type: str
    calculation_value: Decimal | None
    amount_cents: int
    explanation: str
    fallback_applied: str | None = None


@dataclass(frozen=True)
class EngineResult:
    margin_cents: int
    allocations: tuple[Allocation, ...]
    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def agents_cents(self) -> int:
        return sum(a.amount_cents for a in self.allocations if a.beneficiary_kind == AGENT)

    @property
    def company_cents(self) -> int:
        return sum(a.amount_cents for a in self.allocations if a.beneficiary_kind == COMPANY)

    @property
    def distributed_cents(self) -> int:
        return sum(a.amount_cents for a in self.allocations)


class EngineError(Exception):
    """The plan cannot be applied to this sale. Nothing is written, so a sale
    is never partially paid; it stays pending review."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message
