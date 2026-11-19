"""Margin distribution engine, without a database.

The percentages used here are test data, not configuration: in production
every share is set by the organization's administrators.
"""

import random
from decimal import Decimal

import pytest

from app.modules.commissions.engine.allocate import allocate
from app.modules.commissions.engine.types import (
    ChainNode,
    EngineError,
    PlanSpec,
    RuleSpec,
    SaleContext,
)
from app.modules.commissions.engine.validation import validate_plan

MARGIN = 15000  # 150.00 EUR


def node(depth, name, role="NET", *, eligible=True, delegation=False, role_id=None):
    return ChainNode(
        agent_id=f"a-{name}", name=name, depth=depth, role_id=role_id or f"r-{role}", role_code=role,
        eligible=eligible, allows_delegation=delegation,
    )


def rule(seq, beneficiary, calc, *, pct=None, amount=None, level=None, role=None, min_=None, max_=None, fallback=None):
    return RuleSpec(
        id=f"rule-{seq}", sequence=seq, beneficiary_type=beneficiary, calculation_type=calc,
        percentage=Decimal(str(pct)) if pct is not None else None, amount_cents=amount,
        network_level=level, required_role_id=f"r-{role}" if role else None, required_role_code=role,
        min_amount_cents=min_, max_amount_cents=max_, fallback_strategy=fallback,
    )


def plan(*rules, fallback="COMPANY", mode="FULL"):
    return PlanSpec(id="plan", version=1, name="Test", fallback_strategy=fallback, distribution_mode=mode, rules=rules)


def by_label(result):
    return {(a.agent_name, a.label): a.amount_cents for a in result.allocations}


# --- Reference scenarios ---


def test_porta_a_porta_seller_and_director():
    """60% to the seller, 40% to the first Director above them."""
    p = plan(
        rule(1, "SELLER", "PERCENTAGE", pct=60),
        rule(2, "ROLE_IN_UPLINE", "PERCENTAGE", pct=40, role="DIR"),
    )
    chain = (node(0, "Luca", "PAP"), node(1, "Anna", "DIR"))
    result = allocate(p, SaleContext(margin_cents=MARGIN, chain=chain, max_depth=2))
    assert [(a.agent_name, a.amount_cents) for a in result.allocations] == [("Luca", 9000), ("Anna", 6000)]
    assert result.company_cents == 0


def test_networker_four_levels():
    """50% seller, 20/15/10% to upline levels 1-3, 5% company."""
    p = plan(
        rule(1, "SELLER", "PERCENTAGE", pct=50),
        rule(2, "UPLINE_LEVEL", "PERCENTAGE", pct=20, level=1),
        rule(3, "UPLINE_LEVEL", "PERCENTAGE", pct=15, level=2),
        rule(4, "UPLINE_LEVEL", "PERCENTAGE", pct=10, level=3),
        rule(5, "COMPANY", "PERCENTAGE", pct=5),
    )
    chain = (node(0, "Paolo"), node(1, "Anna"), node(2, "Mario"), node(3, "Luca"))
    result = allocate(p, SaleContext(margin_cents=MARGIN, chain=chain))
    assert [a.amount_cents for a in result.allocations] == [7500, 3000, 2250, 1500, 750]
    assert result.agents_cents == 14250 and result.company_cents == 750


@pytest.mark.parametrize(
    "fallback, expected_company, expected_agents",
    [
        ("COMPANY", 1500 + 750, 12750),       # missing level 3 goes to the company
        ("STOP", 1500 + 750, 12750),          # undistributed, left to the company
        ("NEXT_AVAILABLE", 1500 + 750, 12750),  # nobody higher up, so the company
    ],
)
def test_networker_incomplete_upline(fallback, expected_company, expected_agents):
    """The plan pays level 3 but the upline stops at level 2."""
    p = plan(
        rule(1, "SELLER", "PERCENTAGE", pct=50),
        rule(2, "UPLINE_LEVEL", "PERCENTAGE", pct=20, level=1),
        rule(3, "UPLINE_LEVEL", "PERCENTAGE", pct=15, level=2),
        rule(4, "UPLINE_LEVEL", "PERCENTAGE", pct=10, level=3),
        rule(5, "COMPANY", "PERCENTAGE", pct=5),
        fallback=fallback,
    )
    chain = (node(0, "Paolo"), node(1, "Anna"), node(2, "Mario"))
    result = allocate(p, SaleContext(margin_cents=MARGIN, chain=chain))
    assert result.company_cents == expected_company
    assert result.agents_cents == expected_agents
    assert result.distributed_cents == MARGIN


