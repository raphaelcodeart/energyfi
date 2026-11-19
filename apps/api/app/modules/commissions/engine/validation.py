"""Validation a Split Plan must pass before it can become ACTIVE.

* PERCENTAGE / MINIMUM_GUARANTEE are percentages of the margin (0-100) whose
  sum never exceeds 100.
* FIXED_AMOUNT is independent of the margin. It is checked against the
  product's reference margin when fixed; with a percentage margin the check
  happens per sale, and a sale whose margin is insufficient is held for
  review rather than partially paid.
* REMAINDER takes what is left; at most one per plan.
* FULL requires either a REMAINDER or pure percentages (no min/max) summing
  to exactly 100.
* PARTIAL distributes only what is declared; the rest is the company's.

Errors are user-facing; the summary on the reference margin feeds the
panel's distributed/residual totals.
"""

from dataclasses import dataclass, field
from decimal import Decimal

from app.modules.commissions.engine.allocate import euro, percent_of, rule_label
from app.modules.commissions.engine.types import RuleSpec

BENEFICIARY_TYPES = ("SELLER", "UPLINE_LEVEL", "ROLE_IN_UPLINE", "INFLUENCER", "PROMOTER", "COMPANY")
CALCULATION_TYPES = ("PERCENTAGE", "FIXED_AMOUNT", "MINIMUM_GUARANTEE", "REMAINDER")
FALLBACK_STRATEGIES = ("COMPANY", "NEXT_AVAILABLE", "STOP")
DISTRIBUTION_MODES = ("FULL", "PARTIAL")


@dataclass
class PlanValidation:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    percentage_total: Decimal = Decimal(0)
    fixed_total_cents: int = 0
    has_remainder: bool = False
    #: Computed on the reference margin when known; the residual goes to the
    #: REMAINDER rule if any, otherwise to the company.
    reference_margin_cents: int | None = None
    distributed_cents: int | None = None
    residual_cents: int | None = None

    @property
    def ok(self) -> bool:
        return not self.errors


