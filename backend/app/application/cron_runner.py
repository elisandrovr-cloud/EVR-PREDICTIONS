"""Synchronous pipeline orchestration for serverless / cron environments.

Celery beat drives the pipeline on a container host, but platforms like Vercel
have no always-on worker. These functions run the same use-cases end-to-end and
synchronously inside a single request, so an HTTP cron trigger can advance the
pipeline without a broker. The Celery tasks in ``app.workers.tasks`` remain the
async path for the container deployment.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import select

from app.application import ingestion
from app.application.agents import build_agent_parlays
from app.application.parlay_service import build_parlays_for_day
from app.application.prediction_service import generate_for_day
from app.application.results_service import close_day
from app.core.logging import get_logger
from app.infrastructure.db.models import Game
from app.infrastructure.db.session import SessionLocal

logger = get_logger(__name__)


def run_bootstrap() -> dict[str, Any]:
    """Teams + today's schedule + source health — the dawn/first-run job."""
    with SessionLocal() as db:
        teams = ingestion.sync_teams(db)
        sched = ingestion.sync_schedule(db, date.today())
        ingestion.record_source_statuses(db)
    return {"teams": teams, **sched}


def run_refresh() -> dict[str, Any]:
    """The 2-minute tick, synchronous: schedule/odds/weather → predictions → parlays."""
    today = date.today()
    with SessionLocal() as db:
        sched = ingestion.sync_schedule(db, today)
        odds = ingestion.sync_odds(db, today)
        weather = ingestion.sync_weather(db, today)
        ingestion.record_source_statuses(db)
        preds = generate_for_day(db, today)
        parlays = build_parlays_for_day(db, today)
        agents = build_agent_parlays(db, today)
    return {**sched, "odds_captured": odds, "weather_updates": weather,
            "predictions": preds.get("predictions", 0), "parlays": parlays, "agent_parlays": agents}


def run_slate_stats() -> dict[str, int]:
    """Pitcher/batter/bullpen/team-offense stats for everyone on today's slate."""
    pitchers = batters = 0
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
        # With fresh stats + recent form in place, regenerate props and re-run the debate.
        preds = generate_for_day(db, date.today())
        build_parlays_for_day(db, date.today())
        build_agent_parlays(db, date.today())
    return {"pitchers": pitchers, "batters": batters, "teams": len(team_ids),
            "predictions": preds.get("predictions", 0)}


def run_agent_cycle(only: list[str] | None = None) -> dict[str, Any]:
    """One full multi-agent monitoring cycle (the 1-minute heartbeat).

    Every agent is time-boxed internally, so the whole cycle stays inside a
    serverless function's budget; work that doesn't fit continues next minute.
    """
    from app.agents import SUPERVISOR

    with SessionLocal() as db:
        result = SUPERVISOR.run_cycle(db, day=date.today(), only=only)
        return result.as_dict()


def run_close_day() -> dict[str, Any]:
    """Nightly no-human-in-the-loop learning: settle, recalibrate, retrain, snapshot."""
    yesterday = date.today() - timedelta(days=1)
    with SessionLocal() as db:
        ingestion.sync_schedule(db, yesterday)  # ensure final scores are in
        return close_day(db, yesterday)
