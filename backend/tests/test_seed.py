"""Auto-seed: an empty DB gets today's games + predictions on demand (serverless)."""
from __future__ import annotations

from datetime import date, timezone, datetime

from sqlalchemy import func, select

from app.application import seed
from app.infrastructure.db.models import Game, Prediction, Team


class FakeMlb:
    """Minimal stand-in for MlbStatsProvider returning a 2-game slate."""

    def teams(self):
        return [
            {"id": 147, "name": "New York Yankees", "abbreviation": "NYY",
             "league": {"name": "AL"}, "division": {"name": "AL East"}, "venue": {"name": "Yankee Stadium"}},
            {"id": 111, "name": "Boston Red Sox", "abbreviation": "BOS",
             "league": {"name": "AL"}, "division": {"name": "AL East"}, "venue": {"name": "Fenway Park"}},
            {"id": 119, "name": "Los Angeles Dodgers", "abbreviation": "LAD",
             "league": {"name": "NL"}, "division": {"name": "NL West"}, "venue": {"name": "Dodger Stadium"}},
            {"id": 137, "name": "San Francisco Giants", "abbreviation": "SF",
             "league": {"name": "NL"}, "division": {"name": "NL West"}, "venue": {"name": "Oracle Park"}},
        ]

    def schedule(self, day):
        iso = datetime.now(timezone.utc).isoformat()
        return [
            {
                "gamePk": 700001, "gameDate": iso, "status": {"abstractGameState": "Preview"},
                "teams": {
                    "home": {"team": {"id": 147}, "probablePitcher": {"id": 1}, "score": None},
                    "away": {"team": {"id": 111}, "probablePitcher": {"id": 2}, "score": None},
                },
                "venue": {"name": "Yankee Stadium"}, "lineups": {}, "linescore": {}, "officials": [],
            },
            {
                "gamePk": 700002, "gameDate": iso, "status": {"abstractGameState": "Preview"},
                "teams": {
                    "home": {"team": {"id": 119}, "probablePitcher": {"id": 3}, "score": None},
                    "away": {"team": {"id": 137}, "probablePitcher": {"id": 4}, "score": None},
                },
                "venue": {"name": "Dodger Stadium"}, "lineups": {}, "linescore": {}, "officials": [],
            },
        ]


class FakeWeather:
    def conditions_for_venue(self, venue):
        return {}


class FakeRegistry:
    def __init__(self):
        self.mlb = FakeMlb()
        self.weather = FakeWeather()

    def statuses(self):
        return []


class TestAutoSeed:
    def test_empty_db_is_populated(self, db) -> None:
        assert db.scalar(select(func.count(Game.id))) == 0
        result = seed.ensure_today_seeded(db, registry=FakeRegistry())
        assert result["seeded"] is True

        teams = db.scalar(select(func.count(Team.id)))
        games = db.scalar(select(func.count(Game.id)).where(Game.game_date == date.today()))
        preds = db.scalar(select(func.count(Prediction.id)).where(Prediction.game_date == date.today()))
        assert teams == 4
        assert games == 2
        # each game yields moneyline (x2), run line (x2), over, under, first inning
        assert preds >= 2 * 7

    def test_seed_is_idempotent(self, db) -> None:
        seed.ensure_today_seeded(db, registry=FakeRegistry())
        games_after_first = db.scalar(select(func.count(Game.id)))
        preds_after_first = db.scalar(select(func.count(Prediction.id)))
        # second call must not duplicate games or predictions
        seed.ensure_today_seeded(db, registry=FakeRegistry())
        assert db.scalar(select(func.count(Game.id))) == games_after_first
        assert db.scalar(select(func.count(Prediction.id))) == preds_after_first

    def test_disabled_when_auto_seed_off(self, db, monkeypatch) -> None:
        from app.core.config import settings

        monkeypatch.setattr(settings, "AUTO_SEED", False)
        result = seed.ensure_today_seeded(db, registry=FakeRegistry())
        assert result == {"seeded": False, "reason": "disabled"}
        assert db.scalar(select(func.count(Game.id))) == 0

    def test_produces_moneyline_predictions(self, db) -> None:
        seed.ensure_today_seeded(db, registry=FakeRegistry())
        ml = db.scalars(
            select(Prediction).where(Prediction.market == "moneyline", Prediction.game_pk == 700001)
        ).all()
        assert len(ml) == 2  # home + away
        assert all(0 < p.probability < 1 for p in ml)
        assert all(p.explanation for p in ml)
