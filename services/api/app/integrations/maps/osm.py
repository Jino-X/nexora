"""OpenStreetMap places adapter: Nominatim (geocoding) + Overpass (nearby search).

Public endpoints have strict usage policies (Nominatim: max 1 request/second, a valid User-Agent,
caching). They suit development and light personal use only. For production, point NOMINATIM_URL
and OVERPASS_URL at self-hosted or commercial instances. Data (c) OpenStreetMap contributors, ODbL."""

from __future__ import annotations

import asyncio
import math
import time
from typing import Any
from urllib.parse import quote

import httpx
from pydantic import BaseModel

from app.core.exceptions import UpstreamError, ValidationFailedError
from app.integrations.base import TTLCache, fetch_json, round_coord

ATTRIBUTION = "(c) OpenStreetMap contributors (ODbL)"

PLACE_CATEGORIES: dict[str, dict[str, Any]] = {
    "petrol_pump": {"label": "Petrol pumps", "tags": [("amenity", "fuel")]},
    "ev_charging": {"label": "EV charging", "tags": [("amenity", "charging_station")]},
    "hotel": {"label": "Hotels", "tags": [("tourism", "hotel"), ("tourism", "guest_house"), ("tourism", "motel")]},
    "restaurant": {"label": "Restaurants", "tags": [("amenity", "restaurant"), ("amenity", "fast_food")]},
    "cafe": {"label": "Cafes", "tags": [("amenity", "cafe")]},
    "hospital": {"label": "Hospitals", "tags": [("amenity", "hospital"), ("amenity", "clinic")]},
    "pharmacy": {"label": "Pharmacies", "tags": [("amenity", "pharmacy")]},
    "atm": {"label": "ATMs", "tags": [("amenity", "atm")]},
    "bank": {"label": "Banks", "tags": [("amenity", "bank")]},
    "parking": {"label": "Parking", "tags": [("amenity", "parking")]},
    "police": {"label": "Police", "tags": [("amenity", "police")]},
    "supermarket": {"label": "Supermarkets", "tags": [("shop", "supermarket")]},
}

CATEGORY_ALIASES = {
    "petrol": "petrol_pump",
    "fuel": "petrol_pump",
    "gas station": "petrol_pump",
    "gas": "petrol_pump",
    "petrol bunk": "petrol_pump",
    "diesel": "petrol_pump",
    "charging": "ev_charging",
    "hotels": "hotel",
    "lodge": "hotel",
    "stay": "hotel",
    "food": "restaurant",
    "restaurants": "restaurant",
    "hotel food": "restaurant",
    "coffee": "cafe",
    "hospitals": "hospital",
    "clinic": "hospital",
    "doctor": "hospital",
    "medical": "pharmacy",
    "medicine": "pharmacy",
    "chemist": "pharmacy",
    "cash": "atm",
    "atms": "atm",
    "grocery": "supermarket",
}


def normalize_category(value: str) -> str:
    key = value.strip().lower().replace("-", " ")
    if key.replace(" ", "_") in PLACE_CATEGORIES:
        return key.replace(" ", "_")
    if key in CATEGORY_ALIASES:
        return CATEGORY_ALIASES[key]
    raise ValidationFailedError(f"Unknown place category '{value}'", details={"allowed": sorted(PLACE_CATEGORIES)})


class Place(BaseModel):
    id: str
    name: str
    category: str
    latitude: float
    longitude: float
    distance_m: int | None = None
    address: str | None = None
    opening_hours: str | None = None
    phone: str | None = None
    website: str | None = None
    brand: str | None = None
    directions_url: str
    osm_url: str


class GeocodeResult(BaseModel):
    label: str
    latitude: float
    longitude: float
    type: str | None = None


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def directions_url(lat: float, lon: float, origin: tuple[float, float] | None = None) -> str:
    url = f"https://www.google.com/maps/dir/?api=1&destination={lat:.6f},{lon:.6f}"
    if origin:
        url += f"&origin={origin[0]:.6f},{origin[1]:.6f}"
    return url


def _address(tags: dict[str, str]) -> str | None:
    parts = [tags.get("addr:housenumber"), tags.get("addr:street"), tags.get("addr:suburb"), tags.get("addr:city")]
    joined = ", ".join(p for p in parts if p)
    return joined or tags.get("addr:full")


