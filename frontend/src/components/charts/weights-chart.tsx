"use client";

/** Ensemble weights per model — magnitude across categories: single hue bars. */
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { CHART_AXIS, CHART_GRID, CHART_SERIES, tooltipStyle } from "@/components/charts/chart-theme";
import type { ModelWeight } from "@/lib/types";

const MODEL_LABELS: Record<string, string> = {
  random_forest: "Random Forest",
  xgboost: "XGBoost",
  lightgbm: "LightGBM",
  catboost: "CatBoost",
  neural_net: "Red Neuronal",
  online_sgd: "SGD Online",
  elo: "ELO",
  monte_carlo: "Monte Carlo",
  stacked: "Stacking",
};

export function WeightsChart({ weights, market }: { weights: ModelWeight[]; market: string }) {
  const rows = weights
    .filter((w) => w.market === market)
    .sort((a, b) => b.weight - a.weight)
    .map((w) => ({
      model: MODEL_LABELS[w.model_name] ?? w.model_name,
      weight: +(w.weight * 100).toFixed(1),
    }));

  if (rows.length === 0) {
    return (
      <p className="px-4 py-8 text-center text-xs text-terminal-muted">
        Pesos aún no calibrados para este mercado — se ajustan tras la primera jornada.
      </p>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={Math.max(180, rows.length * 32)}>
      <BarChart data={rows} layout="vertical" margin={{ top: 4, right: 24, bottom: 0, left: 40 }}>
        <CartesianGrid stroke={CHART_GRID} horizontal={false} />
        <XAxis type="number" stroke={CHART_AXIS} fontSize={10} tickLine={false} axisLine={false} unit="%" />
        <YAxis
          type="category"
          dataKey="model"
          stroke={CHART_AXIS}
          fontSize={11}
          width={92}
          tickLine={false}
          axisLine={false}
        />
        <Tooltip contentStyle={tooltipStyle} formatter={(v) => [`${v}%`, "Peso"]} cursor={{ fill: "#1c243340" }} />
        <Bar dataKey="weight" name="Peso" fill={CHART_SERIES[0]} radius={[0, 4, 4, 0]} barSize={16} />
      </BarChart>
    </ResponsiveContainer>
  );
}
