"""YouTube and music tools (official APIs, links and embeds only)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.assistant.tools import ToolContext, ToolRegistry, ToolResult, ToolSpec


class YouTubeArgs(BaseModel):
    query: str = Field(min_length=1, max_length=200)
    kind: Literal["video", "channel", "playlist"] = "video"
    max_results: int = Field(6, ge=1, le=12)


async def youtube_search(ctx: ToolContext, args: YouTubeArgs) -> ToolResult:
    results = await ctx.services.youtube.search(args.query, kind=args.kind, max_results=args.max_results)
    msg = f"Found {len(results)} YouTube {args.kind}s for '{args.query}'." if results else "No YouTube results."
    if results:
        msg += f" Top result: {results[0].title}."
    data = [{"title": r.title, "channel": r.channel_title, "url": r.url} for r in results]
    return ToolResult(
        ok=True, message=msg, data=data, card={"type": "youtube", "items": [r.model_dump() for r in results]}
    )


class MusicArgs(BaseModel):
    query: str = Field(min_length=1, max_length=150, description="Song, artist, mood or genre, e.g. 'relaxing piano'")
    limit: int = Field(8, ge=1, le=15)


async def music_search(ctx: ToolContext, args: MusicArgs) -> ToolResult:
    provider = ctx.services.music
    results = await provider.search(args.query, args.limit)
    msg = f"Here's some {args.query} music." if results else f"I couldn't find music for '{args.query}'."
    data = [{"title": r.title, "artist": r.artist, "kind": r.kind, "url": r.url} for r in results]
    return ToolResult(
        ok=True,
        message=msg,
        data=data,
        card={"type": "music", "provider": provider.name, "items": [r.model_dump() for r in results]},
    )


def register(registry: ToolRegistry) -> None:
    registry.register(
        ToolSpec(
            name="youtube_search",
            category="youtube",
            args_model=YouTubeArgs,
            handler=youtube_search,
            description="Search YouTube videos, channels or playlists. Results show as playable official embeds.",
        )
    )
    registry.register(
        ToolSpec(
            name="music_search",
            category="music",
            args_model=MusicArgs,
            handler=music_search,
            description="Find songs or playlists to play (official previews, embeds and links). "
            "Use for 'play some music'.",
        )
    )
