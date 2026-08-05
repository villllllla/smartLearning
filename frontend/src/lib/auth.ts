import { authApi, type AuthUser } from "@/api/auth";

const TOKEN_KEY = "sl_access_token";
const USER_KEY = "sl_auth_user";

export function getStoredToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function getStoredUser(): AuthUser | null {
  const raw = localStorage.getItem(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as AuthUser;
  } catch {
    return null;
  }
}

export function saveAuth(token: string, user: AuthUser) {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

export function clearAuth() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

export async function refreshAuthUser(): Promise<AuthUser | null> {
  if (!getStoredToken()) return null;
  try {
    const res = await authApi.me();
    saveAuth(getStoredToken()!, res.user);
    return res.user;
  } catch {
    clearAuth();
    return null;
  }
}
