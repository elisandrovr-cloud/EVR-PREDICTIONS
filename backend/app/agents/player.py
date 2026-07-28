"""Agent 3 — Player Intelligence.

Builds and maintains the player database: bio, photo, position, handedness and
roster status for every player involved in today's games, pulled from the
official MLB `/people` endpoint. Feeds the per-player profile pages.
"""
from __future__ import annotations

import time
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.agents.base import AgentInsight, AgentReport, BaseAgent, ChatQuery
from app.core.config import settings
from app.infrastructure.db.models import Game, Player, PlayerStat
from app.infrastructure.providers.registry import ProviderRegistry

PROFILE_TTL = timedelta(days=3)


class PlayerIntelligenceAgent(BaseAgent):
    name = "player_intelligence"
    title = "Player Intelligence"
    description = "Mantiene la base de datos de jugadores: biografía, foto, posición, mano y estado."
    specialties = ("jugador", "perfil", "biografia", "biografía", "quien es", "quién es")

    def work(self, db: Session, reg: ProviderRegistry, day: date) -> AgentReport:
        started = time.perf_counter()
        pending = self._players_needing_profile(db, day)
        updated = 0
        for batch_start in range(0, len(pending), 40):
            if (time.perf_counter() - started) > settings.AGENT_CYCLE_SECONDS:
                break
            batch = pending[batch_start:batch_start + 40]
            try:
                people = reg.mlb.people(batch)
            except Exception:  # noqa: BLE001
                break
            for person in people:
                if self._apply_profile(db, person, reg):
                    updated += 1
            db.commit()

        counts = self._counts(db)
        return AgentReport(
            agent=self.name,
            summary=(
                f"{updated} perfiles actualizados. Base: {counts['batters']} bateadores, "
                f"{counts['pitchers']} lanzadores."
            ),
            details={**counts, "pending": max(0, len(pending) - updated)},
            items_processed=updated,
            changes_detected=updated,
        )

    def _players_needing_profile(self, db: Session, day: date) -> list[int]:
        """Slate players first, then anyone in the DB with a stale/missing profile."""
        slate: list[int] = []
        for g in db.scalars(select(Game).where(Game.game_date == day)):
            for pid in (g.home_pitcher_mlb_id, g.away_pitcher_mlb_id):
                if pid:
                    slate.append(pid)
            for side in ("home", "away"):
                for slot in (g.lineups or {}).get(side, []):
                    if slot.get("id"):
                        slate.append(slot["id"])
        cutoff = datetime.now(timezone.utc) - PROFILE_TTL
        stale = {
            p.mlb_id
            for p in db.scalars(
                select(Player).where(
                    or_(Player.profile_updated_at.is_(None), Player.profile_updated_at < cutoff)
                ).limit(400)
            )
        }
        ordered = [pid for pid in dict.fromkeys(slate) if pid in stale]
        ordered += [pid for pid in stale if pid not in ordered]
        return ordered

    def _apply_profile(self, db: Session, person: dict, reg: ProviderRegistry) -> bool:
        pid = person.get("id")
        if not pid:
            return False
        row = db.scalar(select(Player).where(Player.mlb_id == pid))
        if row is None:
            row = Player(mlb_id=pid, full_name=person.get("fullName", ""))
            db.add(row)
        position = person.get("primaryPosition") or {}
        row.full_name = person.get("fullName") or row.full_name
        row.position = position.get("abbreviation") or row.position
        row.is_pitcher = position.get("type") == "Pitcher"
        row.bats = ((person.get("batSide") or {}).get("code") or row.bats)
        row.throws = ((person.get("pitchHand") or {}).get("code") or row.throws)
        row.age = person.get("currentAge") or row.age
        row.birth_date = person.get("birthDate") or row.birth_date
        row.height = person.get("height") or row.height
        row.weight = person.get("weight") or row.weight
        if person.get("primaryNumber"):
            row.jersey_number = str(person["primaryNumber"])
        if (person.get("currentTeam") or {}).get("id"):
            row.team_mlb_id = person["currentTeam"]["id"]
        row.photo_url = reg.mlb.headshot_url(pid)
        row.profile_updated_at = datetime.now(timezone.utc)
        return True

    @staticmethod
    def _counts(db: Session) -> dict[str, int]:
        total = int(db.scalar(select(func.count(Player.id))) or 0)
        pitchers = int(db.scalar(select(func.count(Player.id)).where(Player.is_pitcher.is_(True))) or 0)
        with_photo = int(db.scalar(select(func.count(Player.id)).where(Player.photo_url.isnot(None))) or 0)
        return {"players": total, "batters": total - pitchers, "pitchers": pitchers, "with_photo": with_photo}

    def insight(self, db: Session, query: ChatQuery) -> AgentInsight | None:
        if query.intent != "player" or not query.player_name:
            return None
        row = db.scalar(select(Player).where(Player.full_name.ilike(f"%{query.player_name}%")))
        if row is None:
            return AgentInsight(
                agent=self.name, title=self.title,
                headline=f"No encuentro a «{query.player_name}» en la base todavía.",
                bullets=["Prueba con el nombre completo, o espera al próximo ciclo de sincronización."],
                confidence=0.3,
            )
        stat = db.scalar(
            select(PlayerStat).where(
                PlayerStat.player_mlb_id == row.mlb_id,
                PlayerStat.kind == ("pitching" if row.is_pitcher else "batting"),
                PlayerStat.scope == "season",
            )
        )
        bullets = [
            f"{row.position or '—'} · {'lanza' if row.is_pitcher else 'batea'} "
            f"{(row.throws if row.is_pitcher else row.bats) or '?'} · {row.age or '?'} años",
            f"Estado de roster: {row.roster_status or 'sin dato'}",
        ]
        if stat and stat.stats:
            s = stat.stats
            if row.is_pitcher:
                bullets.append(
                    f"ERA {s.get('era', '—')} · WHIP {s.get('whip', '—')} · K/9 {s.get('k_per_9', '—')}"
                )
            else:
                bullets.append(
                    f"AVG {s.get('avg', '—')} · OPS {s.get('ops', '—')} · "
                    f"hits en últimos 5: {s.get('last5_total_hits', '—')}"
                )
        return AgentInsight(
            agent=self.name, title=self.title,
            headline=f"{row.full_name} — perfil oficial.",
            bullets=bullets,
            picks=[{"player_mlb_id": row.mlb_id, "player": row.full_name}],
            confidence=0.7,
        )
