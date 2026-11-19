"""Pure SOS Affiliate calculations: no database, no clock, no I/O.

The same functions serve the monthly close, the live "current month" view
and the tests that reproduce the specification's verification table (§12).
Inputs are plain values so a result can always be rebuilt from the stored
operations and the plan version that was applied (ADM-04).
"""

from collections.abc import Hashable, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

CENT = Decimal("0.01")


def money(value: Decimal | str | int) -> Decimal:
    """Rounds to the cent, half up. The only rounding rule in the module (INT-06)."""
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


# --- Bonus Carriera ---------------------------------------------------------


@dataclass(frozen=True)
class CareerLevel:
    level: int
    total_bc: int
    leg_min_bc: int
    bonus: Decimal


def career_levels(config: Mapping[str, Any]) -> list[CareerLevel]:
    return [
        CareerLevel(lv["level"], int(lv["total_bc"]), int(lv["leg_min_bc"]), money(lv["bonus"]))
        for lv in config["career_levels"]
    ]


@dataclass(frozen=True)
class CareerResult:
    bcp: int
    bct: int
    level: int | None
    bonus: Decimal
    #: Requirements of the next level not yet reached, for UI-06.
    next_level: int | None = None
    next_total_bc: int | None = None
    next_leg_min_bc: int | None = None
    next_qualifying_legs: int = 0
    required_legs: int = 3


def evaluate_career(
    bcp: int, leg_volumes: Sequence[int], levels: Sequence[CareerLevel], *, required_legs: int = 3
) -> CareerResult:
    """Spec §5.3: BCT = BCP + sum of every leg; the highest level whose total
    and per-leg minimum (in at least `required_legs` distinct legs) are both
    met. Personal points help the total but never replace a leg minimum, and
    only that level's bonus is due: lower bonuses do not add up (CAR-03)."""
    bct = bcp + sum(leg_volumes)
    reached: CareerLevel | None = None
    for lv in sorted(levels, key=lambda x: x.level, reverse=True):
        valid_legs = sum(1 for v in leg_volumes if v >= lv.leg_min_bc)
        if bct >= lv.total_bc and valid_legs >= required_legs:
            reached = lv
            break
    nxt = next((lv for lv in sorted(levels, key=lambda x: x.level) if reached is None or lv.level > reached.level), None)
    return CareerResult(
        bcp=bcp,
        bct=bct,
        level=reached.level if reached else None,
        bonus=reached.bonus if reached else money(0),
        next_level=nxt.level if nxt else None,
        next_total_bc=nxt.total_bc if nxt else None,
        next_leg_min_bc=nxt.leg_min_bc if nxt else None,
        next_qualifying_legs=sum(1 for v in leg_volumes if nxt and v >= nxt.leg_min_bc),
        required_legs=required_legs,
    )


# --- Network aggregation ----------------------------------------------------


@dataclass
class VolumeSheet:
    """One affiliate's month: personal points and points per leg, where a
    leg is keyed by the direct child it starts from."""

    bcp: int = 0
    legs: dict[Hashable, int] = field(default_factory=dict)

    @property
    def bct(self) -> int:
        return self.bcp + sum(self.legs.values())


def aggregate_volumes(
    personal_points: Mapping[Hashable, int], parent_of: Mapping[Hashable, Hashable | None]
) -> dict[Hashable, VolumeSheet]:
    """Spec §3.2: points are personal for whoever generated them and, for
    every ancestor at any depth (NET-05), belong to exactly one leg: the one
    starting from the ancestor's direct child on the path. Each operation is
    therefore counted once in each ancestor's total (NET-06), and a cycle in
    corrupt data stops the walk instead of looping."""
    sheets: dict[Hashable, VolumeSheet] = {}
    for affiliate, points in personal_points.items():
        if not points:
            continue
        sheets.setdefault(affiliate, VolumeSheet()).bcp += points
        child, ancestor = affiliate, parent_of.get(affiliate)
        seen = {affiliate}
        while ancestor is not None and ancestor not in seen:
            seen.add(ancestor)
            sheet = sheets.setdefault(ancestor, VolumeSheet())
            sheet.legs[child] = sheet.legs.get(child, 0) + points
            child, ancestor = ancestor, parent_of.get(ancestor)
    return sheets


def upline(affiliate: Hashable, parent_of: Mapping[Hashable, Hashable | None], *, limit: int) -> list[Hashable]:
    """The seller followed by its sponsors, at most `limit` entries (BD-03, BD-04)."""
    chain = [affiliate]
    current = parent_of.get(affiliate)
    while current is not None and len(chain) < limit and current not in chain:
        chain.append(current)
        current = parent_of.get(current)
    return chain


# --- BD / BM distributions --------------------------------------------------


@dataclass(frozen=True)
class Share:
    position: int
    beneficiary: Hashable | None
    rate: Decimal
    amount: Decimal


def distribute(base: Decimal, rates: Sequence[Decimal | str], chain: Sequence[Hashable]) -> list[Share]:
    """Every rate applies to the whole base (BM-04, BD-05), position 1 is the
    direct seller (BD-02) and the chain is never compressed: positions with
    nobody above stay unassigned, exactly as in the spec's example where
    four people receive 680 of the theoretical 840 (§7.4)."""
    shares = []
    for i, rate in enumerate(rates):
        rate = Decimal(rate)
        shares.append(Share(
            position=i + 1,
            beneficiary=chain[i] if i < len(chain) else None,
            rate=rate,
            amount=money(Decimal(base) * rate / 100),
        ))
    return shares


def theoretical_total(base: Decimal, rates: Sequence[Decimal | str]) -> Decimal:
    return money(Decimal(base) * sum(Decimal(r) for r in rates) / 100)


# --- Calendar ---------------------------------------------------------------


def next_period(period: str) -> str:
    year, month = (int(x) for x in period.split("-"))
    return f"{year + month // 12}-{month % 12 + 1:02d}"


def validate_period(period: str) -> str:
    try:
        year, month = (int(x) for x in period.split("-"))
    except ValueError as exc:
        raise ValueError("Periodo non valido: usa il formato AAAA-MM.") from exc
    if not (2000 <= year <= 2100 and 1 <= month <= 12) or len(period) != 7:
        raise ValueError("Periodo non valido: usa il formato AAAA-MM.")
    return period
