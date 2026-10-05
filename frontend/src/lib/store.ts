import { useEffect, useState } from "react";
import { create } from "zustand";
import { persist } from "zustand/middleware";

interface User {
  id: string;
  email: string;
  full_name: string;
  phone: string | null;
  role: string;
  branch_id: string | null;
  is_active: boolean;
}

interface AuthState {
  user: User | null;
  accessToken: string | null;
  refreshToken: string | null;
  setAuth: (user: User, accessToken: string, refreshToken: string) => void;
  setTokens: (accessToken: string, refreshToken: string) => void;
  logout: () => void;
  updateUser: (user: Partial<User>) => void;
}

const TOKEN_KEY = "bike-crm-tokens";

function writeTokens(accessToken: string | null, refreshToken: string | null) {
  if (typeof window === "undefined") return;
  try {
    if (accessToken && refreshToken) {
      window.localStorage.setItem(
        TOKEN_KEY,
        JSON.stringify({ accessToken, refreshToken })
      );
    } else {
      window.localStorage.removeItem(TOKEN_KEY);
    }
  } catch {
    /* private mode / quota */
  }
}

function readTokens(): { accessToken: string; refreshToken: string } | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(TOKEN_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (parsed?.accessToken && parsed?.refreshToken) return parsed;
    return null;
  } catch {
    return null;
  }
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      accessToken: null,
      refreshToken: null,
      setAuth: (user, accessToken, refreshToken) => {
        writeTokens(accessToken, refreshToken);
        set({ user, accessToken, refreshToken });
      },
      setTokens: (accessToken, refreshToken) => {
        writeTokens(accessToken, refreshToken);
        set({ accessToken, refreshToken });
      },
      logout: () => {
        writeTokens(null, null);
        set({ user: null, accessToken: null, refreshToken: null });
      },
      updateUser: (userData) =>
        set((state) => ({
          user: state.user ? { ...state.user, ...userData } : null,
        })),
    }),
    {
      name: "bike-crm-auth",
      partialize: (state) => ({
        user: state.user,
        accessToken: state.accessToken,
        refreshToken: state.refreshToken,
      }),
    }
  )
);

export function restoreSession(): boolean {
  const { accessToken, refreshToken } = useAuthStore.getState();
  if (accessToken && refreshToken) return true;

  const stored = readTokens();
  if (stored) {
    useAuthStore.setState({
      accessToken: stored.accessToken,
      refreshToken: stored.refreshToken,
    });
    return true;
  }
  return false;
}

export function useAuthReady(): boolean {
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let done = false;
    const finish = () => {
      if (done) return;
      done = true;
      restoreSession();
      setReady(true);
    };

    if (useAuthStore.persist.hasHydrated()) {
      finish();
      return;
    }

    const unsub = useAuthStore.persist.onFinishHydration(finish);
    const timer = window.setTimeout(finish, 300);

    return () => {
      unsub();
      window.clearTimeout(timer);
    };
  }, []);

  return ready;
}