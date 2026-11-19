"""Tests for the legacy branch cap (33% rule)."""

from app.modules.commissions.policies.branch_cap import BranchProduction, apply_branch_cap


def test_single_branch_under_cap_fully_eligible():
    # Four branches at 25% each: all under the cap.
    branches = [
        BranchProduction("branch-a", 20_000),
        BranchProduction("branch-b", 20_000),
        BranchProduction("branch-c", 20_000),
        BranchProduction("branch-d", 20_000),
    ]
    result = apply_branch_cap(branches, cap_percentage=33)
    assert result.per_branch_eligible_cents["branch-a"] == 20_000
    assert result.excluded_production_cents == 0


def test_single_branch_is_entire_production_so_it_hits_the_cap():
    # A lone branch is 100% of production, so it is cut to the cap.
    branches = [BranchProduction("branch-a", 30_000)]
    result = apply_branch_cap(branches, cap_percentage=33)
    assert result.gross_production_cents == 30_000
    assert result.eligible_production_cents == 9_900  # 33% of 30_000
    assert result.excluded_production_cents == 20_100


def test_branch_exactly_at_cap_boundary_not_excluded():
    branches = [BranchProduction("a", 10_000), BranchProduction("b", 10_000)]
    result = apply_branch_cap(branches, cap_percentage=50)
    # Each branch sits exactly at the 50% cap, which is not over it.
    assert result.per_branch_eligible_cents["a"] == 10_000
    assert result.per_branch_eligible_cents["b"] == 10_000
    assert result.excluded_production_cents == 0


def test_one_branch_over_cap_excess_excluded_not_redistributed():
    branches = [BranchProduction("dominant", 27_000), BranchProduction("small", 3_000)]
    result = apply_branch_cap(branches, cap_percentage=33)
    gross = 30_000
    cap_amount = int(gross * 33 / 100)  # 9_900
    assert result.per_branch_eligible_cents["dominant"] == cap_amount
    assert result.per_branch_eligible_cents["small"] == 3_000
    assert result.excluded_production_cents == 27_000 - cap_amount
    # The excess is dropped, not redistributed to other branches.
    assert result.eligible_production_cents == cap_amount + 3_000


def test_multiple_branches_none_over_cap():
    branches = [BranchProduction("a", 5_000), BranchProduction("b", 5_000), BranchProduction("c", 5_000)]
    result = apply_branch_cap(branches, cap_percentage=50)
    assert result.excluded_production_cents == 0
    assert result.eligible_production_cents == 15_000


def test_no_branches_returns_zero_eligible():
    result = apply_branch_cap([], cap_percentage=33)
    assert result.gross_production_cents == 0
    assert result.eligible_production_cents == 0
    assert result.excluded_production_cents == 0


def test_zero_total_production_returns_zero_eligible():
    branches = [BranchProduction("a", 0), BranchProduction("b", 0)]
    result = apply_branch_cap(branches, cap_percentage=33)
    assert result.eligible_production_cents == 0
