"""Parlay endpoints — auto-generated daily boards per profile."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException

from sqlalchemy import select

from app.api.deps import DbDep
from app.api.schemas import AgentParlayOut, ParlayOut
from app.application.seed import ensure_today_seeded
from app.domain.entities import ParlayProfile
from app.infrastructure.db.models import AgentParlay, Parlay

router = APIRouter(prefix="/parlays", tags=["parlays"])

CATEGORY_ORDER = {"hits": 0, "strikeouts": 1, "games": 2, "mixed": 3}


@router.get("/daily", response_model=list[ParlayOut])
def daily(db: DbDep, day: date | None = None) -> list[ParlayOut]:
    if day is None or day == date.today():
        ensure_today_seeded(db)  # serverless: populate on first request when empty
    rows = db.scalars(select(Parlay).where(Parlay.game_date == (day or date.today()))).all()
    return [ParlayOut.model_validate(r) for r in rows]


@router.get("/agents", response_model=list[AgentParlayOut])
def agents(db: DbDep, day: date | None = None) -> list[AgentParlayOut]:
    """The day's agent-debate parlays: winning pick + full debate transcript,
    for each category (hits / strikeouts / games / mixed) × style (safe / aggressive)."""
    if day is None or day == date.today():
        ensure_today_seeded(db)
    rows = db.scalars(select(AgentParlay).where(AgentParlay.game_date == (day or date.today()))).all()
    rows.sort(key=lambda r: (CATEGORY_ORDER.get(r.category, 9), r.style))
    return [AgentParlayOut.model_validate(r) for r in rows]


@router.get("/profile/{profile}", response_model=ParlayOut)
def by_profile(profile: str, db: DbDep, day: date | None = None) -> ParlayOut:
    if profile not in {p.value for p in ParlayProfile}:
        raise HTTPException(status_code=404, detail="Unknown profile")
    row = db.scalar(
        select(Parlay).where(Parlay.game_date == (day or date.today()), Parlay.profile == profile)
    )
    if row is None:
        raise HTTPException(status_code=404, detail="No parlay generated yet for this profile/day")
    return ParlayOut.model_validate(row)
