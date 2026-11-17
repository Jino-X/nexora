"""The central assistant graph (LangGraph).

load_context -> retrieve_memory -> agent -> (authorize -> execute -> agent)* -> persist

Text, voice and automations all run this graph, so authorization and tool behaviour are identical
across channels. Events are streamed with LangGraph's custom stream writer:
token, tool_start, tool_end, approval_required, status.
"""

from __future__ import annotations

import time
from datetime import datetime
from functools import lru_cache
from typing import Any
from zoneinfo import ZoneInfo

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.runtime import Runtime
from pydantic import ValidationError

from app.assistant.executor import create_approval, execute_tool
from app.assistant.prompts import build_system_prompt
from app.assistant.state import TurnContext, TurnState
from app.assistant.tools import ToolContext
from app.core.permissions import evaluate
from app.database import models as m
from app.database import repositories as repo
from app.database.session import session_scope
from app.llm.base import ChatMessage, ToolCall


def _tool_context(rt: TurnContext, session: Any) -> ToolContext:
    return ToolContext(
        services=rt.services,
        session=session,
        user_id=rt.user_id,
        conversation_id=rt.conversation_id,
        run_id=rt.run_id,
        channel=rt.channel,
        timezone=rt.timezone,
        location=rt.location,
        preferences=rt.preferences,
    )


def available_tools(rt: TurnContext) -> list[dict[str, Any]]:
    schemas = []
    for spec in rt.services.tools.all():
        if rt.channel not in spec.channels:
            continue
        perm = rt.permissions.get(spec.name)
        if perm is not None and not perm.enabled:
            continue
        if spec.category == "memory" and not rt.preferences.get("memory_enabled", True):
            continue
        if spec.name == "youtube_search" and not rt.services.youtube.configured:
            continue
        schemas.append(spec.json_schema())
    return schemas


# ---- nodes -------------------------------------------------------------------------------------


async def load_context(state: TurnState, runtime: Runtime[TurnContext]) -> dict[str, Any]:
    rt = runtime.context
    limit = rt.services.settings.llm_max_context_messages
    async with session_scope(rt.services.sessionmaker) as s:
        rows = await repo.recent_messages(s, rt.user_id, rt.conversation_id, limit + 2)
        rt.permissions = await repo.tool_permissions(s, rt.user_id)
        rt.connected = await repo.connected_providers(s, rt.user_id)
    history = [
        ChatMessage(role=row.role, content=row.content)  # type: ignore[arg-type]
        for row in rows
        if row.run_id != rt.run_id
        and row.role in ("user", "assistant")
        and row.content
        and row.status in ("complete", "cancelled")
    ][-limit:]
    return {"history": history, "working": [], "steps": 0, "tool_trace": [], "cards": [], "approvals": []}


async def retrieve_memory(state: TurnState, runtime: Runtime[TurnContext]) -> dict[str, Any]:
    rt = runtime.context
    memories: list[dict[str, Any]] = []
    if rt.preferences.get("memory_enabled", True) and len(state["user_text"]) > 3:
        async with session_scope(rt.services.sessionmaker) as s:
            hits = await rt.services.memory.search(
                s, rt.user_id, state["user_text"], limit=5, min_score=0.35, touch=True
            )
        memories = [{"id": str(mem.id), "content": mem.content} for mem, _ in hits]
    now_local = datetime.now(ZoneInfo(rt.timezone))
    prompt = build_system_prompt(
        name=rt.display_name,
        now_local=now_local,
        timezone=rt.timezone,
        location_label=rt.location.label if rt.location else None,
        has_location=rt.location is not None,
        language=rt.language,
        style=str(rt.preferences.get("response_style", "concise")),
        channel=rt.channel,
        memories=memories,
    )
    return {"memories": memories, "system_prompt": prompt}


