"use client";

/** Client-side auth state: token presence + current user profile. */
import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { clearTokens, getAccessToken, post, storeTokens } from "@/lib/api";
import { useMe } from "@/lib/queries";
import type { TokenPair, User } from "@/lib/types";

interface AuthState {
  user: User | undefined;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, fullName?: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [hasToken, setHasToken] = useState(false);
  const queryClient = useQueryClient();

  useEffect(() => {
    setHasToken(Boolean(getAccessToken()));
  }, []);

  const { data: user, isLoading } = useMe(hasToken);

  const login = useCallback(
    async (email: string, password: string) => {
      const tokens = await post<TokenPair>("/auth/login", { email, password });
      storeTokens(tokens.access_token, tokens.refresh_token);
      setHasToken(true);
      await queryClient.invalidateQueries({ queryKey: ["me"] });
    },
    [queryClient],
  );

  const register = useCallback(
    async (email: string, password: string, fullName?: string) => {
      const tokens = await post<TokenPair>("/auth/register", {
        email,
        password,
        full_name: fullName ?? null,
      });
      storeTokens(tokens.access_token, tokens.refresh_token);
      setHasToken(true);
      await queryClient.invalidateQueries({ queryKey: ["me"] });
    },
    [queryClient],
  );

  const logout = useCallback(() => {
    clearTokens();
    setHasToken(false);
    queryClient.clear();
  }, [queryClient]);

  return (
    <AuthContext.Provider
      value={{ user, isAuthenticated: hasToken, isLoading: hasToken && isLoading, login, register, logout }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
