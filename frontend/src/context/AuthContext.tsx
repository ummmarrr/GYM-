import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import { api, tokenStore } from "../lib/api";
import type { Entitlements, Role, User } from "../lib/api";

interface AuthValue {
  user: User | null;
  entitlements: Entitlements | null;
  loading: boolean;
  signIn: (email: string, password: string) => Promise<User>;
  signUp: (payload: {
    email: string;
    full_name: string;
    password: string;
    phone?: string;
  }) => Promise<User>;
  signOut: () => void;
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthValue | null>(null);

export function homeFor(role: Role): string {
  if (role === "admin") return "/admin";
  if (role === "trainer") return "/trainer";
  return "/dashboard";
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [entitlements, setEntitlements] = useState<Entitlements | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    if (!tokenStore.get()) {
      setUser(null);
      setEntitlements(null);
      setLoading(false);
      return;
    }
    try {
      const profile = await api.me();
      setUser(profile);
      setEntitlements(await api.entitlements());
    } catch {
      // An expired or tampered token should simply log the person out.
      tokenStore.clear();
      setUser(null);
      setEntitlements(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const afterToken = useCallback(async (token: string) => {
    tokenStore.set(token);
    const profile = await api.me();
    setUser(profile);
    setEntitlements(await api.entitlements());
    return profile;
  }, []);

  const value = useMemo<AuthValue>(
    () => ({
      user,
      entitlements,
      loading,
      signIn: async (email, password) => {
        const { access_token } = await api.login(email, password);
        return afterToken(access_token);
      },
      signUp: async (payload) => {
        const { access_token } = await api.register(payload);
        return afterToken(access_token);
      },
      signOut: () => {
        tokenStore.clear();
        setUser(null);
        setEntitlements(null);
      },
      refresh: load,
    }),
    [user, entitlements, loading, afterToken, load],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}
