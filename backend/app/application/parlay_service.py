"""Automatic parlay construction from the day's prediction pool.

Six profiles with distinct leg counts, probability floors and market mixes.
Legs from the same game get a correlation haircut on the combined probability
unless the profile is same_game (where correlation is the point and priced in).
"""
from __future__ import annotations

import itertools
from datetime import date
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.entities import Odds, ParlayProfile, RiskLevel
from app.infrastructure.db.models import Parlay, Prediction

PROFILE_RULES: dict[ParlayProfile, dict] = {
    ParlayProfile.CONSERVATIVE: {"legs": 2, "min_prob": 0.62, "markets": None, "risk": RiskLevel.LOW},
    ParlayProfile.BALANCED: {"legs": 3, "min_prob": 0.55, "markets": None, "risk": RiskLevel.MEDIUM},
    ParlayProfile.AGGRESSIVE: {"legs": 5, "min_prob": 0.45, "markets": None, "risk": RiskLevel.HIGH},
    ParlayProfile.SAME_GAME: {"legs": 3, "min_prob": 0.50, "markets": None, "risk": RiskLevel.MEDIUM},
    ParlayProfile.HIGH_ODDS: {"legs": 4, "min_prob": 0.25, "markets": None, "risk": RiskLevel.EXTREME},
    ParlayProfile.AI_PREMIUM: {"legs": 3, "min_prob": 0.55, "markets": None, "risk": RiskLevel.MEDIUM},
}

SAME_GAME_CORRELATION_HAIRCUT = 0.92  # multiplier per extra leg sharing a game


def _leg_payload(p: Prediction) -> dict:
    return {
        "prediction_id": p.id,
        "game_pk": p.game_pk,
        "market": p.market,
        "selection": p.selection,
        "probability": p.probability,
        "fair_odds": p.fair_odds,
        "book_odds": p.book_odds,
        "confidence": p.confidence,
        "risk": p.risk,
        "ev": p.expected_value,
        "explanation": p.explanation,
    }


def _combined(legs: Sequence[Prediction], same_game_ok: bool) -> tuple[float, float]:
    prob = 1.0
    decimal = 1.0
    game_counts: dict[int, int] = {}
    for leg in legs:
        prob *= leg.probability
        odds = Odds(american=leg.book_odds) if leg.book_odds else Odds.from_probability(leg.probability)
        decimal *= odds.decimal
        game_counts[leg.game_pk] = game_counts.get(leg.game_pk, 0) + 1
    if not same_game_ok:
        extra_shared = sum(c - 1 for c in game_counts.values() if c > 1)
        prob *= SAME_GAME_CORRELATION_HAIRCUT ** extra_shared
    return prob, decimal


def _score(prob: float, decimal: float) -> float:
    return prob * decimal - 1.0  # EV per unit


def build_parlays_for_day(db: Session, day: date) -> int:
    pool = db.scalars(
        select(Prediction)
        .where(Prediction.game_date == day, Prediction.settled.is_(False))
        .order_by(Prediction.confidence.desc())
    ).all()
    if len(pool) < 2:
        return 0
    created = 0
    for profile, rules in PROFILE_RULES.items():
        candidates = [p for p in pool if p.probability >= rules["min_prob"]]
        if profile == ParlayProfile.AI_PREMIUM:
            candidates = [p for p in candidates if p.is_value_bet] or candidates[:20]
        if profile == ParlayProfile.HIGH_ODDS:
            candidates = sorted(candidates, key=lambda p: p.probability)[:24]
        else:
            candidates = candidates[:24]

        best: tuple[float, list[Prediction], float, float] | None = None
        n_legs = rules["legs"]
        for combo in itertools.combinations(candidates, min(n_legs, len(candidates))):
            games = {c.game_pk for c in combo}
            if profile == ParlayProfile.SAME_GAME:
                if len(games) != 1:
                    continue
            else:
                if len(games) != len(combo):  # one leg per game outside SGP
                    continue
            prob, decimal = _combined(combo, same_game_ok=(profile == ParlayProfile.SAME_GAME))
            ev = _score(prob, decimal)
            if best is None or ev > best[0]:
                best = (ev, list(combo), prob, decimal)
        if best is None:
            continue
        ev, legs, prob, decimal = best
        confidence = sum(l.confidence for l in legs) / len(legs)
        row = db.scalar(select(Parlay).where(Parlay.game_date == day, Parlay.profile == profile.value))
        if row is None:
            row = Parlay(game_date=day, profile=profile.value)
            db.add(row)
        row.legs = [_leg_payload(l) for l in legs]
        row.combined_probability = round(prob, 4)
        row.combined_decimal_odds = round(decimal, 3)
        row.expected_value = round(ev, 4)
        row.confidence = round(confidence, 3)
        row.risk = rules["risk"].value
        row.explanation = (
            f"Perfil {profile.value}: {len(legs)} selecciones, probabilidad conjunta "
            f"{prob:.1%}, cuota decimal {decimal:.2f}, EV {ev:+.2%}."
        )
        created += 1
    db.commit()
    return created
