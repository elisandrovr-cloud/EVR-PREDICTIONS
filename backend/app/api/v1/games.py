"""Games endpoints: schedule, live games, detail, lineups, weather, umpire, odds."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.api.deps import DbDep
from app.api.schemas import GameOut, OddsQuoteOut, TeamOut
from app.infrastructure.cache.redis_client import cache_get, cache_set
from app.infrastructure.db.models import Game, OddsQuote, Team

router = APIRouter(prefix="/games", tags=["games"])


def _with_team_names(db: DbDep, games: list[Game]) -> list[GameOut]:
    teams = {t.mlb_id: t.name for t in db.scalars(select(Team)).all()}
    out = []
    for g in games:
        row = GameOut.model_validate(g)
        row.home_team = teams.get(g.home_team_mlb_id)
        row.away_team = teams.get(g.away_team_mlb_id)
        out.append(row)
    return out


@router.get("/today", response_model=list[GameOut])
def today(db: DbDep) -> list[GameOut]:
    games = db.scalars(
        select(Game).where(Game.game_date == date.today()).order_by(Game.start_time)
    ).all()
    return _with_team_names(db, games)


@router.get("/live", response_model=list[GameOut])
def live(db: DbDep) -> list[GameOut]:
    games = db.scalars(select(Game).where(Game.status == "live").order_by(Game.start_time)).all()
    return _with_team_names(db, games)


@router.get("/calendar/{day}", response_model=list[GameOut])
def calendar(day: date, db: DbDep) -> list[GameOut]:
    games = db.scalars(select(Game).where(Game.game_date == day).order_by(Game.start_time)).all()
    return _with_team_names(db, games)


@router.get("/teams", response_model=list[TeamOut])
def teams(db: DbDep) -> list[TeamOut]:
    cached = cache_get("teams:all")
    if cached:
        return [TeamOut(**t) for t in cached]
    rows = db.scalars(select(Team).order_by(Team.name)).all()
    result = [TeamOut.model_validate(t) for t in rows]
    cache_set("teams:all", [r.model_dump() for r in result], ttl_seconds=600)
    return result


@router.get("/{game_pk}", response_model=GameOut)
def detail(game_pk: int, db: DbDep) -> GameOut:
    game = db.scalar(select(Game).where(Game.game_pk == game_pk))
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")
    return _with_team_names(db, [game])[0]


@router.get("/{game_pk}/odds", response_model=list[OddsQuoteOut])
def game_odds(game_pk: int, db: DbDep, limit: int = 200) -> list[OddsQuoteOut]:
    rows = db.scalars(
        select(OddsQuote).where(OddsQuote.game_pk == game_pk)
        .order_by(OddsQuote.captured_at.desc()).limit(min(limit, 1000))
    ).all()
    return [OddsQuoteOut.model_validate(r) for r in rows]
