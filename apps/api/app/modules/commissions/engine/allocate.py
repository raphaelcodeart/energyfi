"""Divides a sale's margin according to a Split Plan.

Pure and deterministic, so preview, simulation and real calculation agree and
a calculation can be reproduced later from frozen data alone. Two independent
steps:

1. How much: each rule is valued on the margin (fixed amounts, percentages
   rounded half-up to the cent, minimums and caps, then the remainder). A
   share's value never depends on whether its beneficiary exists.
2. To whom: each rule resolves its beneficiary in the chain; if missing, the
   rule's (or plan's) fallback strategy applies.

Invariant: all lines, company included, sum to exactly the margin.
"""

from decimal import ROUND_HALF_UP, Decimal

from app.modules.commissions.engine.types import (
    AGENT,
    COMPANY,
    Allocation,
    ChainNode,
    EngineError,
    EngineResult,
    PlanSpec,
    RuleSpec,
    SaleContext,
)

_HUNDRED = Decimal(100)

BENEFICIARY_LABELS = {
    "SELLER": "Venditore",
    "UPLINE_LEVEL": "Sponsor",
    "ROLE_IN_UPLINE": "Ruolo nella rete",
    "INFLUENCER": "Influencer",
    "PROMOTER": "Promoter (segnalatore)",
    "COMPANY": "Azienda",
}


def euro(cents: int) -> str:
    """Format cents for human-readable explanations: 12345 -> "123,45 €"."""
    sign = "-" if cents < 0 else ""
    cents = abs(cents)
    whole = f"{cents // 100:,}".replace(",", ".")
    return f"{sign}{whole},{cents % 100:02d} €"


def pct_text(value: Decimal) -> str:
    text = format(value.normalize(), "f")
    return text.replace(".", ",") + "%"


