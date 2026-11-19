"""SOS Affiliate pure engine against the specification's verification table.

Each test names the case of "Specifica tecnica" v1.1 §12 it reproduces; the
pass criterion is the spec's: an exact match with the expected result.
"""

from decimal import Decimal

import pytest

from app.modules.affiliate import engine
from app.modules.affiliate.plan import DEFAULT_PLAN, PlanValidationError, validate_plan

LEVELS = engine.career_levels(DEFAULT_PLAN)
BM = DEFAULT_PLAN["bm_rates"]
BD = DEFAULT_PLAN["bd_rates"]
PACKS = {p["code"]: Decimal(p["price"]) for p in DEFAULT_PLAN["packs"]}


def career(bcp, legs):
    return engine.evaluate_career(bcp, legs, LEVELS, required_legs=3)


# --- 12.2 Carriera e volumi --------------------------------------------------


def test_11_level_1_threshold():
    r = career(260, [80, 80, 80])
    assert (r.bct, r.level, r.bonus) == (500, 1, Decimal("75.00"))


def test_12_total_one_point_short():
    r = career(259, [80, 80, 80])
    assert (r.bct, r.level, r.bonus) == (499, None, Decimal("0.00"))


def test_13_only_two_legs():
    r = career(260, [160, 80])
    assert (r.bct, r.level) == (500, None)


def test_14_third_leg_insufficient():
    r = career(260, [79, 80, 81])
    assert (r.bct, r.level) == (500, None)


def test_15_four_legs_one_weak():
    r = career(260, [10, 80, 80, 80])
    assert (r.bct, r.level, r.bonus) == (510, 1, Decimal("75.00"))


def test_16_level_2_bonus_is_not_cumulative():
    r = career(750, [250, 250, 250])
    assert (r.bct, r.level, r.bonus) == (1500, 2, Decimal("250.00"))


@pytest.mark.parametrize("lv", LEVELS, ids=lambda lv: f"level-{lv.level}")
def test_20_every_level_reached_at_the_exact_threshold(lv):
    r = career(lv.total_bc - 3 * lv.leg_min_bc, [lv.leg_min_bc] * 3)
    assert (r.level, r.bonus) == (lv.level, lv.bonus)


@pytest.mark.parametrize("lv", LEVELS, ids=lambda lv: f"level-{lv.level}")
def test_21_every_level_missed_by_one_personal_point(lv):
    r = career(lv.total_bc - 3 * lv.leg_min_bc - 1, [lv.leg_min_bc] * 3)
    assert r.level != lv.level and (r.level or 0) < lv.level


@pytest.mark.parametrize("lv", LEVELS, ids=lambda lv: f"level-{lv.level}")
def test_22_personal_points_never_replace_a_leg_minimum(lv):
    bcp = lv.total_bc - 3 * lv.leg_min_bc + 1
    r = career(bcp, [lv.leg_min_bc - 1, lv.leg_min_bc, lv.leg_min_bc])
    assert r.bct == lv.total_bc
    assert (r.level or 0) < lv.level


def test_presentation_examples():
    # "Il ruolo dei punti personali", both measured against level 2:
    # 200 + 500/500/500 = 1.700 qualifies; 800 + 1.500/200/100 = 2.600 does
    # not, because only one leg reaches 250. All three legs still clear
    # level 1's 80, so that one is the level actually reached.
    assert career(200, [500, 500, 500]).level == 2
    r = career(800, [1500, 200, 100])
    assert (r.bct, r.level) == (2600, 1)
    # "Il primo bonus": 40 + 350 personal, three legs of 80.
    assert (career(390, [80, 80, 80]).bct, career(390, [80, 80, 80]).bonus) == (630, Decimal("75.00"))


def test_progress_points_to_the_next_level():
    r = career(260, [80, 80, 80])
    assert (r.next_level, r.next_total_bc, r.next_leg_min_bc, r.next_qualifying_legs) == (2, 1500, 250, 0)
    assert career(0, []).next_level == 1


# --- 3.2 Rete: gambe e aggregazione -----------------------------------------


def test_a_b_c_example_counts_400_once_per_ancestor():
    parents = {"A": None, "B": "A", "C": "B"}
    sheets = engine.aggregate_volumes({"C": 400}, parents)
    assert sheets["C"].bcp == 400 and sheets["C"].legs == {}
    assert sheets["B"].bcp == 0 and sheets["B"].legs == {"C": 400}
    assert sheets["A"].bcp == 0 and sheets["A"].legs == {"B": 400}
    assert sheets["A"].bct == 400


def test_17_volume_beyond_the_thirteenth_level_reaches_every_ancestor():
    chain = [f"n{i}" for i in range(20)]
    parents = {n: (chain[i - 1] if i else None) for i, n in enumerate(chain)}
    sheets = engine.aggregate_volumes({"n19": 1500}, parents)
    assert sheets["n0"].legs == {"n1": 1500}
    assert sheets["n5"].legs == {"n6": 1500}
    assert all(sheets[n].bct == 1500 for n in chain)


