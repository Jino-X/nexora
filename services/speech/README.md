# Nexora speech server

Internal HTTP service that keeps the speech models loaded and warm:

* **STT:** `ai4bharat/indic-conformer-600m-multilingual` for Tamil and 21 other Indic languages
  (complete-utterance inference), plus optional **faster-whisper** for English and spoken-language
  identification. IndicConformer has no English model.
* **TTS:** `ai4bharat/indic-parler-tts`, synthesized sentence by sentence and streamed as PCM16.

```bash
python3.13 -m venv .venv
.venv/bin/pip install -e ".[dev]"            # API + tests only
.venv/bin/pip install -e ".[models]"         # torch, transformers, onnxruntime, parler-tts, faster-whisper
.venv/bin/uvicorn speech_server.main:create_app --factory --port 8100
.venv/bin/python -m pytest -q                # fake engines, no downloads
```

| Endpoint | |
| --- | --- |
| `GET /health` | Which engines are loaded |
| `POST /v1/stt?language=ta\|en\|auto&sample_rate=16000` | Body is WAV or raw PCM16 mono → `{text, language, engine, duration_ms}` |
| `POST /v1/tts` | `{text, language: ta\|en\|auto, voice?}` → chunked `audio/L16` (header `X-Sample-Rate`) |

Notes:

* A GPU is strongly recommended (`SPEECH_DEVICE=cuda`). Parler-TTS on CPU takes seconds per sentence.
* If parler-tts and IndicConformer need conflicting `transformers` versions, run two instances:
  one with `SPEECH_ENABLE_TTS=false` and one with `SPEECH_ENABLE_STT=false`.
* Requests are processed one at a time per engine, so latency stays predictable. Scale by running
  more instances.
* Set `SPEECH_API_KEY` and never expose the service publicly.
