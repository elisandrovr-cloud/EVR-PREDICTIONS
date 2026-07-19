"""ML core: bayesian updating, ELO, Monte Carlo, prop distributions."""
from __future__ import annotations

import pytest

from app.ml.bayesian import beta_shrink, blend, log_loss_single, update_weights
from app.ml.elo import EloSystem
from app.ml.monte_carlo import MonteCarloSimulator, TeamSimInput
from app.ml.player_props import (
    BatterMatchup,
    PitcherMatchup,
    binomial_at_least,
    poisson_at_least,
)


class TestBayesian:
    def test_update_rewards_accurate_model(self) -> None:
        weights = {"good": 0.5, "bad": 0.5}
        for _ in range(30):
            weights = update_weights(weights, {"good": 0.8, "bad": 0.3}, outcome=1)
        assert weights["good"] > weights["bad"]
        assert sum(weights.values()) == pytest.approx(1.0)

    def test_weights_never_zero(self) -> None:
        weights = {"a": 0.5, "b": 0.5}
        for _ in range(200):
            weights = update_weights(weights, {"a": 0.99, "b": 0.01}, outcome=1)
        assert weights["b"] > 0

    def test_blend_between_extremes(self) -> None:
        p = blend({"m1": 0.6, "m2": 0.8}, {"m1": 0.5, "m2": 0.5})
        assert 0.6 < p < 0.8

    def test_blend_respects_weights(self) -> None:
        heavy_m2 = blend({"m1": 0.4, "m2": 0.9}, {"m1": 0.1, "m2": 0.9})
        heavy_m1 = blend({"m1": 0.4, "m2": 0.9}, {"m1": 0.9, "m2": 0.1})
        assert heavy_m2 > heavy_m1

    def test_log_loss_monotonic(self) -> None:
        assert log_loss_single(0.9, 1) < log_loss_single(0.5, 1) < log_loss_single(0.1, 1)

    def test_beta_shrink_pulls_small_samples_to_prior(self) -> None:
        hot_small = beta_shrink(0.5, 20, 0.25)
        hot_large = beta_shrink(0.5, 600, 0.25)
        assert hot_small < hot_large
        assert 0.25 < hot_small < 0.5


class TestElo:
    def test_expected_home_win_with_advantage(self) -> None:
        elo = EloSystem()
        assert elo.expected_home_win(1500, 1500) > 0.5

    def test_update_direction(self) -> None:
        elo = EloSystem()
        home, away = elo.update(1500, 1500, 6, 2)
        assert home > 1500 > away

    def test_upset_moves_more(self) -> None:
        elo = EloSystem()
        _, favorite_after_loss = elo.update(1400, 1600, 5, 1)
        assert 1600 - favorite_after_loss > 0

    def test_season_reset_regresses(self) -> None:
        assert EloSystem.season_reset(1600) < 1600
        assert EloSystem.season_reset(1400) > 1400


class TestMonteCarlo:
    @pytest.fixture()
    def sim(self) -> MonteCarloSimulator:
        return MonteCarloSimulator(iterations=4000, seed=42)

    def test_probabilities_are_valid(self, sim: MonteCarloSimulator) -> None:
        res = sim.simulate(TeamSimInput(0.55), TeamSimInput(0.45))
        assert 0 < res.home_win < 1
        assert res.home_win + res.away_win == pytest.approx(1.0, abs=1e-6)

    def test_stronger_offense_wins_more(self, sim: MonteCarloSimulator) -> None:
        res = sim.simulate(TeamSimInput(0.75), TeamSimInput(0.35))
        assert res.home_win > 0.6

    def test_over_under_complement(self, sim: MonteCarloSimulator) -> None:
        res = sim.simulate(TeamSimInput(0.5), TeamSimInput(0.5), total_lines=[8.5])
        # non-integer line: over + under must sum to 1
        assert res.over_probs[8.5] + res.under_probs[8.5] == pytest.approx(1.0, abs=1e-6)

    def test_high_scoring_env_raises_total(self, sim: MonteCarloSimulator) -> None:
        low = sim.simulate(TeamSimInput(0.35), TeamSimInput(0.35))
        high = sim.simulate(TeamSimInput(0.75), TeamSimInput(0.75))
        assert high.mean_total > low.mean_total

    def test_runline_tail_below_moneyline(self, sim: MonteCarloSimulator) -> None:
        res = sim.simulate(TeamSimInput(0.6), TeamSimInput(0.45))
        assert res.home_runline_minus_1_5 < res.home_win


class TestDistributions:
    def test_poisson_at_least_bounds(self) -> None:
        assert poisson_at_least(2.0, 0) == pytest.approx(1.0)
        assert 0 < poisson_at_least(2.0, 3) < 1
        assert poisson_at_least(0.001, 5) < 1e-6

    def test_binomial_at_least(self) -> None:
        assert binomial_at_least(4, 0.5, 1) == pytest.approx(1 - 0.5**4)
        assert binomial_at_least(4, 0.25, 5) == 0.0


class TestMatchups:
    def _batter(self, **overrides: float) -> BatterMatchup:
        stats = {"pa": 400, "hit_per_pa": 0.24, "hr_per_pa": 0.04, "bb_per_pa": 0.09,
                 "k_per_pa": 0.2, "rbi_per_pa": 0.13, "run_per_pa": 0.13, "iso": 0.2,
                 "avg": 0.28, "sb_per_game": 0.1, "sprint_speed": 28.5, **overrides}
        return BatterMatchup(batter=stats, opp_pitcher=None, park=None, weather_impact=None,
                             umpire=None, lineup_slot=2)

    def test_hit_probability_ordering(self) -> None:
        m = self._batter()
        assert m.hits_at_least(1) > m.hits_at_least(2) > m.hits_at_least(3)

    def test_better_hitter_higher_hr_prob(self) -> None:
        slugger = self._batter(hr_per_pa=0.06)
        slap = self._batter(hr_per_pa=0.01)
        assert slugger.home_run() > slap.home_run()

    def test_leadoff_gets_more_pa(self) -> None:
        top = BatterMatchup(batter={"pa": 300}, opp_pitcher=None, park=None,
                            weather_impact=None, umpire=None, lineup_slot=1)
        bottom = BatterMatchup(batter={"pa": 300}, opp_pitcher=None, park=None,
                               weather_impact=None, umpire=None, lineup_slot=9)
        assert top.expected_pa > bottom.expected_pa

    def _pitcher(self, **overrides: float) -> PitcherMatchup:
        stats = {"era": 3.5, "k_per_9": 9.5, "bb_per_9": 2.8, "hits_per_9": 7.8,
                 "innings_per_start": 5.8, "avg_pitch_count": 95, "fatigue": 0.0, **overrides}
        return PitcherMatchup(pitcher=stats, opp_offense=None, park=None, umpire=None, team_win_prob=0.55)

    def test_ace_more_strikeouts(self) -> None:
        ace = self._pitcher(k_per_9=12.0)
        soft = self._pitcher(k_per_9=6.0)
        assert ace.strikeouts_at_least(5.5) > soft.strikeouts_at_least(5.5)

    def test_fatigue_reduces_innings(self) -> None:
        fresh = self._pitcher(fatigue=0.0)
        tired = self._pitcher(fatigue=0.8)
        assert fresh.expected_innings > tired.expected_innings

    def test_quality_start_bounded(self) -> None:
        qs = self._pitcher().quality_start()
        assert 0 < qs < 1

    def test_no_hitter_is_rare(self) -> None:
        assert self._pitcher().no_hitter() < 0.01
