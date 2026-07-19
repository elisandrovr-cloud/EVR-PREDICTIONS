"use client";

/** Sala de Agentes — expertos en béisbol debaten y compiten por el mejor parlay
 * del día en cada categoría (hits / ponches / juegos / mixto) y estilo (seguro / agresivo). */
import { useMemo, useState } from "react";
import { motion } from "framer-motion";
import { Crown, Swords } from "lucide-react";

import { Badge, riskBadgeVariant } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PanelSkeleton } from "@/components/ui/skeleton";
import { Tabs } from "@/components/ui/tabs";
import { fmtAmerican, fmtEv, fmtPct, MARKET_LABELS } from "@/lib/format";
import { useAgentParlays } from "@/lib/queries";
import type { AgentParlay } from "@/lib/types";

const CATEGORIES = [
  { id: "hits", label: "Solo Hits" },
  { id: "strikeouts", label: "Solo Ponches" },
  { id: "games", label: "Solo Juegos" },
  { id: "mixed", label: "Mixto" },
];

export default function AgentsPage() {
  const parlays = useAgentParlays();
  const [category, setCategory] = useState("hits");

  const byCategory = useMemo(() => {
    const map: Record<string, AgentParlay[]> = {};
    for (const p of parlays.data ?? []) (map[p.category] ??= []).push(p);
    for (const list of Object.values(map)) list.sort((a, b) => (a.style === "safe" ? -1 : 1));
    return map;
  }, [parlays.data]);

  const current = byCategory[category] ?? [];

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <Swords className="h-5 w-5 text-terminal-accent" />
        <h1 className="font-mono text-sm font-semibold uppercase tracking-widest text-terminal-muted">
          Sala de Agentes — el debate del día
        </h1>
      </div>
      <p className="max-w-3xl text-xs leading-relaxed text-terminal-muted">
        Cuatro analistas con filosofías distintas — <b className="text-terminal-text">El Sabio</b> (seguridad),{" "}
        <b className="text-terminal-text">El Francotirador</b> (valor vs. la casa),{" "}
        <b className="text-terminal-text">El Apostador</b> (cuota máxima) y{" "}
        <b className="text-terminal-text">El Analista</b> (convicción del modelo) — analizan los rosters del día y
        compiten por armar el mejor parlay. El juez elige al ganador por categoría y estilo, y aquí queda el debate.
      </p>

      <Tabs tabs={CATEGORIES} active={category} onChange={setCategory} />

      {parlays.isLoading ? (
        <PanelSkeleton rows={6} />
      ) : current.length === 0 ? (
        <p className="rounded-md border border-dashed border-terminal-border p-8 text-center text-sm text-terminal-muted">
          Aún no hay parlay de {CATEGORIES.find((c) => c.id === category)?.label.toLowerCase()} para hoy. Los de hits y
          ponches requieren que el cron de stats sincronice los lineups; los de juegos aparecen apenas hay cartelera.
        </p>
      ) : (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {current.map((p) => (
            <AgentParlayCard key={p.id} parlay={p} />
          ))}
        </div>
      )}
    </div>
  );
}

function AgentParlayCard({ parlay }: { parlay: AgentParlay }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          {parlay.style === "safe" ? "Seguro" : "Agresivo"}
          <Badge variant={riskBadgeVariant(parlay.risk)}>{parlay.risk}</Badge>
        </CardTitle>
        <div className="flex items-center gap-1.5 font-mono text-[11px] text-terminal-amber">
          <Crown className="h-3.5 w-3.5" /> {parlay.winning_agent}
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid grid-cols-3 gap-2 rounded-md bg-terminal-bg p-2.5 text-center font-mono">
          <Stat label="Acierto" value={fmtPct(parlay.combined_probability)} accent />
          <Stat label="Cuota" value={`x${parlay.combined_decimal_odds.toFixed(2)}`} />
          <Stat label="EV" value={fmtEv(parlay.expected_value)} />
        </div>

        <ol className="space-y-1.5">
          {parlay.legs.map((leg, i) => (
            <li key={i} className="flex items-center justify-between gap-2 rounded border border-terminal-border/60 px-2.5 py-1.5">
              <span className="truncate text-sm text-terminal-text">{leg.selection}</span>
              <span className="flex items-center gap-2 font-mono text-[11px] text-terminal-muted">
                <Badge variant="outline">{MARKET_LABELS[leg.market] ?? leg.market}</Badge>
                {fmtPct(leg.probability)} · {fmtAmerican(leg.book_odds ?? leg.fair_odds)}
              </span>
            </li>
          ))}
        </ol>

        <div>
          <div className="mb-1.5 font-mono text-[10px] uppercase tracking-wider text-terminal-muted">
            El debate
          </div>
          <div className="space-y-1.5">
            {parlay.debate.map((d, i) => (
              <motion.div
                key={d.agent}
                initial={{ opacity: 0, x: -6 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.05 }}
                className={`rounded-md border p-2 text-xs ${
                  d.won
                    ? "border-terminal-amber/50 bg-terminal-amber/5"
                    : "border-terminal-border/50 bg-terminal-bg/40"
                }`}
              >
                <div className="mb-0.5 flex items-center justify-between">
                  <span className="flex items-center gap-1.5 font-semibold text-terminal-text">
                    {d.won && <Crown className="h-3 w-3 text-terminal-amber" />}
                    {d.agent}
                    <span className="font-normal text-terminal-muted/70">· {d.tagline}</span>
                  </span>
                  <span className="font-mono text-[10px] text-terminal-muted">
                    score {(d.score * (parlay.style === "safe" ? 100 : 1)).toFixed(parlay.style === "safe" ? 0 : 2)}
                    {parlay.style === "safe" ? "%" : "x"}
                  </span>
                </div>
                <p className="leading-relaxed text-terminal-muted">{d.argument}</p>
              </motion.div>
            ))}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function Stat({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div>
      <div className="text-[9px] uppercase text-terminal-muted">{label}</div>
      <div className={`text-sm font-bold ${accent ? "text-terminal-accent" : "text-terminal-text"}`}>{value}</div>
    </div>
  );
}
