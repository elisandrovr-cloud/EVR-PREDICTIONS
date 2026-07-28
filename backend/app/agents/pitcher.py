"""Agent 4 — Pitcher Intelligence.

Keeps every probable starter's advanced profile current (ERA/FIP/WHIP, K% and
BB%, hits and HR allowed per batter faced, workload and fatigue) and reads the
day's strikeout market for the Supervisor.
"""
from __future__ import annotations

import time
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.base import AgentInsight, AgentReport, BaseAgent, ChatQuery
from app.application import ingestion
from app.core.config import settings
from app.domain.entities import Market
from app.infrastructure.db.models import BullpenStat, Game, Player, PlayerStat, Prediction
from app.infrastructure.providers.registry import ProviderRegistry
from app.ml.features import LEAGUE


class PitcherIntelligenceAgent(BaseAgent):
    name = "pitcher_intelligence"
    title = "Pitcher Intelligence"
    description = "Analiza abridores y bullpens: ERA, FIP, WHIP, K%, BB%, carga de trabajo y fatiga."
    specialties = ("pitcher", "lanzador", "abridor", "ponche", "ponches", "strikeout", "strikeouts", "bullpen")

    def work(self, db: Session, reg: ProviderRegistry, day: date) -> AgentReport:
        started = time.perf_counter()
        games = db.scalars(select(Game).where(Game.game_date == day, Game.status != "final")).all()
        have = {
            r.player_mlb_id
            for r in db.scalars(
                select(PlayerStat).where(PlayerStat.kind == "pitching", PlayerStat.scope == "season")
            )
        }
        pending = [
            pid
            for g in games
            for pid in (g.home_pitcher_mlb_id, g.away_pitcher_mlb_id)
            if pid and pid not in have
        ]
        synced = 0
        for pid in dict.fromkeys(pending):
            if (time.perf_counter() - started) > settings.AGENT_CYCLE_SECONDS:
                break
            try:
                ingestion.sync_pitcher_stats(db, pid, reg)
                synced += 1
            except Exception:  # noqa: BLE001 — one bad player must not stop the cycle
                continue

        # Bullpen freshness for the teams playing today.
        pen_have = {r.team_mlb_id for r in db.scalars(select(BullpenStat))}
        for g in games:
            if (time.perf_counter() - started) > settings.AGENT_CYCLE_SECONDS:
                break
            for tid in (g.home_team_mlb_id, g.away_team_mlb_id):
                if tid and tid not in pen_have:
                    try:
                        ingestion.sync_bullpen(db, tid, reg)
                        pen_have.add(tid)
                    except Exception:  # noqa: BLE001
                        continue

        ready = {
            r.player_mlb_id
            for r in db.scalars(
                select(PlayerStat).where(PlayerStat.kind == "pitching", PlayerStat.scope == "season")
            )
        }
        covered = sum(
            1 for g in games for pid in (g.home_pitcher_mlb_id, g.away_pitcher_mlb_id)
            if pid and pid in ready
        )
        return AgentReport(
            agent=self.name,
            summary=f"{synced} abridores sincronizados; {covered} perfiles de pitcheo listos para hoy.",
            details={"synced": synced, "starters_today": covered, "games": len(games)},
            items_processed=synced,
            changes_detected=synced,
        )

    def insight(self, db: Session, query: ChatQuery) -> AgentInsight | None:
        if query.intent not in ("strikeouts", "general", "parlay", "pitcher"):
            return None
        limit = query.count or 5
        rows = db.scalars(
            select(Prediction)
            .where(
                Prediction.game_date == (query.day or date.today()),
                Prediction.market == Market.PITCHER_STRIKEOUTS.value,
            )
            .order_by((Prediction.probability * Prediction.confidence).desc())
            .limit(limit)
        ).all()
        if not rows:
            return AgentInsight(
                agent=self.name, title=self.title,
                headline="Todavía no hay líneas de ponches calculadas para hoy.",
                bullets=["Los abridores confirmados aún no tienen estadísticas sincronizadas."],
                confidence=0.3,
            )
        bullets = []
        picks = []
        for r in rows:
            stat = db.scalar(
                select(PlayerStat).where(
                    PlayerStat.player_mlb_id == r.player_mlb_id,
                    PlayerStat.kind == "pitching",
                    PlayerStat.scope == "season",
                )
            )
            k9 = (stat.stats.get("k_per_9") if stat else None) or LEAGUE["k_per_9"]
            name = self._name(db, r.player_mlb_id) or r.selection
            bullets.append(
                f"{r.selection} — {r.probability:.0%} de acierto. K/9 de {float(k9):.1f} "
                f"(liga {LEAGUE['k_per_9']:.1f}); confianza del modelo {r.confidence:.0%}."
            )
            picks.append({
                "prediction_id": r.id, "player": name, "selection": r.selection,
                "market": r.market, "probability": r.probability, "line": r.line,
                "book_odds": r.book_odds, "confidence": r.confidence, "why": r.explanation,
            })
        return AgentInsight(
            agent=self.name, title=self.title,
            headline=f"Mejores {len(rows)} líneas de ponches de hoy.",
            bullets=bullets, picks=picks,
            confidence=float(sum(r.confidence for r in rows) / len(rows)),
        )

    @staticmethod
    def _name(db: Session, mlb_id: int | None) -> str | None:
        if not mlb_id:
            return None
        row = db.scalar(select(Player).where(Player.mlb_id == mlb_id))
        return row.full_name if row else None
