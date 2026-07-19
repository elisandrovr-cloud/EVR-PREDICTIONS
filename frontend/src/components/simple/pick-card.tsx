"use client";

/** A single betting pick explained in plain language for a total beginner. */
import { Star } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { PLAIN_MARKET, confidenceLabel, outOfTen, payoutText, plainTitle, safetyStars, stakeAdvice } from "@/lib/plain";
import type { Prediction } from "@/lib/types";
import { cn } from "@/lib/utils";

export function PickCard({ pred }: { pred: Prediction }) {
  const conf = confidenceLabel(pred.probability);
  const stars = safetyStars(pred.probability);

  return (
    <div className="rounded-xl border border-terminal-border bg-terminal-panel p-4">
      <div className="mb-2 flex items-center justify-between gap-2">
        <Badge variant="outline">{PLAIN_MARKET[pred.market] ?? "Apuesta"}</Badge>
        <div className="flex items-center gap-0.5" aria-label={`${stars} de 5 estrellas`}>
          {Array.from({ length: 5 }).map((_, i) => (
            <Star
              key={i}
              className={cn("h-3.5 w-3.5", i < stars ? "fill-terminal-amber text-terminal-amber" : "text-terminal-border")}
            />
          ))}
        </div>
      </div>

      <h3 className="text-base font-bold leading-snug text-terminal-text">{plainTitle(pred)}</h3>

      <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
        <span className={cn("font-semibold", conf.color)}>
          {conf.emoji} {conf.text}
        </span>
        <span className="text-terminal-muted">Pasa {outOfTen(pred.probability)}</span>
      </div>

      <div className="mt-3 rounded-lg bg-terminal-bg p-2.5 text-sm text-terminal-text">
        💵 {payoutText(pred.book_odds, pred.fair_odds)}
        <span className="ml-2 text-xs text-terminal-muted">· {stakeAdvice(pred.kelly_stake)}</span>
      </div>

      <p className="mt-2 text-xs leading-relaxed text-terminal-muted">
        <span className="font-semibold text-terminal-text">¿Por qué?</span> {pred.explanation}
      </p>
    </div>
  );
}
