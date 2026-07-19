"""Team ELO ratings with home-field advantage and margin-of-victory scaling."""
from __future__ import annotations

import math
from dataclasses import dataclass

HOME_ADVANTAGE = 24.0
K_FACTOR = 4.0  # MLB games are high-variance; small K keeps ratings stable
SEASON_REGRESSION = 0.33  # regress toward 1500 between seasons


@dataclass
class EloSystem:
    home_advantage: float = HOME_ADVANTAGE
    k: float = K_FACTOR

    def expected_home_win(self, home_elo: float, away_elo: float) -> float:
        diff = home_elo + self.home_advantage - away_elo
        return 1.0 / (1.0 + math.pow(10.0, -diff / 400.0))

    def update(self, home_elo: float, away_elo: float, home_score: int, away_score: int) -> tuple[float, float]:
        expected = self.expected_home_win(home_elo, away_elo)
        actual = 1.0 if home_score > away_score else 0.0 if home_score < away_score else 0.5
        margin = abs(home_score - away_score)
        mov_mult = math.log(max(margin, 1) + 1) * 1.2
        delta = self.k * mov_mult * (actual - expected)
        return home_elo + delta, away_elo - delta

    @staticmethod
    def season_reset(elo: float) -> float:
        return elo + (1500.0 - elo) * SEASON_REGRESSION
