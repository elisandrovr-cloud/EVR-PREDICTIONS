"use client";

/** Motor IA: histórico de rendimiento + pesos del ensemble por mercado. */
import { useState } from "react";

import { PerformanceChart } from "@/components/charts/performance-chart";
import { WeightsChart } from "@/components/charts/weights-chart";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PanelSkeleton } from "@/components/ui/skeleton";
import { Tabs } from "@/components/ui/tabs";
import { useEngineMetrics, useModelWeights } from "@/lib/queries";

const MARKET_TABS = [
  { id: "moneyline", label: "Moneyline" },
  { id: "run_line", label: "Run Line" },
  { id: "total_over", label: "Totales" },
  { id: "first_inning", label: "1er Inning" },
];

export default function StatsPage() {
  const metrics = useEngineMetrics(60);
  const weights = useModelWeights();
  const [market, setMarket] = useState("moneyline");

  return (
    <div className="space-y-4">
      <h1 className="font-mono text-sm font-semibold uppercase tracking-widest text-terminal-muted">
        EVR Prediction Engine — estado del motor
      </h1>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Rendimiento (60 días)</CardTitle>
          </CardHeader>
          <CardContent>
            {metrics.isLoading ? <PanelSkeleton rows={4} /> : <PerformanceChart metrics={metrics.data ?? []} />}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Pesos del ensemble (recalibración bayesiana diaria)</CardTitle>
          </CardHeader>
          <Tabs className="px-4" tabs={MARKET_TABS} active={market} onChange={setMarket} />
          <CardContent>
            {weights.isLoading ? (
              <PanelSkeleton rows={4} />
            ) : (
              <WeightsChart weights={weights.data ?? []} market={market} />
            )}
          </CardContent>
        </Card>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Cómo aprende</CardTitle>
        </CardHeader>
        <CardContent className="grid grid-cols-1 gap-4 text-xs leading-relaxed text-terminal-muted md:grid-cols-3">
          <div>
            <div className="mb-1 font-semibold text-terminal-text">1 · Liquidación automática</div>
            Al cerrar la jornada, el motor descarga resultados y boxscores oficiales y califica cada predicción
            (win / loss / push) sin intervención humana.
          </div>
          <div>
            <div className="mb-1 font-semibold text-terminal-text">2 · Recalibración bayesiana</div>
            Cada modelo del ensemble (Random Forest, XGBoost, LightGBM, CatBoost, red neuronal, SGD online, ELO,
            Monte Carlo) recibe un peso nuevo según su log-loss real, con actualización multiplicativa.
          </div>
          <div>
            <div className="mb-1 font-semibold text-terminal-text">3 · Reentrenamiento</div>
            El zoo de modelos se reentrena con el histórico acumulado de features → resultados, el miembro online
            hace partial-fit diario y el ELO de los 30 equipos se actualiza con los marcadores finales.
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
