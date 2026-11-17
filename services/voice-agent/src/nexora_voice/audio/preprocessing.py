"""Utterance preprocessing before STT: merge frames, downmix, resample to 16 kHz mono PCM16."""

from __future__ import annotations

import numpy as np
from livekit import rtc

TARGET_RATE = 16_000
MIN_SECONDS = 0.2
SILENCE_RMS = 0.004  # ~-48 dBFS; below this the utterance is treated as silence


def to_pcm16_mono_16k(frames: list[rtc.AudioFrame] | rtc.AudioFrame) -> bytes:
    frame = rtc.combine_audio_frames(frames) if isinstance(frames, list) else frames
    if frame.sample_rate != TARGET_RATE:
        resampler = rtc.AudioResampler(frame.sample_rate, TARGET_RATE, num_channels=frame.num_channels)
        out = resampler.push(frame) + resampler.flush()
        frame = rtc.combine_audio_frames(out) if out else frame
    samples = np.frombuffer(frame.data, dtype=np.int16)
    if frame.num_channels > 1:
        samples = samples.reshape(-1, frame.num_channels).mean(axis=1).astype(np.int16)
    return samples.tobytes()


def is_speech_like(pcm16: bytes) -> bool:
    """Cheap guard so silence or noise bursts don't cost an STT call."""
    samples = np.frombuffer(pcm16, dtype=np.int16).astype(np.float32) / 32768.0
    if samples.size < TARGET_RATE * MIN_SECONDS:
        return False
    return float(np.sqrt(np.mean(samples**2))) >= SILENCE_RMS
