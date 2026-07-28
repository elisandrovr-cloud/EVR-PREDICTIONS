"""Supervisor AI — coordinates the eight specialized agents.

Two responsibilities:

1. **Monitoring cycle** — runs the agents in dependency order (data gathering →
   analysis → prediction → pricing → news), isolates failures, and writes a
   conclusion the dashboard can show.
2. **Chat** — parses the user's question, routes it to the agents that own that
   domain, collects their insights and synthesizes ONE justified answer. Every
   recommendation carries the statistics behind it, the factors that raise the
   risk and a confidence level — never a bare list.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.base import AgentInsight, AgentReport, BaseAgent, ChatQuery
from app.agents.batter import BatterIntelligenceAgent
from app.agents.betting import BettingIntelligenceAgent
from app.agents.lineup import LineupIntelligenceAgent
from app.agents.news import NewsIntelligenceAgent
from app.agents.pitcher import PitcherIntelligenceAgent
from app.agents.player import PlayerIntelligenceAgent
from app.agents.prediction import PredictionAIAgent
from app.agents.roster import RosterIntelligenceAgent
from app.core.logging import get_logger
from app.infrastructure.cache.redis_client import cache_get, cache_set
from app.infrastructure.db.models import AgentRun, Player, RosterChange
from app.infrastructure.providers.registry import ProviderRegistry, get_registry

logger = get_logger(__name__)

LAST_CYCLE_KEY = "evr:supervisor:last_cycle"

DISCLAIMER = (
    "Estas probabilidades son estimaciones estadísticas del modelo, no garantías de resultado. "
    "Apuesta con responsabilidad."
)

# Intent → keywords (Spanish first, English accepted).
INTENT_PATTERNS: list[tuple[str, tuple[str, ...]]] = [
    ("parlay", ("parlay", "combinada", "combinadas", "picks", "pick")),
    ("hits", ("hit", "hits", "imparable", "imparables")),
    ("home_runs", ("jonron", "jonrón", "jonrones", "home run", "homerun", "hr", "cuadrangular")),
    ("total_bases", ("bases totales", "total bases")),
    ("rbi", ("rbi", "carreras impulsadas", "impulsada", "impulsadas")),
    ("strikeouts", ("ponche", "ponches", "strikeout", "strikeouts", " k ", "chocolate")),
    ("moneyline", ("moneyline", "money line", "ganador", "quien gana", "quién gana", "gana el juego")),
    ("totals", ("over", "under", "total de carreras", "altas", "bajas")),
    ("run_line", ("run line", "runline", "hándicap", "handicap")),
    ("value", ("valor", "value", "ev", "edge", "ventaja", "mejor cuota")),
    ("news", ("noticia", "noticias", "lesion", "lesión", "lesionado", "news", "reporte")),
    ("lineup", ("lineup", "alineacion", "alineación", "orden al bate")),
    ("roster", ("roster", "movimiento", "movimientos", "transaccion", "transacción")),
]


@dataclass
class CycleResult:
    started_at: datetime
    reports: list[AgentReport] = field(default_factory=list)
    conclusion: str = ""
    duration_ms: float = 0.0
    changes_detected: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "started_at": self.started_at.isoformat(),
            "duration_ms": round(self.duration_ms, 1),
            "changes_detected": self.changes_detected,
            "conclusion": self.conclusion,
            "agents": [r.as_dict() for r in self.reports],
        }


@dataclass
class ChatAnswer:
    question: str
    intent: str
    answer: str
    insights: list[AgentInsight] = field(default_factory=list)
    picks: list[dict[str, Any]] = field(default_factory=list)
    confidence: float = 0.5
    agents_consulted: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "intent": self.intent,
            "answer": self.answer,
            "insights": [i.as_dict() for i in self.insights],
            "picks": self.picks,
            "confidence": round(self.confidence, 3),
            "agents_consulted": self.agents_consulted,
            "disclaimer": DISCLAIMER,
        }


class Supervisor:
    """Coordinates every agent. One instance is shared across the app."""

    def __init__(self) -> None:
        self.roster = RosterIntelligenceAgent()
        self.lineup = LineupIntelligenceAgent()
        self.player = PlayerIntelligenceAgent()
        self.pitcher = PitcherIntelligenceAgent()
        self.batter = BatterIntelligenceAgent()
        self.betting = BettingIntelligenceAgent()
        self.news = NewsIntelligenceAgent()
        self.prediction = PredictionAIAgent()

    @property
    def agents(self) -> list[BaseAgent]:
        """Dependency order: gather → profile → analyze → predict → price → publish."""
        return [
            self.roster, self.lineup, self.player, self.pitcher,
            self.batter, self.prediction, self.betting, self.news,
        ]

    def agent_by_name(self, name: str) -> BaseAgent | None:
        return next((a for a in self.agents if a.name == name), None)

    def roster_of_agents(self) -> list[dict[str, Any]]:
        return [
            {"name": a.name, "title": a.title, "description": a.description,
             "specialties": list(a.specialties)}
            for a in self.agents
        ]

    # ── monitoring cycle ────────────────────────────────────────────────────
    def run_cycle(
        self,
        db: Session,
        registry: ProviderRegistry | None = None,
        day: date | None = None,
        only: list[str] | None = None,
    ) -> CycleResult:
        reg = registry or get_registry()
        target = day or date.today()
        started = datetime.now(timezone.utc)
        clock = time.perf_counter()
        result = CycleResult(started_at=started)

        for agent in self.agents:
            if only and agent.name not in only:
                continue
            report = agent.execute(db, reg, target)
            result.reports.append(report)
            result.changes_detected += report.changes_detected

        result.duration_ms = (time.perf_counter() - clock) * 1000
        result.conclusion = self._conclude(result)
        cache_set(LAST_CYCLE_KEY, result.as_dict(), ttl_seconds=3600)
        logger.info(
            "supervisor cycle complete",
            extra={"agents": len(result.reports), "changes": result.changes_detected},
        )
        return result

    def _conclude(self, result: CycleResult) -> str:
        errors = [r for r in result.reports if r.status == "error"]
        predicted = next((r for r in result.reports if r.agent == "prediction_ai"), None)
        betting = next((r for r in result.reports if r.agent == "betting_intelligence"), None)
        parts: list[str] = []
        if predicted and predicted.details.get("predictions"):
            parts.append(f"{predicted.details['predictions']} probabilidades recalculadas")
        if betting and betting.details.get("value_bets"):
            parts.append(f"{betting.details['value_bets']} apuestas con valor")
        if result.changes_detected:
            parts.append(f"{result.changes_detected} cambios detectados")
        if errors:
            parts.append(f"{len(errors)} agente(s) con error")
        return "Ciclo completo: " + (", ".join(parts) if parts else "sin novedades") + "."

    def last_cycle(self) -> dict[str, Any] | None:
        return cache_get(LAST_CYCLE_KEY)

    def status(self, db: Session) -> list[dict[str, Any]]:
        """Latest run per agent — powers the agent status board."""
        out: list[dict[str, Any]] = []
        for agent in self.agents:
            last = db.scalar(
                select(AgentRun).where(AgentRun.agent == agent.name).order_by(AgentRun.started_at.desc())
            )
            out.append({
                "name": agent.name,
                "title": agent.title,
                "description": agent.description,
                "status": last.status if last else "idle",
                "summary": last.summary if last else "Aún no ha corrido en este despliegue.",
                "items_processed": last.items_processed if last else 0,
                "changes_detected": last.changes_detected if last else 0,
                "duration_ms": round(last.duration_ms, 1) if last else None,
                "last_run": last.started_at.isoformat() if last else None,
            })
        return out

    # ── chat ────────────────────────────────────────────────────────────────
    def parse(self, db: Session, question: str) -> ChatQuery:
        text = f" {question.lower().strip()} "
        intent = "general"
        for candidate, keywords in INTENT_PATTERNS:
            if any(k in text for k in keywords):
                intent = candidate
                break
        count = None
        match = re.search(r"\b(\d{1,2})\b", text)
        if match:
            value = int(match.group(1))
            if 1 <= value <= 20:
                count = value
        player_name = self._detect_player(db, question)
        if player_name and intent in ("general", "news"):
            intent = "player"
        return ChatQuery(raw=question, intent=intent, count=count, player_name=player_name)

    @staticmethod
    def _detect_player(db: Session, question: str) -> str | None:
        """Match capitalized word pairs in the question against known players."""
        candidates = re.findall(r"\b([A-ZÁÉÍÓÚÑ][\wáéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][\wáéíóúñ]+)?)\b", question)
        for candidate in sorted(candidates, key=len, reverse=True):
            if len(candidate) < 4:
                continue
            hit = db.scalar(select(Player).where(Player.full_name.ilike(f"%{candidate}%")))
            if hit:
                return hit.full_name
        return None

    def answer(self, db: Session, question: str, day: date | None = None) -> ChatAnswer:
        query = self.parse(db, question)
        query.day = day or date.today()

        insights: list[AgentInsight] = []
        for agent in self.agents:
            try:
                insight = agent.insight(db, query)
            except Exception as exc:  # noqa: BLE001 — one agent must not break the chat
                logger.warning("agent insight failed", extra={"agent": agent.name, "error": str(exc)})
                continue
            if insight is not None:
                insights.append(insight)

        picks: list[dict[str, Any]] = []
        for insight in insights:
            picks.extend(insight.picks)
        confidence = (
            sum(i.confidence for i in insights) / len(insights) if insights else 0.3
        )
        answer_text = self._synthesize(db, query, insights, picks, confidence)
        return ChatAnswer(
            question=question, intent=query.intent, answer=answer_text,
            insights=insights, picks=picks[:20], confidence=confidence,
            agents_consulted=[i.agent for i in insights],
        )

    def _synthesize(
        self,
        db: Session,
        query: ChatQuery,
        insights: list[AgentInsight],
        picks: list[dict[str, Any]],
        confidence: float,
    ) -> str:
        """Compose the Supervisor's single, justified answer."""
        if not insights:
            return (
                "Todavía no tengo datos suficientes para responder eso. Los agentes se sincronizan "
                "cada minuto: en cuanto haya cartelera, alineaciones y estadísticas del día podré "
                f"analizarlo.\n\n{DISCLAIMER}"
            )

        lines: list[str] = [self._opening(query, picks)]

        for insight in insights:
            lines.append(f"\n**{insight.title}** — {insight.headline}")
            for bullet in insight.bullets[:5]:
                lines.append(f"  • {bullet}")

        risks = self._risk_factors(db, query)
        if risks:
            lines.append("\n**Qué aumenta el riesgo**")
            for risk in risks:
                lines.append(f"  • {risk}")

        lines.append(
            f"\n**Conclusión del Supervisor** — Confianza global {confidence:.0%}. "
            + self._closing(query, picks, confidence)
        )
        lines.append(f"\n_{DISCLAIMER}_")
        return "\n".join(lines)

    @staticmethod
    def _opening(query: ChatQuery, picks: list[dict[str, Any]]) -> str:
        intent_text = {
            "parlay": "Armé el parlay consultando a todos los agentes",
            "hits": "Revisé el mercado de hits del día",
            "home_runs": "Revisé el mercado de jonrones",
            "strikeouts": "Revisé el mercado de ponches",
            "moneyline": "Revisé los ganadores probables del día",
            "value": "Busqué dónde el modelo le gana al libro",
            "news": "Consulté el monitoreo de noticias y lesiones",
            "lineup": "Consulté el estado de las alineaciones",
            "roster": "Consulté los movimientos de roster",
            "player": f"Analicé a {query.player_name}",
            "totals": "Revisé los totales de carreras",
        }.get(query.intent, "Consulté a los agentes especializados")
        return f"{intent_text}: {len(picks)} selección(es) respaldadas por datos oficiales."

    @staticmethod
    def _risk_factors(db: Session, query: ChatQuery) -> list[str]:
        risks: list[str] = []
        critical = db.scalars(
            select(RosterChange)
            .where(RosterChange.severity == "critical")
            .order_by(RosterChange.detected_at.desc())
            .limit(3)
        ).all()
        for change in critical:
            risks.append(f"{change.detail} (puede alterar el cálculo)")
        pending_lineups = db.scalars(
            select(RosterChange)
            .where(RosterChange.change_type == "lineup_absence")
            .order_by(RosterChange.detected_at.desc())
            .limit(2)
        ).all()
        for change in pending_lineups:
            risks.append(change.detail)
        if query.intent == "parlay":
            risks.append(
                "Un parlay exige que TODAS las patas acierten: la probabilidad conjunta "
                "cae rápido con cada selección añadida."
            )
        return risks[:4]

    @staticmethod
    def _closing(query: ChatQuery, picks: list[dict[str, Any]], confidence: float) -> str:
        if not picks:
            return "No hay selecciones con respaldo suficiente todavía; conviene esperar al próximo ciclo."
        best = max(picks, key=lambda p: p.get("probability", 0) or 0)
        text = (
            f"La selección con mayor respaldo es «{best.get('selection', best.get('player', '—'))}» "
            f"({(best.get('probability') or 0):.0%})."
        )
        if confidence < 0.5:
            text += " La confianza es baja: considera esperar a que se publiquen las alineaciones oficiales."
        elif query.intent == "parlay":
            text += " Para un parlay, menos patas = más probabilidad de cobrar."
        return text


SUPERVISOR = Supervisor()
