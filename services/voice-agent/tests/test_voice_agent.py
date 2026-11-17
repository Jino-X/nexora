"""Voice agent unit tests: dispatch validation, audio preprocessing, STT/TTS/LLM adapters, SSE parsing.
Adapters are exercised through LiveKit's public interfaces against mocked HTTP services."""

from __future__ import annotations

import json
import uuid

import httpx
import numpy as np
import pytest
from livekit import rtc
from livekit.agents import APIStatusError, llm, stt

from nexora_voice.audio.preprocessing import is_speech_like, to_pcm16_mono_16k
from nexora_voice.orchestration.assistant_client import AssistantClient, parse_sse
from nexora_voice.providers.llm.nexora_api import NexoraAssistantLLM, latest_user_text
from nexora_voice.providers.stt.indic_conformer import SpeechServerSTT
from nexora_voice.providers.tts.indic_tts import SpeechServerTTS
from nexora_voice.schemas.events import InvalidDispatchError, parse_dispatch_metadata


def tone_frame(seconds: float = 0.5, rate: int = 48000, channels: int = 2, amp: float = 0.3) -> rtc.AudioFrame:
    n = int(seconds * rate)
    t = np.arange(n) / rate
    mono = (amp * np.sin(2 * np.pi * 220 * t) * 32767).astype(np.int16)
    data = np.repeat(mono[:, None], channels, axis=1).reshape(-1)
    return rtc.AudioFrame(data=data.tobytes(), sample_rate=rate, num_channels=channels, samples_per_channel=n)


# ---- dispatch metadata ---------------------------------------------------------------------------


def test_dispatch_metadata_validation():
    sid = str(uuid.uuid4())
    meta = parse_dispatch_metadata(
        json.dumps({"voice_session_id": sid, "participant_identity": "u1", "turn_mode": "manual", "language": "ta"})
    )
    assert str(meta.voice_session_id) == sid and meta.turn_mode == "manual"
    for bad in (
        None,
        "",
        "{not json",
        json.dumps({"participant_identity": "u1"}),
        json.dumps({"voice_session_id": sid}),
    ):
        with pytest.raises(InvalidDispatchError):
            parse_dispatch_metadata(bad)


# ---- preprocessing -----------------------------------------------------------------------------


def test_preprocessing_resamples_and_downmixes():
    pcm = to_pcm16_mono_16k(tone_frame(0.5, 48000, 2))
    samples = np.frombuffer(pcm, dtype=np.int16)
    assert abs(samples.size - 8000) < 400  # ~0.5 s at 16 kHz mono (resampler may hold back a few samples)
    assert is_speech_like(pcm)
    silence = to_pcm16_mono_16k(tone_frame(0.5, 16000, 1, amp=0.0))
    assert not is_speech_like(silence)


# ---- STT adapter --------------------------------------------------------------------------------


async def test_stt_adapter_posts_pcm_and_returns_final_transcript():
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["params"] = dict(request.url.params)
        seen["key"] = request.headers.get("x-speech-key")
        seen["bytes"] = len(request.content)
        return httpx.Response(
            200, json={"text": "இன்று வானிலை", "language": "ta", "engine": "indic-conformer", "duration_ms": 120}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        adapter = SpeechServerSTT(http, base_url="http://speech", api_key="k", language="ta")
        event = await adapter.recognize([tone_frame(1.0, 48000, 1)])
    assert event.type == stt.SpeechEventType.FINAL_TRANSCRIPT
    assert event.alternatives[0].text == "இன்று வானிலை" and event.alternatives[0].language == "ta"
    assert seen["params"] == {"language": "ta", "sample_rate": "16000"} and seen["key"] == "k"
    assert abs(int(seen["bytes"]) - 32000) < 1000  # 1 s of 16 kHz PCM16


async def test_stt_adapter_skips_silence_without_calling_server():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"text": "x"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        adapter = SpeechServerSTT(http, base_url="http://speech", api_key=None)
        event = await adapter.recognize([tone_frame(1.0, 16000, 1, amp=0.0)])
    assert event.alternatives[0].text == "" and calls == 0


async def test_stt_adapter_maps_server_errors():
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(503, text="no english"))
    ) as http:
        adapter = SpeechServerSTT(http, base_url="http://speech", api_key=None, language="en")
        with pytest.raises(APIStatusError):
            await adapter.recognize([tone_frame(1.0, 16000, 1)])


# ---- TTS adapter --------------------------------------------------------------------------------


