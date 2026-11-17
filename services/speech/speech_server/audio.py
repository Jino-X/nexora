"""Audio validation and conversion (numpy only, so it is testable without the model stack)."""

from __future__ import annotations

import io
import re
import wave

import numpy as np

TARGET_RATE = 16_000


class AudioError(ValueError):
    pass


def decode_wav(data: bytes) -> tuple[np.ndarray, int]:
    """Decode a PCM WAV into float32 mono samples in [-1, 1]."""
    try:
        with wave.open(io.BytesIO(data), "rb") as wf:
            channels, width, rate, frames = wf.getnchannels(), wf.getsampwidth(), wf.getframerate(), wf.getnframes()
            raw = wf.readframes(frames)
    except (wave.Error, EOFError) as exc:
        raise AudioError(f"Invalid WAV data: {exc}") from exc
    if width != 2:
        raise AudioError("Only 16-bit PCM WAV is supported")
    if not 8000 <= rate <= 48000:
        raise AudioError(f"Unsupported sample rate {rate}")
    samples = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)
    return samples, rate


def pcm16_to_float(data: bytes) -> np.ndarray:
    if len(data) % 2:
        raise AudioError("PCM16 payload has an odd number of bytes")
    return np.frombuffer(data, dtype="<i2").astype(np.float32) / 32768.0


def resample(samples: np.ndarray, src_rate: int, dst_rate: int = TARGET_RATE) -> np.ndarray:
    """Band-limited enough for speech at these rates: linear interpolation after a simple low-pass."""
    if src_rate == dst_rate or samples.size == 0:
        return samples.astype(np.float32)
    if src_rate > dst_rate:
        # Moving-average low-pass to reduce aliasing before decimation.
        k = max(1, round(src_rate / dst_rate))
        if k > 1:
            samples = np.convolve(samples, np.ones(k, dtype=np.float32) / k, mode="same")
    duration = samples.size / src_rate
    n_out = round(duration * dst_rate)
    x_old = np.linspace(0.0, duration, num=samples.size, endpoint=False)
    x_new = np.linspace(0.0, duration, num=n_out, endpoint=False)
    return np.interp(x_new, x_old, samples).astype(np.float32)


def validate(samples: np.ndarray, rate: int, max_seconds: float) -> float:
    seconds = samples.size / rate
    if seconds < 0.15:
        raise AudioError("Audio too short")
    if seconds > max_seconds:
        raise AudioError(f"Audio too long ({seconds:.1f}s > {max_seconds:.0f}s)")
    if not np.isfinite(samples).all():
        raise AudioError("Audio contains invalid samples")
    return seconds


def float_to_pcm16(samples: np.ndarray) -> bytes:
    clipped = np.clip(samples, -1.0, 1.0)
    return (clipped * 32767.0).astype("<i2").tobytes()


SENTENCE_RE = re.compile(r"(?<=[.!?।|])\s+|\n+")


def split_sentences(text: str, max_chars: int = 220) -> list[str]:
    """Split text for chunked TTS: sentence boundaries (incl. Indic danda), then soft-wrap long ones."""
    out: list[str] = []
    for sentence in SENTENCE_RE.split(text.strip()):
        sentence = sentence.strip()
        while len(sentence) > max_chars:
            cut = sentence.rfind(",", 0, max_chars)
            cut = cut if cut > max_chars // 3 else sentence.rfind(" ", 0, max_chars)
            cut = cut if cut > 0 else max_chars
            out.append(sentence[: cut + 1].strip())
            sentence = sentence[cut + 1 :].strip()
        if sentence:
            out.append(sentence)
    return out


TAMIL_RE = re.compile(r"[஀-௿]")


def guess_text_language(text: str) -> str:
    """Pick a TTS voice language from the script: any Tamil characters -> ta, else en."""
    return "ta" if TAMIL_RE.search(text) else "en"
