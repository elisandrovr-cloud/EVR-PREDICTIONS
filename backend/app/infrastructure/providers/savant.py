"""Baseball Savant — Statcast expected stats & quality-of-contact leaderboards (free CSV)."""
from __future__ import annotations

import csv
import io
from typing import Any

from app.infrastructure.providers.base import BaseProvider


class SavantProvider(BaseProvider):
    source_name = "baseball_savant"
    base_url = "https://baseballsavant.mlb.com"

    def _csv(self, path: str, params: dict[str, Any]) -> list[dict[str, str]]:
        resp = self._client.get(path, params=params)
        resp.raise_for_status()
        reader = csv.DictReader(io.StringIO(resp.text))
        return list(reader)

    def expected_stats(self, player_type: str = "batter") -> list[dict[str, str]]:
        """xBA / xSLG / xwOBA / xERA leaderboard for the current season."""
        return self._csv(
            "/leaderboard/expected_statistics",
            {"type": player_type, "position": "", "team": "", "min": "q", "csv": "true"},
        )

    def statcast_quality(self, player_type: str = "batter") -> list[dict[str, str]]:
        """Barrel%, hard-hit%, sweet-spot%, EV leaderboards."""
        return self._csv(
            "/leaderboard/statcast",
            {"type": player_type, "min": "q", "sort": "barrels_per_pa_percent", "sortDir": "desc", "csv": "true"},
        )
