"use client";

import { createBrowserClient } from "@supabase/ssr";
import type { SupabaseClient } from "@supabase/supabase-js";

import { config } from "@/lib/config";

let client: SupabaseClient | null = null;

/** Singleton browser client. Sessions live in cookies so proxy.ts can refresh and check them. */
export function getSupabase(): SupabaseClient {
  if (!client) {
    client = createBrowserClient(config.supabaseUrl, config.supabaseKey);
  }
  return client;
}