def test_every_leg_contributes_to_the_total():
    parents = {"root": None, "a": "root", "b": "root", "c": "root", "d": "root", "a1": "a"}
    sheets = engine.aggregate_volumes({"root": 260, "a1": 80, "b": 80, "c": 80, "d": 10}, parents)
    root = sheets["root"]
    assert root.legs == {"a": 80, "b": 80, "c": 80, "d": 10}
    assert root.bct == 510


def test_cycle_in_corrupt_tree_does_not_loop():
    sheets = engine.aggregate_volumes({"x": 10}, {"x": "y", "y": "x"})
    assert sheets["x"].bcp == 10 and sheets["y"].legs == {"x": 10}


# --- 12.3 BM e BD ------------------------------------------------------------


def test_23_bm_rates_total_4_percent():
    assert len(BM) == 13 and sum(Decimal(r) for r in BM) == Decimal("4.00")


def test_24_bm_on_a_base():
    v = Decimal("10000.00")
    shares = engine.distribute(v, BM, [f"p{i}" for i in range(13)])
    assert shares[0].amount == v * Decimal("0.01")
    assert sum(s.amount for s in shares) == v * Decimal("0.04") == engine.theoretical_total(v, BM)
    # Presentation example on 10.000 MamiCash: 100, 65, 45, 40 ...
    assert [s.amount for s in shares[:4]] == [Decimal("100.00"), Decimal("65.00"), Decimal("45.00"), Decimal("40.00")]


def test_25_bd_rates_total_42_percent():
    assert len(BD) == 13 and sum(Decimal(r) for r in BD) == Decimal("42.00")


@pytest.mark.parametrize(
    "pack,direct,total",
    [("START", "180.00", "420.00"), ("BUSINESS", "360.00", "840.00"),
     ("PREMIUM", "720.00", "1680.00"), ("INTERNATIONAL", "1800.00", "4200.00")],
    ids=["26-start", "27-business", "28-premium", "29-international"],
)
def test_26_29_pack_direct_share_and_theoretical_total(pack, direct, total):
    shares = engine.distribute(PACKS[pack], BD, ["seller"])
    assert shares[0].amount == Decimal(direct)
    assert engine.theoretical_total(PACKS[pack], BD) == Decimal(total)


def test_30_business_in_mario_luca_andrea_giovanni():
    parents = {"Mario": None, "Luca": "Mario", "Andrea": "Luca", "Giovanni": "Andrea"}
    chain = engine.upline("Giovanni", parents, limit=13)
    paid = {s.beneficiary: s.amount for s in engine.distribute(PACKS["BUSINESS"], BD, chain) if s.beneficiary}
    assert paid == {"Giovanni": Decimal("360.00"), "Andrea": Decimal("140.00"),
                    "Luca": Decimal("100.00"), "Mario": Decimal("80.00")}
    assert sum(paid.values()) == Decimal("680.00")


def test_31_distribution_stops_at_position_13():
    chain = [f"n{i}" for i in range(30)]
    parents = {n: (chain[i + 1] if i + 1 < len(chain) else None) for i, n in enumerate(chain)}
    up = engine.upline("n0", parents, limit=13)
    shares = engine.distribute(PACKS["START"], BD, up)
    assert len(up) == 13 and len(shares) == 13
    assert shares[-1].beneficiary == "n12"
    assert sum(s.amount for s in shares) == Decimal("420.00")


def test_32_two_business_sales():
    one = engine.distribute(PACKS["BUSINESS"], BD, ["seller"])[0].amount
    assert one * 2 == Decimal("720.00")
    assert engine.theoretical_total(PACKS["BUSINESS"], BD) * 2 == Decimal("1680.00")


def test_money_rounds_half_up_to_the_cent():
    # 0,25% of 1.002 = 2,505 -> 2,51; a float would give 2,50.
    assert engine.distribute(Decimal("1002"), ["0.25"], ["x"])[0].amount == Decimal("2.51")


# --- Plan invariants (checklist §14) ----------------------------------------


def test_default_plan_is_valid():
    validate_plan(DEFAULT_PLAN)


@pytest.mark.parametrize("mutate", [
    lambda c: c["career_levels"].pop(),
    lambda c: c["bm_rates"].__setitem__(0, "1.10"),
    lambda c: c["bd_rates"].pop(),
])
def test_plan_breaking_the_specification_is_refused(mutate):
    import copy
    config = copy.deepcopy(DEFAULT_PLAN)
    mutate(config)
    with pytest.raises(PlanValidationError):
        validate_plan(config)


def test_periods():
    assert engine.next_period("2026-12") == "2027-01"
    assert engine.next_period("2026-11") == "2026-12"
    with pytest.raises(ValueError):
        engine.validate_period("2026-13")