async def agent(state: TurnState, runtime: Runtime[TurnContext]) -> dict[str, Any]:
    rt = runtime.context
    write = runtime.stream_writer
    steps = state.get("steps", 0)
    messages = [
        ChatMessage("system", state["system_prompt"]),
        *state.get("history", []),
        ChatMessage("user", state["user_text"]),
        *state.get("working", []),
    ]
    max_steps = rt.services.settings.llm_max_tool_steps
    tools = available_tools(rt) if steps < max_steps else None

    async def on_token(token: str) -> None:
        rt.visible.append(token)
        write({"type": "token", "text": token})

    started = time.perf_counter()
    response = None
    try:
        response = await rt.llm.chat(
            messages, tools=tools, on_token=on_token, max_tokens=350 if rt.channel == "voice" else None
        )
    finally:
        duration = int((time.perf_counter() - started) * 1000)
        async with session_scope(rt.services.sessionmaker) as s:
            s.add(
                m.ExecutionLog(
                    user_id=rt.user_id,
                    run_id=rt.run_id,
                    conversation_id=rt.conversation_id,
                    event_type="llm_call",
                    name=f"agent_step_{steps}",
                    status="ok" if response else "error",
                    duration_ms=duration,
                    provider=response.provider if response else None,
                    model=response.model if response else None,
                    input_tokens=response.usage.input_tokens if response else 0,
                    output_tokens=response.usage.output_tokens if response else 0,
                    details={"channel": rt.channel, "tools_offered": len(tools or [])},
                )
            )
    rt.usage["input_tokens"] += response.usage.input_tokens
    rt.usage["output_tokens"] += response.usage.output_tokens
    llm_meta = {"provider": response.provider, "model": response.model, "offline": response.offline}
    known = {t["function"]["name"] for t in tools or []}
    calls = [c for c in response.tool_calls if c.name in known]
    if calls:
        write({"type": "status", "text": "Working on it..."})
        working = [*state.get("working", []), ChatMessage("assistant", response.content, tool_calls=calls)]
        return {"working": working, "pending": calls, "steps": steps + 1, "llm": llm_meta}
    return {"pending": [], "final_text": "".join(rt.visible).strip(), "llm": llm_meta, "steps": steps + 1}


async def authorize(state: TurnState, runtime: Runtime[TurnContext]) -> dict[str, Any]:
    rt = runtime.context
    write = runtime.stream_writer
    working = list(state.get("working", []))
    approvals = list(state.get("approvals", []))
    trace = list(state.get("tool_trace", []))
    authorized: list[dict[str, Any]] = []
    async with session_scope(rt.services.sessionmaker) as s:
        for call in state.get("pending", []):
            spec = rt.services.tools.get(call.name)
            if spec is None:
                working.append(_tool_msg(call, '{"ok": false, "message": "Unknown tool"}'))
                continue
            try:
                args = spec.args_model.model_validate(call.arguments or {})
            except ValidationError as exc:
                errors = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()[:5])
                working.append(_tool_msg(call, f'{{"ok": false, "message": "Invalid arguments: {errors}"}}'))
                trace.append({"id": call.id, "tool": call.name, "status": "invalid_arguments"})
                continue
            decision = evaluate(
                spec, channel=rt.channel, permissions=rt.permissions, connected=rt.connected, preferences=rt.preferences
            )
            if not decision.allowed:
                payload = {"ok": False, "message": decision.reason, "error_code": decision.code}
                working.append(_tool_msg(call, _json(payload)))
                trace.append({"id": call.id, "tool": call.name, "status": "denied", "reason": decision.code})
                write(
                    {
                        "type": "tool_end",
                        "id": call.id,
                        "tool": call.name,
                        "ok": False,
                        "message": decision.reason,
                        "error_code": decision.code,
                    }
                )
                continue
            if decision.needs_approval:
                approval = await create_approval(_tool_context(rt, s), spec, args)
                info = {
                    "approval_id": str(approval.id),
                    "tool": spec.name,
                    "summary": approval.summary,
                    "expires_at": approval.expires_at.isoformat(),
                }
                approvals.append(info)
                write({"type": "approval_required", **info})
                working.append(
                    _tool_msg(
                        call,
                        _json(
                            {
                                "ok": True,
                                "status": "approval_required",
                                "message": "Waiting for the user's approval in the app.",
                                "summary": approval.summary,
                            }
                        ),
                    )
                )
                trace.append(
                    {"id": call.id, "tool": call.name, "status": "approval_required", "approval_id": str(approval.id)}
                )
                continue
            authorized.append({"call": call, "args": args})
    return {"working": working, "approvals": approvals, "tool_trace": trace, "authorized": authorized, "pending": []}


