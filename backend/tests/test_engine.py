"""Engine integration: full prediction pass over a synthetic game context."""
from __future__ import annotations

import pytest

from app.domain.entities import Market
from app.ml.engine import EVRPredictionEngine
from app.ml.features import GameContext, build_game_features, expected_runs_per_inning, GAME_FEATURES


@pytest.fixture()
def ctx() -> GameContext:
    return GameContext(
        game_pk=999001,
        home_team="New York Yankees",
        away_team="Boston Red Sox",
        home_elo=1560,
        away_elo=1490,
        home_sp={"era": 3.1, "fip": 3.3, "whip": 1.05, "k_pct": 0.28, "bb_pct": 0.06},
        away_sp={"era": 4.6, "fip": 4.4, "whip": 1.38, "k_pct": 0.19, "bb_pct": 0.09},
        home_bullpen={"era": 3.6, "fatigue": 0.2},
        away_bullpen={"era": 4.3, "fatigue": 0.5},
        home_offense={"ops": 0.780, "runs_per_game": 5.2, "k_pct": 0.21},
        away_offense={"ops": 0.700, "runs_per_game": 4.1, "k_pct": 0.24},
        park={"runs": 101, "hr": 110, "doubles": 95, "triples": 87},
        weather={"impact": {"runs_multiplier": 1.05, "hr_multiplier": 1.1}},
        umpire={"name": "Pat Hoberg", "zone": 1.0, "runs_delta": 0.0},
        home_form_l10=0.7,
        away_form_l10=0.4,
        lineup_confirmed=True,
    )


@pytest.fixture()
def engine() -> EVRPredictionEngine:
    return EVRPredictionEngine(mc_iterations=3000, seed=7)


class TestGamePredictions:
    def test_produces_all_game_markets(self, engine: EVRPredictionEngine, ctx: GameContext) -> None:
        preds = engine.predict_game(ctx)
        markets = {p.market for p in preds}
        assert {Market.MONEYLINE, Market.RUN_LINE, Market.TOTAL_OVER,
                Market.TOTAL_UNDER, Market.FIRST_INNING} <= markets

    def test_favorite_identified(self, engine: EVRPredictionEngine, ctx: GameContext) -> None:
        preds = engine.predict_game(ctx)
        home_ml = next(p for p in preds if p.market == Market.MONEYLINE and p.selection == ctx.home_team)
        away_ml = next(p for p in preds if p.market == Market.MONEYLINE and p.selection == ctx.away_team)
        assert home_ml.probability > away_ml.probability
        assert home_ml.probability > 0.5

    def test_probabilities_bounded(self, engine: EVRPredictionEngine, ctx: GameContext) -> None:
        for p in engine.predict_game(ctx):
            assert 0.0 < p.probability < 1.0
            assert 0.0 < p.confidence < 1.0
            assert p.explanation

    def test_model_breakdown_present(self, engine: EVRPredictionEngine, ctx: GameContext) -> None:
        preds = engine.predict_game(ctx)
        ml = next(p for p in preds if p.market == Market.MONEYLINE)
        assert "elo" in ml.model_breakdown
        assert "monte_carlo" in ml.model_breakdown
        assert "_features" in ml.model_breakdown

    def test_features_complete(self, ctx: GameContext) -> None:
        feats = build_game_features(ctx)
        assert set(GAME_FEATURES) <= set(feats)

    def test_expected_runs_sensitivity(self) -> None:
        strong = expected_runs_per_inning(5.5, 4.8, 4.5, 1.05, 1.05, 0.0)
        weak = expected_runs_per_inning(3.8, 2.9, 3.4, 0.95, 0.95, 0.0)
        assert strong > weak > 0


class TestPropPredictions:
    def test_batter_props_generated(self, engine: EVRPredictionEngine, ctx: GameContext) -> None:
        batter = {"pa": 350, "hit_per_pa": 0.25, "hr_per_pa": 0.05, "bb_per_pa": 0.1,
                  "k_per_pa": 0.18, "rbi_per_pa": 0.14, "run_per_pa": 0.14, "iso": 0.25, "avg": 0.29}
        props = engine.predict_batter_props(ctx, batter, ctx.away_sp, 3, ctx.game_pk, "Aaron Judge", 592450)
        markets = {p.market for p in props}
        assert Market.PLAYER_HITS in markets
        assert Market.PLAYER_HOME_RUNS in markets
        assert all(0 < p.probability < 1 for p in props)
        assert all(p.player_id == 592450 for p in props)

    def test_pitcher_props_generated(self, engine: EVRPredictionEngine, ctx: GameContext) -> None:
        pitcher = {"era": 2.9, "k_per_9": 11.0, "bb_per_9": 2.2, "hits_per_9": 6.9,
                   "innings_per_start": 6.1, "avg_pitch_count": 98, "fatigue": 0.1}
        props = engine.predict_pitcher_props(ctx, pitcher, ctx.away_offense, 0.6, ctx.game_pk, "Gerrit Cole", 543037)
        markets = {p.market for p in props}
        assert {Market.PITCHER_STRIKEOUTS, Market.PITCHER_WIN, Market.QUALITY_START, Market.NO_HITTER} <= markets
        no_no = next(p for p in props if p.market == Market.NO_HITTER)
        assert no_no.probability < 0.02
