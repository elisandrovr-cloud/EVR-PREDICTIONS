"""Curated reference datasets: park factors and umpire tendencies.

Seeded from public multi-year data (Baseball Savant park factors, Umpire Scorecards).
Values refresh from live sources when those adapters succeed; these are the durable
fallback so the engine never runs blind.
"""
from __future__ import annotations

from typing import Any

# index 100 = league average. runs/hr/2b/3b factors + physical traits.
PARK_FACTORS: dict[str, dict[str, Any]] = {
    "Coors Field": {"runs": 112, "hr": 111, "doubles": 116, "triples": 133, "foul_territory": "large", "altitude_ft": 5190},
    "Fenway Park": {"runs": 104, "hr": 96, "doubles": 126, "triples": 103, "foul_territory": "small", "altitude_ft": 20},
    "Great American Ball Park": {"runs": 103, "hr": 114, "doubles": 97, "triples": 95, "foul_territory": "small", "altitude_ft": 550},
    "Yankee Stadium": {"runs": 101, "hr": 110, "doubles": 95, "triples": 87, "foul_territory": "small", "altitude_ft": 55},
    "Citizens Bank Park": {"runs": 101, "hr": 108, "doubles": 97, "triples": 94, "foul_territory": "small", "altitude_ft": 20},
    "Truist Park": {"runs": 101, "hr": 104, "doubles": 99, "triples": 92, "foul_territory": "average", "altitude_ft": 1050},
    "Chase Field": {"runs": 102, "hr": 101, "doubles": 108, "triples": 118, "foul_territory": "average", "altitude_ft": 1086},
    "Kauffman Stadium": {"runs": 102, "hr": 92, "doubles": 106, "triples": 121, "foul_territory": "large", "altitude_ft": 750},
    "Wrigley Field": {"runs": 100, "hr": 102, "doubles": 96, "triples": 95, "foul_territory": "small", "altitude_ft": 600},
    "Dodger Stadium": {"runs": 99, "hr": 106, "doubles": 94, "triples": 82, "foul_territory": "average", "altitude_ft": 512},
    "Angel Stadium": {"runs": 99, "hr": 103, "doubles": 95, "triples": 89, "foul_territory": "average", "altitude_ft": 160},
    "Rogers Centre": {"runs": 100, "hr": 103, "doubles": 99, "triples": 90, "foul_territory": "average", "altitude_ft": 250},
    "Globe Life Field": {"runs": 99, "hr": 101, "doubles": 97, "triples": 95, "foul_territory": "average", "altitude_ft": 545},
    "Minute Maid Park": {"runs": 99, "hr": 103, "doubles": 96, "triples": 92, "foul_territory": "small", "altitude_ft": 50},
    "Daikin Park": {"runs": 99, "hr": 103, "doubles": 96, "triples": 92, "foul_territory": "small", "altitude_ft": 50},
    "Nationals Park": {"runs": 100, "hr": 101, "doubles": 98, "triples": 92, "foul_territory": "average", "altitude_ft": 25},
    "Target Field": {"runs": 99, "hr": 99, "doubles": 101, "triples": 100, "foul_territory": "average", "altitude_ft": 815},
    "Busch Stadium": {"runs": 98, "hr": 93, "doubles": 99, "triples": 92, "foul_territory": "average", "altitude_ft": 465},
    "American Family Field": {"runs": 100, "hr": 107, "doubles": 95, "triples": 92, "foul_territory": "average", "altitude_ft": 635},
    "PNC Park": {"runs": 98, "hr": 91, "doubles": 102, "triples": 106, "foul_territory": "average", "altitude_ft": 730},
    "Progressive Field": {"runs": 99, "hr": 99, "doubles": 100, "triples": 92, "foul_territory": "small", "altitude_ft": 650},
    "Comerica Park": {"runs": 98, "hr": 94, "doubles": 99, "triples": 116, "foul_territory": "large", "altitude_ft": 585},
    "Guaranteed Rate Field": {"runs": 100, "hr": 106, "doubles": 95, "triples": 89, "foul_territory": "average", "altitude_ft": 595},
    "Rate Field": {"runs": 100, "hr": 106, "doubles": 95, "triples": 89, "foul_territory": "average", "altitude_ft": 595},
    "Oriole Park at Camden Yards": {"runs": 99, "hr": 102, "doubles": 97, "triples": 88, "foul_territory": "small", "altitude_ft": 20},
    "Citi Field": {"runs": 97, "hr": 101, "doubles": 95, "triples": 88, "foul_territory": "average", "altitude_ft": 10},
    "loanDepot park": {"runs": 97, "hr": 95, "doubles": 99, "triples": 104, "foul_territory": "average", "altitude_ft": 8},
    "Petco Park": {"runs": 96, "hr": 98, "doubles": 94, "triples": 96, "foul_territory": "average", "altitude_ft": 15},
    "Oracle Park": {"runs": 95, "hr": 88, "doubles": 98, "triples": 128, "foul_territory": "large", "altitude_ft": 10},
    "T-Mobile Park": {"runs": 94, "hr": 96, "doubles": 93, "triples": 90, "foul_territory": "average", "altitude_ft": 15},
    "Tropicana Field": {"runs": 96, "hr": 96, "doubles": 96, "triples": 99, "foul_territory": "large", "altitude_ft": 45},
    "Kaseya Center": {"runs": 100, "hr": 100, "doubles": 100, "triples": 100, "foul_territory": "average", "altitude_ft": 10},
    "Sutter Health Park": {"runs": 103, "hr": 105, "doubles": 102, "triples": 100, "foul_territory": "small", "altitude_ft": 20},
    "George M. Steinbrenner Field": {"runs": 103, "hr": 108, "doubles": 98, "triples": 92, "foul_territory": "small", "altitude_ft": 40},
}

