import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { withAuthHeaders } from "@/api/client";

export type Theme = "light" | "dark" | "system";

const STORAGE_KEY = "sl.theme";

interface ThemeContextValue {
  theme: Theme;
  resolved: "light" | "dark";
  setTheme: (t: Theme) => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

function readInitial(): Theme {
  if (typeof window === "undefined") return "system";
  const v = window.localStorage.getItem(STORAGE_KEY);
  return v === "light" || v === "dark" || v === "system" ? v : "system";
}

function systemPrefersDark(): boolean {
  if (typeof window === "undefined") return false;
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

function applyClass(resolved: "light" | "dark") {
  const root = document.documentElement;
  if (resolved === "dark") root.classList.add("dark");
  else root.classList.remove("dark");
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(readInitial);
  const [systemDark, setSystemDark] = useState<boolean>(systemPrefersDark);

  useEffect(() => {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const handler = (e: MediaQueryListEvent) => setSystemDark(e.matches);
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, []);

  // One-shot: pull persisted preference from backend on mount and reconcile.
  // We never overwrite an explicitly different *local* preference set during
  // this session — only adopt the backend value when the user hasn't touched
  // it yet (i.e. localStorage was empty or matches "system").
  useEffect(() => {
    const hadLocal = !!window.localStorage.getItem(STORAGE_KEY);
    fetch("/api/settings", withAuthHeaders())
      .then((r) => (r.ok ? r.json() : null))
      .then((data: { appearance_theme?: Theme } | null) => {
        if (!data || !data.appearance_theme) return;
        if (!hadLocal) {
          setThemeState(data.appearance_theme);
        }
      })
      .catch(() => {
        /* offline / not yet booted; keep local */
      });
  }, []);

  const resolved: "light" | "dark" = useMemo(() => {
    if (theme === "system") return systemDark ? "dark" : "light";
    return theme;
  }, [theme, systemDark]);

  useEffect(() => {
    applyClass(resolved);
  }, [resolved]);

  const setTheme = useCallback((t: Theme) => {
    setThemeState(t);
    try {
      window.localStorage.setItem(STORAGE_KEY, t);
    } catch {
      /* ignore */
    }
  }, []);

  const value = useMemo(
    () => ({ theme, resolved, setTheme }),
    [theme, resolved, setTheme],
  );
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme must be used within ThemeProvider");
  return ctx;
}
