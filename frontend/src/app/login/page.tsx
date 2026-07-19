"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Github, LineChart } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/lib/auth-context";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "/api/v1";

export default function LoginPage() {
  const { login } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email, password);
      router.push("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error de autenticación");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto mt-16 max-w-sm">
      <div className="mb-6 flex items-center justify-center gap-2">
        <LineChart className="h-6 w-6 text-terminal-accent" />
        <span className="font-mono text-lg font-bold">
          EVR <span className="text-terminal-accent">MLB AI</span> PRO
        </span>
      </div>
      <Card>
        <CardContent className="space-y-3">
          <form onSubmit={submit} className="space-y-3">
            <Input type="email" placeholder="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
            <Input
              type="password"
              placeholder="contraseña"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
            {error && <p className="text-xs text-terminal-red">{error}</p>}
            <Button type="submit" className="w-full" disabled={busy}>
              {busy ? "Entrando…" : "Iniciar sesión"}
            </Button>
          </form>
          <div className="flex items-center gap-2 text-[10px] uppercase tracking-widest text-terminal-muted">
            <span className="h-px flex-1 bg-terminal-border" /> o <span className="h-px flex-1 bg-terminal-border" />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <a href={`${API_URL}/auth/oauth/google/login`}>
              <Button variant="outline" className="w-full" type="button">
                Google
              </Button>
            </a>
            <a href={`${API_URL}/auth/oauth/github/login`}>
              <Button variant="outline" className="w-full" type="button">
                <Github className="h-4 w-4" /> GitHub
              </Button>
            </a>
          </div>
          <p className="text-center text-xs text-terminal-muted">
            ¿Sin cuenta?{" "}
            <Link href="/register" className="text-terminal-accent hover:underline">
              Regístrate
            </Link>
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
