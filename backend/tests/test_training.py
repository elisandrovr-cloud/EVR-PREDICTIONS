"""Learning loop: outcome grading and weight persistence."""
from __future__ import annotations

from datetime import date

from app.domain.entities import Market
from app.infrastructure.db.models import Game, ModelWeight, Prediction, Team
from app.ml.training import (
    load_market_weights,
    recalibrate_from_settled,
    resolve_outcome,
    update_elo_from_finals,
)


def _game(**overrides) -> Game:
    defaults = dict(
        game_pk=7001, game_date=date(2026, 7, 18), status="final",
        home_team_mlb_id=147, away_team_mlb_id=111,
        home_score=6, away_score=3,
        linescore={"innings": [{"home": {"runs": 1}, "away": {"runs": 0}}]},
    )
    defaults.update(overrides)
    return Game(**defaults)


def _pred(**overrides) -> Prediction:
    defaults = dict(
        game_pk=7001, game_date=date(2026, 7, 18), market=Market.MONEYLINE.value,
        selection="New York Yankees", probability=0.6, fair_odds=-150,
        confidence=0.7, features={"_picked_home": True},
    )
    defaults.update(overrides)
    return Prediction(**defaults)


class TestOutcomeResolution:
    def test_moneyline_home_win(self) -> None:
        assert resolve_outcome(_pred(), _game()) == "win"

    def test_moneyline_home_loss(self) -> None:
        assert resolve_outcome(_pred(), _game(home_score=2, away_score=5)) == "loss"

    def test_runline_cover(self) -> None:
        p = _pred(market=Market.RUN_LINE.value, selection="Yankees -1.5", line=-1.5)
        assert resolve_outcome(p, _game(home_score=6, away_score=3)) == "win"
        assert resolve_outcome(p, _game(home_score=4, away_score=3)) == "loss"

    def test_runline_plus_side(self) -> None:
        p = _pred(market=Market.RUN_LINE.value, selection="Red Sox +1.5", line=1.5)
        assert resolve_outcome(p, _game(home_score=4, away_score=3)) == "win"

    def test_total_over_under_and_push(self) -> None:
        over = _pred(market=Market.TOTAL_OVER.value, selection="Over 8.5", line=8.5)
        under = _pred(market=Market.TOTAL_UNDER.value, selection="Under 8.5", line=8.5)
        g = _game(home_score=6, away_score=3)  # total 9
        assert resolve_outcome(over, g) == "win"
        assert resolve_outcome(under, g) == "loss"
        push = _pred(market=Market.TOTAL_OVER.value, selection="Over 9", line=9.0)
        assert resolve_outcome(push, g) == "push"

    def test_first_inning(self) -> None:
        p = _pred(market=Market.FIRST_INNING.value, selection="YRFI", line=0.5)
        assert resolve_outcome(p, _game()) == "win"
        no_run = _game(linescore={"innings": [{"home": {"runs": 0}, "away": {"runs": 0}}]})
        assert resolve_outcome(p, no_run) == "loss"

    def test_ungradeable_without_score(self) -> None:
        assert resolve_outcome(_pred(), _game(home_score=None, away_score=None)) is None

    def test_player_prop_from_stored_results(self) -> None:
        p = _pred(id=42, market=Market.PLAYER_HITS.value, selection="Judge 2+ hits", line=1.5)
        g = _game(linescore={"innings": [], "player_results": {"42": 2.0}})
        assert resolve_outcome(p, g) == "win"
        g_low = _game(linescore={"innings": [], "player_results": {"42": 1.0}})
        assert resolve_outcome(p, g_low) == "loss"


class TestRecalibration:
    def test_weights_persisted_and_favor_better_model(self, db) -> None:
        day = date(2026, 7, 18)
        for i in range(12):
            db.add(_pred(
                id=100 + i, game_pk=7100 + i, settled=True, outcome="win",
                model_breakdown={"monte_carlo": 0.75, "elo": 0.40},
            ))
        db.commit()
        weights = recalibrate_from_settled(db, day)
        ml = weights[Market.MONEYLINE.value]
        assert ml["monte_carlo"] > ml["elo"]
        stored = load_market_weights(db)
        assert Market.MONEYLINE.value in stored
        rows = db.query(ModelWeight).all()
        assert len(rows) > 0


class TestEloUpdates:
    def test_elo_moves_after_final(self, db) -> None:
        db.add(Team(mlb_id=147, name="New York Yankees", abbreviation="NYY", elo=1500))
        db.add(Team(mlb_id=111, name="Boston Red Sox", abbreviation="BOS", elo=1500))
        db.add(_game())
        db.commit()
        updated = update_elo_from_finals(db, date(2026, 7, 18))
        assert updated == 1
        home = db.query(Team).filter_by(mlb_id=147).one()
        away = db.query(Team).filter_by(mlb_id=111).one()
        assert home.elo > 1500 > away.elo
