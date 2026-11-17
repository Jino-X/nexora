/** Typed fetch wrapper for the Nexora API (bearer auth, error envelope, timeouts). */

import type { ApiErrorBody } from "@nexora/shared-types";

import { config } from "@/lib/config";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details?: unknown,
    public requestId?: string | null,
  ) {
    super(message);
    this.name = "ApiError";
  }

  get isNotConfigured() {
    return this.status === 503;
  }
}

type TokenGetter = () => Promise<string | null>;
let tokenGetter: TokenGetter = async () => null;
let onUnauthorized: () => void = () => {};

export function setTokenGetter(fn: TokenGetter) {
  tokenGetter = fn;
}

export function setUnauthorizedHandler(fn: () => void) {
  onUnauthorized = fn;
}

export async function authHeaders(): Promise<Record<string, string>> {
  const token = await tokenGetter();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
  body?: unknown;
  query?: Record<string, string | number | boolean | null | undefined>;
  signal?: AbortSignal;
  timeoutMs?: number;
}

export function buildUrl(path: string, query?: RequestOptions["query"]): string {
  const url = new URL(`${config.apiUrl}/api/v1${path}`);
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== undefined && value !== null && value !== "") url.searchParams.set(key, String(value));
  }
  return url.toString();
}

export async function toApiError(res: Response): Promise<ApiError> {
  const body = (await res.json().catch(() => null)) as ApiErrorBody | null;
  const err = body?.error;
  return new ApiError(
    res.status,
    err?.code ?? "http_error",
    err?.message ?? res.statusText,
    err?.details,
    err?.request_id,
  );
}

export async function api<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), opts.timeoutMs ?? 30_000);
  opts.signal?.addEventListener("abort", () => controller.abort());
  let res: Response;
  try {
    res = await fetch(buildUrl(path, opts.query), {
      method: opts.method ?? "GET",
      headers: {
        ...(opts.body !== undefined ? { "Content-Type": "application/json" } : {}),
        ...(await authHeaders()),
      },
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
      signal: controller.signal,
    });
  } catch (error) {
    if (controller.signal.aborted && !opts.signal?.aborted) {
      throw new ApiError(0, "timeout", "The request timed out. Check your connection.");
    }
    throw new ApiError(0, "network_error", "Can't reach the Nexora API. Is it running?", error);
  } finally {
    clearTimeout(timeout);
  }
  if (res.status === 401) {
    const err = await toApiError(res);
    onUnauthorized();
    throw err;
  }
  if (!res.ok) throw await toApiError(res);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}
