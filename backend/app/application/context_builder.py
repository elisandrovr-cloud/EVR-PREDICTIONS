"""Assembles the denormalized GameContext the engine consumes, from DB snapshots."""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.db.models import BullpenStat, Game, PlayerStat, Team
from app.infrastructure.providers.static_data import park_factor, umpire_tendency
from app.ml.features import GameContext


def _stat(db: Session, player_id: int | None, kind: str, scope: str = "season") -> dict[str, Any] | None:
    if not player_id:
        return None
    row = db.scalar(
        select(PlayerStat).where(
            PlayerStat.player_mlb_id == player_id, PlayerStat.kind == kind, PlayerStat.scope == scope
        )
    )
    return row.stats if row else None


def _bullpen(db: Session, team_id: int) -> dict[str, Any] | None:
    row = db.scalar(select(BullpenStat).where(BullpenStat.team_mlb_id == team_id, BullpenStat.scope == "season"))
    return row.stats if row else None


def _team_offense(db: Session, team_id: int) -> dict[str, Any] | None:
    row = db.scalar(
        select(PlayerStat).where(
            PlayerStat.player_mlb_id == team_id, PlayerStat.kind == "team", PlayerStat.scope == "offense"
        )
    )
    return row.stats if row else None


def build_context(db: Session, game: Game) -> GameContext:
    home = db.scalar(select(Team).where(Team.mlb_id == game.home_team_mlb_id))
    away = db.scalar(select(Team).where(Team.mlb_id == game.away_team_mlb_id))
    umpire_data = dict(umpire_tendency((game.umpire or {}).get("name")))
    umpire_data["name"] = (game.umpire or {}).get("name", "TBD")
    home_off = _team_offense(db, game.home_team_mlb_id) or {}
    away_off = _team_offense(db, game.away_team_mlb_id) or {}
    return GameContext(
        game_pk=game.game_pk,
        home_team=home.name if home else str(game.home_team_mlb_id),
        away_team=away.name if away else str(game.away_team_mlb_id),
        home_elo=home.elo if home else 1500.0,
        away_elo=away.elo if away else 1500.0,
        home_sp=_stat(db, game.home_pitcher_mlb_id, "pitching"),
        away_sp=_stat(db, game.away_pitcher_mlb_id, "pitching"),
        home_bullpen=_bullpen(db, game.home_team_mlb_id),
        away_bullpen=_bullpen(db, game.away_team_mlb_id),
        home_offense=home_off,
        away_offense=away_off,
        park={**park_factor(game.venue_name)},
        weather=game.weather or {},
        umpire=umpire_data,
        home_form_l10=float(home_off.get("form_l10", 0.5)) if home_off else 0.5,
        away_form_l10=float(away_off.get("form_l10", 0.5)) if away_off else 0.5,
        lineup_confirmed=game.lineup_confirmed,
    )
