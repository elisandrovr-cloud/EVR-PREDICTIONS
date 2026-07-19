"use client";

import Link from "next/link";
import { LogOut, User as UserIcon } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth-context";
import { useLiveGames } from "@/lib/queries";

function Clock() {
  const [now, setNow] = useState<Date | null>(null);
  useEffect(() => {
    setNow(new Date());
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);
  return (
    <span suppressHydrationWarning className="font-mono text-xs text-terminal-muted">
      {now ? now.toLocaleTimeString() : "--:--:--"}
    </span>
  );
}

export function Topbar() {
  const { user, isAuthenticated, logout } = useAuth();
  const { data: live } = useLiveGames();

  return (
    <header className="sticky top-0 z-30 flex h-12 items-center justify-between border-b border-terminal-border bg-terminal-bg/95 px-4 backdrop-blur md:pl-56">
      <div className="flex items-center gap-3">
        <span className="relative flex h-2 w-2">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-terminal-green opacity-60" />
          <span className="relative inline-flex h-2 w-2 rounded-full bg-terminal-green" />
        </span>
        <span className="font-mono text-xs uppercase tracking-wider text-terminal-muted">
          {live?.length ? `${live.length} juegos en vivo` : "Mercados monitoreados 24/7"}
        </span>
      </div>
      <div className="flex items-center gap-3">
        <Clock />
        {isAuthenticated && user ? (
          <div className="flex items-center gap-2">
            <span className="hidden font-mono text-xs text-terminal-muted sm:inline">{user.email}</span>
            <Button variant="ghost" size="sm" onClick={logout} aria-label="Cerrar sesión">
              <LogOut className="h-3.5 w-3.5" />
            </Button>
          </div>
        ) : (
          <Link href="/login">
            <Button variant="outline" size="sm">
              <UserIcon className="h-3.5 w-3.5" /> Entrar
            </Button>
          </Link>
        )}
      </div>
    </header>
  );
}
