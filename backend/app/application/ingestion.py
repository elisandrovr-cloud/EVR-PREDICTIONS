"""Data ingestion use-cases: schedule, teams, stats, odds, weather.

Change detection publishes domain events (lineup confirmed / pitcher changed)
that trigger immediate recomputation instead of waiting for the next tick.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.domain.entities import Odds
from app.domain.events import GameFinal, LineupConfirmed, PitcherChanged
from app.infrastructure.db.models import (
    ApiSourceStatus,
    BullpenStat,
    Game,
    OddsQuote,
    Player,
    PlayerStat,
    Team,
)
from app.infrastructure.providers.registry import ProviderRegistry, get_registry

logger = get_logger(__name__)


def _iso_to_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def sync_teams(db: Session, registry: ProviderRegistry | None = None) -> int:
    reg = registry or get_registry()
    count = 0
    for t in reg.mlb.teams():
        row = db.scalar(select(Team).where(Team.mlb_id == t["id"]))
        if row is None:
            row = Team(mlb_id=t["id"], name=t.get("name", ""), abbreviation=t.get("abbreviation", ""))
            db.add(row)
        row.name = t.get("name", row.name)
        row.abbreviation = t.get("abbreviation", row.abbreviation)
        row.league = (t.get("league") or {}).get("name")
        row.division = (t.get("division") or {}).get("name")
        row.venue_name = (t.get("venue") or {}).get("name")
        count += 1
    db.commit()
    return count


def _extract_lineups(g: dict[str, Any]) -> dict[str, Any]:
    lineups = g.get("lineups") or {}
    out: dict[str, list[dict[str, Any]]] = {"home": [], "away": []}
    for side in ("home", "away"):
        for player in lineups.get(f"{side}Players", []) or []:
            out[side].append({
                "id": player.get("id"),
                "name": player.get("fullName"),
                "position": (player.get("primaryPosition") or {}).get("abbreviation"),
            })
    return out


def sync_schedule(db: Session, day: date, registry: ProviderRegistry | None = None) -> dict[str, int]:
    """Upsert today's games; emit events on lineup/pitcher changes and finals."""
    reg = registry or get_registry()
    stats = {"games": 0, "lineups_confirmed": 0, "pitcher_changes": 0, "finals": 0}
    for g in reg.mlb.schedule(day):
        game_pk = g["gamePk"]
        row = db.scalar(select(Game).where(Game.game_pk == game_pk))
        teams = g.get("teams", {})
        home, away = teams.get("home", {}), teams.get("away", {})
        status = (g.get("status") or {}).get("abstractGameState", "Preview").lower()
        status_map = {"preview": "scheduled", "live": "live", "final": "final"}
        new_status = status_map.get(status, status)
        home_p = (home.get("probablePitcher") or {}).get("id")
        away_p = (away.get("probablePitcher") or {}).get("id")
        lineups = _extract_lineups(g)
        lineup_confirmed = bool(lineups["home"]) and bool(lineups["away"])

        if row is None:
            row = Game(
                game_pk=game_pk, game_date=day,
                home_team_mlb_id=(home.get("team") or {}).get("id", 0),
                away_team_mlb_id=(away.get("team") or {}).get("id", 0),
            )
            db.add(row)
        else:
            if home_p and row.home_pitcher_mlb_id and home_p != row.home_pitcher_mlb_id:
                PitcherChanged(game_pk=game_pk, team_side="home", new_pitcher_id=home_p).publish()
                stats["pitcher_changes"] += 1
            if away_p and row.away_pitcher_mlb_id and away_p != row.away_pitcher_mlb_id:
                PitcherChanged(game_pk=game_pk, team_side="away", new_pitcher_id=away_p).publish()
                stats["pitcher_changes"] += 1
            if lineup_confirmed and not row.lineup_confirmed:
                LineupConfirmed(game_pk=game_pk).publish()
                stats["lineups_confirmed"] += 1
            if new_status == "final" and row.status != "final":
                GameFinal(game_pk=game_pk).publish()
                stats["finals"] += 1

        row.game_date = day
        row.start_time = _iso_to_dt(g.get("gameDate"))
        row.status = new_status
        row.venue_name = (g.get("venue") or {}).get("name")
        row.home_score = home.get("score")
        row.away_score = away.get("score")
        row.home_pitcher_mlb_id = home_p or row.home_pitcher_mlb_id
        row.away_pitcher_mlb_id = away_p or row.away_pitcher_mlb_id
        row.lineups = lineups
        row.lineup_confirmed = lineup_confirmed or row.lineup_confirmed
        linescore = g.get("linescore") or {}
        if linescore:
            row.linescore = {**(row.linescore or {}), "innings": linescore.get("innings", [])}
        officials = g.get("officials") or []
        for off in officials:
            if (off.get("officialType") == "Home Plate") and off.get("official"):
                row.umpire = {"name": off["official"].get("fullName")}

        # Upsert only the two probable pitchers per game here (cheap). Batter
        # identities are upserted during the progressive backfill, alongside their
        # stats, to keep this schedule sync fast enough for a serverless timeout.
        for team_key in (home, away):
            pp = team_key.get("probablePitcher") or {}
            _upsert_player(db, pp.get("id"), pp.get("fullName"), (team_key.get("team") or {}).get("id"), "P")
        stats["games"] += 1
    db.commit()
    return stats


