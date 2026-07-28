"""ORM models. JSON columns hold provider payloads whose shape evolves upstream."""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    type_annotation_map = {dict[str, Any]: JSON, list[Any]: JSON}


# ── Identity & billing ────────────────────────────────────────────────────────
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str | None] = mapped_column(String(255))
    full_name: Mapped[str | None] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="user")  # user | premium | admin
    provider: Mapped[str] = mapped_column(String(20), default="local")  # local | google | github
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    subscription: Mapped["Subscription | None"] = relationship(back_populates="user", uselist=False)
    bankroll: Mapped["Bankroll | None"] = relationship(back_populates="user", uselist=False)


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    plan: Mapped[str] = mapped_column(String(20), default="free")  # free | pro | premium
    status: Mapped[str] = mapped_column(String(20), default="active")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="subscription")


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    amount: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    status: Mapped[str] = mapped_column(String(20), default="pending")
    provider_ref: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(100), index=True)
    detail: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    ip: Mapped[str | None] = mapped_column(String(45))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


# ── Baseball reference data ───────────────────────────────────────────────────
class Team(Base):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(primary_key=True)
    mlb_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    abbreviation: Mapped[str] = mapped_column(String(10))
    league: Mapped[str | None] = mapped_column(String(50))
    division: Mapped[str | None] = mapped_column(String(50))
    venue_name: Mapped[str | None] = mapped_column(String(120))
    elo: Mapped[float] = mapped_column(Float, default=1500.0)


