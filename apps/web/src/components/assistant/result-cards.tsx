"use client";

import type {
  Briefing,
  MusicResult,
  NewsItem,
  Place,
  ResultCard,
  WeatherReport,
  YouTubeResult,
} from "@nexora/shared-types";
import {
  Bell,
  Brain,
  CalendarClock,
  CheckCircle2,
  Cloud,
  CloudDrizzle,
  CloudFog,
  CloudLightning,
  CloudRain,
  CloudSnow,
  CloudSun,
  Droplets,
  ExternalLink,
  KeyRound,
  Mail,
  MapPin,
  Navigation,
  Play,
  Send,
  Sun,
  Wind,
} from "lucide-react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useState } from "react";

import { IconTile } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { formatDistance, timeAgo } from "@/lib/format";
import { cn } from "@/lib/utils";

const PlacesMap = dynamic(() => import("@/components/maps/places-map"), {
  ssr: false,
  loading: () => <div className="bg-muted h-[260px] animate-pulse rounded-xl" />,
});

function Shell({ children, className }: { children: React.ReactNode; className?: string }) {
  return <div className={cn("glass overflow-hidden rounded-2xl", className)}>{children}</div>;
}

export function weatherIcon(code: number, className = "size-5") {
  if (code === 0 || code === 1) return <Sun className={className} />;
  if (code === 2) return <CloudSun className={className} />;
  if (code === 3) return <Cloud className={className} />;
  if (code === 45 || code === 48) return <CloudFog className={className} />;
  if (code >= 51 && code <= 57) return <CloudDrizzle className={className} />;
  if ((code >= 61 && code <= 67) || (code >= 80 && code <= 82)) return <CloudRain className={className} />;
  if ((code >= 71 && code <= 77) || code === 85 || code === 86) return <CloudSnow className={className} />;
  if (code >= 95) return <CloudLightning className={className} />;
  return <Cloud className={className} />;
}

/** Sky gradient that follows the actual conditions. */
function skyFor(code: number, isDay: boolean): string {
  if (!isDay) return "linear-gradient(135deg, #1e1b4b, #312e81 55%, #4c1d95)";
  if (code <= 1) return "linear-gradient(135deg, #f59e0b, #f97316 45%, #ec4899)";
  if (code <= 3) return "linear-gradient(135deg, #38bdf8, #6366f1 60%, #8b5cf6)";
  if (code <= 48) return "linear-gradient(135deg, #64748b, #6366f1)";
  if (code >= 95) return "linear-gradient(135deg, #4c1d95, #7c3aed 50%, #0f172a)";
  return "linear-gradient(135deg, #0ea5e9, #2563eb 55%, #4338ca)";
}

