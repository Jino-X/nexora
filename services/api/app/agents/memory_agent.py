"""Personal memory tools."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.assistant.tools import ToolContext, ToolRegistry, ToolResult, ToolSpec


class SaveArgs(BaseModel):
    content: str = Field(min_length=3, max_length=2000, description="The fact to remember, written in third person")
    kind: Literal["profile", "preference", "fact", "project", "note"] = "fact"


class SearchArgs(BaseModel):
    query: str = Field(min_length=1, max_length=300)
    limit: int = Field(5, ge=1, le=10)


async def memory_save(ctx: ToolContext, args: SaveArgs) -> ToolResult:
    retention = ctx.preferences.get("memory_retention_days")
    memory = await ctx.services.memory.create(
        ctx.session,
        ctx.user_id,
        args.content,
        kind=args.kind,
        source="assistant",
        source_conversation_id=ctx.conversation_id,
        retention_days=retention,
    )
    return ToolResult(
        ok=True,
        message="Saved to your memory.",
        data={"id": str(memory.id), "content": memory.content},
        card={"type": "memory_saved", "memory": {"id": str(memory.id), "content": memory.content, "kind": memory.kind}},
    )


async def memory_search(ctx: ToolContext, args: SearchArgs) -> ToolResult:
    hits = await ctx.services.memory.search(ctx.session, ctx.user_id, args.query, limit=args.limit, touch=True)
    data = [
        {"content": mem.content, "kind": mem.kind, "saved": mem.created_at.date().isoformat(), "score": round(score, 3)}
        for mem, score in hits
    ]
    msg = (
        ("Here's what I remember: " + "; ".join(d["content"] for d in data[:3]))
        if data
        else "I don't have anything saved about that."
    )
    return ToolResult(
        ok=True,
        message=msg,
        data=data,
        card={
            "type": "memories",
            "items": [{"id": str(mem.id), "content": mem.content, "kind": mem.kind} for mem, _ in hits],
        },
    )


def register(registry: ToolRegistry) -> None:
    registry.register(
        ToolSpec(
            name="memory_save",
            category="memory",
            args_model=SaveArgs,
            handler=memory_save,
            risk="write",
            description="Save a durable fact about the user ONLY when they explicitly ask you to remember it. "
            "Never save passwords, keys or other secrets.",
        )
    )
    registry.register(
        ToolSpec(
            name="memory_search",
            category="memory",
            args_model=SearchArgs,
            handler=memory_search,
            description="Search what the user previously asked you to remember (projects, preferences, facts).",
        )
    )
