"""Model engines. Heavy dependencies (torch, transformers, parler-tts, faster-whisper) are imported
lazily, so the server and its tests run without them. Install with `pip install -e '.[models]'`."""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass
from typing import ClassVar

import numpy as np

from speech_server.audio import TARGET_RATE, resample, split_sentences
from speech_server.config import Settings

logger = logging.getLogger("speech.engines")


def pick_device(preference: str) -> str:
    if preference != "auto":
        return preference
    try:
        import torch

        if torch.cuda.is_available():
            return "cuda"
        if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            return "mps"
    except ImportError:
        pass
    return "cpu"


@dataclass
class Transcript:
    text: str
    language: str
    engine: str
    duration_ms: int


class STTEngine(ABC):
    name: str
    languages: set[str]

    @abstractmethod
    def transcribe(self, samples_16k: np.ndarray, language: str) -> str: ...


class TTSEngine(ABC):
    name: str
    sample_rate: int

    @abstractmethod
    def synthesize(self, text: str, language: str, voice: str | None) -> np.ndarray: ...


class IndicConformerSTT(STTEngine):
    """ai4bharat/indic-conformer-600m-multilingual (22 Indian languages, incl. Tamil; no English).
    Complete-utterance inference: there are no partial results."""

    name = "indic-conformer"
    languages: ClassVar[set[str]] = {
        "as",
        "bn",
        "brx",
        "doi",
        "gu",
        "hi",
        "kn",
        "kok",
        "ks",
        "mai",
        "ml",
        "mni",
        "mr",
        "ne",
        "or",
        "pa",
        "sa",
        "sat",
        "sd",
        "ta",
        "te",
        "ur",
    }

    def __init__(self, settings: Settings) -> None:
        import torch
        from transformers import AutoModel

        self.torch = torch
        self.decoding = settings.indic_decoding
        self.model = AutoModel.from_pretrained(settings.indic_model, trust_remote_code=True)
        logger.info("loaded %s", settings.indic_model)

    def transcribe(self, samples_16k: np.ndarray, language: str) -> str:
        wav = self.torch.from_numpy(samples_16k).unsqueeze(0)
        with self.torch.inference_mode():
            return str(self.model(wav, language, self.decoding)).strip()


class WhisperSTT(STTEngine):
    """faster-whisper for English and for spoken-language identification."""

    name = "faster-whisper"
    languages: ClassVar[set[str]] = {"en"}

    def __init__(self, settings: Settings, device: str) -> None:
        from faster_whisper import WhisperModel

        assert settings.whisper_model
        self.model = WhisperModel(
            settings.whisper_model,
            device="cuda" if device == "cuda" else "cpu",
            compute_type=settings.whisper_compute_type,
        )
        logger.info("loaded faster-whisper %s", settings.whisper_model)

    def detect_language(self, samples_16k: np.ndarray) -> tuple[str, float]:
        _, info = self.model.transcribe(samples_16k, beam_size=1, without_timestamps=True, max_new_tokens=1)
        return info.language, float(info.language_probability)

    def transcribe(self, samples_16k: np.ndarray, language: str) -> str:
        segments, _ = self.model.transcribe(
            samples_16k, language=language, beam_size=1, vad_filter=False, condition_on_previous_text=False
        )
        return " ".join(s.text.strip() for s in segments).strip()


