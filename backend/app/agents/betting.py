"""Agent 6 — Betting Intelligence.

Compares the model's probability against the sportsbook's implied probability and
reports Expected Value, edge, Closing Line Value, risk and confidence.

Lines come from the interchangeable sportsbook layer: Hard Rock Bet prices are
entered by the user (Hard Rock publishes no public odds API), and any authorized
aggregator/feed can be plugged in without changing this agent.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.base import AgentInsight, AgentReport, BaseAgent, ChatQuery
from app.core.config import settings
from app.domain.entities import Edge, Odds
from app.infrastructure.db.models import OddsQuote, Prediction
from app.infrastructure.providers.registry import ProviderRegistry
from app.infrastructure.providers.sportsbook import available_books


class BettingIntelligenceAgent(BaseAgent):
    name = "betting_intelligence"
    title = "Betting Intelligence"
    description = "Compara la probabilidad del modelo contra la cuota del libro: EV, edge, CLV, riesgo."
    specialties = ("value", "ev", "edge", "cuota", "cuotas", "linea", "línea", "apuesta", "hard rock", "clv")

    def work(self, db: Session, reg: ProviderRegistry, day: date) -> AgentReport:
        preds = db.scalars(
            select(Prediction).where(Prediction.game_date == day, Prediction.settled.is_(False))
        ).all()
        priced = 0
        value_bets = 0
        best_edge = 0.0
        for p in preds:
            if p.book_odds is None:
                continue
            priced += 1
            econ = Edge(model_probability=p.probability, market_odds=Odds(american=p.book_odds))
            p.expected_value = round(econ.expected_value, 4)
            p.edge = round(econ.edge, 4)
            p.kelly_stake = round(econ.kelly_stake(settings.KELLY_FRACTION), 4)
            p.is_value_bet = bool(econ.edge >= settings.MIN_EDGE_FOR_VALUE_BET and econ.expected_value > 0)
            if p.is_value_bet:
                value_bets += 1
            best_edge = max(best_edge, econ.edge)
            p.clv = self._closing_line_value(db, p)
        db.commit()

        books = available_books()
        enabled = [b["book"] for b in books if b["enabled"]]
        return AgentReport(
            agent=self.name,
            summary=(
                f"{priced} selecciones con cuota; {value_bets} con ventaja real. "
                f"Libros activos: {', '.join(enabled) or 'ninguno'}."
            ),
            details={
                "priced": priced, "value_bets": value_bets, "best_edge": round(best_edge, 4),
                "unpriced": len(preds) - priced, "books": books,
            },
            items_processed=priced,
            changes_detected=value_bets,
        )

    @staticmethod
    def _closing_line_value(db: Session, pred: Prediction) -> float | None:
        """CLV = how much better our price is than the latest market price."""
        quotes = db.scalars(
            select(OddsQuote)
            .where(OddsQuote.game_pk == pred.game_pk, OddsQuote.selection == pred.selection)
            .order_by(OddsQuote.captured_at.desc())
            .limit(1)
        ).all()
        if not quotes or pred.book_odds is None:
            return None
        latest = quotes[0]
        taken = Odds(american=pred.book_odds).implied_probability
        closing = latest.implied_prob
        return round(closing - taken, 4)  # positive = we beat the market

    def insight(self, db: Session, query: ChatQuery) -> AgentInsight | None:
        if query.intent not in ("value", "general", "parlay", "moneyline", "hits", "strikeouts"):
            return None
        limit = query.count or 5
        rows = db.scalars(
            select(Prediction)
            .where(
                Prediction.game_date == (query.day or date.today()),
                Prediction.is_value_bet.is_(True),
            )
            .order_by(Prediction.expected_value.desc())
            .limit(limit)
        ).all()
        books = [b["book"] for b in available_books() if b["enabled"]]
        if not rows:
            return AgentInsight(
                agent=self.name, title=self.title,
                headline="Sin ventaja medible contra el libro ahora mismo.",
                bullets=[
                    "Para medir EV necesito las cuotas: cárgalas desde «Mis cuotas» "
                    f"(libro por defecto: {settings.DEFAULT_BOOK_NAME}) o activa un proveedor autorizado.",
                    f"Fuentes de cuotas activas: {', '.join(books) or 'ninguna'}.",
                ],
                confidence=0.35,
            )
        bullets = [
            f"{r.selection}: modelo {r.probability:.0%} vs libro "
            f"{Odds(american=r.book_odds).implied_probability:.0%} → EV {r.expected_value:+.1%}, "
            f"edge {r.edge:+.1%}."
            for r in rows if r.book_odds is not None
        ]
        return AgentInsight(
            agent=self.name, title=self.title,
            headline=f"{len(rows)} apuestas con valor positivo detectadas.",
            bullets=bullets,
            picks=[{
                "prediction_id": r.id, "selection": r.selection, "market": r.market,
                "probability": r.probability, "book_odds": r.book_odds,
                "expected_value": r.expected_value, "edge": r.edge,
                "kelly_stake": r.kelly_stake, "why": r.explanation,
            } for r in rows],
            confidence=0.8,
        )
