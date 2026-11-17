"""LiveKit TTS adapter for the Nexora speech server (AI4Bharat Indic Parler-TTS).

The server synthesizes sentence by sentence and streams raw PCM16 as each sentence finishes. Audio
is pushed to LiveKit as it arrives, so playback starts after the first sentence. Interruption
cancels this task, which closes the HTTP stream and stops synthesis server-side."""

from __future__ import annotations

import httpx
from livekit.agents import APIConnectionError, APIConnectOptions, APIStatusError, APITimeoutError, tts
from livekit.agents.utils import shortuuid


class SpeechServerTTS(tts.TTS):
    def __init__(
        self,
        http: httpx.AsyncClient,
        *,
        base_url: str,
        api_key: str | None,
        language: str = "auto",
        voice: str | None = None,
        sample_rate: int = 24000,
    ) -> None:
        super().__init__(capabilities=tts.TTSCapabilities(streaming=False), sample_rate=sample_rate, num_channels=1)
        self._http = http
        self._url = f"{base_url.rstrip('/')}/v1/tts"
        self._headers = {"X-Speech-Key": api_key} if api_key else {}
        self.language = language
        self.voice = voice

    @property
    def model(self) -> str:
        return "indic-parler-tts"

    @property
    def provider(self) -> str:
        return "nexora-speech"

    def synthesize(self, text: str, *, conn_options: APIConnectOptions = APIConnectOptions()) -> SpeechServerStream:
        return SpeechServerStream(tts=self, input_text=text, conn_options=conn_options)


class SpeechServerStream(tts.ChunkedStream):
    def __init__(self, *, tts: SpeechServerTTS, input_text: str, conn_options: APIConnectOptions) -> None:
        super().__init__(tts=tts, input_text=input_text, conn_options=conn_options)
        self._server = tts

    async def _run(self, output_emitter: tts.AudioEmitter) -> None:
        output_emitter.initialize(
            request_id=shortuuid(), sample_rate=self._server.sample_rate, num_channels=1, mime_type="audio/pcm"
        )
        payload = {"text": self._input_text, "language": self._server.language, "voice": self._server.voice}
        carry = b""
        try:
            async with self._server._http.stream(
                "POST",
                self._server._url,
                json=payload,
                headers=self._server._headers,
                timeout=httpx.Timeout(max(self._conn_options.timeout, 30.0), connect=5.0),
            ) as res:
                if res.status_code >= 400:
                    body = (await res.aread()).decode(errors="replace")[:200]
                    raise APIStatusError(
                        f"speech server TTS error: {body}",
                        status_code=res.status_code,
                        retryable=res.status_code >= 500 and res.status_code != 503,
                    )
                rate = int(res.headers.get("x-sample-rate", self._server.sample_rate))
                if rate != self._server.sample_rate:
                    raise APIStatusError(f"unexpected TTS sample rate {rate}", retryable=False)
                async for chunk in res.aiter_bytes():
                    data = carry + chunk
                    usable = len(data) - (len(data) % 2)  # keep PCM16 sample alignment
                    if usable:
                        output_emitter.push(data[:usable])
                    carry = data[usable:]
        except httpx.TimeoutException as exc:
            raise APITimeoutError("speech server TTS timed out") from exc
        except httpx.HTTPError as exc:
            raise APIConnectionError(f"speech server unreachable: {type(exc).__name__}") from exc
        output_emitter.flush()
