"use client";

/** Panel de administración: usuarios, fuentes de datos, modelos y jobs. */
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { PlayCircle, RefreshCcw } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PanelSkeleton } from "@/components/ui/skeleton";
import { post } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { useAdminOverview, useAdminSources, useAdminUsers, useModelWeights } from "@/lib/queries";

const JOBS = [
  { id: "bootstrap", label: "Bootstrap (equipos + cartelera)" },
  { id: "refresh", label: "Refresh datos" },
  { id: "predict", label: "Regenerar predicciones" },
  { id: "parlays", label: "Reconstruir parlays" },
  { id: "close-day", label: "Cerrar jornada (aprendizaje)" },
];

export default function AdminPage() {
  const { user } = useAuth();
  const overview = useAdminOverview();
  const users = useAdminUsers();
  const sources = useAdminSources();
  const weights = useModelWeights();
  const queryClient = useQueryClient();

  const runJob = useMutation({
    mutationFn: (job: string) => post<{ status: string; task_id: string }>(`/admin/jobs/${job}`, {}),
  });

  if (user && user.role !== "admin") {
    return (
      <p className="rounded-md border border-dashed border-terminal-border p-8 text-center text-sm text-terminal-muted">
        Se requiere rol de administrador.
      </p>
    );
  }

  return (
    <div className="space-y-4">
      <h1 className="font-mono text-sm font-semibold uppercase tracking-widest text-terminal-muted">Panel Admin</h1>

      <div className="grid grid-cols-3 gap-3">
        <Tile label="Usuarios" value={overview.data?.users} />
        <Tile label="Predicciones hoy" value={overview.data?.predictions_today} />
        <Tile label="Value bets hoy" value={overview.data?.value_bets_today} />
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <PlayCircle className="h-3.5 w-3.5" /> Jobs del pipeline
          </CardTitle>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-2">
          {JOBS.map((j) => (
            <Button key={j.id} variant="outline" size="sm" onClick={() => runJob.mutate(j.id)}>
              <RefreshCcw className="h-3 w-3" /> {j.label}
            </Button>
          ))}
          {runJob.isSuccess && (
            <p className="w-full text-xs text-terminal-green">Job encolado: {runJob.data.task_id}</p>
          )}
          {runJob.isError && <p className="w-full text-xs text-terminal-red">{(runJob.error as Error).message}</p>}
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Fuentes de datos</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            {sources.isLoading ? (
              <PanelSkeleton />
            ) : (
              <table className="w-full text-left text-xs">
                <tbody>
                  {(sources.data ?? []).map((s) => (
                    <tr key={s.source} className="border-b border-terminal-border/50 last:border-0">
                      <td className="px-4 py-2 font-mono text-terminal-text">{s.source}</td>
                      <td className="px-4 py-2">
                        <Badge
                          variant={
                            s.status === "ok"
                              ? "green"
                              : s.status === "degraded"
                                ? "amber"
                                : s.status === "down"
                                  ? "red"
                                  : "outline"
                          }
                        >
                          {s.status}
                        </Badge>
                      </td>
                      <td className="px-4 py-2 text-right font-mono text-terminal-muted">
                        {s.latency_ms != null ? `${Math.round(s.latency_ms)} ms` : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Usuarios</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            {users.isLoading ? (
              <PanelSkeleton />
            ) : (
              <table className="w-full text-left text-xs">
                <tbody>
                  {(users.data ?? []).map((u) => (
                    <tr key={u.id} className="border-b border-terminal-border/50 last:border-0">
                      <td className="px-4 py-2 text-terminal-text">{u.email}</td>
                      <td className="px-4 py-2">
                        <Badge variant={u.role === "admin" ? "violet" : "outline"}>{u.role}</Badge>
                      </td>
                      <td className="px-4 py-2 text-right">
                        <Badge variant={u.is_active ? "green" : "red"}>{u.is_active ? "activo" : "inactivo"}</Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Pesos de modelos ({weights.data?.length ?? 0} registros)</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {weights.data && weights.data.length > 0 ? (
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-terminal-border font-mono text-[10px] uppercase text-terminal-muted">
                  <th className="px-4 py-2">Mercado</th>
                  <th className="px-4 py-2">Modelo</th>
                  <th className="px-4 py-2 text-right">Peso</th>
                  <th className="px-4 py-2 text-right">Brier</th>
                  <th className="px-4 py-2 text-right">Muestras</th>
                </tr>
              </thead>
              <tbody>
                {weights.data.map((w) => (
                  <tr key={`${w.market}-${w.model_name}`} className="border-b border-terminal-border/50 last:border-0">
                    <td className="px-4 py-1.5 font-mono text-terminal-muted">{w.market}</td>
                    <td className="px-4 py-1.5 text-terminal-text">{w.model_name}</td>
                    <td className="px-4 py-1.5 text-right font-mono">{(w.weight * 100).toFixed(1)}%</td>
                    <td className="px-4 py-1.5 text-right font-mono">
                      {w.brier_score != null ? w.brier_score.toFixed(3) : "—"}
                    </td>
                    <td className="px-4 py-1.5 text-right font-mono">{w.samples}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="p-6 text-center text-xs text-terminal-muted">
              Los pesos aparecen tras la primera jornada liquidada.
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function Tile({ label, value }: { label: string; value: number | undefined }) {
  return (
    <div className="rounded-lg border border-terminal-border bg-terminal-panel p-3">
      <div className="font-mono text-[10px] uppercase tracking-wider text-terminal-muted">{label}</div>
      <div className="mt-1 font-mono text-2xl font-bold text-terminal-text">{value ?? "—"}</div>
    </div>
  );
}