class ParlerTTS(TTSEngine):
    """ai4bharat/indic-parler-tts: Tamil and Indian-English voices controlled by a text description."""

    name = "indic-parler-tts"

    def __init__(self, settings: Settings, device: str) -> None:
        import torch
        from parler_tts import ParlerTTSForConditionalGeneration
        from transformers import AutoTokenizer

        self.torch = torch
        self.settings = settings
        self.device = "cpu" if device == "mps" else device  # parler generation is unreliable on MPS
        self.model = ParlerTTSForConditionalGeneration.from_pretrained(settings.tts_model).to(self.device)
        self.tokenizer = AutoTokenizer.from_pretrained(settings.tts_model)
        self.description_tokenizer = AutoTokenizer.from_pretrained(self.model.config.text_encoder._name_or_path)
        self.native_rate = int(self.model.config.sampling_rate)
        self.sample_rate = settings.tts_output_sample_rate
        logger.info("loaded %s on %s (native %d Hz)", settings.tts_model, self.device, self.native_rate)

    def describe(self, language: str, voice: str | None) -> str:
        speaker = voice or (self.settings.tts_voice_ta if language == "ta" else self.settings.tts_voice_en)
        return f"{speaker} {self.settings.tts_style}"

    def synthesize(self, text: str, language: str, voice: str | None) -> np.ndarray:
        desc = self.description_tokenizer(self.describe(language, voice), return_tensors="pt").to(self.device)
        prompt = self.tokenizer(text, return_tensors="pt").to(self.device)
        with self.torch.inference_mode():
            generation = self.model.generate(
                input_ids=desc.input_ids,
                attention_mask=desc.attention_mask,
                prompt_input_ids=prompt.input_ids,
                prompt_attention_mask=prompt.attention_mask,
            )
        audio = generation.to(self.torch.float32).cpu().numpy().squeeze()
        return resample(audio, self.native_rate, self.sample_rate)


class SpeechEngines:
    """Holds loaded models (loaded once, reused across requests) and routes by language."""

    def __init__(
        self,
        settings: Settings,
        *,
        indic: STTEngine | None = None,
        whisper: STTEngine | None = None,
        tts: TTSEngine | None = None,
    ) -> None:
        self.settings = settings
        self.indic = indic
        self.whisper = whisper
        self.tts = tts

    @classmethod
    def load(cls, settings: Settings) -> SpeechEngines:
        device = pick_device(settings.device)
        indic = whisper = tts = None
        if settings.enable_stt:
            indic = IndicConformerSTT(settings)
            if settings.whisper_model:
                try:
                    whisper = WhisperSTT(settings, device)
                except ImportError:
                    logger.warning("faster-whisper not installed: English STT and language detection disabled")
        if settings.enable_tts:
            tts = ParlerTTS(settings, device)
        engines = cls(settings, indic=indic, whisper=whisper, tts=tts)
        if settings.warmup:
            engines.warmup()
        return engines

    def warmup(self) -> None:
        silence = np.zeros(TARGET_RATE, dtype=np.float32)
        started = time.perf_counter()
        if self.indic:
            self.indic.transcribe(silence, self.settings.default_language)
        if self.tts:
            self.tts.synthesize("வணக்கம்", "ta", None)
        logger.info("warm-up done in %.1fs", time.perf_counter() - started)

    def resolve_language(self, samples: np.ndarray, requested: str | None) -> str:
        lang = (requested or "auto").lower()
        if lang != "auto":
            return lang
        if isinstance(self.whisper, WhisperSTT):
            detected, prob = self.whisper.detect_language(samples)
            if prob >= 0.5:
                return detected
        return self.settings.default_language

    def transcribe(self, samples_16k: np.ndarray, requested_language: str | None) -> Transcript:
        started = time.perf_counter()
        language = self.resolve_language(samples_16k, requested_language)
        if self.indic and language in self.indic.languages:
            engine = self.indic
        elif self.whisper and language in self.whisper.languages:
            engine = self.whisper
        elif self.indic and language == "en" and not self.whisper:
            raise RuntimeError("English STT needs faster-whisper (SPEECH_WHISPER_MODEL); IndicConformer has no English")
        else:
            raise RuntimeError(f"No STT engine for language '{language}'")
        text = engine.transcribe(samples_16k, language)
        return Transcript(
            text=text, language=language, engine=engine.name, duration_ms=int((time.perf_counter() - started) * 1000)
        )

    def synthesize_stream(self, text: str, language: str, voice: str | None) -> Iterator[np.ndarray]:
        if not self.tts:
            raise RuntimeError("TTS is disabled on this server")
        for sentence in split_sentences(text):
            yield self.tts.synthesize(sentence, language, voice)
