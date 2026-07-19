"""The Odds API — sportsbook lines for MLB (moneyline, run line, totals, props)."""
from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.infrastructure.providers.base import BaseProvider

SPORT_KEY = "baseball_mlb"


class OddsApiProvider(BaseProvider):
    source_name = "odds_api"
    base_url = settings.ODDS_API_BASE

    @property
    def enabled(self) -> bool:
        return bool(settings.ODDS_API_KEY)

    def game_odds(self) -> list[dict[str, Any]]:
        if not self.enabled:
            return []
        data = self._get(
            f"/sports/{SPORT_KEY}/odds",
            params={
                "apiKey": settings.ODDS_API_KEY,
                "regions": "us",
                "markets": "h2h,spreads,totals",
                "oddsFormat": "american",
            },
        )
        return data if isinstance(data, list) else []

    def event_props(self, event_id: str) -> dict[str, Any]:
        if not self.enabled:
            return {}
        return self._get(
            f"/sports/{SPORT_KEY}/events/{event_id}/odds",
            params={
                "apiKey": settings.ODDS_API_KEY,
                "regions": "us",
                "markets": (
                    "batter_hits,batter_home_runs,batter_rbis,batter_total_bases,batter_stolen_bases,"
                    "batter_walks,pitcher_strikeouts,pitcher_outs,pitcher_hits_allowed,pitcher_walks,"
                    "pitcher_earned_runs"
                ),
                "oddsFormat": "american",
            },
        )
