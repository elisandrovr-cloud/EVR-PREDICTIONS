"use client";

/** Bankroll personal: balance, registro de apuestas y liquidación manual. */
import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { PanelSkeleton } from "@/components/ui/skeleton";
import { post } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { fmtAmerican, fmtMoney } from "@/lib/format";
import { useBankroll, useBets } from "@/lib/queries";
import type { Bet } from "@/lib/types";

export default function BankrollPage() {
  const { isAuthenticated } = useAuth();
  const bankroll = useBankroll(isAuthenticated);
  const bets = useBets(isAuthenticated);
  const queryClient = useQueryClient();

  const [description, setDescription] = useState("");
  const [stake, setStake] = useState("");
  const [odds, setOdds] = useState("");

  const placeBet = useMutation({
    mutationFn: () =>
      post<Bet>("/bankroll/bets", {
        description,
        stake: Number(stake),
        american_odds: Number(odds),
      }),
    onSuccess: () => {
      setDescription("");
      setStake("");
      setOdds("");
      void queryClient.invalidateQueries({ queryKey: ["bets"] });
      void queryClient.invalidateQueries({ queryKey: ["bankroll"] });
    },
  });

  const settle = useMutation({
    mutationFn: ({ id, result }: { id: number; result: string }) =>
      post<Bet>(`/bankroll/bets/${id}/settle/${result}`, {}),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["bets"] });
      void queryClient.invalidateQueries({ queryKey: ["bankroll"] });
    },
  });

  if (!isAuthenticated) {
    return (
      <p className="rounded-md border border-dashed border-terminal-border p-8 text-center text-sm text-terminal-muted">
        Inicia sesión para gestionar tu bankroll.
      </p>
    );
  }

  return (
    <div className="space-y-4">
      <h1 className="font-mono text-sm font-semibold uppercase tracking-widest text-terminal-muted">Bankroll</h1>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle>Balance</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="font-mono text-3xl font-bold text-terminal-green">
              {bankroll.data ? fmtMoney(bankroll.data.balance, bankroll.data.currency) : "—"}
            </div>
            <p className="mt-2 text-[11px] text-terminal-muted">
              Sugerencia del motor: apuesta fraccional de Kelly (25%) mostrada en cada predicción.
            </p>
          </CardContent>
        </Card>
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Registrar apuesta</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-wrap items-end gap-2">
            <div className="min-w-40 flex-1">
              <label className="mb-1 block text-[10px] uppercase text-terminal-muted">Descripción</label>
              <Input value={description} onChange={(e) => setDescription(e.target.value)} placeholder="NYY ML vs BOS" />
            </div>
            <div className="w-28">
              <label className="mb-1 block text-[10px] uppercase text-terminal-muted">Stake</label>
              <Input type="number" value={stake} onChange={(e) => setStake(e.target.value)} placeholder="50" />
            </div>
            <div className="w-28">
              <label className="mb-1 block text-[10px] uppercase text-terminal-muted">Cuota (US)</label>
              <Input type="number" value={odds} onChange={(e) => setOdds(e.target.value)} placeholder="-110" />
            </div>
            <Button
              onClick={() => placeBet.mutate()}
              disabled={!description || !stake || !odds || placeBet.isPending}
            >
              Registrar
            </Button>
            {placeBet.isError && (
              <p className="w-full text-xs text-terminal-red">{(placeBet.error as Error).message}</p>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Historial</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {bets.isLoading ? (
            <PanelSkeleton />
          ) : bets.data && bets.data.length > 0 ? (
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-terminal-border font-mono text-[10px] uppercase tracking-wider text-terminal-muted">
                  <th className="px-4 py-2">Apuesta</th>
                  <th className="px-4 py-2 text-right">Stake</th>
                  <th className="px-4 py-2 text-right">Cuota</th>
                  <th className="px-4 py-2 text-right">Payout</th>
                  <th className="px-4 py-2 text-right">Estado</th>
                </tr>
              </thead>
              <tbody>
                {bets.data.map((b) => (
                  <tr key={b.id} className="border-b border-terminal-border/50 last:border-0">
                    <td className="px-4 py-2 text-terminal-text">{b.description}</td>
                    <td className="px-4 py-2 text-right font-mono">{fmtMoney(b.stake)}</td>
                    <td className="px-4 py-2 text-right font-mono">{fmtAmerican(b.american_odds)}</td>
                    <td className="px-4 py-2 text-right font-mono">{b.payout != null ? fmtMoney(b.payout) : "—"}</td>
                    <td className="px-4 py-2 text-right">
                      {b.status === "open" ? (
                        <span className="flex justify-end gap-1">
                          {["won", "lost", "push"].map((r) => (
                            <Button
                              key={r}
                              size="sm"
                              variant="outline"
                              onClick={() => settle.mutate({ id: b.id, result: r })}
                            >
                              {r}
                            </Button>
                          ))}
                        </span>
                      ) : (
                        <Badge variant={b.status === "won" ? "green" : b.status === "lost" ? "red" : "outline"}>
                          {b.status}
                        </Badge>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="p-8 text-center text-xs text-terminal-muted">Sin apuestas registradas.</p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
