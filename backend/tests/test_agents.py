"""Agent debate + hits board."""
from __future__ import annotations

from datetime import date

from sqlalchemy import select

from app.application.agents import AGENTS, build_agent_parlays
from app.infrastructure.db.models import AgentParlay, Player, PlayerStat, Prediction


def _pred(**kw) -> Prediction:
    base = dict(
        game_date=date.today(), fair_odds=-120, book_odds=-110, confidence=0.7,
        risk="medium", settled=False, explanation="x",
    )
    base.update(kw)
    return Prediction(**base)


def _seed_pool(db) -> None:
    # two games, batter hits + pitcher strikeouts + game markets
    rows = [
        _pred(game_pk=1, market="player_hits", selection="Judge 1+ hit", player_mlb_id=101, line=0.5, probability=0.74),
        _pred(game_pk=1, market="player_hits", selection="Soto 1+ hit", player_mlb_id=102, line=0.5, probability=0.70),
        _pred(game_pk=2, market="player_hits", selection="Betts 1+ hit", player_mlb_id=103, line=0.5, probability=0.68),
        _pred(game_pk=2, market="player_hits", selection="Freeman 1+ hit", player_mlb_id=104, line=0.5, probability=0.66),
        _pred(game_pk=1, market="pitcher_strikeouts", selection="Cole over 5.5 K", player_mlb_id=201, line=5.5, probability=0.63),
        _pred(game_pk=2, market="pitcher_strikeouts", selection="Snell over 6.5 K", player_mlb_id=202, line=6.5, probability=0.60),
        _pred(game_pk=1, market="moneyline", selection="Yankees", probability=0.64),
        _pred(game_pk=2, market="moneyline", selection="Dodgers", probability=0.61),
        _pred(game_pk=1, market="total_over", selection="Over 8.5", line=8.5, probability=0.55),
    ]
    for r in rows:
        db.add(r)
    db.commit()


class TestAgentDebate:
    def test_builds_parlays_across_categories(self, db) -> None:
        _seed_pool(db)
        created = build_agent_parlays(db, date.today())
        assert created > 0
        rows = db.scalars(select(AgentParlay)).all()
        categories = {r.category for r in rows}
        # hits, strikeouts, games and mixed should all be represented (safe pool is rich)
        assert "hits" in categories
        assert "games" in categories
        assert "mixed" in categories

    def test_winner_and_debate_recorded(self, db) -> None:
        _seed_pool(db)
        build_agent_parlays(db, date.today())
        hits_safe = db.scalar(
            select(AgentParlay).where(
                AgentParlay.category == "hits", AgentParlay.style == "safe"
            )
        )
        assert hits_safe is not None
        assert hits_safe.winning_agent in {a.name for a in AGENTS}
        assert len(hits_safe.legs) >= 2
        assert 0 < hits_safe.combined_probability <= 1
        assert hits_safe.combined_decimal_odds > 1
        # debate transcript has one entry per proposing agent, exactly one winner
        assert len(hits_safe.debate) >= 2
        assert sum(1 for d in hits_safe.debate if d["won"]) == 1
        # every leg in a hits parlay is a hit market
        assert all(leg["market"] == "player_hits" for leg in hits_safe.legs)

    def test_aggressive_has_more_legs_than_safe(self, db) -> None:
        _seed_pool(db)
        build_agent_parlays(db, date.today())
        safe = db.scalar(select(AgentParlay).where(AgentParlay.category == "mixed", AgentParlay.style == "safe"))
        aggr = db.scalar(select(AgentParlay).where(AgentParlay.category == "mixed", AgentParlay.style == "aggressive"))
        assert safe and aggr
        assert len(aggr.legs) >= len(safe.legs)

    def test_idempotent(self, db) -> None:
        _seed_pool(db)
        build_agent_parlays(db, date.today())
        n1 = len(db.scalars(select(AgentParlay)).all())
        build_agent_parlays(db, date.today())
        n2 = len(db.scalars(select(AgentParlay)).all())
        assert n1 == n2


class TestHitsBoard:
    def test_hits_board_ranked_with_recent_form(self, client, db) -> None:
        _seed_pool(db)
        db.add(Player(mlb_id=101, full_name="Aaron Judge", team_mlb_id=147, position="RF"))
        db.add(PlayerStat(player_mlb_id=101, kind="batting", scope="season",
                          stats={"last5_hits": [2, 1, 0, 3, 1], "last5_total_hits": 7}))
        db.commit()

        resp = client.get("/api/v1/predictions/hits-board")
        assert resp.status_code == 200
        board = resp.json()
        assert len(board) >= 4
        # sorted by probability descending
        probs = [row["probability"] for row in board]
        assert probs == sorted(probs, reverse=True)
        judge = next(r for r in board if r["player_mlb_id"] == 101)
        assert judge["player"] == "Aaron Judge"
        assert judge["last5_hits"] == [2, 1, 0, 3, 1]
        assert judge["last5_total"] == 7