DEFAULT_PARK = {"runs": 100, "hr": 100, "doubles": 100, "triples": 100, "foul_territory": "average", "altitude_ft": 300}

# Umpire tendencies: expected strike-zone size vs league, over rate, K/BB deltas.
# zone: >1 = bigger zone (pitcher friendly). Seeded from Umpire Scorecards aggregates.
UMPIRE_TENDENCIES: dict[str, dict[str, float]] = {
    "Pat Hoberg": {"zone": 1.00, "over_rate": 0.50, "k_delta": 0.00, "bb_delta": 0.00, "runs_delta": 0.0},
    "Dan Iassogna": {"zone": 1.04, "over_rate": 0.46, "k_delta": 0.04, "bb_delta": -0.03, "runs_delta": -0.25},
    "Laz Diaz": {"zone": 1.03, "over_rate": 0.47, "k_delta": 0.03, "bb_delta": -0.02, "runs_delta": -0.2},
    "Angel Hernandez": {"zone": 0.97, "over_rate": 0.53, "k_delta": -0.03, "bb_delta": 0.04, "runs_delta": 0.3},
    "CB Bucknor": {"zone": 0.98, "over_rate": 0.52, "k_delta": -0.02, "bb_delta": 0.03, "runs_delta": 0.2},
    "Doug Eddings": {"zone": 1.05, "over_rate": 0.45, "k_delta": 0.05, "bb_delta": -0.03, "runs_delta": -0.3},
    "Ron Kulpa": {"zone": 1.01, "over_rate": 0.49, "k_delta": 0.01, "bb_delta": -0.01, "runs_delta": -0.05},
    "Mark Carlson": {"zone": 1.02, "over_rate": 0.48, "k_delta": 0.02, "bb_delta": -0.01, "runs_delta": -0.1},
    "Tripp Gibson": {"zone": 1.00, "over_rate": 0.50, "k_delta": 0.0, "bb_delta": 0.0, "runs_delta": 0.0},
    "Adam Hamari": {"zone": 1.03, "over_rate": 0.46, "k_delta": 0.03, "bb_delta": -0.02, "runs_delta": -0.2},
    "Ben May": {"zone": 0.99, "over_rate": 0.51, "k_delta": -0.01, "bb_delta": 0.01, "runs_delta": 0.1},
    "Nic Lentz": {"zone": 0.98, "over_rate": 0.52, "k_delta": -0.02, "bb_delta": 0.02, "runs_delta": 0.15},
}

DEFAULT_UMPIRE = {"zone": 1.0, "over_rate": 0.5, "k_delta": 0.0, "bb_delta": 0.0, "runs_delta": 0.0}


def park_factor(venue_name: str | None) -> dict[str, Any]:
    return PARK_FACTORS.get(venue_name or "", DEFAULT_PARK)


def umpire_tendency(name: str | None) -> dict[str, float]:
    return UMPIRE_TENDENCIES.get(name or "", DEFAULT_UMPIRE)