class Player(Base):
    __tablename__ = "players"

    id: Mapped[int] = mapped_column(primary_key=True)
    mlb_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(120), index=True)
    team_mlb_id: Mapped[int | None] = mapped_column(Integer, index=True)
    position: Mapped[str | None] = mapped_column(String(10))
    bats: Mapped[str | None] = mapped_column(String(1))
    throws: Mapped[str | None] = mapped_column(String(1))
    # Profile fields (Agent 3 — Player Intelligence)
    is_pitcher: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    photo_url: Mapped[str | None] = mapped_column(String(255))
    age: Mapped[int | None] = mapped_column(Integer)
    birth_date: Mapped[str | None] = mapped_column(String(20))
    height: Mapped[str | None] = mapped_column(String(12))
    weight: Mapped[int | None] = mapped_column(Integer)
    jersey_number: Mapped[str | None] = mapped_column(String(5))
    roster_status: Mapped[str | None] = mapped_column(String(40))  # Active | Injured List | Minors…
    injury_note: Mapped[str | None] = mapped_column(Text)
    profile_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RosterChange(Base):
    """Roster/lineup movement detected by the monitoring agents (audit history)."""

    __tablename__ = "roster_changes"
    __table_args__ = (Index("ix_roster_change_detected", "detected_at", "team_mlb_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    team_mlb_id: Mapped[int | None] = mapped_column(Integer, index=True)
    player_mlb_id: Mapped[int | None] = mapped_column(Integer, index=True)
    player_name: Mapped[str | None] = mapped_column(String(120))
    change_type: Mapped[str] = mapped_column(String(40), index=True)
    # injury | activated | optioned | suspended | rest | added | removed |
    # lineup_posted | lineup_order | pitcher_change | status_change
    detail: Mapped[str] = mapped_column(Text, default="")
    previous_value: Mapped[str | None] = mapped_column(String(255))
    new_value: Mapped[str | None] = mapped_column(String(255))
    game_pk: Mapped[int | None] = mapped_column(Integer, index=True)
    severity: Mapped[str] = mapped_column(String(10), default="info")  # info | warning | critical
    detected_by: Mapped[str] = mapped_column(String(40), default="roster_intelligence")
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class PlayerNews(Base):
    """News / injury notes gathered by Agent 7 (News Intelligence)."""

    __tablename__ = "player_news"
    __table_args__ = (Index("ix_news_player_published", "player_mlb_id", "published_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    player_mlb_id: Mapped[int | None] = mapped_column(Integer, index=True)
    team_mlb_id: Mapped[int | None] = mapped_column(Integer, index=True)
    headline: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(30), default="news")  # news | injury | transaction
    source: Mapped[str] = mapped_column(String(60), default="mlb_stats_api")
    url: Mapped[str | None] = mapped_column(String(255))
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class AgentRun(Base):
    """Execution log for every agent cycle — powers the agent status board."""

    __tablename__ = "agent_runs"
    __table_args__ = (Index("ix_agent_run_agent_started", "agent", "started_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    agent: Mapped[str] = mapped_column(String(40), index=True)
    status: Mapped[str] = mapped_column(String(12), default="ok")  # ok | error | skipped
    summary: Mapped[str] = mapped_column(Text, default="")
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    items_processed: Mapped[int] = mapped_column(Integer, default=0)
    changes_detected: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[float] = mapped_column(Float, default=0.0)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class ChatMessage(Base):
    """Chat transcript between the user and the Supervisor AI."""

    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    session_key: Mapped[str] = mapped_column(String(64), index=True, default="default")
    role: Mapped[str] = mapped_column(String(12))  # user | assistant
    content: Mapped[str] = mapped_column(Text)
    intent: Mapped[str | None] = mapped_column(String(40))
    agents_consulted: Mapped[list[Any]] = mapped_column(JSON, default=list)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class PlayerStat(Base):
    """Rolling stat snapshots per scope: season, last7, last15, last30, home, away, vs_hand…"""

    __tablename__ = "player_stats"
    __table_args__ = (UniqueConstraint("player_mlb_id", "scope", "kind", name="uq_player_scope_kind"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    player_mlb_id: Mapped[int] = mapped_column(Integer, index=True)
    kind: Mapped[str] = mapped_column(String(10))  # batting | pitching
    scope: Mapped[str] = mapped_column(String(30))
    stats: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class BullpenStat(Base):
    __tablename__ = "bullpen_stats"
    __table_args__ = (UniqueConstraint("team_mlb_id", "scope", name="uq_bullpen_scope"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    team_mlb_id: Mapped[int] = mapped_column(Integer, index=True)
    scope: Mapped[str] = mapped_column(String(30), default="season")
    stats: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class ParkFactor(Base):
    __tablename__ = "park_factors"

    id: Mapped[int] = mapped_column(primary_key=True)
    venue_name: Mapped[str] = mapped_column(String(120), unique=True)
    factors: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class Umpire(Base):
    __tablename__ = "umpires"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    stats: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


# ── Games / odds ──────────────────────────────────────────────────────────────
class Game(Base):
    __tablename__ = "games"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_pk: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    game_date: Mapped[date] = mapped_column(Date, index=True)
    start_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(30), default="scheduled", index=True)
    venue_name: Mapped[str | None] = mapped_column(String(120))
    home_team_mlb_id: Mapped[int] = mapped_column(Integer, index=True)
    away_team_mlb_id: Mapped[int] = mapped_column(Integer, index=True)
    home_score: Mapped[int | None] = mapped_column(Integer)
    away_score: Mapped[int | None] = mapped_column(Integer)
    home_pitcher_mlb_id: Mapped[int | None] = mapped_column(Integer)
    away_pitcher_mlb_id: Mapped[int | None] = mapped_column(Integer)
    lineups: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    lineup_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    weather: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    umpire: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    linescore: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class OddsQuote(Base):
    __tablename__ = "odds_quotes"
    __table_args__ = (Index("ix_odds_game_market_ts", "game_pk", "market", "captured_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    game_pk: Mapped[int] = mapped_column(Integer, index=True)
    book: Mapped[str] = mapped_column(String(60))
    market: Mapped[str] = mapped_column(String(40), index=True)
    selection: Mapped[str] = mapped_column(String(120))
    line: Mapped[float | None] = mapped_column(Float)
    american: Mapped[float] = mapped_column(Float)
    implied_prob: Mapped[float] = mapped_column(Float)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


# ── Engine outputs ────────────────────────────────────────────────────────────
class Prediction(Base):
    __tablename__ = "predictions"
    __table_args__ = (Index("ix_pred_date_market", "game_date", "market"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    game_pk: Mapped[int] = mapped_column(Integer, index=True)
    game_date: Mapped[date] = mapped_column(Date, index=True)
    market: Mapped[str] = mapped_column(String(40), index=True)
    selection: Mapped[str] = mapped_column(String(160))
    player_mlb_id: Mapped[int | None] = mapped_column(Integer, index=True)
    line: Mapped[float | None] = mapped_column(Float)
    probability: Mapped[float] = mapped_column(Float)
    fair_odds: Mapped[float] = mapped_column(Float)
    book_odds: Mapped[float | None] = mapped_column(Float)
    expected_value: Mapped[float | None] = mapped_column(Float)
    edge: Mapped[float | None] = mapped_column(Float)
    kelly_stake: Mapped[float | None] = mapped_column(Float)
    clv: Mapped[float | None] = mapped_column(Float)  # closing line value vs latest market price
    confidence: Mapped[float] = mapped_column(Float)
    risk: Mapped[str] = mapped_column(String(10), default="medium")
    is_value_bet: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    explanation: Mapped[str] = mapped_column(Text, default="")
    model_breakdown: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    features: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    settled: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    outcome: Mapped[str | None] = mapped_column(String(10))  # win | loss | push | void
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Parlay(Base):
    __tablename__ = "parlays"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_date: Mapped[date] = mapped_column(Date, index=True)
    profile: Mapped[str] = mapped_column(String(20), index=True)
    legs: Mapped[list[Any]] = mapped_column(JSON, default=list)
    combined_probability: Mapped[float] = mapped_column(Float)
    combined_decimal_odds: Mapped[float] = mapped_column(Float)
    expected_value: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float)
    risk: Mapped[str] = mapped_column(String(10))
    explanation: Mapped[str] = mapped_column(Text, default="")
    settled: Mapped[bool] = mapped_column(Boolean, default=False)
    outcome: Mapped[str | None] = mapped_column(String(10))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AgentParlay(Base):
    """A parlay chosen by the daily agent debate, per category + risk style."""

    __tablename__ = "agent_parlays"
    __table_args__ = (UniqueConstraint("game_date", "category", "style", name="uq_agent_parlay"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    game_date: Mapped[date] = mapped_column(Date, index=True)
    category: Mapped[str] = mapped_column(String(20), index=True)  # hits | strikeouts | games | mixed
    style: Mapped[str] = mapped_column(String(12))  # safe | aggressive
    winning_agent: Mapped[str] = mapped_column(String(40))
    legs: Mapped[list[Any]] = mapped_column(JSON, default=list)
    combined_probability: Mapped[float] = mapped_column(Float)
    combined_decimal_odds: Mapped[float] = mapped_column(Float)
    expected_value: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float)
    risk: Mapped[str] = mapped_column(String(10))
    debate: Mapped[list[Any]] = mapped_column(JSON, default=list)  # [{agent, argument, score}]
    explanation: Mapped[str] = mapped_column(Text, default="")
    settled: Mapped[bool] = mapped_column(Boolean, default=False)
    outcome: Mapped[str | None] = mapped_column(String(10))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ModelWeight(Base):
    __tablename__ = "model_weights"
    __table_args__ = (UniqueConstraint("model_name", "market", name="uq_model_market"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    model_name: Mapped[str] = mapped_column(String(40))
    market: Mapped[str] = mapped_column(String(40))
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    brier_score: Mapped[float | None] = mapped_column(Float)
    log_loss: Mapped[float | None] = mapped_column(Float)
    samples: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class EngineMetric(Base):
    """Daily engine performance snapshot (accuracy, ROI, CLV) for the dashboard."""

    __tablename__ = "engine_metrics"
    __table_args__ = (UniqueConstraint("metric_date", "market", name="uq_metric_date_market"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    metric_date: Mapped[date] = mapped_column(Date, index=True)
    market: Mapped[str] = mapped_column(String(40), default="all")
    predictions: Mapped[int] = mapped_column(Integer, default=0)
    wins: Mapped[int] = mapped_column(Integer, default=0)
    losses: Mapped[int] = mapped_column(Integer, default=0)
    pushes: Mapped[int] = mapped_column(Integer, default=0)
    roi: Mapped[float | None] = mapped_column(Float)
    clv: Mapped[float | None] = mapped_column(Float)
    brier_score: Mapped[float | None] = mapped_column(Float)


class ApiSourceStatus(Base):
    __tablename__ = "api_source_status"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(60), unique=True)
    status: Mapped[str] = mapped_column(String(20), default="unknown")  # ok | degraded | down | disabled
    last_success: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    latency_ms: Mapped[float | None] = mapped_column(Float)


# ── Bankroll ──────────────────────────────────────────────────────────────────
class Bankroll(Base):
    __tablename__ = "bankrolls"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    balance: Mapped[float] = mapped_column(Float, default=1000.0)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    user: Mapped[User] = relationship(back_populates="bankroll")


class Bet(Base):
    __tablename__ = "bets"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    prediction_id: Mapped[int | None] = mapped_column(ForeignKey("predictions.id", ondelete="SET NULL"))
    description: Mapped[str] = mapped_column(String(255))
    stake: Mapped[float] = mapped_column(Float)
    american_odds: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(10), default="open")  # open | won | lost | push
    payout: Mapped[float | None] = mapped_column(Float)
    placed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
