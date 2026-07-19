"use client";

import { motion } from "framer-motion";

import { Badge, riskBadgeVariant } from "@/components/ui/badge";
import { fmtAmerican, fmtEv, fmtPct, MARKET_LABELS } from "@/lib/format";
import type { Prediction } from "@/lib/types";
import { cn } from "@/lib/utils";

export function ProbabilityBar({ value, className }: { value: number; className?: string }) {
  return (
    <div className={cn("h-1.5 w-full overflow-hidden rounded-full bg-terminal-border", className)}>
      <motion.div
        initial={{ width: 0 }}
        animate={{ width: `${Math.min(value * 100, 100)}%` }}
        transition={{ duration: 0.6, ease: "easeOut" }}
        className={cn(
          "h-full rounded-full",
          value >= 0.6 ? "bg-terminal-green" : value >= 0.45 ? "bg-terminal-amber" : "bg-terminal-red",
        )}
      />
    </div>
  );
}

export function PredictionRow({ pred, showMarket = true }: { pred: Prediction; showMarket?: boolean }) {
  return (
    <div className="border-b border-terminal-border/60 px-4 py-3 last:border-0 hover:bg-terminal-border/20">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            {showMarket && <Badge variant="outline">{MARKET_LABELS[pred.market] ?? pred.market}</Badge>}
            <span className="truncate text-sm font-medium text-terminal-text">{pred.selection}</span>
            {pred.is_value_bet && <Badge variant="green">VALUE</Badge>}
            {pred.outcome && (
              <Badge variant={pred.outcome === "win" ? "green" : pred.outcome === "loss" ? "red" : "outline"}>
                {pred.outcome}
              </Badge>
            )}
          </div>
          <p className="mt-1 line-clamp-2 text-xs leading-relaxed text-terminal-muted">{pred.explanation}</p>
          <ProbabilityBar value={pred.probability} className="mt-2 max-w-56" />
        </div>
        <div className="grid shrink-0 grid-cols-2 gap-x-4 gap-y-1 text-right font-mono text-xs sm:grid-cols-4">
          <Metric label="Prob" value={fmtPct(pred.probability)} accent />
          <Metric label="Conf" value={fmtPct(pred.confidence, 0)} />
          <Metric
            label="EV"
            value={fmtEv(pred.expected_value)}
            className={
              pred.expected_value == null
                ? undefined
                : pred.expected_value > 0
                  ? "text-terminal-green"
                  : "text-terminal-red"
            }
          />
          <Metric label="Cuota" value={fmtAmerican(pred.book_odds ?? pred.fair_odds)} />
        </div>
      </div>
      <div className="mt-1.5 flex items-center justify-end gap-2">
        <Badge variant={riskBadgeVariant(pred.risk)}>{pred.risk}</Badge>
        {pred.kelly_stake != null && pred.kelly_stake > 0 && (
          <span className="font-mono text-[10px] text-terminal-muted">
            Kelly: {fmtPct(pred.kelly_stake, 1)} bankroll
          </span>
        )}
      </div>
    </div>
  );
}

function Metric({
  label,
  value,
  accent,
  className,
}: {
  label: string;
  value: string;
  accent?: boolean;
  className?: string;
}) {
  return (
    <div>
      <div className="text-[9px] uppercase tracking-wider text-terminal-muted/70">{label}</div>
      <div className={cn("tabular-nums", accent ? "text-terminal-accent" : "text-terminal-text", className)}>
        {value}
      </div>
    </div>
  );
}
