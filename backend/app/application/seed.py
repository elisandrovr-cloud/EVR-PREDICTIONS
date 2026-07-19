"""Lazy self-seeding for serverless deployments.

On a container host the Celery worker keeps the database populated. On Vercel
there is no always-on worker, so read requests populate the data themselves:

1. Light seed (fast, every empty request): teams + today's schedule + game-level
   predictions + parlays + the agent debate for game/mixed categories.
2. Progressive stat backfill (time-boxed, throttled): each request syncs a small
   batch of player/team stats — pitchers first, then batters by lineup slot — and
   regenerates the games that just became ready so player props, the hits board
   and the hits/strikeouts agent parlays fill in over a few page loads. Bounded by
   item count AND wall-clock time so it never trips a serverless timeout.

Everything is idempotent and best-effort — it never raises into a read.
"""
from __future__ import annotations

import time
from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.application import ingestion
from app.application.agents import build_agent_parlays
from app.application.parlay_service import build_parlays_for_day
from app.application.prediction_service import generate_for_day
from app.core.config import settings
from app.core.logging import get_logger
from app.infrastructure.db.models import BullpenStat, Game, PlayerStat, Prediction, Team
from app.infrastructure.providers.registry import ProviderRegistry, get_registry

logger = get_logger(__name__)

_last_backfill = 0.0  # per-process throttle for the stat backfill


def _count(db: Session, model, *conditions) -> int:
    stmt = select(func.count(model.id))
    for cond in conditions:
        stmt = stmt.where(cond)
    return int(db.scalar(stmt) or 0)


def ensure_today_seeded(db: Session, registry: ProviderRegistry | None = None) -> dict[str, Any]:
    """Populate today's slate if empty, then advance the stat backfill. Safe to
    call on every read; cheap once fully populated. Never raises."""
    if not settings.AUTO_SEED:
        return {"seeded": False, "reason": "disabled"}
    reg = registry or get_registry()
    today = date.today()
    summary: dict[str, Any] = {"seeded": False}
    try:
        from app.infrastructure.db.session import ensure_schema

        ensure_schema()  # serverless: the ASGI lifespan may not run
        if _count(db, Team) == 0:
            summary["teams"] = ingestion.sync_teams(db, reg)
        if _count(db, Game, Game.game_date == today) == 0:
            summary["schedule"] = ingestion.sync_schedule(db, today, reg)
            try:
                ingestion.sync_weather(db, today, reg)
            except Exception:  # noqa: BLE001 — weather is optional
                pass
        if _count(db, Game, Game.game_date == today) > 0 and _count(
            db, Prediction, Prediction.game_date == today
        ) == 0:
            summary["predictions"] = generate_for_day(db, today)
            summary["parlays"] = build_parlays_for_day(db, today)
            summary["agent_parlays"] = build_agent_parlays(db, today)
            summary["seeded"] = True

        # Phase 2: progressive stat backfill → props, hits board, hits/K parlays.
        if settings.AUTO_SEED_STATS:
            summary["backfilled"] = _maybe_backfill(db, reg, today)
        return summary
    except Exception as exc:  # noqa: BLE001 — seeding must never break a read
        logger.warning("auto-seed failed", extra={"error": str(exc)})
        return {"seeded": False, "error": str(exc)[:200]}


def _maybe_backfill(db: Session, reg: ProviderRegistry, today: date) -> int:
    """Throttled per process so overlapping requests don't all fetch at once."""
    global _last_backfill
    now = time.monotonic()
    if now - _last_backfill < settings.SEED_BACKFILL_MIN_INTERVAL:
        return 0
    _last_backfill = now
    processed = _advance_backfill(db, reg, today)
    if processed:
        _regenerate_ready_games(db, today)
    return processed


