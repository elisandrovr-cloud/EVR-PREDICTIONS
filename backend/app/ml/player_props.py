"""Analytic player-prop probability models.

Per-PA event rates (shrunk toward league priors via beta-binomial) are adjusted
for the opposing starter, park, weather and umpire, then rolled into binomial /
Poisson distributions over expected plate appearances or batters faced. These
serve both as standalone probabilities and as the `monte_carlo` member vote for
prop markets in the ensemble.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from app.ml.bayesian import beta_shrink
from app.ml.features import LEAGUE


def _pf(stats: dict[str, Any] | None, key: str, default: float) -> float:
    if not stats:
        return default
    try:
        v = stats.get(key)
        return float(v) if v is not None else default
    except (TypeError, ValueError):
        return default


def poisson_at_least(lam: float, k: int) -> float:
    """P(X >= k) for Poisson(lam)."""
    lam = max(lam, 1e-6)
    cdf = 0.0
    term = math.exp(-lam)
    for i in range(k):
        cdf += term
        term *= lam / (i + 1)
    return max(0.0, min(1.0, 1 - cdf))


def binomial_at_least(n: int, p: float, k: int) -> float:
    p = min(max(p, 1e-6), 1 - 1e-6)
    prob = 0.0
    for i in range(k, n + 1):
        prob += math.comb(n, i) * p**i * (1 - p) ** (n - i)
    return max(0.0, min(1.0, prob))


@dataclass
class BatterMatchup:
    batter: dict[str, Any]  # season/rolling rates per PA
    opp_pitcher: dict[str, Any] | None
    park: dict[str, Any] | None
    weather_impact: dict[str, Any] | None
    umpire: dict[str, Any] | None
    lineup_slot: int = 5

    @property
    def expected_pa(self) -> float:
        return max(3.0, 4.9 - (self.lineup_slot - 1) * 0.12)

    def _pitcher_mult(self, batter_key: str, pitcher_key: str, league_rate: float) -> float:
        """How much the opposing pitcher inflates/deflates a per-PA event rate."""
        pitcher_rate = _pf(self.opp_pitcher, pitcher_key, league_rate)
        return pitcher_rate / league_rate if league_rate > 0 else 1.0

    def rate(self, event: str) -> float:
        """Adjusted per-PA probability of a batter event."""
        pa_seen = _pf(self.batter, "pa", 200.0)
        if event == "hit":
            raw = _pf(self.batter, "hit_per_pa", LEAGUE["hit_per_pa"])
            base = beta_shrink(raw, pa_seen, LEAGUE["hit_per_pa"])
            mult = self._pitcher_mult("hit_per_pa", "hits_allowed_per_pa", LEAGUE["hit_per_pa"])
            park = _pf(self.park, "runs", 100.0) / 100.0
            return base * (0.7 + 0.3 * mult) * (0.9 + 0.1 * park)
        if event == "hr":
            raw = _pf(self.batter, "hr_per_pa", LEAGUE["hr_per_pa"])
            base = beta_shrink(raw, pa_seen, LEAGUE["hr_per_pa"], prior_strength=120.0)
            mult = self._pitcher_mult("hr_per_pa", "hr_allowed_per_pa", LEAGUE["hr_per_pa"])
            park = _pf(self.park, "hr", 100.0) / 100.0
            wx = float((self.weather_impact or {}).get("hr_multiplier", 1.0))
            return base * (0.7 + 0.3 * mult) * (0.75 + 0.25 * park) * wx
        if event == "bb":
            raw = _pf(self.batter, "bb_per_pa", LEAGUE["bb_pct"])
            base = beta_shrink(raw, pa_seen, LEAGUE["bb_pct"])
            zone = _pf(self.umpire, "zone", 1.0)
            pitcher_bb = _pf(self.opp_pitcher, "bb_pct", LEAGUE["bb_pct"]) / LEAGUE["bb_pct"]
            return base * (0.7 + 0.3 * pitcher_bb) * (2.0 - zone)
        if event == "so":
            raw = _pf(self.batter, "k_per_pa", LEAGUE["k_pct"])
            base = beta_shrink(raw, pa_seen, LEAGUE["k_pct"])
            pitcher_k = _pf(self.opp_pitcher, "k_pct", LEAGUE["k_pct"]) / LEAGUE["k_pct"]
            zone = _pf(self.umpire, "zone", 1.0)
            return base * (0.6 + 0.4 * pitcher_k) * zone
        if event == "rbi":
            raw = _pf(self.batter, "rbi_per_pa", LEAGUE["rbi_per_pa"])
            return beta_shrink(raw, pa_seen, LEAGUE["rbi_per_pa"])
        if event == "run":
            raw = _pf(self.batter, "run_per_pa", LEAGUE["run_per_pa"])
            return beta_shrink(raw, pa_seen, LEAGUE["run_per_pa"])
        raise ValueError(f"unknown batter event {event}")

    # ── market probabilities ────────────────────────────────────────────────
    def hits_at_least(self, k: int) -> float:
        return binomial_at_least(round(self.expected_pa), self.rate("hit"), k)

    def home_run(self) -> float:
        return binomial_at_least(round(self.expected_pa), self.rate("hr"), 1)

    def rbi_at_least(self, k: int = 1) -> float:
        return poisson_at_least(self.rate("rbi") * self.expected_pa, k)

    def run_scored(self) -> float:
        return poisson_at_least(self.rate("run") * self.expected_pa, 1)

    def walk(self) -> float:
        return binomial_at_least(round(self.expected_pa), self.rate("bb"), 1)

    def strikeout(self) -> float:
        return binomial_at_least(round(self.expected_pa), self.rate("so"), 1)

    def total_bases_at_least(self, line: float) -> float:
        """Expected TB from hit mix; Poisson over the PA horizon."""
        hit_rate = self.rate("hit")
        iso = _pf(self.batter, "iso", LEAGUE["iso"])
        # slugging per hit approx: 1 + ISO/AVG spread across hit types
        avg = max(_pf(self.batter, "avg", LEAGUE["avg"]), 0.1)
        tb_per_hit = 1.0 + min(iso / avg, 1.2)
        lam = hit_rate * self.expected_pa * tb_per_hit
        return poisson_at_least(lam, math.ceil(line))

    def stolen_base(self) -> float:
        sb_rate = _pf(self.batter, "sb_per_game", LEAGUE["sb_per_game"])
        sprint = _pf(self.batter, "sprint_speed", 27.0)
        speed_mult = 1.0 + (sprint - 27.0) * 0.12
        return poisson_at_least(max(sb_rate * speed_mult, 1e-4), 1)

    def double(self) -> float:
        doubles_rate = _pf(self.batter, "double_per_pa", 0.045)
        park = _pf(self.park, "doubles", 100.0) / 100.0
        return poisson_at_least(doubles_rate * self.expected_pa * (0.8 + 0.2 * park), 1)

    def triple(self) -> float:
        triples_rate = _pf(self.batter, "triple_per_pa", 0.004)
        park = _pf(self.park, "triples", 100.0) / 100.0
        return poisson_at_least(triples_rate * self.expected_pa * (0.7 + 0.3 * park), 1)


@dataclass
class PitcherMatchup:
    pitcher: dict[str, Any]
    opp_offense: dict[str, Any] | None
    park: dict[str, Any] | None
    umpire: dict[str, Any] | None
    team_win_prob: float = 0.5

    @property
    def expected_innings(self) -> float:
        ip = _pf(self.pitcher, "innings_per_start", 5.3)
        pitch_ct = _pf(self.pitcher, "avg_pitch_count", 92.0)
        fatigue = _pf(self.pitcher, "fatigue", 0.0)  # 0..1
        return max(3.0, min(7.5, ip * (1 - 0.25 * fatigue) * (pitch_ct / 92.0)))

    def strikeouts_at_least(self, line: float) -> float:
        k9 = _pf(self.pitcher, "k_per_9", LEAGUE["k_per_9"])
        opp_k_mult = _pf(self.opp_offense, "k_pct", LEAGUE["k_pct"]) / LEAGUE["k_pct"]
        zone = _pf(self.umpire, "zone", 1.0)
        lam = k9 / 9.0 * self.expected_innings * (0.7 + 0.3 * opp_k_mult) * zone
        return poisson_at_least(lam, math.ceil(line))

    def walks_at_least(self, line: float) -> float:
        bb9 = _pf(self.pitcher, "bb_per_9", LEAGUE["bb_per_9"])
        zone = _pf(self.umpire, "zone", 1.0)
        lam = bb9 / 9.0 * self.expected_innings * (2.0 - zone)
        return poisson_at_least(lam, math.ceil(line))

    def hits_allowed_at_least(self, line: float) -> float:
        h9 = _pf(self.pitcher, "hits_per_9", LEAGUE["hits_per_9"])
        opp_mult = _pf(self.opp_offense, "avg", LEAGUE["avg"]) / LEAGUE["avg"]
        lam = h9 / 9.0 * self.expected_innings * (0.7 + 0.3 * opp_mult)
        return poisson_at_least(lam, math.ceil(line))

    def earned_runs_at_least(self, line: float) -> float:
        era = _pf(self.pitcher, "era", LEAGUE["era"])
        park = _pf(self.park, "runs", 100.0) / 100.0
        lam = era / 9.0 * self.expected_innings * (0.85 + 0.15 * park)
        return poisson_at_least(lam, math.ceil(line))

    def outs_at_least(self, line: float) -> float:
        """Normal approximation over recorded outs."""
        mean_outs = self.expected_innings * 3.0
        sd = 3.4
        z = (line - mean_outs) / sd
        return max(0.0, min(1.0, 1 - _norm_cdf(z)))

    def quality_start(self) -> float:
        p_ip = self.outs_at_least(18)  # 6+ innings
        p_er = 1 - self.earned_runs_at_least(4)  # ≤3 ER
        return max(0.0, min(1.0, p_ip * p_er * 1.12))  # positively correlated

    def win(self) -> float:
        """Pitcher must last 5 and team must win — correlated events."""
        lasts_five = self.outs_at_least(15)
        return max(0.0, min(1.0, self.team_win_prob * lasts_five * 0.82))

    def no_hitter(self) -> float:
        h9 = _pf(self.pitcher, "hits_per_9", LEAGUE["hits_per_9"])
        lam_9 = h9  # expected hits over 9 innings
        return math.exp(-lam_9) * 0.9  # Poisson(0 hits), slight haircut for bullpen eras


def _norm_cdf(z: float) -> float:
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))
