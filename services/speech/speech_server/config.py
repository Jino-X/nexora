"""Speech server settings."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="SPEECH_", extra="ignore")

    # Shared secret with the voice agent (the server must not be exposed publicly).
    api_key: SecretStr | None = None
    device: str = "auto"  # auto | cpu | cuda | mps

    enable_stt: bool = True
    enable_tts: bool = True
    warmup: bool = True

    # STT
    indic_model: str = "ai4bharat/indic-conformer-600m-multilingual"
    indic_decoding: Literal["ctc", "rnnt"] = "ctc"
    # Optional English + language-ID engine (IndicConformer has no English model).
    whisper_model: str | None = "small"
    whisper_compute_type: str = "int8"
    default_language: str = "ta"
    max_audio_seconds: float = 30.0

    # TTS
    tts_model: str = "ai4bharat/indic-parler-tts"
    tts_voice_ta: str = "Jaya"
    tts_voice_en: str = "Thoma"
    tts_style: str = "speaks at a moderate pace with a clear, friendly tone. The recording is very high quality with no background noise."
    tts_output_sample_rate: int = 24000
    max_tts_chars: int = 1200


@lru_cache
def get_settings() -> Settings:
    return Settings()
