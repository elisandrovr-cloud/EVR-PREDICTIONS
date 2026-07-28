"""Odds endpoints — including manual entry of the lines you see in your book.

Hard Rock Bet publishes no public odds API, so the supported (and permitted) way
to price against it is to enter the numbers you see in your own account. Betting
Intelligence then measures the model's edge against exactly those prices.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.api.deps import DbDep
from app.api.schemas import ManualOddsIn, OddsQuoteOut
from app.core.config import settings
from app.domain.entities import Edge, Odds
from app.infrastructure.db.models import Game, OddsQuote, Prediction
from app.infrastructure.providers.sportsbook import available_books

router = APIRouter(prefix="/odds", tags=["odds"])


@router.get("/books")
def books() -> dict:
    return {"default_book": settings.DEFAULT_BOOK_NAME, "providers": available_books()}


@router.post("/manual", response_model=OddsQuoteOut, status_code=201)
def add_manual_line(payload: ManualOddsIn, db: DbDep) -> OddsQuoteOut:
    """Record a line you read in your sportsbook and re-price the matching pick."""
    game = db.scalar(select(Game).where(Game.game_pk == payload.game_pk))
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")
    if payload.american == 0 or -100 < payload.american < 100:
        raise HTTPException(status_code=422, detail="American odds must be <= -100 or >= +100")

    quote = OddsQuote(
        game_pk=payload.game_pk,
        book=payload.book or settings.DEFAULT_BOOK_NAME,
        market=payload.market,
        selection=payload.selection,
        line=payload.line,
        american=payload.american,
        implied_prob=round(Odds(american=payload.american).implied_probability, 4),
        captured_at=datetime.now(timezone.utc),
    )
    db.add(quote)

    # Attach the price to the matching prediction so EV/edge update immediately.
    match = db.scalar(
        select(Prediction).where(
            Prediction.game_pk == payload.game_pk,
            Prediction.selection == payload.selection,
        )
    )
    if match is not None and not match.settled:
        econ = Edge(model_probability=match.probability, market_odds=Odds(american=payload.american))
        match.book_odds = payload.american
        match.edge = round(econ.edge, 4)
        match.expected_value = round(econ.expected_value, 4)
        match.kelly_stake = round(econ.kelly_stake(settings.KELLY_FRACTION), 4)
        match.is_value_bet = bool(
            econ.edge >= settings.MIN_EDGE_FOR_VALUE_BET and econ.expected_value > 0
        )
    db.commit()
    db.refresh(quote)
    return OddsQuoteOut.model_validate(quote)


@router.get("/today", response_model=list[OddsQuoteOut])
def today_quotes(db: DbDep, limit: int = 200) -> list[OddsQuoteOut]:
    game_pks = [g.game_pk for g in db.scalars(select(Game).where(Game.game_date == date.today()))]
    if not game_pks:
        return []
    rows = db.scalars(
        select(OddsQuote)
        .where(OddsQuote.game_pk.in_(game_pks))
        .order_by(OddsQuote.captured_at.desc())
        .limit(min(limit, 1000))
    ).all()
    return [OddsQuoteOut.model_validate(r) for r in rows]
