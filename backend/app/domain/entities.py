"""Domain entities and value objects (framework-free core of the hexagon)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class Market(StrEnum):
    MONEYLINE = "moneyline"
    RUN_LINE = "run_line"
    TOTAL_OVER = "total_over"
    TOTAL_UNDER = "total_under"
    FIRST_INNING = "first_inning"
    PLAYER_HITS = "player_hits"
    PLAYER_HOME_RUNS = "player_home_runs"
    PLAYER_RBI = "player_rbi"
    PLAYER_TOTAL_BASES = "player_total_bases"
    PLAYER_STOLEN_BASES = "player_stolen_bases"
    PLAYER_RUNS = "player_runs"
    PLAYER_WALKS = "player_walks"
    PITCHER_STRIKEOUTS = "pitcher_strikeouts"
    PITCHER_WALKS = "pitcher_walks"
    PITCHER_OUTS = "pitcher_outs"
    PITCHER_HITS_ALLOWED = "pitcher_hits_allowed"
    PITCHER_EARNED_RUNS = "pitcher_earned_runs"
    PITCHER_WIN = "pitcher_win"
    QUALITY_START = "quality_start"
    NO_HITTER = "no_hitter"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    EXTREME = "extreme"


class ParlayProfile(StrEnum):
    CONSERVATIVE = "conservative"
    BALANCED = "balanced"
    AGGRESSIVE = "aggressive"
    SAME_GAME = "same_game"
    HIGH_ODDS = "high_odds"
    AI_PREMIUM = "ai_premium"


@dataclass(frozen=True)
class Odds:
    """American odds value object with conversion helpers."""

    american: float

    @property
    def decimal(self) -> float:
        a = self.american
        return 1 + (a / 100 if a > 0 else 100 / abs(a))

    @property
    def implied_probability(self) -> float:
        a = self.american
        return 100 / (a + 100) if a > 0 else abs(a) / (abs(a) + 100)

    @staticmethod
    def from_probability(p: float) -> "Odds":
        p = min(max(p, 1e-6), 1 - 1e-6)
        if p >= 0.5:
            return Odds(american=round(-100 * p / (1 - p)))
        return Odds(american=round(100 * (1 - p) / p))


@dataclass(frozen=True)
class Edge:
    """Value-bet economics for a selection."""

    model_probability: float
    market_odds: Odds

    @property
    def expected_value(self) -> float:
        """EV per 1 unit staked."""
        d = self.market_odds.decimal
        return self.model_probability * (d - 1) - (1 - self.model_probability)

    @property
    def edge(self) -> float:
        return self.model_probability - self.market_odds.implied_probability

    def kelly_stake(self, fraction: float = 0.25) -> float:
        b = self.market_odds.decimal - 1
        if b <= 0:
            return 0.0
        q = 1 - self.model_probability
        kelly = (b * self.model_probability - q) / b
        return max(0.0, kelly * fraction)


@dataclass
class PredictionCandidate:
    """A single market selection produced by the engine before persistence."""

    game_pk: int
    market: Market
    selection: str
    probability: float
    confidence: float
    explanation: str
    player_id: int | None = None
    line: float | None = None
    book_odds: float | None = None
    model_breakdown: dict[str, float] = field(default_factory=dict)
    created_at: datetime | None = None

    @property
    def fair_odds(self) -> float:
        return Odds.from_probability(self.probability).american

    def economics(self) -> Edge | None:
        if self.book_odds is None:
            return None
        return Edge(model_probability=self.probability, market_odds=Odds(american=self.book_odds))

    @property
    def risk(self) -> RiskLevel:
        if self.probability >= 0.65:
            return RiskLevel.LOW
        if self.probability >= 0.5:
            return RiskLevel.MEDIUM
        if self.probability >= 0.3:
            return RiskLevel.HIGH
        return RiskLevel.EXTREME
