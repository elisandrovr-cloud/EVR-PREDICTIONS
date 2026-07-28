"""Agent contract: how every specialized agent reports work and answers questions."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.infrastructure.db.models import AgentRun, RosterChange
from app.infrastructure.providers.registry import ProviderRegistry

logger = get_logger(__name__)


@dataclass
class AgentReport:
    """Result of one agent cycle — persisted to `agent_runs`."""

    agent: str
    status: str = "ok"  # ok | error | skipped
    summary: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    items_processed: int = 0
    changes_detected: int = 0
    duration_ms: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "agent": self.agent,
            "status": self.status,
            "summary": self.summary,
            "details": self.details,
            "items_processed": self.items_processed,
            "changes_detected": self.changes_detected,
            "duration_ms": round(self.duration_ms, 1),
        }


@dataclass
class AgentInsight:
    """One agent's contribution to a chat answer."""

    agent: str
    title: str
    headline: str
    bullets: list[str] = field(default_factory=list)
    picks: list[dict[str, Any]] = field(default_factory=list)
    confidence: float = 0.5

    def as_dict(self) -> dict[str, Any]:
        return {
            "agent": self.agent,
            "title": self.title,
            "headline": self.headline,
            "bullets": self.bullets,
            "picks": self.picks,
            "confidence": round(self.confidence, 3),
        }


@dataclass
class ChatQuery:
    """A parsed user question handed to the agents."""

    raw: str
    intent: str
    count: int | None = None
    market: str | None = None
    player_name: str | None = None
    day: date | None = None


class BaseAgent:
    """Base class for the eight specialized agents.

    Subclasses implement `work()` (monitoring cycle) and optionally `insight()`
    (chat contribution). `execute()` wraps `work()` with timing, error isolation
    and persistence so one failing agent never stops the others.
    """

    name: str = "base"
    title: str = "Agente"
    description: str = ""
    specialties: tuple[str, ...] = ()
    cycle_seconds: int = 60  # how often this agent wants to run

    # ── monitoring cycle ────────────────────────────────────────────────────
    def work(self, db: Session, reg: ProviderRegistry, day: date) -> AgentReport:  # pragma: no cover
        raise NotImplementedError

    def execute(self, db: Session, reg: ProviderRegistry, day: date) -> AgentReport:
        started = time.perf_counter()
        try:
            report = self.work(db, reg, day)
        except Exception as exc:  # noqa: BLE001 — isolate agent failures
            logger.warning("agent failed", extra={"agent": self.name, "error": str(exc)})
            report = AgentReport(agent=self.name, status="error", summary=f"Error: {str(exc)[:180]}")
        report.duration_ms = (time.perf_counter() - started) * 1000
        self._persist(db, report)
        return report

    def _persist(self, db: Session, report: AgentReport) -> None:
        try:
            db.add(AgentRun(
                agent=report.agent, status=report.status, summary=report.summary,
                details=report.details, items_processed=report.items_processed,
                changes_detected=report.changes_detected, duration_ms=report.duration_ms,
            ))
            db.commit()
        except Exception:  # noqa: BLE001 — logging must never break the cycle
            db.rollback()

    # ── chat ────────────────────────────────────────────────────────────────
    def insight(self, db: Session, query: ChatQuery) -> AgentInsight | None:
        """Contribute to a chat answer. Return None when the question isn't ours."""
        return None

    # ── helpers shared by agents ────────────────────────────────────────────
    @staticmethod
    def record_change(
        db: Session,
        change_type: str,
        detail: str,
        *,
        detected_by: str,
        team_mlb_id: int | None = None,
        player_mlb_id: int | None = None,
        player_name: str | None = None,
        previous_value: str | None = None,
        new_value: str | None = None,
        game_pk: int | None = None,
        severity: str = "info",
    ) -> RosterChange:
        change = RosterChange(
            team_mlb_id=team_mlb_id, player_mlb_id=player_mlb_id, player_name=player_name,
            change_type=change_type, detail=detail, previous_value=previous_value,
            new_value=new_value, game_pk=game_pk, severity=severity, detected_by=detected_by,
            detected_at=datetime.now(timezone.utc),
        )
        db.add(change)
        return change
