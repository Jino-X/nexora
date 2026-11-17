"use client";

import { Loader2, LocateFixed, MapPin } from "lucide-react";
import dynamic from "next/dynamic";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { PlacesList } from "@/components/assistant/result-cards";
import { EmptyState, ErrorState, PageHeader } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { useGeolocation } from "@/hooks/use-geolocation";
import { useMe, useNearby } from "@/lib/api/hooks";
import { cn } from "@/lib/utils";

const PlacesMap = dynamic(() => import("@/components/maps/places-map"), {
  ssr: false,
  loading: () => <Skeleton className="h-[420px]" />,
});

const CATEGORIES = [
  ["petrol_pump", "Petrol pumps"],
  ["ev_charging", "EV charging"],
  ["hotel", "Hotels"],
  ["restaurant", "Restaurants"],
  ["cafe", "Cafes"],
  ["hospital", "Hospitals"],
  ["pharmacy", "Pharmacies"],
  ["atm", "ATMs"],
  ["bank", "Banks"],
  ["supermarket", "Supermarkets"],
  ["parking", "Parking"],
  ["police", "Police"],
] as const;

function NearbyInner() {
  const params = useSearchParams();
  const [category, setCategory] = useState(params.get("category") ?? "petrol_pump");
  const [radius, setRadius] = useState(3000);
  const geo = useGeolocation({ auto: true });
  const me = useMe();
  const prefs = me.data?.preferences;
  const [useHome, setUseHome] = useState(false);
  const center =
    geo.coords && !useHome
      ? { latitude: geo.coords.latitude, longitude: geo.coords.longitude }
      : prefs?.home_latitude != null && prefs.home_longitude != null
        ? { latitude: prefs.home_latitude, longitude: prefs.home_longitude }
        : null;
  const places = useNearby(category, center?.latitude, center?.longitude, radius);

  return (
    <div>
      <PageHeader
        tone="rose"
        title="Nearby"
        icon={MapPin}
        description="Places from OpenStreetMap around your location."
      />
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Select value={category} onValueChange={setCategory}>
          <SelectTrigger className="w-48" aria-label="Category">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {CATEGORIES.map(([id, label]) => (
              <SelectItem key={id} value={id}>
                {label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={String(radius)} onValueChange={(v) => setRadius(Number(v))}>
          <SelectTrigger className="w-32" aria-label="Radius">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {[1000, 3000, 5000, 10000].map((r) => (
              <SelectItem key={r} value={String(r)}>
                {r / 1000} km
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button
          variant="outline"
          onClick={() => {
            setUseHome(false);
            geo.request();
          }}
        >
          {geo.status === "locating" ? <Loader2 className="animate-spin" /> : <LocateFixed />}{" "}
          {geo.coords ? "Refresh location" : "Use my location"}
        </Button>
        {prefs?.home_latitude != null && (
          <Button variant="ghost" onClick={() => setUseHome(true)} className={cn(useHome && "bg-muted")}>
            Around home
          </Button>
        )}
      </div>

      {!center ? (
        <EmptyState
          icon={LocateFixed}
          title="Share your location"
          description={
            geo.error ??
            "Nexora asks your browser for location only when you press the button. It isn't stored unless you save a home location."
          }
          action={
            <Button onClick={geo.request}>
              <LocateFixed /> Use my location
            </Button>
          }
        />
      ) : (
        <div className="grid gap-4 lg:grid-cols-[1.3fr_1fr]">
          <Card className="overflow-hidden p-0">
            <PlacesMap center={center} places={places.data ?? []} height={420} />
          </Card>
          <Card className="overflow-hidden p-0">
            {places.isPending ? (
              <div className="space-y-2 p-4">
                {Array.from({ length: 5 }, (_, i) => (
                  <Skeleton key={i} className="h-12" />
                ))}
              </div>
            ) : places.error ? (
              <ErrorState error={places.error} onRetry={() => places.refetch()} className="m-4" />
            ) : places.data?.length ? (
              <PlacesList places={places.data} />
            ) : (
              <p className="text-muted-foreground p-6 text-center text-sm">
                Nothing found within {radius / 1000} km. Try a larger radius.
              </p>
            )}
            <p className="text-muted-foreground border-t px-3 py-1.5 text-[0.7rem]">© OpenStreetMap contributors</p>
          </Card>
        </div>
      )}
    </div>
  );
}

export default function NearbyPage() {
  return (
    <Suspense>
      <NearbyInner />
    </Suspense>
  );
}