def test_next_available_skips_inactive_sponsor():
    """With NEXT_AVAILABLE, an inactive level-1 sponsor's share moves up to level 2."""
    p = plan(
        rule(1, "SELLER", "PERCENTAGE", pct=80),
        rule(2, "UPLINE_LEVEL", "PERCENTAGE", pct=20, level=1),
        fallback="NEXT_AVAILABLE",
    )
    chain = (node(0, "Paolo"), node(1, "Anna", eligible=False), node(2, "Mario"))
    result = allocate(p, SaleContext(margin_cents=MARGIN, chain=chain))
    sponsor = result.allocations[1]
    assert (sponsor.agent_name, sponsor.amount_cents, sponsor.fallback_applied) == ("Mario", 3000, "NEXT_AVAILABLE")


def test_role_depth_limits_reach():
    """A seller role limited to one level cannot pay level 2."""
    p = plan(
        rule(1, "SELLER", "PERCENTAGE", pct=60),
        rule(2, "UPLINE_LEVEL", "PERCENTAGE", pct=20, level=1),
        rule(3, "UPLINE_LEVEL", "PERCENTAGE", pct=20, level=2),
    )
    chain = (node(0, "Paolo"), node(1, "Anna"), node(2, "Mario"))
    result = allocate(p, SaleContext(margin_cents=MARGIN, chain=chain, max_depth=1))
    assert result.allocations[2].beneficiary_kind == "COMPANY"
    assert result.agents_cents == 12000


def test_influencer_delegate():
    """A delegate sells: 40% to them, 20% to the influencer, 40% to the level above."""
    p = plan(
        rule(1, "SELLER", "PERCENTAGE", pct=40),
        rule(2, "INFLUENCER", "PERCENTAGE", pct=20),
        rule(3, "UPLINE_LEVEL", "PERCENTAGE", pct=40, level=2),
    )
    chain = (node(0, "Delegato", "DEL"), node(1, "Chiara", "INF", delegation=True), node(2, "Mario", "NET"))
    result = allocate(p, SaleContext(margin_cents=MARGIN, chain=chain))
    assert by_label(result) == {
        ("Delegato", "Venditore"): 6000, ("Chiara", "Influencer"): 3000, ("Mario", "Sponsor livello 2"): 6000,
    }


def test_influencer_with_many_delegates_and_explicit_delegation():
    """An explicit delegation wins over the sponsor chain when a delegate
    joined under a different sponsor."""
    p = plan(
        rule(1, "SELLER", "PERCENTAGE", pct=40),
        rule(2, "INFLUENCER", "PERCENTAGE", pct=20),
        rule(3, "COMPANY", "REMAINDER"),
    )
    chiara = node(1, "Chiara", "INF", delegation=True)
    first = allocate(p, SaleContext(margin_cents=MARGIN, chain=(node(0, "D1", "DEL"), chiara)))
    other_branch = (node(0, "D2", "DEL"), node(1, "Paolo", "NET"))
    second = allocate(p, SaleContext(
        margin_cents=MARGIN, chain=other_branch, delegation_influencer=node(99, "Chiara", "INF", delegation=True),
    ))
    assert first.allocations[1].agent_name == "Chiara" == second.allocations[1].agent_name
    assert first.allocations[1].amount_cents == second.allocations[1].amount_cents == 3000


def test_promoter_fee_when_sale_comes_from_a_lead():
    """A referral pays the promoter a fixed fee; the rest goes to the closing chain."""
    p = plan(
        rule(1, "PROMOTER", "FIXED_AMOUNT", amount=2500),
        rule(2, "SELLER", "PERCENTAGE", pct=50),
        rule(3, "UPLINE_LEVEL", "REMAINDER", level=1),
    )
    chain = (node(0, "Luca", "PAP"), node(1, "Anna", "DIR"))
    result = allocate(p, SaleContext(margin_cents=MARGIN, chain=chain, promoter=node(-1, "Sara", "PRO")))
    assert by_label(result) == {
        ("Sara", "Promoter (segnalatore)"): 2500, ("Luca", "Venditore"): 7500, ("Anna", "Sponsor livello 1"): 5000,
    }


