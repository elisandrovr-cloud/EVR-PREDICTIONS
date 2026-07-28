"""Multi-agent endpoints: status board, manual refresh, change history, news, chat."""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.agents import SUPERVISOR
from app.api.deps import DbDep
from app.api.schemas import (
    AgentStatusOut,
    ChangeOut,
    ChatRequest,
    ChatResponse,
    CycleOut,
    NewsOut,
)
from app.application.seed import ensure_today_seeded
from app.infrastructure.db.models import ChatMessage, PlayerNews, RosterChange

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("/status", response_model=list[AgentStatusOut])
def status(db: DbDep) -> list[AgentStatusOut]:
    """What each of the eight agents did on its last run."""
    return [AgentStatusOut(**row) for row in SUPERVISOR.status(db)]


@router.get("/roster")
def roster_of_agents() -> list[dict[str, Any]]:
    """The agent team and what each one specializes in."""
    return SUPERVISOR.roster_of_agents()


@router.get("/last-cycle")
def last_cycle(db: DbDep) -> dict[str, Any]:
    """Result of the most recent monitoring cycle, plus the freshness timestamp."""
    cached = SUPERVISOR.last_cycle()
    if cached:
        return {"available": True, **cached}
    statuses = SUPERVISOR.status(db)
    last_run = max((s["last_run"] for s in statuses if s["last_run"]), default=None)
    return {
        "available": False,
        "started_at": last_run,
        "conclusion": "Aún no se ha ejecutado un ciclo completo en este proceso.",
        "agents": statuses,
        "changes_detected": 0,
        "duration_ms": 0.0,
    }


@router.post("/refresh", response_model=CycleOut)
def refresh_now(db: DbDep, only: str | None = None) -> CycleOut:
    """ACTUALIZAR AHORA — runs a full agent cycle synchronously and returns it.

    `only` optionally restricts the run to a comma-separated list of agent names.
    """
    ensure_today_seeded(db)
    names = [n.strip() for n in only.split(",")] if only else None
    result = SUPERVISOR.run_cycle(db, day=date.today(), only=names)
    return CycleOut(**result.as_dict())


@router.get("/changes", response_model=list[ChangeOut])
def changes(
    db: DbDep,
    limit: int = Query(50, le=300),
    severity: str | None = None,
    change_type: str | None = None,
) -> list[ChangeOut]:
    """Audit history of every roster/lineup movement the agents detected."""
    stmt = select(RosterChange).order_by(RosterChange.detected_at.desc())
    if severity:
        stmt = stmt.where(RosterChange.severity == severity)
    if change_type:
        stmt = stmt.where(RosterChange.change_type == change_type)
    return [ChangeOut.model_validate(r) for r in db.scalars(stmt.limit(limit))]


@router.get("/news", response_model=list[NewsOut])
def news(db: DbDep, limit: int = Query(30, le=200), category: str | None = None) -> list[NewsOut]:
    stmt = select(PlayerNews).order_by(PlayerNews.published_at.desc())
    if category:
        stmt = stmt.where(PlayerNews.category == category)
    return [NewsOut.model_validate(r) for r in db.scalars(stmt.limit(limit))]


@router.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest, db: DbDep) -> ChatResponse:
    """Ask the Supervisor. It routes the question to the specialized agents and
    returns one synthesized, justified answer."""
    ensure_today_seeded(db)
    answer = SUPERVISOR.answer(db, payload.question)
    _persist_chat(db, payload, answer)
    return ChatResponse(**answer.as_dict())


@router.get("/chat/history")
def chat_history(db: DbDep, session_key: str = "default", limit: int = 40) -> list[dict[str, Any]]:
    rows = db.scalars(
        select(ChatMessage)
        .where(ChatMessage.session_key == session_key)
        .order_by(ChatMessage.created_at.desc())
        .limit(min(limit, 200))
    ).all()
    return [
        {
            "role": r.role, "content": r.content, "intent": r.intent,
            "agents_consulted": r.agents_consulted, "payload": r.payload,
            "created_at": r.created_at.isoformat(),
        }
        for r in reversed(rows)
    ]


def _persist_chat(db: DbDep, payload: ChatRequest, answer: Any) -> None:
    try:
        now = datetime.now(timezone.utc)
        db.add(ChatMessage(
            session_key=payload.session_key, role="user", content=payload.question, created_at=now,
        ))
        db.add(ChatMessage(
            session_key=payload.session_key, role="assistant", content=answer.answer,
            intent=answer.intent, agents_consulted=answer.agents_consulted,
            payload={"picks": answer.picks[:10], "confidence": answer.confidence},
            created_at=now,
        ))
        db.commit()
    except Exception:  # noqa: BLE001 — transcript is best-effort
        db.rollback()
