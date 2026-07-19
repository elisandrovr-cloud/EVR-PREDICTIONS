"""Lazy self-seeding for serverless deployments.

On a container host the Celery worker keeps the database populated. On Vercel
there is no always-on worker, so the DB would stay empty and the UI would show
nothing until a cron fired. This module lets a read request populate today's
slate on demand: if there are no games yet, it pulls teams + schedule and
generates game-level predictions synchronously, then returns.

It is deliberately cheap: it makes at most a couple of MLB Stats API calls and
runs the engine only on games (player props need per-player stat snapshots that
the stats cron fills in later). Everything is idempotent and best-effort — it
never raises into the request.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.application import ingestion
from app.application.parlay_service import build_parlays_for_day
from app.application.prediction_service import generate_for_day
from app.core.config import settings
from app.core.logging import get_logger
from app.infrastructure.db.models import Game, Prediction, Team
from app.infrastructure.providers.registry import ProviderRegistry, get_registry

logger = get_logger(__name__)


def _count(db: Session, model, *conditions) -> int:
    stmt = select(func.count(model.id))
    for cond in conditions:
        stmt = stmt.where(cond)
    return int(db.scalar(stmt) or 0)


def ensure_today_seeded(db: Session, registry: ProviderRegistry | None = None) -> dict[str, Any]:
    """Populate today's slate if empty. Safe to call on every read; cheap when
    already populated (two indexed COUNTs). Never raises."""
    if not settings.AUTO_SEED:
        return {"seeded": False, "reason": "disabled"}
    reg = registry or get_registry()
    today = date.today()
    summary: dict[str, Any] = {"seeded": False}
    try:
        # On serverless the ASGI lifespan may not run, so guarantee the schema.
        from app.infrastructure.db.session import ensure_schema

        ensure_schema()
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
            summary["seeded"] = True
        return summary
    except Exception as exc:  # noqa: BLE001 — seeding must never break a read
        logger.warning("auto-seed failed", extra={"error": str(exc)})
        return {"seeded": False, "error": str(exc)[:200]}
