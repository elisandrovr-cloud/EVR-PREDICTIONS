/** API data contracts (mirror of backend Pydantic schemas). */

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface User {
  id: number;
  email: string;
  full_name: string | null;
  role: "user" | "premium" | "admin";
  provider: string;
  is_active: boolean;
  created_at: string;
}

export interface Team {
  mlb_id: number;
  name: string;
  abbreviation: string;
  league: string | null;
  division: string | null;
  venue_name: string | null;
  elo: number;
}

export interface LineupSlot {
  id: number;
  name: string;
  position: string | null;
}

export interface WeatherImpact {
  runs_multiplier: number;
  hr_multiplier: number;
}

export interface Weather {
  venue?: string;
  temperature_c?: number;
  humidity?: number;
  pressure_hpa?: number;
  wind_speed_ms?: number;
  wind_deg?: number;
  rain_probability?: number;
  description?: string;
  roofed?: boolean;
  altitude_m?: number;
  impact?: WeatherImpact;
}

export interface Game {
  game_pk: number;
  game_date: string;
  start_time: string | null;
  status: "scheduled" | "live" | "final" | string;
  venue_name: string | null;
  home_team_mlb_id: number;
  away_team_mlb_id: number;
  home_team: string | null;
  away_team: string | null;
  home_score: number | null;
  away_score: number | null;
  home_pitcher_mlb_id: number | null;
  away_pitcher_mlb_id: number | null;
  lineups: { home?: LineupSlot[]; away?: LineupSlot[] };
  lineup_confirmed: boolean;
  weather: Weather;
  umpire: { name?: string };
  linescore: { innings?: unknown[] };
}

export interface Prediction {
  id: number;
  game_pk: number;
  game_date: string;
  market: string;
  selection: string;
  player_mlb_id: number | null;
  line: number | null;
  probability: number;
  fair_odds: number;
  book_odds: number | null;
  expected_value: number | null;
  edge: number | null;
  kelly_stake: number | null;
  confidence: number;
  risk: "low" | "medium" | "high" | "extreme";
  is_value_bet: boolean;
  explanation: string;
  model_breakdown: Record<string, number>;
  settled: boolean;
  outcome: "win" | "loss" | "push" | null;
  created_at: string;
}

export interface ParlayLeg {
  prediction_id: number;
  game_pk: number;
  market: string;
  selection: string;
  probability: number;
  fair_odds: number;
  book_odds: number | null;
  confidence: number;
  risk: string;
  ev: number | null;
  explanation: string;
}

export interface Parlay {
  id: number;
  game_date: string;
  profile: string;
  legs: ParlayLeg[];
  combined_probability: number;
  combined_decimal_odds: number;
  expected_value: number;
  confidence: number;
  risk: string;
  explanation: string;
  settled: boolean;
  outcome: string | null;
}

export interface OddsQuote {
  game_pk: number;
  book: string;
  market: string;
  selection: string;
  line: number | null;
  american: number;
  implied_prob: number;
  captured_at: string;
}

export interface EngineMetric {
  metric_date: string;
  market: string;
  predictions: number;
  wins: number;
  losses: number;
  pushes: number;
  roi: number | null;
  clv: number | null;
  brier_score: number | null;
}

export interface ModelWeight {
  model_name: string;
  market: string;
  weight: number;
  brier_score: number | null;
  log_loss: number | null;
  samples: number;
  updated_at: string;
}

export interface SourceStatus {
  source: string;
  status: "ok" | "degraded" | "down" | "disabled" | "unknown";
  last_success: string | null;
  last_error: string | null;
  latency_ms: number | null;
}

export interface Bankroll {
  balance: number;
  currency: string;
  updated_at: string;
}

export interface Bet {
  id: number;
  description: string;
  stake: number;
  american_odds: number;
  status: "open" | "won" | "lost" | "push";
  payout: number | null;
  placed_at: string;
}

export interface PlayerSearchResult {
  mlb_id: number;
  name: string;
  team_mlb_id: number | null;
  position: string | null;
  bats: string | null;
  throws: string | null;
}

export interface PlayerStats {
  player: { mlb_id: number; name: string | null; position: string | null };
  snapshots: Record<string, Record<string, number>>;
}