async def execute(state: TurnState, runtime: Runtime[TurnContext]) -> dict[str, Any]:
    rt = runtime.context
    write = runtime.stream_writer
    working = list(state.get("working", []))
    cards = list(state.get("cards", []))
    trace = list(state.get("tool_trace", []))
    for item in state.get("authorized", []):
        call: ToolCall = item["call"]
        spec = rt.services.tools.get(call.name)
        assert spec is not None
        write({"type": "tool_start", "id": call.id, "tool": call.name, "category": spec.category})
        started = time.perf_counter()
        async with session_scope(rt.services.sessionmaker) as s:
            result = await execute_tool(_tool_context(rt, s), spec, item["args"])
        duration = int((time.perf_counter() - started) * 1000)
        event: dict[str, Any] = {
            "type": "tool_end",
            "id": call.id,
            "tool": call.name,
            "ok": result.ok,
            "message": result.message,
            "duration_ms": duration,
        }
        if result.error_code:
            event["error_code"] = result.error_code
        if result.card:
            event["card"] = result.card
            cards.append({"tool": call.name, **result.card})
        write(event)
        trace.append(
            {
                "id": call.id,
                "tool": call.name,
                "status": "ok" if result.ok else "error",
                "message": result.message[:300],
                "duration_ms": duration,
            }
        )
        working.append(_tool_msg(call, result.for_llm()))
    return {"working": working, "cards": cards, "tool_trace": trace, "authorized": []}


async def persist(state: TurnState, runtime: Runtime[TurnContext]) -> dict[str, Any]:
    rt = runtime.context
    text = state.get("final_text") or "".join(rt.visible).strip()
    if not text:
        text = "Done." if state.get("tool_trace") else "I'm not sure how to help with that."
    meta = {
        **state.get("llm", {}),
        "cards": state.get("cards", []),
        "approvals": state.get("approvals", []),
        "usage": rt.usage,
        "memories_used": len(state.get("memories", [])),
    }
    async with session_scope(rt.services.sessionmaker) as s:
        conv = await repo.get_owned(s, m.Conversation, rt.user_id, rt.conversation_id, label="Conversation")
        msg = await repo.add_message(
            s,
            conv,
            role="assistant",
            content=text,
            run_id=rt.run_id,
            channel=rt.channel,
            tool_calls=state.get("tool_trace", []),
            meta=meta,
        )
    return {"final_text": text, "message_id": str(msg.id)}


# ---- wiring ------------------------------------------------------------------------------------


def _tool_msg(call: ToolCall, content: str) -> ChatMessage:
    return ChatMessage("tool", content, tool_call_id=call.id, name=call.name)


def _json(payload: dict[str, Any]) -> str:
    import json

    return json.dumps(payload, default=str, ensure_ascii=False)


def _after_agent(state: TurnState) -> str:
    return "authorize" if state.get("pending") else "persist"


def _after_authorize(state: TurnState) -> str:
    return "execute" if state.get("authorized") else "agent"


@lru_cache(maxsize=1)
def build_graph() -> CompiledStateGraph:
    graph = StateGraph(TurnState, context_schema=TurnContext)
    graph.add_node("load_context", load_context)
    graph.add_node("retrieve_memory", retrieve_memory)
    graph.add_node("agent", agent)
    graph.add_node("authorize", authorize)
    graph.add_node("execute", execute)
    graph.add_node("persist", persist)
    graph.add_edge(START, "load_context")
    graph.add_edge("load_context", "retrieve_memory")
    graph.add_edge("retrieve_memory", "agent")
    graph.add_conditional_edges("agent", _after_agent, {"authorize": "authorize", "persist": "persist"})
    graph.add_conditional_edges("authorize", _after_authorize, {"execute": "execute", "agent": "agent"})
    graph.add_edge("execute", "agent")
    graph.add_edge("persist", END)
    return graph.compile()
