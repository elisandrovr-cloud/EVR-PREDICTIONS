"""Multi-agent system: monitoring cycle, change detection, chat routing."""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import select

from app.agents import SUPERVISOR
from app.agents.base import ChatQuery
from app.domain.entities import Market
from app.infrastructure.db.models import (
    AgentRun,
    Game,
    Player,
    PlayerNews,
    PlayerStat,
    Prediction,
    RosterChange,
    Team,
)


# ── fake official data sources ────────────────────────────────────────────────
class FakeMlb:
    """Mimics the MLB Stats API surface the agents touch."""

    def __init__(self) -> None:
        self.roster_status = "Active"
        self.lineup_posted = False
        self.starter_id = 900

    def teams(self):
        return [
            {"id": 147, "name": "New York Yankees", "abbreviation": "NYY",
             "league": {"name": "AL"}, "division": {"name": "AL East"}, "venue": {"name": "Yankee Stadium"}},
            {"id": 111, "name": "Boston Red Sox", "abbreviation": "BOS",
             "league": {"name": "AL"}, "division": {"name": "AL East"}, "venue": {"name": "Fenway Park"}},
        ]

    def schedule(self, day):
        lineups = {}
        if self.lineup_posted:
            lineups = {
                "homePlayers": [
                    {"id": 101, "fullName": "Aaron Judge", "primaryPosition": {"abbreviation": "RF"}},
                    {"id": 102, "fullName": "Juan Soto", "primaryPosition": {"abbreviation": "LF"}},
                    {"id": 103, "fullName": "Anthony Volpe", "primaryPosition": {"abbreviation": "SS"}},
                ],
                "awayPlayers": [
                    {"id": 201, "fullName": "Rafael Devers", "primaryPosition": {"abbreviation": "3B"}},
                    {"id": 202, "fullName": "Trevor Story", "primaryPosition": {"abbreviation": "SS"}},
                ],
            }
        return [{
            "gamePk": 660001,
            "gameDate": datetime.now(timezone.utc).isoformat(),
            "status": {"abstractGameState": "Preview"},
            "teams": {
                "home": {"team": {"id": 147},
                         "probablePitcher": {"id": self.starter_id, "fullName": "Gerrit Cole"}, "score": None},
                "away": {"team": {"id": 111},
                         "probablePitcher": {"id": 901, "fullName": "Brayan Bello"}, "score": None},
            },
            "venue": {"name": "Yankee Stadium"},
            "lineups": lineups, "linescore": {}, "officials": [],
        }]

    def roster(self, team_id, roster_type="active"):
        base = 100 if team_id == 147 else 200
        return [
            {"person": {"id": base + 1, "fullName": f"Bateador {base + 1}"},
             "position": {"abbreviation": "RF", "type": "Outfielder"},
             "status": {"description": self.roster_status}, "jerseyNumber": "99"},
            {"person": {"id": base + 2, "fullName": f"Bateador {base + 2}"},
             "position": {"abbreviation": "SS", "type": "Infielder"},
             "status": {"description": "Active"}},
            {"person": {"id": 900 if team_id == 147 else 901, "fullName": "Lanzador"},
             "position": {"abbreviation": "P", "type": "Pitcher"},
             "status": {"description": "Active"}},
        ]

    def transactions(self, start, end):
        return [{
            "person": {"id": 101, "fullName": "Aaron Judge"},
            "typeDesc": "Placed on Injured List",
            "description": "Aaron Judge placed on the 10-day injured list.",
            "toTeam": {"id": 147},
        }]

    def people(self, ids):
        return [{
            "id": pid, "fullName": f"Jugador {pid}",
            "primaryPosition": {"abbreviation": "P" if pid >= 900 else "RF",
                                "type": "Pitcher" if pid >= 900 else "Outfielder"},
            "batSide": {"code": "R"}, "pitchHand": {"code": "R"},
            "currentAge": 28, "birthDate": "1997-05-05", "height": "6' 3\"", "weight": 210,
            "primaryNumber": "9", "currentTeam": {"id": 147},
        } for pid in ids]

    def player_stats(self, player_id, group, stat_type="season"):
        if group == "pitching":
            stat = {"era": "3.10", "whip": "1.05", "strikeoutsPer9Inn": "11.0", "walksPer9Inn": "2.2",
                    "hitsPer9Inn": "6.9", "homeRunsPer9": "1.0", "strikeOuts": 120, "baseOnBalls": 24,
                    "battersFaced": 400, "hits": 70, "homeRuns": 12, "inningsPitched": "100.0",
                    "gamesStarted": 17, "numberOfPitches": 1600, "hitByPitch": 4}
        else:
            stat = {"avg": ".285", "obp": ".370", "slg": ".520", "ops": ".890",
                    "plateAppearances": 400, "hits": 110, "homeRuns": 22, "baseOnBalls": 45,
                    "strikeOuts": 90, "rbi": 60, "runs": 65, "doubles": 24, "triples": 2,
                    "stolenBases": 8, "gamesPlayed": 95}
        return {"stats": [{"splits": [{"stat": stat}]}]}

    def player_game_log(self, player_id, group):
        return [{"date": "2026-07-18", "stat": {"hits": 2, "atBats": 4}, "opponent": {"name": "BOS"}}]

    def team_stats(self, team_id, group):
        stat = ({"ops": ".740", "avg": ".252", "runs": 420, "plateAppearances": 3600,
                 "strikeOuts": 800, "gamesPlayed": 95} if group == "hitting"
                else {"era": "3.90", "whip": "1.25"})
        return {"stats": [{"splits": [{"stat": stat}]}]}

    @staticmethod
    def headshot_url(player_id):
        return f"https://midfield.mlbstatic.com/v1/people/{player_id}/spots/120"


