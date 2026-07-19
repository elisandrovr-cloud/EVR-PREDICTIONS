"use client";

/** Tableros Top-N por mercado + listado completo del día. */
import { useState } from "react";

import { HitsBoard } from "@/components/predictions/hits-board";
import { PredictionRow } from "@/components/predictions/prediction-row";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PanelSkeleton } from "@/components/ui/skeleton";
import { Tabs } from "@/components/ui/tabs";
import { useTopBoard } from "@/lib/queries";

const BOARDS = [
  { id: "value-bets", label: "Value Bets" },
  { id: "moneyline", label: "Moneyline" },
  { id: "run-line", label: "Run Line" },
  { id: "over", label: "Over" },
  { id: "under", label: "Under" },
  { id: "hits", label: "Hits" },
  { id: "home-runs", label: "HR" },
  { id: "rbi", label: "RBI" },
  { id: "strikeouts", label: "K" },
  { id: "total-bases", label: "Bases" },
  { id: "stolen-bases", label: "Robos" },
  { id: "first-inning", label: "1er Inning" },
  { id: "upsets", label: "Upsets" },
];

export default function PredictionsPage() {
  const [board, setBoard] = useState("value-bets");
  const preds = useTopBoard(board);

  return (
    <div className="space-y-4">
      <h1 className="font-mono text-sm font-semibold uppercase tracking-widest text-terminal-muted">
        Predicciones del día
      </h1>
      <Card>
        <CardHeader>
          <CardTitle>
            {board === "hits" ? "Probabilidad de hit — todos los bateadores de hoy" : `Top ${BOARDS.find((b) => b.id === board)?.label}`}
          </CardTitle>
        </CardHeader>
        <Tabs className="px-4" tabs={BOARDS} active={board} onChange={setBoard} />
        <CardContent className="p-0">
          {board === "hits" ? (
            <HitsBoard />
          ) : preds.isLoading ? (
            <PanelSkeleton rows={6} />
          ) : preds.data && preds.data.length > 0 ? (
            preds.data.map((p) => <PredictionRow key={p.id} pred={p} />)
          ) : (
            <p className="p-8 text-center text-xs text-terminal-muted">
              Este tablero se llena automáticamente cuando el motor corre sobre la cartelera del día.
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
