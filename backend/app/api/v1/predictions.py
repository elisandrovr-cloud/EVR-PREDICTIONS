"""Prediction endpoints: daily board, tops per market, value bets, upsets, per game."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from app.api.deps import DbDep
from app.api.schemas import HitsBoardRow, PredictionOut
from app.application.seed import ensure_today_seeded
from app.domain.entities import Market
from app.infrastructure.db.models import Player, PlayerStat, Prediction, Team

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


@router.get("/hits-board", response_model=list[HitsBoardRow])
def hits_board(db: DbDep, day: date | None = None) -> list[HitsBoardRow]:
    """Every batter playing today ranked by hit probability (highest first), with
    each batter's hit total over their last 5 games."""
    d = day or date.today()
    if d == date.today():
        ensure_today_seeded(db)
    preds = db.scalars(
        select(Prediction)
        .where(
            Prediction.game_date == d,
            Prediction.market == Market.PLAYER_HITS.value,
            Prediction.line <= 0.5,  # the "1+ hit" line
        )
        .order_by(Prediction.probability.desc())
    ).all()
    if not preds:
        return []
    player_ids = [p.player_mlb_id for p in preds if p.player_mlb_id]
    players = {pl.mlb_id: pl for pl in db.scalars(select(Player).where(Player.mlb_id.in_(player_ids)))}
    teams = {t.mlb_id: t.name for t in db.scalars(select(Team))}
    stats = {
        s.player_mlb_id: s.stats
        for s in db.scalars(
            select(PlayerStat).where(
                PlayerStat.player_mlb_id.in_(player_ids),
                PlayerStat.kind == "batting",
                PlayerStat.scope == "season",
            )
        )
    }
    rows: list[HitsBoardRow] = []
    for p in preds:
        pl = players.get(p.player_mlb_id or 0)
        st = stats.get(p.player_mlb_id or 0, {})
        name = pl.full_name if pl else p.selection.replace(" 1+ hit", "")
        rows.append(HitsBoardRow(
            player_mlb_id=p.player_mlb_id,
            player=name,
            team=teams.get(pl.team_mlb_id) if pl and pl.team_mlb_id else None,
            game_pk=p.game_pk,
            probability=p.probability,
            fair_odds=p.fair_odds,
            book_odds=p.book_odds,
            confidence=p.confidence,
            is_value_bet=p.is_value_bet,
            explanation=p.explanation,
            last5_hits=list(st.get("last5_hits", [])),
            last5_total=int(st.get("last5_total_hits", 0)),
        ))
    return rows


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
