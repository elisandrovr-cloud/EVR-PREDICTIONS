"""Domain events — published to Redis pub/sub so workers react without coupling."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import ClassVar

from app.infrastructure.cache.redis_client import get_redis

EVENTS_CHANNEL = "evr:events"


@dataclass
class DomainEvent:
    name: ClassVar[str] = "domain_event"

    def publish(self) -> None:
        payload = {"event": self.name, "at": datetime.now(timezone.utc).isoformat(), "data": asdict(self)}
        try:
            r = get_redis()
            encoded = json.dumps(payload)
            r.publish(EVENTS_CHANNEL, encoded)  # live subscribers (websocket fan-out)
            r.rpush("evr:events:queue", encoded)  # durable queue drained by workers
            r.expire("evr:events:queue", 3600)
        except Exception:  # noqa: BLE001 — events are best-effort
            pass


@dataclass
class LineupConfirmed(DomainEvent):
    name: ClassVar[str] = "lineup_confirmed"
    game_pk: int = 0


@dataclass
class PitcherChanged(DomainEvent):
    name: ClassVar[str] = "pitcher_changed"
    game_pk: int = 0
    team_side: str = ""
    new_pitcher_id: int = 0


@dataclass
class OddsMoved(DomainEvent):
    name: ClassVar[str] = "odds_moved"
    game_pk: int = 0
    market: str = ""
    delta: float = 0.0


@dataclass
class GameFinal(DomainEvent):
    name: ClassVar[str] = "game_final"
    game_pk: int = 0
