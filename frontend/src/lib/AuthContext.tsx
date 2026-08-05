import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { authApi, type AuthUser } from "@/api/auth";
import { clearAuth, getStoredToken, getStoredUser, saveAuth } from "@/lib/auth";

type AuthState = {
  user: AuthUser | null;
  authEnabled: boolean;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  refresh: () => Promise<void>;
};

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(() => getStoredUser());
  const [authEnabled, setAuthEnabled] = useState(true);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const res = await authApi.me();
      setAuthEnabled(res.auth_enabled);
      const token = getStoredToken();
      if (token && res.user.id > 0) {
        saveAuth(token, res.user);
      }
      setUser(res.user);
    } catch {
      if (getStoredToken()) clearAuth();
      setUser(null);
      setAuthEnabled(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const login = useCallback(async (email: string, password: string) => {
    const res = await authApi.login({ email, password });
    saveAuth(res.access_token, res.user);
    setUser(res.user);
    setAuthEnabled(true);
  }, []);

  const logout = useCallback(() => {
    clearAuth();
    setUser(null);
  }, []);

  const value = useMemo(
    () => ({ user, authEnabled, loading, login, logout, refresh }),
    [user, authEnabled, loading, login, logout, refresh],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
