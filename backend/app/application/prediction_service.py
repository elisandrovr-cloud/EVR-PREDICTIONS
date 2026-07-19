"""Prediction generation use-case: run the engine over a slate, attach market
odds, flag value bets, persist. Regeneration is idempotent per (game, market,
selection) — new runs update probabilities instead of duplicating rows."""
from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.domain.entities import Market, Odds, PredictionCandidate
from app.infrastructure.db.models import Game, OddsQuote, Prediction, Team
from app.application.context_builder import build_context
from app.ml.engine import EVRPredictionEngine
from app.ml.training import load_market_weights

logger = get_logger(__name__)

PROP_SLOTS = 9  # how many lineup batters get prop predictions per team


def _latest_odds(db: Session, game_pk: int) -> dict[tuple[str, str], OddsQuote]:
    """Most recent quote per (market, selection) for a game."""
    quotes = db.scalars(
        select(OddsQuote).where(OddsQuote.game_pk == game_pk).order_by(OddsQuote.captured_at)
    ).all()
    latest: dict[tuple[str, str], OddsQuote] = {}
    for q in quotes:
        latest[(q.market, q.selection)] = q
    return latest


def _attach_book_odds(db: Session, cand: PredictionCandidate, team_names: dict[int, str]) -> None:
    latest = _latest_odds(db, cand.game_pk)
    if not latest:
        return
    market_key = {
        Market.MONEYLINE: "moneyline",
        Market.RUN_LINE: "run_line",
        Market.TOTAL_OVER: "total",
        Market.TOTAL_UNDER: "total",
    }.get(cand.market)
    if market_key is None:
        return
    for (mk, selection), quote in latest.items():
        if mk != market_key:
            continue
        sel_l, cand_l = selection.lower(), cand.selection.lower()
        if market_key == "total":
            side = "over" if cand.market == Market.TOTAL_OVER else "under"
            if side in sel_l and (quote.line is None or cand.line is None or abs(quote.line - cand.line) < 0.01):
                cand.book_odds = quote.american
                return
        elif sel_l in cand_l or cand_l in sel_l:
            cand.book_odds = quote.american
            return


def persist_candidates(db: Session, day: date, candidates: list[PredictionCandidate],
                       home_team_by_pk: dict[int, str]) -> int:
    saved = 0
    for c in candidates:
        econ = c.economics()
        row = db.scalar(
            select(Prediction).where(
                Prediction.game_pk == c.game_pk, Prediction.market == c.market.value,
                Prediction.selection == c.selection,
            )
        )
        if row is None:
            row = Prediction(game_pk=c.game_pk, game_date=day, market=c.market.value, selection=c.selection)
            db.add(row)
        if row.settled:
            continue
        features = c.model_breakdown.pop("_features", {}) if isinstance(c.model_breakdown, dict) else {}
        if c.market == Market.MONEYLINE:
            features["_picked_home"] = c.selection == home_team_by_pk.get(c.game_pk)
        row.game_date = day
        row.player_mlb_id = c.player_id
        row.line = c.line
        row.probability = c.probability
        row.fair_odds = c.fair_odds
        row.book_odds = c.book_odds
        row.expected_value = round(econ.expected_value, 4) if econ else None
        row.edge = round(econ.edge, 4) if econ else None
        row.kelly_stake = round(econ.kelly_stake(settings.KELLY_FRACTION), 4) if econ else None
        row.confidence = c.confidence
        row.risk = c.risk.value
        row.is_value_bet = bool(econ and econ.edge >= settings.MIN_EDGE_FOR_VALUE_BET and econ.expected_value > 0)
        row.explanation = c.explanation
        row.model_breakdown = c.model_breakdown
        row.features = features
        saved += 1
    db.commit()
    return saved


def generate_for_day(db: Session, day: date, only_game_pk: int | None = None) -> dict[str, int]:
    """Full engine pass over the slate (or a single game after a lineup event)."""
    weights = load_market_weights(db)
    engine = EVRPredictionEngine(weights_by_market=weights)
    query = select(Game).where(Game.game_date == day, Game.status != "final")
    if only_game_pk is not None:
        query = select(Game).where(Game.game_pk == only_game_pk)
    games = db.scalars(query).all()
    teams = {t.mlb_id: t.name for t in db.scalars(select(Team)).all()}
    home_team_by_pk: dict[int, str] = {}
    candidates: list[PredictionCandidate] = []

    for game in games:
        ctx = build_context(db, game)
        home_team_by_pk[game.game_pk] = ctx.home_team
        game_preds = engine.predict_game(ctx)
        moneyline_home = next(
            (p.probability for p in game_preds if p.market == Market.MONEYLINE and p.selection == ctx.home_team), 0.5
        )
        for c in game_preds:
            _attach_book_odds(db, c, teams)
        candidates.extend(game_preds)

        # Batter props from confirmed (or projected) lineups
        from app.application.context_builder import _stat  # local import avoids cycle at module load

        for side in ("home", "away"):
            lineup = (game.lineups or {}).get(side, [])[:PROP_SLOTS]
            opp_pitcher_id = game.away_pitcher_mlb_id if side == "home" else game.home_pitcher_mlb_id
            opp_pitcher = _stat(db, opp_pitcher_id, "pitching")
            for slot, batter in enumerate(lineup, start=1):
                stats = _stat(db, batter.get("id"), "batting")
                if not stats or not batter.get("id"):
                    continue
                candidates.extend(
                    engine.predict_batter_props(ctx, stats, opp_pitcher, slot, game.game_pk,
                                                batter.get("name", "?"), batter["id"])
                )

        # Pitcher props
        for side, pid in (("home", game.home_pitcher_mlb_id), ("away", game.away_pitcher_mlb_id)):
            if not pid:
                continue
            stats = _stat(db, pid, "pitching")
            if not stats:
                continue
            opp_off = ctx.away_offense if side == "home" else ctx.home_offense
            win_prob = moneyline_home if side == "home" else 1 - moneyline_home
            pname = _player_name(db, pid)
            candidates.extend(
                engine.predict_pitcher_props(ctx, stats, opp_off, win_prob, game.game_pk, pname, pid)
            )

    saved = persist_candidates(db, day, candidates, home_team_by_pk)
    logger.info("engine pass complete", extra={"day": str(day), "games": len(games), "predictions": saved})
    return {"games": len(games), "predictions": saved}


def _player_name(db: Session, mlb_id: int) -> str:
    from app.infrastructure.db.models import Player

    row = db.scalar(select(Player).where(Player.mlb_id == mlb_id))
    return row.full_name if row else f"Pitcher {mlb_id}"
