"use client";

/** React Query hooks — one per API resource, with live polling cadences. */
import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type {
  AgentParlay,
  Bankroll,
  Bet,
  EngineMetric,
  Game,
  HitsBoardRow,
  ModelWeight,
  OddsQuote,
  Parlay,
  PlayerSearchResult,
  PlayerStats,
  Prediction,
  SourceStatus,
  Team,
  User,
} from "@/lib/types";

const LIVE_MS = 60_000; // dashboards poll every minute; backend refreshes every 2

export const useTodayGames = () =>
  useQuery({ queryKey: ["games", "today"], queryFn: () => api<Game[]>("/games/today"), refetchInterval: LIVE_MS });

export const useLiveGames = () =>
  useQuery({ queryKey: ["games", "live"], queryFn: () => api<Game[]>("/games/live"), refetchInterval: 30_000 });

export const useGame = (gamePk: number) =>
  useQuery({ queryKey: ["games", gamePk], queryFn: () => api<Game>(`/games/${gamePk}`), refetchInterval: LIVE_MS });

export const useGameOdds = (gamePk: number) =>
  useQuery({
    queryKey: ["odds", gamePk],
    queryFn: () => api<OddsQuote[]>(`/games/${gamePk}/odds`),
    refetchInterval: LIVE_MS,
  });

export const useTeams = () =>
  useQuery({ queryKey: ["teams"], queryFn: () => api<Team[]>("/games/teams"), staleTime: 600_000 });

export const useDailyPredictions = (market?: string) =>
  useQuery({
    queryKey: ["predictions", "daily", market ?? "all"],
    queryFn: () => api<Prediction[]>(`/predictions/daily${market ? `?market=${market}` : ""}`),
    refetchInterval: LIVE_MS,
  });

export const useTopBoard = (board: string) =>
  useQuery({
    queryKey: ["predictions", "top", board],
    queryFn: () => api<Prediction[]>(`/predictions/top/${board}`),
    refetchInterval: LIVE_MS,
  });

export const useGamePredictions = (gamePk: number) =>
  useQuery({
    queryKey: ["predictions", "game", gamePk],
    queryFn: () => api<Prediction[]>(`/predictions/game/${gamePk}`),
    refetchInterval: LIVE_MS,
  });

export const useParlays = () =>
  useQuery({ queryKey: ["parlays"], queryFn: () => api<Parlay[]>("/parlays/daily"), refetchInterval: LIVE_MS });

export const useHitsBoard = () =>
  useQuery({
    queryKey: ["predictions", "hits-board"],
    queryFn: () => api<HitsBoardRow[]>("/predictions/hits-board"),
    refetchInterval: LIVE_MS,
  });

export const useAgentParlays = () =>
  useQuery({
    queryKey: ["parlays", "agents"],
    queryFn: () => api<AgentParlay[]>("/parlays/agents"),
    refetchInterval: LIVE_MS,
  });

export const useEngineMetrics = (days = 30) =>
  useQuery({
    queryKey: ["stats", "engine", days],
    queryFn: () => api<EngineMetric[]>(`/stats/engine?days=${days}`),
    staleTime: 300_000,
  });

export const useModelWeights = () =>
  useQuery({ queryKey: ["stats", "weights"], queryFn: () => api<ModelWeight[]>("/stats/weights"), staleTime: 300_000 });

export const useMe = (enabled: boolean) =>
  useQuery({ queryKey: ["me"], queryFn: () => api<User>("/auth/me"), enabled, retry: false });

export const useBankroll = (enabled: boolean) =>
  useQuery({ queryKey: ["bankroll"], queryFn: () => api<Bankroll>("/bankroll"), enabled });

export const useBets = (enabled: boolean) =>
  useQuery({ queryKey: ["bets"], queryFn: () => api<Bet[]>("/bankroll/bets"), enabled });

export const usePlayerSearch = (q: string) =>
  useQuery({
    queryKey: ["players", "search", q],
    queryFn: () => api<PlayerSearchResult[]>(`/players/search?q=${encodeURIComponent(q)}`),
    enabled: q.length >= 2,
  });

export const usePlayerStats = (mlbId: number | null) =>
  useQuery({
    queryKey: ["players", mlbId],
    queryFn: () => api<PlayerStats>(`/players/${mlbId}/stats`),
    enabled: mlbId != null,
  });

export const usePlayerPredictions = (mlbId: number | null) =>
  useQuery({
    queryKey: ["predictions", "player", mlbId],
    queryFn: () => api<Prediction[]>(`/predictions/player/${mlbId}`),
    enabled: mlbId != null,
  });

// Admin
export const useAdminUsers = () =>
  useQuery({ queryKey: ["admin", "users"], queryFn: () => api<User[]>("/admin/users") });

export const useAdminSources = () =>
  useQuery({
    queryKey: ["admin", "sources"],
    queryFn: () => api<SourceStatus[]>("/admin/sources"),
    refetchInterval: LIVE_MS,
  });

export const useAdminOverview = () =>
  useQuery({
    queryKey: ["admin", "overview"],
    queryFn: () => api<{ users: number; predictions_today: number; value_bets_today: number }>("/admin/overview"),
  });
