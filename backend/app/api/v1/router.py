"""Aggregated v1 router."""
from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import admin, auth, bankroll, cron, games, parlays, players, predictions, stats

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(games.router)
api_router.include_router(predictions.router)
api_router.include_router(parlays.router)
api_router.include_router(players.router)
api_router.include_router(bankroll.router)
api_router.include_router(stats.router)
api_router.include_router(admin.router)
api_router.include_router(cron.router)


@api_router.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok", "service": "evr-mlb-ai-pro"}
