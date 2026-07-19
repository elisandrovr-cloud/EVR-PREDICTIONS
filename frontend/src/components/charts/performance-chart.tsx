"use client";

/** Engine accuracy & ROI history — two aligned single-axis charts (never dual-axis). */
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { CHART_AXIS, CHART_GRID, CHART_SERIES, tooltipStyle } from "@/components/charts/chart-theme";
import { fmtDate } from "@/lib/format";
import type { EngineMetric } from "@/lib/types";

export function PerformanceChart({ metrics }: { metrics: EngineMetric[] }) {
  const data = metrics.map((m) => ({
    date: fmtDate(m.metric_date),
    winRate: m.wins + m.losses > 0 ? +((m.wins / (m.wins + m.losses)) * 100).toFixed(1) : null,
    roi: m.roi != null ? +(m.roi * 100).toFixed(1) : null,
  }));

  if (data.length === 0) {
    return (
      <p className="px-4 py-8 text-center text-xs text-terminal-muted">
        Sin histórico todavía — el motor registra métricas tras cada jornada liquidada.
      </p>
    );
  }

  return (
    <div className="space-y-4">
      <ChartBlock title="Win rate (%)" color={CHART_SERIES[0]}>
        <ResponsiveContainer width="100%" height={140}>
          <LineChart data={data} margin={{ top: 6, right: 12, bottom: 0, left: -18 }}>
            <CartesianGrid stroke={CHART_GRID} strokeDasharray="0" vertical={false} />
            <XAxis dataKey="date" stroke={CHART_AXIS} fontSize={10} tickLine={false} axisLine={false} />
            <YAxis stroke={CHART_AXIS} fontSize={10} tickLine={false} axisLine={false} domain={[0, 100]} />
            <Tooltip contentStyle={tooltipStyle} />
            <Line
              type="monotone"
              dataKey="winRate"
              name="Win rate"
              stroke={CHART_SERIES[0]}
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4 }}
              connectNulls
            />
          </LineChart>
        </ResponsiveContainer>
      </ChartBlock>
      <ChartBlock title="ROI (%)" color={CHART_SERIES[1]}>
        <ResponsiveContainer width="100%" height={140}>
          <LineChart data={data} margin={{ top: 6, right: 12, bottom: 0, left: -18 }}>
            <CartesianGrid stroke={CHART_GRID} vertical={false} />
            <XAxis dataKey="date" stroke={CHART_AXIS} fontSize={10} tickLine={false} axisLine={false} />
            <YAxis stroke={CHART_AXIS} fontSize={10} tickLine={false} axisLine={false} />
            <Tooltip contentStyle={tooltipStyle} />
            <Line
              type="monotone"
              dataKey="roi"
              name="ROI"
              stroke={CHART_SERIES[1]}
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4 }}
              connectNulls
            />
          </LineChart>
        </ResponsiveContainer>
      </ChartBlock>
    </div>
  );
}

function ChartBlock({
  title,
  color,
  children,
}: {
  title: string;
  color: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <div className="mb-1 flex items-center gap-1.5 px-1">
        <span className="h-2 w-2 rounded-full" style={{ backgroundColor: color }} />
        <span className="font-mono text-[10px] uppercase tracking-wider text-terminal-muted">{title}</span>
      </div>
      {children}
    </div>
  );
}