def _upsert_player(db: Session, mlb_id: int | None, name: str | None,
                   team_mlb_id: int | None, position: str | None) -> None:
    if not mlb_id or not name:
        return
    row = db.scalar(select(Player).where(Player.mlb_id == mlb_id))
    if row is None:
        row = Player(mlb_id=mlb_id, full_name=name)
        db.add(row)
    row.full_name = name
    if team_mlb_id:
        row.team_mlb_id = team_mlb_id
    if position:
        row.position = position


def sync_weather(db: Session, day: date, registry: ProviderRegistry | None = None) -> int:
    reg = registry or get_registry()
    games = db.scalars(select(Game).where(Game.game_date == day)).all()
    updated = 0
    for game in games:
        if not game.venue_name or game.status == "final":
            continue
        conditions = reg.weather.conditions_for_venue(game.venue_name)
        if conditions:
            game.weather = conditions
            updated += 1
    db.commit()
    return updated


# ── stat helpers ──────────────────────────────────────────────────────────────
def _per_pa(splits: dict[str, Any], key: str) -> float | None:
    pa = float(splits.get("plateAppearances") or 0)
    if pa <= 0:
        return None
    return float(splits.get(key) or 0) / pa


def _upsert_stat(db: Session, player_id: int, kind: str, scope: str, stats: dict[str, Any]) -> None:
    row = db.scalar(
        select(PlayerStat).where(
            PlayerStat.player_mlb_id == player_id, PlayerStat.kind == kind, PlayerStat.scope == scope
        )
    )
    if row is None:
        row = PlayerStat(player_mlb_id=player_id, kind=kind, scope=scope, stats=stats)
        db.add(row)
    else:
        row.stats = {**row.stats, **stats}


def sync_pitcher_stats(db: Session, pitcher_id: int, registry: ProviderRegistry | None = None) -> None:
    reg = registry or get_registry()
    data = reg.mlb.player_stats(pitcher_id, group="pitching")
    for block in data.get("stats", []):
        for split in block.get("splits", []):
            s = split.get("stat", {})
            ip = _innings_to_float(s.get("inningsPitched"))
            bf = float(s.get("battersFaced") or 0)
            starts = float(s.get("gamesStarted") or 0) or 1.0
            stats = {
                "era": _num(s.get("era")), "whip": _num(s.get("whip")),
                "fip": _fip(s), "k_per_9": _num(s.get("strikeoutsPer9Inn")),
                "bb_per_9": _num(s.get("walksPer9Inn")), "hits_per_9": _num(s.get("hitsPer9Inn")),
                "hr_per_9": _num(s.get("homeRunsPer9")),
                "k_pct": (float(s.get("strikeOuts") or 0) / bf) if bf else None,
                "bb_pct": (float(s.get("baseOnBalls") or 0) / bf) if bf else None,
                "hits_allowed_per_pa": (float(s.get("hits") or 0) / bf) if bf else None,
                "hr_allowed_per_pa": (float(s.get("homeRuns") or 0) / bf) if bf else None,
                "innings_per_start": (ip / starts) if ip else None,
                "avg_pitch_count": _num(s.get("numberOfPitches")) / starts if s.get("numberOfPitches") else None,
                "innings_pitched": ip,
            }
            _upsert_stat(db, pitcher_id, "pitching", "season", {k: v for k, v in stats.items() if v is not None})
    db.commit()


