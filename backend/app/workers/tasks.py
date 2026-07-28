"""Celery tasks — the autonomous pipeline."""
from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select

from app.core.logging import configure_logging, get_logger
from app.domain.events import EVENTS_CHANNEL
from app.infrastructure.cache.redis_client import get_redis
from app.infrastructure.db.models import Base, Game
from app.infrastructure.db.session import SessionLocal, engine
from app.workers.celery_app import celery_app

configure_logging()
logger = get_logger(__name__)

Base.metadata.create_all(bind=engine)


@celery_app.task(name="app.workers.tasks.bootstrap_reference_data")
def bootstrap_reference_data() -> dict[str, Any]:
    """Teams + today's schedule + rosters, run at dawn and on demand."""
    from app.application import ingestion

    with SessionLocal() as db:
        teams = ingestion.sync_teams(db)
        sched = ingestion.sync_schedule(db, date.today())
        ingestion.record_source_statuses(db)
    refresh_slate_stats.delay()
    return {"teams": teams, **sched}


@celery_app.task(name="app.workers.tasks.refresh_all_data")
def refresh_all_data() -> dict[str, Any]:
    """The 2-minute tick: schedule/lineups/scores + odds + weather, then re-predict."""
    from app.application import ingestion

    with SessionLocal() as db:
        sched = ingestion.sync_schedule(db, date.today())
        odds = ingestion.sync_odds(db, date.today())
        weather = ingestion.sync_weather(db, date.today())
        ingestion.record_source_statuses(db)
    generate_predictions.delay()
    drain_domain_events.delay()
    return {**sched, "odds_captured": odds, "weather_updates": weather}


@celery_app.task(name="app.workers.tasks.refresh_slate_stats")
def refresh_slate_stats() -> dict[str, int]:
    """Pitcher/batter/bullpen/team-offense stats for everyone on today's slate."""
    from app.application import ingestion

    pitchers = 0
    batters = 0
    with SessionLocal() as db:
        games = db.scalars(select(Game).where(Game.game_date == date.today())).all()
        team_ids: set[int] = set()
        for g in games:
            team_ids.update({g.home_team_mlb_id, g.away_team_mlb_id})
            for pid in (g.home_pitcher_mlb_id, g.away_pitcher_mlb_id):
                if pid:
                    try:
                        ingestion.sync_pitcher_stats(db, pid)
                        pitchers += 1
                    except Exception:  # noqa: BLE001 — one bad player must not stop the slate
                        logger.warning("pitcher stat sync failed", extra={"player": pid})
            for side in ("home", "away"):
                for batter in (g.lineups or {}).get(side, []):
                    if batter.get("id"):
                        try:
                            ingestion.sync_batter_stats(db, batter["id"])
                            ingestion.sync_batter_recent_form(db, batter["id"])
                            batters += 1
                        except Exception:  # noqa: BLE001
                            logger.warning("batter stat sync failed", extra={"player": batter.get("id")})
        for tid in team_ids:
            try:
                ingestion.sync_team_offense(db, tid)
                ingestion.sync_bullpen(db, tid)
            except Exception:  # noqa: BLE001
                logger.warning("team stat sync failed", extra={"team": tid})
    return {"pitchers": pitchers, "batters": batters, "teams": len(team_ids)}


@celery_app.task(name="app.workers.tasks.run_agent_cycle")
def run_agent_cycle(only: list[str] | None = None) -> dict[str, Any]:
    """One full pass of the multi-agent monitoring cycle (every minute)."""
    from app.agents import SUPERVISOR

    with SessionLocal() as db:
        return SUPERVISOR.run_cycle(db, day=date.today(), only=only).as_dict()


@celery_app.task(name="app.workers.tasks.generate_predictions")
def generate_predictions(game_pk: int | None = None) -> dict[str, int]:
    from app.application.prediction_service import generate_for_day

    with SessionLocal() as db:
        return generate_for_day(db, date.today(), only_game_pk=game_pk)


@celery_app.task(name="app.workers.tasks.build_parlays")
def build_parlays() -> dict[str, int]:
    from app.application.agents import build_agent_parlays
    from app.application.parlay_service import build_parlays_for_day

    with SessionLocal() as db:
        parlays = build_parlays_for_day(db, date.today())
        agents = build_agent_parlays(db, date.today())
        return {"parlays": parlays, "agent_parlays": agents}


@celery_app.task(name="app.workers.tasks.drain_domain_events")
def drain_domain_events() -> dict[str, int]:
    """Consume queued domain events; lineup/pitcher changes recompute that game NOW."""
    r = get_redis()
    handled = 0
    recompute: set[int] = set()
    close_needed = False
    try:
        # events are mirrored into a list for reliable draining
        while True:
            raw = r.lpop("evr:events:queue")
            if raw is None:
                break
            event = json.loads(raw)
            name = event.get("event")
            game_pk = (event.get("data") or {}).get("game_pk")
            if name in ("lineup_confirmed", "pitcher_changed") and game_pk:
                recompute.add(int(game_pk))
            elif name == "game_final":
                close_needed = True
            handled += 1
    except Exception:  # noqa: BLE001
        pass
    for pk in recompute:
        generate_predictions.delay(game_pk=pk)
    if close_needed:
        settle_finished_games.delay()
    return {"handled": handled, "recomputed_games": len(recompute)}


@celery_app.task(name="app.workers.tasks.settle_finished_games")
def settle_finished_games() -> dict[str, int]:
    """Settle any game already final today (without waiting for the nightly close)."""
    from app.application.results_service import settle_game

    settled = 0
    with SessionLocal() as db:
        games = db.scalars(
            select(Game).where(Game.game_date == date.today(), Game.status == "final")
        ).all()
        for g in games:
            settled += settle_game(db, g)
    return {"settled": settled}


@celery_app.task(name="app.workers.tasks.close_previous_day")
def close_previous_day() -> dict[str, Any]:
    """Nightly learning: settle yesterday, recalibrate weights, retrain, snapshot."""
    from app.application import ingestion
    from app.application.results_service import close_day

    yesterday = date.today() - timedelta(days=1)
    with SessionLocal() as db:
        ingestion.sync_schedule(db, yesterday)  # ensure final scores are in
        return close_day(db, yesterday)
