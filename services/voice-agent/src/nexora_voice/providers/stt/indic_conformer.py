"""LiveKit STT adapter for the Nexora speech server (AI4Bharat IndicConformer, plus faster-whisper for
English and language ID).

IndicConformer transcribes a complete utterance: it has no partial or interim results. This adapter
therefore declares `streaming=False`, and the session wraps it in a VAD-driven `StreamAdapter`,
which sends each utterance once the speaker pauses."""

from __future__ import annotations

import logging

import httpx
from livekit.agents import APIConnectionError, APIConnectOptions, APIStatusError, APITimeoutError, stt
from livekit.agents.types import NOT_GIVEN, NotGivenOr
from livekit.agents.utils import AudioBuffer, shortuuid

from nexora_voice.audio.preprocessing import TARGET_RATE, is_speech_like, to_pcm16_mono_16k

logger = logging.getLogger("nexora.voice.stt")


class SpeechServerSTT(stt.STT):
    def __init__(self, http: httpx.AsyncClient, *, base_url: str, api_key: str | None, language: str = "auto") -> None:
        super().__init__(capabilities=stt.STTCapabilities(streaming=False, interim_results=False))
        self._http = http
        self._url = f"{base_url.rstrip('/')}/v1/stt"
        self._headers = {"Content-Type": "audio/L16"} | ({"X-Speech-Key": api_key} if api_key else {})
        self._language = language

    @property
    def model(self) -> str:
        return "indic-conformer-600m"

    @property
    def provider(self) -> str:
        return "nexora-speech"

    async def _recognize_impl(
        self, buffer: AudioBuffer, *, language: NotGivenOr[str] = NOT_GIVEN, conn_options: APIConnectOptions
    ) -> stt.SpeechEvent:
        pcm = to_pcm16_mono_16k(buffer)
        request_id = shortuuid()
        if not is_speech_like(pcm):
            return stt.SpeechEvent(
                type=stt.SpeechEventType.FINAL_TRANSCRIPT,
                request_id=request_id,
                alternatives=[stt.SpeechData(language=self._language, text="")],
            )
        lang = language if isinstance(language, str) and language else self._language
        try:
            res = await self._http.post(
                self._url,
                params={"language": lang, "sample_rate": TARGET_RATE},
                content=pcm,
                headers=self._headers,
                timeout=conn_options.timeout,
            )
        except httpx.TimeoutException as exc:
            raise APITimeoutError("speech server timed out") from exc
        except httpx.HTTPError as exc:
            raise APIConnectionError(f"speech server unreachable: {type(exc).__name__}") from exc
        if res.status_code >= 400:
            raise APIStatusError(
                f"speech server error: {res.text[:200]}",
                status_code=res.status_code,
                retryable=res.status_code >= 500 and res.status_code != 503,
            )
        body = res.json()
        logger.debug("stt %s %.0fms", body.get("engine"), body.get("duration_ms", 0))
        return stt.SpeechEvent(
            type=stt.SpeechEventType.FINAL_TRANSCRIPT,
            request_id=request_id,
            alternatives=[
                stt.SpeechData(language=body.get("language") or lang, text=body.get("text", ""), confidence=1.0)
            ],
        )
