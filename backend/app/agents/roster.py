"""Agent 1 — Roster Intelligence.

Watches the official MLB rosters and transaction wire and records every movement:
injuries, activations, options to the minors, suspensions, rest days, additions
and removals. Any change it finds is written to the audit history and flagged so
the Supervisor can force a recalculation.
"""
from __future__ import annotations

import time
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.base import AgentInsight, AgentReport, BaseAgent, ChatQuery
from app.core.config import settings
from app.infrastructure.cache.redis_client import get_redis
from app.infrastructure.db.models import Game, Player, RosterChange, Team
from app.infrastructure.providers.registry import ProviderRegistry

CURSOR_KEY = "evr:agent:roster:cursor"

# MLB transaction typeDesc → our change vocabulary + severity
TRANSACTION_MAP: dict[str, tuple[str, str]] = {
    "Status Change": ("status_change", "warning"),
    "Optioned": ("optioned", "warning"),
    "Recalled": ("activated", "info"),
    "Activated": ("activated", "info"),
    "Selected": ("added", "info"),
    "Signed": ("added", "info"),
    "Released": ("removed", "warning"),
    "Designated for Assignment": ("removed", "warning"),
    "Traded": ("added", "warning"),
    "Suspended": ("suspended", "critical"),
    "Placed on Injured List": ("injury", "critical"),
    "Outrighted": ("optioned", "info"),
}


def _classify_transaction(type_desc: str, description: str) -> tuple[str, str]:
    if type_desc in TRANSACTION_MAP:
        return TRANSACTION_MAP[type_desc]
    text = f"{type_desc} {description}".lower()
    if "injured list" in text or "injury" in text:
        return "injury", "critical"
    if "suspend" in text:
        return "suspended", "critical"
    if "activat" in text or "recall" in text:
        return "activated", "info"
    if "option" in text:
        return "optioned", "warning"
    return "status_change", "info"


def _is_injury_status(status: str | None) -> bool:
    return bool(status) and ("injured" in status.lower() or "il" == status.lower().strip())


