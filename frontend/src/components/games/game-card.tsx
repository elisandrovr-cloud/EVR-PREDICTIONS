"use client";

import Link from "next/link";
import { CloudRain, User, Wind } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { fmtTime } from "@/lib/format";
import type { Game } from "@/lib/types";

export function GameCard({ game }: { game: Game }) {
  const statusVariant = game.status === "live" ? "green" : game.status === "final" ? "outline" : "accent";
  return (
    <Link
      href={`/games/${game.game_pk}`}
      className="block rounded-lg border border-terminal-border bg-terminal-panel p-3 transition-colors hover:border-terminal-accent/50"
    >
      <div className="flex items-center justify-between">
        <Badge variant={statusVariant}>
          {game.status === "live" ? "EN VIVO" : game.status === "final" ? "FINAL" : fmtTime(game.start_time)}
        </Badge>
        {game.lineup_confirmed && <Badge variant="violet">Lineup ✓</Badge>}
      </div>
      <div className="mt-2 space-y-1.5">
        <TeamLine name={game.away_team ?? `#${game.away_team_mlb_id}`} score={game.away_score} />
        <TeamLine name={game.home_team ?? `#${game.home_team_mlb_id}`} score={game.home_score} home />
      </div>
      <div className="mt-2 flex items-center gap-3 text-[10px] text-terminal-muted">
        {game.venue_name && <span className="truncate">{game.venue_name}</span>}
        {game.weather?.wind_speed_ms != null && (
          <span className="flex items-center gap-1">
            <Wind className="h-3 w-3" /> {Math.round(game.weather.wind_speed_ms)} m/s
          </span>
        )}
        {game.weather?.rain_probability != null && game.weather.rain_probability > 0.2 && (
          <span className="flex items-center gap-1 text-terminal-amber">
            <CloudRain className="h-3 w-3" /> {Math.round(game.weather.rain_probability * 100)}%
          </span>
        )}
        {game.umpire?.name && (
          <span className="flex items-center gap-1">
            <User className="h-3 w-3" /> {game.umpire.name}
          </span>
        )}
      </div>
    </Link>
  );
}

function TeamLine({ name, score, home }: { name: string; score: number | null; home?: boolean }) {
  return (
    <div className="flex items-center justify-between">
      <span className="truncate text-sm text-terminal-text">
        {name}
        {home && <span className="ml-1 text-[9px] uppercase text-terminal-muted">local</span>}
      </span>
      <span className="font-mono text-sm font-bold tabular-nums text-terminal-text">{score ?? "–"}</span>
    </div>
  );
}