def sync_batter_stats(db: Session, batter_id: int, registry: ProviderRegistry | None = None) -> None:
    reg = registry or get_registry()
    data = reg.mlb.player_stats(batter_id, group="hitting")
    for block in data.get("stats", []):
        for split in block.get("splits", []):
            s = split.get("stat", {})
            games = float(s.get("gamesPlayed") or 0) or 1.0
            stats = {
                "avg": _num(s.get("avg")), "obp": _num(s.get("obp")), "slg": _num(s.get("slg")),
                "ops": _num(s.get("ops")), "babip": _num(s.get("babip")),
                "iso": (_num(s.get("slg")) - _num(s.get("avg"))) if s.get("slg") and s.get("avg") else None,
                "pa": float(s.get("plateAppearances") or 0),
                "hit_per_pa": _per_pa(s, "hits"), "hr_per_pa": _per_pa(s, "homeRuns"),
                "bb_per_pa": _per_pa(s, "baseOnBalls"), "k_per_pa": _per_pa(s, "strikeOuts"),
                "rbi_per_pa": _per_pa(s, "rbi"), "run_per_pa": _per_pa(s, "runs"),
                "double_per_pa": _per_pa(s, "doubles"), "triple_per_pa": _per_pa(s, "triples"),
                "sb_per_game": float(s.get("stolenBases") or 0) / games,
            }
            _upsert_stat(db, batter_id, "batting", "season", {k: v for k, v in stats.items() if v is not None})
    db.commit()


def sync_batter_recent_form(db: Session, batter_id: int, registry: ProviderRegistry | None = None) -> None:
    """Store the batter's hit count for their last 5 games (newest first) so the
    Hits board can show recent form alongside the model probability."""
    reg = registry or get_registry()
    splits = reg.mlb.player_game_log(batter_id, group="hitting")
    games = []
    for split in splits:
        s = split.get("stat", {})
        games.append({
            "date": split.get("date"),
            "hits": int(s.get("hits") or 0),
            "ab": int(s.get("atBats") or 0),
            "opponent": (split.get("opponent") or {}).get("name"),
        })
    games = list(reversed(games))[:5]  # game logs come oldest-first; keep newest 5
    last5 = list(reversed(games))
    _upsert_stat(db, batter_id, "batting", "season", {
        "last5_hits": [g["hits"] for g in last5],
        "last5_games": last5,
        "last5_total_hits": sum(g["hits"] for g in last5),
    })
    db.commit()


def sync_team_offense(db: Session, team_id: int, registry: ProviderRegistry | None = None) -> None:
    reg = registry or get_registry()
    data = reg.mlb.team_stats(team_id, group="hitting")
    for block in data.get("stats", []):
        for split in block.get("splits", []):
            s = split.get("stat", {})
            games = float(s.get("gamesPlayed") or 0) or 1.0
            bf = float(s.get("plateAppearances") or 0)
            stats = {
                "ops": _num(s.get("ops")), "avg": _num(s.get("avg")),
                "runs_per_game": float(s.get("runs") or 0) / games,
                "k_pct": (float(s.get("strikeOuts") or 0) / bf) if bf else None,
            }
            _upsert_stat(db, team_id, "team", "offense", {k: v for k, v in stats.items() if v is not None})
    db.commit()


