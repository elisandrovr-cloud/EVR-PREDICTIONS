"""Domain value objects: odds math, EV, Kelly, risk."""
from __future__ import annotations

import pytest

from app.domain.entities import Edge, Market, Odds, PredictionCandidate, RiskLevel


class TestOdds:
    def test_positive_american_to_decimal(self) -> None:
        assert Odds(american=150).decimal == pytest.approx(2.5)

    def test_negative_american_to_decimal(self) -> None:
        assert Odds(american=-200).decimal == pytest.approx(1.5)

    def test_implied_probability_positive(self) -> None:
        assert Odds(american=100).implied_probability == pytest.approx(0.5)

    def test_implied_probability_negative(self) -> None:
        assert Odds(american=-150).implied_probability == pytest.approx(0.6)

    def test_from_probability_roundtrip(self) -> None:
        for p in (0.25, 0.5, 0.66, 0.9):
            odds = Odds.from_probability(p)
            assert odds.implied_probability == pytest.approx(p, abs=0.01)

    def test_from_probability_favorite_is_negative(self) -> None:
        assert Odds.from_probability(0.7).american < 0

    def test_from_probability_underdog_is_positive(self) -> None:
        assert Odds.from_probability(0.3).american > 0


class TestEdge:
    def test_positive_ev_when_model_beats_market(self) -> None:
        edge = Edge(model_probability=0.60, market_odds=Odds(american=100))
        assert edge.expected_value == pytest.approx(0.2)
        assert edge.edge == pytest.approx(0.1)

    def test_negative_ev_when_market_beats_model(self) -> None:
        edge = Edge(model_probability=0.45, market_odds=Odds(american=-120))
        assert edge.expected_value < 0

    def test_kelly_zero_for_negative_edge(self) -> None:
        edge = Edge(model_probability=0.40, market_odds=Odds(american=-110))
        assert edge.kelly_stake() == 0.0

    def test_kelly_positive_and_fractional(self) -> None:
        edge = Edge(model_probability=0.60, market_odds=Odds(american=100))
        full_kelly = 0.2  # (1*0.6 - 0.4) / 1
        assert edge.kelly_stake(fraction=0.25) == pytest.approx(full_kelly * 0.25)


class TestPredictionCandidate:
    def _candidate(self, prob: float) -> PredictionCandidate:
        return PredictionCandidate(
            game_pk=1, market=Market.MONEYLINE, selection="Yankees",
            probability=prob, confidence=0.7, explanation="test",
        )

    def test_risk_bands(self) -> None:
        assert self._candidate(0.70).risk == RiskLevel.LOW
        assert self._candidate(0.55).risk == RiskLevel.MEDIUM
        assert self._candidate(0.35).risk == RiskLevel.HIGH
        assert self._candidate(0.10).risk == RiskLevel.EXTREME

    def test_fair_odds_sign(self) -> None:
        assert self._candidate(0.7).fair_odds < 0
        assert self._candidate(0.3).fair_odds > 0

    def test_economics_requires_book_odds(self) -> None:
        c = self._candidate(0.6)
        assert c.economics() is None
        c.book_odds = 110
        econ = c.economics()
        assert econ is not None and econ.expected_value > 0
