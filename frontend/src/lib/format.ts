/** Display helpers: odds, probabilities, money, dates. */

export function fmtAmerican(odds: number | null | undefined): string {
  if (odds == null) return "—";
  return odds > 0 ? `+${Math.round(odds)}` : `${Math.round(odds)}`;
}

export function fmtPct(p: number | null | undefined, digits = 1): string {
  if (p == null) return "—";
  return `${(p * 100).toFixed(digits)}%`;
}

export function fmtEv(ev: number | null | undefined): string {
  if (ev == null) return "—";
  const sign = ev >= 0 ? "+" : "";
  return `${sign}${(ev * 100).toFixed(1)}%`;
}

export function fmtMoney(v: number | null | undefined, currency = "USD"): string {
  if (v == null) return "—";
  return new Intl.NumberFormat("en-US", { style: "currency", currency }).format(v);
}

export function fmtTime(iso: string | null | undefined): string {
  if (!iso) return "TBD";
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString([], { month: "short", day: "numeric" });
}

export const MARKET_LABELS: Record<string, string> = {
  moneyline: "Moneyline",
  run_line: "Run Line",
  total_over: "Over",
  total_under: "Under",
  first_inning: "1st Inning",
  player_hits: "Hits",
  player_home_runs: "Home Runs",
  player_rbi: "RBI",
  player_total_bases: "Total Bases",
  player_stolen_bases: "Stolen Bases",
  player_runs: "Runs",
  player_walks: "Walks",
  pitcher_strikeouts: "Strikeouts (P)",
  pitcher_walks: "Walks (P)",
  pitcher_outs: "Outs (P)",
  pitcher_hits_allowed: "Hits Allowed",
  pitcher_earned_runs: "Earned Runs",
  pitcher_win: "Pitcher Win",
  quality_start: "Quality Start",
  no_hitter: "No-Hitter",
};

export const PROFILE_LABELS: Record<string, string> = {
  conservative: "Conservador",
  balanced: "Balanceado",
  aggressive: "Agresivo",
  same_game: "Same Game",
  high_odds: "High Odds",
  ai_premium: "AI Premium",
};

export const RISK_COLORS: Record<string, string> = {
  low: "text-terminal-green",
  medium: "text-terminal-amber",
  high: "text-orange-400",
  extreme: "text-terminal-red",
};
