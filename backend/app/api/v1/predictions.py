"""Prediction endpoints: daily board, tops per market, value bets, upsets, per game."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from app.api.deps import DbDep
from app.api.schemas import PredictionOut
from app.application.seed import ensure_today_seeded
from app.domain.entities import Market
from app.infrastructure.db.models import Prediction

router = APIRouter(prefix="/predictions", tags=["predictions"])

TOP_MARKET_MAP: dict[str, tuple[list[str], int]] = {
    "moneyline": ([Market.MONEYLINE.value], 10),
    "run-line": ([Market.RUN_LINE.value], 10),
    "over": ([Market.TOTAL_OVER.value], 10),
    "under": ([Market.TOTAL_UNDER.value], 10),
    "hits": ([Market.PLAYER_HITS.value], 20),
    "home-runs": ([Market.PLAYER_HOME_RUNS.value], 10),
    "rbi": ([Market.PLAYER_RBI.value], 10),
    "strikeouts": ([Market.PITCHER_STRIKEOUTS.value], 10),
    "total-bases": ([Market.PLAYER_TOTAL_BASES.value], 10),
    "stolen-bases": ([Market.PLAYER_STOLEN_BASES.value], 10),
    "first-inning": ([Market.FIRST_INNING.value], 10),
}


@router.get("/daily", response_model=list[PredictionOut])
def daily(db: DbDep, day: date | None = None, market: str | None = None,
          limit: int = Query(200, le=1000)) -> list[PredictionOut]:
    if day is None or day == date.today():
        ensure_today_seeded(db)  # serverless: populate on first request when empty
    q = select(Prediction).where(Prediction.game_date == (day or date.today()))
    if market:
        q = q.where(Prediction.market == market)
    rows = db.scalars(q.order_by(Prediction.confidence.desc()).limit(limit)).all()
    return [PredictionOut.model_validate(r) for r in rows]


@router.get("/top/{board}", response_model=list[PredictionOut])
def top_board(board: str, db: DbDep, day: date | None = None) -> list[PredictionOut]:
    if day is None or day == date.today():
        ensure_today_seeded(db)  # serverless: populate on first request when empty
    if board == "value-bets":
        rows = db.scalars(
            select(Prediction)
            .where(Prediction.game_date == (day or date.today()), Prediction.is_value_bet.is_(True))
            .order_by(Prediction.expected_value.desc()).limit(10)
        ).all()
        return [PredictionOut.model_validate(r) for r in rows]
    if board == "upsets":
        rows = db.scalars(
            select(Prediction)
            .where(Prediction.game_date == (day or date.today()),
                   Prediction.market == Market.MONEYLINE.value,
                   Prediction.probability.between(0.38, 0.5),
                   Prediction.book_odds.isnot(None))
            .order_by(Prediction.edge.desc().nullslast()).limit(10)
        ).all()
        return [PredictionOut.model_validate(r) for r in rows]
    if board not in TOP_MARKET_MAP:
        raise HTTPException(status_code=404, detail=f"Unknown board '{board}'")
    markets, top_n = TOP_MARKET_MAP[board]
    rows = db.scalars(
        select(Prediction)
        .where(Prediction.game_date == (day or date.today()), Prediction.market.in_(markets))
        .order_by((Prediction.probability * Prediction.confidence).desc())
        .limit(top_n)
    ).all()
    return [PredictionOut.model_validate(r) for r in rows]


@router.get("/game/{game_pk}", response_model=list[PredictionOut])
def by_game(game_pk: int, db: DbDep) -> list[PredictionOut]:
    rows = db.scalars(
        select(Prediction).where(Prediction.game_pk == game_pk).order_by(Prediction.market, Prediction.probability.desc())
    ).all()
    return [PredictionOut.model_validate(r) for r in rows]


@router.get("/player/{player_mlb_id}", response_model=list[PredictionOut])
def by_player(player_mlb_id: int, db: DbDep, day: date | None = None) -> list[PredictionOut]:
    rows = db.scalars(
        select(Prediction).where(
            Prediction.player_mlb_id == player_mlb_id,
            Prediction.game_date == (day or date.today()),
        ).order_by(Prediction.probability.desc())
    ).all()
    return [PredictionOut.model_validate(r) for r in rows]
