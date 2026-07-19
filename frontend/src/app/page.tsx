"use client";

/** Terminal principal — vista Bloomberg: juegos, value bets, parlays, motor. */
import Link from "next/link";
import { ArrowRight, Flame, TrendingUp, Zap } from "lucide-react";

import { PerformanceChart } from "@/components/charts/performance-chart";
import { GameCard } from "@/components/games/game-card";
import { PredictionRow } from "@/components/predictions/prediction-row";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PanelSkeleton } from "@/components/ui/skeleton";
import { fmtEv, fmtPct, PROFILE_LABELS } from "@/lib/format";
import { useEngineMetrics, useParlays, useTodayGames, useTopBoard } from "@/lib/queries";

export default function DashboardPage() {
  const games = useTodayGames();
  const valueBets = useTopBoard("value-bets");
  const moneyline = useTopBoard("moneyline");
  const parlays = useParlays();
  const metrics = useEngineMetrics(30);

  return (
    <div className="space-y-4">
      <StatStrip />

      <section>
        <SectionHeader title="Cartelera de hoy" href="/games" />
        {games.isLoading ? (
          <PanelSkeleton rows={2} />
        ) : games.data && games.data.length > 0 ? (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {games.data.slice(0, 8).map((g) => (
              <GameCard key={g.game_pk} game={g} />
            ))}
          </div>
        ) : (
          <EmptyNote text="Sin juegos programados hoy. El calendario se sincroniza automáticamente cada 2 minutos." />
        )}
      </section>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Zap className="h-3.5 w-3.5 text-terminal-green" /> Top Value Bets
            </CardTitle>
            <Link href="/predictions" className="text-xs text-terminal-accent hover:underline">
              Ver todas
            </Link>
          </CardHeader>
          <CardContent className="p-0">
            {valueBets.isLoading ? (
              <PanelSkeleton />
            ) : valueBets.data && valueBets.data.length > 0 ? (
              valueBets.data.slice(0, 6).map((p) => <PredictionRow key={p.id} pred={p} />)
            ) : moneyline.data && moneyline.data.length > 0 ? (
              <>
                <p className="border-b border-terminal-border/60 px-4 py-2 text-[11px] text-terminal-muted">
                  Sin edge positivo contra las casas ahora mismo — mostrando las selecciones más probables.
                </p>
                {moneyline.data.slice(0, 5).map((p) => (
                  <PredictionRow key={p.id} pred={p} />
                ))}
              </>
            ) : (
              <EmptyNote text="El motor publica predicciones en cuanto hay cartelera y datos de lineup." />
            )}
          </CardContent>
        </Card>

        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Flame className="h-3.5 w-3.5 text-terminal-amber" /> Parlays IA
              </CardTitle>
              <Link href="/parlays" className="text-xs text-terminal-accent hover:underline">
                Ver todos
              </Link>
            </CardHeader>
            <CardContent className="space-y-2 p-3">
              {parlays.isLoading ? (
                <PanelSkeleton rows={3} />
              ) : parlays.data && parlays.data.length > 0 ? (
                parlays.data.slice(0, 3).map((p) => (
                  <Link
                    key={p.id}
                    href="/parlays"
                    className="flex items-center justify-between rounded-md border border-terminal-border p-2.5 hover:border-terminal-accent/50"
                  >
                    <div>
                      <div className="text-sm text-terminal-text">{PROFILE_LABELS[p.profile] ?? p.profile}</div>
                      <div className="font-mono text-[10px] text-terminal-muted">
                        {p.legs.length} legs · {fmtPct(p.combined_probability)} · x{p.combined_decimal_odds.toFixed(2)}
                      </div>
                    </div>
                    <Badge variant={p.expected_value > 0 ? "green" : "outline"}>{fmtEv(p.expected_value)}</Badge>
                  </Link>
                ))
              ) : (
                <EmptyNote text="Los parlays se generan automáticamente cada 15 minutos." />
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <TrendingUp className="h-3.5 w-3.5 text-terminal-accent" /> Rendimiento del motor
              </CardTitle>
            </CardHeader>
            <CardContent>
              {metrics.isLoading ? <PanelSkeleton rows={3} /> : <PerformanceChart metrics={metrics.data ?? []} />}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

function StatStrip() {
  const metrics = useEngineMetrics(7);
  const valueBets = useTopBoard("value-bets");
  const games = useTodayGames();
  const latest = metrics.data?.at(-1);
  const winRate =
    latest && latest.wins + latest.losses > 0 ? latest.wins / (latest.wins + latest.losses) : null;
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
      <StatTile label="Juegos hoy" value={games.data ? String(games.data.length) : "—"} />
      <StatTile label="Value bets activas" value={valueBets.data ? String(valueBets.data.length) : "—"} />
      <StatTile label="Win rate (último cierre)" value={winRate != null ? fmtPct(winRate, 0) : "—"} />
      <StatTile
        label="ROI (último cierre)"
        value={latest?.roi != null ? fmtEv(latest.roi) : "—"}
        tone={latest?.roi != null ? (latest.roi >= 0 ? "green" : "red") : undefined}
      />
    </div>
  );
}

function StatTile({ label, value, tone }: { label: string; value: string; tone?: "green" | "red" }) {
  return (
    <div className="rounded-lg border border-terminal-border bg-terminal-panel p-3">
      <div className="font-mono text-[10px] uppercase tracking-wider text-terminal-muted">{label}</div>
      <div
        className={`mt-1 font-mono text-2xl font-bold tabular-nums ${
          tone === "green" ? "text-terminal-green" : tone === "red" ? "text-terminal-red" : "text-terminal-text"
        }`}
      >
        {value}
      </div>
    </div>
  );
}

function SectionHeader({ title, href }: { title: string; href: string }) {
  return (
    <div className="mb-2 flex items-center justify-between">
      <h2 className="font-mono text-xs font-semibold uppercase tracking-widest text-terminal-muted">{title}</h2>
      <Link href={href} className="flex items-center gap-1 text-xs text-terminal-accent hover:underline">
        Ver más <ArrowRight className="h-3 w-3" />
      </Link>
    </div>
  );
}

function EmptyNote({ text }: { text: string }) {
  return <p className="rounded-md border border-dashed border-terminal-border p-4 text-center text-xs text-terminal-muted">{text}</p>;
}
