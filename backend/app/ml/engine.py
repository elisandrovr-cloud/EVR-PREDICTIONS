"""EVR Prediction Engine — orchestrates every model into final probabilities.

Vote members per game market:
  elo          — rating-based prior
  monte_carlo  — simulated joint distribution (park/weather/umpire aware)
  random_forest, xgboost, lightgbm, catboost, neural_net, online_sgd — trained zoo
Stacked meta-probability joins the vote when the zoo is trained; the final
number is a Bayesian-weighted logit blend using per-market weights that the
nightly learning loop recalibrates from realized outcomes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.core.config import settings
from app.domain.entities import Market, PredictionCandidate
from app.ml.bayesian import blend, clip_probability
from app.ml.elo import EloSystem
from app.ml.features import (
    GAME_FEATURES,
    GameContext,
    build_game_features,
    expected_runs_per_inning,
    features_to_vector,
)
from app.ml.model_zoo import MarketModelBundle
from app.ml.monte_carlo import MonteCarloSimulator, TeamSimInput
from app.ml.player_props import BatterMatchup, PitcherMatchup

GAME_MARKET_FAMILIES = {
    Market.MONEYLINE: "moneyline",
    Market.RUN_LINE: "run_line",
    Market.TOTAL_OVER: "total",
    Market.TOTAL_UNDER: "total",
    Market.FIRST_INNING: "first_inning",
}

DEFAULT_WEIGHTS: dict[str, float] = {
    "elo": 0.18,
    "monte_carlo": 0.30,
    "random_forest": 0.09,
    "xgboost": 0.11,
    "lightgbm": 0.11,
    "catboost": 0.09,
    "neural_net": 0.06,
    "online_sgd": 0.03,
    "stacked": 0.03,
}


@dataclass
class EngineOutput:
    game_predictions: list[PredictionCandidate] = field(default_factory=list)
    prop_predictions: list[PredictionCandidate] = field(default_factory=list)

    @property
    def all(self) -> list[PredictionCandidate]:
        return [*self.game_predictions, *self.prop_predictions]


class EVRPredictionEngine:
    def __init__(
        self,
        weights_by_market: dict[str, dict[str, float]] | None = None,
        mc_iterations: int | None = None,
        seed: int | None = None,
    ) -> None:
        self.elo = EloSystem()
        self.simulator = MonteCarloSimulator(iterations=mc_iterations or settings.MONTE_CARLO_ITERATIONS, seed=seed)
        self.weights_by_market = weights_by_market or {}
        self.bundles: dict[str, MarketModelBundle] = {}
        for family in set(GAME_MARKET_FAMILIES.values()):
            bundle = MarketModelBundle(family)
            bundle.load()
            self.bundles[family] = bundle

    # ── internals ───────────────────────────────────────────────────────────
    def _weights(self, market: Market) -> dict[str, float]:
        return self.weights_by_market.get(market.value, DEFAULT_WEIGHTS)

    def _confidence(self, votes: dict[str, float], probability: float) -> float:
        """Confidence = model agreement × distance from coin-flip × sample support."""
        if not votes:
            return 0.35
        import statistics

        spread = statistics.pstdev(votes.values()) if len(votes) > 1 else 0.15
        agreement = max(0.0, 1.0 - spread * 4.0)
        conviction = abs(probability - 0.5) * 2.0
        support = min(1.0, len(votes) / 8.0)
        return round(min(0.99, 0.25 + 0.45 * agreement + 0.20 * conviction + 0.10 * support), 3)

    def _vote_and_blend(
        self, market: Market, analytic_votes: dict[str, float], feats: dict[str, float]
    ) -> tuple[float, dict[str, float]]:
        family = GAME_MARKET_FAMILIES[market]
        bundle = self.bundles[family]
        votes = dict(analytic_votes)
        if bundle.trained:
            member_votes = bundle.predict_members(features_to_vector(feats))
            votes.update(member_votes)
            stacked = bundle.predict_stacked(member_votes)
            if stacked is not None:
                votes["stacked"] = stacked
        prob = clip_probability(blend(votes, self._weights(market)))
        return prob, votes

    # ── game markets ────────────────────────────────────────────────────────
    def predict_game(self, ctx: GameContext, total_line: float = 8.5) -> list[PredictionCandidate]:
        feats = build_game_features(ctx)
        elo_home = self.elo.expected_home_win(ctx.home_elo, ctx.away_elo)

        home_rpi = expected_runs_per_inning(
            feats["home_off_runs_pg"], feats["away_sp_era"], feats["away_bullpen_era"],
            feats["park_runs_factor"], feats["weather_runs_mult"], feats["umpire_runs_delta"],
        )
        away_rpi = expected_runs_per_inning(
            feats["away_off_runs_pg"], feats["home_sp_era"], feats["home_bullpen_era"],
            feats["park_runs_factor"], feats["weather_runs_mult"], feats["umpire_runs_delta"],
        )
        # Opposing starter quality shapes the early innings of each offense's runs.
        home_vs_starter = max(0.6, min(1.6, feats["away_sp_fip"] / 4.10))
        away_vs_starter = max(0.6, min(1.6, feats["home_sp_fip"] / 4.10))
        sim = self.simulator.simulate(
            TeamSimInput(home_rpi, starter_run_suppression=home_vs_starter,
                         bullpen_run_suppression=max(0.6, min(1.6, feats["away_bullpen_era"] / 4.10))),
            TeamSimInput(away_rpi, starter_run_suppression=away_vs_starter,
                         bullpen_run_suppression=max(0.6, min(1.6, feats["home_bullpen_era"] / 4.10))),
            total_lines=[total_line],
        )

        wx = ctx.weather or {}
        ump_name = (ctx.umpire or {}).get("name", "TBD") if isinstance(ctx.umpire, dict) else "TBD"
        base_note = (
            f"{ctx.away_team} @ {ctx.home_team} — sim media {sim.mean_away:.1f}-{sim.mean_home:.1f} "
            f"(total {sim.mean_total:.1f}), parque x{feats['park_runs_factor']:.2f} carreras, "
            f"clima x{feats['weather_runs_mult']:.2f}, umpire {ump_name}."
        )

        candidates: list[PredictionCandidate] = []

        def add(market: Market, selection: str, analytic: dict[str, float], line: float | None, extra: str) -> None:
            prob, votes = self._vote_and_blend(market, analytic, feats)
            candidates.append(
                PredictionCandidate(
                    game_pk=ctx.game_pk,
                    market=market,
                    selection=selection,
                    probability=round(prob, 4),
                    confidence=self._confidence(votes, prob),
                    explanation=f"{extra} {base_note}",
                    line=line,
                    model_breakdown={k: round(v, 4) for k, v in votes.items()},
                )
            )

        add(Market.MONEYLINE, ctx.home_team, {"elo": elo_home, "monte_carlo": sim.home_win}, None,
            f"ELO {ctx.home_elo:.0f} vs {ctx.away_elo:.0f}; abridores "
            f"{feats['home_sp_era']:.2f} vs {feats['away_sp_era']:.2f} ERA.")
        add(Market.MONEYLINE, ctx.away_team, {"elo": 1 - elo_home, "monte_carlo": sim.away_win}, None,
            f"ELO {ctx.away_elo:.0f} vs {ctx.home_elo:.0f} como visitante.")
        add(Market.RUN_LINE, f"{ctx.home_team} -1.5", {"elo": max(0.05, elo_home - 0.18),
            "monte_carlo": sim.home_runline_minus_1_5}, -1.5,
            "Cubrir -1.5 exige margen de 2+; la simulación mide la cola de la distribución.")
        add(Market.RUN_LINE, f"{ctx.away_team} +1.5", {"elo": min(0.95, (1 - elo_home) + 0.18),
            "monte_carlo": 1 - sim.home_runline_minus_1_5}, 1.5,
            "El +1.5 gana con derrota por 1 o victoria visitante.")
        over_p = sim.over_probs.get(total_line, 0.5)
        add(Market.TOTAL_OVER, f"Over {total_line}", {"elo": 0.5, "monte_carlo": over_p}, total_line,
            f"Runs esperados {sim.mean_total:.1f} vs línea {total_line}.")
        add(Market.TOTAL_UNDER, f"Under {total_line}", {"elo": 0.5, "monte_carlo": sim.under_probs.get(total_line, 0.5)},
            total_line, f"Runs esperados {sim.mean_total:.1f} vs línea {total_line}.")
        add(Market.FIRST_INNING, "Anotan en 1er inning (YRFI)", {"elo": 0.5, "monte_carlo": sim.first_inning_run},
            0.5, "Probabilidad conjunta de carrera en la primera entrada.")

        for c in candidates:
            c.model_breakdown["_mean_total"] = round(sim.mean_total, 2)
        self._attach_features(candidates, feats)
        return candidates

    @staticmethod
    def _attach_features(candidates: list[PredictionCandidate], feats: dict[str, float]) -> None:
        packed = {k: round(float(v), 5) for k, v in feats.items() if k in GAME_FEATURES}
        for c in candidates:
            c.model_breakdown["_features"] = packed  # type: ignore[assignment]

    # ── player props ────────────────────────────────────────────────────────
    def predict_batter_props(self, ctx: GameContext, batter: dict[str, Any], opp_pitcher: dict[str, Any] | None,
                             lineup_slot: int, game_pk: int, name: str, player_id: int) -> list[PredictionCandidate]:
        m = BatterMatchup(
            batter=batter, opp_pitcher=opp_pitcher, park=ctx.park,
            weather_impact=(ctx.weather or {}).get("impact"), umpire=ctx.umpire, lineup_slot=lineup_slot,
        )
        note = f"{name} (slot {lineup_slot}, {m.expected_pa:.1f} PA esperadas)"
        specs: list[tuple[Market, str, float, float | None, str]] = [
            (Market.PLAYER_HITS, f"{name} 1+ hit", m.hits_at_least(1), 0.5, "Rate de hit ajustado al pitcher rival."),
            (Market.PLAYER_HITS, f"{name} 2+ hits", m.hits_at_least(2), 1.5, "Cola binomial de multi-hit."),
            (Market.PLAYER_HITS, f"{name} 3+ hits", m.hits_at_least(3), 2.5, "Cola extrema de multi-hit."),
            (Market.PLAYER_HOME_RUNS, f"{name} HR", m.home_run(), 0.5, "HR/PA con parque y clima."),
            (Market.PLAYER_RBI, f"{name} 1+ RBI", m.rbi_at_least(1), 0.5, "Poisson sobre RBI/PA."),
            (Market.PLAYER_RUNS, f"{name} anota carrera", m.run_scored(), 0.5, "Poisson sobre R/PA."),
            (Market.PLAYER_WALKS, f"{name} 1+ BB", m.walk(), 0.5, "BB con zona del umpire."),
            (Market.PLAYER_TOTAL_BASES, f"{name} 2+ bases totales", m.total_bases_at_least(1.5), 1.5,
             "TB desde mezcla de hits e ISO."),
            (Market.PLAYER_STOLEN_BASES, f"{name} base robada", m.stolen_base(), 0.5, "SB con sprint speed."),
        ]
        out: list[PredictionCandidate] = []
        for market, selection, prob, line, why in specs:
            prob = clip_probability(prob)
            out.append(
                PredictionCandidate(
                    game_pk=game_pk, market=market, selection=selection, player_id=player_id, line=line,
                    probability=round(prob, 4),
                    confidence=self._confidence({"analytic": prob}, prob),
                    explanation=f"{why} {note}.",
                    model_breakdown={"analytic": round(prob, 4)},
                )
            )
        return out

    def predict_pitcher_props(self, ctx: GameContext, pitcher: dict[str, Any], opp_offense: dict[str, Any] | None,
                              team_win_prob: float, game_pk: int, name: str, player_id: int,
                              k_line: float = 5.5) -> list[PredictionCandidate]:
        m = PitcherMatchup(pitcher=pitcher, opp_offense=opp_offense, park=ctx.park, umpire=ctx.umpire,
                           team_win_prob=team_win_prob)
        ip = m.expected_innings
        note = f"{name} proyecta {ip:.1f} IP"
        specs: list[tuple[Market, str, float, float | None, str]] = [
            (Market.PITCHER_STRIKEOUTS, f"{name} over {k_line} K", m.strikeouts_at_least(k_line), k_line,
             "K/9 vs K% rival y zona del umpire."),
            (Market.PITCHER_WALKS, f"{name} over 1.5 BB", m.walks_at_least(1.5), 1.5, "BB/9 con zona del umpire."),
            (Market.PITCHER_OUTS, f"{name} over 16.5 outs", m.outs_at_least(16.5), 16.5,
             "Aproximación normal sobre outs registrados."),
            (Market.PITCHER_HITS_ALLOWED, f"{name} over 4.5 hits", m.hits_allowed_at_least(4.5), 4.5,
             "H/9 vs contacto rival."),
            (Market.PITCHER_EARNED_RUNS, f"{name} over 2.5 ER", m.earned_runs_at_least(2.5), 2.5,
             "ERA escalada al parque."),
            (Market.PITCHER_WIN, f"{name} gana", m.win(), None, "Win prob del equipo × durar 5+."),
            (Market.QUALITY_START, f"{name} quality start", m.quality_start(), None, "6+ IP y ≤3 ER correlacionados."),
            (Market.NO_HITTER, f"{name} no-hitter", m.no_hitter(), None, "Poisson de 0 hits en 9."),
        ]
        out: list[PredictionCandidate] = []
        for market, selection, prob, line, why in specs:
            prob = clip_probability(prob)
            out.append(
                PredictionCandidate(
                    game_pk=game_pk, market=market, selection=selection, player_id=player_id, line=line,
                    probability=round(prob, 4),
                    confidence=self._confidence({"analytic": prob}, prob),
                    explanation=f"{why} {note}.",
                    model_breakdown={"analytic": round(prob, 4)},
                )
            )
        return out
