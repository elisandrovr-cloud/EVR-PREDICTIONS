"""Agent 5 — Batter Intelligence.

Keeps hitters' season rates and last-5-game form current for everyone in today's
lineups, and reads the hit / home-run / total-bases markets for the Supervisor.
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
from app.infrastructure.db.models import Game, Player, PlayerStat, Prediction
from app.infrastructure.providers.registry import ProviderRegistry

MARKET_BY_INTENT = {
    "hits": Market.PLAYER_HITS.value,
    "home_runs": Market.PLAYER_HOME_RUNS.value,
    "total_bases": Market.PLAYER_TOTAL_BASES.value,
    "rbi": Market.PLAYER_RBI.value,
}


class BatterIntelligenceAgent(BaseAgent):
    name = "batter_intelligence"
    title = "Batter Intelligence"
    description = "Analiza bateadores: AVG/OBP/SLG, tasas por turno, forma de los últimos 5 juegos y matchups."
    specialties = ("bateador", "hit", "hits", "jonron", "jonrón", "home run", "bases", "rbi", "carreras")

    def work(self, db: Session, reg: ProviderRegistry, day: date) -> AgentReport:
        started = time.perf_counter()
        games = db.scalars(select(Game).where(Game.game_date == day, Game.status != "final")).all()
        have = {
            r.player_mlb_id
            for r in db.scalars(
                select(PlayerStat).where(PlayerStat.kind == "batting", PlayerStat.scope == "season")
            )
        }
        pending: list[tuple[int, str | None, int | None]] = []
        for g in games:
            for side in ("home", "away"):
                team_id = g.home_team_mlb_id if side == "home" else g.away_team_mlb_id
                for slot in (g.lineups or {}).get(side, []):
                    bid = slot.get("id")
                    if bid and bid not in have and not any(bid == p[0] for p in pending):
                        pending.append((bid, slot.get("name"), team_id))

        synced = 0
        for bid, name, team_id in pending:
            if (time.perf_counter() - started) > settings.AGENT_CYCLE_SECONDS:
                break
            try:
                ingestion.sync_batter_stats(db, bid, reg)
                ingestion.sync_batter_recent_form(db, bid, reg)
                ingestion._upsert_player(db, bid, name, team_id, None)  # noqa: SLF001
                db.commit()
                synced += 1
            except Exception:  # noqa: BLE001
                db.rollback()
                continue

        return AgentReport(
            agent=self.name,
            summary=f"{synced} bateadores sincronizados; {len(pending) - synced} pendientes.",
            details={"synced": synced, "pending": max(0, len(pending) - synced), "games": len(games)},
            items_processed=synced,
            changes_detected=synced,
        )

    def insight(self, db: Session, query: ChatQuery) -> AgentInsight | None:
        if query.intent not in ("hits", "home_runs", "total_bases", "rbi", "general", "parlay", "value"):
            return None
        market = MARKET_BY_INTENT.get(query.intent, Market.PLAYER_HITS.value)
        limit = query.count or 5
        stmt = select(Prediction).where(
            Prediction.game_date == (query.day or date.today()),
            Prediction.market == market,
        )
        if market == Market.PLAYER_HITS.value:
            stmt = stmt.where(Prediction.line <= 0.5)  # the "1+ hit" line
        rows = db.scalars(
            stmt.order_by((Prediction.probability * Prediction.confidence).desc()).limit(limit)
        ).all()
        if not rows:
            return AgentInsight(
                agent=self.name, title=self.title,
                headline="Aún no hay líneas de bateo calculadas para hoy.",
                bullets=["Faltan alineaciones o estadísticas; el ciclo las sincroniza automáticamente."],
                confidence=0.3,
            )
        bullets, picks = [], []
        for r in rows:
            stat = db.scalar(
                select(PlayerStat).where(
                    PlayerStat.player_mlb_id == r.player_mlb_id,
                    PlayerStat.kind == "batting",
                    PlayerStat.scope == "season",
                )
            )
            s = stat.stats if stat else {}
            last5 = s.get("last5_hits") or []
            form = f"últimos 5 juegos: {sum(last5)} hits" if last5 else "sin forma reciente aún"
            bullets.append(
                f"{r.selection} — {r.probability:.0%}. AVG {s.get('avg', '—')}, "
                f"OPS {s.get('ops', '—')}, {form}."
            )
            picks.append({
                "prediction_id": r.id, "player": self._name(db, r.player_mlb_id) or r.selection,
                "selection": r.selection, "market": r.market, "probability": r.probability,
                "line": r.line, "book_odds": r.book_odds, "confidence": r.confidence,
                "last5_hits": last5, "why": r.explanation,
            })
        return AgentInsight(
            agent=self.name, title=self.title,
            headline=f"Mejores {len(rows)} selecciones de bateo ({market.replace('player_', '')}).",
            bullets=bullets, picks=picks,
            confidence=float(sum(r.confidence for r in rows) / len(rows)),
        )

    @staticmethod
    def _name(db: Session, mlb_id: int | None) -> str | None:
        if not mlb_id:
            return None
        row = db.scalar(select(Player).where(Player.mlb_id == mlb_id))
        return row.full_name if row else None