export function WeatherCard({ report, compact = false }: { report: WeatherReport; compact?: boolean }) {
  const today = report.daily[0];
  const sky = skyFor(report.current.weather_code, report.current.is_day);
  return (
    <Shell>
      <div className="relative overflow-hidden p-5 text-white" style={{ background: sky }}>
        <div aria-hidden className="absolute -top-16 -right-10 size-48 rounded-full bg-white/20 blur-2xl" />
        <div aria-hidden className="absolute -bottom-20 left-10 size-40 rounded-full bg-black/10 blur-2xl" />
        <div className="relative flex items-center justify-between">
          <div>
            <p className="text-sm font-medium text-white/85">{report.location_label ?? "Your location"}</p>
            <p className="font-heading text-6xl font-semibold tracking-tighter">
              {Math.round(report.current.temperature_c)}°
            </p>
            <p className="text-sm font-medium">{report.current.description}</p>
            {report.current.apparent_temperature_c != null && (
              <p className="text-xs text-white/75">Feels like {Math.round(report.current.apparent_temperature_c)}°</p>
            )}
          </div>
          <div className="animate-float drop-shadow-[0_8px_24px_rgba(0,0,0,0.25)]">
            {weatherIcon(report.current.weather_code, "size-20 text-white")}
          </div>
        </div>
        <div className="relative mt-4 grid grid-cols-3 gap-2 text-xs">
          <span className="inline-flex items-center gap-1.5 rounded-xl bg-white/15 px-2.5 py-1.5 backdrop-blur">
            <Droplets className="size-3.5" /> {today?.precipitation_probability_max ?? "-"}% rain
          </span>
          <span className="inline-flex items-center gap-1.5 rounded-xl bg-white/15 px-2.5 py-1.5 backdrop-blur">
            <Wind className="size-3.5" /> {Math.round(report.current.wind_speed_kmh ?? 0)} km/h
          </span>
          <span className="inline-flex items-center justify-center rounded-xl bg-white/15 px-2.5 py-1.5 backdrop-blur">
            {Math.round(today?.temperature_min_c ?? 0)}° / {Math.round(today?.temperature_max_c ?? 0)}°
          </span>
        </div>
      </div>
      {!compact && report.daily.length > 1 && (
        <div className="flex scrollbar-thin gap-1.5 overflow-x-auto p-3">
          {report.daily.slice(0, 7).map((d) => (
            <div
              key={d.date}
              className="bg-background/40 flex min-w-16 flex-col items-center gap-1 rounded-xl border px-2 py-2 text-xs"
            >
              <span className="text-muted-foreground">
                {new Date(`${d.date}T12:00:00`).toLocaleDateString(undefined, { weekday: "short" })}
              </span>
              {weatherIcon(d.weather_code, "size-5 text-brand")}
              <span className="font-medium">
                {Math.round(d.temperature_max_c ?? 0)}°
                <span className="text-muted-foreground"> {Math.round(d.temperature_min_c ?? 0)}°</span>
              </span>
            </div>
          ))}
        </div>
      )}
      <p className="text-muted-foreground px-3 py-1.5 text-[0.7rem]">{report.attribution}</p>
    </Shell>
  );
}

export function PlacesList({ places }: { places: Place[] }) {
  return (
    <ul className="divide-y">
      {places.map((p) => (
        <li key={p.id} className="flex items-start gap-3 p-3">
          <MapPin className="text-brand mt-0.5 size-4 shrink-0" />
          <div className="min-w-0 flex-1">
            <p className="truncate font-medium">{p.name}</p>
            <p className="text-muted-foreground truncate text-xs">
              {[formatDistance(p.distance_m), p.address, p.opening_hours].filter(Boolean).join(" · ")}
            </p>
          </div>
          <Button asChild size="sm" variant="outline">
            <a href={p.directions_url} target="_blank" rel="noreferrer">
              <Navigation /> Go
            </a>
          </Button>
        </li>
      ))}
    </ul>
  );
}

function PlacesCard({ card }: { card: Extract<ResultCard, { type: "places" }> }) {
  return (
    <Shell>
      <PlacesMap center={card.center} places={card.places} height={220} />
      {card.places.length > 0 ? (
        <PlacesList places={card.places.slice(0, 6)} />
      ) : (
        <p className="text-muted-foreground p-3 text-sm">Nothing found nearby.</p>
      )}
      <p className="text-muted-foreground border-t px-3 py-1.5 text-[0.7rem]">{card.attribution}</p>
    </Shell>
  );
}

export function NewsList({ items, limit = 6 }: { items: NewsItem[]; limit?: number }) {
  return (
    <ul className="divide-y">
      {items.slice(0, limit).map((n) => (
        <li key={n.id}>
          <a href={n.link} target="_blank" rel="noreferrer" className="group hover:bg-muted/50 flex gap-3 p-3">
            <div className="min-w-0 flex-1">
              <p className="line-clamp-2 font-medium group-hover:underline">{n.title}</p>
              <p className="text-muted-foreground mt-0.5 text-xs">
                {n.source}
                {n.published_at && ` · ${timeAgo(n.published_at)}`}
              </p>
            </div>
            <ExternalLink className="text-muted-foreground mt-1 size-3.5 shrink-0" />
          </a>
        </li>
      ))}
    </ul>
  );
}

