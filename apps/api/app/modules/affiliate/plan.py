"""SOS Affiliate compensation plan: the default configuration and its checks.

The plan is data, not code. Every number below comes from two documents:
"SOS Affiliate - Specifica tecnica" v1.1 (28/10/2026) and "Piano Compensi SOS
Affiliate" (29/10/2026). It is stored as a versioned row
(`sn_aff_plan_versions`), and every operation records the version it was
computed with, so a new plan never rewrites the past (INT-09, INT-10).

Monetary values are strings so they reach `Decimal` without passing through
a float.
"""

from decimal import Decimal
from typing import Any

PLAN_VERSION_LABEL = "1.1"

DEFAULT_PLAN: dict[str, Any] = {
    # Digital Ambassador monthly subscription (BC-01, BC-02).
    "subscription": {"code": "DIGITAL_AMBASSADOR", "name": "Digital Ambassador", "price": "49.00", "bc": 40},
    # Licence catalogue (spec §4.1, §8.1). BC are per purchase, never per
    # licence (BC-04, BC-05).
    "license_products": [
        {"code": "LICENSE_1", "name": "Licenza singola", "licenses": 1, "nominal": "500.00", "price": "500.00", "bc": 400},
        {"code": "SMALL", "name": "SMALL", "licenses": 2, "nominal": "1000.00", "price": "400.00", "bc": 350},
        {"code": "MEDIUM", "name": "MEDIUM", "licenses": 5, "nominal": "2500.00", "price": "800.00", "bc": 700},
        {"code": "LARGE", "name": "LARGE", "licenses": 12, "nominal": "6000.00", "price": "1600.00", "bc": 1500},
    ],
    # Rome event tickets (piano compensi, "Evento Roma"): BC per formula,
    # never per ticket.
    "event_ticket_products": [
        {"code": "ROMA_1", "name": "Evento Roma - 1 biglietto", "tickets": 1, "price": "70.00", "bc": 50},
        {"code": "ROMA_5", "name": "Evento Roma - 5 biglietti", "tickets": 5, "price": "300.00", "bc": 270},
        {"code": "ROMA_10", "name": "Evento Roma - 10 biglietti", "tickets": 10, "price": "500.00", "bc": 450},
        {"code": "ROMA_20", "name": "Evento Roma - 20 biglietti", "tickets": 20, "price": "700.00", "bc": 600},
    ],
    # Licence resale (piano compensi, "Come funziona la rivendita"): the
    # client pays 500, the seller is owed 450, the company keeps 50 to buy the
    # 500 MamiCash credited to the client company. No BC (BC-06).
    "license_resale": {"price": "500.00", "seller_amount": "450.00", "company_amount": "50.00", "client_mamicash": "500.00"},
    # Commercial Packs generating BD (spec §7.1). Not the licence packages.
    "packs": [
        {"code": "START", "name": "START", "price": "1000.00"},
        {"code": "BUSINESS", "name": "BUSINESS", "price": "2000.00"},
        {"code": "PREMIUM", "name": "PREMIUM", "price": "4000.00"},
        {"code": "INTERNATIONAL", "name": "INTERNATIONAL", "price": "10000.00"},
    ],
    # Career levels (spec §5.1): total BC, minimum BC in each of at least
    # three legs, monthly bonus in euro.
    "career_levels": [
        {"level": 1, "total_bc": 500, "leg_min_bc": 80, "bonus": "75.00"},
        {"level": 2, "total_bc": 1500, "leg_min_bc": 250, "bonus": "250.00"},
        {"level": 3, "total_bc": 6000, "leg_min_bc": 1000, "bonus": "750.00"},
        {"level": 4, "total_bc": 20000, "leg_min_bc": 2500, "bonus": "2000.00"},
        {"level": 5, "total_bc": 50000, "leg_min_bc": 7500, "bonus": "3500.00"},
        {"level": 6, "total_bc": 200000, "leg_min_bc": 25000, "bonus": "10000.00"},
        {"level": 7, "total_bc": 500000, "leg_min_bc": 100000, "bonus": "25000.00"},
        {"level": 8, "total_bc": 1250000, "leg_min_bc": 250000, "bonus": "60000.00"},
        {"level": 9, "total_bc": 3000000, "leg_min_bc": 750000, "bonus": "100000.00"},
        {"level": 10, "total_bc": 7500000, "leg_min_bc": 1500000, "bonus": "250000.00"},
        {"level": 11, "total_bc": 20000000, "leg_min_bc": 4000000, "bonus": "550000.00"},
    ],
    "required_legs": 3,
    # BC bonus is paid on this day of the month after the reference month.
    "career_bonus_pay_day": 15,
    # 13 commission positions each, position 1 = direct seller (spec §6.2, §7.3).
    "bm_rates": ["1.00", "0.65", "0.45", "0.40", "0.35", "0.25", "0.20", "0.15", "0.15", "0.15", "0.15", "0.05", "0.05"],
    "bd_rates": ["18.00", "7.00", "5.00", "4.00", "3.00", "2.00", "1.00", "0.50", "0.50", "0.25", "0.25", "0.25", "0.25"],
    "promotions": {
        # One free licence every six paid subscription months.
        "gift_license_every_paid_months": 6,
        # Launch event: BCT target in the named month qualifies as guest.
        "rome_launch_event": {"period": "2026-11", "target_bc": 6000},
    },
}

