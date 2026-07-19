"""Results settlement: after finals, grade every prediction and parlay from
the official boxscore, then feed the learning loop."""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.domain.entities import Market
from app.infrastructure.db.models import Game, Parlay, Prediction
from app.infrastructure.providers.registry import ProviderRegistry, get_registry
from app.ml.training import (
    recalibrate_from_settled,
    resolve_outcome,
    retrain_zoo,
    snapshot_metrics,
    update_elo_from_finals,
)

logger = get_logger(__name__)

# prop market → boxscore stat extraction
BATTING_EXTRACT: dict[str, str] = {
    Market.PLAYER_HITS.value: "hits",
    Market.PLAYER_HOME_RUNS.value: "homeRuns",
    Market.PLAYER_RBI.value: "rbi",
    Market.PLAYER_RUNS.value: "runs",
    Market.PLAYER_WALKS.value: "baseOnBalls",
    Market.PLAYER_STOLEN_BASES.value: "stolenBases",
}
PITCHING_EXTRACT: dict[str, str] = {
    Market.PITCHER_STRIKEOUTS.value: "strikeOuts",
    Market.PITCHER_WALKS.value: "baseOnBalls",
    Market.PITCHER_HITS_ALLOWED.value: "hits",
    Market.PITCHER_EARNED_RUNS.value: "earnedRuns",
}


def _player_boxscore_stats(boxscore: dict[str, Any]) -> dict[int, dict[str, Any]]:
    out: dict[int, dict[str, Any]] = {}
    for side in ("home", "away"):
        players = (boxscore.get("teams", {}).get(side, {}) or {}).get("players", {})
        for key, pdata in players.items():
            pid = pdata.get("person", {}).get("id")
            if pid:
                out[pid] = pdata.get("stats", {})
    return out


def _actual_value(pred: Prediction, stats: dict[str, Any]) -> float | None:
    if pred.market in BATTING_EXTRACT:
        return float((stats.get("batting") or {}).get(BATTING_EXTRACT[pred.market]) or 0)
    if pred.market in PITCHING_EXTRACT:
        return float((stats.get("pitching") or {}).get(PITCHING_EXTRACT[pred.market]) or 0)
    pitching = stats.get("pitching") or {}
    if pred.market == Market.PLAYER_TOTAL_BASES.value:
        b = stats.get("batting") or {}
        singles = float(b.get("hits") or 0) - float(b.get("doubles") or 0) - float(b.get("triples") or 0) - float(b.get("homeRuns") or 0)
        return singles + 2 * float(b.get("doubles") or 0) + 3 * float(b.get("triples") or 0) + 4 * float(b.get("homeRuns") or 0)
    if pred.market == Market.PITCHER_OUTS.value:
        ip = str(pitching.get("inningsPitched") or "0")
        whole, _, frac = ip.partition(".")
        return float(whole) * 3 + float(frac or 0)
    if pred.market == Market.PITCHER_WIN.value:
        return 1.0 if pitching.get("wins") else 0.0
    if pred.market == Market.QUALITY_START.value:
        ip = str(pitching.get("inningsPitched") or "0")
        whole, _, _ = ip.partition(".")
        return 1.0 if float(whole) >= 6 and float(pitching.get("earnedRuns") or 99) <= 3 else 0.0
    if pred.market == Market.NO_HITTER.value:
        return 1.0 if float(pitching.get("hits") or 99) == 0 else 0.0
    return None


def settle_game(db: Session, game: Game, registry: ProviderRegistry | None = None) -> int:
    """Grade all predictions for a final game. Returns count settled."""
    reg = registry or get_registry()
    preds = db.scalars(
        select(Prediction).where(Prediction.game_pk == game.game_pk, Prediction.settled.is_(False))
    ).all()
    if not preds:
        return 0

    player_results: dict[str, float] = {}
    prop_preds = [p for p in preds if p.player_mlb_id]
    if prop_preds:
        try:
            box = reg.mlb.boxscore(game.game_pk)
            by_player = _player_boxscore_stats(box)
            for p in prop_preds:
                stats = by_player.get(p.player_mlb_id or 0, {})
                actual = _actual_value(p, stats)
                if actual is not None:
                    # binary markets grade on value vs 0.5-style line; store actual
                    player_results[str(p.id)] = actual
        except Exception as exc:  # noqa: BLE001
            logger.warning("boxscore fetch failed", extra={"game_pk": game.game_pk, "error": str(exc)})
    game.linescore = {**(game.linescore or {}), "player_results": player_results}
    db.flush()

    settled = 0
    for p in preds:
        outcome = resolve_outcome(p, game)
        if outcome is None:
            continue
        p.outcome = outcome
        p.settled = True
        settled += 1
    db.commit()
    return settled


def settle_parlays(db: Session, day: date) -> int:
    parlays = db.scalars(select(Parlay).where(Parlay.game_date == day, Parlay.settled.is_(False))).all()
    count = 0
    for parlay in parlays:
        leg_ids = [l.get("prediction_id") for l in parlay.legs if l.get("prediction_id")]
        legs = db.scalars(select(Prediction).where(Prediction.id.in_(leg_ids))).all() if leg_ids else []
        if not legs or any(not l.settled for l in legs):
            continue
        outcomes = {l.outcome for l in legs}
        parlay.outcome = "win" if outcomes <= {"win", "push"} else "loss"
        parlay.settled = True
        count += 1
    db.commit()
    return count


def close_day(db: Session, day: date) -> dict[str, Any]:
    """The nightly no-human-in-the-loop learning pipeline."""
    games = db.scalars(select(Game).where(Game.game_date == day, Game.status == "final")).all()
    settled = sum(settle_game(db, g) for g in games)
    parlays = settle_parlays(db, day)
    weights = recalibrate_from_settled(db, day)
    elo_updates = update_elo_from_finals(db, day)
    training_report = retrain_zoo(db)
    snapshot_metrics(db, day)
    logger.info("day closed", extra={"day": str(day), "settled": settled})
    return {
        "day": str(day),
        "games_final": len(games),
        "predictions_settled": settled,
        "parlays_settled": parlays,
        "markets_recalibrated": len(weights),
        "elo_updates": elo_updates,
        "families_retrained": list(training_report.keys()),
        "closed_at": datetime.now(timezone.utc).isoformat(),
    }
