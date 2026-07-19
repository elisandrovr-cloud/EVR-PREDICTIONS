"""Provider registry — one place the app asks for any data source.

Primary live sources (MLB Stats API, Baseball Savant, FanGraphs, Odds API,
OpenWeather) are fully implemented. Licensed/paywalled feeds (Rotowire,
Action Network, VSIN, sharp-money APIs…) are declared as adapters with the
same interface so wiring a key/scraper in later requires zero changes
elsewhere; until then they report status `disabled`.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

from app.infrastructure.providers.base import BaseProvider
from app.infrastructure.providers.fangraphs import FangraphsProvider
from app.infrastructure.providers.mlb_stats import MlbStatsProvider
from app.infrastructure.providers.odds_api import OddsApiProvider
from app.infrastructure.providers.savant import SavantProvider
from app.infrastructure.providers.weather import WeatherProvider


class LicensedFeedAdapter(BaseProvider):
    """Placeholder adapter for feeds that need a commercial license or scraper."""

    def __init__(self, name: str, url: str) -> None:
        self.source_name = name
        self.base_url = url
        super().__init__()

    @property
    def enabled(self) -> bool:
        return False

    def fetch(self) -> list[dict[str, Any]]:
        return []


LICENSED_FEEDS = [
    ("baseball_reference", "https://www.baseball-reference.com"),
    ("rotowire", "https://www.rotowire.com"),
    ("fantasypros", "https://www.fantasypros.com"),
    ("action_network", "https://www.actionnetwork.com"),
    ("covers", "https://www.covers.com"),
    ("umpire_scorecards", "https://umpscorecards.com"),
    ("codify_baseball", "https://codifybaseball.com"),
    ("pitcher_list", "https://pitcherlist.com"),
    ("rotogrinders", "https://rotogrinders.com"),
    ("vsin", "https://vsin.com"),
    ("sharp_money", "https://unabated.com"),
]


class ProviderRegistry:
    def __init__(self) -> None:
        self.mlb = MlbStatsProvider()
        self.odds = OddsApiProvider()
        self.weather = WeatherProvider()
        self.savant = SavantProvider()
        self.fangraphs = FangraphsProvider()
        self.licensed: list[LicensedFeedAdapter] = [LicensedFeedAdapter(n, u) for n, u in LICENSED_FEEDS]

    def all_providers(self) -> list[BaseProvider]:
        return [self.mlb, self.odds, self.weather, self.savant, self.fangraphs, *self.licensed]

    def statuses(self) -> list[dict[str, Any]]:
        return [p.report_status() for p in self.all_providers()]


@lru_cache
def get_registry() -> ProviderRegistry:
    return ProviderRegistry()
