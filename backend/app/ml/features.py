"""Feature engineering: turns raw game/player context into model vectors.

All features are computed from what is stored in the DB (fed by the ingestion
workers) so the engine is deterministic given a snapshot.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

LEAGUE = {
    "era": 4.10, "fip": 4.10, "whip": 1.28, "k_pct": 0.222, "bb_pct": 0.082,
    "avg": 0.244, "obp": 0.315, "slg": 0.400, "ops": 0.715, "iso": 0.156,
    "babip": 0.291, "hr_per_pa": 0.031, "hit_per_pa": 0.218, "rbi_per_pa": 0.115,
    "run_per_pa": 0.12, "sb_per_game": 0.07, "runs_per_game": 4.55,
    "k_per_9": 8.6, "bb_per_9": 3.2, "hits_per_9": 8.2, "hr_per_9": 1.15,
}

GAME_FEATURES = [
    "home_elo", "away_elo", "elo_diff",
    "home_sp_era", "away_sp_era", "home_sp_fip", "away_sp_fip",
    "home_sp_k_pct", "away_sp_k_pct", "home_sp_bb_pct", "away_sp_bb_pct",
    "home_sp_whip", "away_sp_whip",
    "home_bullpen_era", "away_bullpen_era", "home_bullpen_fatigue", "away_bullpen_fatigue",
    "home_off_ops", "away_off_ops", "home_off_runs_pg", "away_off_runs_pg",
    "park_runs_factor", "park_hr_factor",
    "weather_runs_mult", "weather_hr_mult",
    "umpire_zone", "umpire_runs_delta",
    "home_form_l10", "away_form_l10",
    "lineup_confirmed",
]


def _f(d: dict[str, Any] | None, key: str, default: float) -> float:
    if not d:
        return default
    v = d.get(key)
    try:
        return float(v) if v is not None else default
    except (TypeError, ValueError):
        return default


@dataclass
class GameContext:
    """Denormalized snapshot the ingestion layer assembles for one game."""

    game_pk: int
    home_team: str
    away_team: str
    home_elo: float = 1500.0
    away_elo: float = 1500.0
    home_sp: dict[str, Any] | None = None
    away_sp: dict[str, Any] | None = None
    home_bullpen: dict[str, Any] | None = None
    away_bullpen: dict[str, Any] | None = None
    home_offense: dict[str, Any] | None = None
    away_offense: dict[str, Any] | None = None
    park: dict[str, Any] | None = None
    weather: dict[str, Any] | None = None
    umpire: dict[str, Any] | None = None
    home_form_l10: float = 0.5
    away_form_l10: float = 0.5
    lineup_confirmed: bool = False


def build_game_features(ctx: GameContext) -> dict[str, float]:
    impact = (ctx.weather or {}).get("impact", {}) if ctx.weather else {}
    feats = {
        "home_elo": ctx.home_elo,
        "away_elo": ctx.away_elo,
        "elo_diff": ctx.home_elo - ctx.away_elo,
        "home_sp_era": _f(ctx.home_sp, "era", LEAGUE["era"]),
        "away_sp_era": _f(ctx.away_sp, "era", LEAGUE["era"]),
        "home_sp_fip": _f(ctx.home_sp, "fip", LEAGUE["fip"]),
        "away_sp_fip": _f(ctx.away_sp, "fip", LEAGUE["fip"]),
        "home_sp_k_pct": _f(ctx.home_sp, "k_pct", LEAGUE["k_pct"]),
        "away_sp_k_pct": _f(ctx.away_sp, "k_pct", LEAGUE["k_pct"]),
        "home_sp_bb_pct": _f(ctx.home_sp, "bb_pct", LEAGUE["bb_pct"]),
        "away_sp_bb_pct": _f(ctx.away_sp, "bb_pct", LEAGUE["bb_pct"]),
        "home_sp_whip": _f(ctx.home_sp, "whip", LEAGUE["whip"]),
        "away_sp_whip": _f(ctx.away_sp, "whip", LEAGUE["whip"]),
        "home_bullpen_era": _f(ctx.home_bullpen, "era", LEAGUE["era"]),
        "away_bullpen_era": _f(ctx.away_bullpen, "era", LEAGUE["era"]),
        "home_bullpen_fatigue": _f(ctx.home_bullpen, "fatigue", 0.0),
        "away_bullpen_fatigue": _f(ctx.away_bullpen, "fatigue", 0.0),
        "home_off_ops": _f(ctx.home_offense, "ops", LEAGUE["ops"]),
        "away_off_ops": _f(ctx.away_offense, "ops", LEAGUE["ops"]),
        "home_off_runs_pg": _f(ctx.home_offense, "runs_per_game", LEAGUE["runs_per_game"]),
        "away_off_runs_pg": _f(ctx.away_offense, "runs_per_game", LEAGUE["runs_per_game"]),
        "park_runs_factor": _f(ctx.park, "runs", 100.0) / 100.0,
        "park_hr_factor": _f(ctx.park, "hr", 100.0) / 100.0,
        "weather_runs_mult": float(impact.get("runs_multiplier", 1.0)),
        "weather_hr_mult": float(impact.get("hr_multiplier", 1.0)),
        "umpire_zone": _f(ctx.umpire, "zone", 1.0),
        "umpire_runs_delta": _f(ctx.umpire, "runs_delta", 0.0),
        "home_form_l10": ctx.home_form_l10,
        "away_form_l10": ctx.away_form_l10,
        "lineup_confirmed": 1.0 if ctx.lineup_confirmed else 0.0,
    }
    return feats


def features_to_vector(feats: dict[str, float]) -> np.ndarray:
    return np.array([feats.get(name, 0.0) for name in GAME_FEATURES], dtype=float)


def expected_runs_per_inning(
    offense_runs_pg: float,
    opp_sp_era: float,
    opp_bullpen_era: float,
    park_runs_factor: float,
    weather_runs_mult: float,
    umpire_runs_delta: float,
) -> float:
    """Blend of offense scoring rate vs opposing pitching quality, park/weather/ump adjusted."""
    pitching_blend = 0.65 * opp_sp_era + 0.35 * opp_bullpen_era
    pitching_mult = pitching_blend / LEAGUE["era"]
    base = (offense_runs_pg / 9.0) * 0.55 + (LEAGUE["runs_per_game"] / 9.0) * pitching_mult * 0.45
    adjusted = base * park_runs_factor * weather_runs_mult + umpire_runs_delta / 18.0
    return max(0.08, adjusted)
