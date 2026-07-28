"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BarChart3,
  Bot,
  Brain,
  CalendarDays,
  Layers,
  LineChart,
  MessageSquare,
  Settings,
  Sparkles,
  Target,
  Users,
  Wallet,
} from "lucide-react";

import { useAuth } from "@/lib/auth-context";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/", label: "Inicio (Fácil)", icon: Sparkles },
  { href: "/chat", label: "Chat IA", icon: MessageSquare },
  { href: "/agents", label: "Agentes IA", icon: Bot },
  { href: "/games", label: "Juegos", icon: CalendarDays },
  { href: "/predictions", label: "Predicciones", icon: Target },
  { href: "/parlays", label: "Parlays", icon: Layers },
  { href: "/players", label: "Jugadores", icon: Users },
  { href: "/stats", label: "Motor IA", icon: Brain },
  { href: "/bankroll", label: "Bankroll", icon: Wallet },
];

export function Sidebar() {
  const pathname = usePathname();
  const { user } = useAuth();

  return (
    <aside className="fixed inset-y-0 left-0 z-40 hidden w-52 flex-col border-r border-terminal-border bg-terminal-panel md:flex">
      <Link href="/" className="flex items-center gap-2 border-b border-terminal-border px-4 py-4">
        <LineChart className="h-5 w-5 text-terminal-accent" />
        <div className="font-mono text-sm font-bold tracking-tight text-terminal-text">
          EVR <span className="text-terminal-accent">MLB AI</span> PRO
        </div>
      </Link>
      <nav className="flex-1 space-y-0.5 p-2">
        {NAV.map(({ href, label, icon: Icon }) => {
          const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex items-center gap-2.5 rounded-md px-3 py-2 text-sm transition-colors",
                active
                  ? "bg-terminal-accent/10 text-terminal-accent"
                  : "text-terminal-muted hover:bg-terminal-border/40 hover:text-terminal-text",
              )}
            >
              <Icon className="h-4 w-4" />
              {label}
            </Link>
          );
        })}
        {user?.role === "admin" && (
          <Link
            href="/admin"
            className={cn(
              "flex items-center gap-2.5 rounded-md px-3 py-2 text-sm transition-colors",
              pathname.startsWith("/admin")
                ? "bg-terminal-accent/10 text-terminal-accent"
                : "text-terminal-muted hover:bg-terminal-border/40 hover:text-terminal-text",
            )}
          >
            <Settings className="h-4 w-4" />
            Admin
          </Link>
        )}
      </nav>
      <div className="border-t border-terminal-border p-3">
        <div className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-wider text-terminal-muted">
          <BarChart3 className="h-3.5 w-3.5 text-terminal-green" />
          Engine: auto-learning
        </div>
      </div>
    </aside>
  );
}
