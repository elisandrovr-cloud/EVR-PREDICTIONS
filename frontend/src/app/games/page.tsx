"use client";

import { GameCard } from "@/components/games/game-card";
import { PanelSkeleton } from "@/components/ui/skeleton";
import { useTodayGames } from "@/lib/queries";

export default function GamesPage() {
  const games = useTodayGames();
  return (
    <div>
      <h1 className="mb-4 font-mono text-sm font-semibold uppercase tracking-widest text-terminal-muted">
        Calendario MLB — hoy
      </h1>
      {games.isLoading ? (
        <PanelSkeleton rows={4} />
      ) : games.data && games.data.length > 0 ? (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {games.data.map((g) => (
            <GameCard key={g.game_pk} game={g} />
          ))}
        </div>
      ) : (
        <p className="rounded-md border border-dashed border-terminal-border p-6 text-center text-sm text-terminal-muted">
          Sin juegos hoy. La sincronización con MLB Stats API corre cada 2 minutos.
        </p>
      )}
    </div>
  );
}
