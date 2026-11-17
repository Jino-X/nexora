"""Voice agent settings. LIVEKIT_URL / LIVEKIT_API_KEY / LIVEKIT_API_SECRET are read by the LiveKit
Agents CLI directly."""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", ".env.local"), extra="ignore")

    livekit_agent_name: str = "nexora-voice"

    # Core API (the voice agent never talks to integrations or the LLM directly)
    nexora_api_url: str = "http://localhost:8000"
    nexora_internal_service_key: SecretStr | None = None
    assistant_timeout_seconds: float = 60.0

    # Speech providers
    stt_provider: Literal["speech_server", "livekit_inference"] = "speech_server"
    tts_provider: Literal["speech_server", "livekit_inference"] = "speech_server"
    speech_server_url: str = "http://localhost:8100"
    speech_server_key: SecretStr | None = None
    # Optional LiveKit Inference fallbacks (LiveKit Cloud, billed per use), e.g. "deepgram/nova-3"
    stt_fallback_models: Annotated[list[str], NoDecode] = Field(default_factory=list)
    tts_fallback_models: Annotated[list[str], NoDecode] = Field(default_factory=list)
    tts_fallback_voice: str | None = None
    tts_sample_rate: int = 24000

    # Turn handling
    turn_detector: Literal["multilingual", "vad"] = "multilingual"
    min_endpointing_delay: float = 0.5
    max_endpointing_delay: float = 3.0

    # Session limits
    max_session_seconds: int = 900
    idle_timeout_seconds: int = 90
    wake_word_no_speech_seconds: int = 8  # end wake-word sessions with no speech (false triggers)

    @field_validator("stt_fallback_models", "tts_fallback_models", mode="before")
    @classmethod
    def _csv(cls, value: object) -> object:
        if isinstance(value, str):
            return [v.strip() for v in value.split(",") if v.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
