"""Open-Meteo forecast adapter. Free for non-commercial use; commercial use requires an
Open-Meteo API subscription (set OPEN_METEO_URL to the customer endpoint). Data: CC BY 4.0."""

from __future__ import annotations

from typing import Any

import httpx
from pydantic import BaseModel

from app.core.exceptions import UpstreamError
from app.integrations.base import TTLCache, fetch_json, round_coord

WMO_CODES: dict[int, str] = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    56: "Light freezing drizzle",
    57: "Dense freezing drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    66: "Light freezing rain",
    67: "Heavy freezing rain",
    71: "Slight snowfall",
    73: "Moderate snowfall",
    75: "Heavy snowfall",
    77: "Snow grains",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Slight snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}

ATTRIBUTION = "Weather data by Open-Meteo.com (CC BY 4.0)"


class CurrentWeather(BaseModel):
    time: str
    temperature_c: float
    apparent_temperature_c: float | None = None
    humidity_percent: float | None = None
    precipitation_mm: float | None = None
    wind_speed_kmh: float | None = None
    weather_code: int
    description: str
    is_day: bool = True


class DailyWeather(BaseModel):
    date: str
    weather_code: int
    description: str
    temperature_max_c: float | None = None
    temperature_min_c: float | None = None
    precipitation_probability_max: float | None = None
    precipitation_sum_mm: float | None = None
    wind_speed_max_kmh: float | None = None
    sunrise: str | None = None
    sunset: str | None = None


class WeatherReport(BaseModel):
    latitude: float
    longitude: float
    timezone: str
    location_label: str | None = None
    current: CurrentWeather
    daily: list[DailyWeather]
    attribution: str = ATTRIBUTION


def _at(values: list[Any] | None, i: int) -> Any:
    return values[i] if values and i < len(values) else None


class OpenMeteoProvider:
    def __init__(self, http: httpx.AsyncClient, base_url: str, timeout: float = 12.0) -> None:
        self.http = http
        self.base_url = base_url
        self.timeout = timeout
        self.cache = TTLCache(ttl_seconds=600, max_items=256)

    async def forecast(self, latitude: float, longitude: float, days: int = 7) -> WeatherReport:
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            raise UpstreamError("Invalid coordinates", code="invalid_coordinates", status_code=422)
        key = f"{round_coord(latitude, 2)}:{round_coord(longitude, 2)}:{days}"
        if cached := self.cache.get(key):
            return cached
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "current": "temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,"
            "weather_code,wind_speed_10m,is_day",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,"
            "precipitation_sum,wind_speed_10m_max,sunrise,sunset",
            "timezone": "auto",
            "forecast_days": max(1, min(days, 16)),
        }
        data = await fetch_json(
            self.http, "GET", self.base_url, provider="Open-Meteo", params=params, timeout=self.timeout
        )
        report = self._parse(data, latitude, longitude)
        self.cache.set(key, report)
        return report

    @staticmethod
    def _parse(data: dict[str, Any], latitude: float, longitude: float) -> WeatherReport:
        cur = data.get("current") or {}
        code = int(cur.get("weather_code") or 0)
        current = CurrentWeather(
            time=str(cur.get("time", "")),
            temperature_c=float(cur.get("temperature_2m", 0.0)),
            apparent_temperature_c=cur.get("apparent_temperature"),
            humidity_percent=cur.get("relative_humidity_2m"),
            precipitation_mm=cur.get("precipitation"),
            wind_speed_kmh=cur.get("wind_speed_10m"),
            weather_code=code,
            description=WMO_CODES.get(code, "Unknown"),
            is_day=bool(cur.get("is_day", 1)),
        )
        d = data.get("daily") or {}
        daily = []
        for i, day in enumerate(d.get("time") or []):
            dcode = int(_at(d.get("weather_code"), i) or 0)
            daily.append(
                DailyWeather(
                    date=day,
                    weather_code=dcode,
                    description=WMO_CODES.get(dcode, "Unknown"),
                    temperature_max_c=_at(d.get("temperature_2m_max"), i),
                    temperature_min_c=_at(d.get("temperature_2m_min"), i),
                    precipitation_probability_max=_at(d.get("precipitation_probability_max"), i),
                    precipitation_sum_mm=_at(d.get("precipitation_sum"), i),
                    wind_speed_max_kmh=_at(d.get("wind_speed_10m_max"), i),
                    sunrise=_at(d.get("sunrise"), i),
                    sunset=_at(d.get("sunset"), i),
                )
            )
        return WeatherReport(
            latitude=latitude, longitude=longitude, timezone=data.get("timezone", "UTC"), current=current, daily=daily
        )
