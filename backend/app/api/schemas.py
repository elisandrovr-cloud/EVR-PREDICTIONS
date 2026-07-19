"""Pydantic I/O schemas for the REST API."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, EmailStr, Field


# ── auth ──────────────────────────────────────────────────────────────────────
class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class UserOut(BaseModel):
    id: int
    email: str
    full_name: str | None
    role: str
    provider: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ── games ─────────────────────────────────────────────────────────────────────
class GameOut(BaseModel):
    game_pk: int
    game_date: date
    start_time: datetime | None
    status: str
    venue_name: str | None
    home_team_mlb_id: int
    away_team_mlb_id: int
    home_team: str | None = None
    away_team: str | None = None
    home_score: int | None
    away_score: int | None
    home_pitcher_mlb_id: int | None
    away_pitcher_mlb_id: int | None
    lineups: dict[str, Any]
    lineup_confirmed: bool
    weather: dict[str, Any]
    umpire: dict[str, Any]
    linescore: dict[str, Any]

    model_config = {"from_attributes": True}


class TeamOut(BaseModel):
    mlb_id: int
    name: str
    abbreviation: str
    league: str | None
    division: str | None
    venue_name: str | None
    elo: float

    model_config = {"from_attributes": True}


# ── predictions ───────────────────────────────────────────────────────────────
class PredictionOut(BaseModel):
    id: int
    game_pk: int
    game_date: date
    market: str
    selection: str
    player_mlb_id: int | None
    line: float | None
    probability: float
    fair_odds: float
    book_odds: float | None
    expected_value: float | None
    edge: float | None
    kelly_stake: float | None
    confidence: float
    risk: str
    is_value_bet: bool
    explanation: str
    model_breakdown: dict[str, Any]
    settled: bool
    outcome: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ParlayOut(BaseModel):
    id: int
    game_date: date
    profile: str
    legs: list[Any]
    combined_probability: float
    combined_decimal_odds: float
    expected_value: float
    confidence: float
    risk: str
    explanation: str
    settled: bool
    outcome: str | None

    model_config = {"from_attributes": True}


class HitsBoardRow(BaseModel):
    player_mlb_id: int | None
    player: str
    team: str | None
    game_pk: int
    probability: float
    fair_odds: float
    book_odds: float | None
    confidence: float
    is_value_bet: bool
    explanation: str
    last5_hits: list[int] = []
    last5_total: int = 0


class DebateEntry(BaseModel):
    agent: str
    tagline: str
    argument: str
    score: float
    won: bool
    metrics: dict[str, float]


class AgentParlayOut(BaseModel):
    id: int
    game_date: date
    category: str
    style: str
    winning_agent: str
    legs: list[Any]
    combined_probability: float
    combined_decimal_odds: float
    expected_value: float
    confidence: float
    risk: str
    debate: list[DebateEntry]
    explanation: str
    settled: bool
    outcome: str | None

    model_config = {"from_attributes": True}


class OddsQuoteOut(BaseModel):
    game_pk: int
    book: str
    market: str
    selection: str
    line: float | None
    american: float
    implied_prob: float
    captured_at: datetime

    model_config = {"from_attributes": True}


# ── bankroll ──────────────────────────────────────────────────────────────────
class BankrollOut(BaseModel):
    balance: float
    currency: str
    updated_at: datetime

    model_config = {"from_attributes": True}


class BetCreate(BaseModel):
    prediction_id: int | None = None
    description: str
    stake: float = Field(gt=0)
    american_odds: float


class BetOut(BaseModel):
    id: int
    description: str
    stake: float
    american_odds: float
    status: str
    payout: float | None
    placed_at: datetime

    model_config = {"from_attributes": True}


# ── admin / metrics ───────────────────────────────────────────────────────────
class ModelWeightOut(BaseModel):
    model_name: str
    market: str
    weight: float
    brier_score: float | None
    log_loss: float | None
    samples: int
    updated_at: datetime

    model_config = {"from_attributes": True}


class SourceStatusOut(BaseModel):
    source: str
    status: str
    last_success: datetime | None
    last_error: str | None
    latency_ms: float | None

    model_config = {"from_attributes": True}


class EngineMetricOut(BaseModel):
    metric_date: date
    market: str
    predictions: int
    wins: int
    losses: int
    pushes: int
    roi: float | None
    clv: float | None
    brier_score: float | None

    model_config = {"from_attributes": True}


class AuditLogOut(BaseModel):
    id: int
    user_id: int | None
    action: str
    detail: dict[str, Any]
    ip: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
