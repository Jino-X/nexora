"""Provider selection with optional fallback chains (LiveKit FallbackAdapter)."""

from __future__ import annotations

import logging

import httpx
from livekit.agents import inference, stt, tts, vad

from nexora_voice.config import Settings
from nexora_voice.providers.stt.indic_conformer import SpeechServerSTT
from nexora_voice.providers.tts.indic_tts import SpeechServerTTS

logger = logging.getLogger("nexora.voice.providers")


def _inference_language(language: str) -> str | None:
    return None if language == "auto" else language


def build_stt(settings: Settings, http: httpx.AsyncClient, vad_model: vad.VAD, language: str) -> stt.STT:
    chain: list[stt.STT] = []
    if settings.stt_provider == "speech_server":
        key = settings.speech_server_key.get_secret_value() if settings.speech_server_key else None
        chain.append(SpeechServerSTT(http, base_url=settings.speech_server_url, api_key=key, language=language))
    for model in settings.stt_fallback_models:
        chain.append(inference.STT(model=model, language=_inference_language(language) or "multi"))
    if not chain:
        raise RuntimeError("No STT provider configured (set STT_PROVIDER or STT_FALLBACK_MODELS)")
    if len(chain) == 1:
        primary = chain[0]
        # Non-streaming engines get VAD-segmented utterances.
        return primary if primary.capabilities.streaming else stt.StreamAdapter(stt=primary, vad=vad_model)
    return stt.FallbackAdapter(chain, vad=vad_model)


def build_tts(settings: Settings, http: httpx.AsyncClient, language: str, voice: str | None) -> tts.TTS:
    chain: list[tts.TTS] = []
    if settings.tts_provider == "speech_server":
        key = settings.speech_server_key.get_secret_value() if settings.speech_server_key else None
        chain.append(
            SpeechServerTTS(
                http,
                base_url=settings.speech_server_url,
                api_key=key,
                language=language,
                voice=voice,
                sample_rate=settings.tts_sample_rate,
            )
        )
    for model in settings.tts_fallback_models:
        kwargs: dict[str, object] = {"model": model}
        if settings.tts_fallback_voice:
            kwargs["voice"] = settings.tts_fallback_voice
        if lang := _inference_language(language):
            kwargs["language"] = lang
        chain.append(inference.TTS(**kwargs))  # type: ignore[arg-type]
    if not chain:
        raise RuntimeError("No TTS provider configured (set TTS_PROVIDER or TTS_FALLBACK_MODELS)")
    return chain[0] if len(chain) == 1 else tts.FallbackAdapter(chain, sample_rate=settings.tts_sample_rate)
