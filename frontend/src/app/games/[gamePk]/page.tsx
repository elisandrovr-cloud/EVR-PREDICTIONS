"use client";

/** Ficha del juego: marcador, lineups, clima, umpire, cuotas y todas las predicciones. */
import { use, useMemo, useState } from "react";
import { CloudRain, Gauge, Thermometer, User, Wind } from "lucide-react";

import { OddsMovementChart } from "@/components/charts/odds-movement-chart";
import { PredictionRow } from "@/components/predictions/prediction-row";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PanelSkeleton } from "@/components/ui/skeleton";
import { Tabs } from "@/components/ui/tabs";
import { fmtTime, MARKET_LABELS } from "@/lib/format";
import { useGame, useGameOdds, useGamePredictions } from "@/lib/queries";

const GAME_MARKETS = ["moneyline", "run_line", "total_over", "total_under", "first_inning"];

export default function GameDetailPage({ params }: { params: Promise<{ gamePk: string }> }) {
  const { gamePk } = use(params);
  const pk = Number(gamePk);
  const game = useGame(pk);
  const preds = useGamePredictions(pk);
  const odds = useGameOdds(pk);
  const [tab, setTab] = useState("game");

  const grouped = useMemo(() => {
    const all = preds.data ?? [];
    return {
      game: all.filter((p) => GAME_MARKETS.includes(p.market)),
      batters: all.filter((p) => p.market.startsWith("player_")),
      pitchers: all.filter(
        (p) => p.market.startsWith("pitcher_") || p.market === "quality_start" || p.market === "no_hitter",
      ),
    };
  }, [preds.data]);

  const oddsSelections = useMemo(
    () => [...new Set((odds.data ?? []).filter((q) => q.market === "moneyline").map((q) => q.selection))],
    [odds.data],
  );
  const [oddsSel, setOddsSel] = useState<string | null>(null);
  const activeSel = oddsSel ?? oddsSelections[0] ?? null;

  if (game.isLoading) return <PanelSkeleton rows={6} />;
  if (!game.data) return <p className="p-6 text-sm text-terminal-muted">Juego no encontrado.</p>;

  const g = game.data;
  const wx = g.weather;

  return (
    <div className="space-y-4">
      <Card>
        <CardContent className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <Badge variant={g.status === "live" ? "green" : g.status === "final" ? "outline" : "accent"}>
                {g.status === "live" ? "EN VIVO" : g.status === "final" ? "FINAL" : fmtTime(g.start_time)}
              </Badge>
              {g.lineup_confirmed && <Badge variant="violet">Lineups confirmados</Badge>}
            </div>
            <h1 className="mt-2 text-xl font-bold text-terminal-text">
              {g.away_team} <span className="font-mono">{g.away_score ?? ""}</span>
              <span className="mx-2 text-terminal-muted">@</span>
              {g.home_team} <span className="font-mono">{g.home_score ?? ""}</span>
            </h1>
            <p className="mt-1 text-xs text-terminal-muted">{g.venue_name}</p>
          </div>
          <div className="grid grid-cols-2 gap-x-6 gap-y-1 text-xs text-terminal-muted">
            {wx?.temperature_c != null && (
              <span className="flex items-center gap-1.5">
                <Thermometer className="h-3.5 w-3.5" /> {Math.round(wx.temperature_c)}°C
              </span>
            )}
            {wx?.wind_speed_ms != null && (
              <span className="flex items-center gap-1.5">
                <Wind className="h-3.5 w-3.5" /> {Math.round(wx.wind_speed_ms)} m/s
              </span>
            )}
            {wx?.rain_probability != null && (
              <span className="flex items-center gap-1.5">
                <CloudRain className="h-3.5 w-3.5" /> lluvia {Math.round((wx.rain_probability ?? 0) * 100)}%
              </span>
            )}
            {wx?.impact && (
              <span className="flex items-center gap-1.5">
                <Gauge className="h-3.5 w-3.5" /> impacto carreras x{wx.impact.runs_multiplier}
              </span>
            )}
            {g.umpire?.name && (
              <span className="col-span-2 flex items-center gap-1.5">
                <User className="h-3.5 w-3.5" /> HP Umpire: {g.umpire.name}
              </span>
            )}
          </div>
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Predicciones del motor</CardTitle>
          </CardHeader>
          <Tabs
            className="px-4"
            active={tab}
            onChange={setTab}
            tabs={[
              { id: "game", label: `Juego (${grouped.game.length})` },
              { id: "batters", label: `Bateadores (${grouped.batters.length})` },
              { id: "pitchers", label: `Pitchers (${grouped.pitchers.length})` },
            ]}
          />
          <CardContent className="p-0">
            {preds.isLoading ? (
              <PanelSkeleton />
            ) : (
              (grouped[tab as keyof typeof grouped] ?? []).map((p) => <PredictionRow key={p.id} pred={p} />)
            )}
            {!preds.isLoading && (grouped[tab as keyof typeof grouped] ?? []).length === 0 && (
              <p className="p-6 text-center text-xs text-terminal-muted">
                Sin predicciones en esta pestaña todavía.
              </p>
            )}
          </CardContent>
        </Card>

        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Movimiento de cuotas</CardTitle>
            </CardHeader>
            <CardContent>
              {oddsSelections.length > 0 && (
                <div className="mb-2 flex flex-wrap gap-1">
                  {oddsSelections.map((sel) => (
                    <button
                      key={sel}
                      onClick={() => setOddsSel(sel)}
                      className={`rounded px-2 py-1 font-mono text-[10px] ${
                        activeSel === sel
                          ? "bg-terminal-accent/15 text-terminal-accent"
                          : "text-terminal-muted hover:text-terminal-text"
                      }`}
                    >
                      {sel}
                    </button>
                  ))}
                </div>
              )}
              {activeSel ? (
                <OddsMovementChart quotes={odds.data ?? []} selection={activeSel} />
              ) : (
                <p className="py-6 text-center text-xs text-terminal-muted">
                  Sin cuotas capturadas (configura ODDS_API_KEY).
                </p>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Lineups</CardTitle>
            </CardHeader>
            <CardContent className="grid grid-cols-2 gap-3 text-xs">
              <LineupList title={g.away_team ?? "Visitante"} slots={g.lineups?.away ?? []} />
              <LineupList title={g.home_team ?? "Local"} slots={g.lineups?.home ?? []} />
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

function LineupList({ title, slots }: { title: string; slots: { id: number; name: string; position: string | null }[] }) {
  return (
    <div>
      <div className="mb-1.5 font-mono text-[10px] uppercase tracking-wider text-terminal-muted">{title}</div>
      {slots.length === 0 ? (
        <p className="text-terminal-muted/70">Por confirmar</p>
      ) : (
        <ol className="space-y-1">
          {slots.map((s, i) => (
            <li key={s.id} className="flex justify-between gap-2 text-terminal-text">
              <span className="truncate">
                {i + 1}. {s.name}
              </span>
              <span className="text-terminal-muted">{s.position}</span>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