class RosterIntelligenceAgent(BaseAgent):
    name = "roster_intelligence"
    title = "Roster Intelligence"
    description = "Vigila rosters oficiales, lesiones, activaciones, bajadas a ligas menores y suspensiones."
    specialties = ("roster", "lesion", "lesiones", "injury", "cambios", "movimientos", "suspension")

    def work(self, db: Session, reg: ProviderRegistry, day: date) -> AgentReport:
        changes = 0
        processed = 0
        started = time.perf_counter()
        budget = settings.AGENT_CYCLE_SECONDS

        changes += self._sync_transactions(db, reg, day)

        teams = self._teams_to_check(db, reg, day)
        for team_id in teams:
            if (time.perf_counter() - started) > budget:
                break
            changes += self._diff_roster(db, reg, team_id)
            processed += 1
        db.commit()

        return AgentReport(
            agent=self.name,
            summary=(
                f"{processed} rosters revisados, {changes} cambios detectados."
                if changes
                else f"{processed} rosters revisados, sin novedades."
            ),
            details={"teams_checked": processed, "changes": changes},
            items_processed=processed,
            changes_detected=changes,
        )

    # ── roster diffing ──────────────────────────────────────────────────────
    def _teams_to_check(self, db: Session, reg: ProviderRegistry, day: date) -> list[int]:
        """Teams playing today first, then the rest of the league, round-robin so a
        one-minute cycle eventually covers all 30 without ever running long."""
        playing: list[int] = []
        for g in db.scalars(select(Game).where(Game.game_date == day)):
            for tid in (g.home_team_mlb_id, g.away_team_mlb_id):
                if tid and tid not in playing:
                    playing.append(tid)
        others = [t.mlb_id for t in db.scalars(select(Team)) if t.mlb_id not in playing]
        if not playing and not others:
            # Cold database: ask the official API for the league instead of idling.
            try:
                others = [t["id"] for t in reg.mlb.teams() if t.get("id")]
            except Exception:  # noqa: BLE001
                others = []
        ordered = playing + others
        if not ordered:
            return []
        start = 0
        try:
            raw = get_redis().get(CURSOR_KEY)
            start = int(raw) % len(ordered) if raw else 0
            get_redis().setex(CURSOR_KEY, 3600, (start + 6) % len(ordered))
        except Exception:  # noqa: BLE001 — Redis is optional
            pass
        return ordered[start:] + ordered[:start]

    def _diff_roster(self, db: Session, reg: ProviderRegistry, team_id: int) -> int:
        try:
            roster = reg.mlb.roster(team_id)
        except Exception:  # noqa: BLE001 — a single team must not kill the cycle
            return 0
        if not roster:
            return 0

        seen_ids: set[int] = set()
        changes = 0
        for entry in roster:
            person = entry.get("person") or {}
            pid = person.get("id")
            if not pid:
                continue
            seen_ids.add(pid)
            name = person.get("fullName") or ""
            status = (entry.get("status") or {}).get("description")
            position = (entry.get("position") or {}).get("abbreviation")
            is_pitcher = (entry.get("position") or {}).get("type") == "Pitcher"

            row = db.scalar(select(Player).where(Player.mlb_id == pid))
            if row is None:
                row = Player(mlb_id=pid, full_name=name, team_mlb_id=team_id)
                db.add(row)
                self.record_change(
                    db, "added", f"{name} aparece en el roster activo.",
                    detected_by=self.name, team_mlb_id=team_id, player_mlb_id=pid,
                    player_name=name, new_value=status, severity="info",
                )
                changes += 1
            else:
                if row.team_mlb_id and row.team_mlb_id != team_id:
                    self.record_change(
                        db, "added", f"{name} cambió de equipo.",
                        detected_by=self.name, team_mlb_id=team_id, player_mlb_id=pid,
                        player_name=name, previous_value=str(row.team_mlb_id),
                        new_value=str(team_id), severity="warning",
                    )
                    changes += 1
                if status and row.roster_status and status != row.roster_status:
                    severity = "critical" if _is_injury_status(status) else "warning"
                    kind = "injury" if _is_injury_status(status) else "status_change"
                    self.record_change(
                        db, kind, f"{name}: {row.roster_status} → {status}.",
                        detected_by=self.name, team_mlb_id=team_id, player_mlb_id=pid,
                        player_name=name, previous_value=row.roster_status,
                        new_value=status, severity=severity,
                    )
                    changes += 1
            row.full_name = name or row.full_name
            row.team_mlb_id = team_id
            row.position = position or row.position
            row.is_pitcher = is_pitcher
            row.roster_status = status or row.roster_status
            if not row.jersey_number and entry.get("jerseyNumber"):
                row.jersey_number = str(entry["jerseyNumber"])

        # Players we believed were on this roster but no longer are.
        previously = db.scalars(
            select(Player).where(Player.team_mlb_id == team_id, Player.roster_status.isnot(None))
        ).all()
        for row in previously:
            if row.mlb_id not in seen_ids and row.roster_status != "Fuera del roster":
                self.record_change(
                    db, "removed", f"{row.full_name} ya no figura en el roster activo.",
                    detected_by=self.name, team_mlb_id=team_id, player_mlb_id=row.mlb_id,
                    player_name=row.full_name, previous_value=row.roster_status,
                    new_value="Fuera del roster", severity="warning",
                )
                row.roster_status = "Fuera del roster"
                changes += 1
        return changes

    # ── official transaction wire ───────────────────────────────────────────
    def _sync_transactions(self, db: Session, reg: ProviderRegistry, day: date) -> int:
        try:
            transactions = reg.mlb.transactions(day, day)
        except Exception:  # noqa: BLE001
            return 0
        changes = 0
        for tx in transactions:
            person = tx.get("person") or {}
            pid = person.get("id")
            name = person.get("fullName") or ""
            description = tx.get("description") or ""
            type_desc = tx.get("typeDesc") or ""
            kind, severity = _classify_transaction(type_desc, description)
            # skip duplicates already recorded today for this player+description
            exists = db.scalar(
                select(RosterChange).where(
                    RosterChange.player_mlb_id == pid,
                    RosterChange.detail == description,
                    RosterChange.change_type == kind,
                )
            )
            if exists:
                continue
            self.record_change(
                db, kind, description or f"{type_desc}: {name}",
                detected_by=self.name,
                team_mlb_id=(tx.get("toTeam") or {}).get("id"),
                player_mlb_id=pid, player_name=name,
                new_value=type_desc, severity=severity,
            )
            changes += 1
        return changes

    # ── chat ────────────────────────────────────────────────────────────────
    def insight(self, db: Session, query: ChatQuery) -> AgentInsight | None:
        if query.intent not in ("news", "roster", "general", "player"):
            return None
        recent = db.scalars(
            select(RosterChange).order_by(RosterChange.detected_at.desc()).limit(8)
        ).all()
        if not recent:
            return AgentInsight(
                agent=self.name, title=self.title,
                headline="Sin movimientos de roster registrados todavía.",
                bullets=["El monitoreo corre cada minuto; aún no hay cambios que reportar."],
                confidence=0.4,
            )
        critical = [c for c in recent if c.severity == "critical"]
        return AgentInsight(
            agent=self.name, title=self.title,
            headline=(
                f"{len(critical)} movimiento(s) crítico(s) en los últimos cambios."
                if critical else f"{len(recent)} movimientos recientes de roster."
            ),
            bullets=[f"{c.detail} ({c.change_type})" for c in recent[:5]],
            confidence=0.75 if critical else 0.6,
        )
