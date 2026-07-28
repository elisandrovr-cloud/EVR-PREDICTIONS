"""HTTP-triggered cron jobs for serverless schedulers (e.g. Vercel Cron).

Vercel Cron sends a GET to each configured path with `Authorization: Bearer
<CRON_SECRET>` (the project env var). We accept GET and POST, guard with that
shared secret, and run the corresponding synchronous pipeline job.
"""
from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, Header, HTTPException

from app.application import cron_runner
from app.core.config import settings

router = APIRouter(prefix="/cron", tags=["cron"])

JOBS: dict[str, Callable[[], dict[str, Any]]] = {
    "bootstrap": cron_runner.run_bootstrap,
    "refresh": cron_runner.run_refresh,
    "stats": cron_runner.run_slate_stats,
    "close-day": cron_runner.run_close_day,
    # The 1-minute multi-agent heartbeat (roster, lineups, players, odds, news…).
    "agents": cron_runner.run_agent_cycle,
    # Lightweight variants for tight function budgets.
    "agents-watch": lambda: cron_runner.run_agent_cycle(
        only=["roster_intelligence", "lineup_intelligence", "news_intelligence"]
    ),
}


def _authorize(authorization: str | None) -> None:
    if not settings.CRON_SECRET:
        raise HTTPException(status_code=503, detail="Cron disabled: set CRON_SECRET to enable")
    if authorization != f"Bearer {settings.CRON_SECRET}":
        raise HTTPException(status_code=401, detail="Invalid cron credentials")


def _run(job: str, authorization: str | None) -> dict[str, Any]:
    _authorize(authorization)
    fn = JOBS.get(job)
    if fn is None:
        raise HTTPException(status_code=404, detail=f"Unknown cron job '{job}'")
    return {"job": job, "result": fn()}


@router.get("/{job}")
def run_cron_job_get(job: str, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    """Vercel Cron triggers jobs with a GET request."""
    return _run(job, authorization)


@router.post("/{job}")
def run_cron_job_post(job: str, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    """Manual/programmatic trigger."""
    return _run(job, authorization)
