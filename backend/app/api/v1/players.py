"""Player endpoints: search, stat snapshots, probability profiles."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from app.api.deps import DbDep
from app.infrastructure.db.models import Player, PlayerStat

router = APIRouter(prefix="/players", tags=["players"])


@router.get("/search")
def search(db: DbDep, q: str = Query(min_length=2)) -> list[dict[str, Any]]:
    rows = db.scalars(
        select(Player).where(Player.full_name.ilike(f"%{q}%")).limit(25)
    ).all()
    return [
        {"mlb_id": p.mlb_id, "name": p.full_name, "team_mlb_id": p.team_mlb_id,
         "position": p.position, "bats": p.bats, "throws": p.throws}
        for p in rows
    ]


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
