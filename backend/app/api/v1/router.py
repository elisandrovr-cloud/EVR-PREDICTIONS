"""Aggregated v1 router."""
from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter
from sqlalchemy import func, select

from app.api.deps import DbDep
from app.api.v1 import (
    admin,
    agents,
    auth,
    bankroll,
    cron,
    games,
    odds,
    parlays,
    players,
    predictions,
    stats,
)
from app.core.config import settings
from app.infrastructure.db.models import Game, PlayerStat, Prediction, Team

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(agents.router)
api_router.include_router(odds.router)
api_router.include_router(games.router)
api_router.include_router(predictions.router)
api_router.include_router(parlays.router)
api_router.include_router(players.router)
api_router.include_router(bankroll.router)
api_router.include_router(stats.router)
api_router.include_router(admin.router)
api_router.include_router(cron.router)


@api_router.get("/health", tags=["health"])
def health(db: DbDep) -> dict[str, Any]:
    """Diagnostic endpoint: confirms the API is up, whether the database is
    reachable, how much data is loaded, and which optional integrations are on.
    Visit /api/v1/health in a browser to troubleshoot an empty deployment."""
    today = date.today()
    info: dict[str, Any] = {"status": "ok", "service": "evr-mlb-ai-pro", "date": str(today)}
    try:
        from app.infrastructure.db.session import ensure_schema

        ensure_schema()  # serverless: create tables if the lifespan didn't run
        hit_props = int(
            db.scalar(
                select(func.count(Prediction.id)).where(
                    Prediction.game_date == today, Prediction.market == "player_hits"
                )
            )
            or 0
        )
        info["database"] = {
            "connected": True,
            "teams": int(db.scalar(select(func.count(Team.id))) or 0),
            "games_today": int(db.scalar(select(func.count(Game.id)).where(Game.game_date == today)) or 0),
            "predictions_today": int(
                db.scalar(select(func.count(Prediction.id)).where(Prediction.game_date == today)) or 0
            ),
            "hit_props_today": hit_props,
            "batters_with_stats": int(
                db.scalar(
                    select(func.count(PlayerStat.id)).where(
                        PlayerStat.kind == "batting", PlayerStat.scope == "season"
                    )
                )
                or 0
            ),
        }
    except Exception as exc:  # noqa: BLE001 — report DB failure instead of 500
        info["status"] = "degraded"
        info["database"] = {"connected": False, "error": str(exc)[:200]}
    info["config"] = {
        "auto_seed": settings.AUTO_SEED,
        "cron_enabled": bool(settings.CRON_SECRET),
        "odds_enabled": bool(settings.ODDS_API_KEY),
        "weather_enabled": bool(settings.OPENWEATHER_API_KEY),
    }
    db_info = info["database"]
    if not db_info.get("connected"):
        info["hint"] = "Database unreachable. Set DATABASE_URL to a managed Postgres (Neon/Supabase)."
    elif db_info.get("games_today", 0) == 0:
        info["hint"] = (
            "No games loaded. If today has MLB games, open /api/v1/games/today to trigger auto-seed, "
            "or call /api/v1/cron/bootstrap with the CRON_SECRET header."
        )
    return info
