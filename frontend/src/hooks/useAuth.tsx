import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { authApi } from "@/api/auth";
import { AUTH_LOGOUT_EVENT, getAuthToken, setAuthToken } from "@/api/client";
import type { CurrentUser } from "@/types";

interface AuthContextValue {
  /** Whether this deployment has AUTH_ENABLED=true. `undefined` while loading. */
  authEnabled: boolean | undefined;
  user: CurrentUser | undefined;
  isLoading: boolean;
  hasToken: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const [hasToken, setHasToken] = useState(() => getAuthToken() !== null);

  const capabilities = useQuery({
    queryKey: ["auth-capabilities"],
    queryFn: authApi.capabilities,
    staleTime: 60_000,
  });

  const me = useQuery({
    queryKey: ["auth-me", hasToken],
    queryFn: authApi.me,
    // /auth/me works with or without a token (it reports the anonymous
    // principal when auth is disabled); only skip it before capabilities
    // has told us whether auth is even enabled, to avoid a flash of an
    // unauthenticated call on a deployment that doesn't need one.
    enabled: capabilities.isSuccess,
    retry: false,
  });

  useEffect(() => {
    const onLogout = () => {
      setHasToken(false);
      qc.invalidateQueries({ queryKey: ["auth-me"] });
    };
    window.addEventListener(AUTH_LOGOUT_EVENT, onLogout);
    return () => window.removeEventListener(AUTH_LOGOUT_EVENT, onLogout);
  }, [qc]);

  const login = useCallback(
    async (username: string, password: string) => {
      const token = await authApi.login(username, password);
      setAuthToken(token.access_token);
      setHasToken(true);
      await qc.invalidateQueries({ queryKey: ["auth-me"] });
    },
    [qc],
  );

  const logout = useCallback(() => {
    setAuthToken(null);
    setHasToken(false);
    qc.invalidateQueries({ queryKey: ["auth-me"] });
  }, [qc]);

  const value: AuthContextValue = {
    authEnabled: capabilities.data?.auth_enabled,
    user: me.data,
    isLoading: capabilities.isLoading || (capabilities.isSuccess && me.isLoading),
    hasToken,
    login,
    logout,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");
  return ctx;
}
