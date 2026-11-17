"""Location tools: nearby places, geocoding and directions links (OpenStreetMap)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.agents.common import km, resolve_location
from app.assistant.tools import ToolContext, ToolRegistry, ToolResult, ToolSpec
from app.integrations.maps.osm import PLACE_CATEGORIES, directions_url

Category = Literal[
    "petrol_pump",
    "ev_charging",
    "hotel",
    "restaurant",
    "cafe",
    "hospital",
    "pharmacy",
    "atm",
    "bank",
    "parking",
    "police",
    "supermarket",
]


class NearbyArgs(BaseModel):
    category: Category = Field(description="Kind of place to look for")
    place: str | None = Field(None, description="Search around this named place instead of the user's location")
    radius_m: int = Field(3000, ge=200, le=25000, description="Search radius in meters")
    limit: int = Field(6, ge=1, le=15)


async def places_nearby(ctx: ToolContext, args: NearbyArgs) -> ToolResult:
    loc = await resolve_location(ctx, args.place)
    places = await ctx.services.places.nearby(
        args.category, loc.latitude, loc.longitude, radius_m=args.radius_m, limit=args.limit
    )
    label = PLACE_CATEGORIES[args.category]["label"].lower()
    if not places:
        msg = f"No {label} found within {km(args.radius_m)}."
    else:
        top = places[0]
        msg = f"Found {len(places)} {label}; the closest is {top.name}, {km(top.distance_m)} away."
    data = [
        {
            "name": p.name,
            "distance": km(p.distance_m),
            "address": p.address,
            "opening_hours": p.opening_hours,
            "phone": p.phone,
        }
        for p in places
    ]
    card = {
        "type": "places",
        "category": args.category,
        "label": PLACE_CATEGORIES[args.category]["label"],
        "center": {"latitude": loc.latitude, "longitude": loc.longitude, "label": loc.label},
        "places": [p.model_dump() for p in places],
        "attribution": "(c) OpenStreetMap contributors",
    }
    return ToolResult(ok=True, message=msg, data=data, card=card)


class DirectionsArgs(BaseModel):
    destination: str = Field(min_length=2, max_length=200, description="Place name or address")


async def directions_link(ctx: ToolContext, args: DirectionsArgs) -> ToolResult:
    results = await ctx.services.places.geocode(args.destination, limit=1)
    if not results:
        return ToolResult(ok=False, message=f"I couldn't find '{args.destination}'.", error_code="place_not_found")
    dest = results[0]
    origin = (ctx.location.latitude, ctx.location.longitude) if ctx.location else None
    url = directions_url(dest.latitude, dest.longitude, origin)
    return ToolResult(
        ok=True,
        message=f"Here are directions to {dest.label.split(',')[0]}.",
        data={"destination": dest.label, "maps_url": url},
        card={"type": "directions", "destination": dest.model_dump(), "url": url},
    )


def register(registry: ToolRegistry) -> None:
    registry.register(
        ToolSpec(
            name="places_nearby",
            category="location",
            args_model=NearbyArgs,
            handler=places_nearby,
            description="Find nearby places such as petrol pumps, hotels, restaurants, hospitals, ATMs or pharmacies "
            "around the user's location or a named place.",
            timeout_seconds=30,
        )
    )
    registry.register(
        ToolSpec(
            name="directions_link",
            category="location",
            args_model=DirectionsArgs,
            handler=directions_link,
            description="Get a map directions link to a destination.",
        )
    )
