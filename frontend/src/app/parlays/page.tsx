"use client";

/** Parlays generados por IA — 6 perfiles con EV, riesgo y explicación por leg. */
import { Badge, riskBadgeVariant } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PanelSkeleton } from "@/components/ui/skeleton";
import { fmtAmerican, fmtEv, fmtPct, MARKET_LABELS, PROFILE_LABELS } from "@/lib/format";
import { useParlays } from "@/lib/queries";
import type { Parlay } from "@/lib/types";

export default function ParlaysPage() {
  const parlays = useParlays();

  return (
    <div className="space-y-4">
      <h1 className="font-mono text-sm font-semibold uppercase tracking-widest text-terminal-muted">
        Parlays IA del día
      </h1>
      {parlays.isLoading ? (
        <PanelSkeleton rows={6} />
      ) : parlays.data && parlays.data.length > 0 ? (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {parlays.data.map((p) => (
            <ParlayCard key={p.id} parlay={p} />
          ))}
        </div>
      ) : (
        <p className="rounded-md border border-dashed border-terminal-border p-8 text-center text-sm text-terminal-muted">
          Los parlays se construyen automáticamente cada 15 minutos a partir del pool de predicciones.
        </p>
      )}
    </div>
  );
}

function ParlayCard({ parlay }: { parlay: Parlay }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{PROFILE_LABELS[parlay.profile] ?? parlay.profile}</CardTitle>
        <div className="flex items-center gap-2">
          <Badge variant={riskBadgeVariant(parlay.risk)}>{parlay.risk}</Badge>
          <Badge variant={parlay.expected_value > 0 ? "green" : "outline"}>EV {fmtEv(parlay.expected_value)}</Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid grid-cols-3 gap-2 rounded-md bg-terminal-bg p-2.5 text-center font-mono">
          <div>
            <div className="text-[9px] uppercase text-terminal-muted">Prob conjunta</div>
            <div className="text-sm font-bold text-terminal-accent">{fmtPct(parlay.combined_probability)}</div>
          </div>
          <div>
            <div className="text-[9px] uppercase text-terminal-muted">Cuota</div>
            <div className="text-sm font-bold text-terminal-text">x{parlay.combined_decimal_odds.toFixed(2)}</div>
          </div>
          <div>
            <div className="text-[9px] uppercase text-terminal-muted">Confianza</div>
            <div className="text-sm font-bold text-terminal-text">{fmtPct(parlay.confidence, 0)}</div>
          </div>
        </div>
        <ol className="space-y-2">
          {parlay.legs.map((leg, i) => (
            <li key={i} className="rounded-md border border-terminal-border/60 p-2.5">
              <div className="flex items-center justify-between gap-2">
                <span className="text-sm text-terminal-text">{leg.selection}</span>
                <span className="font-mono text-xs text-terminal-muted">
                  {fmtPct(leg.probability)} · {fmtAmerican(leg.book_odds ?? leg.fair_odds)}
                </span>
              </div>
              <div className="mt-1 flex items-center gap-2">
                <Badge variant="outline">{MARKET_LABELS[leg.market] ?? leg.market}</Badge>
                <span className="line-clamp-1 text-[11px] text-terminal-muted">{leg.explanation}</span>
              </div>
            </li>
          ))}
        </ol>
        <p className="text-[11px] leading-relaxed text-terminal-muted">{parlay.explanation}</p>
      </CardContent>
    </Card>
  );
}
