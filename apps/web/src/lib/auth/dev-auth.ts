/**
 * Development-only authentication used when Supabase is not configured. The API issues a short-lived
 * HS256 token from /auth/dev/login (only when AUTH_DEV_MODE=true and APP_ENV != production).
 */

import { config, DEV_TOKEN_COOKIE } from "@/lib/config";

export interface DevUser {
  id: string;
  email: string;
}

export function decodeJwtPayload(token: string): Record<string, unknown> | null {
  try {
    const part = token.split(".")[1];
    const json = atob(
      part
        .replace(/-/g, "+")
        .replace(/_/g, "/")
        .padEnd(Math.ceil(part.length / 4) * 4, "="),
    );
    return JSON.parse(json);
  } catch {
    return null;
  }
}

const listeners = new Set<() => void>();

/** Subscribe to dev-token changes (login/logout in this tab). Used with useSyncExternalStore. */
export function subscribeDevToken(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function notifyDevToken() {
  listeners.forEach((l) => l());
}

export function readDevToken(): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.split("; ").find((c) => c.startsWith(`${DEV_TOKEN_COOKIE}=`));
  if (!match) return null;
  const token = decodeURIComponent(match.split("=")[1]);
  const payload = decodeJwtPayload(token);
  if (!payload || typeof payload.exp !== "number" || payload.exp * 1000 < Date.now()) return null;
  return token;
}

export function devUserFromToken(token: string): DevUser | null {
  const payload = decodeJwtPayload(token);
  if (!payload) return null;
  return { id: String(payload.sub), email: String(payload.email ?? "") };
}

export async function devLogin(email: string, displayName?: string): Promise<string> {
  const res = await fetch(`${config.apiUrl}/api/v1/auth/dev/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, display_name: displayName || undefined }),
  });
  const body = await res.json().catch(() => null);
  if (!res.ok) {
    throw new Error(body?.error?.message ?? "Development login failed. Is the API running with AUTH_DEV_MODE=true?");
  }
  const secure = location.protocol === "https:" ? "; Secure" : "";
  const maxAge = Math.max(60, body.expires_at - Math.floor(Date.now() / 1000));
  document.cookie = `${DEV_TOKEN_COOKIE}=${encodeURIComponent(body.access_token)}; Path=/; Max-Age=${maxAge}; SameSite=Lax${secure}`;
  notifyDevToken();
  return body.access_token as string;
}

export function devLogout(): void {
  document.cookie = `${DEV_TOKEN_COOKIE}=; Path=/; Max-Age=0; SameSite=Lax`;
  notifyDevToken();
}