def percent_of(margin_cents: int, percentage: Decimal) -> int:
    """Percentage of the margin, rounded half-up to the cent (Decimal only)."""
    raw = Decimal(margin_cents) * percentage / _HUNDRED
    return int(raw.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def rule_label(rule: RuleSpec) -> str:
    if rule.label:
        return rule.label
    base = BENEFICIARY_LABELS.get(rule.beneficiary_type, rule.beneficiary_type)
    if rule.beneficiary_type == "UPLINE_LEVEL" and rule.network_level:
        return f"Sponsor livello {rule.network_level}"
    if rule.beneficiary_type == "ROLE_IN_UPLINE" and rule.required_role_code:
        return f"Primo {rule.required_role_code} nella rete"
    return base


# --- 1. How much -------------------------------------------------------------


def _nominal_amounts(plan: PlanSpec, margin_cents: int) -> dict[str, int]:
    amounts: dict[str, int] = {}
    for rule in plan.rules:
        if rule.calculation_type == "FIXED_AMOUNT":
            amount = int(rule.amount_cents or 0)
        elif rule.calculation_type in ("PERCENTAGE", "MINIMUM_GUARANTEE"):
            amount = percent_of(margin_cents, Decimal(rule.percentage or 0))
            if rule.min_amount_cents is not None:
                amount = max(amount, int(rule.min_amount_cents))
            if rule.max_amount_cents is not None:
                amount = min(amount, int(rule.max_amount_cents))
        else:  # REMAINDER is computed last
            continue
        if amount < 0:
            raise EngineError("negative_amount", f"La regola «{rule_label(rule)}» darebbe un importo negativo.")
        amounts[rule.id] = amount

    committed = sum(amounts.values())
    if committed > margin_cents:
        raise EngineError(
            "margin_exceeded",
            f"Le quote del piano ({euro(committed)}) superano il margine della vendita ({euro(margin_cents)}).",
        )

    remainder_rules = [r for r in plan.rules if r.calculation_type == "REMAINDER"]
    if remainder_rules:
        amounts[remainder_rules[0].id] = margin_cents - committed
        return amounts

    leftover = margin_cents - committed
    if plan.distribution_mode == "FULL" and leftover != 0:
        # Without a REMAINDER rule, a FULL plan is percentages summing to 100
        # (enforced by the validator), so any gap is rounding. It goes to the
        # largest share (ties: lowest sequence) to stay deterministic.
        pct_rules = [r for r in plan.rules if r.calculation_type in ("PERCENTAGE", "MINIMUM_GUARANTEE")]
        if not pct_rules or abs(leftover) > len(pct_rules):
            raise EngineError(
                "plan_not_closing",
                "Il piano è a distribuzione completa ma le sue quote non coprono il margine: "
                f"mancano {euro(leftover)}.",
            )
        target = max(pct_rules, key=lambda r: (amounts[r.id], -r.sequence))
        amounts[target.id] += leftover
    return amounts


# --- 2. To whom --------------------------------------------------------------


def _within(ctx: SaleContext, depth: int, limit: int | None = None) -> bool:
    caps = [c for c in (ctx.max_depth, limit) if c is not None]
    return all(depth <= c for c in caps)


def _by_depth(ctx: SaleContext) -> dict[int, ChainNode]:
    return {node.depth: node for node in ctx.chain}


def _search_up(
    ctx: SaleContext, *, start: int, limit: int | None, predicate
) -> ChainNode | None:
    for node in ctx.chain:
        if node.depth < start or not _within(ctx, node.depth, limit):
            continue
        if node.eligible and predicate(node):
            return node
    return None


def _resolve(rule: RuleSpec, ctx: SaleContext) -> tuple[ChainNode | None, str]:
    """Return the rule's beneficiary, or (None, reason it is missing)."""
    kind = rule.beneficiary_type
    if kind == "SELLER":
        seller = ctx.chain[0] if ctx.chain else None
        if seller is None:
            return None, "la vendita non ha un venditore"
        return (seller, "") if seller.eligible else (None, f"{seller.name} non è attivo")

    if kind == "UPLINE_LEVEL":
        level = int(rule.network_level or 0)
        if not _within(ctx, level):
            return None, f"il livello {level} è oltre la profondità del ruolo del venditore ({ctx.max_depth})"
        node = _by_depth(ctx).get(level)
        if node is None:
            return None, f"la rete del venditore non arriva al livello {level}"
        if not node.eligible:
            return None, f"{node.name} (livello {level}) non è attivo"
        if rule.required_role_id and node.role_id != rule.required_role_id:
            return None, f"{node.name} (livello {level}) non ha il ruolo {rule.required_role_code or 'richiesto'}"
        return node, ""

    if kind == "ROLE_IN_UPLINE":
        node = _search_up(
            ctx, start=1, limit=rule.network_level,
            predicate=lambda n: n.role_id == rule.required_role_id,
        )
        if node is None:
            return None, f"nessun {rule.required_role_code or 'ruolo richiesto'} attivo sopra il venditore"
        return node, ""

    if kind == "INFLUENCER":
        explicit = ctx.delegation_influencer
        if explicit is not None:
            return (explicit, "") if explicit.eligible else (None, f"l'influencer {explicit.name} non è attivo")
        node = _search_up(
            ctx, start=1, limit=rule.network_level,
            predicate=lambda n: n.allows_delegation
            and (not rule.required_role_id or n.role_id == rule.required_role_id),
        )
        if node is None:
            return None, "il venditore non è delegato di nessun influencer"
        return node, ""

    if kind == "PROMOTER":
        promoter = ctx.promoter
        if promoter is None:
            return None, "la vendita non nasce da una segnalazione"
        return (promoter, "") if promoter.eligible else (None, f"il promoter {promoter.name} non è attivo")

    return None, ""  # COMPANY is handled by the caller


def _next_available(rule: RuleSpec, ctx: SaleContext) -> ChainNode | None:
    """First eligible member above the vacant position."""
    if rule.beneficiary_type == "UPLINE_LEVEL":
        start = int(rule.network_level or 0) + 1
        return _search_up(
            ctx, start=start, limit=None,
            predicate=lambda n: not rule.required_role_id or n.role_id == rule.required_role_id,
        )
    if rule.beneficiary_type in ("ROLE_IN_UPLINE", "INFLUENCER"):
        return _search_up(ctx, start=1, limit=None, predicate=lambda n: True)
    return None


# --- Applying the plan --------------------------------------------------------


def _calc_value(rule: RuleSpec) -> Decimal | None:
    if rule.calculation_type in ("PERCENTAGE", "MINIMUM_GUARANTEE"):
        return Decimal(rule.percentage or 0)
    if rule.calculation_type == "FIXED_AMOUNT":
        return Decimal(int(rule.amount_cents or 0))
    return None


def _how(rule: RuleSpec, amount: int, margin_cents: int) -> str:
    if rule.calculation_type == "FIXED_AMOUNT":
        return f"quota fissa {euro(amount)}"
    if rule.calculation_type in ("PERCENTAGE", "MINIMUM_GUARANTEE"):
        base = percent_of(margin_cents, Decimal(rule.percentage or 0))
        text = f"{pct_text(Decimal(rule.percentage or 0))} del margine {euro(margin_cents)}"
        if amount != base:
            if rule.min_amount_cents is not None and amount == rule.min_amount_cents and amount > base:
                return f"{text} = {euro(base)}, portato al minimo garantito {euro(amount)}"
            if rule.max_amount_cents is not None and amount == rule.max_amount_cents and amount < base:
                return f"{text} = {euro(base)}, limitato al massimo {euro(amount)}"
            return f"{text} = {euro(amount)} (arrotondamento al centesimo)"
        return f"{text} = {euro(amount)}"
    return f"residuo del margine: {euro(amount)}"


def allocate(plan: PlanSpec, ctx: SaleContext) -> EngineResult:
    if ctx.margin_cents is None or ctx.margin_cents < 0:
        raise EngineError("no_margin", "La vendita non ha un margine di riferimento valido.")
    if not plan.rules:
        raise EngineError("empty_plan", "Il piano non ha regole.")

    amounts = _nominal_amounts(plan, ctx.margin_cents)
    allocations: list[Allocation] = []
    unallocated = 0
    warnings: list[str] = []

    for rule in sorted(plan.rules, key=lambda r: (r.sequence, r.id)):
        amount = amounts[rule.id]
        how = _how(rule, amount, ctx.margin_cents)
        label = rule_label(rule)
        common = dict(
            rule_id=rule.id, sequence=rule.sequence, label=label, beneficiary_type=rule.beneficiary_type,
            calculation_type=rule.calculation_type, calculation_value=_calc_value(rule), amount_cents=amount,
        )

        if rule.beneficiary_type == "COMPANY":
            allocations.append(Allocation(
                **common, beneficiary_kind=COMPANY, agent_id=None, agent_name="Azienda",
                network_level=None, role_code=None, explanation=f"Azienda: {how}",
            ))
            continue

        node, missing = _resolve(rule, ctx)
        if node is not None:
            allocations.append(Allocation(
                **common, beneficiary_kind=AGENT, agent_id=node.agent_id, agent_name=node.name,
                network_level=node.depth if node.depth >= 0 else None, role_code=node.role_code,
                explanation=f"{label} — {node.name}: {how}",
            ))
            continue

        strategy = rule.fallback_strategy or plan.fallback_strategy
        if strategy == "NEXT_AVAILABLE":
            substitute = _next_available(rule, ctx)
            if substitute is not None:
                allocations.append(Allocation(
                    **common, beneficiary_kind=AGENT, agent_id=substitute.agent_id, agent_name=substitute.name,
                    network_level=substitute.depth if substitute.depth >= 0 else None, role_code=substitute.role_code,
                    explanation=f"{label} — {missing}: passa a {substitute.name} (livello {substitute.depth}). {how}",
                    fallback_applied="NEXT_AVAILABLE",
                ))
                continue
            strategy = "COMPANY"
            missing = f"{missing}, e nessun idoneo più in alto"

        if strategy == "STOP":
            unallocated += amount
            if amount:
                warnings.append(f"{label}: {missing}. {euro(amount)} non distribuiti.")
            continue

        allocations.append(Allocation(
            **common, beneficiary_kind=COMPANY, agent_id=None, agent_name="Azienda",
            network_level=None, role_code=None,
            explanation=f"{label} — {missing}: la quota resta all'azienda. {how}",
            fallback_applied="COMPANY",
        ))

    leftover = ctx.margin_cents - sum(a.amount_cents for a in allocations)
    if leftover < 0:  # defensive; _nominal_amounts prevents this
        raise EngineError("margin_exceeded", "La distribuzione supera il margine.")
    if leftover:
        detail = []
        if unallocated:
            detail.append(f"{euro(unallocated)} di quote senza beneficiario")
        if leftover - unallocated:
            detail.append(f"{euro(leftover - unallocated)} non assegnati dal piano")
        allocations.append(Allocation(
            rule_id=None, sequence=10_000, label="Residuo azienda", beneficiary_type="COMPANY",
            beneficiary_kind=COMPANY, agent_id=None, agent_name="Azienda", network_level=None, role_code=None,
            calculation_type="REMAINDER", calculation_value=None, amount_cents=leftover,
            explanation="Resta all'azienda: " + ", ".join(detail) + ".",
            fallback_applied="STOP" if unallocated else None,
        ))

    result = EngineResult(margin_cents=ctx.margin_cents, allocations=tuple(allocations), warnings=tuple(warnings))
    # Explicit checks rather than `assert`, so they survive python -O.
    if result.distributed_cents != ctx.margin_cents:
        raise EngineError("invariant", "Invariante violata: la somma delle quote non è il margine.")
    if any(a.amount_cents < 0 for a in result.allocations):
        raise EngineError("invariant", "Invariante violata: quota negativa.")
    return result
