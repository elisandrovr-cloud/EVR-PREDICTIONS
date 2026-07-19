/** Plain-language helpers — turn betting jargon into words anyone understands. */
import type { Prediction } from "@/lib/types";

/** A short, human title for a pick (no jargon). */
export function plainTitle(p: Prediction): string {
  switch (p.market) {
    case "moneyline":
      return `Gana ${p.selection}`;
    case "run_line":
      return p.selection.includes("-1.5")
        ? `${p.selection.replace(" -1.5", "")} gana por 2 o más`
        : `${p.selection.replace(" +1.5", "")} no pierde por más de 1`;
    case "total_over":
      return `Se anotan MÁS de ${p.line} carreras en total`;
    case "total_under":
      return `Se anotan MENOS de ${p.line} carreras en total`;
    case "first_inning":
      return "Anotan en la 1ª entrada";
    case "player_hits":
      return p.selection.replace(/1\+ hit/, "pega al menos 1 hit")
        .replace(/2\+ hits/, "pega 2 hits o más")
        .replace(/3\+ hits/, "pega 3 hits o más");
    case "player_home_runs":
      return p.selection.replace(/HR/, "pega un jonrón");
    case "player_rbi":
      return p.selection.replace(/1\+ RBI/, "produce al menos 1 carrera");
    case "player_total_bases":
      return p.selection.replace(/2\+ bases totales/, "consigue 2+ bases");
    case "player_stolen_bases":
      return p.selection.replace(/base robada/, "se roba una base");
    case "player_runs":
      return p.selection.replace(/anota carrera/, "anota una carrera");
    case "player_walks":
      return p.selection.replace(/1\+ BB/, "recibe una base por bolas");
    case "pitcher_strikeouts":
      return p.selection.replace(/over ([\d.]+) K/, "poncha a más de $1 bateadores");
    case "pitcher_outs":
      return p.selection.replace(/over ([\d.]+) outs/, "consigue más de $1 outs");
    case "pitcher_earned_runs":
      return p.selection.replace(/over ([\d.]+) ER/, "permite más de $1 carreras");
    case "pitcher_hits_allowed":
      return p.selection.replace(/over ([\d.]+) hits/, "permite más de $1 hits");
    case "pitcher_walks":
      return p.selection.replace(/over ([\d.]+) BB/, "da más de $1 bases por bolas");
    case "pitcher_win":
      return p.selection.replace(/gana/, "se lleva la victoria");
    case "quality_start":
      return `${p.selection.replace(" quality start", "")} lanza un gran juego`;
    case "no_hitter":
      return p.selection.replace(/no-hitter/, "lanza un juego sin hits");
    default:
      return p.selection;
  }
}

/** A one-line, kid-simple category label. */
export const PLAIN_MARKET: Record<string, string> = {
  moneyline: "Quién gana el juego",
  run_line: "Gana por muchas / aguanta",
  total_over: "Muchas carreras",
  total_under: "Pocas carreras",
  first_inning: "Carrera temprana",
  player_hits: "Hits de un bateador",
  player_home_runs: "Jonrones",
  player_rbi: "Carreras producidas",
  player_total_bases: "Bases de un bateador",
  player_stolen_bases: "Bases robadas",
  pitcher_strikeouts: "Ponches del lanzador",
};

/** Confidence → a plain word + emoji + color. */
export function confidenceLabel(p: number): { text: string; emoji: string; color: string } {
  if (p >= 0.7) return { text: "Muy segura", emoji: "🟢", color: "text-terminal-green" };
  if (p >= 0.6) return { text: "Segura", emoji: "🟢", color: "text-terminal-green" };
  if (p >= 0.52) return { text: "Buena", emoji: "🟡", color: "text-terminal-amber" };
  if (p >= 0.45) return { text: "Arriesgada", emoji: "🟠", color: "text-orange-400" };
  return { text: "Muy arriesgada", emoji: "🔴", color: "text-terminal-red" };
}

/** Stars 1–5 from a probability, for an at-a-glance safety read. */
export function safetyStars(p: number): number {
  if (p >= 0.72) return 5;
  if (p >= 0.63) return 4;
  if (p >= 0.55) return 3;
  if (p >= 0.47) return 2;
  return 1;
}

export function decimalFromAmerican(a: number): number {
  return a > 0 ? 1 + a / 100 : 1 + 100 / Math.abs(a);
}

/** "Apuestas $10 → ganas $9" in plain terms. */
export function payoutText(odds: number | null | undefined, fair: number, stake = 10): string {
  const a = odds ?? fair;
  const profit = stake * (decimalFromAmerican(a) - 1);
  return `Apuestas $${stake} → ganas $${profit.toFixed(0)}`;
}

/** "7 de cada 10 veces" from a probability. */
export function outOfTen(p: number): string {
  return `${Math.round(p * 10)} de cada 10 veces`;
}

/** How much to bet, in plain terms, from the model's Kelly fraction. */
export function stakeAdvice(kelly: number | null | undefined): string {
  if (!kelly || kelly <= 0) return "Mejor no apostar aquí";
  if (kelly >= 0.04) return "Puedes apostar un poco más";
  if (kelly >= 0.02) return "Apuesta normal";
  return "Apuesta pequeña";
}
