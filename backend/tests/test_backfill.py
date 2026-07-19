"""Progressive stat backfill: the slate fills in props / hits board by itself."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select

from app.application import seed
from app.infrastructure.db.models import PlayerStat, Prediction


def _batter(pid: int, name: str, slot: int) -> dict:
    return {"id": pid, "fullName": name, "primaryPosition": {"abbreviation": "OF"}}


class FakeMlb:
    def teams(self):
        return [
            {"id": 147, "name": "New York Yankees", "abbreviation": "NYY",
             "league": {"name": "AL"}, "division": {"name": "AL East"}, "venue": {"name": "Yankee Stadium"}},
            {"id": 111, "name": "Boston Red Sox", "abbreviation": "BOS",
             "league": {"name": "AL"}, "division": {"name": "AL East"}, "venue": {"name": "Fenway Park"}},
        ]

    def schedule(self, day):
        iso = datetime.now(timezone.utc).isoformat()
        return [{
            "gamePk": 500100, "gameDate": iso, "status": {"abstractGameState": "Preview"},
            "teams": {
                "home": {"team": {"id": 147}, "probablePitcher": {"id": 900, "fullName": "Gerrit Cole"}, "score": None},
                "away": {"team": {"id": 111}, "probablePitcher": {"id": 901, "fullName": "Brayan Bello"}, "score": None},
            },
            "venue": {"name": "Yankee Stadium"},
            "lineups": {
                "homePlayers": [_batter(101, "Aaron Judge", 1), _batter(102, "Juan Soto", 2),
                                _batter(103, "Anthony Rizzo", 3)],
                "awayPlayers": [_batter(201, "Rafael Devers", 1), _batter(202, "Trevor Story", 2),
                                _batter(203, "Jarren Duran", 3)],
            },
            "linescore": {}, "officials": [],
        }]

    def player_stats(self, player_id, group, stat_type="season"):
        if group == "pitching":
            stat = {"era": "3.10", "whip": "1.05", "strikeoutsPer9Inn": "11.0", "walksPer9Inn": "2.2",
                    "hitsPer9Inn": "6.9", "homeRunsPer9": "1.0", "strikeOuts": 120, "baseOnBalls": 24,
                    "battersFaced": 400, "hits": 70, "homeRuns": 12, "inningsPitched": "100.0",
                    "gamesStarted": 17, "numberOfPitches": 1600, "hitByPitch": 4}
        else:
            stat = {"avg": ".285", "obp": ".370", "slg": ".520", "ops": ".890", "babip": ".310",
                    "plateAppearances": 400, "hits": 110, "homeRuns": 22, "baseOnBalls": 45,
                    "strikeOuts": 90, "rbi": 60, "runs": 65, "doubles": 24, "triples": 2,
                    "stolenBases": 8, "gamesPlayed": 95}
        return {"stats": [{"splits": [{"stat": stat}]}]}

    def player_game_log(self, player_id, group):
        return [
            {"date": "2026-07-14", "stat": {"hits": 1, "atBats": 4}, "opponent": {"name": "TB"}},
            {"date": "2026-07-15", "stat": {"hits": 2, "atBats": 4}, "opponent": {"name": "TB"}},
            {"date": "2026-07-16", "stat": {"hits": 0, "atBats": 3}, "opponent": {"name": "BAL"}},
            {"date": "2026-07-17", "stat": {"hits": 3, "atBats": 5}, "opponent": {"name": "BAL"}},
            {"date": "2026-07-18", "stat": {"hits": 1, "atBats": 4}, "opponent": {"name": "BOS"}},
        ]

    def team_stats(self, team_id, group):
        if group == "hitting":
            stat = {"ops": ".740", "avg": ".252", "runs": 420, "plateAppearances": 3600,
                    "strikeOuts": 800, "gamesPlayed": 95}
        else:
            stat = {"era": "3.90", "whip": "1.25"}
        return {"stats": [{"splits": [{"stat": stat}]}]}


class FakeWeather:
    def conditions_for_venue(self, venue):
        return {}


class FakeRegistry:
    def __init__(self):
        self.mlb = FakeMlb()
        self.weather = FakeWeather()

    def statuses(self):
        return []


class TestBackfill:
    def test_props_and_hits_board_fill_in(self, db, monkeypatch) -> None:
        monkeypatch.setattr(seed.settings, "SEED_BACKFILL_MIN_INTERVAL", 0.0)
        seed._last_backfill = 0.0
        reg = FakeRegistry()

        # First pass: light seed + a backfill batch + regeneration of the ready game.
        seed.ensure_today_seeded(db, registry=reg)

        # batter + pitcher stats got synced
        assert db.scalar(select(func.count(PlayerStat.id)).where(PlayerStat.kind == "batting")) >= 6
        assert db.scalar(select(func.count(PlayerStat.id)).where(PlayerStat.kind == "pitching")) >= 2

        # player-hit props now exist and carry recent form
        hit_preds = db.scalars(
            select(Prediction).where(Prediction.market == "player_hits", Prediction.line <= 0.5)
        ).all()
        assert len(hit_preds) >= 6
        judge = db.scalar(
            select(PlayerStat).where(PlayerStat.player_mlb_id == 101, PlayerStat.kind == "batting")
        )
        assert judge.stats["last5_hits"] == [1, 2, 0, 3, 1]
        assert judge.stats["last5_total_hits"] == 7

    def test_hits_board_endpoint_populated(self, client, db, monkeypatch) -> None:
        monkeypatch.setattr(seed.settings, "SEED_BACKFILL_MIN_INTERVAL", 0.0)
        seed._last_backfill = 0.0
        # patch the registry the endpoint's seed will use
        monkeypatch.setattr(seed, "get_registry", lambda: FakeRegistry())

        board = client.get("/api/v1/predictions/hits-board").json()
        assert len(board) >= 6
        probs = [r["probability"] for r in board]
        assert probs == sorted(probs, reverse=True)
        judge = next(r for r in board if r["player"] == "Aaron Judge")
        assert judge["last5_hits"] == [1, 2, 0, 3, 1]
        assert judge["team"] == "New York Yankees"

    def test_strikeout_and_hits_agent_parlays_appear(self, client, db, monkeypatch) -> None:
        monkeypatch.setattr(seed.settings, "SEED_BACKFILL_MIN_INTERVAL", 0.0)
        seed._last_backfill = 0.0
        monkeypatch.setattr(seed, "get_registry", lambda: FakeRegistry())

        agents = client.get("/api/v1/parlays/agents").json()
        categories = {a["category"] for a in agents}
        # with props now present, hits and strikeouts categories should be built
        assert "hits" in categories
        assert "strikeouts" in categories