def sync_bullpen(db: Session, team_id: int, registry: ProviderRegistry | None = None) -> None:
    reg = registry or get_registry()
    data = reg.mlb.team_stats(team_id, group="pitching")
    for block in data.get("stats", []):
        for split in block.get("splits", []):
            s = split.get("stat", {})
            row = db.scalar(
                select(BullpenStat).where(BullpenStat.team_mlb_id == team_id, BullpenStat.scope == "season")
            )
            stats = {
                "era": _num(s.get("era")), "whip": _num(s.get("whip")),
                "k_pct": None, "fatigue": (row.stats.get("fatigue", 0.0) if row else 0.0),
            }
            if row is None:
                row = BullpenStat(team_mlb_id=team_id, scope="season", stats={})
                db.add(row)
            row.stats = {**row.stats, **{k: v for k, v in stats.items() if v is not None}}
    db.commit()


def sync_odds(db: Session, day: date, registry: ProviderRegistry | None = None) -> int:
    """Capture current book lines; store every snapshot for line-movement charts."""
    reg = registry or get_registry()
    if not reg.odds.enabled:
        return 0
    games = {g.game_pk: g for g in db.scalars(select(Game).where(Game.game_date == day)).all()}
    team_names = {t.name: t.mlb_id for t in db.scalars(select(Team)).all()}
    inserted = 0
    for event in reg.odds.game_odds():
        game_pk = _match_event_to_game(event, games, team_names)
        if game_pk is None:
            continue
        for book in event.get("bookmakers", []):
            for market in book.get("markets", []):
                market_key = {"h2h": "moneyline", "spreads": "run_line", "totals": "total"}.get(market["key"])
                if not market_key:
                    continue
                for outcome in market.get("outcomes", []):
                    price = float(outcome.get("price", 0))
                    if not price:
                        continue
                    db.add(OddsQuote(
                        game_pk=game_pk, book=book.get("title", book.get("key", "")),
                        market=market_key, selection=str(outcome.get("name", "")),
                        line=outcome.get("point"), american=price,
                        implied_prob=round(Odds(american=price).implied_probability, 4),
                    ))
                    inserted += 1
    db.commit()
    return inserted


def _match_event_to_game(event: dict[str, Any], games: dict[int, Game], team_names: dict[str, int]) -> int | None:
    home_id = team_names.get(event.get("home_team", ""))
    away_id = team_names.get(event.get("away_team", ""))
    for pk, g in games.items():
        if g.home_team_mlb_id == home_id and g.away_team_mlb_id == away_id:
            return pk
    return None


def record_source_statuses(db: Session, registry: ProviderRegistry | None = None) -> None:
    reg = registry or get_registry()
    for status in reg.statuses():
        row = db.scalar(select(ApiSourceStatus).where(ApiSourceStatus.source == status["source"]))
        if row is None:
            row = ApiSourceStatus(source=status["source"])
            db.add(row)
        row.status = status["status"]
        row.last_success = status["last_success"]
        row.last_error = status["last_error"]
        row.latency_ms = status["latency_ms"]
    db.commit()


# ── numeric parsing helpers ───────────────────────────────────────────────────
def _num(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _innings_to_float(ip: Any) -> float:
    """MLB '123.2' innings notation → 123.667."""
    if ip in (None, ""):
        return 0.0
    text = str(ip)
    if "." in text:
        whole, frac = text.split(".")
        return float(whole) + float(frac) / 3.0
    return float(text)


def _fip(s: dict[str, Any]) -> float | None:
    ip = _innings_to_float(s.get("inningsPitched"))
    if ip <= 0:
        return None
    hr = _num(s.get("homeRuns"))
    bb = _num(s.get("baseOnBalls"))
    hbp = _num(s.get("hitByPitch"))
    k = _num(s.get("strikeOuts"))
    return round((13 * hr + 3 * (bb + hbp) - 2 * k) / ip + 3.15, 2)
