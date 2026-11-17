"""News tools (RSS aggregation with attribution)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.assistant.tools import ToolContext, ToolRegistry, ToolResult, ToolSpec


class NewsArgs(BaseModel):
    category: str | None = Field(
        None, description="One of: world, india, business, science, technology, ai. Omit for the user's mix."
    )
    query: str | None = Field(None, max_length=100, description="Optional keyword filter")
    limit: int = Field(6, ge=1, le=15)


async def news_headlines(ctx: ToolContext, args: NewsArgs) -> ToolResult:
    categories = [args.category.lower()] if args.category else ctx.preferences.get("news_categories") or None
    items = await ctx.services.news.headlines(categories, limit=args.limit, query=args.query)
    if not items:
        return ToolResult(
            ok=True, message="I couldn't load any headlines right now.", data=[], card={"type": "news", "items": []}
        )
    lines = [f"{i.title} ({i.source})" for i in items[:3]]
    msg = "Top headlines: " + "; ".join(lines) + "."
    data = [
        {"title": i.title, "source": i.source, "published": i.published_at, "summary": i.summary, "link": i.link}
        for i in items
    ]
    return ToolResult(
        ok=True, message=msg, data=data, card={"type": "news", "items": [i.model_dump(mode="json") for i in items]}
    )


def register(registry: ToolRegistry) -> None:
    registry.register(
        ToolSpec(
            name="news_headlines",
            category="news",
            args_model=NewsArgs,
            handler=news_headlines,
            description="Get the latest news headlines with source and link. Use for news, current events, AI or "
            "technology updates. Never invent news.",
        )
    )
