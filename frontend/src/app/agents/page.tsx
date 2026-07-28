"use client";

/** Centro de control multi-agente: estado de los 8 agentes, ciclo de monitoreo,
 * cambios detectados, noticias y las combinadas del comité de parlays. */
import { useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Bot, Clock, Crown, Newspaper, RefreshCw, Swords } from "lucide-react";

import { Badge, riskBadgeVariant } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PanelSkeleton } from "@/components/ui/skeleton";
import { Tabs } from "@/components/ui/tabs";
import { post } from "@/lib/api";
import { fmtAmerican, fmtEv, fmtPct, MARKET_LABELS } from "@/lib/format";
import {
  useAgentParlays,
  useAgentStatus,
  useChanges,
  useLastCycle,
  useNews,
} from "@/lib/queries";
import type { AgentParlay, AgentStatus } from "@/lib/types";

const CATEGORIES = [
  { id: "hits", label: "Solo Hits" },
  { id: "strikeouts", label: "Solo Ponches" },
  { id: "games", label: "Solo Juegos" },
  { id: "mixed", label: "Mixto" },
];

export default function AgentsPage() {
  const agents = useAgentStatus();
  const cycle = useLastCycle();
  const changes = useChanges(20);
  const news = useNews(12);
  const parlays = useAgentParlays();
  const [category, setCategory] = useState("hits");
  const queryClient = useQueryClient();

  const refresh = useMutation({
    mutationFn: () => post<{ conclusion: string }>("/agents/refresh", {}),
    onSuccess: () => {
      void queryClient.invalidateQueries();
    },
  });

  const byCategory = useMemo(() => {
    const map: Record<string, AgentParlay[]> = {};
    for (const p of parlays.data ?? []) (map[p.category] ??= []).push(p);
    for (const list of Object.values(map)) list.sort((a) => (a.style === "safe" ? -1 : 1));
    return map;
  }, [parlays.data]);

  return (
    <div className="space-y-4">
      {/* Encabezado + ACTUALIZAR AHORA */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-terminal-border bg-terminal-panel p-4">
        <div>
          <h1 className="flex items-center gap-2 text-lg font-bold text-terminal-text">
            <Bot className="h-5 w-5 text-terminal-accent" /> Equipo de Agentes IA
          </h1>
          <p className="mt-0.5 flex items-center gap-1.5 text-xs text-terminal-muted">
            <Clock className="h-3.5 w-3.5" />
            {cycle.data?.started_at
              ? `Última actualización: ${new Date(cycle.data.started_at).toLocaleString()}`
              : "Esperando el primer ciclo de monitoreo…"}
          </p>
          {cycle.data?.conclusion && (
            <p className="mt-1 text-xs text-terminal-text">{cycle.data.conclusion}</p>
          )}
        </div>
        <Button onClick={() => refresh.mutate()} disabled={refresh.isPending}>
          <RefreshCw className={`h-4 w-4 ${refresh.isPending ? "animate-spin" : ""}`} />
          {refresh.isPending ? "Actualizando…" : "ACTUALIZAR AHORA"}
        </Button>
      </div>
      {refresh.isError && (
        <p className="text-xs text-terminal-red">{(refresh.error as Error).message}</p>
      )}

      {/* Estado de los 8 agentes */}
      <section>
        <h2 className="mb-2 font-mono text-xs font-semibold uppercase tracking-widest text-terminal-muted">
          Los 8 agentes especializados
        </h2>
        {agents.isLoading ? (
          <PanelSkeleton rows={4} />
        ) : (
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-4">
            {(agents.data ?? []).map((a) => (
              <AgentCard key={a.name} agent={a} />
            ))}
          </div>
        )}
      </section>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* Cambios detectados */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <AlertTriangle className="h-3.5 w-3.5 text-terminal-amber" /> Cambios detectados
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            {changes.isLoading ? (
              <PanelSkeleton rows={4} />
            ) : changes.data && changes.data.length > 0 ? (
              <ul className="max-h-80 overflow-y-auto">
                {changes.data.map((c) => (
                  <li key={c.id} className="border-b border-terminal-border/50 px-4 py-2 last:border-0">
                    <div className="flex items-start justify-between gap-2">
                      <span className="text-sm text-terminal-text">{c.detail}</span>
                      <Badge
                        variant={
                          c.severity === "critical" ? "red" : c.severity === "warning" ? "amber" : "outline"
                        }
                      >
                        {c.change_type}
                      </Badge>
                    </div>
                    <div className="mt-0.5 font-mono text-[10px] text-terminal-muted">
                      {new Date(c.detected_at).toLocaleString()} · {c.detected_by}
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="p-6 text-center text-xs text-terminal-muted">
                Sin movimientos detectados todavía. El monitoreo corre cada minuto.
              </p>
            )}
          </CardContent>
        </Card>

        {/* Noticias */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Newspaper className="h-3.5 w-3.5 text-terminal-accent" /> Noticias y lesiones
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            {news.isLoading ? (
              <PanelSkeleton rows={4} />
            ) : news.data && news.data.length > 0 ? (
              <ul className="max-h-80 overflow-y-auto">
                {news.data.map((n) => (
                  <li key={n.id} className="border-b border-terminal-border/50 px-4 py-2 last:border-0">
                    <div className="flex items-center gap-2">
                      <Badge variant={n.category === "injury" ? "red" : "outline"}>{n.category}</Badge>
                      <span className="text-sm font-medium text-terminal-text">{n.headline}</span>
                    </div>
                    <p className="mt-0.5 text-xs text-terminal-muted">{n.body}</p>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="p-6 text-center text-xs text-terminal-muted">
                Sin noticias oficiales registradas.
              </p>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Comité de parlays */}
      <section>
        <h2 className="mb-2 flex items-center gap-2 font-mono text-xs font-semibold uppercase tracking-widest text-terminal-muted">
          <Swords className="h-3.5 w-3.5" /> Comité de parlays — el debate del día
        </h2>
        <Tabs tabs={CATEGORIES} active={category} onChange={setCategory} />
        <div className="mt-3 grid grid-cols-1 gap-4 lg:grid-cols-2">
          {(byCategory[category] ?? []).map((p) => (
            <ParlayCard key={p.id} parlay={p} />
          ))}
          {(byCategory[category] ?? []).length === 0 && (
            <p className="rounded-md border border-dashed border-terminal-border p-6 text-center text-xs text-terminal-muted lg:col-span-2">
              Aún no hay combinada de esta categoría. Se arma cuando los agentes tienen datos suficientes.
            </p>
          )}
        </div>
      </section>
    </div>
  );
}

function AgentCard({ agent }: { agent: AgentStatus }) {
  const tone =
    agent.status === "ok" ? "green" : agent.status === "error" ? "red" : "outline";
  return (
    <div className="rounded-lg border border-terminal-border bg-terminal-panel p-3">
      <div className="flex items-start justify-between gap-2">
        <span className="text-sm font-semibold text-terminal-text">{agent.title}</span>
        <Badge variant={tone}>{agent.status}</Badge>
      </div>
      <p className="mt-1 text-[11px] leading-relaxed text-terminal-muted">{agent.description}</p>
      <p className="mt-2 text-xs text-terminal-text">{agent.summary}</p>
      <div className="mt-2 flex items-center justify-between font-mono text-[10px] text-terminal-muted">
        <span>{agent.items_processed} procesados</span>
        {agent.duration_ms != null && <span>{Math.round(agent.duration_ms)} ms</span>}
      </div>
    </div>
  );
}

function ParlayCard({ parlay }: { parlay: AgentParlay }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{parlay.style === "safe" ? "Segura" : "Agresiva"}</CardTitle>
        <div className="flex items-center gap-2">
          <Badge variant={riskBadgeVariant(parlay.risk)}>{parlay.risk}</Badge>
          <Badge variant="amber">
            <Crown className="mr-1 inline h-3 w-3" />
            {parlay.winning_agent}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-2">
        <div className="grid grid-cols-3 gap-2 rounded-md bg-terminal-bg p-2 text-center font-mono text-xs">
          <div>
            <div className="text-[9px] uppercase text-terminal-muted">Acierto</div>
            <div className="text-sm font-bold text-terminal-accent">
              {fmtPct(parlay.combined_probability)}
            </div>
          </div>
          <div>
            <div className="text-[9px] uppercase text-terminal-muted">Cuota</div>
            <div className="text-sm font-bold">x{parlay.combined_decimal_odds.toFixed(2)}</div>
          </div>
          <div>
            <div className="text-[9px] uppercase text-terminal-muted">EV</div>
            <div className="text-sm font-bold">{fmtEv(parlay.expected_value)}</div>
          </div>
        </div>
        <ol className="space-y-1">
          {parlay.legs.map((leg, i) => (
            <li key={i} className="flex items-center justify-between gap-2 rounded border border-terminal-border/60 px-2 py-1.5 text-sm">
              <span className="truncate text-terminal-text">{leg.selection}</span>
              <span className="flex shrink-0 items-center gap-2 font-mono text-[11px] text-terminal-muted">
                <Badge variant="outline">{MARKET_LABELS[leg.market] ?? leg.market}</Badge>
                {fmtPct(leg.probability)} · {fmtAmerican(leg.book_odds ?? leg.fair_odds)}
              </span>
            </li>
          ))}
        </ol>
        {parlay.debate.length > 0 && (
          <details className="rounded-md bg-terminal-bg p-2">
            <summary className="cursor-pointer font-mono text-[10px] uppercase tracking-wider text-terminal-muted">
              Ver el debate ({parlay.debate.length} agentes)
            </summary>
            <div className="mt-2 space-y-1.5">
              {parlay.debate.map((d) => (
                <div key={d.agent} className={`text-xs ${d.won ? "text-terminal-text" : "text-terminal-muted"}`}>
                  <span className="font-semibold">
                    {d.won && "👑 "}
                    {d.agent}:
                  </span>{" "}
                  {d.argument}
                </div>
              ))}
            </div>
          </details>
        )}
      </CardContent>
    </Card>
  );
}