async def test_tts_adapter_streams_aligned_pcm():
    pcm = (np.full(4800, 1000, dtype=np.int16)).tobytes()  # 0.2 s at 24 kHz

    class OddChunks(httpx.AsyncByteStream):
        async def __aiter__(self):
            for i in range(0, len(pcm), 333):  # odd sizes split samples across chunks
                yield pcm[i : i + 333]

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["language"] == "ta" and body["voice"] == "Jaya"
        return httpx.Response(200, stream=OddChunks(), headers={"x-sample-rate": "24000"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        adapter = SpeechServerTTS(http, base_url="http://speech", api_key=None, language="ta", voice="Jaya")
        frames = [ev.frame async for ev in adapter.synthesize("வணக்கம்")]
    assert frames and frames[0].sample_rate == 24000
    # Every sample survives the odd chunk boundaries intact (the emitter may append trailing silence).
    samples = np.concatenate([np.frombuffer(f.data, dtype=np.int16) for f in frames])
    assert int((samples == 1000).sum()) == 4800 and set(np.unique(samples)) <= {0, 1000}


# ---- LLM adapter (core API) ------------------------------------------------------------------------


def sse(*events: tuple[str, dict]) -> bytes:
    return "".join(f"id: {i}\nevent: {e}\ndata: {json.dumps(d)}\n\n" for i, (e, d) in enumerate(events, 1)).encode()


def user_ctx(text: str) -> llm.ChatContext:
    ctx = llm.ChatContext.empty()
    ctx.add_message(role="assistant", content="Hi")
    ctx.add_message(role="user", content=text)
    return ctx


async def collect(adapter: NexoraAssistantLLM, text: str) -> str:
    out = []
    async with adapter.chat(chat_ctx=user_ctx(text)) as stream:
        async for chunk in stream:
            if chunk.delta and chunk.delta.content:
                out.append(chunk.delta.content)
    return "".join(out)


async def test_llm_adapter_streams_tokens_and_relays_tool_events():
    relayed: list[str] = []
    requests: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        assert request.headers["x-nexora-internal-key"] == "ik"
        return httpx.Response(
            200,
            content=sse(
                ("run_started", {"run_id": "r"}),
                ("tool_start", {"tool": "weather_forecast"}),
                ("tool_end", {"tool": "weather_forecast", "ok": True}),
                ("token", {"text": "It's 29"}),
                ("token", {"text": "°C."}),
                ("message_end", {"content": "It's 29°C."}),
                ("done", {"status": "completed"}),
            ),
            headers={"content-type": "text/event-stream"},
        )

    async def relay(ev):
        relayed.append(ev.event)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = AssistantClient(http, base_url="http://api", internal_key="ik")
        adapter = NexoraAssistantLLM(
            client, session_id="s1", room_name="nxr-1", participant_identity="u1", language="ta", on_event=relay
        )
        text = await collect(adapter, "இன்று வானிலை?")
    assert text == "It's 29°C."
    assert requests[0] == {
        "session_id": "s1",
        "room_name": "nxr-1",
        "participant_identity": "u1",
        "text": "இன்று வானிலை?",
        "language": "ta",
    }
    assert relayed == ["tool_start", "tool_end", "message_end"]


async def test_llm_adapter_speaks_offline_answer_from_message_end():
    body = sse(("run_started", {}), ("message_end", {"content": "Reminder set."}), ("done", {}))
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=body))) as http:
        adapter = NexoraAssistantLLM(
            AssistantClient(http, base_url="http://api", internal_key="ik"),
            session_id="s",
            room_name="r",
            participant_identity="u",
            language=None,
        )
        assert await collect(adapter, "remind me") == "Reminder set."


async def test_llm_adapter_apologises_when_api_is_down():
    def down(request):
        raise httpx.ConnectError("refused", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(down)) as http:
        adapter = NexoraAssistantLLM(
            AssistantClient(http, base_url="http://api", internal_key="ik"),
            session_id="s",
            room_name="r",
            participant_identity="u",
            language="en",
        )
        text = []
        with pytest.raises(Exception):  # noqa: B017 - connection errors still surface after the apology
            async with adapter.chat(chat_ctx=user_ctx("hello")) as stream:
                async for chunk in stream:
                    if chunk.delta and chunk.delta.content:
                        text.append(chunk.delta.content)
        assert "Sorry" in "".join(text)


async def test_llm_adapter_stops_on_closed_session():
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(409, text="closed"))) as http:
        adapter = NexoraAssistantLLM(
            AssistantClient(http, base_url="http://api", internal_key="ik"),
            session_id="s",
            room_name="r",
            participant_identity="u",
            language="en",
        )
        with pytest.raises(APIStatusError):
            await collect(adapter, "hello")


def test_latest_user_text():
    ctx = user_ctx("first")
    ctx.add_message(role="user", content="second")
    assert latest_user_text(ctx) == "second"
    assert latest_user_text(llm.ChatContext.empty()) == ""


async def test_parse_sse_handles_comments_and_multiline():
    async def lines():
        for line in [": keep-alive", "", "id: 3", "event: token", 'data: {"text":', 'data: "hi"}', ""]:
            yield line

    events = [e async for e in parse_sse(lines())]
    assert len(events) == 1 and events[0].id == 3 and events[0].data == {"text": "hi"}
