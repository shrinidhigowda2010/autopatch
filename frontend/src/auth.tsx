import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api } from "./api";
import { getGuestFlag, getStoredToken, setGuestFlag, setStoredToken } from "./token";

export interface AuthUser {
  id: string;
  coder_id: string;
  full_name: string;
  email: string;
  role: string;
  created_at: string;
  last_login: string | null;
  stats?: {
    total_scans: number;
    bugs_found: number;
    patches_accepted: number;
    patches_rejected: number;
    member_since: string;
  };
}

interface AuthState {
  user: AuthUser | null;
  token: string | null;
  isGuest: boolean;
  loading: boolean;
  setSession: (token: string, user: AuthUser) => void;
  continueAsGuest: () => void;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
  initials: string;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [token, setToken] = useState<string | null>(() => getStoredToken());
  const [isGuest, setIsGuest] = useState(() => getGuestFlag());
  const [loading, setLoading] = useState(Boolean(getStoredToken()));

  const setSession = useCallback((nextToken: string, nextUser: AuthUser) => {
    setStoredToken(nextToken);
    setGuestFlag(false);
    setToken(nextToken);
    setUser(nextUser);
    setIsGuest(false);
  }, []);

  const continueAsGuest = useCallback(() => {
    setStoredToken(null);
    setGuestFlag(true);
    setToken(null);
    setUser(null);
    setIsGuest(true);
  }, []);

  const logout = useCallback(async () => {
    const current = getStoredToken();
    if (current) {
      try {
        await api("/api/auth/logout", { method: "POST" });
      } catch {
        /* token may already be invalid */
      }
    }
    setStoredToken(null);
    setGuestFlag(false);
    setToken(null);
    setUser(null);
    setIsGuest(false);
  }, []);

  const refresh = useCallback(async () => {
    const current = getStoredToken();
    if (!current) {
      setLoading(false);
      return;
    }
    try {
      const me = await api<AuthUser>("/api/auth/me");
      setUser(me);
      setToken(current);
      setIsGuest(false);
    } catch {
      setStoredToken(null);
      setUser(null);
      setToken(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const initials = useMemo(() => {
    if (!user?.full_name) return "?";
    return (
      user.full_name
        .split(/\s+/)
        .filter(Boolean)
        .slice(0, 2)
        .map((part) => part[0]?.toUpperCase() || "")
        .join("") || "?"
    );
  }, [user]);

  const value = useMemo(
    () => ({ user, token, isGuest, loading, setSession, continueAsGuest, logout, refresh, initials }),
    [user, token, isGuest, loading, setSession, continueAsGuest, logout, refresh, initials],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
