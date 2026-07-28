"""MLB Stats API (statsapi.mlb.com) — free official source for schedule, lineups,
pitchers, linescores, player/team stats and results."""
from __future__ import annotations

from datetime import date
from typing import Any

from app.core.config import settings
from app.infrastructure.providers.base import BaseProvider


class MlbStatsProvider(BaseProvider):
    source_name = "mlb_stats_api"
    base_url = settings.MLB_STATS_API_BASE

    def schedule(self, day: date) -> list[dict[str, Any]]:
        data = self._get(
            "/schedule",
            params={
                "sportId": 1,
                "date": day.isoformat(),
                "hydrate": "probablePitcher,lineups,weather,officials,linescore,team,venue",
            },
        )
        games: list[dict[str, Any]] = []
        for d in data.get("dates", []):
            games.extend(d.get("games", []))
        return games

    def teams(self) -> list[dict[str, Any]]:
        return self._get("/teams", params={"sportId": 1, "activeStatus": "Y"}).get("teams", [])

    def live_feed(self, game_pk: int) -> dict[str, Any]:
        # v1.1 endpoint lives on the same host, outside the /api/v1 base path
        started = self._client.get(
            f"{settings.MLB_STATS_API_BASE.replace('/api/v1', '')}/api/v1.1/game/{game_pk}/feed/live"
        )
        started.raise_for_status()
        return started.json()

    def boxscore(self, game_pk: int) -> dict[str, Any]:
        return self._get(f"/game/{game_pk}/boxscore")

    def player_stats(self, player_id: int, group: str, stat_type: str = "season") -> dict[str, Any]:
        return self._get(
            f"/people/{player_id}/stats",
            params={"stats": stat_type, "group": group, "season": date.today().year, "gameType": "R"},
        )

    def player_game_log(self, player_id: int, group: str) -> list[dict[str, Any]]:
        data = self._get(
            f"/people/{player_id}/stats",
            params={"stats": "gameLog", "group": group, "season": date.today().year, "gameType": "R"},
        )
        for block in data.get("stats", []):
            return block.get("splits", [])
        return []

    def team_stats(self, team_id: int, group: str) -> dict[str, Any]:
        return self._get(
            f"/teams/{team_id}/stats",
            params={"stats": "season", "group": group, "season": date.today().year, "gameType": "R"},
        )

    def standings(self) -> dict[str, Any]:
        return self._get("/standings", params={"leagueId": "103,104", "season": date.today().year})

    # ── profile / movement endpoints (used by the monitoring agents) ─────────
    def people(self, player_ids: list[int]) -> list[dict[str, Any]]:
        """Full bio for up to ~100 players at once (official /people endpoint)."""
        if not player_ids:
            return []
        ids = ",".join(str(p) for p in player_ids[:100])
        return self._get("/people", params={"personIds": ids}).get("people", [])

    def roster(self, team_id: int, roster_type: str = "active") -> list[dict[str, Any]]:
        return self._get(f"/teams/{team_id}/roster", params={"rosterType": roster_type}).get("roster", [])

    def transactions(self, start: date, end: date) -> list[dict[str, Any]]:
        """Official transaction wire: activations, IL moves, options, releases."""
        return self._get(
            "/transactions",
            params={"startDate": start.isoformat(), "endDate": end.isoformat(), "sportId": 1},
        ).get("transactions", [])

    @staticmethod
    def headshot_url(player_id: int) -> str:
        """Official MLB headshot CDN pattern."""
        return f"https://midfield.mlbstatic.com/v1/people/{player_id}/spots/120"
