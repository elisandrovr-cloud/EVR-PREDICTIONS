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


# ── multi-agent platform ──────────────────────────────────────────────────────
class AgentStatusOut(BaseModel):
    name: str
    title: str
    description: str
    status: str
    summary: str
    items_processed: int
    changes_detected: int
    duration_ms: float | None
    last_run: str | None


class CycleOut(BaseModel):
    started_at: str
    duration_ms: float
    changes_detected: int
    conclusion: str
    agents: list[Any]


class ChangeOut(BaseModel):
    id: int
    team_mlb_id: int | None
    player_mlb_id: int | None
    player_name: str | None
    change_type: str
    detail: str
    previous_value: str | None
    new_value: str | None
    game_pk: int | None
    severity: str
    detected_by: str
    detected_at: datetime

    model_config = {"from_attributes": True}


class NewsOut(BaseModel):
    id: int
    player_mlb_id: int | None
    team_mlb_id: int | None
    headline: str
    body: str
    category: str
    source: str
    url: str | None
    published_at: datetime

    model_config = {"from_attributes": True}


class ChatRequest(BaseModel):
    question: str = Field(min_length=2, max_length=500)
    session_key: str = "default"


class ChatResponse(BaseModel):
    question: str
    intent: str
    answer: str
    insights: list[Any]
    picks: list[Any]
    confidence: float
    agents_consulted: list[str]
    disclaimer: str


class PlayerOut(BaseModel):
    mlb_id: int
    full_name: str
    team_mlb_id: int | None
    team: str | None = None
    position: str | None
    bats: str | None
    throws: str | None
    is_pitcher: bool
    photo_url: str | None
    age: int | None
    height: str | None
    weight: int | None
    jersey_number: str | None
    roster_status: str | None

    model_config = {"from_attributes": True}


class PlayerProfileOut(BaseModel):
    player: PlayerOut
    stats: dict[str, Any]
    splits: dict[str, Any]
    last5: list[Any]
    predictions: list[Any]
    news: list[NewsOut]
    changes: list[ChangeOut]


class ManualOddsIn(BaseModel):
    """A line the user read in their sportsbook (Hard Rock Bet by default)."""

    game_pk: int
    market: str
    selection: str
    american: float
    line: float | None = None
    book: str | None = None


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
