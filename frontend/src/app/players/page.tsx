"use client";

/** Base de datos de jugadores: bateadores y lanzadores, con búsqueda, orden y comparación. */
import Link from "next/link";
import { useState } from "react";
import { Search, Users } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { PanelSkeleton } from "@/components/ui/skeleton";
import { Tabs } from "@/components/ui/tabs";
import { usePlayerDirectory } from "@/lib/queries";
import type { PlayerRow } from "@/lib/types";

const KINDS = [
  { id: "batters", label: "Bateadores" },
  { id: "pitchers", label: "Lanzadores" },
];

const SORTS = [
  { id: "name", label: "Nombre" },
  { id: "age", label: "Edad" },
  { id: "team", label: "Equipo" },
];

const PAGE_SIZE = 50;

export default function PlayersPage() {
  const [kind, setKind] = useState("batters");
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState("name");
  const [page, setPage] = useState(0);
  const [compare, setCompare] = useState<PlayerRow[]>([]);

  const directory = usePlayerDirectory({
    kind,
    q: query || undefined,
    sort,
    limit: PAGE_SIZE,
    offset: page * PAGE_SIZE,
  });

  const toggleCompare = (player: PlayerRow) => {
    setCompare((prev) =>
      prev.find((p) => p.mlb_id === player.mlb_id)
        ? prev.filter((p) => p.mlb_id !== player.mlb_id)
        : prev.length >= 4
          ? prev
          : [...prev, player],
    );
  };

  const total = directory.data?.total ?? 0;
  const pages = Math.ceil(total / PAGE_SIZE);

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <Users className="h-5 w-5 text-terminal-accent" />
        <h1 className="text-lg font-bold text-terminal-text">Todos los jugadores</h1>
        <Badge variant="outline">{total} en la base</Badge>
      </div>

      <Tabs
        tabs={KINDS}
        active={kind}
        onChange={(id) => {
          setKind(id);
          setPage(0);
        }}
      />

      <div className="flex flex-wrap items-center gap-2">
        <div className="relative min-w-56 flex-1">
          <Search className="absolute left-3 top-2.5 h-4 w-4 text-terminal-muted" />
          <Input
            className="pl-9"
            placeholder="Buscar por nombre…"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setPage(0);
            }}
          />
        </div>
        <div className="flex gap-1">
          {SORTS.map((s) => (
            <Button
              key={s.id}
              size="sm"
              variant={sort === s.id ? "default" : "outline"}
              onClick={() => setSort(s.id)}
            >
              {s.label}
            </Button>
          ))}
        </div>
      </div>

      {compare.length >= 2 && <CompareStrip players={compare} onClear={() => setCompare([])} />}

      {directory.isLoading ? (
        <PanelSkeleton rows={8} />
      ) : directory.data && directory.data.items.length > 0 ? (
        <>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {directory.data.items.map((p) => (
              <PlayerCard
                key={p.mlb_id}
                player={p}
                selected={!!compare.find((c) => c.mlb_id === p.mlb_id)}
                onToggle={() => toggleCompare(p)}
              />
            ))}
          </div>
          {pages > 1 && (
            <div className="flex items-center justify-center gap-2">
              <Button size="sm" variant="outline" disabled={page === 0} onClick={() => setPage((p) => p - 1)}>
                Anterior
              </Button>
              <span className="font-mono text-xs text-terminal-muted">
                {page + 1} / {pages}
              </span>
              <Button
                size="sm"
                variant="outline"
                disabled={page + 1 >= pages}
                onClick={() => setPage((p) => p + 1)}
              >
                Siguiente
              </Button>
            </div>
          )}
        </>
      ) : (
        <p className="rounded-md border border-dashed border-terminal-border p-8 text-center text-sm text-terminal-muted">
          {query
            ? "Ningún jugador coincide con esa búsqueda."
            : "La base se llena sola: Player Intelligence sincroniza los perfiles oficiales cada minuto."}
        </p>
      )}
    </div>
  );
}

function PlayerCard({
  player,
  selected,
  onToggle,
}: {
  player: PlayerRow;
  selected: boolean;
  onToggle: () => void;
}) {
  return (
    <div
      className={`flex items-center gap-3 rounded-lg border bg-terminal-panel p-3 ${
        selected ? "border-terminal-accent" : "border-terminal-border"
      }`}
    >
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={player.photo_url ?? "https://midfield.mlbstatic.com/v1/people/0/spots/120"}
        alt=""
        className="h-12 w-12 shrink-0 rounded-full bg-terminal-bg object-cover"
        loading="lazy"
      />
      <div className="min-w-0 flex-1">
        <Link href={`/players/${player.mlb_id}`} className="truncate font-medium text-terminal-text hover:text-terminal-accent">
          {player.full_name}
        </Link>
        <div className="truncate text-[11px] text-terminal-muted">
          {player.position ?? "—"} · {player.team ?? "Sin equipo"}
          {player.age ? ` · ${player.age} años` : ""}
        </div>
        {player.roster_status && player.roster_status !== "Active" && (
          <Badge variant={player.roster_status.includes("Injured") ? "red" : "amber"}>
            {player.roster_status}
          </Badge>
        )}
      </div>
      <Button size="sm" variant={selected ? "default" : "ghost"} onClick={onToggle} title="Comparar">
        {selected ? "✓" : "+"}
      </Button>
    </div>
  );
}

function CompareStrip({ players, onClear }: { players: PlayerRow[]; onClear: () => void }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Comparando {players.length} jugadores</CardTitle>
        <Button size="sm" variant="ghost" onClick={onClear}>
          Limpiar
        </Button>
      </CardHeader>
      <CardContent className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="font-mono text-[10px] uppercase text-terminal-muted">
              <th className="py-1">Jugador</th>
              <th className="py-1">Equipo</th>
              <th className="py-1">Pos</th>
              <th className="py-1">Edad</th>
              <th className="py-1">Estado</th>
            </tr>
          </thead>
          <tbody>
            {players.map((p) => (
              <tr key={p.mlb_id} className="border-t border-terminal-border/50">
                <td className="py-1.5">
                  <Link href={`/players/${p.mlb_id}`} className="text-terminal-accent hover:underline">
                    {p.full_name}
                  </Link>
                </td>
                <td className="py-1.5 text-terminal-muted">{p.team ?? "—"}</td>
                <td className="py-1.5 text-terminal-muted">{p.position ?? "—"}</td>
                <td className="py-1.5 text-terminal-muted">{p.age ?? "—"}</td>
                <td className="py-1.5 text-terminal-muted">{p.roster_status ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </CardContent>
    </Card>
  );
}
