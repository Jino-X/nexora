"""Weather tools (Open-Meteo)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.agents.common import resolve_location
from app.assistant.tools import ToolContext, ToolRegistry, ToolResult, ToolSpec


class WeatherArgs(BaseModel):
    place: str | None = Field(None, description="City or place name. Omit to use the user's current location.")
    days: int = Field(1, ge=1, le=7, description="Number of forecast days to include (1 = today)")


async def weather_forecast(ctx: ToolContext, args: WeatherArgs) -> ToolResult:
    loc = await resolve_location(ctx, args.place)
    report = await ctx.services.weather.forecast(loc.latitude, loc.longitude, days=max(args.days, 2))
    report.location_label = loc.label
    today = report.daily[0] if report.daily else None
    cur = report.current
    where = f" in {loc.label}" if loc.label else ""
    message = f"It's {cur.temperature_c:.0f}°C and {cur.description.lower()}{where}"
    if today:
        message += (
            f"; today {today.temperature_min_c:.0f}–{today.temperature_max_c:.0f}°C"
            f", {today.precipitation_probability_max or 0:.0f}% chance of rain"
        )
    message += "."
    data = {
        "location": loc.label,
        "current": {
            "temp_c": cur.temperature_c,
            "feels_like_c": cur.apparent_temperature_c,
            "conditions": cur.description,
            "humidity": cur.humidity_percent,
            "wind_kmh": cur.wind_speed_kmh,
        },
        "days": [
            {
                "date": d.date,
                "conditions": d.description,
                "min_c": d.temperature_min_c,
                "max_c": d.temperature_max_c,
                "rain_chance": d.precipitation_probability_max,
                "rain_mm": d.precipitation_sum_mm,
            }
            for d in report.daily[: args.days]
        ],
        "source": report.attribution,
    }
    return ToolResult(
        ok=True, message=message, data=data, card={"type": "weather", "report": report.model_dump(mode="json")}
    )


def register(registry: ToolRegistry) -> None:
    registry.register(
        ToolSpec(
            name="weather_forecast",
            category="weather",
            args_model=WeatherArgs,
            handler=weather_forecast,
            description="Get current weather and the daily forecast (temperature, rain, wind) for a place or the "
            "user's location.",
        )
    )