def test_promoter_fee_without_lead_follows_fallback():
    """Without a referral, the promoter fee is paid to no agent and follows the fallback."""
    p = plan(
        rule(1, "PROMOTER", "FIXED_AMOUNT", amount=2500),
        rule(2, "SELLER", "REMAINDER"),
        fallback="STOP",
    )
    result = allocate(p, SaleContext(margin_cents=MARGIN, chain=(node(0, "Luca"),)))
    assert result.agents_cents == 12500
    assert result.company_cents == 2500
    assert result.allocations[-1].label == "Residuo azienda"
    assert result.warnings


def test_minimum_guarantee_and_cap():
    p = plan(
        rule(1, "SELLER", "MINIMUM_GUARANTEE", pct=10, min_=2000),
        rule(2, "UPLINE_LEVEL", "PERCENTAGE", pct=50, level=1, max_=5000),
        rule(3, "COMPANY", "REMAINDER"),
    )
    result = allocate(p, SaleContext(margin_cents=MARGIN, chain=(node(0, "Luca"), node(1, "Anna"))))
    assert [a.amount_cents for a in result.allocations] == [2000, 5000, 8000]


def test_fixed_amounts_over_margin_are_refused():
    p = plan(rule(1, "SELLER", "FIXED_AMOUNT", amount=20000), rule(2, "COMPANY", "REMAINDER"))
    with pytest.raises(EngineError) as exc:
        allocate(p, SaleContext(margin_cents=MARGIN, chain=(node(0, "Luca"),)))
    assert exc.value.code == "margin_exceeded"


def test_rounding_cent_goes_to_largest_share_deterministically():
    """Three 33.3333% shares of 100.00 sum to 99.99; the missing cent goes to
    the largest share (the first one on ties)."""
    p = plan(
        rule(1, "SELLER", "PERCENTAGE", pct="33.3334"),
        rule(2, "UPLINE_LEVEL", "PERCENTAGE", pct="33.3333", level=1),
        rule(3, "UPLINE_LEVEL", "PERCENTAGE", pct="33.3333", level=2),
    )
    chain = (node(0, "A"), node(1, "B"), node(2, "C"))
    result = allocate(p, SaleContext(margin_cents=10000, chain=chain))
    assert [a.amount_cents for a in result.allocations] == [3334, 3333, 3333]
    odd = allocate(p, SaleContext(margin_cents=1, chain=chain))
    assert odd.distributed_cents == 1


def test_partial_plan_leaves_residual_to_company():
    p = plan(rule(1, "SELLER", "PERCENTAGE", pct=30), mode="PARTIAL")
    result = allocate(p, SaleContext(margin_cents=MARGIN, chain=(node(0, "Luca"),)))
    assert result.agents_cents == 4500 and result.company_cents == 10500


# --- Validator ---


@pytest.mark.parametrize("total", ["99", "101"])
def test_full_plan_must_close_exactly(total):
    """A FULL plan totalling 99% or 101% is invalid."""
    rules = [rule(1, "SELLER", "PERCENTAGE", pct=50), rule(2, "UPLINE_LEVEL", "PERCENTAGE", pct=Decimal(total) - 50, level=1)]
    v = validate_plan(rules, distribution_mode="FULL", fallback_strategy="COMPANY")
    assert not v.ok


def test_valid_mixed_plan_with_remainder():
    rules = [
        rule(1, "PROMOTER", "FIXED_AMOUNT", amount=2500),
        rule(2, "SELLER", "PERCENTAGE", pct=50),
        rule(3, "UPLINE_LEVEL", "REMAINDER", level=1),
    ]
    v = validate_plan(rules, distribution_mode="FULL", fallback_strategy="COMPANY", reference_margin_cents=MARGIN)
    assert v.ok, v.errors
    assert v.distributed_cents == 10000 and v.residual_cents == 5000