class FakeWeather:
    def conditions_for_venue(self, venue):
        return {}


class FakeRegistry:
    def __init__(self) -> None:
        self.mlb = FakeMlb()
        self.weather = FakeWeather()

    def statuses(self):
        return []


# ── monitoring cycle ──────────────────────────────────────────────────────────
class TestMonitoringCycle:
    def test_full_cycle_runs_every_agent(self, db) -> None:
        reg = FakeRegistry()
        result = SUPERVISOR.run_cycle(db, registry=reg, day=date.today())
        assert len(result.reports) == 8
        assert {r.agent for r in result.reports} == {a.name for a in SUPERVISOR.agents}
        # a failing agent would be status=error; all should be ok against fakes
        assert [r.agent for r in result.reports if r.status == "error"] == []
        assert result.conclusion.startswith("Ciclo completo")

    def test_cycle_is_logged_per_agent(self, db) -> None:
        SUPERVISOR.run_cycle(db, registry=FakeRegistry(), day=date.today())
        runs = db.scalars(select(AgentRun)).all()
        assert len(runs) == 8
        assert all(r.duration_ms >= 0 for r in runs)

    def test_only_filter_runs_a_subset(self, db) -> None:
        result = SUPERVISOR.run_cycle(
            db, registry=FakeRegistry(), day=date.today(), only=["news_intelligence"]
        )
        assert [r.agent for r in result.reports] == ["news_intelligence"]

    def test_status_board_reports_last_run(self, db) -> None:
        SUPERVISOR.run_cycle(db, registry=FakeRegistry(), day=date.today())
        board = SUPERVISOR.status(db)
        assert len(board) == 8
        assert all(entry["last_run"] for entry in board)


