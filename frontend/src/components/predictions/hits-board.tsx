"use client";

/** Ranked hit-probability board: every batter today, highest first, with last-5 form. */
import { motion } from "framer-motion";

import { Badge } from "@/components/ui/badge";
import { PanelSkeleton } from "@/components/ui/skeleton";
import { fmtAmerican, fmtPct } from "@/lib/format";
import { useHitsBoard } from "@/lib/queries";
import type { HitsBoardRow } from "@/lib/types";

export function HitsBoard() {
  const board = useHitsBoard();

  if (board.isLoading) return <PanelSkeleton rows={8} />;
  if (!board.data || board.data.length === 0) {
    return (
      <div className="flex flex-col items-center gap-2 p-8 text-center">
        <span className="relative flex h-2.5 w-2.5">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-terminal-accent opacity-60" />
          <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-terminal-accent" />
        </span>
        <p className="text-xs text-terminal-muted">
          Sincronizando bateadores del día… El tablero se llena solo en ~1–2 minutos conforme llegan
          los lineups y las estadísticas. Esta vista se actualiza sola cada minuto.
        </p>
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[640px] text-left text-sm">
        <thead>
          <tr className="border-b border-terminal-border font-mono text-[10px] uppercase tracking-wider text-terminal-muted">
            <th className="px-3 py-2 w-8">#</th>
            <th className="px-3 py-2">Bateador</th>
            <th className="px-3 py-2 text-right">Prob. Hit</th>
            <th className="px-3 py-2 text-center">Últimos 5 (hits)</th>
            <th className="px-3 py-2 text-right">L5 Total</th>
            <th className="px-3 py-2 text-right">Cuota</th>
          </tr>
        </thead>
        <tbody>
          {board.data.map((row, i) => (
            <BatterRow key={`${row.player_mlb_id}-${i}`} row={row} rank={i + 1} />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function BatterRow({ row, rank }: { row: HitsBoardRow; rank: number }) {
  return (
    <tr className="border-b border-terminal-border/50 last:border-0 hover:bg-terminal-border/20">
      <td className="px-3 py-2 font-mono text-xs text-terminal-muted">{rank}</td>
      <td className="px-3 py-2">
        <div className="flex items-center gap-2">
          <span className="font-medium text-terminal-text">{row.player}</span>
          {row.is_value_bet && <Badge variant="green">VALUE</Badge>}
        </div>
        {row.team && <span className="text-[10px] text-terminal-muted">{row.team}</span>}
      </td>
      <td className="px-3 py-2 text-right">
        <div className="flex items-center justify-end gap-2">
          <div className="hidden h-1.5 w-20 overflow-hidden rounded-full bg-terminal-border sm:block">
            <motion.div
              initial={{ width: 0 }}
              animate={{ width: `${Math.min(row.probability * 100, 100)}%` }}
              transition={{ duration: 0.5 }}
              className={
                row.probability >= 0.65
                  ? "h-full bg-terminal-green"
                  : row.probability >= 0.5
                    ? "h-full bg-terminal-amber"
                    : "h-full bg-terminal-red"
              }
            />
          </div>
          <span className="font-mono text-sm font-bold tabular-nums text-terminal-accent">
            {fmtPct(row.probability)}
          </span>
        </div>
      </td>
      <td className="px-3 py-2">
        <Last5 hits={row.last5_hits} />
      </td>
      <td className="px-3 py-2 text-right font-mono tabular-nums text-terminal-text">
        {row.last5_hits.length ? row.last5_total : "—"}
      </td>
      <td className="px-3 py-2 text-right font-mono text-xs text-terminal-muted">
        {fmtAmerican(row.book_odds ?? row.fair_odds)}
      </td>
    </tr>
  );
}

/** Newest game on the right; color intensity by hit count. */
function Last5({ hits }: { hits: number[] }) {
  if (!hits.length) {
    return <span className="text-[10px] text-terminal-muted/60">sin datos</span>;
  }
  return (
    <div className="flex items-center justify-center gap-1">
      {hits.map((h, i) => (
        <span
          key={i}
          title={`${h} hit${h === 1 ? "" : "s"}`}
          className="flex h-6 w-6 items-center justify-center rounded font-mono text-[11px] font-bold"
          style={{
            backgroundColor:
              h >= 3 ? "#059669" : h === 2 ? "#0284c7" : h === 1 ? "#1c2433" : "#10151f",
            color: h === 0 ? "#8b98ad" : "#dbe2ef",
            border: h === 0 ? "1px solid #1c2433" : "none",
          }}
        >
          {h}
        </span>
      ))}
    </div>
  );
}
