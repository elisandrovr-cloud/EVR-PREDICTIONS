"""API integration tests: auth lifecycle, games, predictions, parlays, admin, bankroll."""
from __future__ import annotations

from datetime import date

from app.domain.entities import Market
from app.infrastructure.db.models import Game, Parlay, Prediction, Team, User


def _auth_headers(client, email="user@evr-example.com", password="secret-pass-123") -> dict[str, str]:
    resp = client.post("/api/v1/auth/register", json={"email": email, "password": password})
    assert resp.status_code == 201, resp.text
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


class TestHealth:
    def test_health(self, client) -> None:
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_openapi_available(self, client) -> None:
        assert client.get("/openapi.json").status_code == 200


class TestAuth:
    def test_register_login_refresh_me(self, client) -> None:
        reg = client.post("/api/v1/auth/register",
                          json={"email": "a@example.com", "password": "longpassword1", "full_name": "Test"})
        assert reg.status_code == 201
        tokens = reg.json()

        login = client.post("/api/v1/auth/login", json={"email": "a@example.com", "password": "longpassword1"})
        assert login.status_code == 200

        refreshed = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
        assert refreshed.status_code == 200
        assert refreshed.json()["access_token"]

        me = client.get("/api/v1/auth/me",
                        headers={"Authorization": f"Bearer {refreshed.json()['access_token']}"})
        assert me.status_code == 200
        assert me.json()["email"] == "a@example.com"

    def test_refresh_rotation_blocks_reuse(self, client) -> None:
        reg = client.post("/api/v1/auth/register", json={"email": "rot@example.com", "password": "longpassword1"})
        refresh_token = reg.json()["refresh_token"]
        assert client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token}).status_code == 200
        # second use of the same token must fail (rotation)
        assert client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token}).status_code == 401

    def test_duplicate_email_rejected(self, client) -> None:
        client.post("/api/v1/auth/register", json={"email": "dup@example.com", "password": "longpassword1"})
        resp = client.post("/api/v1/auth/register", json={"email": "dup@example.com", "password": "longpassword1"})
        assert resp.status_code == 409

    def test_wrong_password_rejected(self, client) -> None:
        client.post("/api/v1/auth/register", json={"email": "wp@example.com", "password": "longpassword1"})
        resp = client.post("/api/v1/auth/login", json={"email": "wp@example.com", "password": "wrong-password"})
        assert resp.status_code == 401

    def test_protected_route_requires_token(self, client) -> None:
        assert client.get("/api/v1/auth/me").status_code == 401


class TestGamesAndPredictions:
    def _seed(self, db) -> None:
        db.add(Team(mlb_id=147, name="New York Yankees", abbreviation="NYY", elo=1550))
        db.add(Team(mlb_id=111, name="Boston Red Sox", abbreviation="BOS", elo=1480))
        db.add(Game(game_pk=5001, game_date=date.today(), status="scheduled",
                    home_team_mlb_id=147, away_team_mlb_id=111, venue_name="Yankee Stadium"))
        db.add(Prediction(
            game_pk=5001, game_date=date.today(), market=Market.MONEYLINE.value,
            selection="New York Yankees", probability=0.62, fair_odds=-163, book_odds=-140,
            expected_value=0.06, edge=0.04, confidence=0.74, is_value_bet=True,
            explanation="test pick",
        ))
        db.commit()

    def test_today_games(self, client, db) -> None:
        self._seed(db)
        resp = client.get("/api/v1/games/today")
        assert resp.status_code == 200
        games = resp.json()
        assert len(games) == 1
        assert games[0]["home_team"] == "New York Yankees"

    def test_game_detail_and_404(self, client, db) -> None:
        self._seed(db)
        assert client.get("/api/v1/games/5001").status_code == 200
        assert client.get("/api/v1/games/99999").status_code == 404

    def test_daily_predictions(self, client, db) -> None:
        self._seed(db)
        resp = client.get("/api/v1/predictions/daily")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_top_boards(self, client, db) -> None:
        self._seed(db)
        assert client.get("/api/v1/predictions/top/moneyline").status_code == 200
        value = client.get("/api/v1/predictions/top/value-bets")
        assert value.status_code == 200
        assert len(value.json()) == 1
        assert client.get("/api/v1/predictions/top/nonsense").status_code == 404

    def test_parlay_endpoints(self, client, db) -> None:
        db.add(Parlay(game_date=date.today(), profile="conservative", legs=[],
                      combined_probability=0.4, combined_decimal_odds=2.6,
                      expected_value=0.04, confidence=0.7, risk="low", explanation="x"))
        db.commit()
        daily = client.get("/api/v1/parlays/daily")
        assert daily.status_code == 200 and len(daily.json()) == 1
        assert client.get("/api/v1/parlays/profile/conservative").status_code == 200
        assert client.get("/api/v1/parlays/profile/unknown").status_code == 404


class TestBankroll:
    def test_bet_lifecycle(self, client) -> None:
        headers = _auth_headers(client, email="bettor@evr-example.com")
        bank = client.get("/api/v1/bankroll", headers=headers)
        assert bank.status_code == 200
        start_balance = bank.json()["balance"]

        bet = client.post("/api/v1/bankroll/bets", headers=headers,
                          json={"description": "NYY ML", "stake": 100, "american_odds": -110})
        assert bet.status_code == 201
        bet_id = bet.json()["id"]

        after = client.get("/api/v1/bankroll", headers=headers).json()["balance"]
        assert after == start_balance - 100

        settled = client.post(f"/api/v1/bankroll/bets/{bet_id}/settle/won", headers=headers)
        assert settled.status_code == 200
        final = client.get("/api/v1/bankroll", headers=headers).json()["balance"]
        assert final > after

    def test_stake_cannot_exceed_bankroll(self, client) -> None:
        headers = _auth_headers(client, email="broke@evr-example.com")
        resp = client.post("/api/v1/bankroll/bets", headers=headers,
                           json={"description": "too big", "stake": 999999, "american_odds": 100})
        assert resp.status_code == 422


class TestAdmin:
    def test_admin_gate(self, client, db) -> None:
        headers = _auth_headers(client, email="pleb@evr-example.com")
        assert client.get("/api/v1/admin/users", headers=headers).status_code == 403
        user = db.query(User).filter_by(email="pleb@evr-example.com").one()
        user.role = "admin"
        db.commit()
        assert client.get("/api/v1/admin/users", headers=headers).status_code == 200
        assert client.get("/api/v1/admin/overview", headers=headers).status_code == 200
