"""Daily agent debate — expert personas compete to build the best parlay.

Four analyst personas, each with a distinct philosophy, look at today's
prediction pool and propose a parlay for a given category (hits / strikeouts /
games / mixed) and risk style (safe / aggressive). A judge scores every proposal
by the metric that matters for that style, the best one wins, and the whole
argument is recorded as a debate transcript so the user sees *why* each pick was
made. Results are precomputed (cron / seed) so a parlay is already waiting each
day. No external LLM calls — the "reasoning" is deterministic baseball logic.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.domain.entities import Odds, RiskLevel
from app.infrastructure.db.models import AgentParlay, Prediction

logger = get_logger(__name__)

GAME_MARKETS = {"moneyline", "run_line", "total_over", "total_under", "first_inning"}
CATEGORY_MARKETS: dict[str, Callable[[Prediction], bool]] = {
    "hits": lambda p: p.market == "player_hits" and (p.line or 0) <= 0.5,
    "strikeouts": lambda p: p.market == "pitcher_strikeouts",
    "games": lambda p: p.market in GAME_MARKETS,
    "mixed": lambda p: True,
}

STYLE_RULES = {
    "safe": {"min_prob": 0.58, "legs": 3, "max_per_game": 1, "risk": RiskLevel.LOW},
    "aggressive": {"min_prob": 0.42, "legs": 5, "max_per_game": 2, "risk": RiskLevel.HIGH},
}
SAME_GAME_HAIRCUT = 0.94


@dataclass(frozen=True)
class Agent:
    name: str
    tagline: str
    # higher key = more attractive leg for this persona
    leg_key: Callable[[Prediction], float]
    argument: Callable[[list[Prediction], float, float, float], str]


def _edge(p: Prediction) -> float:
    if p.expected_value is not None:
        return p.expected_value
    return p.probability - 0.5


def _decimal(p: Prediction) -> float:
    return Odds(american=p.book_odds).decimal if p.book_odds else Odds.from_probability(p.probability).decimal


AGENTS: list[Agent] = [
    Agent(
        name="El Sabio",
        tagline="Prioriza la seguridad: cobra primero, sueña después",
        leg_key=lambda p: p.probability,
        argument=lambda legs, prob, dec, ev: (
            f"Elegí las {len(legs)} selecciones más probables del día. Una combinada del "
            f"{prob:.0%} de acierto se cobra; no arriesgo el banco por una cuota bonita."
        ),
    ),
    Agent(
        name="El Francotirador",
        tagline="Caza valor contra la casa, no favoritos obvios",
        leg_key=lambda p: _edge(p),
        argument=lambda legs, prob, dec, ev: (
            f"Cada pata tiene ventaja contra la línea de la casa. EV combinado {ev:+.0%}: "
            f"a la larga esto es lo que deja dinero, aunque el acierto sea {prob:.0%}."
        ),
    ),
    Agent(
        name="El Apostador",
        tagline="Va por el batazo: máxima cuota, máxima adrenalina",
        leg_key=lambda p: _decimal(p),
        argument=lambda legs, prob, dec, ev: (
            f"Cuota combinada x{dec:.1f}. Si pega, paga como campanazo. "
            f"Con {len(legs)} patas agresivas voy por el premio gordo, no por migajas."
        ),
    ),
    Agent(
        name="El Analista",
        tagline="Solo confía en la convicción del modelo",
        leg_key=lambda p: p.probability * p.confidence,
        argument=lambda legs, prob, dec, ev: (
            f"Ordené por probabilidad × confianza del modelo. Estas {len(legs)} son las de mayor "
            f"convicción cuantitativa: {prob:.0%} de acierto con respaldo del ensemble."
        ),
    ),
]


def _select_legs(pool: list[Prediction], agent: Agent, n: int, max_per_game: int) -> list[Prediction]:
    ranked = sorted(pool, key=agent.leg_key, reverse=True)
    chosen: list[Prediction] = []
    per_game: dict[int, int] = {}
    seen_players: set[int] = set()
    for p in ranked:
        if len(chosen) >= n:
            break
        if per_game.get(p.game_pk, 0) >= max_per_game:
            continue
        if p.player_mlb_id and p.player_mlb_id in seen_players:
            continue
        chosen.append(p)
        per_game[p.game_pk] = per_game.get(p.game_pk, 0) + 1
        if p.player_mlb_id:
            seen_players.add(p.player_mlb_id)
    return chosen


def _combine(legs: list[Prediction]) -> tuple[float, float, float]:
    prob = 1.0
    dec = 1.0
    game_counts: dict[int, int] = {}
    for leg in legs:
        prob *= leg.probability
        dec *= _decimal(leg)
        game_counts[leg.game_pk] = game_counts.get(leg.game_pk, 0) + 1
    extra_shared = sum(c - 1 for c in game_counts.values() if c > 1)
    prob *= SAME_GAME_HAIRCUT**extra_shared
    ev = prob * dec - 1.0
    return prob, dec, ev


def _leg_payload(p: Prediction) -> dict:
    return {
        "prediction_id": p.id,
        "game_pk": p.game_pk,
        "market": p.market,
        "selection": p.selection,
        "player_mlb_id": p.player_mlb_id,
        "probability": p.probability,
        "book_odds": p.book_odds,
        "fair_odds": p.fair_odds,
        "confidence": p.confidence,
        "explanation": p.explanation,
    }


def _judge_score(style: str, prob: float, dec: float) -> float:
    # safe wants the highest chance of cashing; aggressive wants expected payout multiple.
    return prob if style == "safe" else prob * dec


def _debate_for(pool: list[Prediction], style: str) -> dict | None:
    """Run all agents on one (category, style) and return the winning proposal
    plus the full debate transcript."""
    rules = STYLE_RULES[style]
    eligible = [p for p in pool if p.probability >= rules["min_prob"]]
    if len(eligible) < 2:
        return None

    proposals: list[dict] = []
    for agent in AGENTS:
        legs = _select_legs(eligible, agent, rules["legs"], rules["max_per_game"])
        if len(legs) < 2:
            continue
        prob, dec, ev = _combine(legs)
        score = _judge_score(style, prob, dec)
        proposals.append({
            "agent": agent.name,
            "tagline": agent.tagline,
            "argument": agent.argument(legs, prob, dec, ev),
            "score": round(score, 4),
            "legs": legs,
            "prob": prob,
            "dec": dec,
            "ev": ev,
        })
    if not proposals:
        return None

    proposals.sort(key=lambda x: x["score"], reverse=True)
    winner = proposals[0]
    transcript = [
        {
            "agent": pr["agent"],
            "tagline": pr["tagline"],
            "argument": pr["argument"],
            "score": pr["score"],
            "won": i == 0,
            "metrics": {"probability": round(pr["prob"], 4),
                        "decimal_odds": round(pr["dec"], 3),
                        "ev": round(pr["ev"], 4)},
        }
        for i, pr in enumerate(proposals)
    ]
    return {"winner": winner, "transcript": transcript}


def build_agent_parlays(db: Session, day: date) -> int:
    """Precompute the winning parlay + debate for each category × style."""
    predictions = db.scalars(
        select(Prediction).where(Prediction.game_date == day, Prediction.settled.is_(False))
    ).all()
    if not predictions:
        return 0

    created = 0
    for category, belongs in CATEGORY_MARKETS.items():
        pool = [p for p in predictions if belongs(p)]
        for style, rules in STYLE_RULES.items():
            result = _debate_for(pool, style)
            row = db.scalar(
                select(AgentParlay).where(
                    AgentParlay.game_date == day,
                    AgentParlay.category == category,
                    AgentParlay.style == style,
                )
            )
            if result is None:
                continue
            winner = result["winner"]
            legs = winner["legs"]
            confidence = sum(l.confidence for l in legs) / len(legs)
            if row is None:
                row = AgentParlay(game_date=day, category=category, style=style)
                db.add(row)
            if row.settled:
                continue
            row.winning_agent = winner["agent"]
            row.legs = [_leg_payload(l) for l in legs]
            row.combined_probability = round(winner["prob"], 4)
            row.combined_decimal_odds = round(winner["dec"], 3)
            row.expected_value = round(winner["ev"], 4)
            row.confidence = round(confidence, 3)
            row.risk = rules["risk"].value
            row.debate = result["transcript"]
            row.explanation = (
                f"Debate de agentes ({category}/{style}): ganó {winner['agent']}. "
                f"{len(legs)} patas, {winner['prob']:.0%} de acierto, cuota x{winner['dec']:.2f}, "
                f"EV {winner['ev']:+.0%}."
            )
            created += 1
    db.commit()
    logger.info("agent debate complete", extra={"day": str(day), "parlays": created})
    return created