def _advance_backfill(db: Session, reg: ProviderRegistry, today: date) -> int:
    """Sync a time-boxed batch of missing player/team stats. Pitchers first (few,
    gate strikeout props), then batters by lineup slot, then team offense/bullpen."""
    games = db.scalars(select(Game).where(Game.game_date == today, Game.status != "final")).all()
    if not games:
        return 0
    have_pitch = {r.player_mlb_id for r in db.scalars(
        select(PlayerStat).where(PlayerStat.kind == "pitching", PlayerStat.scope == "season"))}
    have_bat = {r.player_mlb_id for r in db.scalars(
        select(PlayerStat).where(PlayerStat.kind == "batting", PlayerStat.scope == "season"))}
    have_team = {r.player_mlb_id for r in db.scalars(
        select(PlayerStat).where(PlayerStat.kind == "team", PlayerStat.scope == "offense"))}
    have_pen = {r.team_mlb_id for r in db.scalars(select(BullpenStat))}

    pitchers: list[int] = []
    batters: list[int] = []
    teams: list[int] = []
    for g in games:
        for pid in (g.home_pitcher_mlb_id, g.away_pitcher_mlb_id):
            if pid and pid not in have_pitch and pid not in pitchers:
                pitchers.append(pid)
        for side in ("home", "away"):
            for slot in (g.lineups or {}).get(side, []):
                bid = slot.get("id")
                if bid and bid not in have_bat and bid not in batters:
                    batters.append(bid)
        for tid in (g.home_team_mlb_id, g.away_team_mlb_id):
            if tid and (tid not in have_team or tid not in have_pen) and tid not in teams:
                teams.append(tid)

    start = time.monotonic()
    processed = 0
    limit = settings.SEED_BACKFILL_MAX_ITEMS
    budget = settings.SEED_BACKFILL_SECONDS

    def over_budget() -> bool:
        return processed >= limit or (time.monotonic() - start) > budget

    for tid in teams:  # team context first — cheap and improves every prediction
        if over_budget():
            break
        try:
            ingestion.sync_team_offense(db, tid, reg)
            ingestion.sync_bullpen(db, tid, reg)
            processed += 1
        except Exception:  # noqa: BLE001
            logger.warning("team backfill failed", extra={"team": tid})
    for pid in pitchers:
        if over_budget():
            break
        try:
            ingestion.sync_pitcher_stats(db, pid, reg)
            processed += 1
        except Exception:  # noqa: BLE001
            logger.warning("pitcher backfill failed", extra={"player": pid})
    for bid in batters:
        if over_budget():
            break
        try:
            ingestion.sync_batter_stats(db, bid, reg)
            ingestion.sync_batter_recent_form(db, bid, reg)
            processed += 1
        except Exception:  # noqa: BLE001
            logger.warning("batter backfill failed", extra={"player": bid})
    return processed


def _game_ready_for_props(db: Session, game: Game) -> bool:
    have_bat = {r.player_mlb_id for r in db.scalars(
        select(PlayerStat).where(PlayerStat.kind == "batting", PlayerStat.scope == "season"))}
    have_pitch = {r.player_mlb_id for r in db.scalars(
        select(PlayerStat).where(PlayerStat.kind == "pitching", PlayerStat.scope == "season"))}
    pitchers_ready = all(
        pid in have_pitch for pid in (game.home_pitcher_mlb_id, game.away_pitcher_mlb_id) if pid
    )
    lineup_ids = [s.get("id") for side in ("home", "away") for s in (game.lineups or {}).get(side, []) if s.get("id")]
    if not lineup_ids:
        return pitchers_ready  # pitcher props can still be generated
    covered = sum(1 for bid in lineup_ids if bid in have_bat)
    return pitchers_ready and covered >= min(6, len(lineup_ids))


def _has_props(db: Session, game_pk: int) -> bool:
    return _count(db, Prediction, Prediction.game_pk == game_pk, Prediction.market == "player_hits") > 0


def _regenerate_ready_games(db: Session, today: date) -> None:
    """Regenerate props for games whose stats just became available, then rebuild
    parlays + the agent debate over the enriched pool."""
    games = db.scalars(select(Game).where(Game.game_date == today, Game.status != "final")).all()
    changed = False
    for g in games:
        if not _has_props(db, g.game_pk) and _game_ready_for_props(db, g):
            generate_for_day(db, today, only_game_pk=g.game_pk)
            changed = True
    if changed:
        build_parlays_for_day(db, today)
        build_agent_parlays(db, today)