def validate_plan(
    rules: list[RuleSpec],
    *,
    distribution_mode: str,
    fallback_strategy: str,
    reference_margin_cents: int | None = None,
    seller_role_can_close_sales: bool | None = None,
) -> PlanValidation:
    v = PlanValidation(reference_margin_cents=reference_margin_cents)

    if distribution_mode not in DISTRIBUTION_MODES:
        v.errors.append("Modalità di distribuzione non valida.")
    if fallback_strategy not in FALLBACK_STRATEGIES:
        v.errors.append("Strategia per il livello mancante non valida.")
    if seller_role_can_close_sales is False:
        v.errors.append("Il ruolo del venditore non può chiudere vendite: un piano per questo ruolo non si applicherebbe mai.")
    if not rules:
        v.errors.append("Il piano non ha regole.")
        return v

    seen: dict[tuple, str] = {}
    remainders = 0
    has_min_or_max = False
    for rule in rules:
        name = f"«{rule_label(rule)}»"
        if rule.beneficiary_type not in BENEFICIARY_TYPES:
            v.errors.append(f"{name}: tipo di beneficiario non valido.")
            continue
        if rule.calculation_type not in CALCULATION_TYPES:
            v.errors.append(f"{name}: tipo di calcolo non valido.")
            continue
        if rule.fallback_strategy is not None and rule.fallback_strategy not in FALLBACK_STRATEGIES:
            v.errors.append(f"{name}: strategia per il livello mancante non valida.")

        if rule.beneficiary_type == "UPLINE_LEVEL" and not (rule.network_level and rule.network_level >= 1):
            v.errors.append(f"{name}: indica il livello di rete (1 = sponsor diretto).")
        if rule.beneficiary_type == "ROLE_IN_UPLINE" and not rule.required_role_id:
            v.errors.append(f"{name}: indica quale ruolo cercare nella rete.")
        if rule.network_level is not None and rule.network_level < 1:
            v.errors.append(f"{name}: il livello di rete parte da 1.")

        key = (rule.beneficiary_type, rule.network_level, rule.required_role_id)
        if rule.beneficiary_type != "COMPANY" and key in seen:
            v.errors.append(f"{name} duplica {seen[key]}: stesso beneficiario due volte.")
        seen.setdefault(key, name)

        ct = rule.calculation_type
        if ct in ("PERCENTAGE", "MINIMUM_GUARANTEE"):
            if rule.percentage is None:
                v.errors.append(f"{name}: manca la percentuale.")
            elif not (Decimal(0) < Decimal(rule.percentage) <= Decimal(100)):
                v.errors.append(f"{name}: la percentuale deve essere maggiore di 0 e al massimo 100.")
            else:
                v.percentage_total += Decimal(rule.percentage)
            if rule.amount_cents is not None:
                v.errors.append(f"{name}: una quota percentuale non ha anche un importo fisso.")
            if ct == "MINIMUM_GUARANTEE" and rule.min_amount_cents is None:
                v.errors.append(f"{name}: un minimo garantito ha bisogno dell'importo minimo.")
        elif ct == "FIXED_AMOUNT":
            if rule.amount_cents is None or rule.amount_cents <= 0:
                v.errors.append(f"{name}: l'importo fisso deve essere maggiore di zero.")
            else:
                v.fixed_total_cents += int(rule.amount_cents)
            if rule.percentage is not None:
                v.errors.append(f"{name}: un importo fisso non ha anche una percentuale.")
        elif ct == "REMAINDER":
            remainders += 1
            if rule.percentage is not None or rule.amount_cents is not None:
                v.errors.append(f"{name}: il residuo non ha valore proprio, prende ciò che resta.")

        for attr, label in (("min_amount_cents", "minimo"), ("max_amount_cents", "massimo")):
            value = getattr(rule, attr)
            if value is None:
                continue
            has_min_or_max = True
            if ct not in ("PERCENTAGE", "MINIMUM_GUARANTEE"):
                v.errors.append(f"{name}: minimo e massimo valgono solo per le quote percentuali.")
            if value < 0:
                v.errors.append(f"{name}: il {label} non può essere negativo.")
        if (
            rule.min_amount_cents is not None and rule.max_amount_cents is not None
            and rule.min_amount_cents > rule.max_amount_cents
        ):
            v.errors.append(f"{name}: il minimo supera il massimo.")

    v.has_remainder = remainders > 0
    if remainders > 1:
        v.errors.append("Un piano può avere al massimo una regola Residuo.")
    if v.percentage_total > 100:
        v.errors.append(f"Le percentuali sommano {v.percentage_total.normalize()}%: non possono superare il 100%.")

    if distribution_mode == "FULL" and not v.has_remainder:
        only_pct = all(r.calculation_type == "PERCENTAGE" for r in rules)
        if not only_pct or has_min_or_max:
            v.errors.append(
                "Distribuzione completa con quote fisse, minimi o tetti: aggiungi una regola Residuo "
                "che prenda ciò che resta, così il totale è sempre esattamente il margine."
            )
        elif v.percentage_total != 100:
            v.errors.append(
                f"Distribuzione completa: le percentuali devono sommare esattamente 100%, "
                f"ora sommano {v.percentage_total.normalize()}%."
            )
    if distribution_mode == "PARTIAL" and v.has_remainder:
        v.errors.append("Con una regola Residuo il margine è distribuito tutto: scegli la distribuzione completa.")

    if reference_margin_cents is not None:
        committed = v.fixed_total_cents
        for rule in rules:
            if rule.calculation_type in ("PERCENTAGE", "MINIMUM_GUARANTEE") and rule.percentage is not None:
                amount = percent_of(reference_margin_cents, Decimal(rule.percentage))
                if rule.min_amount_cents is not None:
                    amount = max(amount, rule.min_amount_cents)
                if rule.max_amount_cents is not None:
                    amount = min(amount, rule.max_amount_cents)
                committed += amount
        if committed > reference_margin_cents:
            v.errors.append(
                f"Sul margine di riferimento ({euro(reference_margin_cents)}) le quote valgono "
                f"{euro(committed)}: lo superano."
            )
        v.distributed_cents = committed
        v.residual_cents = max(reference_margin_cents - committed, 0)
    elif v.fixed_total_cents:
        v.warnings.append(
            "Il piano contiene quote fisse e il margine del prodotto non è un importo fisso: "
            "ogni vendita verrà controllata, e una vendita con margine insufficiente resterà da rivedere."
        )

    return v
