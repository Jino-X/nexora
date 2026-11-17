"use client";

import type { WeatherReport } from "@nexora/shared-types";
import { CloudSun, Droplets, Loader2, LocateFixed, Search, Sunrise, Sunset } from "lucide-react";
import { useState, type FormEvent } from "react";

import { weatherIcon, WeatherCard } from "@/components/assistant/result-cards";
import { EmptyState, ErrorState, PageHeader } from "@/components/common";
import { Stagger, StaggerItem } from "@/components/fx/motion";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useGeolocation } from "@/hooks/use-geolocation";
import { useGeocode, useMe, useWeather } from "@/lib/api/hooks";

type Day = WeatherReport["daily"][number];

/** Week view: each row has a temperature bar placed on the week's overall min-max range. */
function DailyForecast({ days }: { days: Day[] }) {
  const lows = days.map((d) => d.temperature_min_c ?? 0);
  const highs = days.map((d) => d.temperature_max_c ?? 0);
  const floor = Math.min(...lows);
  const span = Math.max(Math.max(...highs) - floor, 1);
  const today = days[0];

  return (
    <Card>
      <CardContent className="p-2 sm:p-3">
        <Stagger as="ul" className="space-y-1">
          {days.map((d, i) => {
            const lo = d.temperature_min_c ?? 0;
            const hi = d.temperature_max_c ?? 0;
            const rain = Math.round(d.precipitation_probability_max ?? 0);
            return (
              <StaggerItem
                as="li"
                key={d.date}
                className="hover:bg-foreground/5 flex items-center gap-3 rounded-2xl px-3 py-2.5 text-sm transition-colors"
              >
                <span className="w-20 shrink-0">
                  <span className="block font-medium">
                    {i === 0
                      ? "Today"
                      : new Date(`${d.date}T12:00:00`).toLocaleDateString(undefined, { weekday: "long" })}
                  </span>
                  <span className="text-muted-foreground text-xs">
                    {new Date(`${d.date}T12:00:00`).toLocaleDateString(undefined, { day: "numeric", month: "short" })}
                  </span>
                </span>
                <span className="bg-brand/10 grid size-9 shrink-0 place-items-center rounded-xl">
                  {weatherIcon(d.weather_code, "size-5 text-brand")}
                </span>
                <span className="hidden min-w-0 flex-1 truncate sm:block">{d.description}</span>
                <span
                  className={`inline-flex w-12 shrink-0 items-center justify-end gap-0.5 text-xs ${rain >= 40 ? "text-sky-500" : "text-muted-foreground"}`}
                >
                  <Droplets className="size-3" />
                  {rain}%
                </span>
                <span className="text-muted-foreground w-8 shrink-0 text-right tabular-nums">{Math.round(lo)}°</span>
                <span className="bg-foreground/10 relative h-1.5 w-full max-w-28 min-w-14 flex-1 rounded-full sm:flex-none">
                  <span
                    className="absolute inset-y-0 rounded-full bg-gradient-to-r from-sky-400 via-amber-400 to-orange-500"
                    style={{ left: `${((lo - floor) / span) * 100}%`, right: `${100 - ((hi - floor) / span) * 100}%` }}
                  />
                </span>
                <span className="w-8 shrink-0 font-semibold tabular-nums">{Math.round(hi)}°</span>
              </StaggerItem>
            );
          })}
        </Stagger>
        {today?.sunrise && (
          <div className="mt-2 grid grid-cols-2 gap-2">
            <div className="flex items-center gap-3 rounded-2xl bg-amber-500/10 px-4 py-3">
              <Sunrise className="size-5 text-amber-500" />
              <div>
                <p className="text-muted-foreground text-xs">Sunrise</p>
                <p className="font-semibold">{today.sunrise.slice(11)}</p>
              </div>
            </div>
            <div className="flex items-center gap-3 rounded-2xl bg-violet-500/10 px-4 py-3">
              <Sunset className="size-5 text-violet-500" />
              <div>
                <p className="text-muted-foreground text-xs">Sunset</p>
                <p className="font-semibold">{today.sunset?.slice(11)}</p>
              </div>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default function WeatherPage() {
  const me = useMe();
  const geo = useGeolocation();
  const geocode = useGeocode();
  const [place, setPlace] = useState<{ lat: number; lon: number; label: string } | null>(null);
  const [query, setQuery] = useState("");
  const prefs = me.data?.preferences;
  const target =
    place ??
    (geo.coords ? { lat: geo.coords.latitude, lon: geo.coords.longitude, label: "Current location" } : null) ??
    (prefs?.home_latitude != null && prefs.home_longitude != null
      ? { lat: prefs.home_latitude, lon: prefs.home_longitude, label: prefs.home_label ?? "Home" }
      : null);
  const weather = useWeather(target?.lat, target?.lon, Boolean(target));

  async function search(e: FormEvent) {
    e.preventDefault();
    if (!query.trim()) return;
    const results = await geocode.mutateAsync(query.trim());
    if (results[0])
      setPlace({ lat: results[0].latitude, lon: results[0].longitude, label: results[0].label.split(",")[0] });
  }

  return (
    <div>
      <PageHeader tone="amber" title="Weather" icon={CloudSun} description="Forecasts from Open-Meteo for any place." />
      <div className="mb-5 flex flex-col gap-2 sm:flex-row">
        <form onSubmit={search} className="flex flex-1 gap-2">
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search a city, e.g. Madurai"
            aria-label="Place"
          />
          <Button type="submit" variant="outline" disabled={geocode.isPending}>
            {geocode.isPending ? <Loader2 className="animate-spin" /> : <Search />} Search
          </Button>
        </form>
        <Button
          variant="outline"
          onClick={() => {
            setPlace(null);
            geo.request();
          }}
        >
          {geo.status === "locating" ? <Loader2 className="animate-spin" /> : <LocateFixed />} Use my location
        </Button>
      </div>
      {geocode.data?.length === 0 && (
        <p className="text-muted-foreground mb-4 text-sm">No place found for that search.</p>
      )}
      {geo.error && <p className="text-destructive mb-4 text-sm">{geo.error}</p>}

      {!target ? (
        <EmptyState
          tone="amber"
          icon={CloudSun}
          title="Where should I check?"
          description="Search for a place or share your location to see the forecast."
        />
      ) : weather.isPending ? (
        <Skeleton className="h-72" />
      ) : weather.error ? (
        <ErrorState error={weather.error} onRetry={() => weather.refetch()} />
      ) : weather.data ? (
        <div className="grid items-start gap-4 lg:grid-cols-[1fr_1.4fr]">
          <WeatherCard report={{ ...weather.data, location_label: target.label }} compact />
          <DailyForecast days={weather.data.daily} />
        </div>
      ) : null}
    </div>
  );
}
