"""LLM providers: Ollama/OpenAI-compatible streaming, think-tag filtering, fallback, offline router."""

from __future__ import annotations

import json
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
import pytest

from app.assistant.offline import OfflineIntentRouter, parse_when, route
from app.llm.base import ChatMessage, LLMError, ThinkTagFilter
from app.llm.factory import FallbackLLM
from app.llm.ollama import OllamaProvider
from app.llm.openai_compat import OpenAICompatibleProvider

TOOLS = [
    {"type": "function", "function": {"name": n, "parameters": {}}}
    for n in (
        "weather_forecast",
        "places_nearby",
        "news_headlines",
        "reminder_create",
        "memory_save",
        "memory_search",
        "youtube_search",
        "music_search",
        "gmail_unread",
        "briefing_generate",
    )
]


def _client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_ollama_streams_tokens_and_tool_calls():
    lines = [
        {"message": {"role": "assistant", "content": "<think>hmm</think>Hel"}, "done": False},
        {"message": {"role": "assistant", "content": "lo"}, "done": False},
        {
            "message": {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"function": {"name": "weather_forecast", "arguments": {"place": "Chennai"}}}],
            },
            "done": False,
        },
        {"message": {"role": "assistant", "content": ""}, "done": True, "prompt_eval_count": 120, "eval_count": 9},
    ]

    def handler(request):
        payload = json.loads(request.content)
        assert payload["think"] is False and payload["model"] == "qwen3:8b" and payload["tools"]
        return httpx.Response(200, content="\n".join(json.dumps(x) for x in lines).encode())

    tokens: list[str] = []

    async def on_token(t):
        tokens.append(t)

    provider = OllamaProvider(_client(handler), base_url="http://ollama", model="qwen3:8b")
    res = await provider.chat([ChatMessage("user", "hi")], tools=TOOLS[:1], on_token=on_token)
    assert "".join(tokens) == "Hello" and res.content == "Hello"
    assert res.tool_calls[0].name == "weather_forecast" and res.tool_calls[0].arguments == {"place": "Chennai"}
    assert res.usage.input_tokens == 120


async def test_ollama_missing_model_is_unavailable():
    provider = OllamaProvider(
        _client(lambda r: httpx.Response(404, json={"error": "model not found"})),
        base_url="http://ollama",
        model="qwen3:8b",
    )
    with pytest.raises(LLMError):
        await provider.chat([ChatMessage("user", "hi")])


async def test_openai_compatible_tool_call_deltas():
    chunks = [
        {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {"index": 0, "id": "call_1", "function": {"name": "news_", "arguments": '{"cat'}}
                        ]
                    }
                }
            ]
        },
        {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [{"index": 0, "function": {"name": "headlines", "arguments": 'egory": "ai"}'}}]
                    }
                }
            ]
        },
        {"choices": [], "usage": {"prompt_tokens": 50, "completion_tokens": 7}},
    ]
    body = "".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + "data: [DONE]\n\n"
    provider = OpenAICompatibleProvider(
        _client(lambda r: httpx.Response(200, content=body.encode())),
        base_url="https://cloud/v1",
        api_key="k",
        model="m",
    )
    res = await provider.chat([ChatMessage("user", "ai news")], tools=TOOLS)
    assert res.tool_calls[0].name == "news_headlines" and res.tool_calls[0].arguments == {"category": "ai"}
    assert res.usage.output_tokens == 7


async def test_fallback_when_ollama_down():
    def down(request):
        raise httpx.ConnectError("refused", request=request)

    chain = FallbackLLM(
        [OllamaProvider(_client(down), base_url="http://ollama", model="qwen3:8b"), OfflineIntentRouter()],
        cooldown_seconds=60,
    )
    res = await chain.chat([ChatMessage("user", "what's the weather")], tools=TOOLS)
    assert res.offline and res.tool_calls[0].name == "weather_forecast"
    assert chain.primary_status()["ollama"]["cooling_down"] is True


@pytest.mark.parametrize(
    "chunks,expected",
    [
        (["<think>a</think>b"], "b"),
        (["<thi", "nk>x</th", "ink>yes"], "yes"),
        (["no tags"], "no tags"),
        (["a<", "b"], "a<b"),
    ],
)
def test_think_filter(chunks, expected):
    f = ThinkTagFilter()
    out = "".join(f.feed(c) for c in chunks) + f.flush()
    assert out == expected


NOW = datetime(2026, 11, 14, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
AVAILABLE = {t["function"]["name"] for t in TOOLS}


@pytest.mark.parametrize(
    "text,tool,args",
    [
        ("What's the weather in Chennai?", "weather_forecast", {"place": "Chennai"}),
        ("Find a petrol pump near my current location", "places_nearby", {"category": "petrol_pump"}),
        ("Find hotels near this location", "places_nearby", {"category": "hotel"}),
        ("Give me today's important news", "news_headlines", {}),
        ("Search YouTube for React tutorials", "youtube_search", {"query": "React tutorials"}),
        ("Play some relaxing music", "music_search", {"query": "relaxing"}),
        ("Remember that my project deadline is Friday", "memory_save", None),
        ("What did I tell you about my upcoming project?", "memory_search", {"query": "my upcoming project"}),
        ("Summarize my unread emails", "gmail_unread", {}),
        ("Create my daily briefing", "briefing_generate", {}),
        ("இன்று வானிலை எப்படி?", "weather_forecast", None),
    ],
)
def test_offline_router_intents(text, tool, args):
    result = route(text, AVAILABLE, NOW)
    assert result is not None and result[0] == tool
    if args is not None:
        for key, value in args.items():
            assert result[1][key] == value


def test_offline_router_reminder_time():
    name, args = route("Remind me to call my client tomorrow", AVAILABLE, NOW)
    assert name == "reminder_create" and args["remind_at"] == "2026-11-15T09:00"
    assert "call my client" in args["message"]
    assert parse_when("in 20 minutes", NOW).minute == 20
    assert parse_when("tomorrow at 6:30 pm", NOW).hour == 18
    assert parse_when("no time here", NOW) is None


async def test_offline_router_composes_from_tool_messages():
    router = OfflineIntentRouter()
    res = await router.chat(
        [ChatMessage("user", "weather"), ChatMessage("tool", json.dumps({"ok": True, "message": "It's 29°C."}))],
        tools=TOOLS,
    )
    assert res.content == "It's 29°C." and res.offline
    unknown = await router.chat([ChatMessage("user", "write me a poem")], tools=TOOLS)
    assert "offline mode" in unknown.content
