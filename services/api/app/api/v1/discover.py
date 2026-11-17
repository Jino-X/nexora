"""Location, weather, news, YouTube and music endpoints (direct UI access to the same providers the
assistant tools use)."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Query

from app.api.deps import DB, CurrentUser, ServicesDep
from app.database import repositories as repo
from app.integrations.maps.osm import PLACE_CATEGORIES, GeocodeResult, Place
from app.integrations.music.providers import MusicResult
from app.integrations.news.rss import NewsItem
from app.integrations.weather.open_meteo import WeatherReport
from app.integrations.youtube.client import YouTubeResult

location = APIRouter(prefix="/location", tags=["location"])
weather = APIRouter(prefix="/weather", tags=["weather"])
news = APIRouter(prefix="/news", tags=["news"])
youtube = APIRouter(prefix="/youtube", tags=["youtube"])
music = APIRouter(prefix="/music", tags=["music"])


@location.get("/categories")
async def categories(user: CurrentUser) -> list[dict[str, str]]:
    return [{"id": key, "label": value["label"]} for key, value in PLACE_CATEGORIES.items()]


@location.get("/geocode", response_model=list[GeocodeResult])
async def geocode(
    user: CurrentUser,
    services: ServicesDep,
    q: str = Query(min_length=2, max_length=200),
    limit: int = Query(5, ge=1, le=10),
) -> list[GeocodeResult]:
    return await services.places.geocode(q, limit=limit)


@location.get("/reverse")
async def reverse(
    user: CurrentUser, services: ServicesDep, lat: float = Query(ge=-90, le=90), lon: float = Query(ge=-180, le=180)
) -> dict[str, str | None]:
    return {"label": await services.places.reverse(lat, lon)}


@location.get("/nearby", response_model=list[Place])
async def nearby(
    user: CurrentUser,
    services: ServicesDep,
    category: str = Query(max_length=40),
    lat: float = Query(ge=-90, le=90),
    lon: float = Query(ge=-180, le=180),
    radius_m: int = Query(3000, ge=200, le=25000),
    limit: int = Query(15, ge=1, le=30),
) -> list[Place]:
    return await services.places.nearby(category, lat, lon, radius_m=radius_m, limit=limit)


@weather.get("", response_model=WeatherReport)
async def get_weather(
    user: CurrentUser,
    services: ServicesDep,
    db: DB,
    lat: float | None = Query(None, ge=-90, le=90),
    lon: float | None = Query(None, ge=-180, le=180),
    days: int = Query(7, ge=1, le=16),
) -> WeatherReport:
    label = None
    if lat is None or lon is None:
        prefs = await repo.get_preferences(db, user.id)
        if prefs.home_latitude is None or prefs.home_longitude is None:
            from app.core.exceptions import ValidationFailedError

            raise ValidationFailedError("Provide lat/lon or set a home location", code="location_required")
        lat, lon, label = prefs.home_latitude, prefs.home_longitude, prefs.home_label
    report = await services.weather.forecast(lat, lon, days=days)
    report.location_label = label
    return report


@news.get("/categories")
async def news_categories(user: CurrentUser, services: ServicesDep) -> dict[str, list[str]]:
    return {"categories": services.news.categories, "sources": sorted({f["name"] for f in services.news.feeds})}


@news.get("", response_model=list[NewsItem])
async def headlines(
    user: CurrentUser,
    services: ServicesDep,
    db: DB,
    category: str | None = Query(None, max_length=32),
    q: str | None = Query(None, max_length=100),
    limit: int = Query(20, ge=1, le=60),
) -> list[NewsItem]:
    if category:
        cats: list[str] | None = [category]
    else:
        cats = (await repo.get_preferences(db, user.id)).news_categories or None
    return await services.news.headlines(cats, limit=limit, query=q)


@youtube.get("/search", response_model=list[YouTubeResult])
async def youtube_search(
    user: CurrentUser,
    services: ServicesDep,
    q: str = Query(min_length=1, max_length=200),
    kind: Literal["video", "channel", "playlist"] = "video",
    limit: int = Query(12, ge=1, le=25),
) -> list[YouTubeResult]:
    services.rate_limiter.check(f"youtube:{user.id}", 30)
    return await services.youtube.search(q, kind=kind, max_results=limit)


@music.get("/search", response_model=list[MusicResult])
async def music_search(
    user: CurrentUser,
    services: ServicesDep,
    q: str = Query(min_length=1, max_length=150),
    limit: int = Query(12, ge=1, le=25),
) -> list[MusicResult]:
    return await services.music.search(q, limit)


@music.get("/provider")
async def music_provider(user: CurrentUser, services: ServicesDep) -> dict[str, str]:
    return {"provider": services.music.name}
