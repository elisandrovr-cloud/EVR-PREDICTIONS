"""Player database: browse batters/pitchers, full profiles and side-by-side compare."""
from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select

from app.api.deps import DbDep
from app.api.schemas import ChangeOut, NewsOut, PlayerOut, PlayerProfileOut
from app.infrastructure.db.models import (
    Player,
    PlayerNews,
    PlayerStat,
    Prediction,
    RosterChange,
    Team,
)

router = APIRouter(prefix="/players", tags=["players"])

SORTABLE = {
    "name": Player.full_name,
    "age": Player.age,
    "team": Player.team_mlb_id,
    "position": Player.position,
}


def _team_names(db: DbDep) -> dict[int, str]:
    return {t.mlb_id: t.name for t in db.scalars(select(Team))}


def _to_out(row: Player, teams: dict[int, str]) -> PlayerOut:
    out = PlayerOut.model_validate(row)
    out.team = teams.get(row.team_mlb_id) if row.team_mlb_id else None
    return out


@router.get("", response_model=dict)
def list_players(
    db: DbDep,
    kind: str = Query("batters", pattern="^(batters|pitchers|all)$"),
    q: str | None = None,
    team_mlb_id: int | None = None,
    status: str | None = None,
    sort: str = Query("name", pattern="^(name|age|team|position)$"),
    order: str = Query("asc", pattern="^(asc|desc)$"),
    limit: int = Query(50, le=200),
    offset: int = 0,
) -> dict[str, Any]:
    """Searchable, filterable, sortable directory split into batters and pitchers."""
    stmt = select(Player)
    count_stmt = select(func.count(Player.id))
    if kind != "all":
        is_pitcher = kind == "pitchers"
        stmt = stmt.where(Player.is_pitcher.is_(is_pitcher))
        count_stmt = count_stmt.where(Player.is_pitcher.is_(is_pitcher))
    if q:
        stmt = stmt.where(Player.full_name.ilike(f"%{q}%"))
        count_stmt = count_stmt.where(Player.full_name.ilike(f"%{q}%"))
    if team_mlb_id:
        stmt = stmt.where(Player.team_mlb_id == team_mlb_id)
        count_stmt = count_stmt.where(Player.team_mlb_id == team_mlb_id)
    if status:
        stmt = stmt.where(Player.roster_status == status)
        count_stmt = count_stmt.where(Player.roster_status == status)

    column = SORTABLE.get(sort, Player.full_name)
    stmt = stmt.order_by(column.desc() if order == "desc" else column.asc())
    rows = db.scalars(stmt.offset(offset).limit(limit)).all()
    teams = _team_names(db)
    return {
        "total": int(db.scalar(count_stmt) or 0),
        "limit": limit,
        "offset": offset,
        "items": [_to_out(r, teams) for r in rows],
    }


@router.get("/search")
def search(db: DbDep, q: str = Query(min_length=2)) -> list[dict[str, Any]]:
    rows = db.scalars(select(Player).where(Player.full_name.ilike(f"%{q}%")).limit(25)).all()
    return [
        {"mlb_id": p.mlb_id, "name": p.full_name, "team_mlb_id": p.team_mlb_id,
         "position": p.position, "bats": p.bats, "throws": p.throws,
         "is_pitcher": p.is_pitcher, "photo_url": p.photo_url}
        for p in rows
    ]


@router.get("/compare")
def compare(db: DbDep, ids: str = Query(description="Comma-separated MLB player ids")) -> dict[str, Any]:
    """Side-by-side comparison of up to 4 players."""
    try:
        wanted = [int(x) for x in ids.split(",") if x.strip()][:4]
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="ids must be integers") from exc
    if len(wanted) < 2:
        raise HTTPException(status_code=422, detail="Provide at least two player ids")
    teams = _team_names(db)
    out = []
    for mlb_id in wanted:
        row = db.scalar(select(Player).where(Player.mlb_id == mlb_id))
        if row is None:
            continue
        stat = db.scalar(
            select(PlayerStat).where(
                PlayerStat.player_mlb_id == mlb_id,
                PlayerStat.kind == ("pitching" if row.is_pitcher else "batting"),
                PlayerStat.scope == "season",
            )
        )
        out.append({"player": _to_out(row, teams), "stats": (stat.stats if stat else {})})
    return {"players": out}


@router.get("/{mlb_id}/stats")
def stats(mlb_id: int, db: DbDep) -> dict[str, Any]:
    player = db.scalar(select(Player).where(Player.mlb_id == mlb_id))
    snapshots = db.scalars(select(PlayerStat).where(PlayerStat.player_mlb_id == mlb_id)).all()
    if player is None and not snapshots:
        raise HTTPException(status_code=404, detail="Player not found")
    return {
        "player": {
            "mlb_id": mlb_id,
            "name": player.full_name if player else None,
            "position": player.position if player else None,
        },
        "snapshots": {f"{s.kind}:{s.scope}": s.stats for s in snapshots},
    }


@router.get("/{mlb_id}/profile", response_model=PlayerProfileOut)
def profile(mlb_id: int, db: DbDep) -> PlayerProfileOut:
    """Everything the agents know about one player, for their profile page."""
    player = db.scalar(select(Player).where(Player.mlb_id == mlb_id))
    if player is None:
        raise HTTPException(status_code=404, detail="Player not found")
    teams = _team_names(db)
    snapshots = db.scalars(select(PlayerStat).where(PlayerStat.player_mlb_id == mlb_id)).all()
    kind = "pitching" if player.is_pitcher else "batting"
    season = next((s.stats for s in snapshots if s.kind == kind and s.scope == "season"), {})
    splits = {f"{s.kind}:{s.scope}": s.stats for s in snapshots if s.scope != "season"}
    predictions = db.scalars(
        select(Prediction)
        .where(Prediction.player_mlb_id == mlb_id, Prediction.game_date == date.today())
        .order_by(Prediction.probability.desc())
    ).all()
    news = db.scalars(
        select(PlayerNews)
        .where(PlayerNews.player_mlb_id == mlb_id)
        .order_by(PlayerNews.published_at.desc())
        .limit(10)
    ).all()
    changes = db.scalars(
        select(RosterChange)
        .where(RosterChange.player_mlb_id == mlb_id)
        .order_by(RosterChange.detected_at.desc())
        .limit(10)
    ).all()
    return PlayerProfileOut(
        player=_to_out(player, teams),
        stats=season,
        splits=splits,
        last5=list(season.get("last5_games", [])),
        predictions=[
            {
                "id": p.id, "market": p.market, "selection": p.selection, "line": p.line,
                "probability": p.probability, "confidence": p.confidence,
                "book_odds": p.book_odds, "fair_odds": p.fair_odds,
                "is_value_bet": p.is_value_bet, "explanation": p.explanation,
            }
            for p in predictions
        ],
        news=[NewsOut.model_validate(n) for n in news],
        changes=[ChangeOut.model_validate(c) for c in changes],
    )