# ── change detection ──────────────────────────────────────────────────────────
class TestRosterIntelligence:
    def test_detects_injury_from_transactions(self, db) -> None:
        SUPERVISOR.roster.execute(db, FakeRegistry(), date.today())
        injuries = db.scalars(
            select(RosterChange).where(RosterChange.change_type == "injury")
        ).all()
        assert injuries, "the injured-list transaction should be recorded"
        assert injuries[0].severity == "critical"
        assert "injured list" in injuries[0].detail.lower()

    def test_detects_roster_status_change(self, db) -> None:
        reg = FakeRegistry()
        SUPERVISOR.roster.execute(db, reg, date.today())          # baseline
        reg.mlb.roster_status = "Injured List (10-day)"           # status flips
        SUPERVISOR.roster.execute(db, reg, date.today())
        changes = db.scalars(
            select(RosterChange).where(RosterChange.change_type == "injury")
        ).all()
        assert any("Active" in (c.previous_value or "") for c in changes)

    def test_no_duplicate_transaction_rows(self, db) -> None:
        reg = FakeRegistry()
        SUPERVISOR.roster.execute(db, reg, date.today())
        first = len(db.scalars(select(RosterChange)).all())
        SUPERVISOR.roster.execute(db, reg, date.today())
        second = len(db.scalars(select(RosterChange)).all())
        assert second == first, "the same transaction must not be recorded twice"


class TestLineupIntelligence:
    def test_detects_official_lineup_and_pitcher_change(self, db) -> None:
        reg = FakeRegistry()
        SUPERVISOR.lineup.execute(db, reg, date.today())  # creates the game, no lineup yet

        reg.mlb.lineup_posted = True
        reg.mlb.starter_id = 999  # starter swapped
        SUPERVISOR.lineup.execute(db, reg, date.today())

        posted = db.scalars(
            select(RosterChange).where(RosterChange.change_type == "lineup_posted")
        ).all()
        swapped = db.scalars(
            select(RosterChange).where(RosterChange.change_type == "pitcher_change")
        ).all()
        assert posted, "publishing the official lineup should be recorded"
        assert swapped and swapped[0].severity == "critical"


class TestPlayerIntelligence:
    def test_builds_profiles_with_photo_and_bio(self, db) -> None:
        reg = FakeRegistry()
        SUPERVISOR.lineup.execute(db, reg, date.today())
        reg.mlb.lineup_posted = True
        SUPERVISOR.lineup.execute(db, reg, date.today())
        SUPERVISOR.player.execute(db, reg, date.today())

        players = db.scalars(select(Player).where(Player.photo_url.isnot(None))).all()
        assert players, "profiles should carry the official headshot"
        assert all(p.age for p in players)
        assert any(p.is_pitcher for p in players)


class TestNewsIntelligence:
    def test_publishes_news_from_changes(self, db) -> None:
        reg = FakeRegistry()
        SUPERVISOR.roster.execute(db, reg, date.today())
        SUPERVISOR.news.execute(db, reg, date.today())
        news = db.scalars(select(PlayerNews)).all()
        assert news
        assert any(n.category == "injury" for n in news)

    def test_news_is_not_duplicated(self, db) -> None:
        reg = FakeRegistry()
        SUPERVISOR.roster.execute(db, reg, date.today())
        SUPERVISOR.news.execute(db, reg, date.today())
        first = len(db.scalars(select(PlayerNews)).all())
        SUPERVISOR.news.execute(db, reg, date.today())
        assert len(db.scalars(select(PlayerNews)).all()) == first


