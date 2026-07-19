"""FanGraphs — advanced pitching/batting leaderboards via public JSON API."""
from __future__ import annotations

from datetime import date
from typing import Any

from app.infrastructure.providers.base import BaseProvider


class FangraphsProvider(BaseProvider):
    source_name = "fangraphs"
    base_url = "https://www.fangraphs.com/api"

    def leaders(self, stats: str = "pit", qual: str = "0") -> list[dict[str, Any]]:
        """Season leaderboard: FIP, xFIP, Stuff+, Location+, Pitching+, CSW% (pit)
        or wOBA/wRC+ family (bat)."""
        data = self._get(
            "/leaders/major-league/data",
            params={
                "age": "",
                "pos": "all",
                "stats": stats,
                "lg": "all",
                "season": date.today().year,
                "season1": date.today().year,
                "ind": 0,
                "qual": qual,
                "pageitems": 500,
                "pagenum": 1,
            },
        )
        return data.get("data", []) if isinstance(data, dict) else []
