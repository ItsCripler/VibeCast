import { createContext, useContext, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPost } from "../../lib/api";
import type { User } from "../../types";

type AuthValue = { user: User | null; loading: boolean; refresh: () => Promise<void>; logout: () => Promise<void> };
const AuthContext = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const client = useQueryClient();
  const query = useQuery({ queryKey: ["current-user"], queryFn: () => apiGet<User>("/auth/me"), retry: false, staleTime: 60_000 });
  const refresh = async () => { await client.invalidateQueries({ queryKey: ["current-user"] }); };
  const logout = async () => {
    try { await apiPost<void>("/auth/logout"); } finally { await client.setQueryData(["current-user"], null); }
  };
  const value: AuthValue = { user: query.data || null, loading: query.isPending, refresh, logout };
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}
