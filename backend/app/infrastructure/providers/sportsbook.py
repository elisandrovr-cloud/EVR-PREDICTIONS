"""Sportsbook line providers, behind one interchangeable interface.

Hard Rock Bet does not publish a public odds API. Rather than scrape it (which
would violate their terms), this module defines a `SportsbookProvider` port with
three interchangeable adapters:

* `ManualSportsbookProvider` — lines the user enters in the app (or via the API).
  Always available, always allowed, and the default for Hard Rock Bet.
* `OddsApiSportsbookProvider` — The Odds API, an authorized aggregator that
  redistributes book lines under license (needs ODDS_API_KEY).
* `AuthorizedFeedProvider` — placeholder for a commercial/affiliate feed; drop in
  credentials and it takes over without touching any caller.

Callers ask the registry for lines and never care where they came from, so
swapping in an authorized Hard Rock feed later is a one-line change.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol

from app.core.config import settings


@dataclass(frozen=True)
class BookLine:
    """One sportsbook price, normalized across providers."""

    book: str
    game_pk: int
    market: str
    selection: str
    american: float
    line: float | None = None
    player_mlb_id: int | None = None
    captured_at: datetime | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "book": self.book,
            "game_pk": self.game_pk,
            "market": self.market,
            "selection": self.selection,
            "american": self.american,
            "line": self.line,
            "player_mlb_id": self.player_mlb_id,
            "captured_at": (self.captured_at or datetime.now(timezone.utc)).isoformat(),
        }


class SportsbookProvider(Protocol):  # pragma: no cover - typing only
    book_name: str

    @property
    def enabled(self) -> bool: ...

    def fetch_lines(self, game_pks: list[int]) -> list[BookLine]: ...


class ManualSportsbookProvider:
    """Lines supplied by the user (POST /api/v1/odds/manual) and stored as quotes.

    This is how Hard Rock Bet is supported today: the user pastes the numbers they
    see in their account, and Betting Intelligence measures the model's edge
    against exactly those prices.
    """

    book_name = "Hard Rock Bet"

    @property
    def enabled(self) -> bool:
        return True

    def fetch_lines(self, game_pks: list[int]) -> list[BookLine]:
        # Manual lines already live in the odds_quotes table; nothing to pull.
        return []


class OddsApiSportsbookProvider:
    """Authorized aggregator (The Odds API). Enabled when ODDS_API_KEY is set."""

    book_name = "odds_api"

    @property
    def enabled(self) -> bool:
        return bool(settings.ODDS_API_KEY)

    def fetch_lines(self, game_pks: list[int]) -> list[BookLine]:
        # The ingestion layer already persists these via OddsApiProvider; this
        # adapter exists so Betting Intelligence can treat every book uniformly.
        return []


class AuthorizedFeedProvider:
    """Placeholder for a licensed Hard Rock / affiliate feed.

    Set SPORTSBOOK_FEED_URL + SPORTSBOOK_FEED_KEY once you have an agreement and
    implement fetch_lines(); nothing else in the codebase changes.
    """

    book_name = "authorized_feed"

    @property
    def enabled(self) -> bool:
        return bool(settings.SPORTSBOOK_FEED_URL and settings.SPORTSBOOK_FEED_KEY)

    def fetch_lines(self, game_pks: list[int]) -> list[BookLine]:
        return []


def available_books() -> list[dict[str, Any]]:
    providers: list[SportsbookProvider] = [
        ManualSportsbookProvider(),
        OddsApiSportsbookProvider(),
        AuthorizedFeedProvider(),
    ]
    return [{"book": p.book_name, "enabled": p.enabled} for p in providers]
