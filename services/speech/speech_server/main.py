"""Nexora speech server: IndicConformer STT and Indic Parler-TTS behind a small internal HTTP API.

Run: uvicorn speech_server.main:create_app --factory --port 8100
Endpoints (all need X-Speech-Key when SPEECH_API_KEY is set):
  GET  /health
  POST /v1/stt?language=ta|en|auto&sample_rate=16000   body: audio/wav or audio/L16 (PCM16 mono)
  POST /v1/tts   {"text": "...", "language": "ta|en|auto", "voice": "Jaya"} -> chunked audio/L16 stream
"""

import asyncio
import hmac
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from speech_server.audio import (
    AudioError,
    decode_wav,
    float_to_pcm16,
    guess_text_language,
    pcm16_to_float,
    resample,
    validate,
)
from speech_server.config import Settings, get_settings
from speech_server.engines import SpeechEngines

logger = logging.getLogger("speech")


class TTSRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    language: str = "auto"
    voice: str | None = Field(None, max_length=64)


def create_app(settings: Settings | None = None, engines: SpeechEngines | None = None) -> FastAPI:
    settings = settings or get_settings()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    # Inference is CPU/GPU bound: one request at a time per engine keeps latency predictable.
    stt_lock, tts_lock = asyncio.Lock(), asyncio.Lock()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.engines = engines or await asyncio.to_thread(SpeechEngines.load, settings)
        yield

    app = FastAPI(title="Nexora Speech", version="0.1.0", lifespan=lifespan)

    def require_key(x_speech_key: Annotated[str | None, Header()] = None) -> None:
        expected = settings.api_key.get_secret_value() if settings.api_key else None
        if expected and not (x_speech_key and hmac.compare_digest(x_speech_key, expected)):
            raise HTTPException(401, "invalid speech key")

    def get_engines(request: Request) -> SpeechEngines:
        return request.app.state.engines

    @app.get("/health")
    async def health(request: Request) -> dict[str, object]:
        e: SpeechEngines | None = getattr(request.app.state, "engines", None)
        return {
            "status": "ok" if e else "loading",
            "stt": {"indic": bool(e and e.indic), "whisper": bool(e and e.whisper)},
            "tts": {"enabled": bool(e and e.tts), "sample_rate": e.tts.sample_rate if e and e.tts else None},
        }

    @app.post("/v1/stt", dependencies=[Depends(require_key)])
    async def stt(
        request: Request,
        engines: Annotated[SpeechEngines, Depends(get_engines)],
        language: Annotated[str, Query(max_length=8)] = "auto",
        sample_rate: Annotated[int, Query(ge=8000, le=48000)] = 16000,
    ) -> dict[str, object]:
        body = await request.body()
        try:
            if body[:4] == b"RIFF":
                samples, rate = decode_wav(body)
            else:
                samples, rate = pcm16_to_float(body), sample_rate
            seconds = validate(samples, rate, settings.max_audio_seconds)
            samples = resample(samples, rate)
        except AudioError as exc:
            raise HTTPException(422, str(exc)) from exc
        async with stt_lock:
            try:
                result = await asyncio.to_thread(engines.transcribe, samples, language)
            except RuntimeError as exc:
                raise HTTPException(503, str(exc)) from exc
        return {
            "text": result.text,
            "language": result.language,
            "engine": result.engine,
            "duration_ms": result.duration_ms,
            "audio_seconds": round(seconds, 2),
        }

    @app.post("/v1/tts", dependencies=[Depends(require_key)])
    async def tts(body: TTSRequest, engines: Annotated[SpeechEngines, Depends(get_engines)]) -> StreamingResponse:
        if not engines.tts:
            raise HTTPException(503, "TTS is disabled on this server")
        text = body.text.strip()[: settings.max_tts_chars]
        language = guess_text_language(text) if body.language == "auto" else body.language

        async def chunks() -> AsyncIterator[bytes]:
            iterator = engines.synthesize_stream(text, language, body.voice)
            while True:
                async with tts_lock:
                    audio = await asyncio.to_thread(next, iterator, None)
                if audio is None:
                    break
                yield float_to_pcm16(audio)

        return StreamingResponse(
            chunks(),
            media_type="audio/L16",
            headers={"X-Sample-Rate": str(engines.tts.sample_rate), "X-Channels": "1", "X-Language": language},
        )

    return app
