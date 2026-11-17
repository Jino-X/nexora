/** Formatting helpers (Intl-based, no date library). */

export function timeAgo(iso: string | null | undefined): string {
  if (!iso) return "";
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
  const units: [Intl.RelativeTimeFormatUnit, number][] = [
    ["year", 31_536_000],
    ["month", 2_592_000],
    ["week", 604_800],
    ["day", 86_400],
    ["hour", 3600],
    ["minute", 60],
  ];
  for (const [unit, seconds] of units) {
    if (Math.abs(diff) >= seconds) return rtf.format(-Math.round(diff / seconds), unit);
  }
  return diff >= 0 ? "just now" : "in a moment";
}

export function formatDateTime(iso: string | null | undefined, opts?: Intl.DateTimeFormatOptions): string {
  if (!iso) return "-";
  return new Intl.DateTimeFormat(undefined, opts ?? { dateStyle: "medium", timeStyle: "short" }).format(new Date(iso));
}

export function formatTime(iso: string | null | undefined): string {
  if (!iso) return "";
  return new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit" }).format(new Date(iso));
}

export function formatDistance(meters: number | null | undefined): string {
  if (meters === null || meters === undefined) return "";
  return meters < 1000 ? `${meters} m` : `${(meters / 1000).toFixed(1)} km`;
}

export function greeting(date = new Date()): string {
  const h = date.getHours();
  if (h < 5) return "Good night";
  if (h < 12) return "Good morning";
  if (h < 17) return "Good afternoon";
  return "Good evening";
}

export function bytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

export const TOOL_LABELS: Record<string, string> = {
  weather_forecast: "Checking the weather",
  places_nearby: "Searching nearby places",
  directions_link: "Finding directions",
  news_headlines: "Reading the news",
  gmail_unread: "Reading unread email",
  gmail_search: "Searching email",
  gmail_read: "Opening email",
  gmail_create_draft: "Drafting email",
  gmail_send_email: "Sending email",
  whatsapp_send_message: "Sending WhatsApp message",
  youtube_search: "Searching YouTube",
  music_search: "Finding music",
  memory_save: "Saving to memory",
  memory_search: "Searching memory",
  vault_list_items: "Checking the vault",
  reminder_create: "Setting a reminder",
  automation_create: "Creating an automation",
  automation_list: "Listing automations",
  briefing_generate: "Preparing your briefing",
};
