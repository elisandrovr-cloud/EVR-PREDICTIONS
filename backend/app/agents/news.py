"""Agent 7 — News Intelligence.

Turns official MLB signals into a readable news feed: the transaction wire,
roster-status moves (injured list, activations, suspensions) and pitcher changes
detected by the other agents. Third-party newsrooms can be added through the
provider registry without touching this agent.
"""
from __future__ import annotations

import hashlib
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.base import AgentInsight, AgentReport, BaseAgent, ChatQuery
from app.infrastructure.db.models import Player, PlayerNews, RosterChange
from app.infrastructure.providers.registry import ProviderRegistry

CATEGORY_BY_CHANGE = {
    "injury": "injury",
    "suspended": "injury",
    "activated": "transaction",
    "optioned": "transaction",
    "added": "transaction",
    "removed": "transaction",
    "status_change": "transaction",
    "pitcher_change": "news",
    "lineup_posted": "news",
    "lineup_absence": "news",
    "lineup_order": "news",
}

HEADLINE_BY_CHANGE = {
    "injury": "Lesión",
    "suspended": "Suspensión",
    "activated": "Activado",
    "optioned": "Enviado a ligas menores",
    "added": "Movimiento de roster",
    "removed": "Baja del roster",
    "status_change": "Cambio de estatus",
    "pitcher_change": "Cambio de abridor",
    "lineup_posted": "Alineación publicada",
    "lineup_absence": "Ausencia en la alineación",
    "lineup_order": "Cambio en el orden al bate",
}


def _fingerprint(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


class NewsIntelligenceAgent(BaseAgent):
    name = "news_intelligence"
    title = "News Intelligence"
    description = "Publica noticias oficiales: lesiones, movimientos, cambios de pitcher y de última hora."
    specialties = ("noticia", "noticias", "news", "lesion", "lesión", "reporte")

    def work(self, db: Session, reg: ProviderRegistry, day: date) -> AgentReport:
        since = datetime.now(timezone.utc) - timedelta(hours=36)
        changes = db.scalars(
            select(RosterChange).where(RosterChange.detected_at >= since).order_by(RosterChange.detected_at.desc())
        ).all()
        created = 0
        for change in changes:
            fingerprint = _fingerprint(
                change.change_type, str(change.player_mlb_id or ""), change.detail[:120],
                change.detected_at.date().isoformat(),
            )
            if db.scalar(select(PlayerNews).where(PlayerNews.fingerprint == fingerprint)):
                continue
            prefix = HEADLINE_BY_CHANGE.get(change.change_type, "Actualización")
            subject = change.player_name or "MLB"
            db.add(PlayerNews(
                player_mlb_id=change.player_mlb_id,
                team_mlb_id=change.team_mlb_id,
                headline=f"{prefix}: {subject}",
                body=change.detail,
                category=CATEGORY_BY_CHANGE.get(change.change_type, "news"),
                source="mlb_stats_api",
                fingerprint=fingerprint,
                published_at=change.detected_at,
            ))
            created += 1
        db.commit()

        total = len(db.scalars(select(PlayerNews).where(PlayerNews.published_at >= since)).all())
        return AgentReport(
            agent=self.name,
            summary=f"{created} noticias nuevas; {total} en las últimas 36 horas.",
            details={"created": created, "recent_total": total},
            items_processed=len(changes),
            changes_detected=created,
        )

    def insight(self, db: Session, query: ChatQuery) -> AgentInsight | None:
        if query.intent not in ("news", "general", "player"):
            return None
        stmt = select(PlayerNews).order_by(PlayerNews.published_at.desc()).limit(6)
        if query.intent == "player" and query.player_name:
            player = db.scalar(select(Player).where(Player.full_name.ilike(f"%{query.player_name}%")))
            if player is None:
                return None
            stmt = (
                select(PlayerNews)
                .where(PlayerNews.player_mlb_id == player.mlb_id)
                .order_by(PlayerNews.published_at.desc())
                .limit(5)
            )
        items = db.scalars(stmt).all()
        if not items:
            return AgentInsight(
                agent=self.name, title=self.title,
                headline="Sin noticias relevantes registradas.",
                bullets=["El monitoreo oficial no ha reportado movimientos recientes."],
                confidence=0.4,
            )
        injuries = [n for n in items if n.category == "injury"]
        return AgentInsight(
            agent=self.name, title=self.title,
            headline=(
                f"{len(injuries)} alerta(s) de lesión entre las últimas noticias."
                if injuries else f"{len(items)} noticias recientes."
            ),
            bullets=[f"{n.headline} — {n.body[:140]}" for n in items],
            confidence=0.7 if injuries else 0.55,
        )