class OSMPlacesProvider:
    def __init__(
        self, http: httpx.AsyncClient, *, nominatim_url: str, overpass_url: str, user_agent: str, timeout: float = 20.0
    ) -> None:
        self.http = http
        self.nominatim_url = nominatim_url.rstrip("/")
        # Comma-separated list: tried in order (self-hosted first, public instances as fallback).
        self.overpass_urls = [u.strip() for u in overpass_url.split(",") if u.strip()]
        self.headers = {"User-Agent": user_agent}
        self.timeout = timeout
        self.nearby_cache = TTLCache(ttl_seconds=900, max_items=256)
        self.geo_cache = TTLCache(ttl_seconds=86_400, max_items=1024)
        self._nominatim_lock = asyncio.Lock()
        self._last_nominatim = 0.0

    async def _nominatim(self, path: str, params: dict[str, Any], language: str) -> Any:
        async with self._nominatim_lock:  # public policy: at most 1 request per second
            wait = 1.0 - (time.monotonic() - self._last_nominatim)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_nominatim = time.monotonic()
            return await fetch_json(
                self.http,
                "GET",
                f"{self.nominatim_url}{path}",
                provider="Nominatim",
                params={**params, "format": "jsonv2"},
                headers={**self.headers, "Accept-Language": language},
                timeout=self.timeout,
            )

    async def geocode(self, query: str, *, limit: int = 5, language: str = "en") -> list[GeocodeResult]:
        query = query.strip()[:200]
        if not query:
            return []
        key = f"geo:{language}:{query.lower()}:{limit}"
        if (cached := self.geo_cache.get(key)) is not None:
            return cached
        data = await self._nominatim("/search", {"q": query, "limit": limit}, language)
        results = [
            GeocodeResult(
                label=item.get("display_name", ""),
                latitude=float(item["lat"]),
                longitude=float(item["lon"]),
                type=item.get("type"),
            )
            for item in data or []
        ]
        self.geo_cache.set(key, results)
        return results

    async def reverse(self, latitude: float, longitude: float, *, language: str = "en") -> str | None:
        key = f"rev:{language}:{round_coord(latitude)}:{round_coord(longitude)}"
        if (cached := self.geo_cache.get(key)) is not None:
            return cached
        data = await self._nominatim("/reverse", {"lat": latitude, "lon": longitude, "zoom": 14}, language)
        label = (data or {}).get("display_name")
        self.geo_cache.set(key, label)
        return label

    async def _overpass(self, query: str) -> Any:
        """Try each configured endpoint; one short backoff retry on overload (429/5xx/timeout)."""
        last: UpstreamError | None = None
        endpoints = self.overpass_urls if len(self.overpass_urls) > 1 else self.overpass_urls * 2
        for attempt, url in enumerate(endpoints):
            if attempt:
                await asyncio.sleep(min(2.0 * attempt, 4.0))
            try:
                return await fetch_json(
                    self.http,
                    "POST",
                    url,
                    provider="Overpass",
                    data={"data": query},
                    headers=self.headers,
                    timeout=self.timeout + 5,
                )
            except UpstreamError as exc:
                status = (exc.details or {}).get("status") if isinstance(exc.details, dict) else None
                if exc.code not in ("upstream_timeout", "upstream_rate_limited") and status not in (502, 503, 504):
                    raise
                last = exc
        assert last is not None
        raise UpstreamError(
            "The places service is busy right now. Please try again in a minute.", code="places_unavailable"
        ) from last

    @staticmethod
    def build_overpass_query(category: str, latitude: float, longitude: float, radius_m: int, limit: int) -> str:
        selectors = "".join(
            f'nwr["{k}"="{v}"](around:{radius_m},{latitude:.6f},{longitude:.6f});'
            for k, v in PLACE_CATEGORIES[category]["tags"]
        )
        return f"[out:json][timeout:20];({selectors});out center tags {limit * 3};"

    async def nearby(
        self, category: str, latitude: float, longitude: float, *, radius_m: int = 3000, limit: int = 10
    ) -> list[Place]:
        category = normalize_category(category)
        radius_m = max(200, min(radius_m, 25_000))
        limit = max(1, min(limit, 30))
        key = f"{category}:{round_coord(latitude)}:{round_coord(longitude)}:{radius_m}:{limit}"
        if (cached := self.nearby_cache.get(key)) is not None:
            return cached
        query = self.build_overpass_query(category, latitude, longitude, radius_m, limit)
        data = await self._overpass(query)
        places = self._parse(data, category, latitude, longitude)[:limit]
        self.nearby_cache.set(key, places)
        return places

    @staticmethod
    def _parse(data: dict[str, Any], category: str, latitude: float, longitude: float) -> list[Place]:
        places: list[Place] = []
        seen: set[str] = set()
        for el in data.get("elements") or []:
            lat = el.get("lat") or (el.get("center") or {}).get("lat")
            lon = el.get("lon") or (el.get("center") or {}).get("lon")
            if lat is None or lon is None:
                continue
            tags = el.get("tags") or {}
            name = tags.get("name") or tags.get("brand") or PLACE_CATEGORIES[category]["label"].rstrip("s")
            osm_id = f"{el.get('type', 'node')}/{el.get('id')}"
            if osm_id in seen:
                continue
            seen.add(osm_id)
            places.append(
                Place(
                    id=osm_id,
                    name=name,
                    category=category,
                    latitude=float(lat),
                    longitude=float(lon),
                    distance_m=int(haversine_m(latitude, longitude, float(lat), float(lon))),
                    address=_address(tags),
                    opening_hours=tags.get("opening_hours"),
                    phone=tags.get("phone") or tags.get("contact:phone"),
                    website=tags.get("website") or tags.get("contact:website"),
                    brand=tags.get("brand"),
                    directions_url=directions_url(float(lat), float(lon), (latitude, longitude)),
                    osm_url=f"https://www.openstreetmap.org/{quote(osm_id)}",
                )
            )
        places.sort(key=lambda p: p.distance_m or 0)
        return places
