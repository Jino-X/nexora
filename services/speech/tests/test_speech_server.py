"""Speech server tests with fake engines (no model downloads)."""

from __future__ import annotations

import io
import wave
from typing import ClassVar

import numpy as np
import pytest
from fastapi.testclient import TestClient

from speech_server.audio import AudioError, decode_wav, guess_text_language, resample, split_sentences, validate
from speech_server.config import Settings
from speech_server.engines import SpeechEngines, STTEngine, TTSEngine
from speech_server.main import create_app


class FakeIndic(STTEngine):
    name = "indic-conformer"
    languages: ClassVar[set[str]] = {"ta", "hi"}

    def __init__(self) -> None:
        self.calls: list[tuple[int, str]] = []

    def transcribe(self, samples_16k: np.ndarray, language: str) -> str:
        self.calls.append((samples_16k.size, language))
        return "வணக்கம் Nexora"


class FakeTTS(TTSEngine):
    name = "fake-tts"
    sample_rate = 24000

    def synthesize(self, text: str, language: str, voice: str | None) -> np.ndarray:
        return np.full(2400, 0.25, dtype=np.float32)  # 0.1 s per sentence


def wav_bytes(seconds: float = 1.0, rate: int = 48000, channels: int = 2) -> bytes:
    t = np.linspace(0, seconds, int(rate * seconds), endpoint=False)
    tone = (0.3 * np.sin(2 * np.pi * 220 * t) * 32767).astype("<i2")
    data = np.repeat(tone[:, None], channels, axis=1).tobytes()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(data)
    return buf.getvalue()


@pytest.fixture
def indic() -> FakeIndic:
    return FakeIndic()


@pytest.fixture
def client(indic: FakeIndic):
    settings = Settings(_env_file=None, api_key="k", warmup=False)
    app = create_app(settings, SpeechEngines(settings, indic=indic, tts=FakeTTS()))
    with TestClient(app) as c:
        yield c


def test_decode_resample_validate():
    samples, rate = decode_wav(wav_bytes(1.0, 48000, 2))
    assert rate == 48000 and samples.ndim == 1
    out = resample(samples, rate, 16000)
    assert abs(out.size - 16000) <= 1
    with pytest.raises(AudioError):
        validate(np.zeros(100, dtype=np.float32), 16000, 30)
    with pytest.raises(AudioError):
        validate(np.zeros(16000 * 31, dtype=np.float32), 16000, 30)
    with pytest.raises(AudioError):
        decode_wav(b"RIFFnot-a-wav")


def test_sentence_split_and_script_detection():
    parts = split_sentences("வணக்கம்! இன்று மழை பெய்யும். Take an umbrella.")
    assert parts == ["வணக்கம்!", "இன்று மழை பெய்யும்.", "Take an umbrella."]
    assert all(len(p) <= 220 for p in split_sentences("word " * 200))
    assert guess_text_language("Weather is 29°C") == "en"
    assert guess_text_language("இன்று 29°C") == "ta"


def test_stt_requires_key(client):
    assert client.post("/v1/stt?language=ta", content=wav_bytes()).status_code == 401


def test_stt_routes_tamil_to_indic(client, indic):
    res = client.post("/v1/stt?language=ta", content=wav_bytes(), headers={"X-Speech-Key": "k"})
    assert res.status_code == 200
    body = res.json()
    assert body["engine"] == "indic-conformer" and body["text"].startswith("வணக்கம்")
    assert abs(indic.calls[0][0] - 16000) <= 1  # resampled to 16 kHz mono


def test_stt_english_without_whisper_is_honest_503(client):
    res = client.post("/v1/stt?language=en", content=wav_bytes(), headers={"X-Speech-Key": "k"})
    assert res.status_code == 503 and "English STT" in res.json()["detail"]


def test_stt_auto_without_lid_uses_default_language(client, indic):
    res = client.post("/v1/stt?language=auto", content=wav_bytes(), headers={"X-Speech-Key": "k"})
    assert res.json()["language"] == "ta"


def test_stt_raw_pcm_and_validation(client):
    pcm = (np.zeros(16000, dtype="<i2")).tobytes()
    assert (
        client.post("/v1/stt?language=ta&sample_rate=16000", content=pcm, headers={"X-Speech-Key": "k"}).status_code
        == 200
    )
    assert client.post("/v1/stt?language=ta", content=b"\x00", headers={"X-Speech-Key": "k"}).status_code == 422


def test_tts_streams_pcm_per_sentence(client):
    res = client.post(
        "/v1/tts", json={"text": "வணக்கம்! Good morning.", "language": "auto"}, headers={"X-Speech-Key": "k"}
    )
    assert res.status_code == 200
    assert res.headers["x-sample-rate"] == "24000" and res.headers["x-language"] == "ta"
    assert len(res.content) == 2 * 2400 * 2  # two sentences x 2400 samples x 2 bytes
