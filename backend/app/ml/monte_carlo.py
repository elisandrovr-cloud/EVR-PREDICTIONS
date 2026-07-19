"""Monte Carlo game simulator.

Simulates a full game inning-by-inning from each side's expected runs/inning,
adjusted for starter quality, bullpen, park, weather and umpire. Produces joint
distributions for moneyline, run line, totals and first-inning markets from the
same simulated sample, so correlated markets stay internally consistent.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

LEAGUE_RUNS_PER_INNING = 4.55 / 9.0


@dataclass
class TeamSimInput:
    expected_runs_per_inning: float
    starter_innings: float = 5.3  # expected starter workload
    starter_run_suppression: float = 1.0  # <1 = better than average starter
    bullpen_run_suppression: float = 1.0


@dataclass
class SimResult:
    home_win: float
    away_win: float
    home_runline_minus_1_5: float
    away_runline_plus_1_5: float
    over_probs: dict[float, float] = field(default_factory=dict)
    under_probs: dict[float, float] = field(default_factory=dict)
    first_inning_run: float = 0.0
    home_scores_first: float = 0.0
    mean_total: float = 0.0
    mean_home: float = 0.0
    mean_away: float = 0.0


class MonteCarloSimulator:
    def __init__(self, iterations: int = 10_000, seed: int | None = None) -> None:
        self.iterations = iterations
        self.rng = np.random.default_rng(seed)

    def _innings_runs(self, team: TeamSimInput, n_sims: int) -> np.ndarray:
        """9-inning run matrix. Starter covers early innings, bullpen the rest."""
        base = max(team.expected_runs_per_inning, 0.05)
        innings = np.arange(1, 10)
        starter_mask = innings <= round(team.starter_innings)
        lam = np.where(starter_mask, base * team.starter_run_suppression, base * team.bullpen_run_suppression)
        # Negative-binomial-ish overdispersion via gamma-poisson mixture
        shape = 1.6
        lam_matrix = self.rng.gamma(shape, np.maximum(lam, 1e-4) / shape, size=(n_sims, 9))
        return self.rng.poisson(lam_matrix)

    def simulate(self, home: TeamSimInput, away: TeamSimInput, total_lines: list[float] | None = None) -> SimResult:
        n = self.iterations
        home_by_inning = self._innings_runs(home, n)
        away_by_inning = self._innings_runs(away, n)
        home_runs = home_by_inning.sum(axis=1)
        away_runs = away_by_inning.sum(axis=1)

        # extra innings: break ties with single-inning shootouts
        ties = home_runs == away_runs
        if ties.any():
            n_ties = int(ties.sum())
            tie_break = self.rng.random(n_ties) < 0.52  # home edge in extras
            home_runs = home_runs.astype(float)
            away_runs = away_runs.astype(float)
            home_runs[ties] += np.where(tie_break, 1.0, 0.0)
            away_runs[ties] += np.where(~tie_break, 1.0, 0.0)

        total = home_runs + away_runs
        margin = home_runs - away_runs
        lines = total_lines or [7.0, 7.5, 8.0, 8.5, 9.0, 9.5, 10.0]

        return SimResult(
            home_win=float((margin > 0).mean()),
            away_win=float((margin < 0).mean()),
            home_runline_minus_1_5=float((margin >= 2).mean()),
            away_runline_plus_1_5=float((margin >= 2).mean() * -1 + 1),
            over_probs={line: float((total > line).mean()) for line in lines},
            under_probs={line: float((total < line).mean()) for line in lines},
            first_inning_run=float(((home_by_inning[:, 0] + away_by_inning[:, 0]) > 0).mean()),
            home_scores_first=float((home_by_inning[:, 0] > 0).mean()),
            mean_total=float(total.mean()),
            mean_home=float(home_runs.mean()),
            mean_away=float(away_runs.mean()),
        )