export function YouTubeGrid({ items }: { items: YouTubeResult[] }) {
  const [playing, setPlaying] = useState<string | null>(null);
  return (
    <div className="grid gap-3 p-3 sm:grid-cols-2">
      {items.map((v) => (
        <div key={v.id} className="overflow-hidden rounded-xl border">
          {playing === v.id && v.embed_url ? (
            <iframe
              src={`${v.embed_url}?autoplay=1`}
              title={v.title}
              className="aspect-video w-full"
              allow="autoplay; encrypted-media; picture-in-picture"
              allowFullScreen
            />
          ) : (
            <button
              type="button"
              className="group bg-muted relative block aspect-video w-full"
              onClick={() => (v.embed_url ? setPlaying(v.id) : window.open(v.url, "_blank"))}
            >
              {v.thumbnail_url && (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={v.thumbnail_url} alt="" className="size-full object-cover" loading="lazy" />
              )}
              <span className="absolute inset-0 grid place-items-center bg-black/20 opacity-90 group-hover:bg-black/30">
                <span className="grid size-11 place-items-center rounded-full bg-white/90 text-black">
                  <Play className="size-5" />
                </span>
              </span>
            </button>
          )}
          <div className="p-2.5">
            <p className="line-clamp-2 text-sm font-medium">{v.title}</p>
            <a href={v.url} target="_blank" rel="noreferrer" className="text-muted-foreground text-xs hover:underline">
              {v.channel_title ?? "YouTube"}
            </a>
          </div>
        </div>
      ))}
    </div>
  );
}

