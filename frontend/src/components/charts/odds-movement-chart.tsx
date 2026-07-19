"use client";

/** Line-movement chart: implied probability over time, one line per book (max 4,
 * fixed categorical order, legend + direct tooltip identity). */
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { CHART_AXIS, CHART_GRID, CHART_SERIES, tooltipStyle } from "@/components/charts/chart-theme";
import type { OddsQuote } from "@/lib/types";

export function OddsMovementChart({ quotes, selection }: { quotes: OddsQuote[]; selection: string }) {
  const filtered = quotes
    .filter((q) => q.selection === selection)
    .sort((a, b) => a.captured_at.localeCompare(b.captured_at));

  const books = [...new Set(filtered.map((q) => q.book))].slice(0, 4);
  const byTime = new Map<string, Record<string, number | string>>();
  for (const q of filtered) {
    if (!books.includes(q.book)) continue;
    const t = new Date(q.captured_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    const row = byTime.get(t) ?? { time: t };
    row[q.book] = +(q.implied_prob * 100).toFixed(1);
    byTime.set(t, row);
  }
  const data = [...byTime.values()];

  if (data.length < 2) {
    return (
      <p className="px-4 py-6 text-center text-xs text-terminal-muted">
        Se necesitan más capturas de cuotas para graficar el movimiento.
      </p>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={200}>
      <LineChart data={data} margin={{ top: 6, right: 12, bottom: 0, left: -14 }}>
        <CartesianGrid stroke={CHART_GRID} vertical={false} />
        <XAxis dataKey="time" stroke={CHART_AXIS} fontSize={10} tickLine={false} axisLine={false} />
        <YAxis stroke={CHART_AXIS} fontSize={10} tickLine={false} axisLine={false} unit="%" />
        <Tooltip contentStyle={tooltipStyle} />
        <Legend wrapperStyle={{ fontSize: 11 }} />
        {books.map((book, i) => (
          <Line
            key={book}
            type="stepAfter"
            dataKey={book}
            stroke={CHART_SERIES[i]}
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4 }}
            connectNulls
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}
