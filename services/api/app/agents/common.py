"""Helpers shared by tool modules."""

from __future__ import annotations

from app.assistant.tools import Location, ToolContext
from app.core.exceptions import ValidationFailedError


async def resolve_location(ctx: ToolContext, place: str | None) -> Location:
    """Named place, then the device location shared for this request, then the saved home location."""
    if place and place.strip().lower() not in ("here", "my location", "current location", "near me"):
        results = await ctx.services.places.geocode(place, limit=1)
        if not results:
            raise ValidationFailedError(f"I couldn't find a place called '{place}'", code="place_not_found")
        top = results[0]
        return Location(top.latitude, top.longitude, top.label.split(",")[0])
    if ctx.location is not None:
        return ctx.location
    prefs = ctx.preferences
    if prefs.get("home_latitude") is not None and prefs.get("home_longitude") is not None:
        return Location(float(prefs["home_latitude"]), float(prefs["home_longitude"]), prefs.get("home_label"))
    raise ValidationFailedError(
        "I need a location. Share your location in the app, set a home location in Settings, or name a place.",
        code="location_required",
    )


def km(meters: int | None) -> str:
    if meters is None:
        return "?"
    return f"{meters} m" if meters < 1000 else f"{meters / 1000:.1f} km"