export function MusicList({ items }: { items: MusicResult[] }) {
  const [embed, setEmbed] = useState<string | null>(null);
  return (
    <div>
      {embed && (
        <iframe
          src={embed}
          title="Player"
          className="h-[152px] w-full border-b"
          allow="autoplay; clipboard-write; encrypted-media"
          loading="lazy"
        />
      )}
      <ul className="divide-y">
        {items.slice(0, 8).map((m) => (
          <li key={`${m.provider}-${m.id}`} className="flex items-center gap-3 p-3">
            {m.artwork_url ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={m.artwork_url} alt="" className="size-10 rounded-md object-cover" loading="lazy" />
            ) : (
              <span className="bg-muted size-10 rounded-md" />
            )}
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium">{m.title}</p>
              <p className="text-muted-foreground truncate text-xs">{m.artist ?? m.kind}</p>
            </div>
            {m.embed_url ? (
              <Button
                size="icon-sm"
                variant="outline"
                onClick={() => setEmbed(m.embed_url)}
                aria-label={`Play ${m.title}`}
              >
                <Play />
              </Button>
            ) : m.preview_url ? (
              <audio controls preload="none" src={m.preview_url} className="h-8 w-36" />
            ) : null}
            <a
              href={m.url}
              target="_blank"
              rel="noreferrer"
              aria-label="Open in music app"
              className="text-muted-foreground"
            >
              <ExternalLink className="size-4" />
            </a>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function BriefingView({ briefing }: { briefing: Briefing }) {
  return (
    <div className="space-y-3 p-4">
      <p className="leading-relaxed">{briefing.text}</p>
      {briefing.issues.length > 0 && (
        <p className="text-muted-foreground text-xs">Skipped: {briefing.issues.join(" · ")}</p>
      )}
    </div>
  );
}

function SimpleRow({
  icon: Icon,
  children,
  action,
}: {
  icon: typeof Bell;
  children: React.ReactNode;
  action?: React.ReactNode;
}) {
  return (
    <Shell className="flex items-center gap-3 p-3 text-sm">
      <IconTile icon={Icon} tone="violet" size="sm" />
      <div className="min-w-0 flex-1">{children}</div>
      {action}
    </Shell>
  );
}

export function ResultCardView({ card }: { card: ResultCard }) {
  switch (card.type) {
    case "weather":
      return <WeatherCard report={card.report} />;
    case "places":
      return <PlacesCard card={card} />;
    case "directions":
      return (
        <SimpleRow
          icon={Navigation}
          action={
            <Button asChild size="sm">
              <a href={card.url} target="_blank" rel="noreferrer">
                Open maps
              </a>
            </Button>
          }
        >
          <p className="truncate font-medium">{card.destination.label.split(",")[0]}</p>
          <p className="text-muted-foreground truncate text-xs">{card.destination.label}</p>
        </SimpleRow>
      );
    case "news":
      return card.items.length ? (
        <Shell>
          <NewsList items={card.items} />
        </Shell>
      ) : null;
    case "youtube":
      return (
        <Shell>
          <YouTubeGrid items={card.items.slice(0, 4)} />
        </Shell>
      );
    case "music":
      return (
        <Shell>
          <MusicList items={card.items} />
          <p className="text-muted-foreground border-t px-3 py-1.5 text-[0.7rem]">
            Official {card.provider === "spotify" ? "Spotify" : "Apple Music"} previews and links
          </p>
        </Shell>
      );
    case "emails":
      return (
        <Shell>
          <ul className="divide-y">
            {card.items.map((e) => (
              <li key={e.id} className="flex gap-3 p-3 text-sm">
                <Mail className={cn("mt-0.5 size-4 shrink-0", e.unread ? "text-brand" : "text-muted-foreground")} />
                <div className="min-w-0">
                  <p className={cn("truncate", e.unread && "font-semibold")}>{e.subject || "(no subject)"}</p>
                  <p className="text-muted-foreground truncate text-xs">{e.from_}</p>
                </div>
              </li>
            ))}
          </ul>
        </Shell>
      );
    case "email":
      return (
        <SimpleRow icon={Mail}>
          <p className="truncate font-medium">{card.item.subject}</p>
          <p className="text-muted-foreground truncate text-xs">{card.item.from_}</p>
        </SimpleRow>
      );
    case "email_draft":
      return (
        <SimpleRow icon={Mail} action={<Badge variant="outline">Draft saved</Badge>}>
          <p className="truncate font-medium">{card.draft.subject}</p>
          <p className="text-muted-foreground truncate text-xs">To {card.draft.to}</p>
        </SimpleRow>
      );
    case "email_sent":
    case "whatsapp_sent":
      return (
        <SimpleRow icon={Send} action={<CheckCircle2 className="text-success size-5" />}>
          <p className="font-medium">{card.type === "email_sent" ? "Email sent" : "WhatsApp message sent"}</p>
          <p className="text-muted-foreground truncate text-xs">To {card.to}</p>
        </SimpleRow>
      );
    case "memory_saved":
      return (
        <SimpleRow
          icon={Brain}
          action={
            <Link href="/memory" className="text-brand text-xs">
              Manage
            </Link>
          }
        >
          <p className="text-muted-foreground text-xs">Saved to memory</p>
          <p className="truncate">{card.memory.content}</p>
        </SimpleRow>
      );
    case "memories":
      return card.items.length ? (
        <Shell className="p-3 text-sm">
          <p className="text-muted-foreground mb-2 flex items-center gap-1.5 text-xs">
            <Brain className="size-3.5" /> From your memory
          </p>
          <ul className="list-disc space-y-1 pl-5">
            {card.items.map((m) => (
              <li key={m.id}>{m.content}</li>
            ))}
          </ul>
        </Shell>
      ) : null;
    case "vault_items":
      return (
        <SimpleRow
          icon={KeyRound}
          action={
            <Button asChild size="sm" variant="outline">
              <Link href="/vault">Open vault</Link>
            </Button>
          }
        >
          <p className="font-medium">{card.items.length} vault item(s)</p>
          <p className="text-muted-foreground truncate text-xs">{card.items.map((i) => i.name).join(", ") || "None"}</p>
        </SimpleRow>
      );
    case "reminder":
      return (
        <SimpleRow
          icon={Bell}
          action={
            <Link href="/automations" className="text-brand text-xs">
              View
            </Link>
          }
        >
          <p className="font-medium">{card.message}</p>
          <p className="text-muted-foreground text-xs">{card.when}</p>
        </SimpleRow>
      );
    case "automation":
      return (
        <SimpleRow
          icon={CalendarClock}
          action={
            <Link href="/automations" className="text-brand text-xs">
              View
            </Link>
          }
        >
          <p className="font-medium">{card.name}</p>
          <p className="text-muted-foreground text-xs">{card.schedule}</p>
        </SimpleRow>
      );
    case "briefing":
      return (
        <Shell>
          <BriefingView briefing={card.briefing} />
        </Shell>
      );
    default:
      return null;
  }
}
