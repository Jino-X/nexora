"use client";

import { useMounted } from "@/hooks/use-mounted";
import { greeting } from "@/lib/format";

/**
 * Time-of-day greeting and today's date, read from the browser clock after hydration. Returns null on
 * the server and during hydration, so a page prerendered at build time never disagrees with the
 * visitor's local time.
 */
export function useToday(): { greeting: string; date: string } | null {
  const mounted = useMounted();
  if (!mounted) return null;
  const now = new Date();
  return {
    greeting: greeting(now),
    date: new Intl.DateTimeFormat(undefined, { weekday: "long", day: "numeric", month: "long" }).format(now),
  };
}
