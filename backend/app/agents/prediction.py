"""Agent 8 — Prediction AI.

Runs the EVR ensemble (Random Forest, XGBoost, LightGBM, CatBoost, neural net,
online SGD, stacking, ELO, Monte Carlo with Bayesian weight updating) over the
enriched data the other agents gathered, then rebuilds parlays and the parlay
committee's debate.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents.base import AgentInsight, AgentReport, BaseAgent, ChatQuery
from app.application.agents import build_agent_parlays
from app.application.parlay_service import build_parlays_for_day
from app.application.prediction_service import generate_for_day
from app.domain.entities import Market, Odds
from app.infrastructure.db.models import ModelWeight, Prediction
from app.infrastructure.providers.registry import ProviderRegistry
from app.ml.model_zoo import MODEL_NAMES

INTENT_MARKETS = {
    "moneyline": [Market.MONEYLINE.value],
    "totals": [Market.TOTAL_OVER.value, Market.TOTAL_UNDER.value],
    "run_line": [Market.RUN_LINE.value],
}


class PredictionAIAgent(BaseAgent):
    name = "prediction_ai"
    title = "Prediction AI"
    description = "Ensemble de ML (RF, XGBoost, LightGBM, CatBoost, red neuronal, ELO, Monte Carlo, bayesiano)."
    specialties = ("prediccion", "predicción", "probabilidad", "moneyline", "total", "parlay", "modelo")

    def work(self, db: Session, reg: ProviderRegistry, day: date) -> AgentReport:
        result = generate_for_day(db, day)
        parlays = build_parlays_for_day(db, day)
        agent_parlays = build_agent_parlays(db, day)
        value_bets = int(
            db.scalar(
                select(func.count(Prediction.id)).where(
                    Prediction.game_date == day, Prediction.is_value_bet.is_(True)
                )
            ) or 0
        )
        weights = db.scalars(select(ModelWeight)).all()
        trained_models = sorted({w.model_name for w in weights}) or MODEL_NAMES
        return AgentReport(
            agent=self.name,
            summary=(
                f"{result.get('predictions', 0)} probabilidades calculadas sobre "
                f"{result.get('games', 0)} juegos; {parlays} parlays y {agent_parlays} combinadas de agentes."
            ),
            details={
                **result, "parlays": parlays, "agent_parlays": agent_parlays,
                "value_bets": value_bets, "models": trained_models,
            },
            items_processed=result.get("predictions", 0),
            changes_detected=result.get("predictions", 0),
        )

    def insight(self, db: Session, query: ChatQuery) -> AgentInsight | None:
        if query.intent == "parlay":
            return self._parlay_insight(db, query)
        markets = INTENT_MARKETS.get(query.intent)
        if markets is None and query.intent != "general":
            return None
        limit = query.count or 5
        stmt = select(Prediction).where(Prediction.game_date == (query.day or date.today()))
        if markets:
            stmt = stmt.where(Prediction.market.in_(markets))
        else:
            stmt = stmt.where(Prediction.market.in_([Market.MONEYLINE.value, Market.TOTAL_OVER.value]))
        rows = db.scalars(
            stmt.order_by((Prediction.probability * Prediction.confidence).desc()).limit(limit)
        ).all()
        if not rows:
            return AgentInsight(
                agent=self.name, title=self.title,
                headline="Todavía no hay probabilidades calculadas para hoy.",
                bullets=["El ensemble corre en cuanto haya cartelera y datos de los otros agentes."],
                confidence=0.3,
            )
        bullets = []
        for r in rows:
            votes = {k: v for k, v in (r.model_breakdown or {}).items()
                     if not k.startswith("_") and isinstance(v, (int, float))}
            agreement = (
                f"{len(votes)} modelos votaron (rango {min(votes.values()):.0%}–{max(votes.values()):.0%})"
                if votes else "voto analítico"
            )
            bullets.append(f"{r.selection} — {r.probability:.0%}; {agreement}; confianza {r.confidence:.0%}.")
        return AgentInsight(
            agent=self.name, title=self.title,
            headline=f"Top {len(rows)} por probabilidad × confianza del ensemble.",
            bullets=bullets,
            picks=[{
                "prediction_id": r.id, "selection": r.selection, "market": r.market,
                "probability": r.probability, "confidence": r.confidence,
                "book_odds": r.book_odds, "fair_odds": r.fair_odds, "why": r.explanation,
            } for r in rows],
            confidence=float(sum(r.confidence for r in rows) / len(rows)),
        )

    def _parlay_insight(self, db: Session, query: ChatQuery) -> AgentInsight:
        """Build a parlay of N legs on demand (defaults to the safest available)."""
        legs_wanted = query.count or 3
        pool = db.scalars(
            select(Prediction)
            .where(
                Prediction.game_date == (query.day or date.today()),
                Prediction.settled.is_(False),
                Prediction.probability >= 0.5,
            )
            .order_by((Prediction.probability * Prediction.confidence).desc())
            .limit(60)
        ).all()
        if query.market:
            pool = [p for p in pool if p.market == query.market] or pool

        legs: list[Prediction] = []
        used_games: set[int] = set()
        used_players: set[int] = set()
        for p in pool:
            if len(legs) >= legs_wanted:
                break
            if p.player_mlb_id and p.player_mlb_id in used_players:
                continue
            if not p.player_mlb_id and p.game_pk in used_games:
                continue
            legs.append(p)
            used_games.add(p.game_pk)
            if p.player_mlb_id:
                used_players.add(p.player_mlb_id)

        if not legs:
            return AgentInsight(
                agent=self.name, title=self.title,
                headline="No tengo suficientes selecciones para armar ese parlay todavía.",
                bullets=["Espera a que se publiquen alineaciones y se sincronicen las estadísticas."],
                confidence=0.3,
            )
        combined = 1.0
        decimal = 1.0
        for leg in legs:
            combined *= leg.probability
            odds = Odds(american=leg.book_odds) if leg.book_odds else Odds.from_probability(leg.probability)
            decimal *= odds.decimal
        return AgentInsight(
            agent=self.name, title=self.title,
            headline=(
                f"Parlay de {len(legs)} selecciones: {combined:.1%} de acierto conjunto, "
                f"cuota aproximada x{decimal:.2f}."
            ),
            bullets=[
                f"{leg.selection} — {leg.probability:.0%} · {leg.explanation[:110]}"
                for leg in legs
            ],
            picks=[{
                "prediction_id": leg.id, "selection": leg.selection, "market": leg.market,
                "probability": leg.probability, "book_odds": leg.book_odds,
                "confidence": leg.confidence, "why": leg.explanation,
            } for leg in legs],
            confidence=float(sum(leg.confidence for leg in legs) / len(legs)),
        )
