"use client";

/** Buscador de jugadores + snapshots de stats + props del día. */
import { useState } from "react";
import { Search } from "lucide-react";

import { PredictionRow } from "@/components/predictions/prediction-row";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { PanelSkeleton } from "@/components/ui/skeleton";
import { usePlayerPredictions, usePlayerSearch, usePlayerStats } from "@/lib/queries";

const STAT_LABELS: Record<string, string> = {
  avg: "AVG", obp: "OBP", slg: "SLG", ops: "OPS", iso: "ISO", babip: "BABIP",
  era: "ERA", whip: "WHIP", fip: "FIP", k_per_9: "K/9", bb_per_9: "BB/9",
  hits_per_9: "H/9", innings_per_start: "IP/GS", pa: "PA",
  hit_per_pa: "H/PA", hr_per_pa: "HR/PA", k_pct: "K%", bb_pct: "BB%",
};

export default function PlayersPage() {
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<number | null>(null);
  const results = usePlayerSearch(query);
  const stats = usePlayerStats(selected);
  const props = usePlayerPredictions(selected);

  return (
    <div className="space-y-4">
      <h1 className="font-mono text-sm font-semibold uppercase tracking-widest text-terminal-muted">Jugadores</h1>
      <div className="relative max-w-md">
        <Search className="absolute left-3 top-2.5 h-4 w-4 text-terminal-muted" />
        <Input
          placeholder="Buscar jugador (mín. 2 letras)…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="pl-9"
        />
      </div>

      {results.data && results.data.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {results.data.map((p) => (
            <button
              key={p.mlb_id}
              onClick={() => setSelected(p.mlb_id)}
              className={`rounded-md border px-3 py-1.5 text-sm transition-colors ${
                selected === p.mlb_id
                  ? "border-terminal-accent text-terminal-accent"
                  : "border-terminal-border text-terminal-text hover:border-terminal-accent/50"
              }`}
            >
              {p.name} <span className="text-xs text-terminal-muted">{p.position ?? ""}</span>
            </button>
          ))}
        </div>
      )}

      {selected && (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>Stats — {stats.data?.player.name ?? `#${selected}`}</CardTitle>
            </CardHeader>
            <CardContent>
              {stats.isLoading ? (
                <PanelSkeleton rows={3} />
              ) : stats.data && Object.keys(stats.data.snapshots).length > 0 ? (
                Object.entries(stats.data.snapshots).map(([scope, values]) => (
                  <div key={scope} className="mb-4">
                    <div className="mb-1.5 font-mono text-[10px] uppercase tracking-wider text-terminal-muted">
                      {scope}
                    </div>
                    <div className="grid grid-cols-3 gap-2 sm:grid-cols-4">
                      {Object.entries(values)
                        .filter(([k, v]) => typeof v === "number" && STAT_LABELS[k])
                        .map(([k, v]) => (
                          <div key={k} className="rounded bg-terminal-bg p-2 text-center">
                            <div className="text-[9px] uppercase text-terminal-muted">{STAT_LABELS[k]}</div>
                            <div className="font-mono text-sm text-terminal-text">
                              {Number(v) < 1 ? Number(v).toFixed(3) : Number(v).toFixed(2)}
                            </div>
                          </div>
                        ))}
                    </div>
                  </div>
                ))
              ) : (
                <p className="text-xs text-terminal-muted">
                  Sin snapshots — se sincronizan cuando el jugador entra en un lineup del día.
                </p>
              )}
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Props de hoy</CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              {props.isLoading ? (
                <PanelSkeleton rows={3} />
              ) : props.data && props.data.length > 0 ? (
                props.data.map((p) => <PredictionRow key={p.id} pred={p} />)
              ) : (
                <p className="p-6 text-center text-xs text-terminal-muted">Sin props hoy para este jugador.</p>
              )}
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
