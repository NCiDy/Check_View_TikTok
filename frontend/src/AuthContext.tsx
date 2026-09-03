import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api, setCsrfToken } from "./api";
import type { User } from "./types";

interface AuthState {
  user: User | null;
  sessionId: string | null;
  loading: boolean;
  signedOutReason: string | null;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshMe: () => Promise<void>;
  forceSignOut: (reason?: string) => void;
}

interface AuthResponse {
  user: User;
  session_id: string;
  csrf_token: string;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [signedOutReason, setSignedOutReason] = useState<string | null>(null);

  const applyAuth = useCallback((response: AuthResponse) => {
    setUser(response.user);
    setSessionId(response.session_id);
    setCsrfToken(response.csrf_token);
    setSignedOutReason(null);
  }, []);

  const forceSignOut = useCallback((reason = "Phiên đăng nhập đã kết thúc") => {
    setUser(null);
    setSessionId(null);
    setCsrfToken("");
    setSignedOutReason(reason);
  }, []);

  const refreshMe = useCallback(async () => {
    const response = await api<AuthResponse>(`/api/auth/me?t=${Date.now()}`);
    applyAuth(response);
  }, [applyAuth]);

  useEffect(() => {
    refreshMe().catch(() => forceSignOut("")).finally(() => setLoading(false));
  }, [forceSignOut, refreshMe]);

  useEffect(() => {
    const onUnauthorized = (event: Event) => {
      forceSignOut((event as CustomEvent<string>).detail || "Phiên đăng nhập đã hết hạn");
    };
    window.addEventListener("auth:unauthorized", onUnauthorized);
    return () => window.removeEventListener("auth:unauthorized", onUnauthorized);
  }, [forceSignOut]);

  const login = useCallback(async (username: string, password: string) => {
    const response = await api<AuthResponse>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    });
    applyAuth(response);
  }, [applyAuth]);

  const logout = useCallback(async () => {
    try {
      await api<{ success: boolean }>("/api/auth/logout", { method: "POST" });
    } finally {
      forceSignOut("");
    }
  }, [forceSignOut]);

  const value = useMemo<AuthState>(() => ({
    user,
    sessionId,
    loading,
    signedOutReason,
    login,
    logout,
    refreshMe,
    forceSignOut,
  }), [user, sessionId, loading, signedOutReason, login, logout, refreshMe, forceSignOut]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth phải nằm trong AuthProvider");
  return value;
}
