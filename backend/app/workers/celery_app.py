"""Celery application + beat schedule.

Cadence:
  every 2 min  — refresh schedule/lineups/odds/weather, then regenerate predictions
  every 30 min — refresh player/team/bullpen stats for today's slate
  06:00 UTC    — bootstrap reference data (teams, park factors) for the new day
  08:30 UTC    — close previous day: settle, recalibrate, retrain (nightly learning)
Event-driven: a dedicated listener task consumes Redis pub/sub domain events so a
confirmed lineup or pitcher change recomputes that game immediately.
"""
from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery(
    "evr",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    result_expires=3600,
)

celery_app.conf.beat_schedule = {
    # The multi-agent heartbeat: rosters, lineups, players, prices and news.
    "agent-cycle-every-minute": {
        "task": "app.workers.tasks.run_agent_cycle",
        "schedule": float(settings.AGENT_MONITOR_INTERVAL),
    },
    "refresh-data-every-2-min": {
        "task": "app.workers.tasks.refresh_all_data",
        "schedule": float(settings.DATA_REFRESH_SECONDS),
    },
    "stats-refresh-every-30-min": {
        "task": "app.workers.tasks.refresh_slate_stats",
        "schedule": crontab(minute="*/30"),
    },
    "event-listener-heartbeat": {
        "task": "app.workers.tasks.drain_domain_events",
        "schedule": 30.0,
    },
    "bootstrap-daily": {
        "task": "app.workers.tasks.bootstrap_reference_data",
        "schedule": crontab(hour=6, minute=0),
    },
    "close-day-nightly-learning": {
        "task": "app.workers.tasks.close_previous_day",
        "schedule": crontab(hour=8, minute=30),
    },
    "build-parlays": {
        "task": "app.workers.tasks.build_parlays",
        "schedule": crontab(minute="*/15"),
    },
}
