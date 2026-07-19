"""Nightly self-learning loop.

After each slate finishes:
 1. Pull final results for every tracked game.
 2. Settle predictions (win/loss/push) against real outcomes.
 3. Bayesian-update per-market ensemble weights from each model's vote.
 4. Update team ELO ratings from final scores.
 5. Retrain the model zoo on all accumulated (features → outcome) rows and
    partial-fit the online SGD member.
 6. Persist daily engine metrics (accuracy, Brier, ROI, CLV).
Runs with zero human intervention from Celery beat.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.domain.entities import Market, Odds
from app.infrastructure.db.models import (
    EngineMetric,
    Game,
    ModelWeight,
    Prediction,
    Team,
)
from app.ml.bayesian import brier_single, update_weights
from app.ml.elo import EloSystem
from app.ml.engine import DEFAULT_WEIGHTS, GAME_MARKET_FAMILIES
from app.ml.features import GAME_FEATURES
from app.ml.model_zoo import MarketModelBundle

logger = get_logger(__name__)


# ── outcome resolution ────────────────────────────────────────────────────────
def resolve_outcome(pred: Prediction, game: Game) -> str | None:
    """Grade a prediction against the final game state. None = cannot grade."""
    if game.home_score is None or game.away_score is None:
        return None
    home, away = game.home_score, game.away_score
    total = home + away
    margin = home - away
    market = pred.market
    sel = pred.selection.lower()

    if market == Market.MONEYLINE.value:
        home_won = margin > 0
        picked_home = str(game.home_team_mlb_id) in sel or "home" in sel or _is_home_pick(pred, game)
        return "win" if picked_home == home_won else "loss"
    if market == Market.RUN_LINE.value:
        if "-1.5" in sel:
            return "win" if margin >= 2 else "loss"
        return "win" if margin <= 1 else "loss"
    if market == Market.TOTAL_OVER.value:
        line = pred.line or 8.5
        if total == line:
            return "push"
        return "win" if total > line else "loss"
    if market == Market.TOTAL_UNDER.value:
        line = pred.line or 8.5
        if total == line:
            return "push"
        return "win" if total < line else "loss"
    if market == Market.FIRST_INNING.value:
        innings = (game.linescore or {}).get("innings", [])
        if not innings:
            return None
        first = innings[0]
        runs = (first.get("home", {}).get("runs") or 0) + (first.get("away", {}).get("runs") or 0)
        return "win" if runs > 0 else "loss"
    # Player props are graded by the results worker from the boxscore (stored in
    # linescore["player_results"] as {prediction_id: actual_value}).
    results = (game.linescore or {}).get("player_results", {})
    actual = results.get(str(pred.id))
    if actual is None:
        return None
    line = pred.line if pred.line is not None else 0.5
    if float(actual) == line:
        return "push"
    return "win" if float(actual) > line else "loss"


def _is_home_pick(pred: Prediction, game: Game) -> bool:
    feats = pred.features or {}
    return bool(feats.get("_picked_home"))


# ── weight recalibration ──────────────────────────────────────────────────────
def load_market_weights(db: Session) -> dict[str, dict[str, float]]:
    weights: dict[str, dict[str, float]] = {}
    for row in db.scalars(select(ModelWeight)):
        weights.setdefault(row.market, {})[row.model_name] = row.weight
    return weights


def persist_market_weights(db: Session, market: str, weights: dict[str, float],
                           losses: dict[str, list[float]]) -> None:
    for model_name, w in weights.items():
        row = db.scalar(
            select(ModelWeight).where(ModelWeight.market == market, ModelWeight.model_name == model_name)
        )
        model_losses = losses.get(model_name, [])
        if row is None:
            row = ModelWeight(market=market, model_name=model_name, weight=w, samples=0)
            db.add(row)
        row.weight = w
        row.samples = (row.samples or 0) + len(model_losses)
        if model_losses:
            row.brier_score = float(np.mean(model_losses))
        row.updated_at = datetime.now(timezone.utc)


def recalibrate_from_settled(db: Session, day: date) -> dict[str, dict[str, float]]:
    """Run the multiplicative-weights update over every graded game-market prediction."""
    all_weights = load_market_weights(db)
    preds = db.scalars(
        select(Prediction).where(Prediction.game_date == day, Prediction.settled.is_(True),
                                 Prediction.outcome.in_(["win", "loss"]))
    ).all()
    per_market_losses: dict[str, dict[str, list[float]]] = {}
    for pred in preds:
        if pred.market not in {m.value for m in GAME_MARKET_FAMILIES}:
            continue
        outcome = 1 if pred.outcome == "win" else 0
        votes = {k: v for k, v in (pred.model_breakdown or {}).items()
                 if not k.startswith("_") and isinstance(v, (int, float))}
        if not votes:
            continue
        current = all_weights.get(pred.market) or dict(DEFAULT_WEIGHTS)
        all_weights[pred.market] = update_weights(current, votes, outcome)
        bucket = per_market_losses.setdefault(pred.market, {})
        for name, p in votes.items():
            bucket.setdefault(name, []).append(brier_single(float(p), outcome))
    for market, weights in all_weights.items():
        persist_market_weights(db, market, weights, per_market_losses.get(market, {}))
    db.commit()
    logger.info("recalibrated weights", extra={"day": str(day), "graded": len(preds)})
    return all_weights


# ── ELO updates ───────────────────────────────────────────────────────────────
def update_elo_from_finals(db: Session, day: date) -> int:
    elo = EloSystem()
    games = db.scalars(
        select(Game).where(Game.game_date == day, Game.status == "final")
    ).all()
    updated = 0
    for g in games:
        if g.home_score is None or g.away_score is None:
            continue
        home = db.scalar(select(Team).where(Team.mlb_id == g.home_team_mlb_id))
        away = db.scalar(select(Team).where(Team.mlb_id == g.away_team_mlb_id))
        if not home or not away:
            continue
        home.elo, away.elo = elo.update(home.elo, away.elo, g.home_score, g.away_score)
        updated += 1
    db.commit()
    return updated


# ── zoo retraining ────────────────────────────────────────────────────────────
def build_training_matrix(db: Session, family: str) -> tuple[np.ndarray, np.ndarray]:
    markets = [m.value for m, fam in GAME_MARKET_FAMILIES.items() if fam == family]
    preds = db.scalars(
        select(Prediction).where(Prediction.market.in_(markets), Prediction.settled.is_(True),
                                 Prediction.outcome.in_(["win", "loss"]))
    ).all()
    rows: list[list[float]] = []
    ys: list[int] = []
    for p in preds:
        feats = p.features or {}
        if not feats:
            continue
        rows.append([float(feats.get(name, 0.0)) for name in GAME_FEATURES])
        ys.append(1 if p.outcome == "win" else 0)
    if not rows:
        return np.empty((0, len(GAME_FEATURES))), np.empty(0)
    return np.array(rows), np.array(ys)


def retrain_zoo(db: Session) -> dict[str, dict[str, float]]:
    report: dict[str, dict[str, float]] = {}
    for family in sorted(set(GAME_MARKET_FAMILIES.values())):
        X, y = build_training_matrix(db, family)
        bundle = MarketModelBundle(family)
        bundle.load()
        if len(y) and bundle.trained:
            bundle.partial_fit_online(X[-64:], y[-64:])
        scores = bundle.fit(X, y, GAME_FEATURES)
        if scores:
            bundle.save()
            report[family] = scores
    return report


# ── daily metrics ─────────────────────────────────────────────────────────────
def snapshot_metrics(db: Session, day: date) -> None:
    preds = db.scalars(
        select(Prediction).where(Prediction.game_date == day, Prediction.settled.is_(True))
    ).all()
    by_market: dict[str, list[Prediction]] = {"all": []}
    for p in preds:
        by_market.setdefault(p.market, []).append(p)
        by_market["all"].append(p)
    for market, rows in by_market.items():
        wins = sum(1 for r in rows if r.outcome == "win")
        losses = sum(1 for r in rows if r.outcome == "loss")
        pushes = sum(1 for r in rows if r.outcome == "push")
        stake = profit = 0.0
        briers: list[float] = []
        for r in rows:
            if r.outcome in ("win", "loss"):
                briers.append(brier_single(r.probability, 1 if r.outcome == "win" else 0))
            if r.book_odds is not None and r.outcome in ("win", "loss"):
                stake += 1.0
                profit += (Odds(american=r.book_odds).decimal - 1.0) if r.outcome == "win" else -1.0
        row = db.scalar(select(EngineMetric).where(EngineMetric.metric_date == day, EngineMetric.market == market))
        if row is None:
            row = EngineMetric(metric_date=day, market=market)
            db.add(row)
        row.predictions = len(rows)
        row.wins, row.losses, row.pushes = wins, losses, pushes
        row.roi = round(profit / stake, 4) if stake else None
        row.brier_score = round(float(np.mean(briers)), 4) if briers else None
    db.commit()