# ── chat routing ──────────────────────────────────────────────────────────────
def _seed_predictions(db) -> None:
    db.add(Team(mlb_id=147, name="New York Yankees", abbreviation="NYY"))
    db.add(Player(mlb_id=101, full_name="Aaron Judge", team_mlb_id=147, is_pitcher=False))
    db.add(Player(mlb_id=900, full_name="Gerrit Cole", team_mlb_id=147, is_pitcher=True))
    db.add(PlayerStat(player_mlb_id=101, kind="batting", scope="season",
                      stats={"avg": 0.285, "ops": 0.89, "last5_hits": [2, 1, 0, 3, 1],
                             "last5_total_hits": 7}))
    db.add(PlayerStat(player_mlb_id=900, kind="pitching", scope="season",
                      stats={"era": 3.1, "k_per_9": 11.0}))
    common = dict(game_pk=660001, game_date=date.today(), fair_odds=-140,
                  confidence=0.72, risk="low", explanation="respaldo estadístico")
    db.add(Prediction(market=Market.PLAYER_HITS.value, selection="Aaron Judge 1+ hit",
                      player_mlb_id=101, line=0.5, probability=0.71, **common))
    db.add(Prediction(market=Market.PITCHER_STRIKEOUTS.value, selection="Gerrit Cole over 5.5 K",
                      player_mlb_id=900, line=5.5, probability=0.66, **common))
    db.add(Prediction(market=Market.MONEYLINE.value, selection="New York Yankees",
                      probability=0.63, book_odds=-120, expected_value=0.08, edge=0.08,
                      is_value_bet=True, **common))
    db.commit()


class TestChatRouting:
    def test_parses_intents(self, db) -> None:
        assert SUPERVISOR.parse(db, "dame los mejores hits").intent == "hits"
        assert SUPERVISOR.parse(db, "quiero un parlay de 10 picks").intent == "parlay"
        assert SUPERVISOR.parse(db, "dame los mejores ponches").intent == "strikeouts"
        assert SUPERVISOR.parse(db, "mejores moneyline de hoy").intent == "moneyline"
        assert SUPERVISOR.parse(db, "qué jugador tiene más valor hoy").intent == "value"
        assert SUPERVISOR.parse(db, "hay noticias de lesiones?").intent == "news"

    def test_extracts_leg_count(self, db) -> None:
        assert SUPERVISOR.parse(db, "dame un parlay de 10 picks").count == 10

    def test_hits_question_consults_batter_agent(self, db) -> None:
        _seed_predictions(db)
        answer = SUPERVISOR.answer(db, "dame los mejores hits")
        assert answer.intent == "hits"
        assert "batter_intelligence" in answer.agents_consulted
        assert answer.picks, "should return concrete selections"
        assert "Aaron Judge" in answer.answer

    def test_strikeouts_question_consults_pitcher_agent(self, db) -> None:
        _seed_predictions(db)
        answer = SUPERVISOR.answer(db, "dame los mejores strikeouts")
        assert "pitcher_intelligence" in answer.agents_consulted
        assert any("Cole" in p["selection"] for p in answer.picks)

    def test_parlay_question_builds_legs(self, db) -> None:
        _seed_predictions(db)
        answer = SUPERVISOR.answer(db, "dame un parlay de 3 picks")
        assert answer.intent == "parlay"
        assert "prediction_ai" in answer.agents_consulted
        assert len(answer.picks) >= 2

    def test_answer_always_justifies_and_warns(self, db) -> None:
        _seed_predictions(db)
        answer = SUPERVISOR.answer(db, "dame los mejores hits")
        assert "Conclusión del Supervisor" in answer.answer
        assert "estimaciones estadísticas" in answer.as_dict()["disclaimer"]
        assert answer.confidence > 0

    def test_player_question_routes_to_player_agent(self, db) -> None:
        _seed_predictions(db)
        answer = SUPERVISOR.answer(db, "cómo está Aaron Judge?")
        assert answer.intent == "player"
        assert "player_intelligence" in answer.agents_consulted

    def test_empty_database_answers_honestly_without_inventing_picks(self, db) -> None:
        answer = SUPERVISOR.answer(db, "dame los mejores hits")
        assert answer.picks == [], "must not fabricate selections when there is no data"
        assert "aún no hay líneas" in answer.answer.lower()
        assert answer.confidence < 0.5


class TestValueAgent:
    def test_betting_agent_reports_edge(self, db) -> None:
        _seed_predictions(db)
        insight = SUPERVISOR.betting.insight(db, ChatQuery(raw="valor", intent="value", day=date.today()))
        assert insight is not None
        assert insight.picks
        assert "EV" in insight.bullets[0]
