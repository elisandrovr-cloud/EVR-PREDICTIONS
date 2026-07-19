"""Bankroll & bet-tracking endpoints (per authenticated user)."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from sqlalchemy import select

from app.api.deps import CurrentUser, DbDep
from app.api.schemas import BankrollOut, BetCreate, BetOut
from app.domain.entities import Odds
from app.infrastructure.db.models import Bankroll, Bet

router = APIRouter(prefix="/bankroll", tags=["bankroll"])


def _get_bankroll(db: DbDep, user_id: int) -> Bankroll:
    row = db.scalar(select(Bankroll).where(Bankroll.user_id == user_id))
    if row is None:
        row = Bankroll(user_id=user_id)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


@router.get("", response_model=BankrollOut)
def get_bankroll(user: CurrentUser, db: DbDep) -> BankrollOut:
    return BankrollOut.model_validate(_get_bankroll(db, user.id))


@router.get("/bets", response_model=list[BetOut])
def list_bets(user: CurrentUser, db: DbDep) -> list[BetOut]:
    rows = db.scalars(
        select(Bet).where(Bet.user_id == user.id).order_by(Bet.placed_at.desc()).limit(200)
    ).all()
    return [BetOut.model_validate(r) for r in rows]


@router.post("/bets", response_model=BetOut, status_code=201)
def place_bet(payload: BetCreate, user: CurrentUser, db: DbDep) -> BetOut:
    bankroll = _get_bankroll(db, user.id)
    if payload.stake > bankroll.balance:
        raise HTTPException(status_code=422, detail="Stake exceeds bankroll")
    bet = Bet(
        user_id=user.id, prediction_id=payload.prediction_id, description=payload.description,
        stake=payload.stake, american_odds=payload.american_odds,
    )
    bankroll.balance -= payload.stake
    db.add(bet)
    db.commit()
    db.refresh(bet)
    return BetOut.model_validate(bet)


@router.post("/bets/{bet_id}/settle/{result}", response_model=BetOut)
def settle_bet(bet_id: int, result: str, user: CurrentUser, db: DbDep) -> BetOut:
    if result not in ("won", "lost", "push"):
        raise HTTPException(status_code=422, detail="result must be won|lost|push")
    bet = db.scalar(select(Bet).where(Bet.id == bet_id, Bet.user_id == user.id))
    if bet is None:
        raise HTTPException(status_code=404, detail="Bet not found")
    if bet.status != "open":
        raise HTTPException(status_code=409, detail="Bet already settled")
    bankroll = _get_bankroll(db, user.id)
    bet.status = result
    bet.settled_at = datetime.now(timezone.utc)
    if result == "won":
        bet.payout = round(bet.stake * Odds(american=bet.american_odds).decimal, 2)
        bankroll.balance += bet.payout
    elif result == "push":
        bet.payout = bet.stake
        bankroll.balance += bet.stake
    else:
        bet.payout = 0.0
    db.commit()
    db.refresh(bet)
    return BetOut.model_validate(bet)
