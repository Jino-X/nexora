"use client";

import {
  ArrowRight,
  CloudSun,
  Compass,
  Fuel,
  Hospital,
  Hotel,
  Landmark,
  MapPin,
  Newspaper,
  UtensilsCrossed,
} from "lucide-react";
import Link from "next/link";

import { NewsList, WeatherCard } from "@/components/assistant/result-cards";
import { ErrorState, IconTile, PageHeader, type Tone } from "@/components/common";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useMe, useNews, useWeather } from "@/lib/api/hooks";

const PLACE_SHORTCUTS: { id: string; label: string; icon: typeof Fuel; tone: Tone }[] = [
  { id: "petrol_pump", label: "Petrol pumps", icon: Fuel, tone: "rose" },
  { id: "hotel", label: "Hotels", icon: Hotel, tone: "pink" },
  { id: "restaurant", label: "Restaurants", icon: UtensilsCrossed, tone: "amber" },
  { id: "hospital", label: "Hospitals", icon: Hospital, tone: "emerald" },
  { id: "atm", label: "ATMs", icon: Landmark, tone: "sky" },
];

export default function DiscoverPage() {
  const me = useMe();
  const hasHome = me.data?.preferences.home_latitude != null;
  const weather = useWeather(null, null, hasHome);
  const news = useNews(undefined, undefined, 8);

  return (
    <div>
      <PageHeader
        tone="cyan"
        title="Discover"
        icon={Compass}
        description="News, weather and places around you, from open data sources."
      />
      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="flex items-center gap-2 text-sm">
              <Newspaper className="text-brand size-4" /> Top stories
            </CardTitle>
            <Link href="/discover/news" className="text-brand inline-flex items-center gap-1 text-xs">
              More <ArrowRight className="size-3" />
            </Link>
          </CardHeader>
          <CardContent className="px-0">
            {news.isPending ? (
              <Skeleton className="mx-4 h-60" />
            ) : news.error ? (
              <ErrorState error={news.error} className="mx-4" />
            ) : (
              <NewsList items={news.data ?? []} limit={8} />
            )}
          </CardContent>
        </Card>
        <div className="space-y-4">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle className="flex items-center gap-2 text-sm">
                <CloudSun className="text-brand size-4" /> Weather
              </CardTitle>
              <Link href="/discover/weather" className="text-brand inline-flex items-center gap-1 text-xs">
                Forecast <ArrowRight className="size-3" />
              </Link>
            </CardHeader>
            <CardContent>
              {!hasHome ? (
                <p className="text-muted-foreground text-sm">
                  <Link href="/discover/weather" className="text-brand underline-offset-2 hover:underline">
                    Check weather for your location
                  </Link>{" "}
                  or set a home location in Settings.
                </p>
              ) : weather.isPending ? (
                <Skeleton className="h-36" />
              ) : weather.error ? (
                <ErrorState error={weather.error} />
              ) : weather.data ? (
                <WeatherCard
                  report={{ ...weather.data, location_label: me.data?.preferences.home_label ?? null }}
                  compact
                />
              ) : null}
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-sm">
                <MapPin className="text-brand size-4" /> Nearby
              </CardTitle>
            </CardHeader>
            <CardContent className="grid grid-cols-2 gap-2">
              {PLACE_SHORTCUTS.map((p) => (
                <Link
                  key={p.id}
                  href={`/discover/nearby?category=${p.id}`}
                  className="bg-background/40 hover:border-brand/40 flex items-center gap-2.5 rounded-2xl border px-3 py-2.5 text-sm font-medium transition-all hover:-translate-y-0.5"
                >
                  <IconTile icon={p.icon} tone={p.tone} size="sm" /> {p.label}
                </Link>
              ))}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
