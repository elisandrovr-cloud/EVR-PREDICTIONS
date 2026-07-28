"use client";

/** Perfil individual del jugador: bio, estadísticas, forma reciente, props de hoy,
 * noticias y movimientos detectados por los agentes. */
import Link from "next/link";
import { use } from "react";
import { ArrowLeft, Newspaper } from "lucide-react";

import { PickCard } from "@/components/simple/pick-card";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PanelSkeleton } from "@/components/ui/skeleton";
import { fmtPct } from "@/lib/format";
import { usePlayerProfile } from "@/lib/queries";
import type { Prediction } from "@/lib/types";

const STAT_LABELS: Record<string, string> = {
  avg: "AVG", obp: "OBP", slg: "SLG", ops: "OPS", iso: "ISO", babip: "BABIP",
  hit_per_pa: "H/PA", hr_per_pa: "HR/PA", bb_per_pa: "BB/PA", k_per_pa: "K/PA",
  rbi_per_pa: "RBI/PA", pa: "PA", sb_per_game: "SB/J",
  era: "ERA", whip: "WHIP", fip: "FIP", k_per_9: "K/9", bb_per_9: "BB/9",
  hits_per_9: "H/9", hr_per_9: "HR/9", k_pct: "K%", bb_pct: "BB%",
  innings_per_start: "IP/GS", innings_pitched: "IP",
};

export default function PlayerProfilePage({ params }: { params: Promise<{ mlbId: string }> }) {
  const { mlbId } = use(params);
  const profile = usePlayerProfile(Number(mlbId));

  if (profile.isLoading) return <PanelSkeleton rows={8} />;
  if (profile.isError || !profile.data) {
    return (
      <div className="space-y-3">
        <BackLink />
        <p className="rounded-md border border-dashed border-terminal-border p-8 text-center text-sm text-terminal-muted">
          No encontré a este jugador. Player Intelligence lo agregará en cuanto aparezca en un roster oficial.
        </p>
      </div>
    );
  }

  const { player, stats, last5, predictions, news, changes } = profile.data;
  const statEntries = Object.entries(stats).filter(
    ([k, v]) => STAT_LABELS[k] && typeof v === "number",
  ) as [string, number][];

  return (
    <div className="space-y-4">
      <BackLink />

      {/* Cabecera del perfil */}
      <Card>
        <CardContent className="flex flex-wrap items-center gap-4">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={player.photo_url ?? "https://midfield.mlbstatic.com/v1/people/0/spots/120"}
            alt={player.full_name}
            className="h-20 w-20 rounded-full bg-terminal-bg object-cover"
          />
          <div className="min-w-0 flex-1">
            <h1 className="text-xl font-bold text-terminal-text">
              {player.full_name}
              {player.jersey_number && (
                <span className="ml-2 font-mono text-sm text-terminal-muted">#{player.jersey_number}</span>
              )}
            </h1>
            <p className="mt-0.5 text-sm text-terminal-muted">
              {player.team ?? "Sin equipo"} · {player.position ?? "—"}
              {player.age ? ` · ${player.age} años` : ""}
              {player.height ? ` · ${player.height}` : ""}
              {player.weight ? ` · ${player.weight} lb` : ""}
            </p>
            <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
              <Badge variant="outline">
                {player.is_pitcher ? `Lanza ${player.throws ?? "?"}` : `Batea ${player.bats ?? "?"}`}
              </Badge>
              {player.roster_status && (
                <Badge variant={player.roster_status.includes("Injured") ? "red" : "green"}>
                  {player.roster_status}
                </Badge>
              )}
              <Badge variant={player.is_pitcher ? "violet" : "accent"}>
                {player.is_pitcher ? "Lanzador" : "Bateador"}
              </Badge>
            </div>
          </div>
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        {/* Estadísticas */}
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Estadísticas de temporada</CardTitle>
          </CardHeader>
          <CardContent>
            {statEntries.length > 0 ? (
              <div className="grid grid-cols-3 gap-2 sm:grid-cols-5">
                {statEntries.map(([key, value]) => (
                  <div key={key} className="rounded bg-terminal-bg p-2 text-center">
                    <div className="text-[9px] uppercase text-terminal-muted">{STAT_LABELS[key]}</div>
                    <div className="font-mono text-sm text-terminal-text">
                      {value < 1 && value > 0 ? value.toFixed(3) : value.toFixed(2)}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-xs text-terminal-muted">
                Sin estadísticas sincronizadas todavía — los agentes las traen automáticamente.
              </p>
            )}

            {last5.length > 0 && (
              <div className="mt-4">
                <div className="mb-1.5 font-mono text-[10px] uppercase tracking-wider text-terminal-muted">
                  Últimos 5 juegos
                </div>
                <div className="flex flex-wrap gap-2">
                  {last5.map((g, i) => (
                    <div key={i} className="rounded border border-terminal-border px-2 py-1 text-center">
                      <div className="text-[9px] text-terminal-muted">{g.date ?? `J${i + 1}`}</div>
                      <div className="font-mono text-sm font-bold text-terminal-text">
                        {g.hits ?? 0}
                        <span className="text-[10px] font-normal text-terminal-muted">
                          /{g.ab ?? 0}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Noticias y movimientos */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Newspaper className="h-3.5 w-3.5" /> Noticias y movimientos
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 p-3">
            {news.length === 0 && changes.length === 0 && (
              <p className="text-xs text-terminal-muted">Sin novedades registradas.</p>
            )}
            {news.map((n) => (
              <div key={n.id} className="rounded border border-terminal-border/60 p-2">
                <div className="flex items-center gap-1.5">
                  <Badge variant={n.category === "injury" ? "red" : "outline"}>{n.category}</Badge>
                  <span className="text-xs font-medium text-terminal-text">{n.headline}</span>
                </div>
                <p className="mt-0.5 text-[11px] text-terminal-muted">{n.body}</p>
              </div>
            ))}
            {changes.map((c) => (
              <div key={c.id} className="text-[11px] text-terminal-muted">
                • {c.detail}
              </div>
            ))}
          </CardContent>
        </Card>
      </div>

      {/* Props de hoy */}
      <section>
        <h2 className="mb-2 font-mono text-xs font-semibold uppercase tracking-widest text-terminal-muted">
          Apuestas de hoy para este jugador
        </h2>
        {predictions.length > 0 ? (
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
            {predictions.map((p) => (
              <PickCard
                key={p.id}
                pred={
                  {
                    ...p,
                    game_pk: 0,
                    game_date: "",
                    player_mlb_id: player.mlb_id,
                    expected_value: null,
                    edge: null,
                    kelly_stake: null,
                    risk: "medium",
                    model_breakdown: {},
                    settled: false,
                    outcome: null,
                    created_at: "",
                  } as unknown as Prediction
                }
              />
            ))}
          </div>
        ) : (
          <p className="rounded-md border border-dashed border-terminal-border p-6 text-center text-xs text-terminal-muted">
            No juega hoy o aún no hay líneas calculadas para él.
          </p>
        )}
      </section>

      {predictions.length > 0 && (
        <p className="text-center text-[11px] text-terminal-muted">
          Probabilidad media del modelo para este jugador hoy:{" "}
          {fmtPct(predictions.reduce((a, p) => a + p.probability, 0) / predictions.length)}
        </p>
      )}
    </div>
  );
}

function BackLink() {
  return (
    <Link href="/players" className="inline-flex items-center gap-1 text-xs text-terminal-accent hover:underline">
      <ArrowLeft className="h-3 w-3" /> Volver a jugadores
    </Link>
  );
}
