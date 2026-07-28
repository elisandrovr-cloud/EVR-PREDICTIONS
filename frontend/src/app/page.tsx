"use client";

/** Inicio en "modo fácil": explica qué apostar hoy en lenguaje para principiantes. */
import Link from "next/link";
import { ArrowRight, Bot, Layers, MessageSquare, Sparkles, Target } from "lucide-react";

import { PickCard } from "@/components/simple/pick-card";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PanelSkeleton } from "@/components/ui/skeleton";
import { fmtPct } from "@/lib/format";
import { outOfTen } from "@/lib/plain";
import { useAgentParlays, useDailyPredictions, useHitsBoard, useLastCycle } from "@/lib/queries";

const CATEGORY_LABELS: Record<string, string> = {
  hits: "Solo Hits",
  strikeouts: "Solo Ponches",
  games: "Solo Juegos",
  mixed: "Mixto (de todo)",
};

export default function HomePage() {
  const preds = useDailyPredictions();
  const hits = useHitsBoard();
  const agents = useAgentParlays();
  const lastCycle = useLastCycle();

  const safest = [...(preds.data ?? [])]
    .filter((p) => p.probability >= 0.55)
    .sort((a, b) => b.probability * b.confidence - a.probability * a.confidence)
    .slice(0, 6);

  const bestParlay = pickBestParlay(agents.data);

  return (
    <div className="space-y-6">
      {/* Encabezado amistoso */}
      <div className="rounded-xl border border-terminal-border bg-gradient-to-br from-terminal-panel to-terminal-bg p-5">
        <div className="flex items-center gap-2">
          <Sparkles className="h-5 w-5 text-terminal-accent" />
          <h1 className="text-xl font-bold text-terminal-text">Tus apuestas de hoy</h1>
        </div>
        <p className="mt-1 max-w-2xl text-sm text-terminal-muted">
          La computadora analizó todos los juegos de hoy y eligió las apuestas con más chance de ganar.
          No necesitas saber de béisbol: cada tarjeta te dice <b className="text-terminal-text">qué apostar</b>,{" "}
          <b className="text-terminal-text">qué tan segura es</b> y <b className="text-terminal-text">cuánto podrías ganar</b>.
        </p>
        <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-3">
          <HowStep n={1} text="Mira las tarjetas verdes: son las más seguras." />
          <HowStep n={2} text="Más estrellas ⭐ = más chance de ganar." />
          <HowStep n={3} text="Empieza con apuestas pequeñas." />
        </div>
      </div>

      {/* Las apuestas más seguras */}
      <section>
        <SectionTitle icon={Target} title="Las 6 apuestas más seguras de hoy" href="/predictions" hrefLabel="Ver todas" />
        {preds.isLoading ? (
          <PanelSkeleton rows={3} />
        ) : safest.length > 0 ? (
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
            {safest.map((p) => (
              <PickCard key={p.id} pred={p} />
            ))}
          </div>
        ) : (
          <Waiting text="Preparando las apuestas del día… Esto se llena solo en 1–2 minutos. Deja la página abierta." />
        )}
      </section>

      {/* Combinada recomendada */}
      {bestParlay && (
        <section>
          <SectionTitle icon={Layers} title="Combinada recomendada (más ganancia)" href="/agents" hrefLabel="Ver todas" />
          <Card>
            <CardHeader>
              <CardTitle>
                {CATEGORY_LABELS[bestParlay.category] ?? bestParlay.category} · {bestParlay.style === "safe" ? "Segura" : "Arriesgada"}
              </CardTitle>
              <Badge variant="amber">👑 {bestParlay.winning_agent}</Badge>
            </CardHeader>
            <CardContent className="space-y-2">
              <p className="text-sm text-terminal-muted">
                Junta {bestParlay.legs.length} apuestas. Si <b className="text-terminal-text">TODAS</b> aciertan,
                pagas poco y ganas mucho — pero es más difícil. Acierta {fmtPct(bestParlay.combined_probability)} de las veces.
              </p>
              <ol className="space-y-1">
                {bestParlay.legs.map((leg, i) => (
                  <li key={i} className="flex items-center gap-2 rounded-md bg-terminal-bg px-2.5 py-1.5 text-sm">
                    <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-terminal-border text-[10px] font-bold">
                      {i + 1}
                    </span>
                    <span className="text-terminal-text">{leg.selection}</span>
                    <span className="ml-auto text-xs text-terminal-muted">{fmtPct(leg.probability)}</span>
                  </li>
                ))}
              </ol>
              <div className="rounded-lg bg-terminal-bg p-2.5 text-sm text-terminal-text">
                💵 Apuestas $10 → ganas ${((bestParlay.combined_decimal_odds - 1) * 10).toFixed(0)}
              </div>
            </CardContent>
          </Card>
        </section>
      )}

      {/* Hits más probables */}
      <section>
        <SectionTitle icon={Target} title="¿Quién va a pegar hit hoy?" href="/predictions" hrefLabel="Ver tabla" />
        {hits.isLoading ? (
          <PanelSkeleton rows={2} />
        ) : hits.data && hits.data.length > 0 ? (
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {hits.data.slice(0, 6).map((h, i) => (
              <div key={`${h.player_mlb_id}-${i}`} className="flex items-center justify-between rounded-lg border border-terminal-border bg-terminal-panel px-3 py-2">
                <div>
                  <div className="text-sm font-medium text-terminal-text">{h.player}</div>
                  <div className="text-[11px] text-terminal-muted">Pega hit {outOfTen(h.probability)}</div>
                </div>
                <div className="text-right">
                  <div className="font-mono text-lg font-bold text-terminal-accent">{fmtPct(h.probability, 0)}</div>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <Waiting text="Cargando bateadores del día… aparecen solos en un par de minutos." />
        )}
      </section>

      {/* Atajos: chat y agentes */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Link
          href="/chat"
          className="flex items-center justify-between rounded-xl border border-terminal-border bg-terminal-panel p-4 hover:border-terminal-accent/50"
        >
          <div className="flex items-center gap-3">
            <MessageSquare className="h-5 w-5 text-terminal-accent" />
            <div>
              <div className="font-semibold text-terminal-text">Pregúntale a la IA</div>
              <div className="text-xs text-terminal-muted">
                «Dame un parlay de 5 picks» · «los mejores hits»
              </div>
            </div>
          </div>
          <ArrowRight className="h-5 w-5 text-terminal-muted" />
        </Link>
        <Link
          href="/agents"
          className="flex items-center justify-between rounded-xl border border-terminal-border bg-terminal-panel p-4 hover:border-terminal-accent/50"
        >
          <div className="flex items-center gap-3">
            <Bot className="h-5 w-5 text-terminal-accent" />
            <div>
              <div className="font-semibold text-terminal-text">8 agentes trabajando 24/7</div>
              <div className="text-xs text-terminal-muted">
                {lastCycle.data?.started_at
                  ? `Última revisión: ${new Date(lastCycle.data.started_at).toLocaleTimeString()}`
                  : "Rosters, lineups, lesiones y cuotas"}
              </div>
            </div>
          </div>
          <ArrowRight className="h-5 w-5 text-terminal-muted" />
        </Link>
      </div>
    </div>
  );
}

function pickBestParlay(list: ReturnType<typeof useAgentParlays>["data"]) {
  if (!list || list.length === 0) return null;
  // prefer a "safe" parlay with the highest chance of cashing
  const safe = list.filter((p) => p.style === "safe").sort((a, b) => b.combined_probability - a.combined_probability);
  return (safe[0] ?? list[0]) || null;
}

function HowStep({ n, text }: { n: number; text: string }) {
  return (
    <div className="flex items-center gap-2 rounded-lg bg-terminal-bg px-3 py-2">
      <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-terminal-accent text-xs font-bold text-terminal-bg">
        {n}
      </span>
      <span className="text-xs text-terminal-text">{text}</span>
    </div>
  );
}

function SectionTitle({
  icon: Icon,
  title,
  href,
  hrefLabel,
}: {
  icon: typeof Target;
  title: string;
  href: string;
  hrefLabel: string;
}) {
  return (
    <div className="mb-2 flex items-center justify-between">
      <h2 className="flex items-center gap-2 text-sm font-bold text-terminal-text">
        <Icon className="h-4 w-4 text-terminal-accent" />
        {title}
      </h2>
      <Link href={href} className="flex items-center gap-1 text-xs text-terminal-accent hover:underline">
        {hrefLabel} <ArrowRight className="h-3 w-3" />
      </Link>
    </div>
  );
}

function Waiting({ text }: { text: string }) {
  return (
    <div className="flex items-center gap-3 rounded-xl border border-dashed border-terminal-border p-5">
      <span className="relative flex h-2.5 w-2.5">
        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-terminal-accent opacity-60" />
        <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-terminal-accent" />
      </span>
      <p className="text-sm text-terminal-muted">{text}</p>
    </div>
  );
}
