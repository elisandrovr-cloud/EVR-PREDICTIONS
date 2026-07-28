"use client";

/** Chat con el Supervisor AI: enruta la pregunta a los agentes y responde justificando. */
import { useEffect, useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Bot, Send, User } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { post } from "@/lib/api";
import { fmtPct } from "@/lib/format";
import type { ChatAnswer } from "@/lib/types";

const SUGGESTIONS = [
  "Dame un parlay de 3 picks",
  "Dame los mejores hits",
  "Dame los mejores ponches",
  "Dame los mejores moneyline",
  "¿Qué jugador tiene más valor hoy?",
  "¿Hay noticias de lesiones?",
];

interface Turn {
  role: "user" | "assistant";
  text: string;
  answer?: ChatAnswer;
}

export default function ChatPage() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const endRef = useRef<HTMLDivElement>(null);

  const ask = useMutation({
    mutationFn: (question: string) => post<ChatAnswer>("/agents/chat", { question }),
    onSuccess: (data) => {
      setTurns((prev) => [...prev, { role: "assistant", text: data.answer, answer: data }]);
    },
    onError: (error) => {
      setTurns((prev) => [
        ...prev,
        { role: "assistant", text: `No pude responder: ${(error as Error).message}` },
      ]);
    },
  });

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns]);

  const send = (question: string) => {
    const text = question.trim();
    if (!text || ask.isPending) return;
    setTurns((prev) => [...prev, { role: "user", text }]);
    setInput("");
    ask.mutate(text);
  };

  return (
    <div className="mx-auto flex h-[calc(100vh-7rem)] max-w-3xl flex-col">
      <div className="mb-3">
        <h1 className="flex items-center gap-2 text-lg font-bold text-terminal-text">
          <Bot className="h-5 w-5 text-terminal-accent" /> Pregúntale al Supervisor
        </h1>
        <p className="text-xs text-terminal-muted">
          Tu pregunta se reparte entre los 8 agentes; el Supervisor junta sus análisis y te da una
          sola respuesta explicada.
        </p>
      </div>

      <div className="flex-1 space-y-3 overflow-y-auto rounded-xl border border-terminal-border bg-terminal-panel p-4">
        {turns.length === 0 && (
          <div className="space-y-3">
            <p className="text-sm text-terminal-muted">Prueba con una de estas:</p>
            <div className="flex flex-wrap gap-2">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  onClick={() => send(s)}
                  className="rounded-full border border-terminal-border px-3 py-1.5 text-xs text-terminal-text transition-colors hover:border-terminal-accent hover:text-terminal-accent"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {turns.map((turn, i) => (
          <div key={i} className={`flex gap-2.5 ${turn.role === "user" ? "justify-end" : ""}`}>
            {turn.role === "assistant" && (
              <span className="mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-terminal-accent/15">
                <Bot className="h-4 w-4 text-terminal-accent" />
              </span>
            )}
            <div
              className={`max-w-[85%] rounded-xl px-3.5 py-2.5 text-sm ${
                turn.role === "user"
                  ? "bg-terminal-accent text-terminal-bg"
                  : "bg-terminal-bg text-terminal-text"
              }`}
            >
              {turn.role === "assistant" ? (
                <AssistantBubble turn={turn} />
              ) : (
                turn.text
              )}
            </div>
            {turn.role === "user" && (
              <span className="mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-terminal-border">
                <User className="h-4 w-4 text-terminal-muted" />
              </span>
            )}
          </div>
        ))}

        {ask.isPending && (
          <div className="flex items-center gap-2 text-xs text-terminal-muted">
            <Bot className="h-4 w-4 animate-pulse text-terminal-accent" />
            Consultando a los agentes…
          </div>
        )}
        <div ref={endRef} />
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          send(input);
        }}
        className="mt-3 flex gap-2"
      >
        <Input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ej.: dame un parlay de 5 picks solo de hits"
          disabled={ask.isPending}
        />
        <Button type="submit" disabled={ask.isPending || !input.trim()}>
          <Send className="h-4 w-4" />
        </Button>
      </form>
    </div>
  );
}

/** Renders the Supervisor's markdown-ish answer plus its agent metadata. */
function AssistantBubble({ turn }: { turn: Turn }) {
  const answer = turn.answer;
  return (
    <div className="space-y-2">
      <div className="space-y-1 leading-relaxed">
        {turn.text.split("\n").map((line, i) => {
          const trimmed = line.trim();
          if (!trimmed) return <div key={i} className="h-1" />;
          if (trimmed.startsWith("**") && trimmed.includes("**")) {
            const clean = trimmed.replace(/\*\*/g, "");
            return (
              <div key={i} className="pt-1 font-semibold text-terminal-accent">
                {clean}
              </div>
            );
          }
          if (trimmed.startsWith("•")) {
            return (
              <div key={i} className="pl-3 text-terminal-muted">
                {trimmed}
              </div>
            );
          }
          if (trimmed.startsWith("_") && trimmed.endsWith("_")) {
            return (
              <div key={i} className="pt-1 text-[11px] italic text-terminal-muted/80">
                {trimmed.replace(/_/g, "")}
              </div>
            );
          }
          return <div key={i}>{trimmed}</div>;
        })}
      </div>
      {answer && answer.agents_consulted.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5 border-t border-terminal-border/60 pt-2">
          <span className="text-[10px] uppercase tracking-wider text-terminal-muted">Agentes:</span>
          {answer.agents_consulted.map((a) => (
            <Badge key={a} variant="outline">
              {a.replace("_intelligence", "").replace("_", " ")}
            </Badge>
          ))}
          <Badge variant={answer.confidence >= 0.6 ? "green" : "amber"}>
            confianza {fmtPct(answer.confidence, 0)}
          </Badge>
        </div>
      )}
    </div>
  );
}
