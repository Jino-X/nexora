"use client";

import { useRouter } from "next/navigation";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  useSyncExternalStore,
  type ReactNode,
} from "react";

import { setTokenGetter, setUnauthorizedHandler } from "@/lib/api/client";
import { devLogin, devLogout, devUserFromToken, readDevToken, subscribeDevToken } from "@/lib/auth/dev-auth";
import { getSupabase } from "@/lib/auth/supabase-browser";
import { authMode, config } from "@/lib/config";

export interface AuthUser {
  id: string;
  email: string | null;
}

type Status = "loading" | "authenticated" | "unauthenticated";

interface AuthState {
  mode: "supabase" | "dev";
  status: Status;
  user: AuthUser | null;
  signIn: (email: string, password: string) => Promise<void>;
  signUp: (email: string, password: string, displayName?: string) => Promise<{ needsConfirmation: boolean }>;
  resetPassword: (email: string) => Promise<void>;
  signOut: () => Promise<void>;
  getAccessToken: () => Promise<string | null>;
}

const AuthContext = createContext<AuthState | null>(null);

/** Dev mode: the token cookie is an external store. `undefined` = unknown (server render / hydration). */
function useDevToken(): string | null | undefined {
  return useSyncExternalStore(subscribeDevToken, readDevToken, () => undefined);
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const devToken = useDevToken();
  const [sbUser, setSbUser] = useState<AuthUser | null>(null);
  const [sbStatus, setSbStatus] = useState<Status>("loading");

  const devUser = useMemo(() => (devToken ? devUserFromToken(devToken) : null), [devToken]);
  const user = authMode === "dev" ? devUser : sbUser;
  const status: Status =
    authMode === "dev"
      ? devToken === undefined
        ? "loading"
        : devUser
          ? "authenticated"
          : "unauthenticated"
      : sbStatus;

  const getAccessToken = useCallback(async () => {
    if (authMode === "dev") return readDevToken();
    const { data } = await getSupabase().auth.getSession();
    return data.session?.access_token ?? null;
  }, []);

  useEffect(() => {
    if (authMode === "dev") return;
    const supabase = getSupabase();
    supabase.auth.getUser().then(({ data }) => {
      setSbUser(data.user ? { id: data.user.id, email: data.user.email ?? null } : null);
      setSbStatus(data.user ? "authenticated" : "unauthenticated");
    });
    const { data: sub } = supabase.auth.onAuthStateChange((_event, session) => {
      setSbUser(session?.user ? { id: session.user.id, email: session.user.email ?? null } : null);
      setSbStatus(session?.user ? "authenticated" : "unauthenticated");
    });
    return () => sub.subscription.unsubscribe();
  }, []);

  const signOut = useCallback(async () => {
    if (authMode === "dev") devLogout();
    else {
      await getSupabase().auth.signOut();
      setSbUser(null);
      setSbStatus("unauthenticated");
    }
    router.replace("/login");
    router.refresh();
  }, [router]);

  useEffect(() => {
    setTokenGetter(getAccessToken);
    setUnauthorizedHandler(() => {
      void signOut();
    });
  }, [getAccessToken, signOut]);

  const signIn = useCallback(async (email: string, password: string) => {
    if (authMode === "dev") {
      await devLogin(email);
      return;
    }
    const { data, error } = await getSupabase().auth.signInWithPassword({ email, password });
    if (error) throw new Error(error.message);
    setSbUser({ id: data.user.id, email: data.user.email ?? null });
    setSbStatus("authenticated");
  }, []);

  const signUp = useCallback(async (email: string, password: string, displayName?: string) => {
    if (authMode === "dev") {
      await devLogin(email, displayName);
      return { needsConfirmation: false };
    }
    const { data, error } = await getSupabase().auth.signUp({
      email,
      password,
      options: {
        data: { display_name: displayName },
        emailRedirectTo: `${config.appUrl}/auth/callback?next=/onboarding`,
      },
    });
    if (error) throw new Error(error.message);
    return { needsConfirmation: !data.session };
  }, []);

  const resetPassword = useCallback(async (email: string) => {
    if (authMode === "dev") throw new Error("Password reset needs Supabase Auth (not available in dev mode).");
    const { error } = await getSupabase().auth.resetPasswordForEmail(email, {
      redirectTo: `${config.appUrl}/auth/callback?next=/settings?tab=security`,
    });
    if (error) throw new Error(error.message);
  }, []);

  const value = useMemo<AuthState>(
    () => ({ mode: authMode, status, user, signIn, signUp, resetPassword, signOut, getAccessToken }),
    [status, user, signIn, signUp, resetPassword, signOut, getAccessToken],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