@pytest.mark.parametrize(
    "rules, message",
    [
        ([rule(1, "SELLER", "PERCENTAGE", pct=60), rule(2, "SELLER", "PERCENTAGE", pct=40)], "duplica"),
        ([rule(1, "SELLER", "FIXED_AMOUNT", amount=-5), rule(2, "COMPANY", "REMAINDER")], "maggiore di zero"),
        ([rule(1, "SELLER", "REMAINDER"), rule(2, "COMPANY", "REMAINDER")], "al massimo una"),
        ([rule(1, "UPLINE_LEVEL", "PERCENTAGE", pct=100)], "livello"),
        ([rule(1, "SELLER", "FIXED_AMOUNT", amount=1000)], "Residuo"),
        ([rule(1, "SELLER", "PERCENTAGE", pct=120)], "100"),
    ],
)
def test_invalid_plans(rules, message):
    v = validate_plan(rules, distribution_mode="FULL", fallback_strategy="COMPANY")
    assert not v.ok
    assert any(message in e for e in v.errors), v.errors


def test_fixed_amount_over_reference_margin_is_invalid():
    rules = [rule(1, "SELLER", "FIXED_AMOUNT", amount=16000), rule(2, "COMPANY", "REMAINDER")]
    v = validate_plan(rules, distribution_mode="FULL", fallback_strategy="COMPANY", reference_margin_cents=MARGIN)
    assert not v.ok


# --- Invariants on random plans and networks ---


def _random_valid_plan(rng: random.Random) -> PlanSpec:
    rules = []
    kinds = ["SELLER", "UPLINE_LEVEL", "UPLINE_LEVEL", "UPLINE_LEVEL", "INFLUENCER", "PROMOTER", "ROLE_IN_UPLINE"]
    budget = Decimal(100)
    level = 0
    for seq in range(1, rng.randint(2, 6)):
        kind = kinds[min(seq - 1, len(kinds) - 1)] if seq == 1 else rng.choice(kinds[1:])
        lvl = None
        if kind == "UPLINE_LEVEL":
            level += 1
            lvl = level
        pct = Decimal(rng.randint(1, 3000)) / 100
        if pct > budget - 1:
            break
        budget -= pct
        rules.append(rule(seq, kind, rng.choice(["PERCENTAGE", "FIXED_AMOUNT"]) if kind != "SELLER" else "PERCENTAGE",
                          pct=pct, amount=None, level=lvl, role="DIR" if kind == "ROLE_IN_UPLINE" else None))
    fixed = []
    for r in rules:
        if r.calculation_type == "FIXED_AMOUNT":
            fixed.append(RuleSpec(**{**r.__dict__, "percentage": None, "amount_cents": rng.randint(1, 500)}))
        else:
            fixed.append(r)
    fixed.append(rule(99, rng.choice(["COMPANY", "SELLER" if not any(r.beneficiary_type == "SELLER" for r in fixed) else "COMPANY"]), "REMAINDER"))
    return plan(*fixed, fallback=rng.choice(["COMPANY", "NEXT_AVAILABLE", "STOP"]))


def test_invariants_on_random_plans_and_networks():
    """Over random combinations: lines always sum to the margin, none is
    negative, each has a beneficiary and a traceable rule, nobody is paid twice
    for one rule, and recalculating gives the same result."""
    rng = random.Random(20260922)
    checked = 0
    for _ in range(3000):
        p = _random_valid_plan(rng)
        depth = rng.randint(0, 6)
        chain = tuple(
            node(d, f"n{d}", rng.choice(["NET", "DIR", "INF"]), eligible=d == 0 or rng.random() > 0.2,
                 delegation=rng.random() > 0.7)
            for d in range(depth + 1)
        )
        ctx = SaleContext(
            margin_cents=rng.randint(0, 50000), chain=chain,
            max_depth=rng.choice([None, 1, 2, 3, 5]),
            promoter=node(-1, "prom", "PRO") if rng.random() > 0.5 else None,
        )
        try:
            result = allocate(p, ctx)
        except EngineError as exc:
            assert exc.code == "margin_exceeded"  # fixed shares exceed a small margin
            continue
        checked += 1
        assert result.distributed_cents == ctx.margin_cents
        assert all(a.amount_cents >= 0 for a in result.allocations)
        assert all((a.beneficiary_kind == "COMPANY") == (a.agent_id is None) for a in result.allocations)
        assert all(a.rule_id or a.label == "Residuo azienda" for a in result.allocations)
        rule_ids = [a.rule_id for a in result.allocations if a.rule_id]
        assert len(rule_ids) == len(set(rule_ids))
        assert allocate(p, ctx) == result
    assert checked > 2000