EXPECTED_LEVELS = 11
EXPECTED_POSITIONS = 13
EXPECTED_BM_TOTAL = Decimal("4.00")
EXPECTED_BD_TOTAL = Decimal("42.00")


class PlanValidationError(ValueError):
    pass


def validate_plan(config: dict[str, Any]) -> None:
    """Refuses a plan that breaks the invariants fixed by the specification
    (checklist §14): exactly 11 levels, 13 BM rates totalling 4% and 13 BD
    rates totalling 42%. A plan that changes those numbers is a new
    specification, not a new version."""
    levels = config.get("career_levels") or []
    if len(levels) != EXPECTED_LEVELS:
        raise PlanValidationError(f"Il piano deve avere esattamente {EXPECTED_LEVELS} livelli di carriera.")
    if [lv["level"] for lv in levels] != list(range(1, EXPECTED_LEVELS + 1)):
        raise PlanValidationError("I livelli di carriera devono essere numerati da 1 a 11, in ordine.")
    for prev, cur in zip(levels, levels[1:]):
        if cur["total_bc"] <= prev["total_bc"]:
            raise PlanValidationError("Il volume richiesto deve crescere a ogni livello.")
    for key, total, label in (("bm_rates", EXPECTED_BM_TOTAL, "BM"), ("bd_rates", EXPECTED_BD_TOTAL, "BD")):
        rates = [Decimal(r) for r in config.get(key) or []]
        if len(rates) != EXPECTED_POSITIONS:
            raise PlanValidationError(f"Le aliquote {label} devono essere esattamente {EXPECTED_POSITIONS}.")
        if sum(rates) != total:
            raise PlanValidationError(f"Le aliquote {label} devono sommare {total}%, non {sum(rates)}%.")
    if int(config.get("required_legs", 0)) < 1:
        raise PlanValidationError("Il numero di gambe richieste deve essere almeno 1.")


def product_index(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Every purchasable code in the plan, with the operation kind it maps to."""
    index: dict[str, dict[str, Any]] = {}
    sub = config["subscription"]
    index[sub["code"]] = {**sub, "kind": "SUBSCRIPTION_PAYMENT"}
    for p in config["license_products"]:
        index[p["code"]] = {**p, "kind": "LICENSE_PURCHASE"}
    for p in config["event_ticket_products"]:
        index[p["code"]] = {**p, "kind": "EVENT_TICKET_PURCHASE"}
    for p in config["packs"]:
        index[p["code"]] = {**p, "kind": "PACK_SALE"}
    return index
