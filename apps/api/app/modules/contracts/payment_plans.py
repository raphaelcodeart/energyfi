"""Contract payment plans: single payment, 3 or 12 monthly instalments.

Applies to contracts only; Shop orders have their own checkout.

Stripe objects are created per contract through the API, never as
pre-made Products/Prices: the amount comes from the breakdown frozen on the
contract (`catalog/pricing.py`), which already reflects the customer's VAT.

The 3- and 12-instalment plans are the same mechanism, a Stripe
subscription that stops after N invoices. No financing provider is
involved; SOSNET simply splits its own invoice.
"""

from dataclasses import dataclass

PLAN_FULL = "FULL"
PLAN_INSTALMENTS_3 = "INSTALMENTS_3"
PLAN_MONTHLY_12 = "MONTHLY_12"


@dataclass(frozen=True)
class PaymentPlan:
    key: str
    #: 1 = single charge; >1 = subscription ending after this many invoices.
    instalments: int
    label: str
    description: str


PAYMENT_PLANS: tuple[PaymentPlan, ...] = (
    PaymentPlan(
        key=PLAN_FULL,
        instalments=1,
        label="Soluzione unica",
        description="Un solo pagamento con carta, subito.",
    ),
    PaymentPlan(
        key=PLAN_INSTALMENTS_3,
        instalments=3,
        label="3 rate mensili",
        description="La prima rata oggi, le altre due addebitate automaticamente ogni mese.",
    ),
    PaymentPlan(
        key=PLAN_MONTHLY_12,
        instalments=12,
        label="12 rate mensili",
        description="La prima rata oggi, le altre undici addebitate automaticamente ogni mese.",
    ),
)


def plan_by_key(key: str | None) -> PaymentPlan | None:
    return next((p for p in PAYMENT_PLANS if p.key == key), None)


@dataclass(frozen=True)
class PlanBreakdown:
    """What the customer will be charged, and when.

    A Stripe subscription bills the same amount each period, so the
    instalment is rounded to the cent and `total_cents` may differ from the
    contract by a few cents (`rounding_difference_cents`, at most 6 for 12
    instalments). The difference is shown to the customer beside each
    option; putting the remainder on the first invoice would need a Stripe
    Product per contract, and rounding up silently would overcharge.
    """

    plan: PaymentPlan
    #: What the contract itself says is owed.
    contract_total_cents: int
    #: What this plan will actually collect: instalment x instalments.
    total_cents: int
    instalment_cents: int
    #: total_cents - (contract_total_cents - discount_cents); zero when the
    #: amount divides evenly.
    rounding_difference_cents: int
    #: Taken off a single payment only (never off instalments).
    discount_percentage: int = 0
    discount_cents: int = 0

    @property
    def is_subscription(self) -> bool:
        return self.plan.instalments > 1


def discount_cents_for(total_cents: int, percentage: int) -> int:
    """Single-payment discount, half-up to the cent. Applied to the
    VAT-inclusive price, equivalent to discounting net since VAT is
    proportional."""
    if percentage <= 0 or total_cents <= 0:
        return 0
    return min(total_cents, (total_cents * percentage * 2 + 100) // 200)


def breakdown_for(
    plan: PaymentPlan, total_cents: int, *, discount_percentage: int = 0, discount_cents: int | None = None
) -> PlanBreakdown:
    """`discount_percentage` prices an offered plan; `discount_cents` re-reads
    the discount frozen on the contract, so later setting changes never
    restate what a customer paid. Both apply to single payments only."""
    if plan.instalments <= 1:
        discount = discount_cents if discount_cents is not None else discount_cents_for(total_cents, discount_percentage)
        percentage = discount_percentage if discount_cents is None else (
            round(discount * 100 / total_cents) if total_cents else 0
        )
        return PlanBreakdown(
            plan=plan,
            contract_total_cents=total_cents,
            total_cents=total_cents - discount,
            instalment_cents=total_cents - discount,
            rounding_difference_cents=0,
            discount_percentage=percentage if discount else 0,
            discount_cents=discount,
        )
    # Half-up on the cent, the same rounding the VAT calculation uses.
    instalment = (total_cents * 2 + plan.instalments) // (plan.instalments * 2)
    plan_total = instalment * plan.instalments
    return PlanBreakdown(
        plan=plan,
        contract_total_cents=total_cents,
        total_cents=plan_total,
        instalment_cents=instalment,
        rounding_difference_cents=plan_total - total_cents,
    )


def contract_breakdown(plan: PaymentPlan, contract) -> PlanBreakdown:
    """What a contract that already chose `plan` is charged."""
    return breakdown_for(
        plan, int(contract.gross_amount_cents or 0),
        discount_cents=int(getattr(contract, "payment_discount_cents", 0) or 0) if plan.instalments <= 1 else 0,
    )


def available_breakdowns(total_cents: int, *, full_payment_discount_percentage: int = 0) -> list[PlanBreakdown]:
    """Every plan priced for this contract. Plans whose instalment rounds to
    zero are dropped: Stripe rejects zero-amount recurring prices."""
    out = []
    for plan in PAYMENT_PLANS:
        breakdown = breakdown_for(plan, total_cents, discount_percentage=full_payment_discount_percentage)
        if breakdown.instalment_cents <= 0:
            continue
        out.append(breakdown)
    return out
