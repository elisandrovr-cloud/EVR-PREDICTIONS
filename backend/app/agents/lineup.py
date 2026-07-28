"""Agent 2 — Lineup Intelligence.

Waits for official lineups, then compares them against what we expected: who is
missing, who moved in the batting order, and whether the probable pitcher
changed. Every surprise is logged and the affected game is queued for an
immediate recalculation.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.base import AgentInsight, AgentReport, BaseAgent, ChatQuery
from app.application import ingestion
from app.infrastructure.db.models import Game, RosterChange
from app.infrastructure.providers.registry import ProviderRegistry


def _order(lineup: list[dict[str, Any]]) -> list[int]:
    return [s.get("id") for s in lineup if s.get("id")]


def _names(lineup: list[dict[str, Any]]) -> dict[int, str]:
    return {s["id"]: s.get("name", "?") for s in lineup if s.get("id")}


class LineupIntelligenceAgent(BaseAgent):
    name = "lineup_intelligence"
    title = "Lineup Intelligence"
    description = "Detecta la publicación de alineaciones oficiales, ausencias, cambios de orden y de abridor."
    specialties = ("lineup", "alineacion", "alineación", "orden al bate", "abridor", "titular")

    def work(self, db: Session, reg: ProviderRegistry, day: date) -> AgentReport:
        try:
            payload = reg.mlb.schedule(day)
        except Exception as exc:  # noqa: BLE001
            return AgentReport(agent=self.name, status="error", summary=f"Sin schedule: {str(exc)[:120]}")

        # Snapshot the pre-update state so we can diff against what arrives.
        before: dict[int, dict[str, Any]] = {}
        for g in db.scalars(select(Game).where(Game.game_date == day)):
            before[g.game_pk] = {
                "lineups": g.lineups or {},
                "confirmed": g.lineup_confirmed,
                "home_p": g.home_pitcher_mlb_id,
                "away_p": g.away_pitcher_mlb_id,
            }

        changes = 0
        affected: list[int] = []
        for g in payload:
            game_pk = g.get("gamePk")
            if not game_pk:
                continue
            prev = before.get(game_pk)
            if prev is None:
                continue  # brand-new game; sync below will create it
            fresh = ingestion.extract_lineups(g)
            game_changes = self._diff_game(db, game_pk, prev, fresh, g)
            if game_changes:
                changes += game_changes
                affected.append(game_pk)

        # Persist the same payload we just diffed (no second API call).
        stats = ingestion.sync_schedule(db, day, reg, payload=payload)
        db.commit()

        summary = (
            f"{stats['games']} juegos revisados, {changes} novedades de alineación."
            if changes else f"{stats['games']} juegos revisados, alineaciones sin cambios."
        )
        return AgentReport(
            agent=self.name, summary=summary,
            details={"games": stats["games"], "affected_games": affected,
                     "lineups_confirmed": stats["lineups_confirmed"]},
            items_processed=stats["games"], changes_detected=changes,
        )

    def _diff_game(
        self, db: Session, game_pk: int, prev: dict[str, Any], fresh: dict[str, Any], raw: dict[str, Any]
    ) -> int:
        changes = 0
        prev_lu = prev["lineups"] or {}
        was_projected = bool(prev_lu.get("projected"))
        for side in ("home", "away"):
            new_side = fresh.get(side) or []
            old_side = prev_lu.get(side) or []
            if not new_side:
                continue
            new_ids, old_ids = _order(new_side), _order(old_side)
            new_names = _names(new_side)

            if not old_ids or was_projected:
                self.record_change(
                    db, "lineup_posted",
                    f"Alineación oficial publicada ({side}): {', '.join(list(new_names.values())[:5])}…",
                    detected_by=self.name, game_pk=game_pk, severity="warning",
                    new_value=",".join(str(i) for i in new_ids[:9]),
                )
                changes += 1
                if old_ids:  # projected lineup existed → report the surprises
                    missing = [n for i, n in _names(old_side).items() if i not in new_ids]
                    if missing:
                        self.record_change(
                            db, "lineup_absence",
                            f"No están en la alineación ({side}): {', '.join(missing[:4])}.",
                            detected_by=self.name, game_pk=game_pk, severity="warning",
                        )
                        changes += 1
                continue

            if new_ids != old_ids:
                dropped = [n for i, n in _names(old_side).items() if i not in new_ids]
                if dropped:
                    self.record_change(
                        db, "lineup_absence", f"Fuera de la alineación ({side}): {', '.join(dropped[:4])}.",
                        detected_by=self.name, game_pk=game_pk, severity="warning",
                    )
                    changes += 1
                moved = [
                    f"{new_names[pid]} {old_ids.index(pid) + 1}º→{new_ids.index(pid) + 1}º"
                    for pid in new_ids
                    if pid in old_ids and old_ids.index(pid) != new_ids.index(pid)
                ]
                if moved:
                    self.record_change(
                        db, "lineup_order", f"Cambios de orden ({side}): {', '.join(moved[:4])}.",
                        detected_by=self.name, game_pk=game_pk, severity="info",
                    )
                    changes += 1

        teams = raw.get("teams", {})
        for side in ("home", "away"):
            new_p = ((teams.get(side) or {}).get("probablePitcher") or {}).get("id")
            new_name = ((teams.get(side) or {}).get("probablePitcher") or {}).get("fullName", "?")
            old_p = prev["home_p"] if side == "home" else prev["away_p"]
            if new_p and old_p and new_p != old_p:
                self.record_change(
                    db, "pitcher_change", f"Cambio de abridor ({side}): ahora lanza {new_name}.",
                    detected_by=self.name, game_pk=game_pk, player_mlb_id=new_p,
                    player_name=new_name, previous_value=str(old_p), new_value=str(new_p),
                    severity="critical",
                )
                changes += 1
        return changes

    def insight(self, db: Session, query: ChatQuery) -> AgentInsight | None:
        if query.intent not in ("lineup", "general", "news"):
            return None
        confirmed = db.scalars(
            select(Game).where(Game.game_date == (query.day or date.today()), Game.lineup_confirmed.is_(True))
        ).all()
        total = len(db.scalars(select(Game).where(Game.game_date == (query.day or date.today()))).all())
        recent = db.scalars(
            select(RosterChange)
            .where(RosterChange.change_type.in_(["lineup_posted", "lineup_absence", "lineup_order", "pitcher_change"]))
            .order_by(RosterChange.detected_at.desc())
            .limit(5)
        ).all()
        return AgentInsight(
            agent=self.name, title=self.title,
            headline=f"{len(confirmed)} de {total} alineaciones oficiales confirmadas.",
            bullets=[c.detail for c in recent] or ["Sin sorpresas de alineación registradas."],
            confidence=0.8 if confirmed else 0.5,
        )
