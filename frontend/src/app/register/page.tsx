"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { LineChart } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/lib/auth-context";

export default function RegisterPage() {
  const { register } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await register(email, password, name || undefined);
      router.push("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error en el registro");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto mt-16 max-w-sm">
      <div className="mb-6 flex items-center justify-center gap-2">
        <LineChart className="h-6 w-6 text-terminal-accent" />
        <span className="font-mono text-lg font-bold">Crear cuenta</span>
      </div>
      <Card>
        <CardContent>
          <form onSubmit={submit} className="space-y-3">
            <Input placeholder="nombre (opcional)" value={name} onChange={(e) => setName(e.target.value)} />
            <Input type="email" placeholder="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
            <Input
              type="password"
              placeholder="contraseña (mín. 8 caracteres)"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              minLength={8}
              required
            />
            {error && <p className="text-xs text-terminal-red">{error}</p>}
            <Button type="submit" className="w-full" disabled={busy}>
              {busy ? "Creando…" : "Registrarme"}
            </Button>
            <p className="text-center text-xs text-terminal-muted">
              ¿Ya tienes cuenta?{" "}
              <Link href="/login" className="text-terminal-accent hover:underline">
                Inicia sesión
              </Link>
            </p>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
